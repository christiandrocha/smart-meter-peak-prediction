# 0012. A read-only pre-check before the shared pipeline task in the daily peak job, failing fast and closed

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-22 |
| **Deciders** | Christian |
| **Related** | PEAK_MODEL_CONCURRENCY; FR-33 to FR-42, NFR-19 to NFR-23, AC-68 to AC-80; D-39, D-41 to D-45; OD-14 to OD-17; C-08, C-11, C-12; A-19 to A-24; amends ADR 0008 (task graph of `smart_meter_peak_model`); ADR 0001, 0007 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

The daily job `smart_meter_peak_model` (ADR 0008) and the ingestion job `smart_meter_ingestion`
both start updates of the one pipeline `smart_meter_silver_gold`. The pipeline accepts one update at
a time. On 2026-10-22 on `dev` (DA-13), a peak run whose `refresh_silver_gold` started while the
ingestion run had an update in progress was refused in about 2 s: the task ended `INTERNAL_ERROR`
with "Pipeline update already in progress.", the job did not retry it despite `max_retries: 1`, and
every task behind it was skipped. The error names neither the blocking run nor the action. The
reverse order fails the ingestion run's own pipeline task, which has no retry (A-19).

Constraints:
- The ingestion job and the pipeline stay identical to tag `v0.1.0` (C-08, D-44), and the training
  job stays identical to tag `v0.2.0` (C-12, D-42).
- No lock exists across two jobs on one pipeline; job queueing applies to runs of the same job only
  (C-11).
- Free Edition: serverless only, at most 5 concurrent job tasks, a daily quota (ADR 0001).
- Serverless auto-optimization retried a failed task although `max_retries` was 0; only
  `disable_auto_optimization: true` stopped it (PEAK_MODEL build deviation D-21, ADR 0008 note).
- The user decided (DEFINE D-39, D-41 to D-45): a pre-check before the pipeline task; keep the
  pipeline task retry for transient `FAILED` updates; no pre-check in the training job; fail at
  once without waiting or retrying; no reverse check in the ingestion job; fail closed when the
  state cannot be read.

## Decision drivers

- An operator must see, in the failed task's error, which run or update blocked the job and what to
  do (FR-36).
- The peak job must not request an update that the platform will refuse when the conflict is
  visible beforehand, so the ingestion run's own update is not refused either (FR-34, FR-35).
- No change to the shipped METER_INGESTION definitions (C-08).
- Small cost: one short serverless task per run (NFR-19), no polling (NFR-23).
- The check must find the ingestion job and the pipeline of the same bundle target, never another
  deployment's (A-22).
- Testable without a workspace: the decision logic runs against a fake client (AC-69 to AC-73).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **A notebook task `check_pipeline_idle` before `refresh_silver_gold`, reading the active runs of the ingestion job and the latest updates of the pipeline through the Databricks SDK. It fails at once with a message naming every blocker, and fails closed when it cannot read the state. The job id and the pipeline id are bundle references passed as task parameters. No retries, auto-optimization disabled** | Clear message with run and update ids; the conflicting request is never sent, so the ingestion run's update is protected too; ids are exact and scoped to the target; logic in a library module, unit-tested with a fake; no change to METER_INGESTION | One more serverless task per run (about 30 s); a race window remains between the check and the pipeline start (C-11); fail-closed turns an API outage into a lost day |
| Status quo with documentation only: keep the refused `INTERNAL_ERROR` and the runbook rule | No code | The error stays unexplained; the misleading retry setting stays; the ingestion run can still be refused by a peak update |
| Wait or poll in the pre-check until the blocker ends | The day is not lost | Rejected by the user (D-43): burns serverless quota while waiting, no bound on the wait that fits the job timeout without a design of its own |
| A condition task that skips `refresh_silver_gold` when the pipeline is busy and scores on the existing Gold | Predictions are produced every day | Scores while ingestion is changing Gold; condition tasks cannot read the API themselves, so a check task is needed anyway; the run reports success while it did not refresh |
| A lock or reverse check in the ingestion job | Closes the window in both directions | No cross-job lock exists (C-11); any change to the ingestion job breaks C-08 (D-44, follow-up of METER_INGESTION) |
| Identify the job and the pipeline by name, with the development-mode prefix stripped (prior art in the integration tests) | No bundle reference needed | Could match another target's or another user's deployment; depends on the display-name prefix format |

## Decision

We will add a task `check_pipeline_idle` as the first task of `smart_meter_peak_model`. It is a
serverless notebook task on the job environment `peak_model_env`, with `max_retries: 0`,
`disable_auto_optimization: true` and a 300 s timeout. `refresh_silver_gold` depends on it, so
`build_features`, `build_labels` and `score_predictions` depend on it through the pipeline task.
`ingest_weather` and `build_weather_silver` keep their dependencies.

The task receives the ingestion job id and the pipeline id as bundle resource references and calls
the library module `smart_meter_peak_prediction.pipeline_guard` with a `WorkspaceClient` under the
job's identity (default notebook authentication; the retry and HTTP timeouts are set through
`Config`, as spike 06 found for `databricks-sdk` 0.40.0). The module performs read calls only (`jobs.get`, `jobs.list`, `jobs.list_runs`,
`pipelines.get`):
- A run of the ingestion job counts as active when its life-cycle state is not `TERMINATED`,
  `SKIPPED` or `INTERNAL_ERROR`.
