# BUILD REPORT: Peak Model

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL |
| **Date** | 2026-10-21 |
| **Source** | DESIGN_PEAK_MODEL.md (status Ready for Build) |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

One report covers the whole feature (DESIGN *Delivery Plan*). It stayed `In Progress` until the PR 3 live evidence (2026-10-22).

---

## Summary

This report covers **PR 1 (manifest entries 1 to 23)** and, below, **PR 2 (entries 24 to 35, branch `build/peak-model-pr2`)**. PR 1: on branch `build/peak-model-pr1`, built on
2026-10-21 from main `d18cea9`: the ten libraries, the five data contracts, the test builders and
the unit tests. Everything was verified locally on Spark 4.0.4, scikit-learn 1.3.2 and MLflow
3.17.2. Nothing was deployed, run on Databricks or committed, and no notebook, bundle resource or
integration test exists yet (entries 24 to 44 belong to PR 2 and PR 3).

| PR | Entries | State |
|---|---|---|
| PR 1 | 1 to 23 | **Built and verified locally** (this report) |
| PR 2 | 24 to 35 | **Built and verified locally**; platform gate passed on `dev` (see *PR 2 gate*) |
| PR 3 | 36 to 44 | **Built and verified locally** (branch `build/peak-model-pr3`); live integration evidence recorded 2026-10-22, 27 of 27 pass (see *PR 3*) |

---

## Files Changed

State legend: done = written and verified locally; nothing here has run on the platform.

### PR 1 files (entries 1 to 23)

| # | PR | File | Action | Verified by |
|---|---|---|---|---|
| 1 | PR 1 | pyproject.toml | Modified | done: dev extra adds `scikit-learn>=1.3,<1.4`, `numpy<2`, `mlflow-skinny>=2.16,<4`, `pyarrow>=15,<22`; integration extra adds `mlflow-skinny`, `pyarrow`; ruff `S608` ignore for `delta_sync.py`, `features.py`, `labels.py`. `ruff check .`, full `pytest` (see Deviations D-01) |
| 2 | PR 1 | src/smart_meter_peak_prediction/peak_config.py | Created | done: `tests/test_peak_tables.py` (names, `PeakParameters` defaults, widgets, G-09, G-01 `check_versions`, calendar months) |
| 3 | PR 1 | src/smart_meter_peak_prediction/delta_sync.py | Created | done: `tests/test_peak_tables.py` (MERGE text, no-op metrics, no `.cache(`/`.persist(` in `src/`, metrics parser, `replaceWhere` predicate, properties SQL). MERGE, `DESCRIBE HISTORY` and `replaceWhere` need Delta and are not executed locally (live check at the PR 2 gate, DA-15) |
| 4 | PR 1 | src/smart_meter_peak_prediction/peak_setup.py | Created | done: `tests/test_peak_tables.py` (DDL equals the contracts in names, types, order and NOT NULL; properties; schema precondition with a fake session). DDL not executed on Delta |
| 5 | PR 1 | src/smart_meter_peak_prediction/weather.py | Created | done: `tests/test_weather.py` (10 tests) |
| 6 | PR 1 | src/smart_meter_peak_prediction/features.py | Created | done: `tests/test_features.py` (7 tests incl. a pandas oracle for three parameter sets) |
| 7 | PR 1 | src/smart_meter_peak_prediction/labels.py | Created | done: `tests/test_labels.py` (9 tests) |
| 8 | PR 1 | src/smart_meter_peak_prediction/model.py | Created | done: `tests/test_training.py` (encoding, `mlflow.pyfunc` save and load round trip with `code_paths`). Imports no PySpark |
| 9 | PR 1 | src/smart_meter_peak_prediction/training.py | Created | done: `tests/test_training.py` (18 tests with a fake tracker) |
| 10 | PR 1 | src/smart_meter_peak_prediction/registry.py | Created | partial: `resolve_champion` (G-07) and `MlflowTracker.register_model` (order: log, reload G-08, tag, alias) tested with fakes in `tests/test_scoring.py` and `tests/test_training.py`. `ensure_feature_table`, `build_training_set`, `table_version`, `log_inputs` and the real `fe.log_model` call are untested: they need the FE client (PR 2 gate, DA-15, DA-16) |
| 11 | PR 1 | src/smart_meter_peak_prediction/scoring.py | Created | done: `tests/test_scoring.py` (12 tests, fake scorer, registry and writer) |
| 12 | PR 1 | docs/contracts/bronze_files_weather_hourly.yaml | Created | done: `check_specs.py` 0 errors; `tests/test_peak_tables.py` (AC-64) |
| 13 | PR 1 | docs/contracts/silver_weather_hourly.yaml | Created | done: same |
| 14 | PR 1 | docs/contracts/ml_household_features_daily.yaml | Created | done: same |
| 15 | PR 1 | docs/contracts/ml_household_labels_daily.yaml | Created | done: same |
| 16 | PR 1 | docs/contracts/gold_consumption_spike_predictions.yaml | Created | done: same |
| 17 | PR 1 | tests/support/peak_builders.py | Created | done: used by every PEAK_MODEL unit test; AC-42, AC-43 and AC-45 fixtures |
| 18 | PR 1 | tests/test_weather.py | Created | done: 10 passed |
| 19 | PR 1 | tests/test_features.py | Created | done: 9 cases passed |
| 20 | PR 1 | tests/test_labels.py | Created | done: 9 passed |
| 21 | PR 1 | tests/test_training.py | Created | done: 18 passed |
| 22 | PR 1 | tests/test_scoring.py | Created | done: 12 passed |
| 23 | PR 1 | tests/test_peak_tables.py | Created | done: 27 cases passed |

### PR 2 files (entries 24 to 35)

| # | PR | File | Action | Verified by |
|---|---|---|---|---|
| 24 | PR 2 | notebooks/ingest_weather.py | Created | done: ruff; `test_peak_bundle.py` (widgets, UTC, no try, library calls exist). Not run on Databricks |
| 25 | PR 2 | notebooks/build_weather_silver.py | Created | done: same. Raises on empty Bronze before the MERGE (review finding) |
| 26 | PR 2 | notebooks/build_features.py | Created | done: same, plus pins equal `PINNED_REQUIREMENTS` |
| 27 | PR 2 | notebooks/build_labels.py | Created | done: same; AC-63 parameters are widgets |
| 28 | PR 2 | notebooks/score_predictions.py | Created | done: same |
| 29 | PR 2 | notebooks/train_model.py | Created | done: same; G-05 checked right after reading the widget |
| 30 | PR 2 | resources/smart_meter_peak_model.job.yml | Created | done: `databricks bundle validate -t dev --profile dev` OK; `test_peak_bundle.py` |
| 31 | PR 2 | resources/smart_meter_peak_model_training.job.yml | Created | done: same; `bundle.git.commit` resolved to the HEAD commit in validate output (DA-17 partly) |
| 32 | PR 2 | tests/test_peak_bundle.py | Created | done: 27 cases pass |
| 33 | PR 2 | tests/test_peak_model_adr.py | Created | done: 2 passed |
| 34 | PR 2 | tests/test_secrets_hygiene.py | Updated | done: `test_ac65_tracked_files_contain_no_databricks_token` |
| 35 | PR 2 | tests/local_data/test_peak_seed42.py | Created | done: 6 passed on `data/sample/seed42` (see Verification Log) |
| - | PR 2 | src/smart_meter_peak_prediction/registry.py | Modified (D-11) | `build_training_set` casts `target_date` and `lookup_date` to DATE; new unit test |
| - | PR 2 | src/smart_meter_peak_prediction/training.py | Modified (D-13) | `select_training_rows` casts the label to int |
| - | PR 2 | tests/test_scoring.py, tests/test_peak_tables.py, tests/test_training.py | Updated (D-12) | two G-09 tests and the `build_training_set` test |
| - | PR 2 | tests/local_data/test_pipeline_seed42.py | Updated (D-14) | schema copy fix |
| - | PR 2 | DESIGN_PEAK_MODEL.md | Updated | Test Strategy rows for the three new tests and a change-log line |

