# DESIGN: Peak Model Concurrency

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL_CONCURRENCY |
| **Date** | 2026-10-22 |
| **Author** | Christian |
| **Source** | DEFINE_PEAK_MODEL_CONCURRENCY.md (status Ready for Design, commit 2c13c60); archived `DESIGN_PEAK_MODEL.md` (layout, guards G-01 to G-12, DA-13 to DA-18) and `SHIPPED_2026-10-22.md` (lessons, F-03, F-05, F-14); ADR 0007, ADR 0008; `resources/smart_meter_peak_model.job.yml`; `tests/test_peak_bundle.py`; `tests/integration/conftest.py`; `docs/runbooks/peak_model.md` |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

---

## Overview

A new first task, `check_pipeline_idle`, runs in the daily job `smart_meter_peak_model` before
`refresh_silver_gold`. It is a serverless notebook task on the existing job environment
`peak_model_env`, with no retries and auto-optimization disabled. It reads two things with the
Databricks SDK under the job's identity: the active runs of `smart_meter_ingestion`, and the latest
updates of `smart_meter_silver_gold`. It identifies both by ids that the bundle passes in as task
parameters. When either is active, the task fails at once with a message naming every blocking run
or update, in UTC with `Z`, and the rerun action. When it cannot read the state, it fails closed with
a message naming what could not be read. The decision logic lives in a new library module,
`pipeline_guard`, which takes a client-like object. Unit tests run it against a recording fake, and
the integration test runner reuses it. The METER_INGESTION job and pipeline and the training job do
not change (ADR 0012, amending ADR 0008).

---

## Architecture

```text
 DATABRICKS FREE EDITION (serverless, target dev)

 METER_INGESTION (unchanged, tag v0.1.0)
   job smart_meter_ingestion 06:00 UTC ... -> refresh_silver_gold --+
                                                                    |  one update at a time
                                                                    v
                                              pipeline smart_meter_silver_gold
                                                                    ^
 Job smart_meter_peak_model (daily 08:00 UTC, max 1 concurrent run) |
 +------------------------------------------------------------------|-----------------------------+
 | [0] check_pipeline_idle (notebook, peak_model_env, 0 retries, auto-optimization off, 300 s)     |
 |       WorkspaceClient() (job identity, default notebook auth)                                   |
 |       pipeline_guard.check(client, ingestion_job_id, pipeline_id)   READ ONLY:                   |
 |         jobs.get(ingestion_job_id)            identity: base name == smart_meter_ingestion      |
 |         jobs.list(name = deployed name)       unique (at most 2 read)                           |
 |         jobs.list_runs(job_id, active_only)   any run not TERMINATED/SKIPPED/INTERNAL_ERROR     |
 |         pipelines.get(pipeline_id)            identity + latest_updates not COMPLETED/FAILED/   |
 |                                               CANCELED                                          |
 |       idle    -> exit value JSON (checked_at ...Z, ids, pipeline state, latest update)          |
 |       busy    -> raise PipelineGuardError(FR-36 message)    -> task FAILED                      |
 |       unknown -> raise PipelineGuardError(FR-38 message)    -> task FAILED (fail closed)        |
 |        |                                                                                        |
 | [1] refresh_silver_gold (pipeline_task, after 0; 1 retry / 600 s for FAILED updates, D-41) -----+
 | [2] ingest_weather (unchanged, no dependency)                                                   |
 | [3] build_weather_silver (unchanged, after 2)                                                   |
 | [4] build_features (unchanged: after 1 and 3)   [5] build_labels (unchanged: after 1)           |
 | [6] score_predictions (unchanged: after 4 and 5)                                                |
 +-------------------------------------------------------------------------------------------------+
   levels: L0 {check_pipeline_idle, ingest_weather}  L1 {refresh_silver_gold, build_weather_silver}
           L2 {build_features, build_labels}         L3 {score_predictions}      widest level: 2
   pre-check FAILED -> refresh_silver_gold, build_features, build_labels, score_predictions
                       end UPSTREAM_FAILED; ingest_weather and build_weather_silver still run
```

---

## Components

Package path `src/smart_meter_peak_prediction/` is abbreviated `pkg/`.

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Guard library (`pkg/pipeline_guard.py`) | Pure decision logic over a client-like object: id parsing (G-13), identity and uniqueness reads (G-14, G-15), active-run and active-update classification (G-16, G-17), the FR-36 and FR-38 messages, UTC formatting with `Z`, the exit-value dictionary, bounded client construction. Standard library only; it never imports the SDK, so CI needs no SDK. It reads enum values through `.value` when present, otherwise `str()` | Python 3.11 stdlib | FR-34 to FR-38, NFR-20 to NFR-23 |
| Pre-check notebook (`notebooks/check_pipeline_idle.py`) | Wiring only: `src_path`, widgets `ingestion_job_id` and `pipeline_id`, UTC session setting and assertion (project rule), `pipeline_guard.run(WorkspaceClient, ...)`, print the message, `pipeline_guard.enforce(report)` (raises on busy or unknown), `dbutils.notebook.exit(json)` on idle. No try/except (I-14), no `%pip`, no secrets | Databricks notebook, serverless environment version 2 | FR-33, FR-36, FR-37, NFR-20 |
| Daily job resource (`resources/smart_meter_peak_model.job.yml`) | New task `check_pipeline_idle`; `refresh_silver_gold` depends on it; comment on the D-41 retry and the refused update | Databricks Asset Bundles | FR-33, FR-42, NFR-19, NFR-23 |
| Integration runner (`tests/integration/conftest.py`) | `PeakRunner.assert_ingestion_idle` delegates to `pipeline_guard.check` (one definition of "active"); `run(..., require_idle=False)` for the busy-case tests; outputs skip tasks that never ran | pytest, databricks-sdk | AC-74 to AC-77 support |
| Tests | Unit: guard with a recording fake (AC-69 to AC-73), bundle graph and unchanged definitions (AC-68, AC-78), docs (AC-79), secrets (AC-80). Integration: busy and idle runs on `dev` (AC-74 to AC-77) | pytest | All AC |
| Runbook, ADRs, README | Concurrency section and troubleshooting row, `--only` commands with the pre-check, evidence order; ADR 0012 (new), dated note in ADR 0008 | Markdown | FR-40, FR-41 |
| Spike 06 (`spikes/databricks/06_*`) | Pre-build probe of every platform call the guard depends on (DA-20, DA-22, DA-23, DA-26); never imported | Python, databricks-sdk | Risk reduction (SHIPPED lesson "probe every client call") |

