# BUILD REPORT: Meter Ingestion

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | METER_INGESTION |
| **Date** | 2026-10-19 |
| **Source** | DESIGN_METER_INGESTION.md |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

---

## Summary

This report covers **PR 1 (manifest entries 1 to 23)**. The local sampling port, CLI, producer, Docker files, plan, pyproject and `.env.example` changes, A-08 check and their tests are done and verified against `data/raw`. On 2026-10-16 the Databricks spikes 00, 01 and 04 and the DA-06 deploy test were run on the `dev` workspace and recorded in ADR 0001: A-02, A-09, A-10, DA-02, DA-03, DA-07, DA-08 and DA-10 pass, AC-15 is shown on the platform, DA-06 fails and DA-01 is partial. Both went through `/iterate` on 2026-10-16: DA-06 changes the first deploy to three steps; DA-01 publishes `silver.meter_readings_evaluated` and makes `metrics.py` count rules, scope and duplicates as table totals from it (new manifest entry 30a for its contract; PR 2a is now 20 files). The Kafka spikes 02 and 03 ran the same day: A-03, A-05, A-06, DA-05 and DA-09 pass, so every row of ADR 0001 now has a result.

**PR 2a (entries 24 to 42 and 30a) was built on 2026-10-19** on branch `feat/meter-ingestion-pr2a`: library modules, summary view SQL, contract 30a, local pipeline harness and unit tests, all verified locally (Spark 4.0.4, Java 17). Nothing was run against Databricks or Kafka. PR 2b and PR 3 are not started. PR 2a status: **Complete** (local scope; live evidence pending, see below).

---

## Files Changed

State legend: done, written-not-run, partial, not started.

| # | PR | File | Action | State and verification |
|---|---|---|---|---|
| 1 | PR 1 | spikes/local/a08_offgrid_null_cooccurrence.py | Created | done: Ran on data/raw: A-08 PASS (see AC-11) |
| 2 | PR 1 | spikes/databricks/00_setup_catalog.py | Created | done: Run 2026-10-16 as a one-off serverless job (SUCCESS). A-09 Pass, verified by listing schemas and Volumes. DA-06 manual deploy test run before it: Fail |
| 3 | PR 1 | spikes/databricks/01_spike_autoloader.py | Created | done: Run 2026-10-16 (SUCCESS). A-02 Pass: 143,633 rows on run 1, 0 on run 2, no rescued data |
| 4 | PR 1 | spikes/databricks/02_spike_kafka_consume.py | Created | done: Run 2026-10-16 (SUCCESS). 1,000 events read with SCRAM-SHA-256 and an inline PEM CA; `processingTime` rejected; secrets readable |
| 5 | PR 1 | spikes/databricks/03_spike_kafka_unreachable.py | Created | done: Run 2026-10-16 with the service off. The query failed at once (DNS); the failure escaped the notebook `try`, so the checkpoint and table were checked directly: unchanged |
| 6 | PR 1 | spikes/databricks/04_spike_lakeflow_pipeline/pipeline.py | Created | done: Ran in the spike pipeline on 2026-10-16 without changes |
| 7 | PR 1 | spikes/databricks/04_spike_lakeflow_pipeline/summary_view.sql | Created | done: Published as `gold.spike_summary` (`VIEW`) |
| 8 | PR 1 | spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py | Created | done: Run 2026-10-16 with `--profile dev`; 12 of 13 checks pass (DA-01 update 2 fails); pipeline deleted afterwards |
| 9 | PR 1 | docs/adr/0001-runtime-environment-constraints.md | Modified | partial: A-08, A-02, A-09, A-10, DA-01 (Partial), DA-02, DA-03, DA-06 (Fail), DA-07, DA-08 and DA-10 recorded. A-03, A-05, A-06, DA-05 and DA-09 stay Pending (spikes 02 and 03) |
| 10 | PR 1 | docs/spikes/README.md | Modified | partial: Spikes 00, 01 and 04 recorded; 02 and 03 Pending |
| 11 | PR 1 | docs/adr/0002 to 0006 (conditional) | Modified | partial: ADR 0003 updated through `/iterate` (DA-06 first-deploy order). ADR 0004 updated through `/iterate` (DA-01: published evaluation table, counts from its columns). ADR 0002 waits for A-03 and A-06 |
| 12 | PR 1 | pyproject.toml | Modified | done: Extras sample, producer, integration; dev adds pyspark and keeps pyyaml; markers integration and local_data; addopts excludes both. |
| 13 | PR 1 | `.env.example` | Modified | done: Placeholders KAFKA_TOPIC, REPLAY_SPEED, SAMPLE_STREAM_FILE, DATABRICKS_WAREHOUSE_ID, no values |
| 14 | PR 1 | config/sample_plan.json | Created | done: Loaded by tests; recomputed blocks equal it (local_data test) |
| 15 | PR 1 | src/smart_meter_peak_prediction/sampling.py | Created | done: ruff; tests/test_sampling.py; local_data tests; outputs byte-identical to pinned checksums |
| 16 | PR 1 | scripts/prepare_sample.py | Created | done: ruff; CLI run on data/raw; tests/test_sampling.py |
| 17 | PR 1 | src/smart_meter_peak_prediction/producer.py | Created | done: ruff; tests/test_producer.py; `--dry-run` over the real stream file (247,569 events). No broker contacted |
| 18 | PR 1 | docker/producer/Dockerfile | Created | written-not-run: Not built: docker build is the user's step (see Pending on the user) |
| 19 | PR 1 | .dockerignore | Created | done: Reviewed by hand; excludes .env, data/, *.pem, .git |
| 20 | PR 1 | tests/test_sampling.py | Created | done: 11 passed |
| 21 | PR 1 | tests/local_data/test_sample_seed42.py | Created | done: `pytest -m local_data`: 6 passed against data/raw |
| 22 | PR 1 | tests/test_producer.py | Created | done: 13 passed |
| 23 | PR 1 | tests/test_runtime_adr.py | Created | done (1 red by design): check_specs test passes; the ADR-results test fails until the user records spike results |

