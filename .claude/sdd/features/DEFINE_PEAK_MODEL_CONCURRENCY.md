# DEFINE: Peak Model Concurrency

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL_CONCURRENCY |
| **Date** | 2026-10-22 |
| **Author** | Christian |
| **Source** | No brainstorm (the problem is known). `.claude/sdd/archive/PEAK_MODEL/SHIPPED_2026-10-22.md` follow-up F-14 (supersedes F-07) and lessons row "Platform (pipeline concurrency)"; `DESIGN_PEAK_MODEL.md` DA-13, OD-07, risk row and change log 2026-10-22; `BUILD_REPORT_PEAK_MODEL.md` gate log DA-13 entry; ADR 0008; `resources/smart_meter_peak_model.job.yml`, `resources/smart_meter_ingestion.job.yml`; `docs/runbooks/peak_model.md` (Concurrency); `tests/integration/conftest.py` (`PeakRunner.assert_ingestion_idle`) |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: the release after v0.2.0 (number set at `/ship`). This feature closes PEAK_MODEL
follow-ups F-14 and F-07 (SHIPPED_2026-10-22).

**User decisions taken in this phase (2026-10-22):** the questions Q-20 to Q-24 were answered as
recommended and are recorded as D-41 to D-45: keep the pipeline task retry (D-41), no pre-check in
the training job (D-42), fail at once with no wait and no pre-check retries (D-43), no reverse check
in the ingestion job (D-44, recorded as a METER_INGESTION follow-up), and fail closed when the state
cannot be read (D-45). OD-14 to OD-18 stay open for `/design`.

**ID numbering.** IDs continue the project-wide series: FR-33, NFR-19, AC-68, C-11, OD-14 continue
after PEAK_MODEL (FR-18 to FR-32, NFR-10 to NFR-18, AC-36 to AC-67, C-08 to C-10, OD-07 to OD-13).
D-39, A-19 and Q-20 continue the decision, assumption and question series (last used: D-38, A-18,
Q-19). F-NN in this document always means a PEAK_MODEL SHIPPED follow-up, not a brainstorm finding.
Constraints C-01 to C-10 apply under their original IDs.

---

## Problem Statement

The daily job `smart_meter_peak_model` and the ingestion job `smart_meter_ingestion` both refresh
the shared pipeline `smart_meter_silver_gold`, and the pipeline accepts one update at a time. When
the peak job's `refresh_silver_gold` task starts while another update runs, the request is refused
in about 2 s, the task ends `INTERNAL_ERROR` with "Pipeline update already in progress.", the job
does not retry it despite `max_retries: 1`, and every task behind it is skipped (DA-13, dev,
2026-10-22: ingestion run 1002990004411119, peak run 839517104898682). That day gets no
predictions. The error does not say which run holds the pipeline or what to do, and the job
configuration suggests a retry that never happens (F-14). The reverse order costs as much: an update
started by the peak job while an ingestion run is still in its ingest tasks makes the ingestion
run's own `refresh_silver_gold` (no retry) fail by the same rule (A-19).

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Platform operator (job owner, receives the on-failure email) | Know within one look why a daily run stopped, which run or update blocked it, and what to do | Failed task run of the daily job: its error message, and the on-failure email |
| Scheduled daily run of `smart_meter_peak_model` | Never request a pipeline update that the platform will refuse when the conflict is visible beforehand | Task graph of the daily job |
| `smart_meter_ingestion` (shipped, METER_INGESTION) | Its own pipeline update is not refused because a peak run started one during its ingest tasks | Unchanged job; protected by the peak job checking first |
| Integration tests and the runbook | One documented rule for when a run that includes the pipeline may start | `docs/runbooks/peak_model.md`, `tests/integration/` |
| Reviewer | Trace the concurrency behaviour to a decision and to tests | ADR, this DEFINE, tests named after AC-68 to AC-80 |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| No refused pipeline request from the peak job when the conflict is visible | Peak daily runs whose `refresh_silver_gold` ends with "Pipeline update already in progress." while an ingestion run or a pipeline update was already active at pre-check time | 0 (AC-74, AC-75) |
| Diagnosis from the message alone | Pre-check failures whose message does not name the blocking run id or update id and the action to take | 0 (AC-69 to AC-71, AC-74, AC-75) |
| Small cost | Wall-clock duration of the pre-check task on dev | <= 120 s (AC-76) |
| No change to the shipped ingestion feature | Differences of the `smart_meter_ingestion` job and `smart_meter_silver_gold` pipeline definitions against tag `v0.1.0` | 0 (AC-78) |
| Safe rerun | Manual steps other than rerunning the job after a refusal by the pre-check | 0 (AC-77) |