---

## Data Model

This feature creates, writes and changes no table, view, volume, contract or model. It reads
platform metadata only, and its output is one task outcome per daily run attempt. The PEAK_MODEL
tables and the contracts in `docs/contracts/` are unchanged.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| Runs of job `smart_meter_ingestion` (Jobs API, read) | platform metadata | One job run | `run_id` | - | Fields used: `run_id`, `state.life_cycle_state`, `start_time` (epoch ms, UTC) |
| Job `smart_meter_ingestion` (Jobs API, read) | platform metadata | One job | `job_id` | - | Fields used: `job_id`, `settings.name` (development prefix stripped for the identity check) |
| Pipeline `smart_meter_silver_gold` (Pipelines API, read) | platform metadata | One pipeline | `pipeline_id` | - | Fields used: `name`, `state` (diagnostic only), `latest_updates[].update_id`, `.state`, `.creation_time` (format probed in DA-22) |
| Pre-check outcome | task run | One `check_pipeline_idle` task run | job `run_id`, task `run_id` | - | `SUCCESS` with the JSON exit value below, or `FAILED` with the FR-36 or FR-38 message as the task error |

Exit value on success (keys fixed, values illustrative):

```json
{
  "outcome": "idle",
  "checked_at": "2026-10-23T08:00:41Z",
  "ingestion_job": {"job_id": 123456789, "name": "smart_meter_ingestion", "active_runs": []},
  "pipeline": {"pipeline_id": "0a1b-...", "name": "smart_meter_silver_gold", "state": "IDLE",
               "latest_update": {"update_id": "3c4d-...", "state": "COMPLETED"}}
}
```

Failure message (FR-36; every blocker on its own line; all times UTC with `Z`):

```text
check_pipeline_idle stopped the run before refresh_silver_gold: the shared pipeline is busy (checked at 2026-10-23T08:00:41Z).
Blocking:
  - job smart_meter_ingestion (job id 123456789): active run 1002990004411119, state RUNNING, started 2026-10-23T07:58:02Z
  - pipeline smart_meter_silver_gold (pipeline id 0a1b-...): update 3c4d-..., state RUNNING, created 2026-10-23T07:59:10Z
Action: wait until the run or update named above ends, then rerun smart_meter_peak_model.
Without action, the next scheduled run (08:00 UTC) is the retry. refresh_silver_gold and the tasks after it did not start; rerunning is safe.
```

Failure message (FR-38, fail closed):

```text
check_pipeline_idle could not establish the pipeline state and fails closed (checked at 2026-10-23T08:00:41Z).
Could not read:
  - job smart_meter_ingestion (job id 123456789): active runs: PermissionDenied (PERMISSION_DENIED): <first line of the API error, at most 200 characters>
Action: fix the cause named above (deployment, permission or API availability), then rerun smart_meter_peak_model.
Without action, the next scheduled run (08:00 UTC) checks again.
```

When both blockers and unreadable items exist, the message has both blocks; the outcome is a
failure either way. A run that is queued and has no start time reads `not started`; a creation time
that cannot be parsed reads `creation time not reported`, so no non-UTC time is ever printed. The
error text from the API is cut to its first line and 200 characters, and holds names and ids only;
no header, token or host is formatted into the message.

### Data quality rules (guards)

