# Runbook: peak model

How to deploy, bootstrap, train, score, verify, reset and clean up the PEAK_MODEL feature: the
daily next-day consumption spike model on top of the METER_INGESTION Gold tables. It targets the
`dev` bundle target on Databricks Free Edition. Design: `.claude/sdd/features/DESIGN_PEAK_MODEL.md`.
Decisions: ADR 0007 to 0011. Contracts: `docs/contracts/` (`bronze_files_weather_hourly`,
`silver_weather_hourly`, `ml_household_features_daily`, `ml_household_labels_daily`,
`gold_consumption_spike_predictions`). The ingestion side is in `docs/runbooks/meter_ingestion.md`.

## What runs where

```text
local machine                       Databricks (serverless, target dev, catalog smart_meter_dev)
-------------                       --------------------------------------------------------------
weather CSV --databricks fs cp-->   Volume landing/weather/
                                    job smart_meter_peak_model (daily 08:00 UTC, paused in dev mode)
                                     refresh_silver_gold -> existing pipeline smart_meter_silver_gold
                                     ingest_weather -> build_weather_silver
                                     build_features (after both), build_labels (after the pipeline)
                                     score_predictions (champion model) -> gold.consumption_spike_predictions
                                    job smart_meter_peak_model_training (on demand, no schedule)
                                     train_model -> MLflow run + model version + alias champion
```

- The bundle adds two jobs and no pipeline (ADR 0008). `databricks.yml` and the METER_INGESTION
  resources are unchanged.
- Every table is recomputed in full and written with a change-only MERGE, so a rerun with no new
  input changes 0 rows (ADR 0011). Bronze weather is the replay source (ADR 0006).
- Time is UTC end to end: every notebook sets and asserts `spark.sql.session.timeZone = UTC`.
- Every notebook task runs on the job environment `peak_model_env` (serverless environment
  version 2, Python 3.11, scikit-learn 1.3.0; ADR 0007). The notebooks install the pinned
  `databricks-feature-engineering==0.18.2` themselves.
- No secret is needed: PEAK_MODEL uses the workspace identity only.

## Concurrency with the ingestion job

**Do not run the peak daily job, or any run that includes `refresh_silver_gold`
(`--only refresh_silver_gold` included), while `smart_meter_ingestion` is running.** Both jobs
refresh the same pipeline, and a pipeline allows one update at a time. The second update is refused
with "Pipeline update already in progress.", the task ends `INTERNAL_ERROR`, and it is **not
retried** (DA-13 failed at the PR 2 gate: the task `max_retries: 1` covers transient `FAILED`
updates only). What to do:

1. The schedules are offset on purpose: ingestion at 06:00 UTC, peak at 08:00 UTC. A manual run is
   the usual cause of an overlap. Check first:
   `databricks jobs list-runs --job-id <ingestion job id> --active-only -p dev` must list nothing.
2. If a peak run was refused, wait for the ingestion run to end, then rerun the peak job (or, to
   repeat only the step, `--only refresh_silver_gold` and the tasks behind it). Nothing was
   written by the refused task, so the rerun is safe. In production use the next daily run is the
   retry.
3. The integration tests need the ingestion job idle for the whole sequence, even for tasks that
   skip the pipeline, because they compare against Gold. In normal operation, tasks that do not run the pipeline (`ingest_weather`, `build_weather_silver`, `build_features`,
   `build_labels`, `score_predictions` run alone with `--only`, and the training job) can overlap
   the ingestion job. The task limit holds: at most 2 + 2 tasks run at once, below the Free
   Edition limit of 5.
4. Run training only when no daily run is active. The training job fails with a guard error
   (G-04) if the feature table changes underneath it.

The integration tests that start a run (`tests/integration/`) check that the ingestion job and the
pipeline are idle first and fail with this advice if they are not.

## Serverless auto-optimization and retries

Serverless jobs may retry a failed task even when `max_retries` is 0 or unset (build deviation
D-21; the same pattern was seen on `ingest_kafka`, follow-up F-02). For training this would
register one model version per attempt, so `train_model` sets `max_retries: 0` and
`disable_auto_optimization: true`. A failed attempt can still leave a registered version without
the `champion` alias: that is harmless (scoring reads the alias only) and is removed with the
model cleanup below. The other tasks are idempotent, so a retry is safe. When a run shows two
attempts of one task, read the first attempt's error, not the last.

## 1. Prerequisites

