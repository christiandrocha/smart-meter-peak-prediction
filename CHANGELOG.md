# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: SemVer.
Entries are added by `/ship`.

## [Unreleased]

## [0.6.0] - 2026-11-09

### Added

- Follow-up task template (FOLLOW_UP_TEMPLATE, CHANGE track):
  `.claude/sdd/templates/FOLLOW_UP_TEMPLATE.md` with Metadata (spec-prefixed `F-NN`, source spec
  and finding, status `Open`, `In Progress`, `Closed` or `Dropped`), Problem, Triage against E1 to
  E8 (CHANGE track or full cycle; in doubt, full cycle), Done Criterion, Target and Priority,
  Closure and Self-Review. Follow-up files live in `.claude/sdd/follow-ups/` as
  `F_<SPEC>_<NN>.md`; `scripts/check_specs.py` does not read them.

### Changed

- Confirmation rules aligned with the repository guarantees (ALIGN_CONFIRMATION_RULES, CHANGE
  track, E8 `Relaxing`): `git push --force-with-lease` runs without confirmation only on a branch
  created for the current task, after a rebase, and only after reading ruleset `main-protection`
  (26640008) and finding it active on the default branch with `non_fast_forward` and no bypass
  actors; otherwise it still needs confirmation. `git push --force` stays on the confirmation
  list. `CLAUDE.md` rule 8 names this one exception.
- After a merge, the remote head branch is removed by GitHub (`delete_branch_on_merge`): no
  `git push --delete`, removal confirmed with `git ls-remote --heads origin <branch>`, merge
  without `--delete-branch`, local branch deleted with `git branch -d`.
- `.claude/sdd/README.md` describes the follow-ups folder: creation, triage and closure.

### Unchanged

- No production file (`src/`, `resources/`, `notebooks/`, `databricks.yml`), no gate
  (`scripts/check_specs.py`) and no archived document of an earlier feature changed; the package
  version stays 0.4.1.

## [0.5.0] - 2026-11-06

### Added

- CHANGE track for small tooling or process changes (SMALL_CHANGE_TRACK): one document
  `CHANGE_<FEATURE>.md` from `.claude/sdd/templates/CHANGE_TEMPLATE.md` replaces DEFINE, DESIGN,
  BUILD_REPORT and SHIPPED for changes that meet the eligibility criteria E1 to E8. The checker
  requires one row per criterion with result `Yes` (E8 may be `Relaxing`, with a `## Rule Changes`
  section), traceability from every AC to Test Strategy and Evidence, and an `Evidence commit` SHA in
  a `Complete` document. In a `Complete` document an Evidence result of `Fail` or `Not run` is an
  error; `Deferred: <reason>` is accepted and listed as a warning, and `Deferred` without a reason
  is an error. A change folder in `archive/` holds only the CHANGE document.
- `scripts/check_specs.py` reports every `.md` file in `features/` or `reports/` whose name has no
  phase prefix as an error; `.gitkeep` files give none.
- `scripts/check_specs.py` checks the shipped specs in `.claude/sdd/archive/` (SPEC_ARCHIVE_GATES):
  the existing rules per archive folder; every archived document in its phase's final status and
  exactly one `SHIPPED_YYYY-MM-DD.md` per folder; SHIPPED documents as a checked phase (file-name
  date equal to `Shipped on`, all template sections with a non-empty Self-Review, and from the
  2026-11-05 cut-off also `Pull Requests and Branches` and no unfilled placeholders); a warning for
  each archived finding marked `Open`; and an error for an unprefixed citation of another spec's
  finding ID.
- `.claude/sdd/citation_allowlist.json`: the 17 existing unprefixed citations (12 entries), frozen
  with exact counts; a different count or a stale entry is an error.
- Unit tests for AC-107 to AC-119 in `tests/test_check_specs.py`, including a self-test that checks
  the final-status documents of `features/` and `reports/` as if they were archived.

### Changed

- The SHIPPED template ends with `## Self-Review`.
- `.claude/sdd/README.md` describes the archive checks.
- `.claude/sdd/README.md`, `docs/conventions/git.md` and `CLAUDE.md` describe the CHANGE track and
  the branch names `spec/`, `build/`, `ship/` and `change/` (`feat/` is no longer the convention);
  the branch example in `docs/conventions/naming.md` follows them.

### Unchanged

- No production file (`src/`, `resources/`, `notebooks/`, `databricks.yml`) and no archived document
  of an earlier feature changed; the package version stays 0.4.1.

