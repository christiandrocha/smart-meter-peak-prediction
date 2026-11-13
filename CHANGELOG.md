# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: SemVer.
Entries are added by `/ship`.

## [Unreleased]

### Fixed

- Reset commands name the project interpreter (RESET_COMMAND_VENV, CHANGE track, closes
  RESET_GUARD F-01): the reset commands in `docs/runbooks/peak_model.md` (sections 8 and 9) and in
  the docstring of `scripts/reset_peak_model_outputs.py`, and `RESET_COMMAND` in
  `tests/support/ac66_rules.py` (printed by the AC-66 refusals), name `.venv/bin/python` instead of
  a bare `python`, which the user's machine does not have. Each dry run ends with
  `; echo "exit $?"`. Unit tests AC-203 to AC-205 in `tests/test_reset_command_venv.py`.
- Project commands name the tools in `.venv/bin/` (VENV_COMMANDS, CHANGE track, closes
  RESET_COMMAND_VENV F-01 from RESET_COMMAND_VENV I-01): every copyable `python`, `pytest`, `ruff`,
  `pre-commit` and `pip` command in `CLAUDE.md` (Commands block), `README.md`, both runbooks,
  `.claude/sdd/README.md`, the workflow agent and command files, the usage text of
  `scripts/prepare_sample.py` and `scripts/profile_data.py`, the "next" line printed by
  `scripts/reset_peak_model_outputs.py` and the local-data test docstrings names `.venv/bin/<tool>`,
  so it works on a system with no bare `python` and in a shell that never activates the
  environment. The setup creates the environment with `python3 -m venv .venv`. Unit tests AC-207
  and AC-208 in `tests/test_venv_commands.py`.

### Unchanged

- No line of the reset script's code changed, only its docstring. The AC-202 text in the archived
  RESET_GUARD DEFINE and DESIGN stays as shipped. The shipped AC66_BOTH_LEGS AC-160 test changes
  only the filter that finds the docstring's `--confirm` line. No production file, no file under
  `tests/integration/` and no gate changed; the package version stays 0.8.0.
- VENV_COMMANDS: no agent rule in `CLAUDE.md` changed, only its Commands block. The shipped
  AC66_ZERO_NEW_RUNS AC-172 test changes only the filter that finds the leg command lines.
  `scripts/check_specs.py`, the SDD templates, `src/` and `tests/integration/` keep their bare
  commands (VENV_COMMANDS I-01, needs the full cycle); `ci.yml` and `.pre-commit-config.yaml` work
  as they are.

## [0.8.0] - 2026-11-12

### Added

- Active-run check for the user-run reset (RESET_GUARD, closes PEAK_MODEL F-03 and
  PEAK_MODEL_CONCURRENCY F-02, ADR 0014): `scripts/reset_peak_model_outputs.py` reads the two
  peak jobs, `smart_meter_peak_model` and `smart_meter_peak_model_training`, before the first DROP,
  in the dry run too, and refuses unless both are idle. Each job is found by base name in one page
  of `jobs.list` (development prefix stripped); no match, two matches or a full page refuses.
  `--confirm` has no option or variable that skips the check.
- Job-only mode of `pipeline_guard` (`check_jobs`, appended to the module without changing a
  shipped line): one active-run and identity check per named job, with the shipped rules.
- Unit tests on fakes for the reset script's `main()` and for the job-only mode:
  `tests/test_reset_guard.py`, `tests/test_reset_guard_library.py`, `tests/support/reset_fakes.py`,
  and the docs test `tests/test_reset_guard_docs.py`.

### Changed

- Every refusal before the first DROP prints one line, `refused, nothing dropped: ...`, and exits
  2. The time-zone refusal takes the same prefix. A failed DROP stops the loop and exits 1.
- The reset's warehouse statements wait 20 s, and its Jobs API client uses the shipped limits.
- Three shipped test pins are narrowed, each keeping its name and assert count (DA-68, in
  `tests/test_ac97_timing_docs.py` and `tests/test_ac66_legs_docs.py`), because the version and the
  reset script changed by design.
- The runbook (`docs/runbooks/peak_model.md`, sections 8 and 9) states the idle check.
- Package version 0.8.0 (`pyproject.toml`, `src/smart_meter_peak_prediction/__init__.py`).

### Unchanged

- The peak and pipeline-only modes of `pipeline_guard` are byte-equal to v0.7.3, and the plan of
  the reset script is unchanged. No bundle file (`resources/`, `databricks.yml`, `notebooks/`,
  `pipelines/`) and no dependency changed.

## [0.7.3] - 2026-11-11

### Fixed

- AC-66 first-read gate (AC66_FIRST_READ_GATE, CHANGE track, closes AC66_ZERO_NEW_RUNS F-01 from
  AC66_ZERO_NEW_RUNS I-07): `run_leg` in `tests/support/ac66_rules.py` checks the first run-list
  read with a new private helper, `_usable`, so a read whose check raises an `Exception` (a
  `list` subclass whose `__iter__` raises) stops the leg with the "could not be read (first read:
  not a list of integer run ids)" message instead of the raw error and its text. A
  `BaseException` such as `pytest.fail` still propagates. Unit tests AC-186 and AC-187 in
  `tests/test_ac66_rules.py`.

### Unchanged

- `run_ids` and `count_runs` are unchanged, so `count_runs` keeps its designed `comparison rule`
  result for such a read and the AC-165 tests are unchanged. No production file (`src/`,
  `resources/`, `notebooks/`, `databricks.yml`), no file under `tests/integration/` and no gate
  changed; the live legs need no new run, and the package version stays 0.4.1.