---

## Scope

**In scope:**
- A pre-check step in the daily job `smart_meter_peak_model` that runs before `refresh_silver_gold`
  and fails with a clear message when `smart_meter_ingestion` has an active run or the pipeline
  `smart_meter_silver_gold` has an active update (D-39).
- The task-graph change in the daily job, and the update of the PEAK_MODEL bundle tests that assert
  the old graph (AC-62 tests; OD-18).
- Runbook Concurrency section and troubleshooting row; every documented subset command that runs
  `refresh_silver_gold` also runs the pre-check.
- An ADR recording the decision (new ADR or note to ADR 0008; OD-17).

**Out of scope:**
- Any change to the `smart_meter_ingestion` job or the `smart_meter_silver_gold` pipeline,
  including a reverse check in the ingestion job (D-44). Recorded as a METER_INGESTION follow-up
  (see *Follow-ups for other features*).
- A pre-check in the training job `smart_meter_peak_model_training` (D-42): it has no pipeline task.
- Waiting or polling until the blocker ends, and retries of the pre-check task (D-43).
- A lock that removes the race window between the check and the pipeline start (C-11). The next
  daily run stays the retry for that window (D-39).
- The idle check of the reset script (PEAK_MODEL F-03) and `disable_auto_optimization` on
  `ingest_kafka` (F-05). Both stay follow-ups of their own features; the pre-check logic may be
  reused there later.