| Item | Notes |
|---|---|
| METER_INGESTION deployed, catalog and schemas exist | ADR 0003. The Gold tables must have been built once |
| Databricks CLI authenticated | `databricks auth login --host <workspace-url> --profile dev`; commands use `-p dev` |
| Project installed | `pip install -e ".[dev,integration]"` (the integration extra holds the SDK, MLflow and pyarrow) |
| Weather file | `data/raw/weather_hourly_darksky.csv` (git-ignored; 21,165 rows, header names as in the source) |
| Clean working tree | `git status --porcelain` prints nothing, so the commit the training run logs is the code that runs |

## 2. Deploy

```bash
git status --porcelain            # must print nothing
databricks bundle validate -t dev -p dev; echo "validate exit $?"
databricks bundle deploy -t dev -p dev;   echo "deploy exit $?"
```

Record both exit codes in the build report (AC-62). There is no first-deploy problem of the
METER_INGESTION kind, because PEAK_MODEL adds only jobs. The job names get the development-mode
prefix (`[dev <user>] smart_meter_peak_model`); tests and commands find them by base name.

## 3. Weather upload (once)

```bash
databricks fs cp data/raw/weather_hourly_darksky.csv \
    dbfs:/Volumes/smart_meter_dev/bronze/landing/weather/ -p dev
```

A new weather file must land under a new name (Bronze is append-only and the checkpoint remembers
files). Never overwrite the file.

## 4. Bootstrap order

Run these in order. The first three steps cannot be skipped: scoring needs a `champion` model, and
a first scoring step without one fails with an error naming the alias (AC-61).

1. Data tasks of the daily job. Make sure the ingestion job is idle (see Concurrency), then:

   ```bash
   databricks bundle run -t dev -p dev smart_meter_peak_model \
       --only refresh_silver_gold,ingest_weather,build_weather_silver,build_features,build_labels
   ```

2. Training, twice (the second run is the AC-49 comparison), with no build in between:

   ```bash
   databricks bundle run -t dev -p dev smart_meter_peak_model_training
   databricks bundle run -t dev -p dev smart_meter_peak_model_training
   ```

   Each run logs the training set, scores and metrics to the experiment
   `/Users/<you>/smart_meter_peak_model`, registers a version of
   `smart_meter_dev.ml.consumption_spike_model`, stores the threshold t as the version tag
   `decision_threshold` and moves the alias `champion`.

3. A full daily run (ingestion idle):

   ```bash
   databricks bundle run -t dev -p dev smart_meter_peak_model
   ```

   With the seed-42 data the default target date is 2014-02-28 (latest complete Gold day + 1) and
   the feature date is 2014-02-27.

## 5. Daily operation

The daily job is scheduled for 08:00 UTC. Development mode pauses the schedule, so in `dev` runs
are manual unless you unpause it in the Jobs UI. Failure emails go to the deploying user. Each task
returns a JSON exit value (row counts, QR-17 and QR-18 counts, MERGE metrics, parameters, scored
dates, model version and t); read it from the run page.

Job parameters (strings; an empty value uses the default): `label_threshold` 1.3,
`baseline_day_count` 4, `label_lookback_weeks` 8, `coverage_min` 0.80, `zero_share_max` 0.90,
`eligibility_months` 3, `target_date`, `target_date_end`. After a change to the label or
eligibility parameters the labels are rewritten, so retrain before the next scoring run is
meaningful; restore the defaults by running `build_labels` again with them.

## 6. Training

On demand, never scheduled. The training job parameters are `train_start`, `train_end`,
`validation_start`, `validation_end`, `test_start`, `test_end` and `random_seed` (defaults in the
bundle). The run stops before any metric or registration when a guard fails (empty validation
month, ranges out of order, missing feature row at T - 1). A successful run is reproducible: two
runs on unchanged tables give identical scores, threshold and metrics.

## 7. Backfill

```bash
databricks bundle run -t dev -p dev smart_meter_peak_model \
    --only score_predictions --params target_date=2013-12-01,target_date_end=2014-02-27
```

Rows of the scored dates are replaced as one transaction; a rerun changes only `_scored_at`. A
`target_date` beyond the last feature date fails before any write and names the missing feature
date. Features and labels are rebuilt on every daily run from Gold and Bronze weather; a full
rebuild is the reset below followed by a daily run.

## 8. Evidence order (integration tests)

