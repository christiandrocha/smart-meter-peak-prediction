# DEFINE: Ingestion Guard

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | INGESTION_GUARD |
| **Date** | 2026-10-23 |
| **Author** | Christian |
| **Source** | `.claude/sdd/features/BRAINSTORM_INGESTION_GUARD.md` (Ready for Define, decisions D-46 to D-57, findings F-32 to F-45); spike 07 results (`docs/spikes/README.md`, run 843912359241341); `src/smart_meter_peak_prediction/pipeline_guard.py`; `notebooks/check_pipeline_idle.py`; `resources/smart_meter_ingestion.job.yml`; `tests/test_bundle_config.py`; `tests/test_peak_bundle.py`; `archive/PEAK_MODEL_CONCURRENCY/DEFINE_PEAK_MODEL_CONCURRENCY.md` |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: v0.4.0 (D-46). This feature closes METER_INGESTION follow-up F-02, PEAK_MODEL
follow-up F-05 and PEAK_MODEL_CONCURRENCY follow-up F-01 (the reverse check recorded under D-44).

**User decisions.** D-46 to D-57 (brainstorm, 2026-10-23) are final and are used here under their
original IDs. Two decisions are derived from them (D-58, D-59 under *Decisions and Open Items*); the
user confirmed both on 2026-10-23, together with the live regression run of AC-98.

**ID numbering.** IDs continue the project-wide series: FR-43, NFR-24, AC-81, C-13, OD-19 continue
after PEAK_MODEL_CONCURRENCY (FR-33 to FR-42, NFR-19 to NFR-23, AC-68 to AC-80, C-11, C-12, OD-14 to
OD-18). D-58, A-31 and Q-25 continue the decision, assumption and question series (last used: D-57,
A-30, Q-24). F-NN means a finding of `BRAINSTORM_INGESTION_GUARD.md` unless a feature is named.
G-NN refers to the guard rules of `DESIGN_PEAK_MODEL_CONCURRENCY.md` (archived), in particular G-21
(overall pipeline state: `IDLE` and `FAILED` pass, `DELETED` is unusable, any other or missing value
is busy).

---

## Problem Statement

The shipped ingestion job `smart_meter_ingestion` (v0.1.0) has two faults. First, serverless
auto-optimization retries `ingest_kafka` although it is configured with `max_retries: 0`: a failed
run shows two attempts (F-33, reproduced by spike 07: 2 attempts with `max_retries: 0` alone, 1 with
`disable_auto_optimization: true`). A broker outage then costs twice the quota and reaches the job
failure up to twice as late, against the documented no-retry policy (METER_INGESTION AC-10).
Second, its pipeline task `refresh_silver_gold` (no retry) requests an update of the shared pipeline
`smart_meter_silver_gold` without looking first. When another update is in progress (a
`smart_meter_peak_model` run, a manual run, the UI or the API), the platform refuses the request in
about 2 s, the task ends `INTERNAL_ERROR` with "Pipeline update already in progress.", and the
on-failure email does not say which update blocked it or what to do (A-19 of PEAK_MODEL_CONCURRENCY;
the peak job guards only its own direction, ADR 0012).

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Platform operator (job owner, receives the ingestion on-failure email) | Know from the message alone which update blocked the refresh, that Bronze was kept, and what to do | Failed task run of `smart_meter_ingestion`: its error output and the on-failure email |
| Scheduled run of `smart_meter_ingestion` (06:00 UTC) | Never request a pipeline update that the platform will refuse when the conflict is visible beforehand; a broker outage fails once, not twice | Task graph and task settings of the ingestion job |
| `smart_meter_peak_model` (shipped v0.3.0) | Unchanged behaviour: its pre-check, messages and tests stay as shipped; no mutual refusal with the ingestion job | Unchanged job; shipped live tests AC-74 to AC-77 |
| Integration tests and runbooks | One documented rule for when a run that includes the pipeline task may start, for both jobs | `docs/runbooks/meter_ingestion.md`, `docs/runbooks/peak_model.md`, `tests/integration/` |
| Reviewer | Trace the change to decisions, to the superseded pins and to tests | ADR 0013, this DEFINE, tests named after AC-81 to AC-99 |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| No silent retry of `ingest_kafka` (D-47 a) | Task runs of `ingest_kafka` in a failed ingestion run on dev | Exactly 1 (AC-95) |
| No refused ingestion refresh when the conflict is visible (D-47 b) | Ingestion runs whose `refresh_silver_gold` ends with "Pipeline update already in progress." while an update was active at check time | 0 (AC-87, AC-88, AC-97) |
| Diagnosis from the message alone | Refusals by the check whose message lacks the update id, its state, its UTC creation time, the caller job and the action | 0 (AC-87, AC-97) |
| Small cost | Duration of the check task run on dev | <= 120 s (AC-96, AC-97) |
| No unintended change | Byte differences of the peak daily job, `notebooks/check_pipeline_idle.py`, the training job, the pipeline YAML and `databricks.yml` against their pinned tags; structural differences of the ingestion job YAML against `v0.1.0` beyond the listed changes; modified or failing tests among the 28 shipped `pipeline_guard` tests | 0 (AC-84, AC-85, AC-92) |

