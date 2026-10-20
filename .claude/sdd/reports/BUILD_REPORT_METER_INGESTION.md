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

**PR 2a (entries 24 to 42 and 30a) was built on 2026-10-19** on branch `feat/meter-ingestion-pr2a`: library modules, summary view SQL, contract 30a, local pipeline harness and unit tests, all verified locally (Spark 4.0.4, Java 17). Nothing was run against Databricks or Kafka. PR 2a status: **Complete** (local scope; live evidence pending, see below).

**PR 2b (entries 43 to 52) was built on 2026-10-19** on branch `feat/meter-ingestion-pr2b` (off `feat/meter-ingestion-pr2a`): notebooks, pipeline wiring, bundle resources and their tests, all verified locally; `databricks bundle validate -t dev -p dev` reports `Validation OK!`. Nothing was deployed or run on Databricks, and Kafka was not touched. PR 2b status: **Complete** (local scope; live evidence pending).

**PR 3 (entries 53 to 60) was built on 2026-10-19** on branch `feat/meter-ingestion-pr3` (off `feat/meter-ingestion-pr2b`): the integration tests, the runbook and the README, all verified locally; `databricks bundle validate -t dev -p dev` reports `Validation OK!`. Nothing was deployed, run or submitted on Databricks, Kafka was not touched, and the integration tests were collected but **not run**. PR 3 status: **Complete** (local scope; live evidence pending).

**Feature status.** Every manifest entry (1 to 60 and 30a) is built and verified locally. The header status stays `In Progress` on purpose: the build rules allow `Complete` only when every AC is `Pass` or explicitly accepted by the user, and the platform evidence for 25 ACs (all with an integration test) is `Not run`. The exact steps are under *Pending on the user*; run them before `/ship`, or accept the pending ACs explicitly.

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

PR 3 (entries 53 to 60): see *PR 3 files* below.

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

### PR 2b files (state: done, verified locally; live behaviour pending)

| # | File | Verification |
|---|---|---|
| 43 | notebooks/setup_catalog.py | Statements from `catalog_setup.setup_statements` (tests/test_catalog_setup.py); widgets default to `Settings()` so the manual DA-06 run needs no parameters; UTC set and asserted. Not run on the workspace |
| 44 | notebooks/ingest_files.py | tests/test_bundle_config.py (no try/except, library writer only, widgets match job parameters). Not run |
| 45 | notebooks/ingest_kafka.py | Same, plus a taint-tracked no-print test and the four `dbutils.secrets.get` calls (AC-29). Not run, Kafka untouched |
| 46 | pipelines/meter_pipeline.py | tests/test_pipeline_wiring.py: a fake `dlt` records datasets and expectations and they are compared with `rules.py`; every dataset function also runs in order on local Spark and matches the harness |
| 47 | resources/jobs.yml | Deleted (template job). The placeholder `notebooks/hello.py` was deleted too (see Deviations) |
| 48 | resources/smart_meter_silver_gold.pipeline.yml | test_bundle_config.py; `bundle validate` OK |
| 49 | databricks.yml | test_bundle_config.py; `bundle validate` OK |
| 50 | resources/smart_meter_ingestion.job.yml | test_bundle_config.py; `bundle validate` OK |
| 51 | tests/test_pipeline_wiring.py | 9 tests |
| 52 | tests/test_bundle_config.py | 17 test functions (19 cases) |
| extra | src/.../catalog_setup.py, tests/test_catalog_setup.py (6 cases), pyproject.toml (F821 for `pipelines`) | see Deviations |

### PR 3 files (state: done, verified locally; nothing run on the platform)

| # | File | Verification |
|---|---|---|
| 53 | tests/integration/conftest.py | ruff; collected by pytest; SDK imported lazily (no `databricks-sdk` needed to collect). Fixtures: workspace client (CLI profile or `DATABRICKS_*` env), SQL through the Statement Execution API with a UTC time-zone assertion, settings overrides (`SMART_METER_<FIELD>`), manifests, contracts, order-independent checksums, evidence snapshots in `out/evidence/`, job and pipeline lookup with the development prefix stripped, a `run_tasks` helper (`run_now(only=...)`), and the shared AC-12 totals check. Not run |
| 54 | tests/integration/test_bronze_ingestion.py | 7 tests (AC-05, AC-06, AC-07, AC-08, AC-10 x2, AC-29 redaction). Collected, not run |
| 55 | tests/integration/test_silver_tables.py | 9 test cases (AC-11, AC-12, AC-13, AC-14, AC-18, AC-19, AC-20 x2 DST days, AC-34). Collected, not run |
| 56 | tests/integration/test_gold_tables.py | 8 tests (AC-21, AC-22, AC-25, AC-26 x3 incl. the I-18 pair, AC-31, AC-35). Collected, not run |
| 57 | tests/integration/test_reprocessing.py | 7 tests (AC-09 pair, AC-24 pair, AC-27 pair, AC-12 after full refresh). Collected, not run |
| 58 | tests/integration/test_deployment.py | 2 tests (AC-28, AC-30). Collected, not run |
| 59 | docs/runbooks/meter_ingestion.md | CLI flags checked with `--help` (read-only): `bundle run --only/--full-refresh-all`, `fs cp -r --overwrite`, `fs rm -r`, `secrets put-secret` (prompt and stdin), `bundle validate -o json` (`workspace.file_path`). Commands themselves not executed. Covers I-13 (topic creation, Aiven dependency), DA-06 three-step first deploy, `bundle run`, evidence order, broker outage, full refresh, Bronze reset and schema change, redaction check, update from an empty Gold schema |
| 60 | README.md | Architecture, quick start, layout, limitations; links resolve (`docs/runbooks`, `docs/adr`, `.claude/sdd`) |
| extra | tests/test_integration_layout.py (6 tests), pyproject.toml (S608 ignore for `tests/integration`) | see Deviations |

Collected by `pytest --collect-only -m integration -o addopts= tests/integration`: 33 tests. The default `pytest` deselects them: `198 passed, 46 deselected` (33 integration and 13 local_data).

---

## Acceptance Criteria Evidence

Final status after PR 3. **Local** is the unit, local-data, wiring and bundle evidence of PR 1 to PR 3 (real output, see the PR 1 to PR 3 rows of the Verification Log and the per-PR evidence in git history). **Live** is the platform evidence: `Not run` means the integration test exists, is collected, and was not executed (no deployment, Aiven off). Steps A to G are the evidence steps of `docs/runbooks/meter_ingestion.md` ("Evidence order for the integration tests"); `pytest -m integration` needs `DATABRICKS_CONFIG_PROFILE=dev`.