## [0.7.2] - 2026-11-11

### Added

- AC-119 archive simulation on a fixture feature (AC119_FIXTURE, CHANGE track, closes
  AC66_BOTH_LEGS F-06): two unit tests in `tests/test_check_specs.py` run `simulate_archive` and
  the archive rules of `scripts/check_specs.py` on a fixture feature `FIXTURE_AC119` built in
  `tmp_path`, over a copy of the real archive, with no skip. The positive test (AC-176) shows that
  a correctly prefixed cross-spec citation gives no error; the negative test (AC-177) shows that
  the same citation without its spec prefix gives exactly one rule (c) error. The simulation is
  now exercised between features, when no document is in its final status.
- AC-119 fixture on an empty archive (AC119_EMPTY_ARCHIVE, CHANGE track, closes AC119_FIXTURE
  F-01 from AC119_FIXTURE I-01): `fixture_source` in `tests/test_check_specs.py` takes the cited
  spec from the source's first archived folder, or, when the archive is empty (a new project from
  the template), generates one valid folder `CITED_AC119` to cite. The new test
  `test_ac179_fixture_runs_on_an_empty_archive` (AC-179, AC-180) forces that path on every run,
  so the AC119_FIXTURE tests no longer fail on a project with no archived feature.

### Unchanged

- The repository-state test `test_ac119_final_status_feature_docs_pass_the_archive_rules` is
  unchanged and still skips when no document of `features/` or `reports/` is in its final
  status. No production file (`src/`, `resources/`, `notebooks/`, `databricks.yml`), no gate
  (`scripts/check_specs.py`) and no template changed; the package version stays 0.4.1.

## [0.7.1] - 2026-11-10

### Added

- Run count of `smart_meter_peak_model` for the AC-66 legs: `count_runs` in
  `tests/support/ac66_rules.py` (no SDK, no I/O, no clock) compares two run-id reads and never
  raises; `RUN_JOB_NAME` names the job. `PeakRunner.run_ids` in `tests/integration/conftest.py` is
  the live reader (one list request, one page of 25, every state). Unit tests in
  `tests/test_ac66_rules.py` and docs tests in `tests/test_ac66_legs_docs.py`.

### Changed

- Both AC-66 live legs (`ac66_rerun_leg`, `ac66_rebuild_leg`) read the run list of
  `smart_meter_peak_model` before anything else and again after the refusal or the job run
  (AC66_ZERO_NEW_RUNS, closes AC66_BOTH_LEGS F-03). A clean refusal ends with `0 new runs`; a
  refusal during which a run started fails with its own message; a pass needs exactly its own run
  and prints one line with its run id. A run list that cannot be read never reports a pass or a
  clean refusal. `run_leg` takes a required `runs` reader, so a caller cannot omit the count.

### Docs

- Runbook `docs/runbooks/peak_model.md`: sections 8 and 9 describe the run-list reads, and the leg
  command lines carry `-rP`, so the pass line is printed.

### Unchanged

- No production file (`src/`, `resources/`, `notebooks/`, `databricks.yml`) and no reset script
  changed, and the package version stays 0.4.1 (D-99, as D-92 for v0.7.0). The evidence files,
  record fields, verdict and test names are unchanged.

## [0.7.0] - 2026-11-09

### Added

- AC-66 evidence helpers in `tests/support/ac66_rules.py` (no SDK, no I/O, no clock): the
  precondition of each leg, the expected MERGE metrics, the leg record, the verdict rule and the
  leg procedure with every side effect injected. Unit tests in `tests/test_ac66_rules.py` and
  docs tests in `tests/test_ac66_legs_docs.py`.
- `Evidence.read_text` and `Evidence.remove` in `tests/integration/conftest.py`. `Evidence` takes
  a `folder` argument whose default keeps the shipped `out/evidence/` path.

### Changed

- PEAK_MODEL AC-66 evidence is split into three live tests (PEAK_MODEL F-15, AC66_BOTH_LEGS): the
  rerun leg (`-k "ac66_rerun_leg"`), the rebuild leg (`-k "ac66_rebuild_leg"`) and the verdict
  (`-k "ac66_verdict"`). The verdict passes only when both legs passed against the current
  snapshot, in the PEAK_MODEL AC-66 order (rerun leg first). The combined test
  `test_ac66_after_rerun_and_rebuild_checksums_equal` and the selector `-k "ac66_after"` are
  removed, so a sequence that runs only one leg now fails.
- A leg whose tables are in the wrong state refuses before any job run and changes no evidence
  file. The leg and verdict records are `out/evidence/ac66_rerun_leg.json`,
  `ac66_rebuild_leg.json` and `ac66_verdict.json`; `ac66_after_rebuild.json` is no longer written.
- Runbook `docs/runbooks/peak_model.md` sections 8 (Evidence order) and 9 (Reset) state the new
  order. The module docstring of `tests/integration/test_peak_data.py` and the docstring and
  printed next step of `scripts/reset_peak_model_outputs.py` name the legs. The reset guards are
  unchanged.

### Unchanged

- No production file (`src/`, `resources/`, `notebooks/`, `databricks.yml`) changed, and the
  package version stays 0.4.1 (D-92), as in v0.5.0 and v0.6.0. The snapshot test
  `test_ac66_before_rebuild_snapshot` is unchanged.

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