---

## Scope

**In scope:**
- `disable_auto_optimization: true` on `ingest_kafka`, keeping `max_retries: 0` and its timeout
  (D-51).
- A new read-only reverse pre-check task in `smart_meter_ingestion`, directly before
  `refresh_silver_gold` and after `ingest_files` and `ingest_kafka` (D-50), reading only the pipeline
  (D-48), on serverless environment version 2 (D-55), with `max_retries: 0` and
  `disable_auto_optimization: true` (D-51).
- An additive, backward-compatible generalisation of `pipeline_guard`: a mode without a watched job,
  with the calling job's name and schedule as message inputs (D-54, F-35).
- The explicit supersession of the ingestion-file clause of AC-62 and AC-78 and the new pins (D-53).
- Updates of the shipped tests that encode the v0.1.0 ingestion graph (F-41, F-42), and the extension
  of the AC-10 live test with an attempt count (D-47).
- Runbook updates for the ingestion job and a cross-reference in the peak runbook (D-59).
- ADR 0013 and dated notes on ADR 0012 and ADR 0008, written at `/design` (D-56).

**Out of scope:**
- `disable_auto_optimization` or any other change on `refresh_silver_gold` of either job: spike 07
  showed that the field does not stick on a pipeline task (A-25 invalidated, D-51). Next release, only
  with another mechanism.
- Any change to `smart_meter_peak_model`, `notebooks/check_pipeline_idle.py`, the current peak-mode
  behaviour and messages of `pipeline_guard`, the training job, the pipeline or `databricks.yml`
  (D-53, D-54).
- Naming the peak run, blocking on peak runs or on the training job (Approach B and C; D-48, D-49).
  A bundle reference to the peak job is not possible (A-30). Approach C is the upgrade path if A-28
  is observed.
- The reset script's active-run check and its `main()` test (D-52). Next release (v0.5.0).
- A lock or queue that closes the race window (C-11); waiting, polling or retrying in the check
  (D-43 applies here too).