| AC | Local | Live | Integration test (file `tests/integration/`) and step |
|---|---|---|---|
| AC-01 | Pass | n/a | none: `test_sampling.py`, `local_data/test_sample_seed42.py` (byte-identical, checksums equal the pinned manifest) |
| AC-02 | Pass | n/a | none: unit and local-data (60 households, 20 per group, exclusions equal the pinned list) |
| AC-03 | Pass | n/a | none: unit and local-data (1,432,405 historical, 247,569 stream rows) |
| AC-04 | Pass | n/a | none: unit, local-data and `test_ac04_bundle_cutoff_default_equals_sample_plan` |
| AC-05 | Pass | Pass (run after step C, 2026-10-20) | `test_bronze_ingestion.py::test_ac05_bronze_file_counts_match_manifest`, step B |
| AC-06 | Pass (idempotent writer, unit) | Pass (run after step C, 2026-10-20) | `test_bronze_ingestion.py::test_ac06_rerun_file_ingestion_adds_no_rows`, step B (reruns `ingest_files`) |
| AC-07 | Pass | Pass (step C, 2026-10-20) | `test_bronze_ingestion.py::test_ac07_kafka_bronze_count_uniqueness_and_payload_parse`, step C (needs Aiven on) |
| AC-08 | Pass (unit) | Pass (step C, 2026-10-20) | `test_bronze_ingestion.py::test_ac08_rerun_kafka_ingestion_adds_no_rows`, step C (needs Aiven on) |
| AC-09 | Pass (rebuilt 2026-10-19: unit `test_ac09_replayed_messages_counted_as_duplicates_and_silver_unchanged`, `test_ac09_replayed_invalid_messages_not_quarantined_again`, `test_ac09_dedup_key_is_per_path_and_offset_independent`, `test_ac09_replayed_partially_parseable_invalid_payload_not_quarantined_again` (I-22); local data `test_ac09_seed42_quarantine_has_distinct_dedup_keys_and_no_duplicates`) | Pass (step F, 2026-10-20) | `test_reprocessing.py::test_ac09_before_replay_snapshot`, `::test_ac09_after_replay_silver_unchanged` (now also compares per-rule totals and `quarantine_duplicates`), step F (second replay) |
| AC-10 | Pass (options, bundle, AST guard) | Pass (step D, 2026-10-20; recovery needed a Kafka reset, I-23) | `test_bronze_ingestion.py::test_ac10_before_outage_snapshot`, `::test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged`, step D (Aiven off). Spike 03 evidence stands |
| AC-11 | Pass (rebuilt 2026-10-19: unit `test_ac11_every_bronze_row_classified_exactly_once` with the replayed QR-07 row and the fifth class, 0 unclassified, 0 double-classified; `test_ac11_source_ref_unique_per_bronze_row`; seed 42 local data: 1,679,974 rows, 60 quarantined, 0 outside the period, 0 duplicates, 0 quarantine duplicates, 1,679,914 in Silver) | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac11_reconciliation_classifies_every_bronze_row` (now asserts `is_quarantine_duplicate = 0`), step C |
| AC-12 | Pass (rebuilt 2026-10-19: unit `test_ac12_rule_counts_equal_quarantine_failed_rules_per_update` over two updates, with the replayed invalid row; `test_ac12_rule_counts_sql_covers_every_drop_rule_scope_and_duplicates`; wiring `test_ac12_*`) | Pass (steps C and G, 2026-10-20) | `test_silver_tables.py::test_ac12_update_rule_counts_match_quarantine_rows` (helper now checks `_dedup_key` unique in the quarantine and `qr_09` = valid duplicates + `quarantine_duplicates`) (step C), `test_reprocessing.py::test_ac12_totals_consistent_after_full_refresh` (step G) |
| AC-13 | Pass | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac13_silver_invariants`, step C |
| AC-14 | Pass | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac14_cutoff_rows_once_with_ingestion_path`, step C |
| AC-15 | Pass (unit x7 groups, wired fail rule, spike 04 on the platform) | n/a | none: the DESIGN assigns the platform proof to spike 04 (`expect_or_fail` aborts with 0 rows committed) |
| AC-16 | Pass | n/a | none in the DESIGN (fixture AC) |
| AC-17 | Pass (re-checked against the new wording 2026-10-19: `test_ac17_earlier_ingested_at_wins_and_tie_uses_smaller_source_ref` has the files pair with the earlier row on the larger `_source_ref` and the Kafka tie pair; `test_ac17_rerun_keeps_same_winners` now also runs the pair fixture again, reversed and with 5 partitions: same winners, duplicate total 2) | n/a | none in the DESIGN (fixture AC) |
| AC-18 | Pass | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac18_silver_households_seed42`, step C |
| AC-19 | Pass | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac19_deployed_columns_match_contracts`, step C |
| AC-20 | Pass | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac20_dst_days_have_48_readings` (2 cases), step C |
| AC-21 | Pass | Pass (step C, 2026-10-20) | `test_gold_tables.py::test_ac21_daily_consumption_matches_silver_recomputation`, step C |
| AC-22 | Pass | Pass (step C, 2026-10-20) | `test_gold_tables.py::test_ac22_monthly_quality_matches_independent_recomputation`, step C |
| AC-23 | Pass | n/a | none in the DESIGN (fixture AC) |
| AC-24 | Pass | Pass (before snapshot step B, after test step C, 2026-10-20) | `test_reprocessing.py::test_ac24_before_kafka_snapshot` (step B), `::test_ac24_after_kafka_months_up_to_november_unchanged` (step C) |
| AC-25 | Pass | Pass (step C, 2026-10-20) | `test_gold_tables.py::test_ac25_summary_matches_monthly_and_manifest`, step C (needs `data/sample/seed42/manifest.json`) |
| AC-26 | Pass (wiring, bundle, spike 04 `CREATE VIEW`) | Pass (I-18 pair steps A and B, metadata test step C, 2026-10-20) | `test_gold_tables.py::test_ac26_pipeline_and_table_metadata` (step C); I-18 pair `test_ac26_i18_before_first_update_gold_schema_is_empty` (step A) and `test_ac26_i18_after_first_update_summary_view_exists_and_update_completed` (step B) |
| AC-27 | Pass | Pass (step G, 2026-10-20) | `test_reprocessing.py::test_ac27_before_full_refresh_snapshot`, `::test_ac27_after_full_refresh_checksums_equal`, step G |
| AC-28 | Pass (bundle unit tests, `bundle validate` OK) | Partial: layout test Pass (step C, 2026-10-20); first-deploy exit codes not recorded | `test_deployment.py::test_ac28_deployed_job_pipeline_and_catalog_layout`, step C, plus the exit codes of the three-step first deploy (manual, runbook section 4) |
| AC-29 | Pass (unit, hygiene, `pre-commit run --all-files`) | Not run (redaction of a failing stream's error, I-20) | `test_bronze_ingestion.py::test_ac29_failed_stream_error_does_not_leak_credentials`, runbook "Stream error redaction check" |
| AC-30 | Pass (job timeout test, spike 04: 63 s for 1.68 M rows) | Pass (step C run 682175635266718, 395 s; step E run 1088438823635937, 381 s; 2026-10-20) | `test_deployment.py::test_ac30_daily_job_run_within_60_minutes`, steps C and E |
| AC-31 | Pass (unit: UTC wall clock) | Pass (step C, 2026-10-20) | `test_gold_tables.py::test_ac31_produced_reading_reaches_silver_and_gold_within_24h`, step C |
| AC-32 | Pass | n/a | `test_runtime_adr.py`, `scripts/check_specs.py` (0 errors) |
| AC-33 | Pass | n/a | none in the DESIGN (fixture AC) |
| AC-34 | Pass | Pass (step C, 2026-10-20) | `test_silver_tables.py::test_ac34_seed42_offgrid_null_rows_counted_under_both_rules`, step C |
| AC-35 | Pass | Pass (step C, 2026-10-20) | `test_gold_tables.py::test_ac35_seed42_has_household_record_all_true`, step C |

Summary: 35 ACs. Local result is `Pass` for all 35. The `/iterate` of 2026-10-19 changed the wording of AC-09, AC-11, AC-12 and AC-17; the rebuild (I-15) is done and their local evidence is `Pass` for the new wording (see *Iterate rebuild 2026-10-19*). 25 ACs also need live evidence. After steps C to G (2026-10-20): 23 are `Pass` live (AC-05 to AC-14, AC-18 to AC-22, AC-24 to AC-27, AC-30, AC-31, AC-34, AC-35); 1 is `Partial` (AC-28 the first-deploy exit codes); 1 is `Not run` (AC-29 the redaction check). The other 10 have no live test in the DESIGN: AC-01 to AC-04, AC-15 (spike 04), AC-16, AC-17, AC-23, AC-32, AC-33.

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` | 33 files already formatted |
| Tests | `.venv/bin/pytest` | 52 passed, 1 failed, 6 deselected. The failure is test_ac32_runtime_adr_records_every_spike_outcome (spike results Pending, by design) |
| Local-data tests | `.venv/bin/pytest -m local_data` | 6 passed, 53 deselected (about 77 s) |
| Spec check | `.venv/bin/python scripts/check_specs.py` | 17 document(s) checked, 0 error(s), 0 warning(s) |
| I-22 rebuild | `ruff check .`, `ruff format --check .`, `pre-commit run --all-files`, `pytest`, `pytest -m local_data`, `check_specs.py` | all passed; 202 passed (47 deselected); local_data 14 passed, seed-42 still 60 quarantined, 60 distinct keys, 0 quarantine duplicates; check_specs 19 documents, 0 errors |
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
| PR 2b tests | `JAVA_HOME=~/.local/jdk17 .venv/bin/pytest` | 192 passed, 13 deselected (158 from PR 2a plus 34 new) |
| PR 2b lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | All checks passed; files formatted |
| PR 2b specs | `.venv/bin/python scripts/check_specs.py` | 19 document(s) checked, 0 error(s), 0 warning(s) |
| PR 2b hooks | `.venv/bin/pre-commit run --all-files` | all hooks passed |
| PR 2b bundle | `databricks bundle validate -t dev -p dev` (read-only) | `Validation OK!` (Name smart-meter-peak-prediction, Target dev). No deploy, no job run |
| PR 2b review | code-reviewer subagent | 0 High, 4 Medium, 9 Low (see Issues); Medium 2 to 4 and six Low fixed, Medium 1 left for PR 3 |
| PR 3 lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | All checks passed; 69 files already formatted |
| PR 3 tests | `JAVA_HOME=~/.local/jdk17 .venv/bin/pytest` | 198 passed, 46 deselected (192 + 6 layout tests; deselected: 33 integration, 13 local_data) |
| PR 3 collection | `.venv/bin/pytest --collect-only -q -m integration -o addopts= tests/integration` | 33 tests collected (5 modules); the default run lists none of them and reports them as deselected (test_integration_layout.py checks both in subprocesses) |
| PR 3 specs | `.venv/bin/python scripts/check_specs.py` | 19 document(s) checked, 0 error(s), 0 warning(s) |
| PR 3 hooks | `.venv/bin/pre-commit run --all-files` | all 9 hooks passed |
| PR 3 bundle | `databricks bundle validate -t dev -p dev` (read-only) | `Validation OK!` (User and Path shown, not repeated here). No deploy, no job run, no Kafka |
| PR 3 review | code-reviewer subagent | 2 High, 6 Medium, 9 Low. Both High fixed (job fixture lists with `expand_tasks`; AC-30 and AC-31 select only successful full four-task runs, because the AC-06 and AC-08 reruns are partial `only=` runs). Fixed Medium: UTC accepts `Etc/UTC`, AC-10 accepts `TIMEDOUT`, AC-28 also checks Volumes, Bronze tables and the raw name, README no longer shows a whole-directory command, runbook wording and producer env file (no Databricks keys), AC-25 manifest note. Fixed Low: `payload_ok IS NOT TRUE`, vacuous asserts, stray parentheses. Not changed (Low): tautological QR-10 and expected_readings comparisons, AC-18 literals, DESIGN-id parsing in the layout test, AC-26 wording (DESIGN fix at `/ship`). Medium AC-26 wording is the recorded deviation |
| PR 3 integration | not run | by instruction: no workspace calls, Aiven off. Commands under *Pending on the user* |
| Rebuild lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` (ruff 0.17.0) | All checks passed; 69 files already formatted |
| Rebuild tests | `JAVA_HOME=~/.local/jdk17 .venv/bin/pytest` | 201 passed, 47 deselected (33 integration, 14 local_data); includes the 6 `test_contract_schemas.py` tests that failed before the rebuild |
| Rebuild local data | `.venv/bin/pytest -m local_data` | 14 passed (about 158 s). Seed 42: 1,679,974 evaluated rows, 60 quarantined with 60 distinct `_dedup_key` (all `files:key:`), 0 quarantine duplicates, 0 duplicates, 0 outside the period, 1,679,914 in Silver, 0 unclassified |
| Rebuild specs | `.venv/bin/python scripts/check_specs.py` | 19 document(s) checked, 0 error(s), 0 warning(s) |
| Rebuild hooks | `pre-commit run --all-files` (ruff 0.6.9 pinned) | all 9 hooks passed; the hook rewrote one list comprehension to a generator, which ruff 0.17 also accepts |
| Rebuild review | code-reviewer subagent | 0 High, 4 Medium, 3 Low. Fixed: reconciliation classed a dropped repeat that shares `(household_id, reading_ts)` with a Silver row as a valid duplicate (now keyed on `failed_rules`), new tests for that case, the quarantine tie-break and a dropped pair in the AC-27 fixture. Closed by `/iterate` and rebuild (I-22): a payload that fails QR-07 but has a readable `household_id` and `reading_ts` is now keyed on them, so a replay with a new `produced_at` is not quarantined again |
| Rebuild integration | not run | by instruction; queries for AC-09, AC-11, AC-12 updated, collection checked by `test_integration_layout.py` |
| Live step C replay | producer image, `--speed 0`, topic `meter-readings` recreated empty with 2 partitions | `published 247569 event(s)`, exit 0; watermarks 106,791 + 140,778 = 247,569 (`stream_rows`). A first replay published nothing (no output was kept); a 10-event probe showed the producer works; `delete_records` hung on the Aiven free tier, so the topic was recreated and the empty `bronze.kafka_meter_readings` and its checkpoint were removed |
| Live step C job | `databricks bundle run -t dev -p dev smart_meter_ingestion` | run 682175635266718, TERMINATED SUCCESS, 395 s (setup_catalog 46 s, ingest_files 25 s, ingest_kafka 166 s, refresh_silver_gold 182 s) |
| Live step C tests | `pytest -m integration` with the step C selection | 21 passed. First attempt: the session `sql` fixture timed out on `SELECT current_timezone()` (statement PENDING over 900 s, warehouse; not repeated) and AC-30 failed twice on fixture bugs, both fixed in `tests/integration/conftest.py::full_runs`: `limit=50` rejected by the Jobs API (max 26, now 25, the SDK pages) and partial `only=` runs counted as full runs (they list every task, skipped tasks end `DISABLED`; now every task must end `SUCCESS`) |
| Live step D | `test_ac10_before_outage_snapshot` (247,569 rows, checkpoint batch `0`), Aiven powered off, job run 886556402748181, then `test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged` | Both passed. `ingest_kafka` failed in 17 s with `No resolvable bootstrap urls given in bootstrap.servers` (the powered-off service stops resolving), reported as `INTERNAL_ERROR`; it ran twice (attempts 0 and 1) despite `max_retries: 0`; `refresh_silver_gold` SKIPPED (`UPSTREAM_FAILED`). Bronze and checkpoint unchanged |
| Live step E | Aiven powered on, job run 581319953230342 | Failed as `failOnDataLoss` requires: the power-off had emptied the topic (both partitions `high=0`), `Partition meter-readings-1 offset was changed from 140778 to 0`; again two attempts. Bronze unchanged (247,569 rows, no new commit), but the run left an uncommitted `offsets/1` targeting `{0: 0, 1: 0}`, so every later run would fail the same way (I-23) |
| Live step E recovery | user dropped `bronze.kafka_meter_readings` (guarded on 247,569 rows) and its checkpoint (Catalog Explorer; `databricks fs rm -r` left the folder in place twice), full replay (`published 247569 event(s)`, watermarks 106,791 + 140,778), job run 1088438823635937 | TERMINATED SUCCESS, 381 s (`ingest_kafka` 162 s, `refresh_silver_gold` 172 s); `test_ac07_*` and `test_ac30_*` passed |
| Live step F | `test_ac09_before_replay_snapshot`, second full replay (`published 247569 event(s)`; watermarks 213,582 + 281,556 = 495,138), job run 610579408479777, `test_ac09_after_replay_silver_unchanged` | Both passed. Job TERMINATED SUCCESS in 372 s, one attempt per task (`ingest_kafka` 149 s, `refresh_silver_gold` 203 s). Bronze Kafka went from 247,569 to 495,138 rows (append-only); Silver (1,679,914 rows), the quarantine (60 rows) and their checksums unchanged; snapshot per-rule totals were QR-03 60, QR-04 60, others 0, QR-09 0, quarantine duplicates 0 |
| Live step G | `test_ac27_before_full_refresh_snapshot`, `databricks bundle run -t dev -p dev smart_meter_silver_gold --full-refresh-all` (update 37d7c798, COMPLETED, `full_refresh: true`), `test_ac27_after_full_refresh_checksums_equal`, `test_ac12_totals_consistent_after_full_refresh` | All passed: Silver and Gold checksums after the full refresh equal the snapshot; per-rule totals stay consistent with the quarantine rows |

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
| Cross-path duplicate in AC-17 test | "A cross-path pair with different `_ingested_at`" | Pairs across two files and across two Kafka offsets | A files row and a Kafka row with one key cannot both pass QR-06 | Closed: the build now matches the spec. DEFINE AC-17 and the DESIGN test text were reworded through `/iterate` 2026-10-19 (files pair plus Kafka pair; I-21). One adjustment may remain in the test: the files pair must have the earlier `_ingested_at` on the larger `_source_ref`, and the Kafka pair must tie on `_ingested_at` |
| Extra files | Manifest lists 20 PR 2a files | Also tests/test_config.py, tests/test_rules_metrics.py, tests/local_data/test_pipeline_seed42.py, a `pyproject.toml` ruff S608 ignore | Catalog checks and real-sample figures without Databricks | No |
| Hygiene scan input | `git ls-files` | `git ls-files --cached --others --exclude-standard`, environment values only (never reads `.env`) | Catches new files before commit | No |
| Dedup window | Partition `(household_id, reading_ts)` | Partition also by `is_candidate` | Same ranks for candidates; validated in spike 04 | No |
| Daily total | `sum(energy_kwh)` | Exact decimal(38,10) sum cast to double | Order-independent total for AC-27 (review finding) | No |
| Test time zone | - | conftest pins process TZ to UTC | Spark returns naive datetimes in the process zone | No |
| PR 2b helper module | Setup notebook holds the DDL (entry 43) | DDL lives in `src/.../catalog_setup.py` with `tests/test_catalog_setup.py`; the notebook only executes it | A notebook cannot be imported, so the statements would be untestable | No |
| Placeholder notebook | Entry 47 deletes `resources/jobs.yml` only | `notebooks/hello.py` deleted too | Its own header says to delete it once the first real job exists; nothing references it | No |
| Package path in notebooks | Not specified | Job passes `src_path=${workspace.file_path}/src`; a manual run falls back to `<cwd>/../src` | Avoids py4J notebook-context calls on serverless; the fallback is unverified (pending live) | No |
| Ruff globs | - | `**/pipelines/*` ignores F821 (`spark` is injected) | Same reason as notebooks | No |
| PR 3 extra tests and config | Manifest lists 6 test files for PR 3 (53 to 58) | Also `tests/test_integration_layout.py` (marker, naming, AC coverage, deselection, no SDK import at module level) and a `pyproject.toml` ruff S608 ignore for `tests/integration` | Proves in the default run that the integration tests are collectable, marked and excluded, without a workspace | No |
| AC-26 pipeline count | "Exactly one pipeline in the workspace" | Exactly one pipeline with the bundle name; every pipeline name seen is saved to `out/evidence/ac26_pipelines.json` | The workspace also holds an unrelated idle pipeline (I-10) | No (needs a DESIGN wording fix at `/ship`) |
| Extra integration tests | AC-10 has the `after` test only; no I-18 or redaction test | Added `test_ac10_before_outage_snapshot`, the I-18 pair, `test_ac29_failed_stream_error_does_not_leak_credentials` and `test_ac12_totals_consistent_after_full_refresh` | The DESIGN names a before/after pair for AC-10 without a before test; I-18 and I-20 are PR 3 must-handle items; AC-12 must also hold after a full refresh | No |
| AC-30 run choice | "The latest full job run succeeded" | The latest *successful* run, all four tasks successful, duration and no quota termination checked; newer unsuccessful runs are recorded in evidence | After the AC-10 outage run the latest run is a failure by design | No |
| Re-running a task | "Rerun task `ingest_files`" | `jobs.run_now(job_id, only=[task])` through the SDK | Runs one task of the deployed job without the others | No |
| Time zone | - | The SQL fixture fails unless the warehouse session time zone is UTC | Golden rule 5 | No |
| Seed-42 counts and test order | Counts asserted as stated | Exact counts hold only for a state with no replay, so the runbook fixes the order (step F last among data tests) | AC-07, AC-11 and AC-34 compare with the pinned manifest | No |

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
| I-13 | Topic `meter-readings` did not exist and Aiven does not auto-create topics | Closed (PR 3) | Runbook section 3 creates the topic (2 partitions, idempotent, reads `.env`, prints no credential) and documents the Aiven dependency (an Aiven outage stalls the Silver and Gold refresh). The topic itself was created 2026-10-16 |
| I-14 | Spike 03: a stream failure surfaces at notebook-cell level ("Some streams terminated before this command could finish!") and is not caught by `try` around `awaitTermination` | Closed (PR 2b) | The Kafka task in PR 2a must not rely on catching the exception in Python; let the task fail and use task `timeout_seconds` and retries. PR 2a: `bronze.run_available_now` has no try/except, guarded by an AST test. The notebooks (PR 2b) must follow it. PR 2b: none of the three notebooks nor the pipeline has a try/except, and the AST guard `test_ac10_notebooks_and_pipeline_have_no_try_except` covers them |
| I-12 | ADR 0005 still called the evaluation MV private and mentioned a per-update duplicate count | Closed | ADR 0005 updated 2026-10-16: published evaluation MV, `is_duplicate` table total, event log for observability |
| I-10 | The workspace holds an unrelated pipeline (`elt-uber-eats-analytics`, idle) | Low | Spike 04 ran alongside it. Check the one-pipeline-per-type limit again when the bundle pipeline is deployed |
| I-15 | A replayed invalid Kafka message is a new Bronze row that fails the same rule and was quarantined again; only valid rows were deduplicated (QR-09). AC-09 held for seed 42 only because the stream has no invalid message, which contradicted NFR-02 | Closed (rebuilt 2026-10-19) | Reopened by the user the same day (reverses "accepted as is"). New behaviour: dropped rows are deduplicated by `_dedup_key` (path prefix plus raw business key, or a SHA-256 of the raw payload or record when no key can be read), earliest `_ingested_at` then smallest `_source_ref` wins, repeats are counted in `is_duplicate` (and in `is_quarantine_duplicate`), are not quarantined again and raise no per-rule total (DEFINE QR-09 b, FR-08, AC-09, AC-11, AC-12; DESIGN Column derivations). The existing test `tests/test_silver_dedup.py` that documents re-quarantine (docstring "quarantined again", around line 79) was rewritten as `test_ac09_replayed_invalid_messages_not_quarantined_again`. Code, contracts check and integration queries to rebuild: see the Change Log below |
| I-22 | Review of the I-15 rebuild, Medium, design-level: for a Kafka payload failing QR-07 that still parses partially (for example null `source` with `produced_at` set), `_dedup_key` is the SHA-256 of the whole payload; the replay producer stamps a new `produced_at`, so the replay is quarantined again (NFR-02, AC-09 not met for that class; "not json" payloads are unaffected) | Closed (rebuilt 2026-10-19) | User decision 2026-10-19: key on `kafka:key:` whenever raw `household_id` and `reading_ts` are readable (non-null `get_json_object` results), even when `payload_ok` is false; hash the payload only when either is unreadable (DEFINE *Dedup key of dropped rows*, QD-01; DESIGN Column derivations and AC-09 tests). Rebuilt: `KAFKA_DEDUP_KEY_SQL` in `silver.py`; new test `test_ac09_replayed_partially_parseable_invalid_payload_not_quarantined_again`; extend `test_ac09_dedup_key_is_per_path_and_offset_independent` and the AC-09 fixture |
| I-16 | Code review PR 2a, Medium: Gold total order-dependence (fixed, decimal sum), ANSI not forced in conftest (fixed), unknown pipeline-config keys silently ignored (fixed, ValueError), vacuous totals test (renamed) | Closed | - |
| I-17 | Code review PR 2a, Low. PR 2b closed the `CREATE VIEW` and UTC items. Still open, no PR 3 change: `trim` removes spaces only; `study_*` and cutoff must be midnight dates; the event-log SQL is Databricks-only; the broker-host scan needs `KAFKA_*` exported; `auto_loader_reader` and `kafka_reader` are exercised only by the integration tests | Low, open | Integration run |

| I-18 | PR 2b review, Medium: `household_data_quality_check` (Python) reads the persisted view that the SQL file creates in the same pipeline. The platform dependency edge between a Python dataset and a SQL `CREATE VIEW` is proven only by the local fake | Medium, closed 2026-10-20 | PR 3 added the integration pair `test_ac26_i18_before_first_update_gold_schema_is_empty` and `test_ac26_i18_after_first_update_summary_view_exists_and_update_completed`, and the runbook ordering (steps A and B, from an empty Gold schema). Live run 2026-10-20: the first attempt was invalidated because update `8649ab60` failed with RESOURCE_EXHAUSTED (capacity, not I-18) after the `before` snapshot; update `bf5b5504` then completed but could not count, since the failed update might have left Gold objects. The Gold objects were dropped and the pair re-run: `before` saw an empty Gold schema (snapshot 2026-10-20T14:17:11Z), the next update `47f03259` (created 14:17:15Z) completed, and the view and both MVs exist; both tests passed. The fallback was not needed. Fallback decided by the user 2026-10-19 (record only, no design change now): if the pipeline update from an empty Gold schema fails because the Python `household_data_quality_check` dataset cannot read the SQL-created summary view, derive the check from the monthly table (`gold.household_data_quality_monthly`) instead, applied through a follow-up `/iterate` |
| I-19 | PR 2b review, Medium (fixed): pipeline settings keys now have no default, so a missing `smart_meter.*` key fails the update; wiring test replaced by an executed one; AC-29 print guard is taint-tracked; vacuous and tautological asserts removed; AC-04 test split out | Closed | - |
| I-20 | PR 2b review, Low. Addressed in the runbook: the Aiven dependency of `refresh_silver_gold` (runbook, dependency section, and a pipeline-only run while Aiven is off); `CREATE TABLE IF NOT EXISTS` does not migrate a Bronze schema (runbook, Bronze reset and schema changes); verification of stream error redaction (runbook procedure and `test_ac29_failed_stream_error_does_not_leak_credentials`, not run). Left open: `src_path` fallback and `cluster_by` on serverless, which only a live run can show | Low, open | Live run (steps A to C) and the redaction procedure |
| I-21 | AC-17 wording (DEFINE): the Given "same key from files and from Kafka" is impossible, because QR-06 admits files rows only before the cutoff and Kafka rows only at or after it | Closed | `/iterate` 2026-10-19: AC-17 reworded by the user (files pair plus Kafka pair, run again in reversed order and with a different partitioning). The deviation row "Cross-path duplicate in AC-17 test" is closed. The local AC-17 tests should be checked against the new fixture (earlier `_ingested_at` on the larger `_source_ref` in the files pair; Kafka pair tied on `_ingested_at`) |
| I-23 | Live steps D and E (2026-10-20): (a) powering off the Aiven free service empties the topic and resets its offsets, so the runbook "Broker outage" recovery ("the Kafka stream resumes at the checkpoint offsets") does not hold for a power-off, only for a network outage; a run after power-on fails on `failOnDataLoss` and leaves an uncommitted offsets batch that keeps failing; recovery is a Kafka reset (drop `bronze.kafka_meter_readings` and its checkpoint, re-produce the sample). (b) `ingest_kafka` ran twice per job run despite `max_retries: 0` ("No retry", AC-10), for both an `INTERNAL_ERROR` and a `TERMINATED FAILED` attempt; likely the serverless automatic retry, not verified. (c) `databricks fs rm -r` on the checkpoint folder in the Volume exited without removing it | Medium, open | `/iterate`: runbook "Broker outage" and "Bronze reset" (power-off case, Catalog Explorer for the checkpoint), ADR 0001 (Aiven free power-off loses the topic), DESIGN retry statement for AC-10 after checking the serverless retry setting. AC-10 itself holds: the failed run left Bronze and the checkpoint unchanged |

---

## Pending on the user

Done on 2026-10-16: auth (`dev` profile), `.env`, secret scope, Aiven SASL mechanism, topic, sample upload, DA-06 test and spikes 00 to 04.

Live verification of the whole feature (not run, by instruction). The full procedure, with the order and the pass criteria, is in `docs/runbooks/meter_ingestion.md`. In short:

1. Preparation: power Aiven on; build the producer image `docker build -f docker/producer/Dockerfile -t smart-meter-producer .`; `export DATABRICKS_CONFIG_PROFILE=dev`; `pip install -e ".[dev,integration]"`; `python scripts/prepare_sample.py build --out data/sample/seed42` (the AC-25 test reads its manifest).
2. Deploy (AC-28 evidence, record the exit codes): `databricks bundle deploy -t dev -p dev` (expected to fail at pipeline creation on a fresh workspace), run `notebooks/setup_catalog.py` once from the synced files, `databricks bundle deploy -t dev -p dev` again. If the catalog already exists from the 2026-10-16 spikes, the first deploy may succeed; record what happens.
3. Step A: upload the sample (runbook section 2), `databricks bundle run -t dev -p dev smart_meter_ingestion --only setup_catalog,ingest_files`, then `pytest -m integration tests/integration/test_gold_tables.py::test_ac26_i18_before_first_update_gold_schema_is_empty`. Note: the Gold schema must be empty; if a spike left objects there, follow the runbook "Update from an empty Gold schema".
4. Step B: `databricks bundle run -t dev -p dev smart_meter_silver_gold`, then the I-18 `after` test, `test_ac24_before_kafka_snapshot`, `test_ac05_*`, `test_ac06_*`.
5. Step C: one full replay (producer, Aiven on), `databricks bundle run -t dev -p dev smart_meter_ingestion`, then the Bronze Kafka tests (AC-07, AC-08), all of `test_silver_tables.py` and `test_gold_tables.py` (except the I-18 pair), `test_ac24_after_*`, `test_deployment.py`.
6. Step D (AC-10): `test_ac10_before_outage_snapshot`, power Aiven off, run the job (the Kafka task fails), `test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged`. Step E: Aiven on, run the job, re-run AC-07 and AC-30.
7. Step F (AC-09): `test_ac09_before_replay_snapshot`, second full replay, run the job, `test_ac09_after_replay_silver_unchanged`.
8. Step G (AC-27, AC-12): `test_ac27_before_full_refresh_snapshot`, `databricks bundle run -t dev -p dev smart_meter_silver_gold --full-refresh-all`, `test_ac27_after_*`, `test_ac12_totals_consistent_after_full_refresh`.
9. Redaction (AC-29, I-20): the runbook section "Stream error redaction check".
10. Also look for: `cluster_by` accepted, the UTC assertion passes, `src_path` import works, names carry the `[dev <user>]` prefix, the schedule is paused.

The rebuild of I-15 is done (see *Iterate rebuild 2026-10-19*); steps C, F and G run the updated queries.

Decisions still open:

- Whether to accept any AC as `Pass` without live evidence, so the report can move to `Complete` before `/ship`.

---

## Iterate rebuild 2026-10-19

Scope: the rebuild required by the `/iterate` of 2026-10-19 (commit 0207dc1; QR-09 b, I-15), on branch `feat/meter-ingestion-pr3`, as new commits on top of PR 3.

| File | Change | Verified by |
|---|---|---|
| `src/smart_meter_peak_prediction/silver.py` | `_dedup_key` (files and Kafka expressions as in the DESIGN, control characters as SQL escapes), `quarantine_rank` over `(_dedup_key, is_dropped)`, `is_quarantine_duplicate`, `is_quarantined`, `is_duplicate` = valid or quarantine duplicate; evaluated and quarantine column lists in contract order; the quarantine view keeps `is_quarantined` rows | `test_contract_schemas.py`, `test_silver_dedup.py`, `test_silver_readings.py` |
| `src/smart_meter_peak_prediction/metrics.py` | per-rule totals add `AND NOT is_quarantine_duplicate`; new `quarantine_duplicates`; `quarantine_rows` excludes quarantine duplicates; reconciliation has the fifth class `is_quarantine_duplicate` | unit tests above, seed-42 local data |
| `src/smart_meter_peak_prediction/rules.py`, `pipelines/meter_pipeline.py` | QR-09 note and table comment | `test_pipeline_wiring.py` |
| `tests/support/builders.py` | `mixed_fixture` gains a replayed QR-07 message | AC-11, AC-12 unit tests, wiring |
| `tests/test_silver_dedup.py` | I-15 test replaced by `test_ac09_replayed_invalid_messages_not_quarantined_again`; new `test_ac09_dedup_key_is_per_path_and_offset_independent`; AC-17 rerun test also covers the pair fixture | pytest |
| `tests/test_silver_readings.py`, `tests/test_rules_metrics.py` | AC-11 fifth class, AC-12 totals with the replayed invalid row, SQL builder check | pytest |
| `tests/local_data/test_pipeline_seed42.py` | 60 quarantined rows have 60 distinct keys, 0 quarantine duplicates | `pytest -m local_data` |
| `tests/integration/conftest.py`, `test_silver_tables.py`, `test_reprocessing.py` | AC-12 uniqueness and duplicate decomposition, AC-11 `is_quarantine_duplicate = 0`, AC-09 per-rule and quarantine-duplicate totals unchanged | collected, not run |
| `docs/runbooks/meter_ingestion.md`, ADR 0004, ADR 0005 | Known-limit wording replaced; ADR amendments of 2026-10-19 (status unchanged) | `check_specs.py` |

Deviations: none from the DESIGN. The AC-17 tests already matched the new wording; the rerun test was extended to assert the duplicate total 2 on the pair fixture.

### Self-Review

- **Weak points:** The AC-09 clause for invalid messages is proven only by the unit harness (the seed-42 stream has no invalid message). The `\u0001` and `\u0000` separators in `_dedup_key` are SQL escapes that local Spark parses; Databricks SQL is expected to parse them the same way but this was not run. The reconciliation SQL does a correlated lookup on the quarantine by `_dedup_key`, fine at 60 rows, untested at scale.
- **Risks:** Dropping `is_dropped` from the partition would let a valid row and a dropped row with one business key compete; the test fixtures do not contain that exact collision. Recompute cost grows by one more window over the evaluation table.
- **Trade-offs:** `is_duplicate` mixes two kinds (valid and dropped repeats); `is_quarantine_duplicate` is queryable alone, as the DESIGN requires.
- **Next step:** Run the live steps under *Pending on the user* (steps C, F, G read the changed queries).

---

## Self-Review

### PR 3

- **Weak points:** None of the 33 integration tests has run. The SQL was written for Databricks SQL and checked only by reading it against the contracts and the library (it was not executed on any engine), and the SDK calls (`run_now(only=...)`, `list_runs`, `list_updates`, `tables.get`, `get_run_output`) were checked against the installed `databricks-sdk` signatures, not against the workspace. The runbook commands were checked with `--help` only. Several tests depend on order and on a clean state (exact seed-42 counts, the empty Gold schema, files-only state before Kafka), which the runbook fixes but a test cannot enforce.
- **Risks:** The I-18 platform edge (Python dataset reading the SQL view) was proven live on 2026-10-20 (update `47f03259` from an empty Gold schema); its fallback was not needed. The quarantine dedup of I-15 (decided 2026-10-19) is specified but not built, so AC-09, AC-11, AC-12 and AC-17 need the rebuild before the live run. An Aiven outage stalls the Silver and Gold refresh by design. The free warehouse time zone is assumed to be UTC (the fixture fails otherwise). The pre-commit hook pins ruff 0.6.9 while CI installs the latest ruff, so formatting can differ between them (one `assert ... , message` construct was rewritten to be stable under both).
- **What I would do differently:** Give the integration suite a single orchestrating script that runs steps A to G in order and stops at the first failure, and make the seed-42 expectations relative to a recorded baseline instead of absolute counts.
- **Next improvement:** Run the live verification (*Pending on the user*), fix what it finds through `/iterate` or code changes, then move this report to `Complete` and run `/ship METER_INGESTION`.

### PR 2b

- **Weak points:** The wiring is proven only against a fake `dlt` and local Spark. Not proven on the platform: the Python-to-SQL-view dependency (I-18), `cluster_by` on materialized views, the notebook `src_path` fallback (`os.getcwd()`), `spark.conf.set` of the time zone on serverless, and redaction of stream errors. Nothing was deployed.
- **Risks:** `refresh_silver_gold` waits for Kafka, so an Aiven outage stalls Silver and Gold (accepted in the DESIGN). The first deploy still fails once by design (DA-06).
- **What I would do differently:** Put the notebook bootstrap (src path, widgets, UTC) in one place instead of three copies; the three copies are checked only by tests.
- **Next improvement:** PR 3: integration tests, runbook (including topic creation, I-13, and the Aiven dependency) and README; then the live run listed under Pending on the user.

### PR 2a

- **Weak points:** Lakeflow semantics (MV refresh, `expect_*` on the published evaluation MV, `CREATE VIEW` in the pipeline) are proven only by spike 04 and by the harness; `auto_loader_reader`, `kafka_reader` and the summary `CREATE VIEW` statement have not run. Local Spark 4.0.4 with ANSI forced is close to serverless but not identical.
- **Risks:** AC-27 depends on all Gold aggregates being order independent (daily total fixed; monthly uses counts and min/max only). Pipeline refresh time of the full recompute is only known from spike 04 (63 s). Replayed invalid messages were not deduplicated when PR 2a was built (I-15, resolved by `/iterate` 2026-10-19, pending build).
- **What I would do differently:** Build the harness against the real `dlt` wiring earlier, and add a settings validation step (dates, midnight, ordering) in `Settings.__post_init__`.
- **Next improvement:** PR 2b (notebooks, pipeline wiring with `rules.py`, bundle), then run it on the workspace and collect the pending integration evidence.

### PR 1

- **Weak points:** The producer has only published 1,000 events; a full replay of 247,569 has not run. The DA-01 cause (refresh skipped on an update with no new input) is inferred: spike 04 drops its event log on cleanup, so the update 2 events were not inspected.
- **Risks:** The DA-01 change alters count semantics (table totals instead of per-update counts); DEFINE and DESIGN are aligned, but PR 2a must implement the new contract first. Aiven powers off after inactivity, so integration runs need it on.
- **What I would do differently:** Run the spike 04 pipeline code in a dry check against a fake `dlt` before handing it over, and give the ADR test a distinct state for "spike not yet run" so CI can stay green on the PR 1 branch without skipping.
- **Next improvement:** Start PR 2a.

---

## Next Step

Run the live verification listed under *Pending on the user* (or explicitly accept the pending ACs), then `/ship METER_INGESTION`. The quarantine dedup of I-15 is built (see *Iterate rebuild 2026-10-19*). The AC-17 wording and the I-18 fallback are decided; no user decision is open except whether to accept ACs without live evidence.

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-19 | I-15 reopened and set to "Resolved by /iterate 2026-10-19, pending build" (quarantine dedup by `_dedup_key`); I-21 closed (AC-17 reworded); deviation row "Cross-path duplicate in AC-17 test" closed; I-18 row records the decided fallback and it is removed from "Pending on the user"; AC evidence rows for AC-09, AC-11, AC-12 and AC-17 and the summary line marked as pending rebuild; added a rebuild-first step to "Pending on the user"; PR 2a and PR 3 Self-Review text aligned | User decisions 2026-10-19; DEFINE, DESIGN and the quarantine and evaluation contracts changed through `/iterate` the same day | Rebuild: `src/smart_meter_peak_prediction/silver.py` (`_dedup_key`, `quarantine_rank`, `is_quarantine_duplicate`, `is_quarantined`, `is_duplicate` union), `rules.py` (comments, column lists if any), `metrics.py` (per-rule filter, quarantine-duplicate total, AC-11 reconciliation class), the harness if it lists columns; tests: rewrite the re-quarantine test in `tests/test_silver_dedup.py`, add the two AC-09 tests, extend AC-11, AC-12 and AC-17 tests, update `tests/test_contract_schemas.py` expectations; integration: `test_silver_tables.py` (AC-11, AC-12), `test_reprocessing.py` (AC-09, AC-12 helper); runbook line on re-quarantine; ADR 0004 and 0005 wording. Open PRs #2 (2a libraries), #3 (2b wiring) and #4 (3 integration tests, runbook) are all affected |
| 2026-10-19 | Iterate rebuild: quarantine dedup (I-15 closed), AC-09, AC-11, AC-12 and AC-17 evidence rows, Verification Log rows, new section *Iterate rebuild 2026-10-19* | Rebuild required by commit 0207dc1 | Live steps C, F, G read the updated queries; no DESIGN change |
| 2026-10-19 | I-22 set to "Resolved by /iterate 2026-10-19, pending build" (Kafka `_dedup_key` keyed on the raw business key whenever both raw fields are readable, also for QR-07 failures) | User decision 2026-10-19; DEFINE, DESIGN and the quarantine and evaluation contracts changed through `/iterate` | Rebuild `KAFKA_DEDUP_KEY_SQL` in `silver.py`; tests in `tests/test_silver_dedup.py` (new partially parseable replay test, extended key test and AC-09 fixture); ADR 0005 and runbook wording |
| 2026-10-19 | I-22 rebuilt and closed: `KAFKA_DEDUP_KEY_SQL` no longer conditioned on `payload_ok`; new and extended AC-09 tests; ADR 0005 and runbook reworded | Rebuild required by commit 5c655cc | none; live steps C, F unchanged |
| 2026-10-20 | I-18 closed: the I-18 pair passed live from a dropped Gold schema (update `47f03259`); AC-26 live evidence marked partial; PR 3 Self-Review risk updated | The first attempt was invalidated by the RESOURCE_EXHAUSTED update `8649ab60` after the snapshot | none; the AC-26 metadata test still runs in step C |
| 2026-10-20 | Step C recorded: AC evidence rows and summary, three Verification Log rows | Live step C run 2026-10-20 | `full_runs` fixture fixed (page size, partial runs); steps D to G remain |
| 2026-10-20 | AC-05 and AC-06 live Pass, run after step C | They had no recorded step B result | none; the AC-06 rerun is a partial `only=` run, which `full_runs` now excludes |
| 2026-10-20 | Steps D and E recorded: AC-10 and AC-30 live Pass, summary, three Verification Log rows, new issue I-23 | Live steps D and E run 2026-10-20 | I-23 needs `/iterate` (runbook, ADR 0001, DESIGN retry wording); steps F and G remain |
| 2026-10-20 | Step F recorded: AC-09 live Pass, summary, Verification Log row | Live step F run 2026-10-20 | Step G and AC-29 remain; the seed-42 exact counts of step C no longer hold for Bronze Kafka (two replays) |
| 2026-10-20 | Step G recorded: AC-27 and AC-12 live Pass, summary, Verification Log row | Live step G run 2026-10-20 | AC-29 redaction check, AC-28 first-deploy exit codes and the I-23 `/iterate` remain |