- Schedule changes (ingestion 06:00 UTC, peak 08:00 UTC stay).

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-33 | The system shall run a pre-check step in the daily job `smart_meter_peak_model` before `refresh_silver_gold`. `refresh_silver_gold`, and every task that depends on it directly or indirectly (`build_features`, `build_labels`, `score_predictions`), shall start only when the pre-check succeeds. Tasks that do not depend on the pipeline (`ingest_weather`, `build_weather_silver`) keep their current dependencies. | Must |
| FR-34 | The pre-check shall fail when the `smart_meter_ingestion` job deployed by the same bundle target has at least one active run, that is a run whose life-cycle state is not terminal (terminal: `TERMINATED`, `SKIPPED`, `INTERNAL_ERROR`), at any task of that run. | Must |
| FR-35 | The pre-check shall fail when the `smart_meter_silver_gold` pipeline deployed by the same bundle target has an update in a non-terminal state (terminal: `COMPLETED`, `FAILED`, `CANCELED`), whoever started it (ingestion job, UI, API). | Must |
| FR-36 | When the pre-check fails because of FR-34 or FR-35, its task shall end with result state `FAILED` and an error message that names every blocking item: for a job run, the job name `smart_meter_ingestion` and the run id; for an update, the pipeline name `smart_meter_silver_gold`, the update id and its state. The message shall state the action: wait until the named run or update ends, then rerun `smart_meter_peak_model`; without action, the next scheduled run (08:00 UTC) is the retry. | Must |
| FR-37 | When neither FR-34 nor FR-35 applies, the pre-check shall succeed and the run shall continue as before. The pre-check shall only read: it shall not start, stop, cancel or change any job run, pipeline update, job, pipeline or table. | Must |
| FR-38 | (D-45) When the pre-check cannot establish the state (the ingestion job or the pipeline is not found or not unique, an API call fails, or permission is denied), it shall fail, not pass, with a message that names what could not be read. | Must |
| FR-39 | The system shall leave unchanged: the `smart_meter_ingestion` job and `smart_meter_silver_gold` pipeline definitions (identical to tag `v0.1.0`, C-08, D-44), and the training job `smart_meter_peak_model_training` (identical to tag `v0.2.0`, D-42). | Must |
| FR-40 | Every command in `docs/runbooks/peak_model.md` that starts `refresh_silver_gold` with a task subset (`--only`) shall include the pre-check step. | Must |
| FR-41 | The runbook Concurrency section and troubleshooting table shall describe the pre-check failure, its message and the action. The decision shall be recorded in an Accepted ADR. | Should |
| FR-42 | (D-41) `refresh_silver_gold` shall keep one retry after 600 s (`max_retries: 1`, `min_retry_interval_millis: 600000`) for transient `FAILED` updates. The runbook and the job file comment shall state that a refused update (`INTERNAL_ERROR`) is not retried. | Should |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-19 | Cost and platform limits | The pre-check adds 1 serverless task per daily run, with a task run duration of at most 120 s on dev (expected about 30 s). The widest level of the daily task graph stays at most 2 tasks, so the runbook bound of 2 + 2 concurrent tasks with an overlapping ingestion run stays below the Free Edition limit of 5 (C-01 to C-07). |
| NFR-20 | Security | 0 credentials or tokens in tracked files, bundle YAML or the pre-check code. The pre-check runs under the job's workspace identity with read access only, and takes no secret parameter. |
| NFR-21 | Idempotency | The pre-check has no side effects: with the same platform state, two executions give the same outcome and the same message except for timestamps. A run refused by the pre-check leaves nothing to clean up; rerunning the job is enough. |
| NFR-22 | Time handling | Every timestamp in the pre-check message is UTC in ISO 8601 with a `Z` suffix. |
| NFR-23 | Fail-fast | The pre-check does not wait for the blocker: it decides from one read of the current state, and its task is configured with 0 retries (D-43). |

---

## Data Contracts

This feature writes no table and changes no existing contract. It reads platform metadata and
produces one task outcome per daily run. Contracts are inline because no other feature shares them.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| Runs of job `smart_meter_ingestion` (Jobs API, read only) | METER_INGESTION (platform metadata) | One job run | `run_id` | Read live at pre-check time | Inline: fields used are `run_id`, life-cycle state, start time (UTC) |
| Updates of pipeline `smart_meter_silver_gold` (Pipelines API, read only) | METER_INGESTION (platform metadata) | One pipeline update | `update_id` | Read live at pre-check time | Inline: fields used are `update_id`, update state, creation time (UTC) |
| Pre-check outcome (task run result and error message) | PEAK_MODEL_CONCURRENCY | One pre-check task run per daily job run attempt | job `run_id`, task `run_id` | At task end | Inline: result state `SUCCESS` or `FAILED`; on `FAILED`, the FR-36 or FR-38 message |
| PEAK_MODEL tables (`silver.weather_hourly`, `ml.household_features_daily`, `ml.household_labels_daily`, `gold.consumption_spike_predictions`) | PEAK_MODEL | Unchanged | Unchanged | Unchanged | `docs/contracts/` (no change) |

---

## Acceptance Criteria

Unit criteria run against a fake workspace client that records every call. Live criteria run on the
deployed `dev` target with the integration marker.