There is no profiled data, so the source column names the requirement or decision. G numbers
continue after PEAK_MODEL (G-01 to G-12). Every guard ends the pre-check task `FAILED` before
`refresh_silver_gold` starts.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| G-13 `ingestion_job_id` is a positive integer and `pipeline_id` is non-empty; neither contains an unresolved bundle reference (`${`) | task parameters | `fail` (FR-38 message: "id missing or not resolved") | FR-38, D-45, OD-14 |
| G-14 `jobs.get(ingestion_job_id)` succeeds, its name with the development prefix stripped equals `smart_meter_ingestion`, and `jobs.list(name = deployed name)` returns exactly 1 job (at most 2 read) | ingestion job | `fail` (not found, other name, or not unique, with the ids found) | FR-38, D-45, AC-73, U-01 |
| G-15 `pipelines.get(pipeline_id)` succeeds and its name with the development prefix stripped equals `smart_meter_silver_gold` | pipeline | `fail` (not found or other name) | FR-38, D-45, AC-73 |
| G-16 no run of the ingestion job from `jobs.list_runs(job_id, active_only = True)` has a non-terminal life-cycle state (terminal: `TERMINATED`, `SKIPPED`, `INTERNAL_ERROR`; any other value, including a future one, is active). At most 25 runs are read | ingestion runs | `fail` (FR-36 message) | FR-34, A-20, DA-21 |
| G-17 no entry of `latest_updates` has a non-terminal state (terminal: `COMPLETED`, `FAILED`, `CANCELED`; any other value, including a missing or future one, is active) | pipeline updates | `fail` (FR-36 message) | FR-35, A-20, DA-22 |
| G-18 every read is wrapped: an exception from the SDK becomes an "unreadable" item naming the object, the read and the error class and code; client construction failure is an unreadable item for both objects | all reads | `fail` (fail closed, never success) | FR-38, D-45 |
| G-19 read-only: the module calls only `jobs.get`, `jobs.list`, `jobs.list_runs` and `pipelines.get` (`READ_CALLS`); the unit fake raises and records any other attribute | client | `fail` in tests (AC-69, AC-72) | FR-37, NFR-21 |
| G-20 bounded time: one read per object, no loop or sleep; the client is built with `retry_timeout_seconds = 60` and `http_timeout_seconds = 30` (DA-20); the task timeout is 300 s | pre-check task | `fail` (timeout ends the task `TIMEDOUT`; 0 retries) | NFR-19, NFR-23, D-43 |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-14 | **Bundle references, passed as task base parameters.** `ingestion_job_id` is the bundle reference to the id of the job resource `smart_meter_ingestion`, and `pipeline_id` is the reference to the id of the pipeline resource `smart_meter_silver_gold` (YAML in *Bundle and job layout*). The guard confirms the identity by name (G-14, G-15). A-22 is met by construction: the ids belong to the target being deployed | All files under `resources/` are merged into one bundle configuration (`include: resources/*.yml`), so a resource in one file can reference a resource in another. The same file already references the pipeline id for `refresh_silver_gold`, which is deployed and proven. The Databricks bundle documentation lists the job id substitution among the named-resource substitutions (DA-19). Name lookup (the conftest prior art) would depend on the display prefix and could match another deployment (DEFINE risk) |
| OD-15 | **Serverless notebook task** on the existing `peak_model_env` (serverless environment version 2), `max_retries: 0`, `disable_auto_optimization: true`, `timeout_seconds: 300`. No `%pip`: the environment ships `databricks-sdk` (version probed, DA-20). Client: `WorkspaceClient()` with default authentication, which in a notebook uses the runtime credentials of the job's run-as identity; no secret, no token parameter | A notebook task matches every other PEAK_MODEL task (widgets, `src_path`, exit value, error output read by `PeakRunner`), and the existing G-01 test (every notebook task on `peak_model_env`) holds without change. A Python script task would add a second wiring pattern and has not been run on this workspace. `disable_auto_optimization` is the only setting that stopped a serverless retry (D-21); `max_retries: 0` alone did not. 300 s leaves room for a slow serverless start while staying far below the job timeout; the 120 s budget of NFR-19 is a measured target (AC-74 to AC-76), not the timeout, so a slow start is not mistaken for a busy pipeline |
| OD-16 | **Task key `check_pipeline_idle`; logic in `pkg/pipeline_guard.py`.** Public API: `check(client, ingestion_job_id, pipeline_id, *, now=None) -> GuardReport`; `run(client_factory, ingestion_job_id, pipeline_id, *, now=None) -> GuardReport` (catches client construction errors, G-18); `enforce(report) -> dict` (raises `PipelineGuardError(report.message())` unless `report.ok`, otherwise returns the exit value); `utc_text(value) -> str or None`; `strip_dev_prefix(name)`; constants `INGESTION_JOB`, `PIPELINE`, `PEAK_JOB`, `TERMINAL_RUN_STATES`, `TERMINAL_UPDATE_STATES`, `READ_CALLS`, `CLIENT_LIMITS`. **Active run:** listed by `jobs.list_runs(job_id = id, active_only = True)` and its `state.life_cycle_state` value not in `TERMINATED`, `SKIPPED`, `INTERNAL_ERROR`. **Active update:** an entry of `pipelines.get(id).latest_updates` whose `state` value is not in `COMPLETED`, `FAILED`, `CANCELED`. Unknown or missing values count as active. `pipelines.get(...).state` is reported, not used for the decision. **Reuse:** `PeakRunner.assert_ingestion_idle` calls `check` (cheap, done here; it keeps its extra pipeline `IDLE` assertion). The reset script (PEAK_MODEL F-03) is not changed: it has no bundle ids, needs the peak jobs idle as well and has no `main()` test, so reuse there stays with F-03 | `active_only` is the API's own definition of active (QUEUED, PENDING, RUNNING, TERMINATING per the SDK documentation) and the prior art that passed in 27 integration tests; classifying the returned states again implements FR-34 literally and makes AC-69 testable per state. `latest_updates` is ordered newest first (SDK documentation) and comes with the identity read, so one call covers FR-35 and G-15. Comparing `.value` strings keeps the module SDK-free; a unit test cross-checks the constants against the SDK enums when the SDK is installed |
| OD-17 | **New ADR 0012** (drafted, Proposed) that amends the task graph of ADR 0008, plus a dated note in ADR 0008 *Consequences* pointing to ADR 0012 (manifest entry 16). ADR 0008 stays Accepted, not superseded | The pre-check, its identification by bundle ids and fail-closed rule are lasting decisions with their own options (wait, condition task, name lookup), more than a note can hold. ADR 0008's other decisions (pipeline task first, separate training job) stand. AC-79 needs an Accepted ADR recording D-39: ADR 0012 after the user accepts it (U-03) |
| OD-18 | **Existing tests that change** (assertions extended, none weakened): see *Changes to shipped tests* below. The AC-62 text holds as written: the scoring task still reaches `refresh_silver_gold`, there is no training task in the schedule, and there is one pipeline | The graph test asserts the exact task list, dependencies and timeouts, so it must name the new task; every other AC-62 assertion stays |

### Changes to shipped tests (OD-18)

| File | Test | Change |
|---|---|---|
| `tests/test_peak_bundle.py` | module constant `PEAK_NOTEBOOKS` | Add `check_pipeline_idle.py`. This puts the new notebook under `test_ac63_job_parameters_reach_declared_notebook_widgets`, `test_g01_pip_pins_equal_pinned_requirements_and_restart_precedes_path_setup` (no `%pip` expected), `test_ac37_notebooks_set_and_assert_utc_and_have_no_try_except`, `test_ac63_every_peak_notebook_task_exists_and_points_at_a_notebook` and `test_ac62_notebooks_and_sources_never_import_spike_code` |
| `tests/test_peak_bundle.py` | `test_ac62_daily_job_graph_schedule_and_pipeline_dependency` | Task list gains `check_pipeline_idle` first (7 tasks); `depends(check_pipeline_idle) == []`; `depends(refresh_silver_gold) == ["check_pipeline_idle"]` (was `[]`); timeout list `[300, 2700, 900, 900, 1800, 1800, 1800]`; new assertion `check_pipeline_idle` in `ancestors(score_predictions)`. Width 2, pipeline task, retry 1 / 600000, schedule, `max_concurrent_runs`, job timeout and serverless assertions unchanged |
| `tests/test_peak_bundle.py` | `test_ac63_job_parameters_reach_declared_notebook_widgets` | The set of widgets allowed outside `Settings` and `PeakParameters` becomes `experiment_path`, `git_commit`, `ingestion_job_id`, `pipeline_id` |
| `tests/test_peak_bundle.py` | `test_ac62_library_calls_used_by_the_notebooks_exist` | Module set gains `pipeline_guard` |
| `tests/test_peak_bundle.py` | `test_g01_every_notebook_task_runs_on_serverless_environment_version_2`, `test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged`, `test_ac62_training_is_on_demand_only`, `test_ac53_training_task_is_never_retried_by_the_platform` | No change; they now also cover the new task or confirm the unchanged files |
| `tests/integration/test_peak_deployment.py` | `DAILY_TASKS`, `_task_view`, `_yaml_task_view`, `test_ac62_deployed_jobs_pipeline_and_run_durations` | `DAILY_TASKS` gains `check_pipeline_idle`. Both task views gain `disable_auto_optimization` compared as `bool(...)` (the API omits false booleans; SHIPPED lesson). The latest full successful run must now include the pre-check (AC-76 provides it) |
| `tests/integration/conftest.py` | `PeakRunner` | `assert_ingestion_idle` delegates to `pipeline_guard.check` and keeps the pipeline `IDLE` assertion; `run` gains `require_idle: bool = True`; output collection skips tasks whose result is `UPSTREAM_FAILED` or `UPSTREAM_CANCELED` (never ran) besides `DISABLED` |
| `tests/integration/test_deployment.py` (METER_INGESTION AC-28 layout), `test_peak_data.py`, `test_peak_scoring.py`, `test_peak_training.py` | - | No change: the ingestion job is unchanged, and these tests start only subsets without `refresh_silver_gold` |
| `docs/runbooks/peak_model.md` | bootstrap step 1 command and Concurrency step 2 | `--only check_pipeline_idle,refresh_silver_gold,ingest_weather,build_weather_silver,build_features,build_labels`; the prose `--only` mentions name `check_pipeline_idle,refresh_silver_gold` |