- `ingest_files` and `setup_catalog` settings; schedules (06:00 and 08:00 UTC stay).

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-43 | The system shall stop the platform retry of `ingest_kafka`: the task keeps `max_retries: 0` and `timeout_seconds: 840` and sets `disable_auto_optimization: true`, so a failed `ingest_kafka` task has exactly one attempt per job run. `setup_catalog`, `ingest_files` and `refresh_silver_gold` keep their v0.1.0 retry and timeout settings and do not set `disable_auto_optimization` (D-51). | Must |
| FR-44 | The system shall run a reverse pre-check task in `smart_meter_ingestion` that depends on exactly `ingest_files` and `ingest_kafka`, and `refresh_silver_gold` shall depend on exactly that check task (D-50, D-58). `refresh_silver_gold` starts only when the check succeeds; when an ingest task fails, the check does not run and `refresh_silver_gold` does not start (unchanged outcome for the pipeline task). | Must |
| FR-45 | The check task shall be a notebook task (no `pipeline_task`) with `max_retries: 0`, `disable_auto_optimization: true` and `timeout_seconds: 300`. It shall run on a job environment with serverless environment version 2; every other task of the ingestion job shall keep the default environment (D-55). It shall receive the pipeline id as the bundle resource reference `resources.pipelines.smart_meter_silver_gold.id` of the same target and no job id (D-48, A-30). | Must |
| FR-46 | The check shall read only the pipeline `smart_meter_silver_gold`: its name, its overall state and its `latest_updates`, in one read. It shall pass only when the overall state is `IDLE` or `FAILED` and no entry of `latest_updates` is in a non-terminal state (terminal: `COMPLETED`, `FAILED`, `CANCELED`). Any other overall state, a missing or unknown overall state, or a non-terminal, missing or unknown update state counts as busy (G-21). It shall not read job runs, the peak job or the training job (D-48). | Must |
| FR-47 | When the pipeline is busy, the check task shall end with result state `FAILED` and an error message that names: the check task; the pipeline `smart_meter_silver_gold` and its id; each active update with its update id, state and creation time (UTC, ISO 8601 with `Z`, or "not reported"); the overall pipeline state, also when no active update is listed; the time of the check; the calling job `smart_meter_ingestion` and its schedule (06:00 UTC). It shall state that `refresh_silver_gold` did not start and the Bronze data of the run is kept, and the action: wait until the named update ends, then rerun `smart_meter_ingestion`; without action, the `smart_meter_peak_model` run at 08:00 UTC refreshes the pipeline from Bronze and the next ingestion run (06:00 UTC) checks again (D-49, F-43). | Must |
| FR-48 | When the check cannot establish the pipeline state (pipeline id missing or an unresolved reference, the client cannot be built, the read fails, permission is denied, the id names another pipeline, or the overall state is `DELETED`), it shall fail, never pass, with a message that names the pipeline, what could not be read and a redacted error of at most one line and 200 characters, and the action: fix the cause, then rerun `smart_meter_ingestion` (fail closed, D-45, D-48). | Must |
| FR-49 | The check shall only read: it shall not start, stop, cancel or change any job, job run, pipeline, pipeline update or table, and it shall not wait, poll or sleep. On success it shall end the task with a JSON exit value that states the outcome `idle`, the check time and the pipeline id, name, state and latest update. | Must |
| FR-50 | The generalisation of `pipeline_guard` shall be additive and backward-compatible: the peak-mode functions, their parameters and defaults, messages and exit value are unchanged; the 28 test functions of `tests/test_pipeline_guard.py` at tag `v0.3.0` stay unmodified and pass; `notebooks/check_pipeline_idle.py` and `resources/smart_meter_peak_model.job.yml` stay identical to `v0.3.0` (D-54). | Must |
| FR-51 | The repository shall pin the shipped definitions: the new `resources/smart_meter_ingestion.job.yml` by its SHA-256 at the feature commit, superseding the ingestion-file clause of PEAK_MODEL AC-62 and PEAK_MODEL_CONCURRENCY AC-78; `resources/smart_meter_silver_gold.pipeline.yml` and `databricks.yml` to `v0.1.0`; `resources/smart_meter_peak_model_training.job.yml` to `v0.2.0`; `resources/smart_meter_peak_model.job.yml` and `notebooks/check_pipeline_idle.py` to `v0.3.0` (D-53, D-54). The ingestion job YAML shall differ from `v0.1.0` only by the changes of FR-43 to FR-45 and comments. The archived documents are not edited. | Must |
| FR-52 | Shipped tests that encode the v0.1.0 ingestion graph (F-41, F-42) shall be updated to the new graph, keeping the intent of the guarded criterion: for AC-10, `ingest_kafka` stays an ancestor of `refresh_silver_gold`, with `max_retries: 0` and a timeout of at most 900 s. The AC-10 live test shall additionally assert the attempt count of FR-43 (D-47). | Must |
| FR-53 | `docs/runbooks/meter_ingestion.md` shall describe the check task, its busy and fail-closed messages and the action, and every runbook command that runs `refresh_silver_gold` of the ingestion job with a task subset (`--only`) shall include the check task. `docs/runbooks/peak_model.md` (Concurrency) shall state that the ingestion job checks the pipeline before its own refresh. ADR 0013 (Accepted) shall record the reverse pre-check, and ADR 0012 and ADR 0008 shall carry a dated note referring to it (D-56, D-59). | Should |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-24 | Cost and platform limits | The check adds 1 serverless task per ingestion run, with a task run duration of at most 120 s on dev (about 18 to 32 s expected, F-45). The widest level of the ingestion task graph stays at 2 tasks, so an overlapping peak run gives at most 2 + 2 concurrent tasks, below the Free Edition limit of 5. A full ingestion run stays within 3600 s (METER_INGESTION AC-30). |
| NFR-25 | Security | 0 credentials or tokens in tracked files, bundle YAML, the new notebook or the check message. The check runs under the job's workspace identity with read access only, takes no secret parameter, and redacts bearer tokens, `dapi` tokens and URLs from any error text it prints. |
| NFR-26 | Idempotency | The check has no side effects: with the same platform state, two executions give the same outcome and the same message and exit value except for the check time. A run refused by the check leaves nothing to clean up: Bronze rows written by its ingest tasks stay valid input for the next update, and rerunning the job (or the check task with `refresh_silver_gold`) is enough. |
| NFR-27 | Time handling | Every timestamp in the check message and exit value is UTC, `YYYY-MM-DDTHH:MM:SSZ`; a time without a zone is printed as "not reported", never as local time. The new notebook sets and asserts the Spark session time zone `UTC`. |
| NFR-28 | Fail-fast | The check decides from one read of the current state, never waits, and runs exactly once per job run (0 retries, auto-optimization off); a refusal ends the check task within 120 s. |
| NFR-29 | Compatibility | The check runs on serverless environment version 2 with `databricks-sdk` 0.40.0 (spike 06, A-26): the client is built through `Config` with the existing `CLIENT_LIMITS`. `pipeline_guard` stays importable without the Databricks SDK, so CI needs no SDK. |

---

## Data Contracts