| ID | Given | When | Then |
|---|---|---|---|
| AC-68 | The bundle resource files at the feature commit | The daily job definition is read | A pre-check task exists, has no `pipeline_task` and has `max_retries: 0` (D-43). `refresh_silver_gold` depends directly on it. The pre-check is an ancestor of `build_features`, `build_labels` and `score_predictions`. `ingest_weather` and `build_weather_silver` keep their v0.2.0 dependencies. The widest level of the graph has at most 2 tasks. Schedule `0 0 8 * * ?` UTC and `max_concurrent_runs: 1` are unchanged |
| AC-69 | A fake client: `smart_meter_ingestion` has 1 active run with id R (each non-terminal life-cycle state tested), the pipeline has no active update | The pre-check runs | It fails. The message contains `smart_meter_ingestion`, R, and the rerun action of FR-36. Every timestamp in the message matches ISO 8601 UTC with `Z`. The fake records 0 calls that start, stop, cancel or change anything |
| AC-70 | A fake client: no active ingestion run; the pipeline's latest update U is in a state S | The pre-check runs for each non-terminal S, then for each terminal S (`COMPLETED`, `FAILED`, `CANCELED`) | For each non-terminal S it fails, and the message contains `smart_meter_silver_gold`, U and S. For each terminal S it succeeds |
| AC-71 | A fake client: an active ingestion run R and an active update U | The pre-check runs | It fails, and the message contains both R and U |
| AC-72 | A fake client: no active ingestion run; the pipeline has no update, or its latest update is terminal | The pre-check runs twice | Both executions succeed with the same outcome. The fake records read calls only |
| AC-73 | A fake client in each of these states: the ingestion job matches 0 jobs, it matches 2 jobs, the pipeline matches 0 pipelines, a read call raises an error, a read call is denied | The pre-check runs | It fails in each case (D-45) with a message that names the job or pipeline that could not be read, and it never reports success |
| AC-74 | The `dev` target is deployed, the pipeline is idle, and a run R of `smart_meter_ingestion` has been started and is active | A run of `smart_meter_peak_model` that includes the pre-check and `refresh_silver_gold` starts while R is active | The pre-check task ends `FAILED` with a task run duration of at most 120 s, and its error output contains R. `refresh_silver_gold` ends `UPSTREAM_FAILED` (never started), and so do its dependents. If R reaches its `refresh_silver_gold`, that task does not end with "Pipeline update already in progress." |
| AC-75 | The `dev` target is deployed, no ingestion run is active, and an update U of `smart_meter_silver_gold` has been started through the Pipelines API and is not terminal | A run of `smart_meter_peak_model` that includes the pre-check and `refresh_silver_gold` starts | The pre-check task ends `FAILED` within 120 s, and its error output contains U. `refresh_silver_gold` ends `UPSTREAM_FAILED`. The pipeline lists no update created between the start and the end of the peak run |
| AC-76 | The `dev` target is deployed, no ingestion run is active and the pipeline has no active update | A full run of `smart_meter_peak_model` starts | Every task ends `SUCCESS` on its first attempt. The pre-check task run lasts at most 120 s. Task durations are recorded in the build report |
| AC-77 | A daily run refused by the pre-check (AC-74), and predictions for its default target date T from an earlier successful run | After R ends, the daily job is run again with no other step | The rerun ends `SUCCESS`. The prediction rows of T differ from the earlier run in `_scored_at` only |
| AC-78 | The repository at the feature commit and tag `v0.1.0` (and tag `v0.2.0` for the training job) | The resource definitions are compared | `smart_meter_ingestion` and `smart_meter_silver_gold` are identical to `v0.1.0` (D-44). `smart_meter_peak_model_training` is identical to `v0.2.0` (D-42). `refresh_silver_gold` has `max_retries: 1` and `min_retry_interval_millis: 600000` |
| AC-79 | The repository at the feature commit | `docs/runbooks/peak_model.md` and `docs/adr/` are read and `scripts/check_specs.py` runs | Every runbook command with `--only` that lists `refresh_silver_gold` also lists the pre-check task. The Concurrency section names the pre-check, the message content of FR-36 and the rerun action, and the troubleshooting table has a row for a pre-check failure. An Accepted ADR records D-39. `check_specs.py` reports 0 errors |
| AC-80 | The repository at the feature commit | The secrets scan of tracked files runs and the daily job definition is read | The scan finds 0 Databricks tokens. The pre-check task has no parameter that names a secret scope or a token |

### Traceability (FR and NFR to AC)