The integration tests are user-run (`pytest -m integration`, credentials from the CLI profile
or `DATABRICKS_*` variables; see `tests/integration/conftest.py`). Keep each before/after pair
back to back and follow this order, with the ingestion job idle. After a redeploy, retrain before
`test_ac54` (it compares the run's commit with the deployed one):

```bash
export DATABRICKS_CONFIG_PROFILE=dev
pytest -m integration tests/integration/test_peak_data.py -k "ac36 or ac37 or ac39 or ac40 or ac41 or ac44 or ac47 or ac64"
pytest -m integration tests/integration/test_peak_data.py -k "ac63"      # before, then after (starts build_labels)
pytest -m integration tests/integration/test_peak_data.py -k "ac66_before"
#   optional rebuild leg: python scripts/reset_peak_model_outputs.py --confirm, then the daily job
pytest -m integration tests/integration/test_peak_data.py -k "ac66_after"
pytest -m integration tests/integration/test_peak_training.py            # needs two training runs
pytest -m integration tests/integration/test_peak_scoring.py -k "ac58 or ac59 or ac56"
pytest -m integration tests/integration/test_peak_scoring.py -k "ac57"   # before, then after
pytest -m integration tests/integration/test_peak_scoring.py -k "ac60"
pytest -m integration tests/integration/test_peak_deployment.py          # after a full daily run
```

Snapshots go to `out/evidence/` (git-ignored); copy the output into the build report. AC-61
(missing alias) is not run live because it would delete the alias of the shared model; the
bootstrap order above shows the same failure when no model exists yet. AC-65 is
`pre-commit run --all-files`.

## 9. Reset (user-run, AC-66)

`scripts/reset_peak_model_outputs.py` drops `silver.weather_hourly`,
`ml.household_features_daily` and `ml.household_labels_daily`, and nothing else: it never touches
Bronze, the model, the MLflow runs or `gold.consumption_spike_predictions`. It refuses unless
every table exists with the expected row count (21,165 and 36,480 twice), Bronze weather has rows
and the AC-66 snapshot exists.

```bash
python scripts/reset_peak_model_outputs.py            # dry run: prints the plan and the counts
python scripts/reset_peak_model_outputs.py --confirm  # drops the three tables
pytest -m integration tests/integration/test_peak_data.py -k "ac66_after"   # rebuilds them, then compares
```

The script prints table names and row counts only. After the rebuild the feature table is a new
Delta table with the same content (`ac66_after` starts `ingest_weather`, `build_weather_silver`,
`build_features` and `build_labels` itself and compares counts and checksums, so no daily run is
needed; run the daily job later as usual). The registered model and
the predictions are kept. Retrain only if you also changed parameters or data.

## 10. Model cleanup (order matters, ADR 0007)

Unity Catalog refuses to delete a registered model that still has aliases or versions. Delete in
this order: aliases, then versions, then the model.

```bash
M=smart_meter_dev.ml.consumption_spike_model
databricks registered-models delete-alias $M champion -p dev
databricks model-versions list $M -p dev                 # note the version numbers
databricks model-versions delete $M <version> -p dev     # once per version
databricks registered-models delete $M -p dev
```

To remove only old or orphan versions (for example the ones left by failed attempts), delete those
versions and leave `champion` and its version alone. Deleting the model removes `champion`, so
scoring fails until the training job has run again. Tables are dropped with the reset script;
`bronze.files_weather_hourly` and its checkpoint folder are dropped only together (ADR 0006).

## 11. Troubleshooting

| Symptom | Cause and action |
|---|---|
| `refresh_silver_gold` ends `INTERNAL_ERROR` after about 2 s, "Pipeline update already in progress." | The ingestion job was running. Not retried. Wait for it to end, then rerun (Concurrency) |
| `%pip` fails building scikit-learn | The task is not on `peak_model_env` (Python 3.12 has no 1.3.0 wheel). Redeploy the bundle (D-19) |
| Scoring fails naming the alias `champion`, or the tag `decision_threshold` | No trained model yet: run the training job (bootstrap step 2) |
| Scoring fails naming a missing feature date | `target_date - 1` is later than the last feature date: run `build_features` or pick an earlier date |
| Training fails on G-04 | A build changed the feature table during the run: rerun with no other job active |
| A training run shows two attempts | See "Serverless auto-optimization"; delete the extra version if wanted (section 10) |
| `build_weather_silver` stops "is empty" | Upload the weather file (section 3) and run `ingest_weather` |