### Assumption dependencies

DA numbers continue after PEAK_MODEL (DA-13 to DA-18). Following the SHIPPED lesson ("probe every
client call the DESIGN depends on before the build"), spike 06 checks DA-20, DA-22, DA-23 and DA-26
before manifest entry 4. A failure applies the listed fallback through `/iterate`.

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| DA-19 The bundle reference to the id of job resource `smart_meter_ingestion` resolves in a task base parameter of another job file in the same bundle, in development mode | OD-14, G-13 | `databricks bundle validate -t dev`, deploy, then `jobs.get(peak job)`: the pre-check task's `ingestion_job_id` equals the deployed ingestion job id (manifest entry 7 gate; also asserted by AC-76's exit value) | Lookup by name with the development prefix stripped, scoped by the deploying user's prefix; DEFINE A-22 then stays a risk |
| DA-20 Serverless environment version 2 ships `databricks-sdk` (documentation lists 0.40.0; another listing 0.36.0) with `jobs.list_runs(active_only)`, `jobs.list(name)`, `pipelines.get(...).latest_updates`; `WorkspaceClient()` authenticates in a job notebook task as the run-as identity with no configuration; the `Config` accepts `retry_timeout_seconds` and `http_timeout_seconds` | OD-15, G-20 | Spike 06: one-off serverless notebook run on environment version 2 prints the SDK version, `current_user.me()`, and reads `jobs.get` and `pipelines.get` of the deployed objects | `%pip install databricks-sdk==<probed version>` plus restart in the notebook (the G-01 test then lists it as an ML-style notebook); without the timeout keywords, rely on the 300 s task timeout |
| DA-21 `jobs.list_runs(job_id, active_only=True)` returns every run of the job that is not terminal, including a queued run | G-16, FR-34 | AC-74 (a RUNNING run, live). Queued, blocked and waiting-for-retry runs cannot be forced on Free Edition; unit tests cover the classification | Read the newest page (`limit = 25`, no `active_only`) and classify every run in code |
| DA-22 During an update, `pipelines.get(id).latest_updates[0]` shows that update with its `update_id`, a non-terminal state within seconds of `start_update`, and a `creation_time` that `utc_text` can parse (epoch ms digits or ISO 8601 with zone) | G-17, FR-36, AC-75 | Spike 06: `start_update(full_refresh=False)`, then read every 2 s until terminal; record the state sequence and the `creation_time` text | `pipelines.list_updates(pipeline_id, max_results=5)` (`UpdateInfo`, `creation_time` in epoch ms); an unparseable time is printed as "creation time not reported" in any case |
| DA-23 `jobs.list(name=<deployed name>)` filters on the exact display name, including the `[dev <user>] ` prefix | G-14 (uniqueness) | Spike 06: list with the deployed name returns exactly the ingestion job | Read the job list with the prefix stripped and compare in code (at most 200 jobs read) |
| DA-24 A notebook task that raises ends with result `FAILED` and the exception text appears in `jobs.get_run_output(task_run_id).error`; dependents end `UPSTREAM_FAILED` | FR-36, AC-74, AC-75 | Prior art: AC-60 live test reads the scoring task error naming the missing date. AC-74 asserts it again | - (validated by prior art) |
| DA-25 `max_retries: 0` with `disable_auto_optimization: true` on a serverless notebook task gives exactly one attempt | NFR-23, D-43 | Prior art: `train_model` since D-21. AC-74 and AC-75 assert one task run of `check_pipeline_idle` with `attempt_number` 0 | None needed beyond the assertion; a second attempt would only repeat a read |
| DA-26 An update with no new input stays non-terminal for longer than the time from `run_now` of the peak job to the pre-check's read (expected: update about 2 to 3 min including serverless start; pre-check read about 30 to 60 s after `run_now`) | AC-75 | Spike 06 measures `start_update` to terminal; AC-75 asserts the pre-check error contains U | If the update is too short, AC-75 starts the peak run first with `only=[check_pipeline_idle, refresh_silver_gold]` right after `start_update` (already the plan) and, if still too short, records AC-75 as `Partial` with a direct `pipeline_guard.check` read during U as evidence |

**Spike 06 is recommended** (two files, one serverless notebook run of about 1 minute and one no-op
pipeline update of about 3 minutes, no table change). It is small, but DA-20 and DA-22 decide
whether the notebook can run at all and what the message prints, and the PEAK_MODEL gate showed that
unprobed client calls cost a redeploy each (D-20 to D-23). The documentation is not reliable enough
for DA-20: the environment version 2 page lists `mlflow-skinny` 2.11.4 while spike 05 measured
MLflow 3.17.2 on the same environment. DA-19 is checked by the deploy itself and DA-21 by AC-74.

### Bundle and job layout

`databricks.yml`, `resources/smart_meter_ingestion.job.yml`,
`resources/smart_meter_silver_gold.pipeline.yml` and
`resources/smart_meter_peak_model_training.job.yml` are not changed. Only the daily job file
changes:

```yaml
# resources/smart_meter_peak_model.job.yml (changed part)
      tasks:
        # Read-only pre-check (ADR 0012): fails at once, naming the blocking ingestion run or
        # pipeline update, when the shared pipeline is busy; fails closed when the state cannot be
        # read. Never retried: max_retries 0 alone does not stop a serverless retry (D-21).
        - task_key: check_pipeline_idle
          timeout_seconds: 300
          max_retries: 0
          disable_auto_optimization: true
          environment_key: peak_model_env
          notebook_task:
            notebook_path: ../notebooks/check_pipeline_idle.py
            base_parameters:
              src_path: ${workspace.file_path}/src
              ingestion_job_id: ${resources.jobs.smart_meter_ingestion.id}
              pipeline_id: ${resources.pipelines.smart_meter_silver_gold.id}

        # One retry after 10 minutes for a transient FAILED update (D-41). An update refused because
        # another update is in progress ends INTERNAL_ERROR and is not retried; check_pipeline_idle
        # prevents the visible cases, and a retry does not rerun the pre-check (ADR 0012).
        - task_key: refresh_silver_gold
          depends_on:
            - task_key: check_pipeline_idle
          timeout_seconds: 2700
          max_retries: 1
          min_retry_interval_millis: 600000
          pipeline_task:
            pipeline_id: ${resources.pipelines.smart_meter_silver_gold.id}
            full_refresh: false
        # ingest_weather, build_weather_silver, build_features, build_labels, score_predictions:
        # unchanged
```