| Requirement | Covered by |
|---|---|
| FR-33 | AC-68, AC-74, AC-76 |
| FR-34 | AC-69, AC-71, AC-74 |
| FR-35 | AC-70, AC-71, AC-75 |
| FR-36 | AC-69, AC-70, AC-71, AC-74, AC-75 |
| FR-37 | AC-69, AC-72, AC-76, AC-77 |
| FR-38 | AC-73 |
| FR-39 | AC-78 |
| FR-40 | AC-79 |
| FR-41 | AC-79 |
| FR-42 | AC-78 |
| NFR-19 | AC-68, AC-74, AC-76 |
| NFR-20 | AC-80 |
| NFR-21 | AC-72, AC-77 |
| NFR-22 | AC-69 |
| NFR-23 | AC-68 (0 pre-check retries), AC-74, AC-75 (failure within 120 s, no wait) |

Coverage of the required kinds: correctness AC-68 to AC-71, AC-76; idempotency and reprocessing
AC-72, AC-77; data quality of the inputs (unresolvable or ambiguous job and pipeline) AC-73;
failure paths AC-69 to AC-71, AC-73 to AC-75.

---

## Decisions and Open Items

### Decided by the user

| ID | Decision | Where it is used |
|---|---|---|
| D-39 (2026-10-22) | A pre-check task runs before `refresh_silver_gold` in `smart_meter_peak_model`. It checks for an active run of `smart_meter_ingestion` and an active update of `smart_meter_silver_gold`, and fails with a message that names the blocking run or update and says to rerun after it ends. Accepted costs: one extra serverless task (about 30 s) and a race window between the check and the pipeline start, which stays covered by the existing fallback (the next daily run is the retry) | FR-33 to FR-37, NFR-19, NFR-23, AC-68 to AC-77 |
| D-40 (2026-10-22) | The change is specified as a new feature, PEAK_MODEL_CONCURRENCY. The archived PEAK_MODEL documents are not edited; this feature closes PEAK_MODEL follow-up F-14, which supersedes F-07 | Metadata, Scope |
| D-41 (Q-20, 2026-10-22) | `refresh_silver_gold` keeps `max_retries: 1` with `min_retry_interval_millis: 600000`, for transient `FAILED` updates. A retry does not rerun the pre-check; a retry refused by a new overlap falls under the D-39 race-window fallback | FR-42, AC-78 |
| D-42 (Q-21, 2026-10-22) | No pre-check in the training job `smart_meter_peak_model_training`; it stays identical to tag `v0.2.0` (it has no pipeline task; overlap with a daily run stays guarded by G-04 and the runbook) | FR-39, AC-78, Scope |
| D-43 (Q-22, 2026-10-22) | The pre-check fails at once: no wait, no polling, and no retries of the pre-check task | NFR-23, AC-68, AC-74, AC-75, Scope |
| D-44 (Q-23, 2026-10-22) | No reverse check in `smart_meter_ingestion`; the ingestion job and pipeline stay identical to tag `v0.1.0`. The reverse check is recorded as a METER_INGESTION follow-up | FR-39, AC-78, Scope, *Follow-ups for other features* |
| D-45 (Q-24, 2026-10-22) | Fail closed: when the pre-check cannot read the state (job or pipeline not found or ambiguous, API error, permission denied), it fails with a message naming what could not be read | FR-38, AC-73 |

### Open questions for the user

None. Q-20 to Q-24 are answered as D-41 to D-45.

| ID | Status |
|---|---|
| Q-20 | Answered 2026-10-22 as D-41 (keep the pipeline task retry) |
| Q-21 | Answered 2026-10-22 as D-42 (no pre-check in the training job) |
| Q-22 | Answered 2026-10-22 as D-43 (fail at once, no wait, no pre-check retries) |
| Q-23 | Answered 2026-10-22 as D-44 (no reverse check; METER_INGESTION follow-up) |
| Q-24 | Answered 2026-10-22 as D-45 (fail closed) |