No METER_INGESTION file, `databricks.yml` or resource file was modified (`git status` lists only the
files above; AC-62 is checked by PR 2's `test_peak_bundle.py`).

### PR 3 files (entries 36 to 44)

| # | PR | File | Action | Verified by |
|---|---|---|---|---|
| 36 | PR 3 | tests/integration/conftest.py | Modified | done: ruff; collected with the four new files. Fixtures `peak_job`, `training_job` (by base name), `peak_runner` (`run_now` with job parameters and `only`, polls to the end, reads every task exit value and error; refuses to start a run that includes `refresh_silver_gold` unless `smart_meter_ingestion` and the pipeline are idle, DA-13), `peak_names`, `mlflow_registry` (lazy MLflow: runs, artifact download, version of a run, champion, threshold tag) |
| 37 | PR 3 | tests/integration/test_peak_data.py | Created | done: ruff; `pytest --collect-only -m integration` (12 tests: AC-36, 37, 39, 40, 41, 44, 47, 63 x2, 64, 66 x2). The AC-40 SQL oracle was run against local Spark on the `test_features.py` messy fixture and found 0 differing rows (it exposed a `DECIMAL` division in the first draft of `complete_day_share_28d`, fixed). Run on `dev` 2026-10-22: pass (see *PR 3 live run*) |
| 38 | PR 3 | tests/integration/test_peak_training.py | Created | done: ruff; collected (8 tests: AC-48, 49, 50, 51, 52, 54, 55 x2). AC-53 has no live test by DESIGN (unit only). Run on `dev` 2026-10-22: pass (see *PR 3 live run*) |
| 39 | PR 3 | tests/integration/test_peak_scoring.py | Created | done: ruff; collected (6 tests: AC-56, 57 x2, 58, 59, 60). File order is the evidence order (58, 59, then 56). Run on `dev` 2026-10-22: pass (see *PR 3 live run*) |
| 40 | PR 3 | tests/integration/test_peak_deployment.py | Created | done: ruff; collected (AC-62). It starts no run and asserts the ingestion job and the pipeline are idle first. Run on `dev` 2026-10-22: pass (see *PR 3 live run*) |
| 41 | PR 3 | scripts/reset_peak_model_outputs.py | Created | done: ruff; `tests/test_peak_reset_script.py` (3 tests, AC-66 guards: exactly three DROPs, refusal on other row counts, a missing table, empty Bronze weather or a missing snapshot); `--help` runs. Never run against the workspace |
| 42 | PR 3 | docs/runbooks/peak_model.md | Created | done: covers weather upload, deploy, bootstrap order, training, backfill, evidence order, reset, model cleanup order (aliases, versions, model; ADR 0007), concurrency with the ingestion job (DA-13: refused update, not retried, rerun after the ingestion run) and serverless auto-optimization retries (D-21). `check_specs.py` 0 errors |
| 43 | PR 3 | docs/spikes/README.md | Modified | done: rows for A-17 and spike 05 (figures copied from ADR 0007) |
| 44 | PR 3 | README.md | Modified | done: PEAK_MODEL architecture summary, runbook, contracts and ADRs 0007 to 0011, repository layout and limitations |
| - | PR 3 | tests/test_integration_layout.py | Modified | done: the four new files, their AC set and four collected names are expected (mechanical, same guard as for METER_INGESTION) |
| - | PR 3 | tests/test_peak_reset_script.py | Created | done: 3 tests |

No METER_INGESTION file, `databricks.yml`, resource file, notebook or library module was modified in PR 3.

---

## Acceptance Criteria Evidence

**Local** is the PR 1 unit evidence (real test output, see the Verification Log). **Live** is the
platform evidence: the PR 3 integration tests, run on `dev` on 2026-10-22 (see *PR 3 live run*). `PR 2` and `PR 3` mark where the remaining evidence comes
from. AC-65 and AC-67 are decided by tests of PR 2.

| AC | Local (PR 1) | Live | Test names (PR 1) and what is still missing |
|---|---|---|---|
| AC-36 | Pass (projection) | Pass (live 2026-10-22) | `test_weather.py::test_ac36_bronze_projection_keeps_raw_columns_and_metadata`, `::test_ac36_raw_names_cover_every_source_column_once`. Missing: Auto Loader run and 21,165 rows (PR 2 notebook 24, PR 3 `test_peak_data.py`) |
| AC-37 | Pass (unit) | Pass (live 2026-10-22) | `test_weather.py::test_ac37_weather_ts_is_independent_of_session_time_zone` (four DST days, UTC and Europe/London, 24 rows each). PR 2 local data: `::test_ac37_raw_weather_file_same_in_utc_and_london` Pass (21,165 rows, UTC = London). Missing: deployed table |
| AC-38 | Pass | n/a | `test_weather.py::test_ac38_unparseable_time_fails_before_write`, `::test_ac38_null_time_fails_before_write`, `::test_ac38_non_numeric_temperature_fails_before_write`, `::test_ac38_duplicate_time_keeps_earlier_ingested_and_counts_one`, `::test_ac38_temperature_50_is_kept_and_warn_count_is_one`, `::test_ac38_silver_schema_has_the_contract_columns` |
| AC-39 | Pass (unit) | Pass (live 2026-10-22) | `test_weather.py::test_ac39_day_without_weather_has_count_0_and_null_mean`, `test_features.py::test_ac39_mean_temperature_matches_recomputation_and_is_order_stable` (1, 3 and 8 partitions bitwise equal). PR 2 local data: `::test_ac39_seed42_temperature_hour_counts` Pass. Missing: deployed table (PR 3) |
| AC-40 | Pass (unit) | Pass (live 2026-10-22) | `test_features.py::test_ac40_features_match_independent_recomputation` (3 parameter sets, 0 mismatches, nulls in the same places), `::test_ac40_feature_table_columns_match_the_contract_order`. Missing: SQL recomputation on the deployed table (PR 3) |
| AC-41 | Pass (unit) | Pass (live 2026-10-22) | `test_features.py::test_ac41_feature_grid_is_dense_and_density_check_fails_on_gap`, `::test_ac41_feature_table_not_null_columns_hold_no_null`, `test_labels.py::test_ac41_label_grid_is_dense_with_target_date_plus_one`. PR 2 local data: `::test_ac41_seed42_tables_have_36480_rows` Pass. Missing: deployed tables (PR 3) |
| AC-42 | Pass | n/a | `test_features.py::test_ac42_changing_data_from_t_leaves_earlier_features_and_training_rows_unchanged` (features before T, labels before T and the training rows of T identical; rows dated T or later do differ), `::test_ac42_explicit_lookup_returns_nulls_for_a_missing_feature_row` |
| AC-43 | Pass | n/a | `test_labels.py::test_ac43_hand_computed_label_cases` (0, 1, null, null, null, 1; baselines within 1e-9), `::test_ac43_exact_bound_is_not_a_spike_and_threshold_is_a_parameter` |
| AC-44 | Partial (QR-19 detection only) | Pass (live 2026-10-22) | `test_labels.py::test_ac44_qr19_check_reports_a_violation`. PR 2 local data: `test_peak_seed42.py::test_ac44_seed42_label_counts` Pass (33,093 labelled, 14.5 to 14.7%, 2012-07-29 to 2014-02-27). Missing: deployed table (PR 3) |
| AC-45 | Pass | n/a | `test_labels.py::test_ac45_eligibility_fixture_cases` (late starter, dead meter, 0.80 and 0.7999, zero share 0.90, T = 2012-09-30 and 2012-10-01, 78 / 92), `::test_ac45_coverage_threshold_is_a_parameter` |
| AC-46 | Pass | n/a (unit only by design) | `test_labels.py::test_ac46_appending_later_months_keeps_eligibility_up_to_month_start` |
| AC-47 | Partial (invariants) | Pass (live 2026-10-22) | `test_labels.py::test_ac47_ineligible_rows_have_reasons_and_eligible_rows_none`. PR 2 local data: `::test_ac47_seed42_eligible_rows_per_split` Pass (16,969 / 7,170 / 5,116). Missing: deployed table (PR 3) |
| AC-48 | Pass (unit) | Pass (live 2026-10-22) | `test_training.py::test_ac48_splits_are_ordered_disjoint_and_equal_the_eligible_labelled_rows`, `::test_ac48_missing_feature_row_at_t_minus_1_fails_guard_g02`, `::test_ac48_overlapping_or_unordered_ranges_fail_guard_g09`, `::test_ac48_a_row_outside_the_ranges_is_rejected`. Missing: logged training set on the platform (PR 3) |
| AC-49 | Pass (unit) | Pass (live 2026-10-22) | `test_training.py::test_ac49_two_fits_give_identical_scores_threshold_and_metrics` (shuffled input, bitwise equal scores, equal t and metrics). Missing: two live runs (PR 3) |
| AC-50 | Pass (unit) | Pass (live 2026-10-22) | `test_training.py::test_ac50_run_parameters_cover_model_seed_and_fr31`, `test_peak_tables.py::test_ac50_training_parameters_exclude_the_scoring_only_target_date`, `::test_ac50_pinned_versions_are_checked_by_guard_g01` |
| AC-51 | Pass (unit) | Pass (live 2026-10-22) | `test_training.py::test_ac51_threshold_is_max_f1_with_highest_t_on_ties` (brute force over 400 random cases, a constructed tie, a single positive), `::test_ac51_run_threshold_equals_recomputation_from_validation_scores`, `::test_ac51_no_positive_validation_row_fails_before_any_effect` |
| AC-52 | Pass (unit) | Pass (live 2026-10-22) | `test_training.py::test_ac52_metric_names_cover_segments_with_counts_and_no_accuracy`, `::test_ac52_segment_without_positives_logs_no_pr_auc_and_precision_is_zero_without_flags`, `::test_ac52_ratio_rule_scores_null_total_as_zero_and_zero_baseline_as_1e_minus_6`. The PR-AUC > positive share check needs seed 42 (PR 3) |
| AC-53 | Pass | n/a | `test_training.py::test_ac53_empty_validation_month_fails_before_any_metric_or_registration` (error names 2013-09; no run, metric, model, tag or alias call; `champion` unchanged), `::test_ac53_a_commit_less_run_or_mismatched_parameters_fail_before_any_effect` |
| AC-54 | Pass (unit) | Pass (live 2026-10-22) | `test_training.py::test_ac54_pyfunc_wrapper_round_trip_reproduces_scores` (save and load with `code_paths`, max abs diff 0, signature over `FEATURE_COLUMNS`), `::test_ac54_encoding_uses_fixed_codes_and_unknown_values_become_nan`, `::test_ac54_register_logs_reloads_then_tags_then_moves_the_alias`, `::test_ac54_reload_mismatch_stops_before_the_tag_and_the_alias`. Missing: registry, alias and run records on the platform (DA-16, PR 3) |
| AC-55 | n/a (live only) | Pass (live 2026-10-22) | Live only: `test_peak_training.py::test_ac55_uc_lineage_lists_feature_table_upstream_of_model`, `::test_ac55_logged_versions_rebuild_the_same_training_set` |
| AC-56 | Pass (unit) | Pass (live 2026-10-22) | `test_scoring.py::test_ac56_predictions_cover_exactly_eligible_households_with_label_rule`, `::test_ac56_label_is_zero_below_the_threshold`, `::test_ac56_qr20_fails_on_a_duplicate_and_on_a_score_of_1_2` |
| AC-57 | Pass (unit) | Pass (live 2026-10-22) | `test_scoring.py::test_ac57_reassembly_is_identical_except_scored_at` |
| AC-58 | Pass (unit) | Pass (live 2026-10-22) | `test_scoring.py::test_ac58_default_target_date_is_day_after_latest_complete_day` |
| AC-59 | Pass (unit) | Pass (live 2026-10-22) | `test_scoring.py::test_ac59_range_resolves_to_89_dates` |
| AC-60 | Pass (unit) | Pass (live 2026-10-22) | `test_scoring.py::test_ac60_missing_feature_date_fails_before_write`, `::test_ac60_a_household_missing_from_the_feature_date_fails_before_write`, `::test_ac60_missing_label_rows_fail_before_write` |
| AC-61 | Pass (unit; live not possible by design) | n/a | `test_scoring.py::test_ac61_missing_champion_alias_fails_before_write`, `::test_ac61_champion_without_a_threshold_tag_fails_before_write`, `::test_ac61_champion_resolves_version_and_exact_threshold` |
| AC-62 | Pass (PR 2 unit) | Pass (live 2026-10-22) | `test_peak_bundle.py::test_ac62_daily_job_graph_schedule_and_pipeline_dependency`, `::test_ac62_training_is_on_demand_only`, `::test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged` (SHA-256 and `git show v0.1.0`, also `databricks.yml`), `::test_ac62_peak_model_adds_no_bundle_variable_and_uses_the_layout_variables`. Live: PR 3 |
| AC-63 | Pass (PR 2 unit and local data) | Pass (live 2026-10-22) | PR 2: `test_peak_bundle.py::test_ac63_label_and_eligibility_parameters_are_job_parameters`, `::test_ac63_job_parameters_reach_declared_notebook_widgets` (6 cases), `tests/local_data/test_peak_seed42.py::test_ac63_threshold_1_5_and_coverage_0_90` (7.91%, 29,100), `test_peak_tables.py::test_ac63_baseline_day_count_above_lookback_weeks_is_rejected`. PR 1: `test_peak_tables.py::test_ac63_parameters_default_parse_from_widgets_and_validate`, `::test_ac63_label_parameters_round_trip_through_table_properties`, `test_labels.py::test_ac63_label_parameters_are_recorded_as_table_properties`. Missing: widgets in `build_labels.py`, seed-42 figures (PR 2) |
| AC-64 | Pass (unit) | Pass (live 2026-10-22) | `test_peak_tables.py::test_ac64_library_schemas_equal_contracts_and_underscore_rule` (5 cases), `::test_ac64_non_nullable_contract_columns_hold_no_null` (4 cases), `::test_ac64_label_column_name_and_primary_keys_are_in_the_contracts`, `::test_ac64_ddl_nullability_and_feature_schema_follow_the_contracts`, `::test_ac64_ddl_properties_and_statement_order`, `::test_ac64_schema_precondition_names_the_missing_schemas`, `::test_ac64_object_names_follow_the_layout`, `::test_ac64_calendar_months_cover_partial_months`. Missing: deployed columns (PR 3) |
| AC-65 | Pass | n/a | `test_secrets_hygiene.py::test_ac65_tracked_files_contain_no_databricks_token`; `pre-commit run --all-files` (see Verification Log) |
| AC-66 | Pass (unit) | Pass (live 2026-10-22) | `test_peak_tables.py::test_ac66_merge_updates_only_changed_rows_and_deletes_missing_keys` (3 cases), `::test_ac66_merge_sql_rejects_bad_input_and_keys_only_tables_skip_the_update`, `::test_ac66_merge_metrics_replace_where_and_properties_text`, `::test_ac66_recomputation_with_another_partitioning_is_bitwise_equal` (weather, features, labels; 1 and 7 partitions; equal row counts and `xxhash64` checksums). Missing: MERGE on Delta, rebuild after reset (PR 3, DA-15) |
| AC-67 | Pass | n/a | `test_peak_model_adr.py::test_ac67_adr_0007_accepted_with_spike_05_outcomes_and_variant`, `::test_ac67_check_specs_reports_no_errors` |

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Baseline | `.venv/bin/python -m pytest -q` before any change (after installing the dev extras, D-01) | 203 passed, 47 deselected, 189 s |
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` | 93 files already formatted |
| Tests | `.venv/bin/python -m pytest -q` | **288 passed, 47 deselected** (203 before, 85 new: weather 10, features 9, labels 9, training 18, scoring 12, peak tables 27). Re-run after the review fixes; the first full run before them gave 286 passed in 361 s |
| Spec check | `.venv/bin/python scripts/check_specs.py` | 27 document(s) checked, 0 error(s), 0 warning(s) |
| Code review | `code-reviewer` subagent | 1 High, 5 Medium, 9 Low; see *Code review* |
| Hooks | `.venv/bin/pre-commit run --all-files` | all hooks passed (whitespace, end of files, yaml, large files, private key, merge conflicts, ruff, ruff-format, SDD spec gates) |
| Per-file checks | `ruff check`, `ruff format` and the related pytest file after each entry | passed (see Files Changed) |
| PR 2 lint | `ruff check . && ruff format --check .` | All checks passed; 102 files formatted |
| PR 2 tests | `pytest -q` (one full run after the last change) | **321 passed, 53 deselected** (288 before; 33 new), 364 s |
| PR 2 local data | `pytest -q -m local_data` | **20 passed** (14 METER_INGESTION + 6 new in `test_peak_seed42.py`); seed-42 figures of AC-44, AC-47, AC-63 reproduced by `src/` code |
| PR 2 specs and hooks | `check_specs.py`; `pre-commit run --all-files` | 28 documents, 0 errors; all hooks passed |
| PR 2 bundle | `databricks bundle validate -t dev --profile dev` | Validation OK; three jobs listed; `git_commit` resolved to HEAD (06ae807) |
| Unchanged inputs | `git status` | only the files listed above; no METER_INGESTION file, `databricks.yml` or `resources/` file changed |

---

## Deviations from Design

| ID | Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|---|
| D-01 | Local ML stack and pins | Dev extra `scikit-learn>=1.3,<1.4`, `numpy<2`, `mlflow-skinny>=2.16,<4`, `pyarrow>=15` | `pyarrow>=15,<22`. Installed into the project `.venv` (not the system): scikit-learn 1.3.2, numpy 1.26.4 (was 2.5.4), mlflow-skinny 3.17.2, pyarrow 21.0.0, scipy 1.17.1 and MLflow's dependencies | pyarrow 22 and later require NumPy 2, which scikit-learn 1.3 cannot import. The platform pin 1.3.0 stays in `peak_config.PINNED_REQUIREMENTS`; unit tests assert logic, not platform score values (DESIGN risk table) | Yes, /iterate 2026-10-21 (manifest entry 1 and integration extra read `pyarrow>=15,<22`) |
| D-02 | Delegation | Entries go to `ml-data-engineer` and `pipeline-builder` where named | All entries were implemented directly by the build agent | The libraries share one set of fixtures and cross-module contracts; no deviation in content | n/a |
| D-03 | G-09 extra rules | G-09: ranges ordered and disjoint; shares in (0, 1]; label threshold > 0; integers >= 1 | Also rejects `baseline_day_count > label_lookback_weeks` and `target_date_end` without or before `target_date` | The first can never find N baseline days and would silently label nothing; the second is the "end before start fails" case of AC-59 | Yes, /iterate 2026-10-21 (G-09) |
| D-04 | QR-18 parse | "A null result fails the step" | A temperature that parses to NaN or infinity also fails (`NaN` casts successfully in Spark) | NaN is not a number in the sense of QR-18 and would poison the daily mean | No |
| D-05 | G-02 and the training frame | G-02 is an anti-join count and a null check on the looked-up share | `training.check_feature_rows` runs in pandas against a `feature_keys` frame (household and feature date of the feature table at version VF) that the notebook must pass in `TrainingInputs` | `training.py` is pandas and scikit-learn only; the anti-join needs the key list, 36,480 rows | No |
| D-06 | Selecting training rows | Labels filtered "at version VL" (Spark side, implied) | `training.select_training_rows` filters the labels in pandas; `registry.build_training_set` receives those rows | One implementation of the rule, tested without Spark | No |
| D-07 | Scoring guard | G-06 checks the feature table only | `scoring.check_inputs` also fails when the labels table lacks one row per household at a target date | `replaceWhere` over a date with no label rows would silently delete that date's earlier predictions and write nothing | Yes, /iterate 2026-10-21 (G-06) |
| D-08 | Training-set checksum | "order-independent checksum" in the manifest | `training.frame_checksum` (sum of pandas row hashes modulo 2^64), not Spark `xxhash64` from `metrics.table_checksum_sql` | The training frame is a pandas object; PR 3's AC-55 rebuild check must use the same function on the rebuilt frame | No |
| D-09 | Extra tests outside the manifest names | Registry adapter has no test file in the manifest | `resolve_champion` and `MlflowTracker.register_model` are tested with fakes inside `tests/test_scoring.py` and `tests/test_training.py`; config and parameter tests are in `tests/test_peak_tables.py` | Keeps to the 23 listed files | n/a |
| D-10 | Contract keys | Contract template keys | The features and labels contracts add `timeseries_column`, `density`, `point_in_time` and `properties`; QR-17 uses action `drop` | The DESIGN asks the contracts to state the time-series column, the density rule, the point-in-time rule and the parameter properties; `check_specs.py` ignores unknown keys | No |
| D-11 | `build_training_set` date keys | Hand-off: cast `lookup_date` to date | Casts both `target_date` and `lookup_date` to DATE in `registry.build_training_set` (PR 1 file) | pandas timestamps would reach the lookup as TIMESTAMP | No (test row added) |
| D-12 | Extra tests | Not in the manifest | `test_ac48_training_set_lookup_uses_date_keys_the_spike_shape_and_guard_g04`; the two G-09 tests | Close the PR 1 review gap and the /iterate test gap | Yes (Test Strategy rows, this PR) |
| D-13 | Label dtype | - | `training.select_training_rows` casts the label to int | `toPandas` on a nullable int gives float, and the lookup frame would carry a double label | Yes, /iterate 2026-10-21 (Training set "Label type" bullet) |
| D-14 | Local-data schema helper | - | `StructType(list(schema.fields)).add(...)` in both local-data modules | `StructType.add` mutates the shared library schema, so a second use fails with a duplicate `_corrupt` column | No (test-only) |
| D-15 | Widgets in notebooks | `from_widgets` gets declared names | Notebooks call `PeakParameters.from_mapping` over declared widget names; `from_widgets` is unused (a test forbids it in `build_labels`) | `from_widgets` reads all 15 fields | No (behaviour as the hand-off asks) |
| D-16 | Where tables are created | DDL in `ingest_weather` | Every notebook that needs the tables calls `peak_setup.ensure_tables` (ingest_weather, build_features, build_labels, score_predictions), which imports the ML stack through `scoring` | The partial bootstrap run and reruns must not depend on order | No |
| D-17 | Empty-Bronze stop | - | `build_weather_silver` raises when the recomputed Silver has 0 rows | The MERGE would delete every Silver row | Yes, /iterate 2026-10-21 (new guard G-12 and MERGE note) |
| D-18 | Delegation | Named agents per entry | Implemented directly (as D-02) | - | n/a |
| D-19 | Serverless environment | Notebook tasks with no explicit environment (spike 05 ran on the one-off default) | Both job files declare `peak_model_env` with `environment_version: "2"` and every notebook task uses it; test `test_g01_every_notebook_task_runs_on_serverless_environment_version_2` | PR 2 gate run 568274842588512: the bundle job ran on Python 3.12, `%pip install ... scikit-learn==1.3.0` built from source and failed (`metadata-generation-failed`) in `build_features`, both attempts. Probe: environments 2 and the one-off default are Python 3.11 with scikit-learn 1.3.0; 3 is Python 3.12 with 1.4.2; 4 is Python 3.12 with 1.6.1 and numpy 2.1. User chose environment 2 | Yes, /iterate 2026-10-21 (G-01, risk row, ADR 0007 note) |
| D-20 | Version lookup after `fe.log_model` | Find the new version by run id (PR 1 review fix) | `register_model` searches with `name = '...'` only and matches `run_id` in Python; fails clearly when the run registered none; test `test_ac54_register_finds_the_version_of_this_run_with_a_name_only_filter` (the fake client now rejects other filters, as UC does) | PR 2 gate training run 833313033243922: UC rejected `name = ... and run_id = ...` with `INVALID_PARAMETER_VALUE` after the version was registered | Yes, DESIGN change log 2026-10-21 |
| D-21 | No retry of `train_model` | `max_retries: 0` | Also `disable_auto_optimization: true`; test `test_ac53_training_task_is_never_retried_by_the_platform` | The same run had a second attempt: serverless auto-optimization retries failed tasks even with `max_retries: 0` (the deployed task shows `max_retries` unset). Each attempt registered a version: versions 1 and 2 exist with no alias | Yes, DESIGN change log 2026-10-21; ADR 0008 note |
| D-22 | G-08 reload input | Reload and predict on the feature columns | `registry.reload_input` passes the columns of the registered signature in its order, with `target_date` as a timestamp; `training` passes the test rows with `household_id` and `target_date`; test `test_ac54_reload_uses_the_registered_signature_with_the_fe_lookup_keys`; checked locally against the real signature of version 3 | PR 2 gate training run 252193727620814 (one attempt, D-21 works): `fe.log_model` adds the lookup keys to the signature, so schema enforcement rejected the features-only frame (`Model is missing inputs ['household_id', 'target_date']`); version 3 was registered, G-08 stopped before the tag and the alias | Yes, DESIGN change log 2026-10-21 |
| D-23 | G-08 reload through `fe.score_batch` (supersedes D-22) | `mlflow.pyfunc.load_model` and `predict` | `registry.fe_reload_scores` scores the new version with `fe.score_batch(model_uri="models:/<name>/<version>")` on the test keys with `lookup_date = target_date - 1`, as scoring does, and aligns the result to the input order; `reload_input` removed; test `test_ac54_reload_scores_through_fe_score_batch_by_version_in_input_order` | PR 2 gate training run 725822033088610: a model logged with `fe.log_model` cannot be scored after `pyfunc.load_model` on serverless (`score_batch with local_uri is not supported on serverless runtime`); version 4 registered without an alias. A one-off probe scored the 5,116 logged test rows of version 4 with `fe.score_batch` by version: max abs diff 0 | Yes, DESIGN change log 2026-10-21 |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | `registry.py` (`ensure_feature_table`, `build_training_set`, `table_version`, `MlflowTracker.log_inputs`, the real `fe.log_model` kwargs incl. `code_paths`) and `delta_sync` MERGE / `DESCRIBE HISTORY` / `replaceWhere` are not executable locally | Medium | PR 2 gate: DA-13 to DA-18 on `dev` before PR 3. Done 2026-10-22: DA-14 to DA-18 Pass; DA-13 retry part Fail, DESIGN fallback applied through `/iterate` |
| I-02 | `scoring.py` imports `registry.Champion`, which imports `model.py`, so scoring needs scikit-learn and MLflow importable | Low | Acceptable: the scoring notebook pins them. Move `Champion` to `peak_config` if the dependency grows |
| I-03 | Silver and label steps recompute their input for each count and check (no cache on serverless) | Low | Cheap at this volume (ADR 0011 revisit trigger) |
| I-04 | The local MLflow prints a warning that `predict` has no type hints | Low | Cosmetic; type hints are not used because `fe.score_batch` passes a pandas frame |
| I-05 | No notebook or bundle resource exists yet, so nothing consumes the libraries | Info | PR 2 |

---

## Code review (PR 1)

| Severity | Finding | Handling |
|---|---|---|
| High | `.cache()` in `weather.py` (2), `labels.py`, `scoring.py` (2); not supported on serverless | Fixed: all removed; `scoring.run` materialises the prediction rows once with `collect()` and `createDataFrame`; new test `test_ac66_no_cache_or_persist_in_library_code_for_serverless`. To confirm on `dev` at the PR 2 gate |
| Medium | `last_merge_metrics` could report an earlier MERGE on a no-op rerun | Fixed: `merge_changes` reads the version before; only a newer MERGE counts, else zeros; test added |
| Medium | New model version taken as `max(version)` | Fixed: filtered by the run id. Reading `ModelInfo` from `fe.log_model` stays an option |
| Medium | No test for `build_training_set` G-04, `FeatureLookup` args, `ensure_feature_table`; `lookup_date` dtype; G-04 vs OPTIMIZE versions | Open: PR 2 gate (needs the FE client). Cast `lookup_date` to date when wiring |
| Medium | AC-64 Bronze contract compared with a test builder | Open (Low impact: `weather.BRONZE_COLUMNS` equals the contract via the AC-36 and DDL tests) |
| Medium | Non-UTC session proven for weather only | Open: add features, labels, scoring runs under London and Los Angeles in PR 2 |
| Low | Threshold tag nan/inf; naive `scored_at`; integer offsets not logged | Fixed (tag must lie in (0, 1]; naive `scored_at` raises; offsets logged in `categorical_codes`) |
| Low | `from_widgets` reads all 15 widgets; `peak_setup` imports ML stack via `scoring`; `int()` on a bad property; trivial writer assertion in AC-38; unreachable end-before-start branch; extra G-09 rule | Open or accepted (extra rule is D-03). `from_widgets` must get the declared widget names in PR 2 |

## Code review (PR 2)

`code-reviewer` subagent: 0 High, 5 Medium, 6 Low.

| Severity | Finding | Handling |
|---|---|---|
| Medium | `train_model` reads table properties from the current table, not at VL / VF | Fixed: versions re-checked after the properties are read; a change raises |
| Medium | `_widget_names` tuple decorative; bundle test trusted it | Fixed: `widget_names()` collects the real declarations and asserts equality with the tuple |
| Medium | Wiring test checks only that attributes exist | Open: argument binding via `inspect.signature` is a PR 3 / follow-up item; the gate runs the real calls |
| Medium | Features and labels not tested under non-UTC sessions | Open: weather is; derived tables follow the notebooks' UTC assertion. Follow-up |
| Medium | Empty Bronze would empty Silver via MERGE | Fixed (D-17) |
| Low | Pins test named AC-49; weak restart order | Fixed: renamed `test_g01_...`, asserts restart precedes `sys.path.insert` |
| Low | UTC test also holds hygiene checks | Accepted |
| Low | Tautology in widget test | Fixed |
| Low | FeatureLookup stand-in accepts any kwargs | Accepted: real kwargs verified at the gate (DA-15) |
| Low | G-05 only inside `run_training` | Fixed: checked after the widget read |
| Low | Label dtype float after `toPandas` | Fixed (D-13) |
| Low | `SET TBLPROPERTIES` commits a version on every run; G-04 counts OPTIMIZE versions | Open: watch at the gate (a no-op rerun must still show 0 MERGE changes; G-04 may fail after maintenance) |

---

## Code review (PR 3)

`code-reviewer` subagent on the PR 3 files: 0 High, 4 Medium, 10 Low.

| Severity | Finding | Handling |
|---|---|---|
| Medium | AC-55 1B check cast integer features to float64, so the pandas hash could not match the manifest | Fixed: `target_weekday`, `target_month`, `temperature_hour_count_1d` cast to int32 as in the training frame |
| Medium | AC-56 asserted `len(both) == len(logged) == len(stored)`, but predictions also cover eligible unlabelled rows | Fixed: every logged row must have a prediction; max abs difference 0 on the join |
| Medium | Reset flow never reached the AC-66 rebuild branch (runbook ran the daily job before `ac66_after`) | Fixed: after the reset, `ac66_after` starts the four data tasks itself; runbook, test docstring and script message agree |
| Medium | Idle guard only for runs with `refresh_silver_gold` | Fixed: `PeakRunner.run` checks ingestion job and pipeline idle for every run; runbook asks for idle ingestion during the whole evidence sequence |
| Low | Vacuous duration budgets (equal to job timeouts) | Accepted: durations are saved as evidence (NFR-14); budgets equal the YAML timeouts |
| Low | `HAVING` on a select alias (AC-37) | Fixed: subquery with `WHERE` |
| Low | `THREE_TASKS` holds four tasks; redundant assert; unused `workspace` argument | Fixed |
| Low | `_scored_at` compared as string | Fixed: `unix_micros` |
| Low | Timed-out run keeps running | Fixed: `cancel_run` before failing |
| Low | `git_commit` check goes stale after a redeploy | Accepted: runbook says to retrain after a redeploy |
| Low | Reset script: connection outside the `try`, no active-run check, no `main()` test | Open: user-run guarded script with a dry-run default; row-count and snapshot checks cover the intended safety. Follow-up if wanted |
| Low | `tests/test_peak_reset_script.py` and the layout test change are outside the manifest list | Accepted, listed in Files Changed |

## PR 2 gate (steps for the user; nothing below was run)

Prerequisites: PR 2 committed and merged or at least committed on the branch, so `git status --porcelain` is empty and `bundle.git.commit` is the code that runs. METER_INGESTION is deployed and its data is loaded. Run with the `dev` profile. Deploy and run are user actions.

1. `databricks bundle validate -t dev --profile dev`, then `databricks bundle deploy -t dev --profile dev`.
2. Upload the weather file once: `databricks fs cp data/raw/weather_hourly_darksky.csv dbfs:/Volumes/smart_meter_dev/bronze/landing/weather/ --profile dev`.
3. Partial daily run: `databricks bundle run -t dev --profile dev smart_meter_peak_model --only refresh_silver_gold,ingest_weather,build_weather_silver,build_features,build_labels`.
   - DA-13: the `pipeline_task` of a second job starts an update. Then start `smart_meter_ingestion` and, while it runs, `bundle run ... smart_meter_peak_model --only refresh_silver_gold`: expect a refused update (DESIGN before the 2026-10-22 `/iterate` also expected a successful retry after 600 s; see the gate log).
   - DA-14: widgets receive the job parameters (exit value of `build_labels` shows the parameters). Override check: `--params label_threshold=1.5,coverage_min=0.90` with `--only build_labels` (expect 7.91% and 29,100), then rerun with defaults.
   - DA-15: first `build_features` run MERGEs into the `fe.create_table` table (exit value `merge`; a rerun reports 0 / 0 / 0).
   - DA-18: `SHOW TBLPROPERTIES smart_meter_dev.ml.household_features_daily` and the labels table show the 90-day `delta.*RetentionDuration` and the `smart_meter.*` properties.
   - Expect 21,165 Bronze weather rows and 36,480 rows in each ML table.
4. Training: `databricks bundle run -t dev --profile dev smart_meter_peak_model_training`.
   - DA-15: `create_training_set` works on the MERGEd table. DA-16: G-08 passes (`champion_reload_max_abs_diff` 0). DA-17: the run parameter `git_commit` is 40 hex and equals the deployed commit.
5. Full daily run: `databricks bundle run -t dev --profile dev smart_meter_peak_model` (scores 2014-02-28; exit value names feature date 2014-02-27).
6. Record the exit values, run URLs and durations in this report. Any failed DA applies its DESIGN fallback through `/iterate` before PR 3.

**Gate log.**

- 2026-10-21, deploy of main `db67283` and weather upload: OK.
- 2026-10-21, step 3, run 568274842588512: `refresh_silver_gold` (173 s), `ingest_weather` (79 s), `build_weather_silver` (25 s) and `build_labels` (60 s) succeeded; `build_features` failed in `%pip` on both attempts (Python 3.12 environment, D-19). Fixed by pinning serverless environment version 2; the gate restarts at step 3.
- 2026-10-21, step 3 rerun, run 935178667816547 (environment 2): all five tasks succeeded. Bronze and Silver weather 21,165 rows; features and labels 36,480 rows each with unique keys; 33,093 labelled at 14.61% positive; 29,255 eligible. Features created as an FE table, MERGE inserted 36,480. DA-18 Pass: both tables carry the 90-day retention properties and the `smart_meter.*` parameters.
- 2026-10-21, DA-15 rerun, run 211913268603650: `build_features` MERGE 0 / 0 / 0 (Pass); the table version still rose from 5 to 8 (property updates commit versions; code-review item).
- 2026-10-21, DA-14 and AC-63, run 441478403476938 (`label_threshold=1.5`, `coverage_min=0.90` as job parameters): 2,618 of 33,093 positive (7.91%), 29,100 eligible (Pass). Run 217472839647775 restored the defaults (4,836 positives, 29,255 eligible).
- 2026-10-21, step 4 training, run 833313033243922: failed on both attempts after registering versions 1 and 2 (D-20, D-21); `champion` not set. Fixed; the gate restarts at step 4.
- 2026-10-21, step 4 training rerun, run 252193727620814: one attempt only (D-21 Pass); failed in G-08 because the FE signature includes the lookup keys (D-22); version 3 registered, `champion` not set. Fixed; the gate restarts at step 4.
- 2026-10-21, step 4 training rerun, run 725822033088610: one attempt; G-08 failed because the pyfunc reload of an FE model calls `score_batch` with a local URI, rejected on serverless (D-23); version 4 registered, `champion` not set. Probe: `fe.score_batch` by version reproduced version 4's 5,116 test scores exactly. Fixed; the gate restarts at step 4.
- 2026-10-21, step 4 training, run 735894206202095 (main `efe0e49`): **Pass**, one attempt, 121 s. Version 5 registered, `champion` = 5, `decision_threshold` 0.24259314696216627 (validation F1 at t 0.482), 29,255 training rows, labels and features at Delta version 8. DA-15 Pass (`create_training_set` on the MERGEd table). DA-16 Pass (`champion_reload_max_abs_diff` 0 through `fe.score_batch`). DA-17 Pass (`git_commit` equals the deployed commit). AC-50 parameters logged. AC-52: test PR-AUC 0.4637 above the test positive share 13.6%; ratio rule test PR-AUC 0.4317 (validation: model threshold-tuned, ratio rule 0.4748); test precision and recall at t 0.452 and 0.452 (695 flags, 694 positives in 5,116 rows).
- 2026-10-21, step 5 full daily run, run 955661850767978: **Pass**, 255 s, every task on its first attempt. Weather, features and labels reran with MERGE 0 / 0 / 0. `score_predictions` scored target date 2014-02-28 from feature date 2014-02-27 with version 5: 58 rows (58 eligible households), 3 flagged, scores 0.015 to 0.817 (AC-56, AC-58).
- 2026-10-22, DA-13, ingestion run 1002990004411119 and peak run 839517104898682 (`--only refresh_silver_gold`, started while the ingestion `refresh_silver_gold` was running): **Fail (retry part)**. The peak update was refused in about 2 s ("Pipeline update already in progress"), but the task ended in `INTERNAL_ERROR`, which the job does not retry: no second attempt despite `max_retries: 1` and `min_retry_interval_millis: 600000`. The ingestion run succeeded (188 s, every task on its first attempt), unaffected. The DESIGN fallback applies (schedule offset, accept the failed run, the next daily run is the retry; concurrent use in the runbook), recorded through `/iterate` on 2026-10-22.
- 2026-10-22, model cleanup: versions 1 to 4 of `smart_meter_dev.ml.consumption_spike_model`, left by the failed training attempts, had no alias and were deleted (ADR 0007 order: aliases first, so only versions without one). Version 5 (`champion`) is the only version left.
- 2026-10-22, METER_INGESTION follow-up F-02: the deployed `smart_meter_ingestion` job shows `max_retries` unset on `ingest_kafka` and `refresh_silver_gold` and no `disable_auto_optimization`, the same pattern as D-21. The likely cause of the second `ingest_kafka` attempt is serverless auto-optimization; the fix (`disable_auto_optimization: true` on `ingest_kafka`) goes through `/iterate` on METER_INGESTION, outside PEAK_MODEL.

---

## PR 2 hand-off (what PR 2 must do next)

1. Create entries 24 to 35 in order: notebooks `ingest_weather`, `build_weather_silver`, `build_features`, `build_labels`, `score_predictions`, `train_model`; the two job resource files; `tests/test_peak_bundle.py`, `tests/test_peak_model_adr.py`, the `dapi` test in `tests/test_secrets_hygiene.py`, and `tests/local_data/test_peak_seed42.py`.
2. Notebook wiring that PR 1 expects:
   - set and assert `spark.sql.session.timeZone = UTC`; no try/except; a `_widget_names` tuple per notebook;
   - the three ML notebooks start with `%pip install --quiet databricks-feature-engineering==0.18.2 scikit-learn==1.3.0` and a restart, then call `peak_config.check_versions()` (G-01);
   - `build_weather_silver`: `weather.silver_weather(bronze)`, then `delta_sync.merge_changes(...)`, then print counts (`row_count`, `duplicate_count`, `out_of_range_count`) and the MERGE metrics;
   - `build_features`: `peak_setup.ensure_tables`, `registry.ensure_feature_table(fe, spark, name, peak_setup.feature_table_schema())`, `peak_setup.feature_retention_sql`, `features.build_features`, `features.check_features`, `merge_changes`, then `set_properties_sql(features.feature_table_properties(params))`;
   - `build_labels`: `PeakParameters.from_widgets(dbutils.widgets.get)`, `labels.build_labels` (runs QR-19 and G-10), `merge_changes`, `set_properties_sql(labels.label_table_properties(params))`;
   - `score_predictions`: `scoring.run(..., champion=lambda: registry.resolve_champion(client, model_name), scorer=registry.fe_scorer(fe), writer=scoring.table_writer(predictions_table))`; print `ScoringResult.summary()`;
   - `train_model`: read the labels table pandas, `training.select_training_rows`, `registry.build_training_set` (G-04), read both table properties and versions, pass `feature_keys`, `git_commit` (G-05) and `registry.library_versions()` in `training.TrainingInputs`, run `training.run_training` with `registry.MlflowTracker(mlflow=mlflow, client=MlflowClient(), fe=fe, training_set=training_set, model_name=...)`.
3. `tests/test_peak_bundle.py` must read the widget names from the notebooks and compare them with the job parameters (the library accepts exactly the `PeakParameters` field names), and compare `%pip` pins with `peak_config.PINNED_REQUIREMENTS`.
4. Local-data tests (entry 35) build Gold through `tests/support/harness.py` and call `features.build_features`, `labels.build_labels` with `study_start` 2012-07-01; expect 36,480 rows, 33,093 labels, split counts 16,969 / 7,170 / 5,116.
5. ~~Update DESIGN entry 1 text for D-01 through `/iterate`~~ Done: `/iterate` 2026-10-21 (with D-13 and D-17).
6. After PR 2 is deployed: run the *Gate after PR 2* (bootstrap sequence), which checks DA-13 to DA-18, before PR 3.

## PR 3: integration tests, reset script, runbook (entries 36 to 44)

The integration tests carry the `integration` marker and need the deployed `dev` workspace. They
were run on 2026-10-22 (see *PR 3 live run* below): 27 of 27 pass. Dates and numbers in the assertions are the
figures of ADR 0007 / spike A-17 and the DESIGN Test Strategy.

| AC | Live test (file `tests/integration/`) | Live status |
|---|---|---|
| AC-36 | `test_peak_data.py::test_ac36_bronze_weather_has_21165_rows_and_rerun_adds_none` | Pass (2026-10-22) |
| AC-37 | `test_peak_data.py::test_ac37_silver_weather_range_uniqueness_and_dst_days` | Pass (2026-10-22) |
| AC-39 | `test_peak_data.py::test_ac39_feature_temperature_matches_silver_weather` | Pass (2026-10-22) |
| AC-40 | `test_peak_data.py::test_ac40_every_feature_matches_sql_recomputation` (oracle SQL checked on local Spark: 0 differences) | Pass (2026-10-22) |
| AC-41 | `test_peak_data.py::test_ac41_deployed_feature_and_label_keys_are_complete` | Pass (2026-10-22) |
| AC-44 | `test_peak_data.py::test_ac44_deployed_label_counts_and_qr19` | Pass (2026-10-22) |
| AC-47 | `test_peak_data.py::test_ac47_deployed_eligible_rows_per_split` | Pass (2026-10-22) |
| AC-48 | `test_peak_training.py::test_ac48_logged_training_set_equals_labels_and_features_at_t_minus_1` | Pass (2026-10-22) |
| AC-49 | `test_peak_training.py::test_ac49_two_training_runs_are_identical` (needs two training runs on unchanged tables) | Pass (2026-10-22) |
| AC-50 | `test_peak_training.py::test_ac50_logged_parameters` | Pass (2026-10-22) |
| AC-51 | `test_peak_training.py::test_ac51_version_tag_equals_recomputed_threshold` | Pass (2026-10-22) |
| AC-52 | `test_peak_training.py::test_ac52_seed42_metrics_and_signal` | Pass (2026-10-22) |
| AC-53 | unit only by DESIGN (no live test) | n/a |
| AC-54 | `test_peak_training.py::test_ac54_registered_version_alias_reload_and_run_records` | Pass (2026-10-22) |
| AC-55 | `test_peak_training.py::test_ac55_uc_lineage_lists_feature_table_upstream_of_model`, `::test_ac55_logged_versions_rebuild_the_same_training_set` | Pass (2026-10-22) |
| AC-56 | `test_peak_scoring.py::test_ac56_predictions_for_t_match_eligibility_threshold_and_model` (after AC-59) | Pass (2026-10-22) |
| AC-57 | `test_peak_scoring.py::test_ac57_before_rescore_snapshot`, `::test_ac57_after_rescore_only_scored_at_changes` | Pass (2026-10-22) |
| AC-58 | `test_peak_scoring.py::test_ac58_run_without_target_date_scores_2014_02_28` | Pass (2026-10-22) |
| AC-59 | `test_peak_scoring.py::test_ac59_backfill_covers_test_range_and_rerun_changes_only_scored_at` | Pass (2026-10-22) |
| AC-60 | `test_peak_scoring.py::test_ac60_target_beyond_features_fails_and_writes_nothing` | Pass (2026-10-22) |
| AC-62 | `test_peak_deployment.py::test_ac62_deployed_jobs_pipeline_and_run_durations` | Pass (2026-10-22) |
| AC-63 | `test_peak_data.py::test_ac63_before_parameter_run_snapshot`, `::test_ac63_after_parameter_run_and_restore` | Pass (2026-10-22) |
| AC-64 | `test_peak_data.py::test_ac64_deployed_columns_match_contracts` | Pass (2026-10-22) |
| AC-66 | `test_peak_data.py::test_ac66_before_rebuild_snapshot`, `::test_ac66_after_rerun_and_rebuild_checksums_equal` (rebuild leg after the user-run reset script) | Pass (2026-10-22) |

Design points of the tests worth knowing when reading a failure:

- The tests start jobs only with `only=` task lists that avoid `refresh_silver_gold`, except where a
  full daily run is a precondition the user runs by hand. `PeakRunner.run` refuses any run that
  includes `refresh_silver_gold` while `smart_meter_ingestion` runs or the pipeline is not `IDLE`
  (DA-13). `test_ac62` also asserts idleness first and starts nothing.
- AC-63 `after` starts `build_labels` with `label_threshold=1.5` and `coverage_min=0.90`, and
  restores the defaults in a `finally` block before comparing the checksum with the snapshot.
- AC-66 `after` detects the rebuild leg (a table missing after the reset script) and then expects
  the MERGE to insert exactly the snapshot row counts; otherwise it expects 0 inserted, 0 updated,
  0 deleted.
- AC-49 compares the two newest finished training runs and fails with an instruction when their
  source table versions differ.

### Commands the user must run (live evidence)

```bash
export DATABRICKS_CONFIG_PROFILE=dev        # and optionally DATABRICKS_WAREHOUSE_ID
git status --porcelain                      # must print nothing
databricks bundle validate -t dev -p dev; echo "validate exit $?"
databricks bundle deploy -t dev -p dev;   echo "deploy exit $?"
# ingestion job idle? then, in the order of docs/runbooks/peak_model.md sections 3, 4 and 8:
pytest -m integration tests/integration/test_peak_data.py -k "ac36 or ac37 or ac39 or ac40 or ac41 or ac44 or ac47 or ac64"
pytest -m integration tests/integration/test_peak_data.py -k "ac63"
pytest -m integration tests/integration/test_peak_data.py -k "ac66_before"
python scripts/reset_peak_model_outputs.py            # dry run; add --confirm, then run the daily job (optional rebuild leg)
pytest -m integration tests/integration/test_peak_data.py -k "ac66_after"
pytest -m integration tests/integration/test_peak_training.py          # after two training runs
pytest -m integration tests/integration/test_peak_scoring.py -k "ac58 or ac59 or ac56"
pytest -m integration tests/integration/test_peak_scoring.py -k "ac57"
pytest -m integration tests/integration/test_peak_scoring.py -k "ac60"
pytest -m integration tests/integration/test_peak_deployment.py        # after a full daily run
pre-commit run --all-files                                             # AC-65 evidence
```

---

### PR 3 verification (local, 2026-10-22)

- `ruff check .` and `ruff format --check .`: clean (109 files).
- `pytest -q` (full, before the review fixes): 329 passed, 80 deselected (integration and local_data), 252 s. After the review fixes: `tests/test_integration_layout.py`, `tests/test_peak_reset_script.py`, `tests/test_peak_bundle.py` rerun, 39 passed.
- `pytest --collect-only -m integration -o addopts= tests/integration/test_peak_*.py`: 27 tests collected.
- `python3 scripts/check_specs.py`: 28 documents, 0 errors, 0 warnings.
- AC-40 oracle SQL run on local Spark against `features.build_features` (messy fixture): 0 differing rows in all 12 features.
- Status was `In Progress` until the live run below.

### PR 3 live run (`dev`, 2026-10-22)

- Deploy of branch `build/peak-model-pr3` at `06fbc59` (main `e380c90` plus PR 3, which changes only tests, a script and docs): `bundle validate` exit 0, `bundle deploy` exit 0 (AC-62). Ingestion job, both PEAK_MODEL jobs and the pipeline idle before every step.
- Bootstrap: training runs 800890504587740 (182 s) and 683019748253644 (141 s), unchanged tables, registered versions 6 and 7; `champion` = 7. Full daily run 590469021014875: Success, 293 s (281 s run time; `refresh_silver_gold` 123 s, `build_features` 79 s, `score_predictions` 78 s).
- Integration tests, in the runbook order (`pytest -o addopts= -m integration`):
  - `test_peak_data.py` AC-36, 37, 39, 40, 41, 44, 47, 64: 8 passed (106 s). AC-63 pair: 2 passed (140 s; defaults restored). AC-66 before and after: 2 passed; the rebuild leg was **not** run (`rebuild_after_reset` false): the rerun MERGEs were 0 / 0 / 0 for Silver weather, features and labels. The reset script itself was not run.
  - `test_peak_training.py`: 8 passed (196 s), AC-48 to 52, 54, 55 (UC lineage and the rebuild of the logged training set), AC-49 on runs 800890504587740 and 683019748253644.
  - `test_peak_scoring.py`: AC-58, 59, 56: 3 passed (363 s); AC-57 pair: 2 passed (108 s); AC-60: 1 passed (106 s).
  - `test_peak_deployment.py` AC-62: failed on the first run because of two test defects, then 1 passed (9 s): `jobs.list` returns settings without the job parameters, so `_job_named` now reads the full job with `jobs.get`; the pipeline API omits `continuous` when false, so the test compares `bool(...)`. `ac66_before` rerun after the fixture change: pass.
- AC-65: `pre-commit run --all-files` clean on the staged tree (the hook ruff v0.6.9 and the CI ruff format long asserts differently; the asserts concerned are written in a form both accept).
- Not live by design: AC-53 (unit only), AC-61 (would delete the shared alias). AC-66 rebuild leg (run during `/ship`, 2026-10-22): reset dry run, then `--confirm` dropped only the three tables; `ac66_after` passed in 226 s (MERGE inserted 21,165 / 36,480 / 36,480 rows, checksums equal to the snapshot, `rebuild_after_reset` true). A scoring-only run afterwards (937391410963735, Success) scored with `champion` 7 against the rebuilt feature table.

## Self-Review

- **Weak points:**
  - The platform-facing code (`registry.py`, the Delta writers in `delta_sync.py`, `peak_setup.ensure_tables`) is tested only through fakes and SQL text. DA-15, DA-16 and DA-17 are still assumptions.
  - Local scikit-learn is 1.3.2, the platform pin is 1.3.0. The tests assert logic, not scores; AC-49 on the platform stays live-only.
  - The `Tracker` protocol and `TrainingInputs` are my interpretation of "orchestration over a Tracker protocol" (DESIGN entry 9). PR 2's `train_model` notebook has to follow them exactly (see hand-off).
  - Seed-42 figures (33,093 labels, split counts, 36,480 rows) are not checked until PR 2's local-data test.
- **Risks:**
  - `fe.log_model(..., code_paths=[package folder])` may not forward `code_paths` (DA-16); the fallback is in the DESIGN.
  - A MERGE into a feature table made by `fe.create_table` may break the lookup (DA-15).
  - `numpy<2` and `pyarrow<22` in the dev extra tie the local environment to the serverless stack.
- **What I would do differently:** split `registry.py` into a pure part (champion resolution, version helpers) and a platform part, so the pure part needs neither MLflow nor the FE client and `scoring.py` stays free of scikit-learn.
- **Next improvement:** build PR 2 (entries 24 to 35) from the hand-off above, then run the PR 2 gate on `dev`.

---

## Next Step

Merge PR 3 (#21), then `/ship PEAK_MODEL`. Follow-ups for SHIPPED: the optional AC-66 rebuild leg, bumping the pre-commit ruff pin, the open Low of the PR 3 review (reset script without an active-run check), and METER_INGESTION F-02.
