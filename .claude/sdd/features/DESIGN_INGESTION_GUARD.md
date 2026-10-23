# DESIGN: Ingestion Guard

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | INGESTION_GUARD |
| **Date** | 2026-10-23 |
| **Author** | Christian |
| **Source** | DEFINE_INGESTION_GUARD.md (Ready for Design, commit 5564334); BRAINSTORM_INGESTION_GUARD.md (D-46 to D-57, F-32 to F-45, spike 07 results); archived `DESIGN_PEAK_MODEL_CONCURRENCY.md` (layout, guards G-13 to G-21, DA-19 to DA-26); ADR 0008, ADR 0012; `src/smart_meter_peak_prediction/pipeline_guard.py`; `notebooks/check_pipeline_idle.py`; `resources/smart_meter_ingestion.job.yml`; `resources/smart_meter_peak_model.job.yml`; `tests/test_pipeline_guard.py`, `tests/test_bundle_config.py`, `tests/test_peak_bundle.py`, `tests/test_secrets_hygiene.py`, `tests/test_integration_layout.py`, `tests/test_peak_concurrency_docs.py`; `tests/integration/` (conftest, `test_deployment.py`, `test_bronze_ingestion.py`, `test_peak_concurrency.py`, `test_peak_deployment.py`); `docs/runbooks/meter_ingestion.md`, `docs/runbooks/peak_model.md`; `.claude/kb/databricks/` |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

**ID numbering.** Guards continue after PEAK_MODEL_CONCURRENCY (last G-21): G-22 to G-27. Design
assumptions continue after DA-26: DA-27 to DA-33. User items continue after U-05; U-06 is not used
(nothing needs the user). FR, NFR, AC, D, A and F ids are those of DEFINE and BRAINSTORM.

---

## Overview

The ingestion job `smart_meter_ingestion` gets one new task, `check_silver_gold_idle`, between the
two ingest tasks and `refresh_silver_gold`, and `ingest_kafka` gets `disable_auto_optimization: true`.
The check is a serverless notebook task on a new job environment `ingestion_check_env` (environment
version 2, the runtime spike 06 and spike 07 validated), with no retries, auto-optimization off and a
300 s timeout. It reads only the pipeline `smart_meter_silver_gold`, once, and decides with the
pipeline half of `pipeline_guard` that the peak job already uses: `IDLE` or `FAILED` with no active
update passes; anything else is busy; an unreadable, foreign or deleted pipeline fails closed. A
busy result fails the task with a message naming the update, the caller and the action, so
`refresh_silver_gold` ends `UPSTREAM_FAILED` and Bronze is kept. `pipeline_guard` gains a separate
pipeline-only entry point appended to the module; every shipped line, the peak notebook, the peak job
and the 28 shipped guard tests stay byte-identical (ADR 0013).

---

## Architecture

```text
 DATABRICKS FREE EDITION (serverless, target dev)

 Job smart_meter_ingestion (daily 06:00 UTC, max 1 concurrent run, job timeout 3600 s)
 +-------------------------------------------------------------------------------------------+
 | [0] setup_catalog (unchanged: 600 s, 1 retry)                                             |
 |        |                                                                                  |
 | [1] ingest_files (unchanged: 1800 s, 1 retry)   [2] ingest_kafka (840 s, 0 retries,       |
 |        |                                             disable_auto_optimization: true  NEW)|
 |        +------------------+-------------------------------+                               |
 |                           v                                                               |
 | [3] check_silver_gold_idle  NEW (notebook, env ingestion_check_env = version 2,           |
 |       0 retries, auto-optimization off, 300 s; parameters: src_path, pipeline_id)         |
 |       WorkspaceClient(config=Config(**CLIENT_LIMITS))  (job identity, no secret)          |
 |       pipeline_guard.run_pipeline_check(factory, pipeline_id, caller=INGESTION_CALLER)    |
 |         READ ONLY, ONE CALL:  pipelines.get(pipeline_id)                                  |
 |           name == smart_meter_silver_gold (prefix stripped)          G-15 (reused)        |
 |           state IDLE/FAILED pass; DELETED unusable; other busy       G-21 (reused)        |
 |           latest_updates: any state not COMPLETED/FAILED/CANCELED    G-17 (reused)        |
 |       idle    -> exit value JSON (outcome idle, checked_at ...Z, pipeline id/name/state)  |
 |       busy    -> raise PipelineGuardError(FR-47 message)  -> task FAILED                  |
 |       unknown -> raise PipelineGuardError(FR-48 message)  -> task FAILED (fail closed)    |
 |                           |                                                               |
 | [4] refresh_silver_gold (unchanged pipeline_task: 2700 s, 0 retries, full_refresh false;  |
 |       depends on [3] only) ---------------------------------------------------------+     |
 +-------------------------------------------------------------------------------------|-----+
   levels: L0 {setup_catalog} L1 {ingest_files, ingest_kafka} L2 {check} L3 {refresh}  |
   widest level: 2                                                                     v
                                                       pipeline smart_meter_silver_gold
                                                       (one update at a time)          ^
 Job smart_meter_peak_model (08:00 UTC; UNCHANGED, tag v0.3.0)                         |
   check_pipeline_idle (reads ingestion runs + pipeline) -> refresh_silver_gold -------+
   ... other peak tasks unchanged

 Outcomes of an ingestion run:
   ingest task fails       -> check and refresh end UPSTREAM_FAILED (never started)
   check busy or unknown   -> refresh ends UPSTREAM_FAILED; Bronze rows of this run are kept
   check idle              -> refresh starts one update (race window C-11 remains)
```

No bundle reference from the ingestion job to any job: the peak job already references the
ingestion job id, and a reference back makes `bundle deploy` fail with a Terraform cycle (A-30).

---

## Components

Package path `src/smart_meter_peak_prediction/` is abbreviated `pkg/`.

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Guard library, pipeline-only mode (`pkg/pipeline_guard.py`, appended) | `Caller` (job, task, schedule, next refresh), `INGESTION_CALLER`, `PIPELINE_READ_CALLS`, `PipelineReport` (`ok`, `message()`, `exit_value()`), `check_pipeline`, `run_pipeline_check`, `enforce_pipeline`. Reuses the shipped `_read_pipeline` (G-15, G-17, G-21), `_describe_error` (redaction, 200 characters), `utc_text`, `_checked_at`, `_valid_id`, `_shown`, `ActiveUpdate`, `Unreadable`, `CLIENT_LIMITS` unchanged. Standard library only, no `sleep` | Python 3.11 stdlib | FR-46 to FR-50, NFR-25 to NFR-29 |
| Guard library, peak mode (`pkg/pipeline_guard.py`, existing lines) | Unchanged: `check`, `run`, `enforce`, `GuardReport`, constants, messages and exit value as at `v0.3.0`; the diff against the tag is additions only | Python 3.11 stdlib | FR-50 |
| Reverse pre-check notebook (`notebooks/check_silver_gold_idle.py`) | Wiring only: `src_path`, widget `pipeline_id`, UTC session setting and assertion, prints the SDK version, `run_pipeline_check` with a `Config`-based client, prints the message, `enforce_pipeline` (raises on busy or unknown), `dbutils.notebook.exit(json)`. No `try` (I-14), no `%pip`, no secrets | Databricks notebook, serverless environment version 2 | FR-45 to FR-49, NFR-25, NFR-27, NFR-29 |
| Ingestion job resource (`resources/smart_meter_ingestion.job.yml`) | Job environment `ingestion_check_env`; task `check_silver_gold_idle`; `refresh_silver_gold` depends on it; `disable_auto_optimization: true` on `ingest_kafka`; comments | Databricks Asset Bundles | FR-43 to FR-45, NFR-24, NFR-28 |
| v0.1.0 job fixture (`tests/support/ingestion_job_v0.1.0.yml`) | Byte copy of the v0.1.0 ingestion job file (digest equal to the shipped v0.1.0 pin), so the structural comparison of AC-85 also runs in a clone without tags (CI) | YAML | FR-51 |
| Unit tests | Pipeline-only guard with a recording fake (AC-86 to AC-91), peak-mode regression (AC-92), bundle graph, settings, environments, pins and structural diff (AC-81 to AC-85), secrets and notebook rules (AC-93), docs and ADRs (AC-99); updates of the shipped tests that encode the v0.1.0 graph (OD-22) | pytest | AC-81 to AC-93, AC-99 |
| Live tests | Deployed job read back (AC-94), Kafka outage with one attempt (AC-95), full run (AC-96), busy refusal and rerun (AC-97), the unchanged peak concurrency suite plus the ingestion side of its AC-74 run (AC-98); `PeakRunner` reused as is (its `run` accepts any job) | pytest, databricks-sdk | AC-94 to AC-98 |
| Runbooks, ADRs, README | Ingestion runbook: the check, its messages, the action, the `--only` rule, evidence order. Peak runbook: cross-reference. ADR 0013 (this phase), dated notes on ADR 0012 and ADR 0008 (build) | Markdown | FR-53 |