### Follow-ups for other features

- METER_INGESTION (through `/iterate` on that feature, not here): a reverse check in
  `smart_meter_ingestion` so that its `refresh_silver_gold` does not request an update while a
  `smart_meter_peak_model` update runs (D-44). Today the 2-hour schedule offset avoids that case;
  the ingestion task has `max_retries: 0`, so a refused update there fails the ingestion run. The
  pre-check logic of this feature may be reused.

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-14 | How the pre-check identifies the ingestion job and the pipeline: bundle resource references for the job id and the pipeline id passed as task parameters (exact and scoped to the target), or lookup by name with the development-mode prefix stripped (prior art: `tests/integration/conftest.py`). This decides A-22 |
| OD-15 | Task type and environment of the pre-check (notebook task or Python script task; whether it needs `peak_model_env`), and how D-43 (no retries) is enforced on serverless: whether it sets `disable_auto_optimization`, since `max_retries: 0` alone did not stop a serverless retry (PEAK_MODEL build deviation D-21) |
| OD-16 | Task key, and where the decision logic lives so that a fake client can test it and `PeakRunner.assert_ingestion_idle` and the reset script (F-03) can reuse it. Which API fields define "active" for runs and updates (life-cycle state, `latest_updates` or the update list) |
| OD-17 | ADR form: a new ADR that amends the task graph of ADR 0008 (with a dated note in ADR 0008), or a dated note in ADR 0008 alone |
| OD-18 | How the PEAK_MODEL AC-62 tests are updated for the new task (`tests/test_peak_bundle.py::test_ac62_daily_job_graph_schedule_and_pipeline_dependency` asserts the exact task list, `refresh_silver_gold` having no dependency and the timeout list; `tests/integration/test_peak_deployment.py` asserts the deployed task set). The AC-62 text still holds as written; only the assertions change |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 to C-07 | Constraint | Inherited from METER_INGESTION: Free Edition serverless only; at most 5 concurrent job tasks, one active pipeline per type, daily quota; no secrets in code; UTC end to end | Yes |
| C-08 | Constraint | The METER_INGESTION job and pipeline are not modified (identical to tag `v0.1.0`) | Yes (user, 2026-10-20) |
| C-11 | Constraint | No lock is available across two jobs on one pipeline: job queueing applies to runs of the same job only, so a check cannot reserve the pipeline. A window between the check and the pipeline start remains | Accepted by the user (D-39); the fallback is the next daily run (ADR 0008) |
| C-12 | Constraint | `smart_meter_peak_model_training` stays identical to tag `v0.2.0` (D-42) | Yes (user, 2026-10-22) |
| A-19 | Assumption | A pipeline update requested while another update of the same pipeline runs is refused in about 2 s; the task ends `INTERNAL_ERROR` with "Pipeline update already in progress." and is not retried; downstream tasks are skipped | Validated 2026-10-22 on dev (DA-13; ingestion run 1002990004411119, peak run 839517104898682) |
| A-20 | Assumption | The Jobs API lists an in-progress ingestion run as active (including queued and pending runs), and the Pipelines API reports a running update with its update id and a non-terminal state | Partly validated: `PeakRunner.assert_ingestion_idle` (active-only run list and pipeline state) ran in the 27 passing PR 3 integration tests on 2026-10-22, idle case only. The busy case and the update id are pending; AC-74 and AC-75 validate them |
| A-21 | Assumption | The identity the daily job runs as can read the runs of `smart_meter_ingestion` and the updates of `smart_meter_silver_gold` with no extra grant | Pending (in dev the same user deploys and owns all three resources); checked by AC-76 |
| A-22 | Assumption | The pre-check resolves exactly one ingestion job and one pipeline of the same bundle target | Pending; depends on OD-14 |
| A-23 | Assumption | A serverless task that only reads job and pipeline state finishes in at most 120 s (about 30 s expected) | Pending; measured by AC-74 to AC-76 |
| A-24 | Assumption | A run started with `--only` skips the tasks outside the list, including their role as dependencies, so `--only refresh_silver_gold` would bypass the pre-check (reason for FR-40) | Observed in PR 3 (skipped tasks of an `only=` run end `DISABLED`, `tests/integration/conftest.py`); checked again by AC-74 |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Observed failure with run ids, error text and platform rule (A-19); cost named (lost day, unexplained error, misleading retry) |
| Users | 3 | Operator, scheduled run, ingestion job and reviewer, each with a concrete need and the place they read the outcome |
| Scope | 3 | Minimal and bounded by C-08 and C-12; training job, reverse check and waiting excluded by D-42 to D-44, the reverse check recorded as a METER_INGESTION follow-up |
| Acceptance criteria | 3 | 13 measurable criteria covering every FR and NFR, unit and live, with correctness, idempotency, input quality and failure paths; all final (D-41 to D-45) |
| Constraints | 2 | Platform rule validated (A-19); API visibility of a busy state, permissions and target scoping (A-20 to A-22) are pending until the live tests |
| **Total** | **14/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The race window remains by design (C-11, D-39): an ingestion run that starts between the check
    and the pipeline start still produces the old `INTERNAL_ERROR`. No AC can force that timing,
    so it is accepted, not tested.
  - The retry of `refresh_silver_gold` (D-41) does not rerun the pre-check, so a retry can hit
    the same refusal without a clear message.
  - AC-74 needs a live ingestion run. With the Kafka service off, the run still stays active long
    enough for the pre-check leg, but its own `refresh_silver_gold` may not run, so the last
    clause of AC-74 is then not exercised.
  - A-20 rests on the idle case only; the busy case of the Jobs and Pipelines APIs has not been
    observed through the SDK.