PR 2b (entries 43 to 52) and PR 3 (entries 53 to 60): **not started**.

### PR 2a files (state: done, verified locally)

| # | File | Verification |
|---|---|---|
| 24 | .github/workflows/ci.yml | setup-java Temurin 17 added; no secrets; YAML hook passes |
| 25 | src/.../config.py | tests/test_config.py (6 tests) |
| 26 | src/.../rules.py | tests/test_rules_metrics.py; used by harness |
| 27 | src/.../bronze.py | tests/test_bronze.py (11 tests) |
| 28 | src/.../silver.py | test_silver_readings, test_silver_dedup, test_silver_households |
| 29 | src/.../gold.py | test_gold_daily, test_gold_quality |
| 30 | src/.../metrics.py | reconciliation, totals and checksum SQL run on local Spark |
| 30a | docs/contracts/silver_meter_readings_evaluated.yaml | check_specs 0 errors; test_contract_schemas |
| 31 | pipelines/household_data_quality.sql | SELECT body run locally (AC-25, AC-35); CREATE VIEW itself runs in PR 2b |
| 32 | tests/conftest.py | session Spark, UTC, ANSI on |
| 33 | tests/support/builders.py | used by all unit tests |
| 34 | tests/support/harness.py | used by all pipeline tests |
| 35 to 42 | tests/test_bronze.py, test_silver_readings.py, test_silver_dedup.py, test_silver_households.py, test_gold_daily.py, test_gold_quality.py, test_contract_schemas.py, test_secrets_hygiene.py | 158 passed in total |
| extra | tests/test_config.py, tests/test_rules_metrics.py, tests/local_data/test_pipeline_seed42.py, pyproject.toml (S608 ignore for SQL builders) | see Deviations |

---