---

## Data Model

This feature creates, writes and changes no table, view, volume, contract or model. It reads one
platform object and produces one task outcome per ingestion run. Bronze, Silver, Gold and the
PEAK_MODEL tables and `docs/contracts/` are unchanged.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| Pipeline `smart_meter_silver_gold` (Pipelines API `pipelines.get`, read) | platform metadata | One pipeline | `pipeline_id` | - | Fields used: `name` (development prefix stripped), `state` (overall state, `.value` string), `latest_updates[].update_id`, `.state`, `.creation_time` (ISO 8601 with `Z`, spike 06) |
| Check outcome | task run | One `check_silver_gold_idle` task run per ingestion job run | job `run_id`, task `run_id` | - | `SUCCESS` with the exit value below, or `FAILED` with the FR-47 or FR-48 message as the task error |

Exit value on success (keys fixed, values illustrative):

```json
{
  "outcome": "idle",
  "checked_at": "2026-10-24T06:07:12Z",
  "caller": {"job": "smart_meter_ingestion", "task": "check_silver_gold_idle"},
  "pipeline": {"pipeline_id": "0a1b-...", "name": "smart_meter_silver_gold", "state": "IDLE",
               "latest_update": {"update_id": "3c4d-...", "state": "COMPLETED"}}
}
```

`latest_update` is `null` when `latest_updates` is absent or empty. A report that is not ok has
`outcome` `busy` (blocked) or `unknown` (only unreadable items), as in peak mode; the notebook never
exits with it because `enforce_pipeline` raises first.

Failure message, busy (FR-47; every blocker on its own line; all times UTC with `Z`):

```text
check_silver_gold_idle stopped smart_meter_ingestion before refresh_silver_gold: the shared pipeline is busy (checked at 2026-10-24T06:07:12Z).
Blocking:
  - pipeline smart_meter_silver_gold (pipeline id 0a1b-...): update 3c4d-..., state RUNNING, pipeline state RUNNING, created 2026-10-24T06:05:58Z
refresh_silver_gold did not start; the Bronze data of this run is kept.
Action: wait until the update named above ends, then rerun smart_meter_ingestion.
Without action, the smart_meter_peak_model run at 08:00 UTC refreshes the pipeline from Bronze, and the next smart_meter_ingestion run (06:00 UTC) checks again.
```

When only the overall state is busy (G-21), the blocking line reads
`pipeline smart_meter_silver_gold (pipeline id 0a1b-...): pipeline state RUNNING, no active update is listed in latest_updates`
(a missing state reads `pipeline state not reported`). A creation time that is naive or cannot be
parsed reads `creation time not reported`.

Failure message, fail closed (FR-48):

```text
check_silver_gold_idle could not establish the state of the shared pipeline and fails closed (checked at 2026-10-24T06:07:12Z).
Could not read:
  - pipeline smart_meter_silver_gold (pipeline id 0a1b-...): pipeline: PermissionDenied (PERMISSION_DENIED): <first line of the API error, redacted, at most 200 characters>
refresh_silver_gold did not start; the Bronze data of this run is kept.
Action: fix the cause, then rerun smart_meter_ingestion (the cause is named above: deployment, permission or API availability).
Without action, the next smart_meter_ingestion run (06:00 UTC) checks again.
```

The read labels are those of the shipped `_read_pipeline` (`pipeline`, `pipeline state` for
`DELETED, not usable`, `another pipeline`) plus `pipeline_id` (id missing or not resolved) and
`workspace client` (client construction failed). When blocking and unreadable items both exist
(for example `DELETED` with an active update listed), the message has both blocks and the action
reads "wait until the update named above ends and fix the cause named under 'Could not read', then
rerun smart_meter_ingestion". The message never contains `check_pipeline_idle`, a job id or "rerun
smart_meter_peak_model".

### Data quality rules (guards)

There is no profiled data, so the source column names the requirement, decision or finding. Every
guard ends the check task `FAILED` before `refresh_silver_gold` starts.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| G-22 the pipeline id is non-empty after stripping and contains no unresolved bundle reference marker (a dollar sign followed by an opening brace), checked with the shipped `_valid_id` | task parameter `pipeline_id` | `fail` (FR-48 message: `pipeline_id: id missing or not resolved`; no API call) | FR-48, D-45, AC-89 |
| G-23 read-only and single read: `check_pipeline` calls only `pipelines.get`, exactly once (`PIPELINE_READ_CALLS = ("pipelines.get",)`); never `jobs.*`; no loop, no `sleep`. The unit fake records and raises on any other attribute | client | `fail` in tests (AC-86, AC-87, AC-89) | FR-46, FR-49, NFR-28, D-48 |
| G-24 the decision reuses the shipped `_read_pipeline` unchanged: G-15 identity (another name: unreadable), G-21 overall state (`IDLE`, `FAILED` pass; `DELETED` unreadable; any other, unknown or missing value busy), G-17 updates (any entry not `COMPLETED`, `FAILED`, `CANCELED`, including a missing or unknown state, is active). The report is ok only with no active update, a pass state and nothing unreadable | pipeline state | `fail` (busy: FR-47; `DELETED` or foreign pipeline: FR-48, fail closed) | FR-46, FR-48, G-21, AC-87, AC-88, AC-89 |
| G-25 every failure to read becomes an unreadable item, never success: `_read_pipeline` wraps `pipelines.get` (G-18 pattern); `run_pipeline_check` turns a client-factory exception into an unreadable `workspace client` item. Error text through the shipped `_describe_error`: class, error code, first line only, bearer tokens, `dapi` tokens and URLs replaced by `<redacted>`, cut to 200 characters | all reads | `fail` (fail closed) | FR-48, NFR-25, D-45, AC-89, AC-90 |
| G-26 one attempt, bounded time: the check task and `ingest_kafka` set `max_retries: 0` and `disable_auto_optimization: true` (the only setting that stopped a serverless retry, A-27); the check's timeout is 300 s; the client uses `CLIENT_LIMITS` (60 s retry, 30 s HTTP) | check task, `ingest_kafka` | `fail` (timeout ends the task `TIMEDOUT`; 0 retries) | FR-43, FR-45, NFR-28, A-27 |
| G-27 the ingestion job file holds no reference to a job resource (no `resources.jobs.` text) and the check receives only `src_path` and the pipeline reference | bundle | `fail` in tests (AC-81); a violation would fail the deploy with a cycle (A-30) | A-30, D-48 |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-19 | **Task key `check_silver_gold_idle`, notebook `notebooks/check_silver_gold_idle.py`, job environment key `ingestion_check_env`** (spec `environment_version: "2"`, no dependencies) | The key differs from the peak task `check_pipeline_idle`, which AC-87 forbids in the message and whose notebook is pinned to `v0.3.0`. It names what is checked (the pipeline), not the other job (D-48). Task key equal to the notebook stem, as in the peak job. The environment key names its single purpose and cannot be mistaken for `peak_model_env` (whose G-01 test covers the peak jobs only) |
| OD-20 | **New pipeline-only entry points appended to `pipeline_guard`; no change to any existing line.** API in *Library API* below: `Caller`, `INGESTION_CALLER`, `PIPELINE_READ_CALLS`, `PipelineReport`, `check_pipeline(client, pipeline_id, *, caller, now=None)`, `run_pipeline_check(client_factory, pipeline_id, *, caller, now=None)`, `enforce_pipeline(report)`. "No watched job" is represented by the type: `PipelineReport` has no job fields and its exit value has no `ingestion_job` key, so `GuardReport` and its output stay as shipped | An optional watched job inside `check()` would change the body of a peak-mode function and `GuardReport.message()`, whose job lines, action and schedule are hard-coded to the peak direction (F-35); every such edit is a chance to break AC-92. A separate report keeps the peak path byte-identical, which AC-92 can then check as "the diff against `v0.3.0` is additions only". The pipeline half needs no new code: `_read_pipeline` already returns name, state, latest update and busy flag and fills the update and unreadable lists. Cost: a second message builder of about 50 lines, which is small and tested on its own |
| OD-21 | **Message inputs are library constants, not task parameters.** `INGESTION_CALLER = Caller(job="smart_meter_ingestion", task="check_silver_gold_idle", schedule="06:00 UTC", next_refresh="the smart_meter_peak_model run at 08:00 UTC")`, passed by the notebook. The message does **not** suggest the task-subset rerun; the runbook does (`--only check_silver_gold_idle,refresh_silver_gold`, or Repair run in the UI) | AC-81 requires the check's parameters to be exactly `src_path` and the pipeline id (plus OD-21 inputs if any): no extra widget keeps the task definition minimal and leaves nothing to mistype. A schedule cannot be a bundle reference, so a parameter would only copy the YAML; instead a unit test ties the constant to the YAML (task key, cron `0 0 6 * * ?` UTC, peak cron `0 0 8 * * ?` UTC). One action in the message, as FR-47 words it ("rerun smart_meter_ingestion"), is clearer in an email; a full rerun is safe because the ingest tasks are idempotent (Auto Loader and the Kafka checkpoint add only new data) |
| OD-22 | **Shipped tests that change by design**: see *Changes to shipped tests* below. Assertions are re-targeted to the new graph with the guarded intent kept; none is removed without a stronger replacement. `tests/test_pipeline_guard.py`, `tests/integration/test_peak_concurrency.py` and `tests/integration/test_peak_deployment.py` do not change | F-41, F-42; AC-92 and AC-98 need the shipped peak tests unmodified |
| OD-23 | **Live mechanics.** AC-97 is a **task subset** run `only = [check_silver_gold_idle, refresh_silver_gold]` started right after `pipelines.start_update` (a full run would spend minutes in the ingest tasks while the no-op update, about 125 s, ends; the subset needs no Kafka). AC-96 starts its own full run and **shares it** with the METER_INGESTION AC-30 evidence (`test_deployment.py::test_ac30_*` run right after picks the same latest full successful run). Order in *Test Strategy*: AC-94 first; AC-97 next (Kafka-independent); then the Kafka block, ordered by the current Aiven state so that at most one Kafka reset is needed. Fallback for A-31 (DA-31): rerun once; then start U with `full_refresh=True` (longer, same Silver/Gold content, ADR 0004 and AC-27); then record AC-97 `Partial` with a direct `check_pipeline` read during U as evidence | A full run cannot meet the A-31 timing; the subset mirrors the shipped AC-75 mechanics, which passed. Sharing the AC-96 run saves one 9-minute run. A power-off of the Aiven free service empties the topic, and the next Kafka-on run then needs the runbook Kafka reset (METER_INGESTION I-23); ordering by the current state avoids a second reset |

