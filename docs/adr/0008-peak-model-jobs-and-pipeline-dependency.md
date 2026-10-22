# 0008. PEAK_MODEL jobs: the daily job runs the shared Silver/Gold pipeline first, training runs in a separate on-demand job

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-21 |
| **Deciders** | Christian |
| **Related** | PEAK_MODEL; FR-18, FR-19, FR-28, FR-30, NFR-13, NFR-14; AC-36, AC-38, AC-62; D-24, D-33, D-36; OD-07, OD-11, OD-12; ADR 0001, 0003, 0004, 0007 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

PEAK_MODEL reads the Gold tables of the shipped METER_INGESTION feature and must score only after
a Silver/Gold pipeline update (D-24, D-33). The METER_INGESTION job `smart_meter_ingestion` and the
pipeline `smart_meter_silver_gold` must stay byte-identical to tag `v0.1.0` (C-08, AC-62). Training
runs on demand, and each successful run moves alias `champion` (D-36). The feature also owns hourly
weather in Bronze and Silver (D-25), and no Lakeflow pipeline may be added (FR-30).

Platform facts (ADR 0001, `.claude/kb/databricks/free-edition.md`):
- serverless only;
- at most 5 concurrent job tasks per account;
- one active pipeline per pipeline type;
- a daily fair-usage quota;
- a task can run twice although it sets `max_retries: 0` (DA-12, cause not verified).

Three ways to depend on the pipeline update were open (DEFINE OD-07):
1. a first task that runs the existing pipeline;
2. a first task that runs the whole `smart_meter_ingestion` job (`run_job_task`);
3. a trigger that follows the METER_INGESTION job or the Gold table update.

Two ways to start training were open (OD-12): a separate job, or a run-mode parameter of the daily
job.

## Decision drivers

- The scoring task must depend on a pipeline update in a way a bundle test can check (AC-62).
- The METER_INGESTION definitions stay untouched, and no new pipeline is added.
- A Kafka outage (the free Aiven service powers off, ADR 0001 DA-11) must not stop PEAK_MODEL from
  scoring on the Gold data that already exists.
- No training task may be on the daily schedule (AC-62), and a scheduled run must never register a
  model version.
- Nothing may rely on a platform feature that has not been spiked on Free Edition.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Daily job `smart_meter_peak_model` whose first task is a `pipeline_task` on the existing `smart_meter_silver_gold` pipeline (`full_refresh: false`). Weather ingestion runs beside it, then features, labels and scoring follow. Training is a separate job, `smart_meter_peak_model_training`, with no schedule** | The ordering is explicit in the task graph and testable from the YAML. The job is independent of Kafka. An update with no new Bronze input is cheap, because unchanged materialized views skip the refresh (ADR 0001, DA-01). No training code can run on the schedule. Every task type is proven: pipeline task (spike 04, METER_INGESTION), notebook tasks with Feature Engineering (spike 05) | The pipeline can now be started from two jobs. When both run at the same time, one pipeline update request may be refused. The daily job does not ingest new Bronze readings itself |
| First task `run_job_task` on `smart_meter_ingestion` | One run does ingestion, Gold and scoring; Bronze is always fresh | A Kafka outage fails the PEAK_MODEL run as well. The ingestion job then runs from two places (its own schedule and the parent), against its `max_concurrent_runs: 1` |
| Table-update or job-completion trigger | No duplicate pipeline start | Not spiked on Free Edition. Whether a materialized-view refresh fires a table-update trigger is unknown. The dependency is hard to test from the YAML |
| One job with a `run_mode` parameter (`daily`, `train`) and condition tasks | A single job name (D-35) | The scheduled job would contain the training task, skipped by a condition. That reads as a training task on the daily schedule (AC-62), and a wrong parameter on a scheduled run would register a model |

## Decision

We will deploy two jobs from the same bundle, with no change to `databricks.yml` variables, to the
METER_INGESTION job or to the pipeline:

- **`smart_meter_peak_model` (daily).** Task graph:
  - `refresh_silver_gold`: a `pipeline_task` on the existing pipeline, `full_refresh: false`. It runs
    in parallel with `ingest_weather` (Auto Loader `availableNow` into `bronze.files_weather_hourly`).
  - `build_weather_silver` follows `ingest_weather`. It recomputes `silver.weather_hourly` from
    Bronze in a job task, because no pipeline may be added (OD-11).
  - `build_features` follows `refresh_silver_gold` and `build_weather_silver`.
  - `build_labels` follows `refresh_silver_gold`.
  - `score_predictions` follows `build_features` and `build_labels`.
  - The widest level of the graph has 2 tasks.
  - The schedule is 08:00 UTC, two hours after the ingestion job's 06:00 UTC, so the two pipeline
    starts do not normally overlap. The pipeline task has one retry after 10 minutes, for
    transient failed updates only. An update refused because the ingestion job has one in
    progress ends in `INTERNAL_ERROR` and is not retried (DA-13, PR 2 gate 2026-10-22).
- **`smart_meter_peak_model_training` (on demand).** One notebook task, `train_model`, with no
  schedule and `max_retries: 0`. It reads the feature and label tables that the daily job keeps
  current and registers one version per successful run (D-36).

## Consequences

- **Positive:**
  - AC-62 can be checked from the YAML: the scoring task depends on `refresh_silver_gold`, there
    is no training task in the scheduled job, and exactly one pipeline resource exists.
  - PEAK_MODEL keeps scoring when the Kafka service is off.
  - METER_INGESTION stays byte-identical.
- **Negative:**
  - Fresh readings reach PEAK_MODEL only after a run of `smart_meter_ingestion`. The daily job
    refreshes Gold from the Bronze data that already exists.
  - Two job names to operate instead of one; the user accepted this as D-37 (DEFINE D-35, FR-30,
    AC-62 updated through `/iterate` on 2026-10-21).
  - If an update from the ingestion job is running when the PEAK_MODEL run starts, the update is
    refused ("Pipeline update already in progress.") and the run fails without a retry. The
    next daily run is the retry; the runbook says not to run both jobs at once.
  - A serverless automatic retry of `train_model` (DA-12) could register a second, identical
    version. The version is deterministic (AC-49), so `champion` still points at a correct model.
- **Note (2026-10-21, PR 2 gate):** on serverless, `max_retries: 0` alone does not stop retries:
  auto-optimization retried the failed training task and registered a second version. The
  training task therefore also sets `disable_auto_optimization: true` (build deviation D-21).
- **What would make us revisit this:**
  - a real consumer that needs readings ingested in the same run;
  - Free Edition allowing table-update triggers on materialized views (verified by a spike);
  - refused concurrent updates becoming frequent (observed at the PR 2 gate: the retry does not
    absorb them, so the schedule offset is the only protection).