## Acceptance Criteria Evidence

Evidence collected for PR 1 and PR 2a. Unit and local-data evidence is real output; integration and platform evidence for PR 2b and PR 3 is pending (Aiven is off, nothing was run on Databricks).

| AC | Result | Evidence |
|---|---|---|
| AC-01 | Pass (PR 1 scope) | `pytest tests/test_sampling.py`: test_ac01_* pass. `pytest -m local_data`: test_ac01_seed42_reruns_are_byte_identical and test_ac01_plan_recomputed_from_raw_equals_committed_plan pass; data-file SHA-256 equal `config/sample_manifest.json`; household CSV byte-equal `config/sample_households.csv` |
| AC-02 | Pass (PR 1 scope) | test_ac02_* (unit, 2 tests) and local_data test_ac02_src_sampling_selects_exactly_the_pinned_households and test_ac02_src_sampling_counts_match_pinned_manifest pass: 60 households, 20 per group, 16 Std and 4 ToU per group, exclusions equal the pinned list |
| AC-03 | Pass (PR 1 scope) | test_ac03_* (unit, 2 tests) and local_data test_ac03_seed42_split_counts_match_pinned_manifest pass: 1,432,405 historical and 247,569 stream rows, per-file rows and checksums equal the pinned manifest |
| AC-04 | Pass (PR 1 scope) | test_ac04_* (unit, 2 tests) and local_data test_ac04_seed42_cutoff_2013_11_01_preserves_total pass. Bundle-variable half (AC-28) is PR 2b |
| AC-05 | Partial | PR 2a: test_ac05_* in tests/test_bronze.py pass (file and household projections, source header only in the read schema). Integration counts are PR 3 |
| AC-06 | Not started | PR 3 (integration) |
| AC-07 | Partial | Producer half (PR 1) and test_ac07_kafka_projection_keeps_raw_payload_and_offsets pass. Integration is PR 3 |
| AC-08 | Not started | PR 3 (integration) |
| AC-09 | Partial | PR 2a: test_ac09_replayed_messages_counted_as_duplicates_and_silver_unchanged passes (Silver and quarantine checksums equal, QR-09 total up by the replayed rows). Integration is PR 3. See I-15 for replayed invalid messages |
| AC-10 | Partial | PR 2a: test_ac10_kafka_options_bound_broker_timeouts and the no-try/except test pass. Bundle test is PR 2b; broker-outage evidence is PR 3 (manual). Spike 03 evidence as before |
| AC-11 | Partial | PR 2a: test_ac11_* pass (reconciliation 0 unclassified, 0 double). Local-data on the real seed-42 sample (`pytest -m local_data tests/local_data/test_pipeline_seed42.py`): 1,679,974 Bronze rows, 60 quarantined, 1,679,914 in Silver, 0 out of period, 0 duplicates, 0 unclassified. Integration is PR 3 |
| AC-12 | Partial | PR 2a: test_ac12_rule_counts_equal_quarantine_failed_rules_per_update passes (two updates, equal totals); wiring test is PR 2b; integration is PR 3 |
| AC-13 | Partial | test_ac13_silver_invariants_hold_on_mixed_fixture passes; integration is PR 3 |
| AC-14 | Partial | test_ac14_cutoff_boundary_rows_appear_once_with_correct_path passes; integration is PR 3 |
| AC-15 | Partial | PR 2a unit tests pass (drop rules x5, QR-08 warn, fail rules x7 parametrized, unknown household, QR-10/12, QR-11, QR-13 to QR-15). Platform evidence from spike 04. Wiring is PR 2b |
| AC-16 | Pass (PR 2a scope) | test_ac16_study_period_boundaries_and_scope_count and the settings-driven variant pass; SF-01 total 2 |
| AC-17 | Pass (PR 2a scope) | test_ac17_earlier_ingested_at_wins_and_tie_uses_smaller_source_ref and test_ac17_rerun_keeps_same_winners pass (reversed order, repartitioning) |
| AC-18 | Partial | test_ac18_households_are_typed_and_renamed passes; local-data seed-42: 60 unique, 20 per group. Integration is PR 3 |
| AC-19 | Partial | test_contract_schemas.py passes (7 contracts incl. 30a in order, names and types; non-null columns; naming rule; Bronze inline schemas). Deployed columns are PR 3 |
| AC-20 | Partial | test_ac20_dst_change_days_have_48_utc_readings passes (both DST days); integration is PR 3 |
| AC-21 | Partial | test_ac21_* pass; local-data complete-day share inside 98.5 to 99.5 percent. Integration is PR 3 |
| AC-22 | Partial | test_ac22_* pass (1,488 / 1,344 / 29,184, pandas recomputation); local-data 1,200 rows, unique key. Integration is PR 3 |
| AC-23 | Pass | test_ac23_gap_count_per_month passes (2, 1, 0) |
| AC-24 | Partial | test_ac24_appending_later_months_keeps_earlier_rows passes; integration is PR 3 |
| AC-25 | Partial | test_ac25_* pass (summary SQL run locally). Local-data: Gold coverage within 0.001 of the manifest for all 60 households (I-04 closed). Integration is PR 3 |
| AC-26 | Partial | Spike 04: the pipeline publishes `CREATE VIEW` to `gold` (DA-02 Pass). Other tests are PR 2a/2b/3 |
| AC-27 | Partial | test_ac27_rebuild_is_identical_for_any_input_order passes (Silver, quarantine, daily, monthly checksums over shuffles and 1, 3, 7 partitions); integration is PR 3 |
| AC-28 | Not started | PR 2b/3. Spike 00: A-09 Pass. DA-06 Fail: the evidence uses the three-step first deploy (DESIGN Change Log 2026-10-16) |
| AC-29 | Partial | tests/test_secrets_hygiene.py (8) and bronze secret tests pass; `pre-commit run --all-files` passes. Bundle test is PR 2b. The broker-host scan runs only when KAFKA_* is exported |
| AC-30 | Partial | Spike 04: one update over 1,680,000 synthetic rows completed in 63 s (budget 2700 s). Bundle and integration tests are PR 2b/3 |
| AC-31 | Partial | Producer sets `produced_at` as the UTC wall clock in ISO-8601 (test_ac31_produced_at_is_utc_wall_clock_not_event_time passes). End-to-end check is PR 3 |
| AC-32 | Partial | test_ac32_check_specs_reports_no_errors passes. test_ac32_runtime_adr_records_every_spike_outcome passes: every row of ADR 0001 has a result |
| AC-33 | Pass | test_ac33_* pass (dense months, empty household, orphan) |
| AC-34 | Partial | test_ac34_* pass; local-data seed-42: 60 rows counted under QR-03 and QR-04, 60 quarantine rows with failed_rules [QR-03, QR-04]. Integration is PR 3 |
| AC-35 | Partial | test_ac35_orphan_false_known_household_true passes; local-data seed-42 all true. Integration is PR 3 |

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` | 33 files already formatted |
| Tests | `.venv/bin/pytest` | 52 passed, 1 failed, 6 deselected. The failure is test_ac32_runtime_adr_records_every_spike_outcome (spike results Pending, by design) |
| Local-data tests | `.venv/bin/pytest -m local_data` | 6 passed, 53 deselected (about 77 s) |
| Spec check | `.venv/bin/python scripts/check_specs.py` | 17 document(s) checked, 0 error(s), 0 warning(s) |
| A-08 | `.venv/bin/python spikes/local/a08_offgrid_null_cooccurrence.py` | PASS (see AC-11) |
| Sample build | `.venv/bin/python scripts/prepare_sample.py build --out data/sample/seed42` | 60 households, 1,432,405 historical rows in 17 files, 247,569 stream rows; data files and household CSV byte-identical to the pinned references |
| Producer dry run | `python -m smart_meter_peak_prediction.producer --dry-run --input data/sample/seed42/stream/readings_stream.csv` | 247,569 JSON lines |
| Spike syntax | `python -m py_compile spikes/databricks/**/*.py` | OK |
| DA-06 | Throwaway bundle (pipeline in `smart_meter_dev.silver`), `databricks bundle deploy -t dev -p dev` with the catalog absent | Fail: `cannot create pipeline: Catalog 'smart_meter_dev' does not exist.`; files synced first; destroyed afterwards |
| Spike 00 | `databricks jobs submit` (serverless notebook task) | SUCCESS; `smart_meter_dev` with `bronze`, `silver`, `gold`, `ml` and Volumes `landing`, `checkpoints` listed |
| Spike 01 | `databricks jobs submit`, two seed-42 files in `landing/_spike/readings` | SUCCESS: expected 143,633, run 1 143,633, run 2 143,633, rescued 0, null metadata 0 |
| Producer | `.venv/bin/python -m smart_meter_peak_prediction.producer --limit 1000` (credentials from `.env`) | Published 1,000 events, after topic creation |
| Spike 02 | `databricks jobs submit` | SUCCESS: rows 1000, null metadata 0, duplicate offsets 0, 59 s; `processingTime` rejected (`INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED`) |
| Spike 03 | `databricks jobs submit`, Aiven off | Task failed after 61 s with `ConfigException: No resolvable bootstrap urls`; checkpoint and table inspected directly: unchanged |
| Spike 04 | `.venv/bin/python spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py --profile dev --warehouse-id <id>` | Exit 1 (one FAIL): A-10 105 s; DA-03 31 rows; DA-01 counters (1, 1, 1) on update 1, none on update 2; DA-02, DA-07, DA-08 pass; AC-15 abort; DA-10 63 s; pipeline deleted |
| PR 2a | `JAVA_HOME=~/.local/jdk17 .venv/bin/pytest` (pyspark 4.0.4 installed in .venv) | 158 passed, 13 deselected |
| PR 2a lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | All checks passed; files formatted |
| PR 2a local data | `.venv/bin/pytest -m local_data` | 13 passed (6 PR 1, 7 seed-42 pipeline), 158 deselected |
| PR 2a specs | `.venv/bin/python scripts/check_specs.py` | 19 document(s) checked, 0 error(s), 0 warning(s) |
| PR 2a hooks | `.venv/bin/pre-commit run --all-files` | all hooks passed |
| PR 2a review | code-reviewer subagent | 0 High, 4 Medium, 9 Low (see Issues) |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| Plan key | "Whenever `blocks` is present in the plan" and "chosen blocks copied from the spike plan" (spike key is `groups`) | `config/sample_plan.json` uses `blocks`; the loader also accepts `groups` | Matches the DESIGN wording; the frozen spike plan stays loadable | No (not needed) |
| ADR 0001 table | Lists no A-08 row | Added an A-08 row with the local result (Pass) | The DESIGN asks to record A-08 where the assumption lives; no spike outcome of Databricks touched | No |
| Spike 04 helper package | Spike imports a package through `sys.path` (DA-08) | `run_spike.py` embeds the helper module as a string and uploads it, instead of an extra repo file | Keeps to the manifest file list | No |
| Failing test in a PR 1 build | Test Strategy requires ADR 0001 results for A-02 to A-10 | The test exists and fails until the spikes are run and recorded | Not skipping tests; the failure is the PR 1 gate | No |
| Spikes 01 to 03 | Results printed only | Each ends with `dbutils.notebook.exit(str(result))` | The Jobs API does not return notebook prints, so the counts could not be recorded otherwise | No (spike code) |
| `pyspark` | Dev extra | Declared, not installed in `.venv` | PR 1 needs no Spark or Java | No |
| Producer CLI | `--dry-run` | Also `--input`, `--topic`, `--speed`, `--limit` | Needed to run spikes with a few events; `--limit` is not required elsewhere | No |
| `element_at(failed_rules, 1)` | `rule_name = element_at(...)` | `try_element_at` | ANSI mode raises on an empty array; found by the first local run | No (mechanical) |
| Cross-path duplicate in AC-17 test | "A cross-path pair with different `_ingested_at`" | Pairs across two files and across two Kafka offsets | A files row and a Kafka row with one key cannot both pass QR-06 | No |
| Extra files | Manifest lists 20 PR 2a files | Also tests/test_config.py, tests/test_rules_metrics.py, tests/local_data/test_pipeline_seed42.py, a `pyproject.toml` ruff S608 ignore | Catalog checks and real-sample figures without Databricks | No |
| Hygiene scan input | `git ls-files` | `git ls-files --cached --others --exclude-standard`, environment values only (never reads `.env`) | Catches new files before commit | No |
| Dedup window | Partition `(household_id, reading_ts)` | Partition also by `is_candidate` | Same ranks for candidates; validated in spike 04 | No |
| Daily total | `sum(energy_kwh)` | Exact decimal(38,10) sum cast to double | Order-independent total for AC-27 (review finding) | No |
| Test time zone | - | conftest pins process TZ to UTC | Spark returns naive datetimes in the process zone | No |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | DEFINE row A-08 was thought to be `Pending` | Closed | The DEFINE already records A-08 as validated (Change Log 2026-10-15) |
| I-02 | DEFINE inline schema lists the sample reading files as `household_id, reading_ts, energy_kwh`; the code and pinned checksums use the source header | Low | One-line `/iterate` (already noted in the DESIGN Self-Review) |
| I-03 | `tests/test_runtime_adr.py` failed until ADR 0001 was filled | Closed | All spike results recorded 2026-10-16 |
| I-04 | `coverage_study_period` in the manifest vs Gold observed readings | Closed | Local-data seed-42 test: all 60 households within 0.001 |
| I-05 | Spike 04 uses SDK and Lakeflow calls that were not exercised (`private=True`, `FileLibrary`, `EventLogSpec`, `workspace.upload` with `RAW`) | Closed | Ran on 2026-10-16 without code changes |
| I-07 | Code-reviewer self-review of PR 1: 1 High (wrong `/Workspace` prefix for `spike.src_path` in run_spike.py) and several Medium/Low items fixed (stale-file cleanup in `build_sample`, DA-08/DA-01 assertions, event-log cleanup, upload wrapper, producer row validation, Dockerfile `--user` note). Full gate before Complete still pending | Low | Re-run the code-reviewer before Complete |
| I-06 | Dockerfile not built | Low | User builds it (command below) |
| I-08 | DA-06 failed: deploy cannot create the pipeline before the catalog exists | Closed | `/iterate` on DESIGN and ADR 0003 (2026-10-16): deploy, run `setup_catalog.py`, deploy. `notebooks/setup_catalog.py` (entry 43) must also run by hand, with default catalog and schema values |
| I-09 | DA-01 partial: an update with no new input writes no expectation metrics | Closed | `/iterate` on DESIGN and ADR 0004 (2026-10-16): evaluation table published, counts are table totals in `metrics.py`, event log kept for observability only |
| I-11 | DEFINE worded AC-12, NFR-07, SF-01 and QR-09 as per-update counts within 5 minutes of the update | Closed | `/iterate` on DEFINE (2026-10-16): FR-09, NFR-07, SF-01, QR-09, AC-09, AC-12, AC-16, AC-17, AC-34 restated as table totals; OD-02 and OD-06 resolved |
| I-13 | Topic `meter-readings` did not exist and Aiven does not auto-create topics | Open for PR 3 | PR 2a has no runbook. Topic created 2026-10-16 through the Kafka admin API with 2 partitions as in the contract (broker default 3 replicas). The runbook (entry 59, PR 3) must include topic creation |
| I-14 | Spike 03: a stream failure surfaces at notebook-cell level ("Some streams terminated before this command could finish!") and is not caught by `try` around `awaitTermination` | Medium | The Kafka task in PR 2a must not rely on catching the exception in Python; let the task fail and use task `timeout_seconds` and retries. PR 2a: `bronze.run_available_now` has no try/except, guarded by an AST test. The notebooks (PR 2b) must follow it |
| I-12 | ADR 0005 still called the evaluation MV private and mentioned a per-update duplicate count | Closed | ADR 0005 updated 2026-10-16: published evaluation MV, `is_duplicate` table total, event log for observability |
| I-10 | The workspace holds an unrelated pipeline (`elt-uber-eats-analytics`, idle) | Low | Spike 04 ran alongside it. Check the one-pipeline-per-type limit again when the bundle pipeline is deployed |
| I-15 | A replayed invalid Kafka message is a new Bronze row that fails the same rule and is quarantined again; only valid rows are deduplicated (QR-09). AC-09 holds for seed 42 because the stream has no invalid message | Low | Documented by a test; decide in a later `/iterate` whether replays of invalid rows should be deduplicated |
| I-16 | Code review PR 2a, Medium: Gold total order-dependence (fixed, decimal sum), ANSI not forced in conftest (fixed), unknown pipeline-config keys silently ignored (fixed, ValueError), vacuous totals test (renamed) | Closed | - |
| I-17 | Code review PR 2a, Low, open: session UTC not asserted in the library (PR 2b pipeline asserts it, DA-07); `trim` removes spaces only; `study_*`/cutoff must be midnight dates; event-log SQL is Databricks-only; summary `CREATE VIEW` statement untested until PR 2b; broker-host scan needs KAFKA_* exported; `auto_loader_reader` and `kafka_reader` untested until integration | Low | PR 2b/3 |

---

## Pending on the user

Done on 2026-10-16: auth (`dev` profile), `.env`, secret scope, Aiven SASL mechanism, topic, sample upload, DA-06 test and spikes 00 to 04.

1. Power the Aiven service back on when the Kafka path is needed again.
2. Build the producer image: `docker build -f docker/producer/Dockerfile -t smart-meter-producer .`

---

## Self-Review

### PR 2a

- **Weak points:** Lakeflow semantics (MV refresh, `expect_*` on the published evaluation MV, `CREATE VIEW` in the pipeline) are proven only by spike 04 and by the harness; `auto_loader_reader`, `kafka_reader` and the summary `CREATE VIEW` statement have not run. Local Spark 4.0.4 with ANSI forced is close to serverless but not identical.
- **Risks:** AC-27 depends on all Gold aggregates being order independent (daily total fixed; monthly uses counts and min/max only). Pipeline refresh time of the full recompute is only known from spike 04 (63 s). Replayed invalid messages are not deduplicated (I-15).
- **What I would do differently:** Build the harness against the real `dlt` wiring earlier, and add a settings validation step (dates, midnight, ordering) in `Settings.__post_init__`.
- **Next improvement:** PR 2b (notebooks, pipeline wiring with `rules.py`, bundle), then run it on the workspace and collect the pending integration evidence.

### PR 1

- **Weak points:** The producer has only published 1,000 events; a full replay of 247,569 has not run. The DA-01 cause (refresh skipped on an update with no new input) is inferred: spike 04 drops its event log on cleanup, so the update 2 events were not inspected.
- **Risks:** The DA-01 change alters count semantics (table totals instead of per-update counts); DEFINE and DESIGN are aligned, but PR 2a must implement the new contract first. Aiven powers off after inactivity, so integration runs need it on.
- **What I would do differently:** Run the spike 04 pipeline code in a dry check against a fake `dlt` before handing it over, and give the ADR test a distinct state for "spike not yet run" so CI can stay green on the PR 1 branch without skipping.
- **Next improvement:** Start PR 2a.

---

## Next Step

`/build` PR 2b. (`/ship METER_INGESTION` only after PR 3.)