This feature writes no table and changes no existing contract. It reads platform metadata and
produces one task outcome per ingestion run. Contracts are inline because no other feature shares
them; the field shapes are those recorded by spike 06 (ADR 0012, Platform probe).

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| Pipeline `smart_meter_silver_gold` state (Pipelines API `pipelines.get`, read only) | METER_INGESTION (platform metadata) | One pipeline | `pipeline_id` | Read live at check time | Inline: fields used are `name`, overall `state`, `latest_updates` |
| Entries of `latest_updates` (inside the same read) | METER_INGESTION (platform metadata) | One pipeline update, newest first | `update_id` | Read live at check time | Inline: fields used are `update_id`, `state`, `creation_time` (ISO 8601 with `Z`) |
| Check outcome (task run result, error output, exit value) | INGESTION_GUARD | One check task run per ingestion job run | job `run_id`, task `run_id` | At task end | Inline: result `SUCCESS` with the FR-49 exit value, or `FAILED` with the FR-47 or FR-48 message |
| Bronze, Silver, Gold tables of METER_INGESTION; PEAK_MODEL tables | METER_INGESTION, PEAK_MODEL | Unchanged | Unchanged | Unchanged; a refused ingestion refresh is caught up by the next pipeline update (08:00 UTC peak run or the next ingestion run) | `docs/contracts/` (no change) |

---

## Acceptance Criteria

**Unit** criteria run in CI against the parsed YAML, the repository, or a fake workspace client that
records every call and raises on any method outside the read list. **Live** criteria run on the
deployed `dev` target with the integration marker; their evidence goes into the build report.