### Library API (appended to `pkg/pipeline_guard.py`)

```python
# Pipeline-only mode (INGESTION_GUARD, ADR 0013). Appended; the peak mode above is unchanged.
PIPELINE_READ_CALLS = ("pipelines.get",)


@dataclass(frozen=True)
class Caller:
    """The job that runs a pipeline-only check, as named in its messages (D-54, OD-21)."""

    job: str
    task: str
    schedule: str
    next_refresh: str


INGESTION_CALLER = Caller(
    job=INGESTION_JOB,
    task="check_silver_gold_idle",
    schedule="06:00 UTC",
    next_refresh=f"the {PEAK_JOB} run at 08:00 UTC",
)


@dataclass(frozen=True)
class PipelineReport:
    caller: Caller
    checked_at: str
    pipeline_id: str
    pipeline_name: str | None = None
    pipeline_state: str | None = None
    latest_update: tuple[str, str] | None = None
    pipeline_busy: bool = False
    updates: tuple[ActiveUpdate, ...] = ()
    unreadable: tuple[Unreadable, ...] = ()

    @property
    def ok(self) -> bool: ...          # no active update, pass state, nothing unreadable
    def message(self) -> str: ...      # FR-47 / FR-48 texts of the Data Model
    def exit_value(self) -> dict[str, Any]: ...


def check_pipeline(
    client: Any, pipeline_id: str, *, caller: Caller, now: datetime | None = None
) -> PipelineReport:
    """G-22, then one pipelines.get through the shipped _read_pipeline (G-23, G-24)."""


def run_pipeline_check(
    client_factory: Callable[[], Any], pipeline_id: str, *, caller: Caller,
    now: datetime | None = None,
) -> PipelineReport:
    """A client-factory exception is an unreadable 'workspace client' item (G-25)."""


def enforce_pipeline(report: PipelineReport) -> dict[str, Any]:
    """Raise PipelineGuardError(report.message()) unless ok; otherwise the exit value."""
```

The module docstring gains one paragraph on the pipeline-only mode (an insertion). No existing
definition, constant or line is edited, moved or reformatted.

### Changes to shipped tests (OD-22)

| File | Test or object | Change |
|---|---|---|
| `tests/test_bundle_config.py` | `test_ac28_no_more_than_five_concurrent_tasks` | `len(tasks()) == 5`; task list `setup_catalog`, `ingest_files`, `ingest_kafka`, `check_silver_gold_idle`, `refresh_silver_gold`; new assertion: widest level `== 2` (was only `<= 5`, kept) |
| `tests/test_bundle_config.py` | `test_ac28_task_dependencies_and_pipeline_task` | `sorted(_depends(check)) == ["ingest_files", "ingest_kafka"]`; `_depends(refresh_silver_gold) == ["check_silver_gold_idle"]`; timeouts `[600, 1800, 840, 300, 2700]`; retries `[1, 1, 0, 0, 0]`; pipeline reference and `full_refresh` assertions unchanged |
| `tests/test_bundle_config.py` | `test_ac10_kafka_task_fails_within_15_minutes` | The direct-dependency assertion becomes `"ingest_kafka" in _ancestors("refresh_silver_gold")` (new helper `_ancestors`, D-58); timeout and `max_retries` assertions kept; new: `disable_auto_optimization is True` (FR-43) |
| `tests/test_bundle_config.py` | `test_notebooks_set_and_assert_utc_session_time_zone` | Parametrize list gains `check_silver_gold_idle.py` |
| `tests/test_bundle_config.py` | `test_ac28_job_parameters_reach_declared_notebook_widgets`, `test_ac10_notebooks_and_pipeline_have_no_try_except`, `test_ac29_bundle_reads_kafka_credentials_from_secret_scope`, `test_ac30_job_timeout_within_60_minutes` | No change; they now also cover the check (its `pipeline_id` widget is a base parameter; `Settings.from_mapping` ignores keys that are not settings when the prefix is empty, checked in `config.py`; no `try`; no scope; 300 s below 3600 s) |
| `tests/test_peak_bundle.py` | constant `PINNED_SHA256` | Drop the `resources/smart_meter_ingestion.job.yml` entry; comment: the ingestion clause of AC-62 and AC-78 is superseded by INGESTION_GUARD AC-84 (`tests/test_ingestion_guard_bundle.py`). `test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged` and `test_ac78_ingestion_pipeline_and_training_definitions_unchanged_and_retry_kept` keep their names and code and still pin the pipeline YAML and `databricks.yml` to `v0.1.0` (and the training job to `v0.2.0`) |
| `tests/test_secrets_hygiene.py` | new `test_ac93_*` | Added; shipped tests unchanged (the scan covers the new files as tracked or new files) |
| `tests/test_integration_layout.py` | `test_integration_files_exist_for_every_manifest_entry`, `EXPECTED_ACS`, `test_integration_tests_are_collected_but_deselected_by_default` | File set gains `test_ingestion_guard.py`; `EXPECTED_ACS` gains 94 to 98; collection assertion gains `test_ingestion_guard.py::test_ac97_` |
| `tests/integration/conftest.py` | `full_runs` docstring | "Successful runs of all four tasks" becomes "of every task of the job" (the code already uses the deployed task set) |
| `tests/integration/test_deployment.py` | `JOB_TASKS`, `test_ac30_daily_job_run_within_60_minutes` docstring | `JOB_TASKS` gains `check_silver_gold_idle` (5 keys); "all four tasks" becomes "every task" |
| `tests/integration/test_bronze_ingestion.py` | `test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged` | The run search moves into a helper `_failed_kafka_run_id` (same logic); the test additionally reads that run once with `jobs.get_run` and asserts exactly 1 task run of `ingest_kafka` (FR-52); new `test_ac95_*` in the same file |
| `tests/test_pipeline_guard.py`, `tests/integration/test_peak_concurrency.py`, `tests/integration/test_peak_deployment.py`, `tests/test_peak_concurrency_docs.py` | - | No change. `test_peak_deployment.py` compares the deployed ingestion job with the new YAML through its unchanged `_assert_job_matches_yaml` |

### Assumption dependencies

