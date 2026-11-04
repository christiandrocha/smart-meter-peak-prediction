# 0013. A read-only, pipeline-only pre-check before the pipeline task of the ingestion job, and no platform retry of the Kafka task

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-23 |
| **Deciders** | Christian |
| **Related** | INGESTION_GUARD; FR-43 to FR-53, NFR-24 to NFR-29, AC-81 to AC-99; D-46 to D-59; A-25 to A-32; C-11, C-13; complements ADR 0012 (the peak job's pre-check, whose revisit trigger this answers); updates a consequence of ADR 0008; ADR 0001, 0006 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

The ingestion job `smart_meter_ingestion` (METER_INGESTION, tag `v0.1.0`) and the daily peak job
`smart_meter_peak_model` (ADR 0008, ADR 0012) both start updates of the one pipeline
`smart_meter_silver_gold`, which accepts one update at a time. Since v0.3.0 the peak job checks
before its own pipeline task (ADR 0012); the ingestion job does not. When an update is in progress,
the ingestion job's `refresh_silver_gold` (no retry) is refused in about 2 s and ends
`INTERNAL_ERROR` with "Pipeline update already in progress.", and the on-failure email names neither
the blocking update nor an action (PEAK_MODEL_CONCURRENCY A-19, follow-up F-01).

Second fault: serverless auto-optimization retries `ingest_kafka` although it sets
`max_retries: 0`. A broker outage then shows two failed attempts, costs twice the quota and reaches
the job failure up to twice as late, against the documented no-retry policy (METER_INGESTION AC-10,
follow-ups METER_INGESTION F-02 and PEAK_MODEL F-05). Only `disable_auto_optimization: true` stopped
the same retry on `train_model` and on `check_pipeline_idle` (PEAK_MODEL build deviation D-21).

Spike 07 (2026-10-23, `dev`, run 843912359241341, Databricks CLI v0.298.0, default deployment
engine) established the platform facts this decision rests on:

| Assumption | Result |
|---|---|
| A-25 `disable_auto_optimization` on a `pipeline_task` | Invalidated: `bundle deploy` accepts the field, but the deployed pipeline task reads it back unset, as it does `max_retries`. It cannot be used on `refresh_silver_gold` |
| A-26 one notebook task on a job environment (serverless environment version 2) next to notebook tasks on the default environment | Validated: validate and deploy pass; the version 2 task ran with `databricks-sdk` 0.40.0 and Python 3.11.10 next to two default-environment tasks |
| A-27 `disable_auto_optimization: true` with `max_retries: 0` on a failing notebook task | Validated: 1 attempt. The control with `max_retries: 0` alone (the v0.1.0 `ingest_kafka` settings) had 2 attempts (attempt numbers 0 and 1), which reproduces the fault. The deployed control reads `max_retries` unset; with the setting it reads 0 |
| A-29 the job's run-as identity reads the pipeline state | Validated: `pipelines.get` returned state `IDLE` and three `latest_updates` under the deploying user's identity, the identity the ingestion job runs as |
| A-30 a bundle reference from the ingestion job to the peak job | Validated as a cycle: a one-way job reference resolves to the numeric id, but with references in both directions `bundle validate` passes and `bundle deploy` fails with `Error: Cycle: databricks_job.spike_07_guarded, databricks_job.spike_07_pipeline_task`; `bundle destroy` of that target fails the same way. The peak job already references the ingestion job id (ADR 0012), so the ingestion job cannot reference the peak job |
| A-32 the client in environment version 2 | Validated: `databricks-sdk` 0.40.0; the client is built through `Config` with the retry and HTTP timeouts, as spike 06 found (ADR 0012, Platform probe) |

Constraints:
- No lock exists across two jobs on one pipeline; job queueing applies to runs of the same job only
  (C-11).
- The peak daily job, `notebooks/check_pipeline_idle.py` and the peak-mode behaviour of
  `pipeline_guard` stay as shipped in v0.3.0; the pipeline and `databricks.yml` stay at `v0.1.0`; the
  training job stays at `v0.2.0` (C-13, D-53, D-54).
- Free Edition: serverless only, at most 5 concurrent job tasks, a daily quota (ADR 0001).
- The user decided (INGESTION_GUARD D-46 to D-59): Approach A, pipeline only (D-48); the message
  names the update (D-49); the check runs directly before `refresh_silver_gold`, after both ingest
  tasks (D-50); `disable_auto_optimization` on `ingest_kafka` and the check only (D-51); environment
  version 2 for the check only (D-55).

## Decision drivers

- No refused ingestion refresh when the conflict is visible beforehand, and a failure message that
  names the blocking update and the action (D-47, FR-47).
- Exactly one attempt of `ingest_kafka` per run (D-47, FR-43).
- No change to the shipped peak side and no mutual refusal with it (D-54, AC-98).
- The bundle must deploy: no reference cycle between the two jobs (A-30).
- Small cost: one short serverless task per run, no polling (NFR-24, NFR-28).
- Testable without a workspace: the decision logic runs against a fake client (AC-86 to AC-91).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **A. A notebook task `check_silver_gold_idle` directly before `refresh_silver_gold`, after `ingest_files` and `ingest_kafka`, that reads only the pipeline (one `pipelines.get`: overall state and `latest_updates`), fails at once naming the active update and the action, and fails closed when it cannot read the state. Pipeline id from the bundle reference to the pipeline resource; no job id. Environment version 2, `max_retries: 0`, auto-optimization off. `ingest_kafka` also sets `disable_auto_optimization: true`** | No bundle reference to the peak job, so no cycle (A-30). No mutual refusal: a peak run refused by its own pre-check never creates an update, so the ingestion check passes. Reuses the pipeline half of `pipeline_guard` with no new API call. The peak side stays byte-identical. Bronze is ingested before the check, so a refusal costs only the Silver/Gold refresh | Names the update, not the peak run. Does not protect a peak run's later tasks from a Gold change by the ingestion refresh (A-28, unchanged). The race window between the read and the pipeline start remains (C-11) |
| B. Full mirror of ADR 0012: block on any active run of `smart_meter_peak_model` and on the pipeline, naming the run | Names the peak run; symmetric | Needs the peak job id: a bundle reference makes the deploy fail with a Terraform cycle (A-30, spike 07); the fallback, a name lookup, can match another deployment (rejected in ADR 0012). Mutual refusal (F-38): a peak run refused by its pre-check stays active while `ingest_weather` and `build_weather_silver` run (up to 900 s each), so the ingestion check would refuse too and both jobs lose the day, which breaks the shipped live criterion AC-74. Blocks ingestion for a whole peak run |
| C. Stage-aware check: block on the pipeline and on active peak runs whose `check_pipeline_idle` did not fail | Names the peak run; covers the post-refresh Gold change (A-28); avoids most of the AC-74 refusal | Still needs the peak job id, so the same cycle (A-30) or a name lookup. Adds a new read shape (task states of a run) to probe on `databricks-sdk` 0.40.0. Mutual refusal stays possible when both checks run in the same second (F-38). Kept as the upgrade path if A-28 is observed |
| The check as the first task of the ingestion job | Fails earlier | Also refuses Bronze ingestion, which does not touch the pipeline; a longer race window (the ingest tasks run in between) |
| `disable_auto_optimization: true` on `refresh_silver_gold` as well | Would stop a platform retry of the pipeline task | Does not stick on a pipeline task (A-25, spike 07): the deployed task reads it back unset |
| Status quo with documentation only | No change | The refusal stays unexplained and `ingest_kafka` keeps its silent second attempt |
| Wait or poll in the check until the update ends | The refresh is not lost | Burns serverless quota; rejected for the peak side too (D-43) |

## Decision

We will add a task `check_silver_gold_idle` to `smart_meter_ingestion`. It depends on exactly
`ingest_files` and `ingest_kafka`, and `refresh_silver_gold` depends on exactly it, with the default
run condition (D-50, D-58). It is a serverless notebook task on a job environment
`ingestion_check_env` with environment version 2 (the other ingestion tasks keep the default
environment, D-55), with `max_retries: 0`, `disable_auto_optimization: true` and a 300 s timeout. It
receives the pipeline id as the bundle reference to the pipeline resource of the same target and no
job id (D-48, A-30).

The task calls a pipeline-only mode of `smart_meter_peak_prediction.pipeline_guard`, added next to the
peak mode without changing it (D-54). It reads only `pipelines.get` of `smart_meter_silver_gold`,
once. It passes when the overall pipeline state is `IDLE` or `FAILED` and no entry of
`latest_updates` is in a non-terminal state (terminal: `COMPLETED`, `FAILED`, `CANCELED`); any other,
missing or unknown state counts as busy; `DELETED`, a foreign pipeline, a missing or unresolved id
or any read error fails closed (the G-21 rule of ADR 0012). When busy, it fails with a message that
names the update id, its state and its creation time in UTC with `Z`, the overall pipeline state,
the caller `smart_meter_ingestion` and its schedule, that `refresh_silver_gold` did not start and
Bronze is kept, and the action: wait until the update ends, then rerun `smart_meter_ingestion`;
without action, the 08:00 UTC `smart_meter_peak_model` run refreshes the pipeline from Bronze. It
never waits and never retries.

We will also set `disable_auto_optimization: true` on `ingest_kafka`, keeping `max_retries: 0` and
its 840 s timeout, so a failed run has exactly one attempt (D-51). `refresh_silver_gold` is not
changed: the setting does not stick on a pipeline task (A-25).

This decision answers the revisit trigger of ADR 0012 ("a reverse check added to
`smart_meter_ingestion`"); ADR 0012's decision stands unchanged. It supersedes, for the ingestion job
file only, the "identical to `v0.1.0`" clause of PEAK_MODEL AC-62 and PEAK_MODEL_CONCURRENCY AC-78
(D-53); the file is pinned anew by its digest at the feature commit.

## Consequences

- **Positive:**
  - A visible conflict no longer reaches the pipeline from either job. The operator reads the
    blocking update id and the action in the failed task's error and the failure email.
  - A broker outage fails `ingest_kafka` once, within its 840 s timeout.
  - At most one of the two jobs loses its refresh in an overlap, never both (no mutual refusal):
    the peak pre-check refuses while any ingestion run is active, and the ingestion check refuses
    only while a pipeline update is active.
  - Bronze is ingested before the check, so a refusal loses no data; the next update (the 08:00 UTC
    peak run or the next ingestion run) refreshes Silver and Gold from it (ADR 0006).
- **Negative:**
  - One more serverless task per ingestion run (about 18 to 32 s measured on the peak side).
  - The race window stays in both directions: an update started between a check's read and the
    pipeline task's start still ends `INTERNAL_ERROR` with the old message (C-11).
  - Fail-closed now also costs the ingestion refresh when the API is unavailable or the SDK in
    environment version 2 changes; both checks then fail every day until fixed. Bronze is kept.
  - The message names the update, not the peak run that started it; the operator finds the run from
    the update's creation time.
  - A run started with `--only` that lists `refresh_silver_gold` without `check_silver_gold_idle`
    bypasses the check; the runbook lists the check in every such command.
  - The ingestion job file is no longer byte-identical to `v0.1.0`; it differs only by the three
    changes above and comments (AC-85).
- **What would make us revisit this:**
  - A scoring failure caused by a Gold change during a peak run (A-28): adopt Approach C, which then
    needs a non-cycle way to identify the peak job.
  - A lock, a queue across jobs or a table-update trigger on Free Edition that removes the race
    window (verified by a spike).
  - The platform honouring `disable_auto_optimization` (or another setting) on a pipeline task.
  - The check failing closed more than once a month, or environment version 2 losing
    `databricks-sdk` or its default notebook authentication.