| ID | Level | Given | When | Then |
|---|---|---|---|---|
| AC-81 | Unit | The bundle resource files at the feature commit | The ingestion job definition is read | The job has exactly 5 tasks, in YAML order `setup_catalog`, `ingest_files`, `ingest_kafka`, the check task, `refresh_silver_gold`. `ingest_files` and `ingest_kafka` depend on exactly `setup_catalog`; the check task depends on exactly `ingest_files` and `ingest_kafka`; `refresh_silver_gold` depends on exactly the check task; `ingest_kafka` is an ancestor of `refresh_silver_gold`. No task sets `run_if`. The check task has a `notebook_task` and no `pipeline_task`. The widest level of the graph has 2 tasks. Schedule `0 0 6 * * ?` UTC, `max_concurrent_runs: 1`, job `timeout_seconds: 3600` and the on-failure email are unchanged. The check task's parameters are exactly `src_path` and the pipeline id as the reference `resources.pipelines.smart_meter_silver_gold.id`, plus any message inputs of OD-21; the file contains no reference to a job resource |
| AC-82 | Unit | The bundle resource files at the feature commit | The task settings are read | `ingest_kafka`: `max_retries: 0`, `disable_auto_optimization: true`, `timeout_seconds: 840`. Check task: `max_retries: 0`, `disable_auto_optimization: true`, `timeout_seconds: 300`. `setup_catalog` (600 s, 1 retry), `ingest_files` (1800 s, 1 retry) and `refresh_silver_gold` (2700 s, 0 retries, `full_refresh: false`, same pipeline reference) are as in `v0.1.0` and do not set `disable_auto_optimization`. Every task timeout is below the job timeout |
| AC-83 | Unit | The bundle resource files at the feature commit | The environments and task environments are read | The ingestion job declares exactly one environment, whose spec is `environment_version: "2"` with no extra dependencies. The check task references it; `setup_catalog`, `ingest_files` and `ingest_kafka` have no `environment_key`. Neither the job nor any task has a cluster key (`job_clusters`, `job_cluster_key`, `new_cluster`, `existing_cluster_id`) |
| AC-84 | Unit | The repository at the feature commit, and tags `v0.1.0`, `v0.2.0`, `v0.3.0` when present | The pinned files are hashed and, with the tags present, compared with `git show` | This criterion supersedes the clause of PEAK_MODEL AC-62 and PEAK_MODEL_CONCURRENCY AC-78 that `resources/smart_meter_ingestion.job.yml` is identical to `v0.1.0`; all their other clauses stay in force. The ingestion job YAML equals the SHA-256 pinned at the feature commit (and, once tag `v0.4.0` exists, its content at `v0.4.0`). `resources/smart_meter_silver_gold.pipeline.yml` and `databricks.yml` equal `v0.1.0`. `resources/smart_meter_peak_model_training.job.yml` equals `v0.2.0`. `resources/smart_meter_peak_model.job.yml` and `notebooks/check_pipeline_idle.py` equal `v0.3.0`. The bundle still defines exactly one pipeline |
| AC-85 | Unit | The ingestion job YAML at the feature commit and at `v0.1.0` (pinned digest, and `git show` when the tag is present) | Both are parsed; from the new one the check task and the `environments` block are removed, `disable_auto_optimization` is removed from `ingest_kafka`, and the `depends_on` of `refresh_silver_gold` is restored to `ingest_files` and `ingest_kafka` | The result equals the parsed `v0.1.0` job exactly (no other key, value or task differs) |
| AC-86 | Unit | A fake client: pipeline `smart_meter_silver_gold` with overall state `IDLE`, then `FAILED`; `latest_updates` absent, empty, or with every entry terminal (`COMPLETED`, `FAILED`, `CANCELED`) | The check runs twice for each state with the same fake | Each execution passes. The exit value is JSON-serialisable, has outcome `idle`, a check time ending in `Z`, and the given pipeline id, name, state and latest update. The two executions give equal outcomes and equal exit values except for the check time. The fake records exactly 1 call per execution, `pipelines.get`, and 0 `jobs.*` calls |
| AC-87 | Unit | A fake client: overall state `RUNNING`; the latest update U is in state S, created at a known time | The check runs for each non-terminal `UpdateInfoState` member of the SDK enum, and for a missing and an unknown state | It fails with the guard error. The message contains the check task key, `smart_meter_silver_gold`, the pipeline id, U, S (or `UNKNOWN`), the creation time as `YYYY-MM-DDTHH:MM:SSZ`, the overall state, `smart_meter_ingestion`, `06:00 UTC`, the action "rerun smart_meter_ingestion", `smart_meter_peak_model` with `08:00 UTC` as the next refresh, and that `refresh_silver_gold` did not start and Bronze is kept. It contains neither `check_pipeline_idle` nor "rerun smart_meter_peak_model". The fake records only `pipelines.get` |
| AC-88 | Unit | A fake client: no active entry in `latest_updates` | The check runs for each overall state `DEPLOYING`, `STARTING`, `RUNNING`, `STOPPING`, `RECOVERING`, `RESETTING`, a missing state and an unknown string | It fails as busy (G-21). The message names the pipeline, the overall state (or "not reported") and that no active update is listed, plus the caller and action of AC-87 |
| AC-89 | Unit | A fake client in each of these states: pipeline id empty; pipeline id an unresolved bundle reference; client factory raises; `pipelines.get` raises a generic error, a `PERMISSION_DENIED` error and a `RESOURCE_DOES_NOT_EXIST` error; the id names another pipeline; overall state `DELETED` | The check runs | It fails in every case and never reports success. The message names `smart_meter_silver_gold`, what could not be read, and the action "fix the cause, then rerun smart_meter_ingestion". It names no job id. The fake records at most 1 call, `pipelines.get`, and 0 `jobs.*` calls |
| AC-90 | Unit | A fake `pipelines.get` that raises an error whose first line contains a bearer token, a `dapi` token and an `https://` URL, followed by a second line, and an error with a first line of 500 characters | The check runs | The message contains `<redacted>` and none of the three secret-like strings and no text of the second line; the error text after the error class is at most 200 characters |
| AC-91 | Unit | A fake update whose creation time is given as ISO 8601 with `+02:00`, with `Z`, as epoch milliseconds, as an aware datetime, and as a naive datetime; a check time `now` in a non-UTC zone | The check runs | Every timestamp in the message and exit value matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` and equals the UTC instant of the input; the naive value is printed as "creation time not reported" |
| AC-92 | Unit | The repository at the feature commit and `tests/test_pipeline_guard.py` at tag `v0.3.0` (its 28 test functions) | The test sources are compared and `pytest tests/test_pipeline_guard.py` runs | Each of the 28 v0.3.0 test functions exists with identical source and passes. The peak-mode entry points accept the v0.3.0 arguments (client, ingestion job id, pipeline id, optional `now`) and, for the same fake state, return the same message and exit value as at `v0.3.0` |
| AC-93 | Unit | The repository at the feature commit | The secrets scan of tracked files runs, and the ingestion job definition and the new notebook are read | The scan finds 0 Databricks tokens. Only `ingest_kafka` receives `secret_scope`; the check task has no parameter naming a secret scope or a token. The new notebook has no `try` (I-14), no `dbutils.secrets`, sets and asserts the session time zone `UTC`, builds the client with `Config` and `CLIENT_LIMITS`, and calls `dbutils.notebook.exit`. `pipeline_guard` imports no Databricks SDK module and calls no `sleep` |
| AC-94 | Live | `databricks bundle validate -t dev` and `databricks bundle deploy -t dev` from a clean tree, both with exit code 0 (no Terraform cycle) | The deployed ingestion job is read back through the Jobs API | Its task set equals the 5 YAML task keys, and each task's dependencies, timeout, retries and `disable_auto_optimization` equal the YAML. `ingest_kafka` and the check task read back `disable_auto_optimization` true and `max_retries` 0 (not unset). The check task's pipeline id parameter equals the deployed pipeline id, and its environment has `environment_version` "2" |
| AC-95 | Live | The `dev` target deployed; the Kafka service powered off; the AC-10 snapshot taken (shipped `test_ac10_before_outage_snapshot`) | The ingestion job runs | METER_INGESTION AC-10 holds as shipped (task failed within 900 s, Bronze count and checkpoint unchanged). In addition, the run lists exactly 1 task run of `ingest_kafka`, with attempt number 0 and result `FAILED` or `TIMEDOUT`; the check task and `refresh_silver_gold` end `UPSTREAM_FAILED` (never started) |
| AC-96 | Live | The `dev` target deployed; the Kafka service on; no active run of `smart_meter_peak_model`; the pipeline idle | A full run of `smart_meter_ingestion` starts | Every task ends `SUCCESS` with exactly 1 task run and attempt number 0. The check task run lasts at most 120 s; its exit value has outcome `idle`, the deployed pipeline id and a check time ending in `Z`. `refresh_silver_gold` starts one update, which ends `COMPLETED`. The run lasts at most 3600 s. Task durations are recorded in the build report |
| AC-97 | Live | The `dev` target deployed; no active run of either job; an update U of `smart_meter_silver_gold` started through the Pipelines API and not terminal | A run of `smart_meter_ingestion` that includes the check task and `refresh_silver_gold` starts (full run or task subset), and after U has ended the same run is started again with no other step | First run: exactly 1 task run of the check, attempt number 0, `FAILED` within 120 s; its error output contains U, `smart_meter_silver_gold`, "rerun smart_meter_ingestion" and a timestamp ending in `Z`; `refresh_silver_gold` ends `UPSTREAM_FAILED`; the pipeline lists no update other than U created between the start and the end of the run. Second run: ends `SUCCESS`, with the check passing |
| AC-98 | Live | The `dev` target deployed with v0.4.0 | The shipped tests `tests/integration/test_peak_concurrency.py` (AC-74 to AC-77) and `tests/integration/test_peak_deployment.py` (AC-62) run unmodified | They pass. In the AC-74 scenario (peak run refused while an ingestion run R is active, Kafka service on), the check task of R ends `SUCCESS` and the `refresh_silver_gold` of R ends `SUCCESS`: no mutual refusal |
| AC-99 | Unit | The repository at the feature commit | `pytest` (without the integration marker), `scripts/check_specs.py`, and a read of `docs/runbooks/` and `docs/adr/` run | `pytest` reports 0 failures; no test asserts the v0.1.0 four-task ingestion graph. `check_specs.py` reports 0 errors. `docs/runbooks/meter_ingestion.md` names the check task, its busy and fail-closed messages and the action, and every `--only` command that lists `refresh_silver_gold` of the ingestion job also lists the check task. `docs/runbooks/peak_model.md` (Concurrency) mentions the ingestion job's check. ADR 0013 has status Accepted and records D-48, D-50, D-51, D-55 and the A-30 cycle evidence; ADR 0012 and ADR 0008 carry a dated note referring to ADR 0013 |

### Traceability (FR and NFR to AC)

| Requirement | Covered by |
|---|---|
| FR-43 | AC-82, AC-94, AC-95 |
| FR-44 | AC-81, AC-95, AC-96, AC-97 |
| FR-45 | AC-81, AC-82, AC-83, AC-94 |
| FR-46 | AC-86, AC-87, AC-88, AC-96, AC-97 |
| FR-47 | AC-87, AC-88, AC-97 |
| FR-48 | AC-89, AC-90 |
| FR-49 | AC-86, AC-89, AC-93, AC-96 |
| FR-50 | AC-84, AC-92, AC-98 |
| FR-51 | AC-84, AC-85 |
| FR-52 | AC-81, AC-95, AC-99 |
| FR-53 | AC-99 |
| NFR-24 | AC-81, AC-96, AC-97 |
| NFR-25 | AC-90, AC-93 |
| NFR-26 | AC-86, AC-97 |
| NFR-27 | AC-91, AC-93, AC-96 |
| NFR-28 | AC-82, AC-86, AC-95, AC-97 |
| NFR-29 | AC-83, AC-92, AC-93, AC-94, AC-96 |

Coverage of the required kinds: correctness AC-81 to AC-83, AC-86 to AC-88, AC-96; idempotency and
reprocessing AC-86 (same state twice), AC-97 (rerun after refusal); data quality of the inputs
(unreadable, foreign or deleted pipeline, malformed times) AC-89, AC-91; failure paths AC-87 to AC-90,
AC-95, AC-97; regression of shipped behaviour AC-84, AC-85, AC-92, AC-98.

---

## Decisions and Open Items

### Decided by the user

D-46 to D-57 (brainstorm, 2026-10-23) apply unchanged. Where they are used:

| ID | Where it is used |
|---|---|
| D-46 (feature and release v0.4.0) | Metadata |
| D-47 (goals: 1 attempt; 0 visible-conflict refusals) | Goals, FR-43, FR-52, AC-95, AC-97 |
| D-48 (Approach A: pipeline only; no peak job id, no training job) | FR-45, FR-46, FR-48, AC-81, AC-86 to AC-89 |
| D-49 (message names the update) | FR-47, AC-87, AC-97 |
| D-50 (check directly before `refresh_silver_gold`, after both ingest tasks) | FR-44, AC-81 |
| D-51 (`disable_auto_optimization` on `ingest_kafka` and the check only) | FR-43, FR-45, AC-82, AC-94 |
| D-52 (reset script out of scope) | Scope |
| D-53 (supersession of the AC-62 and AC-78 ingestion clause; pins) | FR-51, AC-84, AC-85 |
| D-54 (peak side unchanged; additive generalisation) | FR-50, AC-84, AC-92, AC-98 |
| D-55 (environment version 2 for the check only) | FR-45, AC-83, AC-94 |
| D-56 (ADR 0013, notes on ADR 0012 and ADR 0008) | FR-53, AC-99 |
| D-57 (spike 07 before `/design`) | Constraints & Assumptions (A-25 to A-30) |

### Derived in this phase (confirmed by the user, 2026-10-23)

| ID | Statement | Derived from | Where it is used |
|---|---|---|---|
| D-58 | `refresh_silver_gold` depends on exactly the check task, and the check depends on exactly `ingest_files` and `ingest_kafka`, with the default run condition (no `run_if`). `ingest_kafka` thus stays an ancestor of `refresh_silver_gold`, which is the intent of the shipped AC-10 dependency assertion | D-50 and the architecture confirmed with Approach A (brainstorm, *Selected Approach*) | FR-44, FR-52, AC-81 |
| D-59 | The ingestion runbook documents the check and the `--only` rule (a subset with `refresh_silver_gold` must include the check), mirroring PEAK_MODEL_CONCURRENCY FR-40 and FR-41 | The bypass behaviour of `--only` (PEAK_MODEL_CONCURRENCY A-24) applies to any job | FR-53, AC-99 |

### Open questions for the user

None. Q-25 is not used.

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-19 | Task key of the check task, name of its notebook (a new notebook, since `check_pipeline_idle.py` is pinned) and the environment key of the ingestion job |
| OD-20 | Shape of the additive `pipeline_guard` API: an optional watched job in the existing functions versus new pipeline-only entry points; how the report and the exit value represent "no watched job" without changing the peak-mode output (AC-92) |
| OD-21 | How the caller's job name, schedule and next-refresh text reach the message: task parameters (widgets) or constants in the new notebook; whether the task subset rerun (check plus `refresh_silver_gold`) is suggested in the message |
| OD-22 | The manifest of shipped tests that change by design (F-41, F-42): `tests/test_bundle_config.py` (AC-10 dependency, AC-28 graph, timeouts and retries, the widget test), `tests/test_peak_bundle.py` (`PINNED_SHA256` split, AC-62 and AC-78 pin tests), `tests/integration/test_deployment.py` (`JOB_TASKS`, the "all four tasks" wording of `full_runs`), `tests/integration/test_bronze_ingestion.py` (AC-10 attempt count) and `tests/integration/conftest.py` |
| OD-23 | Live test mechanics and order: AC-97 as a full run or a task subset; whether AC-96 shares its run with the AC-30 evidence; ordering against AC-95 (Kafka off) and AC-98 (Kafka on); the fallback if the no-op update ends before the check reads it (A-31) |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 to C-07 | Constraint | Inherited from METER_INGESTION: Free Edition serverless only; at most 5 concurrent job tasks, one active pipeline per type, daily quota; no secrets in code; UTC end to end | Yes |
| C-08 | Constraint | METER_INGESTION job and pipeline not modified. For the job, superseded by C-13 within the changes of FR-43 to FR-45; for the pipeline, still in force | Partly superseded (user, D-53) |
| C-11 | Constraint | No lock across two jobs on one pipeline; a window between a check and the pipeline start remains, in both directions | Accepted (D-39, D-48) |
| C-12 | Constraint | `smart_meter_peak_model_training` identical to `v0.2.0` | Yes |
| C-13 | Constraint | Pins of this feature: pipeline YAML and `databricks.yml` at `v0.1.0`; training job at `v0.2.0`; peak daily job and `notebooks/check_pipeline_idle.py` at `v0.3.0`; the ingestion job YAML changes only as AC-85 allows; archived SDD documents are not edited | Yes (user, D-53, D-54) |
| A-25 | Assumption | `disable_auto_optimization` on a `pipeline_task` is accepted and has an effect | Invalidated by spike 07 (2026-10-23): deploy accepts it, the deployed pipeline task shows it unset. `refresh_silver_gold` out of scope |
| A-26 | Assumption | A job with one notebook task on environment version 2 and others on the default environment deploys and runs | Validated by spike 07 (run 843912359241341; `databricks-sdk` 0.40.0, Python 3.11.10). Checked again on the real job by AC-94, AC-96 |
| A-27 | Assumption | With `disable_auto_optimization: true`, a failed notebook task with `max_retries: 0` has exactly 1 attempt; retries appear as additional task runs with attempt number 1 or higher | Validated by spike 07 (1 attempt with the setting, 2 without). On `ingest_kafka` itself: AC-95 |
| A-28 | Assumption | A Gold refresh by the ingestion job during a peak run's later tasks can fail the scoring (F-40). Not changed by this feature | Accepted, watch |
| A-29 | Assumption | The ingestion job's run-as identity can read the pipeline state with no extra grant | Validated by spike 07. Checked on the real job by AC-96 |
| A-30 | Assumption | A bundle reference from the ingestion job to the peak job forms a cycle | Validated by spike 07: `bundle deploy` fails with `Error: Cycle: databricks_job...`. Hence no job reference in the ingestion job (AC-81) |
| A-31 | Assumption | A no-op update started through the Pipelines API stays non-terminal long enough (about 125 s on dev, spike 06) for the check of an ingestion run started right after it to see it | Pending; AC-97 validates. Same risk as DA-26 on the peak side; fallback per OD-23 |
| A-32 | Assumption | Environment version 2 still ships `databricks-sdk` 0.40.0 when the feature is built, so the `Config`-based client works (SDK drift, PEAK_MODEL_CONCURRENCY F-04) | Validated 2026-10-23 (spike 07); checked again by AC-96 |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Both faults observed with evidence: the double attempt reproduced by spike 07 (F-33), the refusal rule validated on dev (A-19); costs named (quota, late failure, unexplained refusal) |
| Users | 3 | Operator, scheduled ingestion run, the unchanged peak job, runbooks and tests, and reviewer, each with the place they read the outcome |
| Scope | 3 | Bounded by D-48 to D-55 and the pins of C-13; pipeline-task setting, peak naming, reset script and locks excluded with the release that may pick them up |
| Acceptance criteria | 3 | 19 criteria, each marked unit or live, covering every FR and NFR, with correctness, idempotency, input quality, failure paths and regression of shipped behaviour |
| Constraints | 2 | Spike 07 validated the platform surface (A-26, A-27, A-29, A-30) and invalidated A-25; the busy-case timing on the ingestion side (A-31) is pending until AC-97 |
| **Total** | **14/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The race window remains by design (C-11): an update started between the check and
    `refresh_silver_gold` still ends `INTERNAL_ERROR` with the old message. No criterion can force
    that timing.
  - The message names the update, not the peak run (D-49); the operator finds the peak run from the
    update's creation time.
  - AC-97 depends on a no-op update outliving the start of a run (A-31); a fast update makes the
    test pass vacuously unless the build checks that U was active when the check read it.
  - AC-85 and AC-92 compare against git tags; in a clone without tags they fall back to pinned
    digests, which prove equality only to the pinned bytes.
- **Risks:**
  - Fail-closed now also applies to the ingestion refresh: an API outage or an SDK change on
    environment version 2 costs the Silver/Gold refresh of both jobs every day until fixed. Bronze is
    kept, so no data is lost.
  - A refused ingestion refresh delays Silver and Gold until the next update. In production the
    08:00 UTC peak run catches up, so METER_INGESTION NFR-08 (fresh within 24 h) still holds; in dev
    both schedules are paused, so a refused manual run needs a manual rerun.
  - Changing pinned shipped files and shipped tests can weaken a shipped guard; AC-85 limits the YAML
    change structurally, and AC-92 and AC-98 run the shipped peak tests unmodified.
  - Live evidence costs quota: AC-95 needs the Kafka service off, AC-96 and AC-98 need it on, and each
    serverless run takes about 9 minutes.
- **Trade-offs:**
  - A pipeline-only check avoids the bundle cycle (A-30) and the mutual refusal of Approach B, at the
    price of not naming the peak run and not covering the post-refresh Gold change (A-28).
  - Placing the check after the ingest tasks keeps Bronze ingestion when the pipeline is busy, but
    with the Kafka service off the check never runs (AC-95 asserts this as intended).
  - Explicit pins (FR-51) make every future change of these files a deliberate act, at the cost of
    one more pin to move per feature.
- **What I would do differently:** Write the extended AC-10 assertion so that it reads the attempt
  count from a single `get_run` with tasks expanded, as spike 07 did, instead of scanning the run
  list, so the count cannot be split across list pages.
- **Next improvement:** In `/design`, settle OD-20 first (the additive API shape decides whether
  AC-92 can hold without touching the peak-mode code paths), then OD-22 (the manifest of shipped tests
  that change), and plan AC-94 as the first live step of the build.

---

## Next Step

`/design .claude/sdd/features/DEFINE_INGESTION_GUARD.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-23 | Created: FR-43 to FR-53, NFR-24 to NFR-29, AC-81 to AC-99, C-13, A-31, A-32, D-58, D-59 (derived), OD-19 to OD-23; A-25 to A-30 carried from the brainstorm with spike 07 results. Status `Ready for Design` | Phase 1 of the SDD workflow, from `BRAINSTORM_INGESTION_GUARD.md` | `/design` can start; OD-19 to OD-23 open |
| 2026-10-23 | D-58, D-59 and the AC-98 live regression run confirmed by the user | Review of the derived items | None |