## [0.4.1] - 2026-11-04

### Added

- Timing evidence for the live AC-97 test. Each run writes `out/evidence/ac97_timing.json`
  (git-ignored), also when an assertion fails. It holds the creation, end and terminal state of the
  no-op update, the refused run and its check task, what the check read, and the rerun. The margin
  `read_after_creation_seconds` and `update_outlived_read_seconds` is recorded, not compared with a
  threshold. Helpers without SDK code are in `tests/support/ac97_timing.py`.
- Live test `test_ac106_ac97_timing_evidence_matches_the_platform`. It starts no run; it checks the
  evidence file for consistency and against three platform reads.
- Runbook subsection "AC-97 timing evidence" in `docs/runbooks/meter_ingestion.md`.
- Unit tests `tests/test_ac97_timing.py` and `tests/test_ac97_timing_docs.py`.

### Changed

- Layout rule in `tests/test_integration_layout.py` accepts three-digit AC names (`test_ac(\d{2,3})_`);
  AC-106 is in the expected live ACs.
- Package version set to 0.4.1.

### Unchanged

- The ingestion job `smart_meter_ingestion`, the daily peak job `smart_meter_peak_model`, the training
  job, the pipeline `smart_meter_silver_gold`, the `pipeline_guard` library and the bundle. No
  production file differs from `v0.4.0` except the version line.

## [0.4.0] - 2026-11-04

### Added

- Pre-check task `check_silver_gold_idle` in the ingestion job `smart_meter_ingestion`. It runs
  after the two ingest tasks and before `refresh_silver_gold`, on its own serverless environment
  (version 2). It is read-only, has no retries, and fails at once when an update of the shared
  pipeline `smart_meter_silver_gold` is in progress or when its state cannot be read. The message
  names the blocking update and the action to take (ADR 0013).
- Pipeline-only mode in `pipeline_guard`, appended to the shared guard. The peak mode is unchanged.
- Tests: unit tests `tests/test_ingestion_guard.py`, `tests/test_ingestion_guard_bundle.py` and
  `tests/test_ingestion_guard_docs.py`; integration tests `tests/integration/test_ingestion_guard_live.py`.
- ADR 0013: a read-only, pipeline-only pre-check in the ingestion job, and no platform retry of
  `ingest_kafka`.

### Changed

- `ingest_kafka` runs once per job run: `max_retries: 0` and `disable_auto_optimization: true`. A
  broker outage fails the task and the next daily run is the retry (AC-10, AC-95).
- Ingestion job graph: five tasks. `refresh_silver_gold` runs only after the check succeeds. A busy
  pipeline now fails the ingestion refresh at the check with a named update, instead of an unnamed
  `INTERNAL_ERROR` on the pipeline task. Bronze ingestion is not affected.
- ADR 0012 and ADR 0008 have dated notes (2026-10-23) that record the coexistence with the ingestion
  job.
- Runbooks: `docs/runbooks/meter_ingestion.md` (Concurrency with the peak job, live evidence rows H
  to J) and `docs/runbooks/peak_model.md` (no ingestion `--only` list).
- Package version set to 0.4.0.

### Unchanged

- The daily peak job `smart_meter_peak_model`, its pre-check `check_pipeline_idle` and the peak mode
  of `pipeline_guard`. The diff against `v0.3.0` adds lines only.
- The pipeline `smart_meter_silver_gold`, the training job `smart_meter_peak_model_training` and the
  schedules of both daily jobs.

### Known limits

- An update started by another run in the same seconds as the check still ends `INTERNAL_ERROR` on
  the task that started second. There is no retry; the next scheduled run is the retry.
- The check runs after `ingest_kafka`. When that task fails, the check does not run and the refresh
  is skipped, as in v0.1.0.
- The check fails closed. An API or SDK fault in the check blocks the Silver and Gold refresh of both
  daily jobs until it is fixed; Bronze is kept.

## [0.3.0] - 2026-10-22

### Added

- Pre-check task `check_pipeline_idle` in the daily job `smart_meter_peak_model`. It runs first, has
  no retries and reads the state of the ingestion job and of the shared pipeline
  `smart_meter_silver_gold` without writing anything. When either is busy, or when its state cannot
  be read, it fails at once and names the blocking run or update. `refresh_silver_gold` runs only
  after it succeeds (ADR 0012).
- Integration tests `tests/integration/test_peak_concurrency.py` for the busy, idle and rerun cases.