**Notebook (`notebooks/check_pipeline_idle.py`) outline.**

```python
# Databricks notebook source
# Read-only pre-check before refresh_silver_gold (FR-33 to FR-38, ADR 0012). No try/except (I-14).
import json, os, sys
dbutils.widgets.text("src_path", "")
# ... src_path to sys.path, as the other notebooks
from smart_meter_peak_prediction import pipeline_guard  # noqa: E402

_widget_names = ("ingestion_job_id", "pipeline_id")
for _name in _widget_names:
    dbutils.widgets.text(_name, "")
spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

from databricks.sdk import WorkspaceClient  # noqa: E402

report = pipeline_guard.run(
    lambda: WorkspaceClient(**pipeline_guard.CLIENT_LIMITS),
    dbutils.widgets.get("ingestion_job_id"),
    dbutils.widgets.get("pipeline_id"),
)
print(report.message())
result = pipeline_guard.enforce(report)  # raises PipelineGuardError: task FAILED with the message
dbutils.notebook.exit(json.dumps(result))
```

**Concurrency.** The widest level stays 2 tasks (`check_pipeline_idle` with `ingest_weather`), so
with an overlapping ingestion run (at most 2 tasks) at most 4 tasks run at once, below the Free
Edition limit of 5 (NFR-19).

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| 0012 | A read-only pre-check before the shared pipeline task in the daily peak job, failing fast and closed (D-39, D-41 to D-45, OD-14 to OD-17; amends ADR 0008) | Proposed |
| 0008 | PEAK_MODEL jobs (existing). Gets a dated note pointing to ADR 0012 at build (manifest entry 16); stays Accepted | Accepted |

---

## Delivery Plan

| Step | Scope | Manifest entries | Files |
|---|---|---|---|
| Spike (own branch, before the build) | Spike 06 and its record | 1 to 3 | 3 |
| PR 1 (single feature PR) | Library, notebook, job, tests, docs | 4 to 18 | 15 |

**Gate inside PR 1.** After entry 7, `databricks bundle validate -t dev` and `bundle deploy -t dev`
(exit codes recorded), then the AC-76 full run, before the busy-case tests (AC-74, AC-75, AC-77).
If the pre-check fails on a platform behaviour, apply the DA fallback through `/iterate` first.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Package path
`src/smart_meter_peak_prediction/` is abbreviated `pkg/`. Agents: `pipeline-builder` for the
library, notebook, bundle and tests; `build-agent` for documents. No `mlflow` or `kafka` module
agent applies.

Existing inputs, read and not modified: `databricks.yml`, `resources/smart_meter_ingestion.job.yml`,
`resources/smart_meter_silver_gold.pipeline.yml`, `resources/smart_meter_peak_model_training.job.yml`
(AC-78), `scripts/reset_peak_model_outputs.py` (F-03 stays open), `pkg/peak_config.py`.

| # | PR | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|---|
| 1 | spike | `spikes/databricks/06_spike_pipeline_guard_probe.py` | Create | Notebook run on serverless environment version 2: print `databricks.sdk.version`, `current_user.me().user_name`, `jobs.get` and `jobs.list(name=...)` of the deployed ingestion job, `pipelines.get` of the pipeline (state, `latest_updates`, raw `creation_time`), construct the client with the G-20 keywords. Question and pass criteria at the top (DA-20, DA-23) | pipeline-builder | - |
| 2 | spike | `spikes/databricks/06_spike_pipeline_guard_probe_submit.py` | Create | Local driver (CLI profile): uploads and submits entry 1 as a one-time serverless run on environment version 2 (spike 05 pattern); then, with the ingestion job idle, `pipelines.start_update(full_refresh=False)` and reads `pipelines.get` every 2 s until terminal, printing the state sequence, `creation_time` text and duration (DA-22, DA-26). Prints PASS or FAIL per DA; no table change | pipeline-builder | 1 |
| 3 | spike | `docs/spikes/README.md` | Update | Record row for spike 06 with the measured results; the results also go into ADR 0012 *Platform probe* | build-agent | 2 |
| 4 | 1 | `pkg/pipeline_guard.py` | Create | Constants, `strip_dev_prefix`, `utc_text`, `ActiveRun`, `ActiveUpdate`, `GuardReport` (`ok`, `message()`, `exit_value()`), `PipelineGuardError`, `check`, `run`, `enforce`, `CLIENT_LIMITS` (G-13 to G-20; FR-34 to FR-38) | pipeline-builder | 3 |
| 5 | 1 | `tests/test_pipeline_guard.py` | Create | Recording fake workspace (read methods only; any other attribute is recorded and raises) and AC-69 to AC-73 tests; SDK enum cross-check with `pytest.importorskip("databricks.sdk")` | pipeline-builder | 4 |
| 6 | 1 | `notebooks/check_pipeline_idle.py` | Create | Wiring of the outline above (FR-33, FR-36, FR-37) | pipeline-builder | 4 |
| 7 | 1 | `resources/smart_meter_peak_model.job.yml` | Update | New task `check_pipeline_idle`, `refresh_silver_gold` depends on it, header and retry comments (FR-33, FR-42; layout above) | pipeline-builder | 6 |
| 8 | 1 | `tests/test_peak_bundle.py` | Update | OD-18 changes; new `test_ac68_*` and `test_ac78_*` (training job SHA-256 pinned from tag `v0.2.0`, plus `git show v0.2.0:<file>` when the tag exists) | pipeline-builder | 7 |
| 9 | 1 | `tests/test_secrets_hygiene.py` | Update | New `test_ac80_*` | pipeline-builder | 6, 7 |
| 10 | 1 | `tests/integration/conftest.py` | Update | `PeakRunner` changes of OD-18; helpers `start_ingestion_run`, `wait_life_cycle`, `task_runs_by_key` | pipeline-builder | 4 |
| 11 | 1 | `tests/integration/test_peak_deployment.py` | Update | OD-18 changes (task set, `disable_auto_optimization` view) | pipeline-builder | 7, 10 |
| 12 | 1 | `tests/integration/test_peak_concurrency.py` | Create | AC-74 to AC-77 live tests, evidence in `out/evidence/` | pipeline-builder | 10 |
| 13 | 1 | `docs/runbooks/peak_model.md` | Update | Diagram, Concurrency section (pre-check, message content, rerun action, D-41 retry), `--only` commands with `check_pipeline_idle`, evidence order for `test_peak_concurrency.py` (AC-76, AC-74, AC-77, AC-75), troubleshooting rows (pre-check busy, pre-check unreadable, `refresh_silver_gold` `INTERNAL_ERROR` now meaning the race window) | build-agent | 7, 12 |
| 14 | 1 | `docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md` | Update | Fill *Platform probe* from spike 06; status `Accepted` after the user's review (U-03) | build-agent | 3, 7 |
| 15 | 1 | `docs/adr/README.md` | Update | Status of 0012 (row added at design) | build-agent | 14 |
| 16 | 1 | `docs/adr/0008-peak-model-jobs-and-pipeline-dependency.md` | Update | Dated note in *Consequences*: the daily graph starts with `check_pipeline_idle` (ADR 0012); the refused-update consequence now applies to the race window only | build-agent | 14 |
| 17 | 1 | `tests/test_peak_concurrency_docs.py` | Create | AC-79 | build-agent | 13, 14, 15 |
| 18 | 1 | `README.md` | Update | Peak job diagram line starts with the pre-check; "Coexistence with ingestion" bullet; link to ADR 0012 | build-agent | 13, 14 |