Spike 07 (2026-10-23, run 843912359241341) validated the platform surface before this design
(BRAINSTORM A-25 to A-30, DEFINE A-32). DA-31 is the only pending item; it affects one live test,
not the design.

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| DA-27 **Validated (spike 07, A-29, A-32).** In environment version 2 (`databricks-sdk` 0.40.0), `WorkspaceClient(config=Config(**CLIENT_LIMITS))` authenticates as the ingestion job's run-as identity and `pipelines.get` returns `state` and `latest_updates` with no extra grant | OD-19, G-23, G-26 | AC-96 exit value on the real job | `%pip install databricks-sdk==0.40.0` in the notebook (an `/iterate`); fail-closed until then |
| DA-28 **Validated (spike 07, A-26).** A job with one notebook task on a job environment (version 2) and the other notebook tasks without `environment_key` deploys and runs; the others keep the default environment | OD-19, FR-45 | AC-94 read-back, AC-96 run | None needed; if the platform changes, `/iterate` to put the check in its own one-task job is not possible without a job reference, so move every ingestion notebook task to the environment after a spike |
| DA-29 **Validated (spike 07, A-27).** `disable_auto_optimization: true` with `max_retries: 0` on a serverless notebook task gives exactly 1 attempt, and the deployed task reads back `max_retries` 0 (not unset). On a pipeline task the field does not stick (A-25) | G-26, FR-43 | AC-94 (read-back on `ingest_kafka` and the check), AC-95 (one attempt on `ingest_kafka`) | None known; a second attempt fails AC-95 and is recorded as a deviation |
| DA-30 **Validated by prior art.** A run with `only` runs a task whose upstream tasks are excluded (shipped AC-06 and AC-08 run `ingest_files` and `ingest_kafka` without `setup_catalog`); a task whose upstream failed ends `UPSTREAM_FAILED` and never starts (shipped AC-74 and AC-75) | OD-23, AC-95, AC-97 | AC-97 first run; AC-95 | None needed |
| DA-31 **Pending (A-31).** A no-op update started through `pipelines.start_update` stays non-terminal until the check of a subset run started right after it reads the pipeline (no-op update about 125 s; a probe 4 s after the start saw it active, spike 06; same mechanics passed in AC-75) | AC-97 | AC-97 asserts the check's error contains U, which proves U was active when read | Rerun once; then U with `full_refresh=True`; then AC-97 `Partial` with a direct `check_pipeline` read during U (OD-23) |
| DA-32 The local SDK of the integration tests reads the deployed job environment as `settings.environments[0].spec.environment_version` | AC-94 | AC-94 first run | Compare `spec.as_dict()`, accepting `environment_version` or the older field `client` equal to "2"; record which one in the build report |
| DA-33 **Validated (spike 07, prior art).** `jobs.get_run(run_id)` lists every attempt of a task as its own entry of `tasks`, with `attempt_number` 0, 1, and so on (spike 07 counted the control's two attempts this way; `PeakRunner.task_runs_by_key` relies on it) | FR-52, AC-95, AC-96, AC-97 | AC-95, AC-96 | None needed |

### Bundle and job layout

`databricks.yml`, `resources/smart_meter_silver_gold.pipeline.yml`,
`resources/smart_meter_peak_model.job.yml` and `resources/smart_meter_peak_model_training.job.yml`
are not changed. The ingestion job file changes only as AC-85 allows (header comment, the
`environments` block, one key on `ingest_kafka`, the new task, the `depends_on` of
`refresh_silver_gold`, comments):

```yaml
# resources/smart_meter_ingestion.job.yml (changed parts; everything else as at v0.1.0)
# Daily ingestion job (DESIGN, Bundle and job layout; INGESTION_GUARD, ADR 0013). ... (header comment
# gains one sentence on the reverse pre-check)
resources:
  jobs:
    smart_meter_ingestion:
      # name, max_concurrent_runs, timeout_seconds, schedule, email_notifications: unchanged
      # Serverless environment version 2 for the reverse pre-check only (D-55): the runtime spike 06
      # and spike 07 validated (databricks-sdk 0.40.0). The other tasks keep the default environment.
      environments:
        - environment_key: ingestion_check_env
          spec:
            environment_version: "2"
      tasks:
        # setup_catalog, ingest_files: unchanged

        # No retry (AC-10): a broker outage fails the task within 15 minutes and the next daily
        # run is the retry. max_retries 0 alone does not stop a serverless retry; with
        # auto-optimization off the task runs exactly once (D-51, ADR 0013).
        - task_key: ingest_kafka
          depends_on:
            - task_key: setup_catalog
          timeout_seconds: 840
          max_retries: 0
          disable_auto_optimization: true
          notebook_task: # unchanged

        # Read-only reverse pre-check (ADR 0013): reads the shared pipeline once and fails at once,
        # naming the active update, when it is busy; fails closed when the state cannot be read.
        # Bronze is already ingested. No job reference here: it would form a bundle cycle (A-30).
        - task_key: check_silver_gold_idle
          depends_on:
            - task_key: ingest_files
            - task_key: ingest_kafka
          timeout_seconds: 300
          max_retries: 0
          disable_auto_optimization: true
          environment_key: ingestion_check_env
          notebook_task:
            notebook_path: ../notebooks/check_silver_gold_idle.py
            base_parameters:
              src_path: ${workspace.file_path}/src
              pipeline_id: ${resources.pipelines.smart_meter_silver_gold.id}

        # Fail rules must not be retried blindly, so no retry here either. An update refused
        # because another one is in progress ends INTERNAL_ERROR; the pre-check prevents the
        # visible cases (race window C-11 remains).
        - task_key: refresh_silver_gold
          depends_on:
            - task_key: check_silver_gold_idle
          timeout_seconds: 2700
          max_retries: 0
          pipeline_task:
            pipeline_id: ${resources.pipelines.smart_meter_silver_gold.id}
            full_refresh: false
```

YAML order of the tasks: `setup_catalog`, `ingest_files`, `ingest_kafka`, `check_silver_gold_idle`,
`refresh_silver_gold` (AC-81). No `run_if` anywhere.

**Notebook (`notebooks/check_silver_gold_idle.py`) outline.**

```python
# Databricks notebook source
# Read-only reverse pre-check before refresh_silver_gold of smart_meter_ingestion (FR-44 to FR-49,
# AC-86 to AC-91; ADR 0013). Reads only the shared pipeline with the job's own identity (default
# notebook authentication, no secret) and fails at once, naming the active update, when it is busy;
# fails closed when it cannot read the state. No try/except (I-14). The pipeline id is a bundle
# reference passed as a task parameter; no job id (A-30).

# COMMAND ----------

import json
import os
import sys

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import pipeline_guard  # noqa: E402

# COMMAND ----------

_widget_names = ("pipeline_id",)
for _name in _widget_names:
    dbutils.widgets.text(_name, "")  # empty fails closed (G-22)

spark.conf.set("spark.sql.session.timeZone", "UTC")  # golden rule 5
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.config import Config  # noqa: E402
from databricks.sdk.version import __version__ as sdk_version  # noqa: E402

print(f"databricks-sdk {sdk_version}")  # SDK drift shows in the task output (PEAK_MODEL_CONCURRENCY F-04)
report = pipeline_guard.run_pipeline_check(
    lambda: WorkspaceClient(config=Config(**pipeline_guard.CLIENT_LIMITS)),
    dbutils.widgets.get("pipeline_id"),
    caller=pipeline_guard.INGESTION_CALLER,
)
print(report.message())
result = pipeline_guard.enforce_pipeline(report)  # raises PipelineGuardError on busy or unknown

# COMMAND ----------

dbutils.notebook.exit(json.dumps(result))
```

**Concurrency.** The widest level stays 2 tasks (`ingest_files`, `ingest_kafka`); the check and the
pipeline task run alone in their levels. With an overlapping peak run (widest level 2) at most 4
tasks run at once, below the Free Edition limit of 5 (NFR-24).

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| 0013 | A read-only, pipeline-only pre-check before the pipeline task of the ingestion job, and no platform retry of the Kafka task (D-48, D-50, D-51, D-55, D-58; options B and C rejected on A-30 and F-38) | Accepted (2026-10-23) |
| 0012 | Peak job pre-check (existing). Gets a dated note at build (manifest entry 19): its revisit trigger "a reverse check added to `smart_meter_ingestion`" is now ADR 0013; C-08 no longer holds for the ingestion job; the decision stands | Accepted |
| 0008 | PEAK_MODEL jobs (existing). Gets a dated note at build (manifest entry 20): the ingestion job checks the pipeline before its own refresh and `ingest_kafka` no longer retries; "METER_INGESTION stays byte-identical" now holds for the pipeline and `databricks.yml` only | Accepted |

**Why ADR 0013 is Accepted at design, not Proposed.** Every fact it rests on is validated: the
user's decisions D-48, D-50, D-51 and D-55 are final; spike 07 validated the mixed environment
(A-26), the single attempt (A-27), the read permission (A-29), the cycle (A-30) and the SDK (A-32),
and invalidated A-25, which the ADR records as a rejected option. The one pending item, A-31
(DA-31), is a timing property of a live test, not a premise of the decision. The build checks the
ADR text against the shipped code (manifest entry 17), as ADR 0012 was checked after spike 06.

Following the PEAK_MODEL_CONCURRENCY precedent, the notes on ADR 0012 and ADR 0008 are written at
build (manifest entries 19, 20), not in this phase; the index row of ADR 0013 is added now.

---

## Delivery Plan

| Step | Scope | Manifest entries | Files |
|---|---|---|---|
| Precondition | Spike 07 branch `spike/07-ingestion-guard` merged (spike files and the row 07 in `docs/spikes/README.md`, which ADR 0013 and DEFINE cite). Not part of the build | - | - |
| PR 1 (single feature PR, branch `build/ingestion-guard`) | Library, notebook, job, tests, docs | 1 to 22 | 22 |

One build PR is enough: 22 files, one job definition, no table or contract change, and the live gate
needs the whole change deployed at once.

**Gate inside PR 1.** After entry 4: `databricks bundle validate -t dev` and
`databricks bundle deploy -t dev` from a clean tree (exit codes recorded; a cycle error means a job
reference slipped in, G-27), then AC-94 before any run. If a DA fails, apply its fallback through
`/iterate` first.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Package path
`src/smart_meter_peak_prediction/` is abbreviated `pkg/`. Agents: `pipeline-builder` (Databricks
module) for the library, notebook, bundle and tests; `streaming-engineer` (Kafka module) for the
Kafka ingestion live test; `build-agent` for documents. No `mlflow` module agent applies.

Existing inputs, read and not modified: `databricks.yml`, `resources/smart_meter_silver_gold.pipeline.yml`,
`resources/smart_meter_peak_model.job.yml`, `resources/smart_meter_peak_model_training.job.yml`,
`notebooks/check_pipeline_idle.py`, `tests/test_pipeline_guard.py`,
`tests/integration/test_peak_concurrency.py`, `tests/integration/test_peak_deployment.py`,
`tests/test_peak_concurrency_docs.py`, `scripts/reset_peak_model_outputs.py` (D-52).

Digests for the pins are computed at build from the tags, never typed by hand:
`git show <tag>:<file> | sha256sum` (tags `v0.1.0`, `v0.2.0`, `v0.3.0` exist), and for the new
ingestion job file `sha256sum resources/smart_meter_ingestion.job.yml` once entry 4 is final.

| # | PR | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|---|
| 1 | 1 | `pkg/pipeline_guard.py` | Update (append only) | Pipeline-only mode per *Library API*: `PIPELINE_READ_CALLS`, `Caller`, `INGESTION_CALLER`, `PipelineReport` (`ok`, `message()` with the FR-47 and FR-48 texts, `exit_value()`), `check_pipeline`, `run_pipeline_check`, `enforce_pipeline`; docstring paragraph. No existing line edited (G-22 to G-25; FR-46 to FR-50; AC-86 to AC-93) | pipeline-builder | - |
| 2 | 1 | `tests/test_ingestion_guard.py` | Create | Recording fake exposing `PIPELINE_READ_CALLS` only; AC-86 to AC-91 tests, the caller-constant test, AC-92 regression tests (pinned digest of `tests/test_pipeline_guard.py`, additions-only diff, signatures, peak output equal to `v0.3.0`), AC-93 library part | pipeline-builder | 1 |
| 3 | 1 | `notebooks/check_silver_gold_idle.py` | Create | Wiring per the outline (FR-45 to FR-49, NFR-25, NFR-27, NFR-29) | pipeline-builder | 1 |
| 4 | 1 | `resources/smart_meter_ingestion.job.yml` | Update | Environment `ingestion_check_env`, task `check_silver_gold_idle`, `refresh_silver_gold` after it, `disable_auto_optimization: true` on `ingest_kafka`, comments (FR-43 to FR-45; layout above). Then the deploy gate and AC-94 | pipeline-builder | 3 |
| 5 | 1 | `tests/support/ingestion_job_v0.1.0.yml` | Create | `git show v0.1.0:resources/smart_meter_ingestion.job.yml` byte for byte; its SHA-256 must equal the shipped v0.1.0 pin `a2e8f0dc...` (AC-85 without tags) | pipeline-builder | - |
| 6 | 1 | `tests/test_ingestion_guard_bundle.py` | Create | AC-81 to AC-85 (graph, settings, environments, pins of FR-51 with the new ingestion digest, structural diff against entry 5 and the tag) | pipeline-builder | 4, 5 |
| 7 | 1 | `tests/test_bundle_config.py` | Update | OD-22 changes (graph, dependencies, timeouts, retries, AC-10 ancestor, UTC list) | pipeline-builder | 4 |
| 8 | 1 | `tests/test_peak_bundle.py` | Update | `PINNED_SHA256` without the ingestion entry, supersession comment (OD-22, D-53) | pipeline-builder | 6 |
| 9 | 1 | `tests/test_secrets_hygiene.py` | Update | New `test_ac93_*` | pipeline-builder | 3, 4 |
| 10 | 1 | `tests/integration/conftest.py` | Update | `full_runs` docstring (OD-22). `PeakRunner` unchanged | pipeline-builder | 4 |
| 11 | 1 | `tests/integration/test_deployment.py` | Update | `JOB_TASKS` with the check; docstring (OD-22) | pipeline-builder | 4 |
| 12 | 1 | `tests/integration/test_bronze_ingestion.py` | Update | `_failed_kafka_run_id` helper, AC-10 attempt count (FR-52), new `test_ac95_*`; module docstring names AC-95 | streaming-engineer | 4 |
| 13 | 1 | `tests/integration/test_ingestion_guard.py` | Create | AC-94, AC-96, AC-97, AC-98 live tests (marker `integration`), evidence in `out/evidence/` | pipeline-builder | 1, 4, 10 |
| 14 | 1 | `tests/test_integration_layout.py` | Update | New file in the set, `EXPECTED_ACS` 94 to 98, collection assertion (OD-22) | pipeline-builder | 12, 13 |
| 15 | 1 | `docs/runbooks/meter_ingestion.md` | Update | Diagram and "What runs where" with the check; "Dependency on Aiven" (one attempt now, the check never runs when `ingest_kafka` fails); new section "## Concurrency with the peak job" (what the check reads, busy and fail-closed messages, action, Bronze kept, 08:00 UTC catch-up, race window, the `--only` rule with `--only check_silver_gold_idle,refresh_silver_gold` and Repair run as the refresh-only rerun, a symptom table, and "check the pipeline is idle before running it directly"); "Run the job" text (five tasks); "Broker outage" (one attempt since v0.4.0, D-51); evidence order rows for AC-94 to AC-98 | build-agent | 4, 13 |
| 16 | 1 | `docs/runbooks/peak_model.md` | Update | Concurrency: one bullet "Reverse direction" (the ingestion job runs `check_silver_gold_idle` before its own `refresh_silver_gold`, pipeline only, so a peak run refused by its own pre-check never refuses the ingestion run; see the ingestion runbook). It must not contain an ingestion `--only` list (the AC-79 test requires `check_pipeline_idle` in every `--only` list with `refresh_silver_gold` in this file). "Serverless auto-optimization" paragraph: `ingest_kafka` fixed in v0.4.0 | build-agent | 15 |
| 17 | 1 | `docs/adr/0013-pipeline-only-pre-check-in-the-ingestion-job.md` | Verify (created at design, Accepted) | Check that names, keys, settings and messages match the shipped code; fix wording only through the build report | build-agent | 4, 13 |
| 18 | 1 | `docs/adr/README.md` | Verify (row added at design) | Row 0013, status Accepted | build-agent | 17 |
| 19 | 1 | `docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md` | Update | Dated note `Note (2026-10-23, INGESTION_GUARD)` at the end of *Consequences*: the reverse-check revisit trigger is answered by ADR 0013 (link with the file name); C-08 no longer holds for the ingestion job; this decision and the peak pre-check are unchanged. Status stays Accepted | build-agent | 17 |
| 20 | 1 | `docs/adr/0008-peak-model-jobs-and-pipeline-dependency.md` | Update | Dated note `Note (2026-10-23, INGESTION_GUARD)` in *Consequences*: the ingestion job checks the pipeline before its own refresh and `ingest_kafka` sets `disable_auto_optimization` (ADR 0013, link with the file name); "METER_INGESTION stays byte-identical" now holds for the pipeline and `databricks.yml`. The existing PEAK_MODEL_CONCURRENCY note stays | build-agent | 17 |
| 21 | 1 | `tests/test_ingestion_guard_docs.py` | Create | AC-99 | build-agent | 15, 16, 17, 18, 19, 20 |
| 22 | 1 | `README.md` | Update | METER_INGESTION diagram (mermaid and plain text) with the check before `refresh_silver_gold`; "Coexistence with ingestion" bullet: both jobs check, link ADR 0013; ADR list gains 0013 | build-agent | 15, 17 |

The build report (`.claude/sdd/reports/BUILD_REPORT_INGESTION_GUARD.md`) is the output of `/build`
and is not a manifest entry.

---

## Test Strategy

Levels as in PEAK_MODEL_CONCURRENCY: **Unit** (pytest, no workspace, runs in CI), **Integration**
(marker `integration`, deployed `dev` target, user-run in the order below). Every test name contains
its AC id.

**Unit fake.** `tests/test_ingestion_guard.py` defines its own `PipelineFake` (the shipped fake in
`tests/test_pipeline_guard.py` is not imported, so that file stays byte-identical). It has `jobs` and
`pipelines` attributes; only `pipelines.get` (from `PIPELINE_READ_CALLS`) is callable; any other
attribute, including every `jobs.*`, is recorded as forbidden and raises. Errors are exception
classes carrying `error_code` (`PERMISSION_DENIED`, `RESOURCE_DOES_NOT_EXIST`). A fixed `now` makes
messages comparable. UTC check as in the shipped tests: every date-time-like substring must fully
match `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z`.

**AC-92 loading of the v0.3.0 module.** When tag `v0.3.0` exists, the test reads
`git show v0.3.0:src/smart_meter_peak_prediction/pipeline_guard.py`, creates a module with
`importlib.util.module_from_spec`, **registers it in `sys.modules` before `exec`** (the dataclass
decorator looks the module up there) and removes it afterwards. Without the tag (CI), golden full
messages and exit values captured from `v0.3.0` at build time are asserted instead.

**Integration order (runbook).** 1. Deploy gate, AC-94. 2. AC-97 (no Kafka needed). 3. Kafka block,
by the current Aiven state, so that at most one Kafka reset (runbook "Broker outage") is needed:
- *Aiven on and the last `ingest_kafka` succeeded since its last power-on:* AC-96, then
  `test_deployment.py::test_ac28_*` and `::test_ac30_*` (same run), then AC-98 (the peak concurrency
  suite in its runbook order AC-76, AC-74, AC-77, AC-75, then `test_ac98_*`, then
  `test_peak_deployment.py`), then AC-95 last (`test_ac10_before_outage_snapshot`, power off, run the
  job, `test_ac10_failed_*`, `test_ac95_*`).
- *Aiven off (it powers off when idle):* AC-95 first (snapshot, run the job, the two tests), then
  power on and do the Kafka reset, then AC-96, the AC-28/AC-30 tests and AC-98 as above.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-81 | Unit | `tests/test_ingestion_guard_bundle.py::test_ac81_ingestion_graph_places_the_check_before_the_pipeline_task` | Exactly 5 tasks in YAML order `setup_catalog`, `ingest_files`, `ingest_kafka`, `check_silver_gold_idle`, `refresh_silver_gold`; dependencies exactly as AC-81 (ingest tasks on `setup_catalog`, check on both ingest tasks, refresh on the check only); `ingest_kafka` in the ancestors of `refresh_silver_gold`; no task has `run_if`; the check has `notebook_task` and no `pipeline_task`; widest level 2; schedule `0 0 6 * * ?` UTC, `max_concurrent_runs` 1, job timeout 3600 and the on-failure email equal the v0.1.0 fixture; base parameters of the check are exactly `src_path` (workspace file path plus `/src`) and `pipeline_id` equal to the pipeline resource reference; the file text contains no `resources.jobs.` (G-27) |
| AC-81 | Unit | `tests/test_bundle_config.py::test_ac28_no_more_than_five_concurrent_tasks`, `::test_ac28_task_dependencies_and_pipeline_task`, `::test_ac10_kafka_task_fails_within_15_minutes` (updated, OD-22) | The shipped graph tests now assert the 5-task graph; AC-10 keeps `ingest_kafka` as an ancestor of the pipeline task (D-58) |
| AC-82 | Unit | `tests/test_ingestion_guard_bundle.py::test_ac82_retry_timeout_and_auto_optimization_settings` | `ingest_kafka`: `max_retries` 0, `disable_auto_optimization` true, timeout 840. Check: 0, true, 300. `setup_catalog` 600/1, `ingest_files` 1800/1, `refresh_silver_gold` 2700/0 with `full_refresh` false and the same pipeline reference, each equal to the v0.1.0 fixture and without `disable_auto_optimization`; every task timeout below the job timeout |
| AC-83 | Unit | `tests/test_ingestion_guard_bundle.py::test_ac83_only_the_check_runs_on_environment_version_2` | `environments` has exactly one entry, key `ingestion_check_env`, spec exactly `environment_version: "2"` (no `dependencies`); the check has that `environment_key`; the three other notebook tasks have none; no cluster key (`job_clusters`, `job_cluster_key`, `new_cluster`, `existing_cluster_id`) on the job or any task |
| AC-84 | Unit | `tests/test_ingestion_guard_bundle.py::test_ac84_pinned_definitions_equal_their_tags` | SHA-256 pins: ingestion job file at the feature commit (and equal to `git show v0.4.0:` once that tag exists); pipeline YAML and `databricks.yml` at `v0.1.0`; training job at `v0.2.0`; peak daily job and `notebooks/check_pipeline_idle.py` at `v0.3.0`; each also equal to `git show <tag>:<file>` when the tag exists; exactly one pipeline resource in `resources/*.yml`. The docstring states that it supersedes the ingestion-file clause of AC-62 and AC-78 |
| AC-84 | Unit | `tests/test_peak_bundle.py::test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged`, `::test_ac78_ingestion_pipeline_and_training_definitions_unchanged_and_retry_kept` (constant updated, OD-22) | Their remaining clauses stay in force: pipeline YAML and `databricks.yml` at `v0.1.0`, training job at `v0.2.0`, the peak retry |
| AC-85 | Unit | `tests/test_ingestion_guard_bundle.py::test_ac85_v010_fixture_is_the_shipped_file` | SHA-256 of `tests/support/ingestion_job_v0.1.0.yml` equals the shipped v0.1.0 pin; equal to `git show v0.1.0:resources/smart_meter_ingestion.job.yml` when the tag exists |
| AC-85 | Unit | `tests/test_ingestion_guard_bundle.py::test_ac85_ingestion_job_differs_from_v010_only_by_the_listed_changes` | Parse the new file; remove the check task and the `environments` block, remove `disable_auto_optimization` from `ingest_kafka`, set the `depends_on` of `refresh_silver_gold` back to `ingest_files` and `ingest_kafka`; the result equals the parsed fixture exactly (whole `resources` mapping, task order included) |
| AC-86 | Unit | `tests/test_ingestion_guard.py::test_ac86_idle_or_failed_pipeline_passes_twice_with_one_read` | Parametrized: overall state `IDLE`, `FAILED` x `latest_updates` absent, empty, `[COMPLETED]`, `[FAILED, COMPLETED]`, `[CANCELED]`. Two runs with the same fake and `now`: both ok, equal reports and exit values; a third with another `now` differs only in `checked_at`; exit value JSON-serialisable with `outcome` `idle`, `checked_at` ending in `Z`, and pipeline id, name (prefix stripped), state and latest update as given; the fake records exactly 1 call per run, `pipelines.get`, and 0 `jobs.*` |
| AC-87 | Unit | `tests/test_ingestion_guard.py::test_ac87_active_update_fails_with_update_caller_and_action` | Overall state `RUNNING`; parametrized update state over `CREATED`, `QUEUED`, `INITIALIZING`, `RESETTING`, `SETTING_UP_TABLES`, `RUNNING`, `STOPPING`, `WAITING_FOR_RESOURCES`, an unknown value and `None`: `enforce_pipeline` raises; message contains `check_silver_gold_idle`, `smart_meter_silver_gold`, the pipeline id, U, S (or `UNKNOWN`), the creation time as `...Z`, `pipeline state RUNNING`, `smart_meter_ingestion`, `06:00 UTC`, "rerun smart_meter_ingestion", `smart_meter_peak_model` and `08:00 UTC`, "refresh_silver_gold did not start", "Bronze"; it contains neither `check_pipeline_idle` nor "rerun smart_meter_peak_model"; UTC check; only `pipelines.get` recorded |
| AC-87 | Unit | `tests/test_ingestion_guard.py::test_ac87_every_non_terminal_sdk_update_state_blocks` | With the SDK installed (`importorskip`): every member of `UpdateInfoState` (or `UpdateStateInfoState`) outside `TERMINAL_UPDATE_STATES` makes `check_pipeline` fail with that state in the message |
| AC-87 | Unit | `tests/test_ingestion_guard.py::test_ac87_caller_constants_match_the_bundle` | `INGESTION_CALLER.task` equals the YAML check task key; `job` equals the ingestion job name; `schedule` "06:00 UTC" matches cron `0 0 6 * * ?` with `timezone_id` UTC; `next_refresh` names `smart_meter_peak_model` and the 08:00 UTC that the peak cron `0 0 8 * * ?` gives |
| AC-88 | Unit | `tests/test_ingestion_guard.py::test_ac88_busy_overall_state_without_active_update_fails_as_busy` | `latest_updates` empty or all terminal; overall state parametrized `DEPLOYING`, `STARTING`, `RUNNING`, `STOPPING`, `RECOVERING`, `RESETTING`, `None` and an unknown string: fails as busy (`pipeline_busy` true, exit outcome `busy`); message names the pipeline, the state (or "not reported") and "no active update is listed", plus the caller and the action of AC-87 |
| AC-89 | Unit | `tests/test_ingestion_guard.py::test_ac89_unreadable_pipeline_fails_closed_with_the_ingestion_action` | Parametrized: empty id; an unresolved pipeline reference (the literal bundle reference text, dollar-brace form, as a Python string in the test); client factory raises (through `run_pipeline_check`); `pipelines.get` raises a generic error, `PERMISSION_DENIED`, `RESOURCE_DOES_NOT_EXIST`; the id names another pipeline; overall state `DELETED`. Each: not ok, `enforce_pipeline` raises, never an exit value; message contains `smart_meter_silver_gold`, the read that failed, "fails closed" and "fix the cause, then rerun smart_meter_ingestion"; no "job id"; at most 1 call, `pipelines.get`, 0 `jobs.*` |
| AC-90 | Unit | `tests/test_ingestion_guard.py::test_ac90_error_text_is_redacted_and_cut_to_one_short_line` | Error with first line "call https://host.example/api failed: Bearer abc123 dapi" plus 32 hex characters, and a second line: message contains `<redacted>`, none of the three strings and nothing of the second line. Error with a 500-character first line: the text after the error class and code is at most 200 characters |
| AC-91 | Unit | `tests/test_ingestion_guard.py::test_ac91_times_are_utc_with_z_or_not_reported` | Creation time as ISO with `+02:00`, ISO with `Z`, epoch ms, aware datetime in a non-UTC zone: the message shows the same UTC instant as `YYYY-MM-DDTHH:MM:SSZ`; naive datetime: "creation time not reported"; `now` aware in a non-UTC zone: `checked_at` is its UTC instant with `Z`; every timestamp in the message and exit value matches the AC-91 pattern |
| AC-92 | Unit | `tests/test_ingestion_guard.py::test_ac92_shipped_guard_tests_are_byte_identical_to_v030` | SHA-256 of `tests/test_pipeline_guard.py` equals its `v0.3.0` digest (and `git show v0.3.0:` when the tag exists); its AST has exactly 28 top-level `test_` functions. The 28 tests themselves run in the same `pytest` session and pass |
| AC-92 | Unit | `tests/test_ingestion_guard.py::test_ac92_guard_module_changes_are_additions_only` | With tag `v0.3.0`: `difflib.SequenceMatcher` over the lines of the tagged and the current `pipeline_guard.py` yields only `equal` and `insert` opcodes |
| AC-92 | Unit | `tests/test_ingestion_guard.py::test_ac92_peak_mode_signatures_and_output_are_unchanged` | Parameter names, kinds and defaults of `check`, `run`, `enforce` equal the v0.3.0 ones (client, ingestion job id, pipeline id, keyword `now=None`); for fake states idle, busy run, busy update, busy state only, unreadable job, `DELETED` and factory failure, `message()` and `exit_value()` equal the `v0.3.0` module's output (tag present) or the golden values (no tag) |
| AC-93 | Unit | `tests/test_secrets_hygiene.py::test_ac93_reverse_check_has_no_secret_and_notebook_is_safe` | Token scan of tracked files (the new notebook, the job file and the library listed as present) finds nothing; only `ingest_kafka` has `secret_scope`; the check's parameter names and values contain no `secret`, `token`, `scope`, `password` or `{{secrets/`; the notebook has no `ast.Try`, no `dbutils.secrets`, sets and asserts the UTC session time zone, contains `Config(**pipeline_guard.CLIENT_LIMITS)` and `dbutils.notebook.exit(` |
| AC-93 | Unit | `tests/test_ingestion_guard.py::test_ac93_library_imports_no_sdk_and_never_sleeps` | The AST of `pipeline_guard.py` has no import of a `databricks` module, no `time` import and no call named `sleep` |
| AC-94 | Integration | `tests/integration/test_ingestion_guard.py::test_ac94_deployed_ingestion_job_equals_the_yaml` | After validate and deploy (exit codes 0 recorded in the build report; no cycle): `jobs.get(job id).settings` task keys equal the 5 YAML keys; per task the sorted `depends_on`, `timeout_seconds`, `max_retries or 0` and `bool(disable_auto_optimization)` equal the YAML; for `ingest_kafka` and the check `max_retries == 0` (not `None`) and `disable_auto_optimization is True`; the check's `pipeline_id` parameter equals the deployed pipeline id; the job environment `ingestion_check_env` has version "2" (DA-32), and only the check references it |
| AC-95 | Integration | `tests/integration/test_bronze_ingestion.py::test_ac95_failed_kafka_run_has_one_attempt_and_skips_the_check` | Loads the AC-10 snapshot; finds the failed run after it (`_failed_kafka_run_id`); one `jobs.get_run`: exactly 1 entry of `ingest_kafka`, `attempt_number` 0, result `FAILED` or `TIMEDOUT`; `check_silver_gold_idle` and `refresh_silver_gold` each one entry with result `UPSTREAM_FAILED` |
| AC-95 | Integration | `tests/integration/test_bronze_ingestion.py::test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged` (extended, FR-52) | METER_INGESTION AC-10 as shipped (failed within 900 s, Bronze count and checkpoint unchanged) plus exactly 1 task run of `ingest_kafka` in that run |
| AC-96 | Integration | `tests/integration/test_ingestion_guard.py::test_ac96_full_run_passes_the_check_and_every_task_succeeds_once` | Pipeline and ingestion idle (`peak_runner.assert_ingestion_idle`) and no active peak run; `peak_runner.run(job)` full run, `SUCCESS`; each of the 5 tasks exactly 1 run, `attempt_number` 0, `SUCCESS`; check at most 120 s; its exit value `outcome` `idle`, the deployed pipeline id, `checked_at` ending in `Z`; `pipelines.list_updates` shows exactly 1 update created between the start and end of `refresh_silver_gold`, state `COMPLETED`; run at most 3600 s; durations saved to `ac96_ingestion_run` |
| AC-96 | Integration | `tests/integration/test_deployment.py::test_ac30_daily_job_run_within_60_minutes` (run right after, OD-23) | The METER_INGESTION AC-30 evidence from the same run, now over 5 tasks |
| AC-97 | Integration | `tests/integration/test_ingestion_guard.py::test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds` | No active run of either job; `pipelines.start_update(full_refresh=False)` gives U; at once `peak_runner.run(job, only=[check_silver_gold_idle, refresh_silver_gold], expect="FAILED", require_idle=False)` (an `AssertionError` is re-raised with the DA-31 advice). Check: exactly 1 task run, `attempt_number` 0, `FAILED`, at most 120 s; its error contains U, `smart_meter_silver_gold`, "rerun smart_meter_ingestion" and a timestamp ending in `Z`; `refresh_silver_gold` `UPSTREAM_FAILED`. In `finally`, wait until `check_pipeline` is ok. No update other than U created between the run's start and end. Then the same subset again with `require_idle=True`: `SUCCESS`, the check `SUCCESS` with `outcome` `idle` |
| AC-98 | Integration | `tests/integration/test_peak_concurrency.py` (AC-74 to AC-77) and `tests/integration/test_peak_deployment.py` (AC-62), unmodified | They pass against the v0.4.0 deployment, in the runbook order; `test_peak_deployment.py` compares the deployed ingestion job with the new YAML |
| AC-98 | Integration | `tests/integration/test_ingestion_guard.py::test_ac98_ac74_ingestion_run_passed_its_check_and_refresh` | Loads `ac74_refused_run` (saved by the shipped AC-74 test); one `jobs.get_run` of its ingestion run R: `check_silver_gold_idle` and `refresh_silver_gold` each exactly 1 run with result `SUCCESS` (no mutual refusal); fails with a hint when the evidence is missing or R's upstream tasks did not succeed (Aiven was off) |
| AC-99 | Unit | `tests/test_ingestion_guard_docs.py::test_ac99_runbook_only_commands_include_the_check` | Every `--only` list in `docs/runbooks/meter_ingestion.md` (code blocks joined over continuations, and inline code) that contains `refresh_silver_gold` contains `check_silver_gold_idle`; at least one such list exists |
| AC-99 | Unit | `tests/test_ingestion_guard_docs.py::test_ac99_runbooks_describe_the_check` | The ingestion runbook section "## Concurrency with the peak job" names `check_silver_gold_idle`, `smart_meter_silver_gold`, "update id", "fails closed", "rerun smart_meter_ingestion", "Bronze" and `08:00 UTC`; the peak runbook section "## Concurrency with the ingestion job" names `check_silver_gold_idle` |
| AC-99 | Unit | `tests/test_ingestion_guard_docs.py::test_ac99_adrs_record_the_reverse_check_and_specs_are_clean` | ADR 0013 status `Accepted`, contains D-48, D-50, D-51, D-55 and "Error: Cycle", and is listed in `docs/adr/README.md`; ADR 0012 and ADR 0008 each contain a `Note (2026-10-23, INGESTION_GUARD)` and the ADR 0013 file name; `check_specs.run(ROOT).errors == []` |
| AC-99 | Unit | `tests/test_ingestion_guard_docs.py::test_ac99_no_test_asserts_the_v010_four_task_graph` | No file under `tests/` (this one excluded) contains the v0.1.0 task sequence (`"ingest_kafka",` directly followed by `"refresh_silver_gold"`) or `len(tasks()) == 4`. The `pytest` result itself (0 failures, CI) and `check_specs.py` (0 errors) are recorded in the build report |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | `databricks bundle validate -t dev`, then `databricks bundle deploy -t dev` from a clean tree. Only the ingestion job changes; the pipeline, the peak jobs and `databricks.yml` deploy unchanged. No catalog, table or secret step. A deploy error "Cycle: databricks_job..." means a job reference was added to the ingestion job (G-27, A-30): remove it |
| Scheduling and retries | Schedules unchanged (ingestion 06:00 UTC, peak 08:00 UTC; paused in development mode). Check: `max_retries: 0`, `disable_auto_optimization: true`, 300 s, no polling. `ingest_kafka`: one attempt (D-51). `refresh_silver_gold`: unchanged (0 retries; a platform retry of a pipeline task cannot be switched off, A-25). A refused run is retried by a manual rerun after the update ends, by Repair run of the failed tasks, or by the next scheduled update |
| Monitoring and alerting | The existing on-failure email links to the run; the check task's error holds the full message and the notebook output prints it with the SDK version. The success exit value records the pipeline state that was read. Live evidence in `out/evidence/` (`ac96_ingestion_run`, the AC-10 snapshot) |
| Secrets | None added. The check runs under the job's run-as identity with default notebook authentication; it takes no secret, scope or token parameter and prints names, ids, states and UTC times only; API error text is redacted and cut (G-25, NFR-25). Only `ingest_kafka` receives the scope name, as before |
| Cost | One serverless notebook task per ingestion run (about 18 to 32 s, at most 120 s), one API read. Kafka outage cost halves (one attempt). Test cost on `dev`: one full ingestion run (AC-96), two subset runs and one no-op update (AC-97), one failing run (AC-95), the peak concurrency suite (three full peak runs, one ingestion run, one no-op update) for AC-98; at most one Kafka reset |
| Backfill / reprocessing | Not affected. A refused run leaves only valid Bronze input (ADR 0006); the next update recomputes Silver and Gold from all of Bronze. `--only` lists without `refresh_silver_gold` need no check; lists with it include `check_silver_gold_idle` (runbook rule, AC-99). Running the pipeline directly (`bundle run smart_meter_silver_gold`, full refresh) bypasses both checks; the runbook asks to confirm the pipeline is idle first |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| Race window between the check's read and the pipeline task's start (C-11), in both directions | An update started in those seconds still ends `INTERNAL_ERROR` with the old message | Accepted (D-39, D-48); the check runs directly before the pipeline task (D-50) to keep the window short; the runbook symptom row explains an `INTERNAL_ERROR` after a passed check |
| Fail closed now also on the ingestion side | An API outage, permission change or SDK drift costs the ingestion refresh every day until fixed; with the peak check failing too, Silver and Gold go stale | Bronze is kept, so no data is lost; the message names the failing read; the notebook prints the SDK version; ADR 0013 revisit trigger |
| AC-97 timing (DA-31) | The update may end before the check reads it | Subset run started at once; the test fails loudly rather than passing vacuously; fallbacks in OD-23 |
| The pins move (FR-51) | A careless edit of a pinned or shipped test could weaken a shipped guard | AC-85 limits the YAML change structurally against a byte-exact fixture; AC-92 keeps the shipped guard tests byte-identical and the module diff additions-only; the changed shipped tests are listed one by one (OD-22) |
| Kafka evidence needs Aiven on and off | A power-off empties the topic; the next Kafka-on run needs the Kafka reset | Integration order by the current Aiven state (at most one reset) |
| Trade-off: a second message builder in `pipeline_guard` | About 50 lines that look like the peak builder | Keeps the peak output untouched (AC-92); both are tested; a later refactor can merge them once both directions are stable |
| Trade-off: constants instead of task parameters for the caller | A schedule change needs a code change | `test_ac87_caller_constants_match_the_bundle` fails when the YAML cron and the constant disagree |
| Trade-off: the update, not the peak run, is named (D-49) | The operator finds the peak run from the update's creation time | Runbook explains how; Approach C stays the upgrade path |

---

## Open Items for the User

None. U-06 is not used: every open design item (OD-19 to OD-23) is resolved above within the
user's decisions D-46 to D-59, and the only pending assumption (DA-31, A-31) has a fallback that
needs no decision.

Follow-ups outside this feature (unchanged): reset script guard and its `main()` test (D-52, next
release); `disable_auto_optimization` on pipeline tasks (A-25, needs another mechanism); Approach C if
A-28 is observed; PEAK_MODEL_CONCURRENCY F-04 (SDK drift), now relevant to both jobs.

---

## Self-Review

- **Weak points:**
  - The race window stays in both directions; no test can force it, and the ingestion pipeline task
    has no retry, so an overlap in those seconds still loses the ingestion refresh with the old
    message.
  - AC-97 depends on the no-op update outliving the start of a subset run (DA-31). The test fails
    rather than passes vacuously, but it may need a rerun.
  - The pipeline-only message builder duplicates the shape of the peak one. That is the price of
    proving the peak output unchanged by "additions only".
  - The caller texts (06:00 UTC, 08:00 UTC) are constants tied to the YAML by a test, not read from
    the deployed job; a schedule change in the UI (not in the bundle) would make them stale.
  - AC-98's ingestion-side assertion reads evidence written by a shipped test, so it depends on that
    test having run first with Aiven on.
- **Risks:**
  - Fail-closed doubles the impact of an API or SDK problem: both jobs lose their refresh until it is
    fixed. Bronze is kept.
  - Changing pinned files and shipped tests can hide a regression; the byte-exact fixture, the
    additions-only diff and the unchanged peak suite limit this.
  - The Kafka evidence needs the Aiven service on and off, with a Kafka reset in between, which
    costs time and quota.
- **Trade-offs:** A pipeline-only check avoids the bundle cycle and mutual refusal, and leaves the
  peak side untouched, at the price of not naming the peak run and not guarding a peak run's later
  tasks (A-28). Placing it after the ingest tasks keeps Bronze ingestion when the pipeline is busy,
  but it never runs when `ingest_kafka` fails. Constants keep the task definition minimal but must be
  kept in step with the YAML by a test.
- **What I would do differently (with more budget or time):** I would remove the race window rather
  than narrow it. The pipeline task would move out of both jobs into one small orchestration job
  that owns every pipeline start. The ingestion and peak jobs would trigger it with `run_job_task`,
  so that job queueing (`max_concurrent_runs: 1` with queueing) serialises the updates. Each job
  would reference only that orchestration job, so no cycle forms. This needs a spike for queued
  `run_job_task` runs on Free Edition and a redesign of both jobs' task graphs.
- **Next improvement:** Build entry 1 (`pipeline_guard` append) together with entry 2. Make
  `test_ac92_guard_module_changes_are_additions_only` and the 28 shipped tests the first green gate,
  so any accidental edit of the peak path is caught before the notebook and the YAML exist. Then
  entries 3 to 6 and the deploy gate with AC-94 as the first live step.

---

## Next Step

`/build .claude/sdd/features/DESIGN_INGESTION_GUARD.md`

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-10-23 | Created from DEFINE_INGESTION_GUARD.md (Ready for Design): architecture, guards G-22 to G-27, OD-19 to OD-23 resolved, DA-27 to DA-33 (spike 07 results; DA-31 pending), job layout, library API, notebook outline, changes to shipped tests, 22-entry manifest (one PR), test strategy for AC-81 to AC-99; ADR 0013 written (Accepted) and listed in the ADR index; notes on ADR 0012 and ADR 0008 planned as manifest entries 19 and 20. Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts at entry 1 once the spike 07 branch is merged |