### Changed

- Daily job graph: the pre-check precedes the shared pipeline task, which is unchanged. An overlap
  with an ingestion run now fails on the pre-check task with a message that names the blocking run,
  instead of an unnamed `INTERNAL_ERROR` on the pipeline task. The next daily run is the retry.
  The runbook (Concurrency) describes the pre-check (ADR 0008 dated note, ADR 0012).
- The pre-check task and its notebook run on serverless environment version 2 (`peak_model_env`).
  Auto-optimization is off for the task and the platform does not retry it.

### Unchanged

- The ingestion job `smart_meter_ingestion`, the pipeline `smart_meter_silver_gold` and the training
  job `smart_meter_peak_model_training` keep their definitions.

## [0.2.0] - 2026-10-22

### Added

- PEAK_MODEL: a daily job predicts, for each eligible household, whether the next day's consumption
  is a spike (strictly above 1.3 times the median of the last four complete same-weekday days within
  eight weeks, ADR 0010). It writes `gold.consumption_spike_predictions` for the target date; the
  default target is the day after the latest complete day (2014-02-28 on the seed-42 sample).
- Weather ingestion from a Unity Catalog Volume into `bronze.files_weather_hourly` and
  `silver.weather_hourly`, with a change-only MERGE and a guard against an empty source.
- ML tables `ml.household_features_daily` and `ml.household_labels_daily`: dense per household and
  date, point-in-time (features as of the day before the target), with the parameters recorded as
  table properties (ADR 0011).
- On-demand training job `smart_meter_peak_model_training`: a gradient boosting model logged to MLflow
  with Unity Catalog feature lookups, registered as `smart_meter_dev.ml.consumption_spike_model`.
  Promotion uses the `champion` alias; the decision threshold is a version tag (ADR 0009).
- Daily job `smart_meter_peak_model` (08:00 UTC) that runs the shared Silver and Gold pipeline first.
- Operations runbook `docs/runbooks/peak_model.md` and a guarded, user-run reset script
  `scripts/reset_peak_model_outputs.py`.
- Data contracts for the five PEAK_MODEL tables in `docs/contracts/` and ADRs 0007 to 0011.

### Changed

- Contract header comments and the PEAK_MODEL runbook point to the archived design documents under
  `.claude/sdd/archive/`. No schema changed.

### Known limits

- The peak job and the ingestion job share one pipeline. An update requested while the other one
  runs is refused and the task ends `INTERNAL_ERROR`, which the job does not retry; the next daily
  run is the retry (runbook, Concurrency).
- Training runs on demand only, without retries. Retry-sensitive steps depend on the idempotent
  writes and on the alias, not on single-attempt execution.

## [0.1.0] - 2026-10-20

### Added

- Meter ingestion (METER_INGESTION): a deterministic 60-household seed-42 sample and a replay
  producer that publishes post-cutoff readings to the Aiven Kafka topic `meter-readings`.
- Bronze ingestion of historical CSV files (Auto Loader, `availableNow`) and of the Kafka topic
  (raw payload with topic, partition and offset). Both are idempotent and do not advance on failure.
- Silver tables `meter_readings`, `meter_readings_quarantine`, `meter_readings_evaluated` and
  `households`: first-ingested-wins deduplication, rule-based quarantine, and table-total rule
  counts. A replay of the stream leaves Silver unchanged; a full refresh from Bronze reproduces
  identical Silver and Gold contents.
- Gold tables `household_daily_consumption`, `household_data_quality_monthly` and the
  `household_data_quality` view, the input contract for PEAK_MODEL.
- Asset Bundle for the `dev` target: daily job `smart_meter_ingestion` and the Lakeflow pipeline
  `smart_meter_silver_gold` (serverless, Unity Catalog `smart_meter_dev`).
- Data contracts for the topic and every published table in `docs/contracts/`, and 33 integration
  tests (`pytest -m integration`) that check 25 acceptance criteria against the workspace.
- Operations runbook `docs/runbooks/meter_ingestion.md` (deploy, evidence order, outage and reset
  procedures) and ADRs 0001 to 0006.

### Known limits

- Live verification ran on Databricks Free Edition with Aiven free-tier Kafka. AC-28 (a first deploy
  on a fresh workspace) is partial; the exit codes of that run are not recorded.
- Powering off the Aiven free service empties the topic; recovery needs a Kafka reset (runbook).
- The four pull requests (#1 to #4) are stacked and not merged at the time of this entry.