---

## Test Strategy

Levels as in PEAK_MODEL: **Unit** (pytest, no workspace, runs in CI), **Integration** (marker
`integration`, deployed `dev` target, user-run in the runbook order). Every test name contains its
AC id. The unit fake is a `FakeWorkspace` with `jobs` and `pipelines` attributes; each exposes only
the read methods of `READ_CALLS` and records `(api, method, kwargs)`. Any other attribute access is
recorded as forbidden and raises. Errors are simulated with exception classes carrying
`error_code` (`RESOURCE_DOES_NOT_EXIST`, `PERMISSION_DENIED`) as the SDK errors do. A fixed `now`
makes messages comparable. UTC check: every substring that looks like a date-time
(`\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}\S*`) must fully match `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z`.

Integration order (runbook): AC-76, then AC-74, then AC-77 (needs both snapshots), then AC-75.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-68 | Unit | `tests/test_peak_bundle.py::test_ac68_pre_check_task_precedes_the_pipeline_and_is_never_retried` | `check_pipeline_idle` exists, has `notebook_task` and no `pipeline_task`, `max_retries` 0 and `disable_auto_optimization` true, `environment_key` `peak_model_env`; `depends(refresh_silver_gold) == ["check_pipeline_idle"]`; it is in `ancestors` of `build_features`, `build_labels` and `score_predictions`; `ingest_weather` has no dependency and `build_weather_silver` depends on `ingest_weather` only (v0.2.0); widest level 2; schedule `0 0 8 * * ?` UTC and `max_concurrent_runs` 1; base parameters are exactly `src_path` and the two bundle id references |
| AC-68 | Unit | `tests/test_peak_bundle.py::test_ac62_daily_job_graph_schedule_and_pipeline_dependency` (updated, OD-18) | The exact 7-task list, dependencies and timeouts |
| AC-68 | Integration | `tests/integration/test_peak_deployment.py::test_ac62_deployed_jobs_pipeline_and_run_durations` (updated) | The deployed task views, including `disable_auto_optimization`, equal the YAML |
| AC-69 | Unit | `tests/test_pipeline_guard.py::test_ac69_active_ingestion_run_fails_with_job_run_id_and_action` | Parametrized over `QUEUED`, `PENDING`, `RUNNING`, `TERMINATING`, `BLOCKED`, `WAITING_FOR_RETRY` and one unknown value: `report.ok` is false, `enforce` raises `PipelineGuardError`; the message contains `smart_meter_ingestion`, run id R, "rerun smart_meter_peak_model" and "08:00 UTC"; the UTC check passes; the fake's forbidden list is empty and every recorded call is in `READ_CALLS` |
| AC-69 | Unit | `tests/test_pipeline_guard.py::test_ac69_listed_run_in_a_terminal_state_does_not_block` | A run returned by `active_only` but already `TERMINATED` (list race) does not block |
| AC-69 | Unit | `tests/test_pipeline_guard.py::test_ac69_state_constants_match_the_sdk_enums` | With the SDK installed (`importorskip`): the terminal run states and update states are members of `RunLifeCycleState` and `UpdateInfoState` / `UpdateStateInfoState`, and every other enum member is classified active |
| AC-70 | Unit | `tests/test_pipeline_guard.py::test_ac70_update_state_decides_the_outcome` | Parametrized over the 8 non-terminal update states (`CREATED`, `QUEUED`, `INITIALIZING`, `RESETTING`, `SETTING_UP_TABLES`, `RUNNING`, `STOPPING`, `WAITING_FOR_RESOURCES`), an unknown value and a missing state: failure, the message contains `smart_meter_silver_gold`, U and S. For `COMPLETED`, `FAILED`, `CANCELED`: success, `enforce` returns the exit value with `outcome` `idle` |
| AC-70 | Unit | `tests/test_pipeline_guard.py::test_ac70_creation_time_is_printed_in_utc_or_not_at_all` | `utc_text` turns epoch ms (int and digit string) and ISO 8601 with `Z` or an offset into `...Z`; a naive or garbage string gives None and the message says "creation time not reported" |
| AC-71 | Unit | `tests/test_pipeline_guard.py::test_ac71_both_blockers_are_named` | Active run R and active update U: one failure whose message contains R and U on separate lines |
| AC-72 | Unit | `tests/test_pipeline_guard.py::test_ac72_idle_state_succeeds_twice_with_read_calls_only` | No active run, and the pipeline has no update (empty `latest_updates`) or a terminal latest update: two `check` calls with the same fixed `now` give equal reports and equal exit values; with different `now` values only `checked_at` differs; every recorded call is a read |
| AC-73 | Unit | `tests/test_pipeline_guard.py::test_ac73_unreadable_state_fails_closed` | Parametrized: job id not found, job name list returns 2 jobs, job id names another job, pipeline id not found, pipeline id names another pipeline, `jobs.list_runs` raises a generic error, `pipelines.get` raises `PERMISSION_DENIED`, empty id, unresolved `${...` id, non-integer job id, client factory raises. Each: `report.ok` false, `enforce` raises, the message names the job or the pipeline that could not be read and the read; no case returns success |
| AC-74 | Integration | `tests/integration/test_peak_concurrency.py::test_ac74_pre_check_refuses_a_run_while_ingestion_is_active` | From idle, `jobs.run_now` on `smart_meter_ingestion` gives R; wait until R is `RUNNING`; full peak run with `require_idle=False`, expect `FAILED`. Pre-check: `FAILED`, one task run with `attempt_number` 0, duration at most 120 s, error contains R and the action; R had not ended before the pre-check ended (precondition). `refresh_silver_gold`, `build_features`, `build_labels`, `score_predictions`: `UPSTREAM_FAILED`. Wait for R to end; if R's `refresh_silver_gold` ran, its error does not contain "Pipeline update already in progress."; whether it ran is saved in `ac74_refused_run` evidence (U-02) |
| AC-75 | Integration | `tests/integration/test_peak_concurrency.py::test_ac75_pre_check_refuses_a_run_while_a_pipeline_update_is_active` | No active ingestion run; `pipelines.start_update(full_refresh=False)` gives U; at once a peak run with `only=["check_pipeline_idle", "refresh_silver_gold"]`, expect `FAILED`. Pre-check `FAILED` within 120 s, one attempt, error contains U; `refresh_silver_gold` `UPSTREAM_FAILED`. After U ends, `pipelines.list_updates` lists no update whose `creation_time` lies between the peak run's start and end. A pre-check that passed because U had already ended fails the test with the DA-26 advice |
| AC-76 | Integration | `tests/integration/test_peak_concurrency.py::test_ac76_full_run_passes_the_pre_check_and_every_task_succeeds_first_time` | Idle state; full daily run `SUCCESS`; every task one run with `attempt_number` 0 and `SUCCESS`; pre-check at most 120 s; its exit value has `outcome` `idle` and the deployed ingestion job id and pipeline id (DA-19, A-21). Durations of all tasks saved to `ac76_run_durations` (for the build report); predictions of the default target date T snapshotted to `ac77_before` (count, checksum without `_scored_at`, max `_scored_at`) |
| AC-77 | Integration | `tests/integration/test_peak_concurrency.py::test_ac77_rerun_after_refusal_succeeds_and_changes_only_scored_at` | Loads `ac74_refused_run` and `ac77_before`; asserts R has ended; runs the daily job with no other step, expect `SUCCESS`; rows of T: same count and checksum without `_scored_at`, `_scored_at` later than the snapshot |
| AC-78 | Unit | `tests/test_peak_bundle.py::test_ac78_ingestion_pipeline_and_training_definitions_unchanged_and_retry_kept` | SHA-256 of the ingestion job and pipeline files equal the v0.1.0 pins; SHA-256 of `resources/smart_meter_peak_model_training.job.yml` equals the v0.2.0 pin, and equals `git show v0.2.0:<file>` when the tag exists; `refresh_silver_gold` has `max_retries` 1 and `min_retry_interval_millis` 600000; the job file comment states that a refused update is not retried |
| AC-78 | Unit | `tests/test_peak_bundle.py::test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged` (unchanged) | The v0.1.0 comparison, kept as the shipped guard |
| AC-79 | Unit | `tests/test_peak_concurrency_docs.py::test_ac79_runbook_only_commands_include_the_pre_check` | Every `--only` list in the runbook (code blocks joined over `\` line continuations, and inline code) that contains `refresh_silver_gold` also contains `check_pipeline_idle`; at least one such list exists |
| AC-79 | Unit | `tests/test_peak_concurrency_docs.py::test_ac79_concurrency_section_and_troubleshooting_describe_the_pre_check` | The Concurrency section names `check_pipeline_idle`, `smart_meter_ingestion`, run id, update id, the rerun action and 08:00 UTC; the troubleshooting table has a row whose symptom names `check_pipeline_idle` |
| AC-79 | Unit | `tests/test_peak_concurrency_docs.py::test_ac79_adr_0012_accepted_records_d39_and_check_specs_is_clean` | ADR 0012 status `Accepted`, mentions D-39, and is listed in `docs/adr/README.md`; ADR 0008 has the dated note naming ADR 0012; `check_specs.run(ROOT).errors == []` |
| AC-80 | Unit | `tests/test_secrets_hygiene.py::test_ac80_pre_check_has_no_secret_parameter_and_tracked_files_no_token` | The Databricks token pattern finds nothing in tracked files (the new notebook, library and job file are among them); the pre-check task's parameter names and values contain no `secret`, `token`, `scope`, `password` or `{{secrets/`; the notebook has no `dbutils.secrets` |
| AC-80 | Unit | `tests/test_secrets_hygiene.py::test_ac65_tracked_files_contain_no_databricks_token` (unchanged) | Shipped scan, kept |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | `databricks bundle validate -t dev`, then `databricks bundle deploy -t dev` from a clean tree. Only the daily job changes; the ingestion job, pipeline and training job deploy unchanged. No catalog or table step. Retrain after the redeploy before the AC-54 test (runbook rule), not needed for this feature's tests |
| Scheduling and retries | Schedule unchanged (peak 08:00 UTC, ingestion 06:00 UTC). Pre-check: `max_retries: 0`, `disable_auto_optimization: true`, timeout 300 s, no polling (D-43). `refresh_silver_gold`: 1 retry after 600 s for `FAILED` updates (D-41), which does not rerun the pre-check. A refused run is retried by a manual rerun after the blocker ends or by the next daily run (NFR-21) |
| Monitoring and alerting | Failure email to the deploying user (existing) links to the run; the pre-check task error holds the full message, and the notebook output prints it too. The success exit value records the state that was read. Evidence of durations in `out/evidence/ac76_run_durations.json` |
| Secrets | None. The pre-check runs under the job's run-as identity through default notebook authentication; it takes no secret, scope or token parameter and prints ids and names only (NFR-20, AC-80). Integration tests use the local CLI profile |
| Cost | One serverless notebook task per daily run, about 30 s expected, at most 120 s measured (NFR-19); 4 read calls. Test cost on `dev`: one ingestion run (AC-74), one no-op pipeline update (AC-75), three full peak runs (AC-76, AC-74, AC-77) and spike 06 (one short run and one no-op update) |
| Backfill / reprocessing | Not affected. Backfill commands with `--only score_predictions` do not run the pipeline and need no pre-check; any `--only` list with `refresh_silver_gold` includes `check_pipeline_idle` (FR-40) |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| Race window between the check and the pipeline start (C-11) | An overlap that starts in those seconds still ends `INTERNAL_ERROR` without the clear message | Accepted (D-39); the runbook troubleshooting row says that an `INTERNAL_ERROR` after a passed pre-check is the race window; next daily run retries |
| Fail closed (D-45) | An API outage or permission change costs a day's predictions | The message names the failing read; the next daily run checks again; ADR 0012 revisit trigger |
| `active_only` may not include every non-terminal state (DA-21) | A queued or blocked ingestion run would be missed | Classification in code; fallback to page reading; at the job-run level these states are rare with `max_concurrent_runs: 1` |
| The name-uniqueness read (U-01) turns a same-named duplicate job into a daily failure | Lost day until the duplicate is renamed or deleted | The message lists the duplicate job ids; U-01 offers dropping the check |
| SDK or authentication drift in the serverless environment (DA-20) | The pre-check fails closed every day | Spike 06 before the build; environment version pinned; fallback `%pip` pin |
| AC-74 needs an ingestion run; with the Kafka service off, `ingest_kafka` fails and R's own pipeline task never runs | The last AC-74 clause is not exercised, and the failed run sends an email | U-02: power the Aiven service on for the evidence run; the evidence records whether the clause ran |
| AC-75 timing (DA-26) | The update may end before the pre-check reads it | Start the peak subset at once; the test fails loudly instead of passing vacuously |
| Changing shipped AC-62 tests (OD-18) | A careless edit could weaken a shipped guard | Assertions are extended, not removed; the change list is explicit and reviewed |
| Trade-off: bundle ids instead of names | Exact and target-scoped, but the notebook cannot be run by hand without passing ids | The runbook shows the deployed ids (`jobs.get`); widgets default to empty, which fails closed (G-13) |
| Trade-off: one extra task per run | About 30 s of serverless time daily | Small against the run's about 300 s |

---

## Open Items for the User

All four were decided by the user on 2026-10-22, each as recommended: U-01 keep the name check,
U-02 the Aiven service is on for the AC-74 run, U-03 accept ADR 0012 after spike 06 fills its probe
section, U-04 spike 06 approved.

| ID | Item | Recommendation (decided 2026-10-22: accepted) |
|---|---|---|
| U-01 | With ids from the bundle, AC-73's case "the ingestion job matches 2 jobs" cannot happen by id. The design keeps AC-73 literal: after `jobs.get(id)` it reads `jobs.list(name = deployed name)` and fails when more than one job has that name (G-14). Alternative: drop that read and `/iterate` AC-73 to "the id names a job with another base name" | Keep the literal check (default, no DEFINE change). It costs one read, honours D-45 as worded ("not unique"), and its failure message lists the duplicate ids |
| U-02 | AC-74 evidence run with the Aiven Kafka service on or off. Off: the pre-check leg is fully tested, but R fails at `ingest_kafka` (failure email), and its own `refresh_silver_gold` does not run, so the last clause of AC-74 is recorded as not exercised. On: R runs to its pipeline task and the clause is exercised | Power Aiven on for the AC-74 run |
| U-03 | ADR 0012 is `Proposed`. AC-79 needs an Accepted ADR recording D-39 | Review and accept ADR 0012 after spike 06 fills its probe section (manifest entry 14) |
| U-04 | Spike 06 starts one no-op pipeline update and one serverless notebook run on `dev` | Approve and run it before manifest entry 4 |

Follow-ups outside this feature (unchanged by this design): PEAK_MODEL F-03 (reset script idle
check, can call `pipeline_guard.check` with ids found by name), F-05 (`disable_auto_optimization`
on `ingest_kafka`, METER_INGESTION), and the METER_INGESTION reverse check (D-44), which can reuse
`pipeline_guard`.

---

## Self-Review

- **Weak points:**
  - The busy cases of the APIs are confirmed only by the live tests and spike 06; the queued,
    blocked and waiting-for-retry run states rest on documentation and unit tests (DA-21).
  - AC-75 depends on timing (DA-26). The test fails rather than passes vacuously, but a
    rerun may be needed.
  - The race window stays by design. No test covers it, and the `refresh_silver_gold` retry can
    still meet a refusal without the clear message.
  - The name-uniqueness read exists mainly to keep AC-73 literal (U-01). With ids it guards
    operator confusion rather than wrong targeting.
  - The pre-check sets the Spark session time zone only to keep the project-wide notebook rule
    and its test; it does not use Spark.
- **Risks:**
  - Fail-closed converts platform hiccups into lost days.
  - Serverless environment drift (SDK version, notebook authentication) would stop every daily
    run. It is caught on the first run, not in CI.
  - The edits to the shipped AC-62 tests must stay additive.
- **Trade-offs:**
  - A notebook task instead of a Python script task: one wiring pattern for the whole job, at the
    cost of a notebook for a few lines.
  - Updates from `latest_updates` instead of `list_updates`: one call for identity and state, with
    the time format to be probed.
  - The `PeakRunner` reuse is done now; the reset script reuse is deferred to F-03.
- **What I would do differently:** With more budget or time, I would remove the race window rather
  than narrow it. One way is to let a single orchestrating job own every pipeline start, with the
  ingestion job calling the peak tasks through `run_job_task`, so that job queueing serialises the
  pipeline. That needs a METER_INGESTION change (C-08, D-44). The other is to replace the peak
  job's pipeline task with a table-update trigger on Gold, once a spike shows that materialized
  view refreshes fire it on Free Edition.
- **Next improvement:** Run spike 06 (manifest entries 1 to 3) and record DA-20, DA-22, DA-23 and
  DA-26 in ADR 0012. Then `/build` from entry 4, with the deploy gate before the busy-case tests.

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-10-22 | Created from DEFINE_PEAK_MODEL_CONCURRENCY.md (Ready for Design): architecture, guards G-13 to G-20, OD-14 to OD-18 resolved, DA-19 to DA-26 with the spike 06 probe plan, job layout, 18-entry manifest (spike plus one PR), test strategy for AC-68 to AC-80, U-01 to U-04; ADR 0012 drafted (Proposed) and listed in the ADR index. Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts with spike 06 (entries 1 to 3), then entry 4 |

---

## Next Step

`/build .claude/sdd/features/DESIGN_PEAK_MODEL_CONCURRENCY.md`
| 2026-10-22 | U-01 to U-04 decided by the user, each as recommended | User answers | Spike 06 runs first (entries 1 to 3); AC-74 runs with the Aiven service on |