- A pipeline update counts as active when its state is not `COMPLETED`, `FAILED` or `CANCELED`. An
  unknown state counts as active.
- The overall pipeline state (`pipelines.get(...).state`, added 2026-10-22 from the build review)
  also decides: `IDLE` and `FAILED` pass; `DEPLOYING`, `STARTING`, `RUNNING`, `STOPPING`,
  `RECOVERING`, `RESETTING` and any other or missing value count as busy; `DELETED` fails closed.
  This covers an update missing from `latest_updates` while the pipeline runs, at no extra call.

When anything is active, the task fails with a message that names the job, the run id, the pipeline,
the update id and its state, with UTC times ending in `Z`. The message says to wait until the named
run or update ends and then rerun `smart_meter_peak_model`; without action, the next scheduled run
is the retry. When it cannot establish the state, the task fails with a message naming what could
not be read: an id that is missing or not resolved, a job or pipeline that is not found, has another
name or is not unique, an API error, or a denied permission. It never waits and never retries.

`refresh_silver_gold` keeps one retry after 600 s for transient `FAILED` updates (D-41). A retry
does not rerun the pre-check.

This decision amends the task graph of ADR 0008; the rest of ADR 0008 stands.

## Consequences

- **Positive:**
  - A visible conflict no longer reaches the pipeline. The operator reads the blocking run or update
    id and the action in the failed task's error.
  - The ingestion run's own update is protected from a peak update started during its ingest tasks,
    with no change to the ingestion job.
  - The same library function backs the idle check of the integration tests
    (`PeakRunner.assert_ingestion_idle`), so the tests and the job use one definition of "active".
  - Ids from the bundle are exact and belong to the same target.
- **Negative:**
  - One more serverless task per daily run (about 30 s, counted against the daily quota).
  - The race window stays: an ingestion run or update that starts after the check and before the
    pipeline task still produces the old `INTERNAL_ERROR` (C-11). The next daily run is the retry.
  - Fail-closed: an API outage or a missing permission costs the day's predictions.
  - A run started with `--only` that omits `check_pipeline_idle` bypasses the check; the runbook
    lists the pre-check in every such command (FR-40).
  - The retry of `refresh_silver_gold` can still meet a new overlap without the clear message.
- **What would make us revisit this:**
  - A lock, a queue across jobs or a table-update trigger on Free Edition that removes the race
    window (verified by a spike).
  - The pre-check failing closed on API errors more than once a month.
  - A reverse check added to `smart_meter_ingestion` through METER_INGESTION, which would share
    `pipeline_guard`.
  - The serverless environment losing `databricks-sdk` or its default notebook authentication.

## Platform probe (spike 06)

Spike 06 (`spikes/databricks/06_spike_pipeline_guard_probe.py`, submitted by
`06_spike_pipeline_guard_probe_submit.py`) ran on `dev` on 2026-10-22: idle probe runs
97142795569245 and a rerun with the `Config` form, busy probe run 727144628966036, no-op update
`ef3a0fd1-1ad5-424c-a86c-ac0afee0acf3`.

| Assumption | Result |
|---|---|
| DA-20 SDK and authentication in environment version 2 | Pass. `databricks-sdk` 0.40.0 is preinstalled (no `%pip`); `WorkspaceClient()` authenticates as the run-as user with no configuration; `jobs.get`, `jobs.list(name)`, `jobs.list_runs(active_only)` and `pipelines.get` all succeed. In 0.40.0 `WorkspaceClient` has no `retry_timeout_seconds` or `http_timeout_seconds` keyword (`TypeError`); both are `Config` fields, so the client is built as `WorkspaceClient(config=Config(retry_timeout_seconds=60, http_timeout_seconds=30))` |
| DA-22 `latest_updates` during an update | Pass. `latest_updates` is newest first; the new update appeared as entry 0 within 2.4 s of `start_update`. State sequence: `CREATED` (2 s), `WAITING_FOR_RESOURCES` (5 s), `INITIALIZING` (51 s), `SETTING_UP_TABLES` (86 s), `RUNNING` (88 s), `COMPLETED` (125 s). `creation_time` is an ISO 8601 string in UTC with `Z` (for example `2026-10-22T17:54:05.206Z`), not epoch milliseconds. `pipelines.get(...).state` read `RUNNING` during the update and `IDLE` otherwise |
| DA-23 `jobs.list(name=...)` | Pass. The filter on the deployed name `[dev christiandr] smart_meter_ingestion` returned exactly the ingestion job |
| DA-26 update length against a pre-check started after it | Pass. An update with no new input lasted 125 s. A probe task submitted right after `start_update` started 4 s later and, 31 s after the start, read the update as `WAITING_FOR_RESOURCES` (active) |

DA-19 (bundle reference to another job's id) is checked at the first deploy of the build; DA-21,
DA-24 and DA-25 by the live tests and prior art, as the DESIGN lists.