- **Risks:**
  - Fail-closed (D-45) turns an API outage or a missing permission into a lost daily run.
  - The pre-check changes the graph that the PEAK_MODEL AC-62 tests assert exactly (OD-18); a
    careless update there could weaken the guard of a shipped AC.
  - Lookup by name (OD-14) would depend on the development-mode name prefix and could match the
    wrong target's job.
- **Trade-offs:**
  - One extra serverless task on every run (about 30 s, daily quota) buys a clear message and
    protects the ingestion run's own update; it does not remove the platform refusal.
  - Fail-fast keeps the job simple and cheap, at the cost of a lost day when an overlap happens
    (the next daily run is the retry), instead of a bounded wait.
  - A new small feature keeps the archived PEAK_MODEL record intact, at the cost of one more set of
    documents and cross-references to AC-62.
- **What I would do differently:** Observe the busy case of the Jobs and Pipelines APIs once
  (one ingestion run plus one SDK read) before `/design`, so that A-20 is validated before the
  ACs depend on it.
- **Next improvement:** In `/design`, settle OD-14 (resource references rather than name lookup)
  and OD-15 (how a serverless retry of the pre-check is prevented, D-43), and plan the A-20 busy-case
  observation as the first live step of the build.

---

## Next Step

1. `/design .claude/sdd/features/DEFINE_PEAK_MODEL_CONCURRENCY.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-22 | Created: FR-33 to FR-42, NFR-19 to NFR-23, AC-68 to AC-80, C-11, A-19 to A-24, D-39, D-40, Q-20 to Q-24, OD-14 to OD-18. Status `Draft` | Phase 1 of the SDD workflow, from PEAK_MODEL follow-up F-14 | `/design` waits for Q-20 to Q-24 |
| 2026-10-22 | Q-20 to Q-24 answered as recommended and recorded as D-41 to D-45; *(proposed)* markers removed from FR-38, FR-39, FR-42, AC-73 and AC-78; AC-68 and NFR-23 require 0 pre-check retries (D-43); C-12 added; METER_INGESTION reverse-check follow-up recorded; OD-15 narrowed; clarity 12/15 to 14/15; status `Ready for Design` | User answers | `/design` can start; OD-14 to OD-18 open |
