# BUILD REPORT: Peak Model

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL |
| **Date** | 2026-10-21 |
| **Source** | DESIGN_PEAK_MODEL.md (status Ready for Build) |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

One report covers the whole feature (DESIGN *Delivery Plan*). It stays `In Progress` until PR 3.

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
| PR 2 | 24 to 35 | **Built and verified locally**; platform gate pending (see *PR 2 gate*) |
| PR 3 | 36 to 44 | Not started |

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

---

## Acceptance Criteria Evidence

**Local** is the PR 1 unit evidence (real test output, see the Verification Log). **Live** is the
platform evidence and is `Not run` for every AC at this point: the integration tests, notebooks and
bundle resources belong to PR 2 and PR 3. `PR 2` and `PR 3` mark where the remaining evidence comes
from. AC-65 and AC-67 are decided by tests of PR 2.

| AC | Local (PR 1) | Live | Test names (PR 1) and what is still missing |
|---|---|---|---|
| AC-36 | Pass (projection) | Not run | `test_weather.py::test_ac36_bronze_projection_keeps_raw_columns_and_metadata`, `::test_ac36_raw_names_cover_every_source_column_once`. Missing: Auto Loader run and 21,165 rows (PR 2 notebook 24, PR 3 `test_peak_data.py`) |
| AC-37 | Pass (unit) | Not run | `test_weather.py::test_ac37_weather_ts_is_independent_of_session_time_zone` (four DST days, UTC and Europe/London, 24 rows each). PR 2 local data: `::test_ac37_raw_weather_file_same_in_utc_and_london` Pass (21,165 rows, UTC = London). Missing: deployed table |
| AC-38 | Pass | n/a | `test_weather.py::test_ac38_unparseable_time_fails_before_write`, `::test_ac38_null_time_fails_before_write`, `::test_ac38_non_numeric_temperature_fails_before_write`, `::test_ac38_duplicate_time_keeps_earlier_ingested_and_counts_one`, `::test_ac38_temperature_50_is_kept_and_warn_count_is_one`, `::test_ac38_silver_schema_has_the_contract_columns` |
| AC-39 | Pass (unit) | Not run | `test_weather.py::test_ac39_day_without_weather_has_count_0_and_null_mean`, `test_features.py::test_ac39_mean_temperature_matches_recomputation_and_is_order_stable` (1, 3 and 8 partitions bitwise equal). PR 2 local data: `::test_ac39_seed42_temperature_hour_counts` Pass. Missing: deployed table (PR 3) |
| AC-40 | Pass (unit) | Not run | `test_features.py::test_ac40_features_match_independent_recomputation` (3 parameter sets, 0 mismatches, nulls in the same places), `::test_ac40_feature_table_columns_match_the_contract_order`. Missing: SQL recomputation on the deployed table (PR 3) |
| AC-41 | Pass (unit) | Not run | `test_features.py::test_ac41_feature_grid_is_dense_and_density_check_fails_on_gap`, `::test_ac41_feature_table_not_null_columns_hold_no_null`, `test_labels.py::test_ac41_label_grid_is_dense_with_target_date_plus_one`. PR 2 local data: `::test_ac41_seed42_tables_have_36480_rows` Pass. Missing: deployed tables (PR 3) |
| AC-42 | Pass | n/a | `test_features.py::test_ac42_changing_data_from_t_leaves_earlier_features_and_training_rows_unchanged` (features before T, labels before T and the training rows of T identical; rows dated T or later do differ), `::test_ac42_explicit_lookup_returns_nulls_for_a_missing_feature_row` |
| AC-43 | Pass | n/a | `test_labels.py::test_ac43_hand_computed_label_cases` (0, 1, null, null, null, 1; baselines within 1e-9), `::test_ac43_exact_bound_is_not_a_spike_and_threshold_is_a_parameter` |
| AC-44 | Partial (QR-19 detection only) | Not run | `test_labels.py::test_ac44_qr19_check_reports_a_violation`. PR 2 local data: `test_peak_seed42.py::test_ac44_seed42_label_counts` Pass (33,093 labelled, 14.5 to 14.7%, 2012-07-29 to 2014-02-27). Missing: deployed table (PR 3) |
| AC-45 | Pass | n/a | `test_labels.py::test_ac45_eligibility_fixture_cases` (late starter, dead meter, 0.80 and 0.7999, zero share 0.90, T = 2012-09-30 and 2012-10-01, 78 / 92), `::test_ac45_coverage_threshold_is_a_parameter` |
| AC-46 | Pass | n/a (unit only by design) | `test_labels.py::test_ac46_appending_later_months_keeps_eligibility_up_to_month_start` |
| AC-47 | Partial (invariants) | Not run | `test_labels.py::test_ac47_ineligible_rows_have_reasons_and_eligible_rows_none`. PR 2 local data: `::test_ac47_seed42_eligible_rows_per_split` Pass (16,969 / 7,170 / 5,116). Missing: deployed table (PR 3) |
| AC-48 | Pass (unit) | Not run | `test_training.py::test_ac48_splits_are_ordered_disjoint_and_equal_the_eligible_labelled_rows`, `::test_ac48_missing_feature_row_at_t_minus_1_fails_guard_g02`, `::test_ac48_overlapping_or_unordered_ranges_fail_guard_g09`, `::test_ac48_a_row_outside_the_ranges_is_rejected`. Missing: logged training set on the platform (PR 3) |
| AC-49 | Pass (unit) | Not run | `test_training.py::test_ac49_two_fits_give_identical_scores_threshold_and_metrics` (shuffled input, bitwise equal scores, equal t and metrics). Missing: two live runs (PR 3) |
| AC-50 | Pass (unit) | Not run | `test_training.py::test_ac50_run_parameters_cover_model_seed_and_fr31`, `test_peak_tables.py::test_ac50_training_parameters_exclude_the_scoring_only_target_date`, `::test_ac50_pinned_versions_are_checked_by_guard_g01` |
| AC-51 | Pass (unit) | Not run | `test_training.py::test_ac51_threshold_is_max_f1_with_highest_t_on_ties` (brute force over 400 random cases, a constructed tie, a single positive), `::test_ac51_run_threshold_equals_recomputation_from_validation_scores`, `::test_ac51_no_positive_validation_row_fails_before_any_effect` |
| AC-52 | Pass (unit) | Not run | `test_training.py::test_ac52_metric_names_cover_segments_with_counts_and_no_accuracy`, `::test_ac52_segment_without_positives_logs_no_pr_auc_and_precision_is_zero_without_flags`, `::test_ac52_ratio_rule_scores_null_total_as_zero_and_zero_baseline_as_1e_minus_6`. The PR-AUC > positive share check needs seed 42 (PR 3) |
| AC-53 | Pass | n/a | `test_training.py::test_ac53_empty_validation_month_fails_before_any_metric_or_registration` (error names 2013-09; no run, metric, model, tag or alias call; `champion` unchanged), `::test_ac53_a_commit_less_run_or_mismatched_parameters_fail_before_any_effect` |
| AC-54 | Pass (unit) | Not run | `test_training.py::test_ac54_pyfunc_wrapper_round_trip_reproduces_scores` (save and load with `code_paths`, max abs diff 0, signature over `FEATURE_COLUMNS`), `::test_ac54_encoding_uses_fixed_codes_and_unknown_values_become_nan`, `::test_ac54_register_logs_reloads_then_tags_then_moves_the_alias`, `::test_ac54_reload_mismatch_stops_before_the_tag_and_the_alias`. Missing: registry, alias and run records on the platform (DA-16, PR 3) |
| AC-55 | Not run | Not run | Live only (UC lineage, rebuild check). `registry.build_training_set` and the manifest checksum exist; no test yet |
| AC-56 | Pass (unit) | Not run | `test_scoring.py::test_ac56_predictions_cover_exactly_eligible_households_with_label_rule`, `::test_ac56_label_is_zero_below_the_threshold`, `::test_ac56_qr20_fails_on_a_duplicate_and_on_a_score_of_1_2` |
| AC-57 | Pass (unit) | Not run | `test_scoring.py::test_ac57_reassembly_is_identical_except_scored_at` |
| AC-58 | Pass (unit) | Not run | `test_scoring.py::test_ac58_default_target_date_is_day_after_latest_complete_day` |
| AC-59 | Pass (unit) | Not run | `test_scoring.py::test_ac59_range_resolves_to_89_dates` |
| AC-60 | Pass (unit) | Not run | `test_scoring.py::test_ac60_missing_feature_date_fails_before_write`, `::test_ac60_a_household_missing_from_the_feature_date_fails_before_write`, `::test_ac60_missing_label_rows_fail_before_write` |
| AC-61 | Pass (unit; live not possible by design) | n/a | `test_scoring.py::test_ac61_missing_champion_alias_fails_before_write`, `::test_ac61_champion_without_a_threshold_tag_fails_before_write`, `::test_ac61_champion_resolves_version_and_exact_threshold` |
| AC-62 | Pass (PR 2 unit) | Not run | `test_peak_bundle.py::test_ac62_daily_job_graph_schedule_and_pipeline_dependency`, `::test_ac62_training_is_on_demand_only`, `::test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged` (SHA-256 and `git show v0.1.0`, also `databricks.yml`), `::test_ac62_peak_model_adds_no_bundle_variable_and_uses_the_layout_variables`. Live: PR 3 |
| AC-63 | Pass (PR 2 unit and local data) | Not run | PR 2: `test_peak_bundle.py::test_ac63_label_and_eligibility_parameters_are_job_parameters`, `::test_ac63_job_parameters_reach_declared_notebook_widgets` (6 cases), `tests/local_data/test_peak_seed42.py::test_ac63_threshold_1_5_and_coverage_0_90` (7.91%, 29,100), `test_peak_tables.py::test_ac63_baseline_day_count_above_lookback_weeks_is_rejected`. PR 1: `test_peak_tables.py::test_ac63_parameters_default_parse_from_widgets_and_validate`, `::test_ac63_label_parameters_round_trip_through_table_properties`, `test_labels.py::test_ac63_label_parameters_are_recorded_as_table_properties`. Missing: widgets in `build_labels.py`, seed-42 figures (PR 2) |
| AC-64 | Pass (unit) | Not run | `test_peak_tables.py::test_ac64_library_schemas_equal_contracts_and_underscore_rule` (5 cases), `::test_ac64_non_nullable_contract_columns_hold_no_null` (4 cases), `::test_ac64_label_column_name_and_primary_keys_are_in_the_contracts`, `::test_ac64_ddl_nullability_and_feature_schema_follow_the_contracts`, `::test_ac64_ddl_properties_and_statement_order`, `::test_ac64_schema_precondition_names_the_missing_schemas`, `::test_ac64_object_names_follow_the_layout`, `::test_ac64_calendar_months_cover_partial_months`. Missing: deployed columns (PR 3) |
| AC-65 | Pass | n/a | `test_secrets_hygiene.py::test_ac65_tracked_files_contain_no_databricks_token`; `pre-commit run --all-files` (see Verification Log) |
| AC-66 | Pass (unit) | Not run | `test_peak_tables.py::test_ac66_merge_updates_only_changed_rows_and_deletes_missing_keys` (3 cases), `::test_ac66_merge_sql_rejects_bad_input_and_keys_only_tables_skip_the_update`, `::test_ac66_merge_metrics_replace_where_and_properties_text`, `::test_ac66_recomputation_with_another_partitioning_is_bitwise_equal` (weather, features, labels; 1 and 7 partitions; equal row counts and `xxhash64` checksums). Missing: MERGE on Delta, rebuild after reset (PR 3, DA-15) |
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

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | `registry.py` (`ensure_feature_table`, `build_training_set`, `table_version`, `MlflowTracker.log_inputs`, the real `fe.log_model` kwargs incl. `code_paths`) and `delta_sync` MERGE / `DESCRIBE HISTORY` / `replaceWhere` are not executable locally | Medium | PR 2 gate: DA-13 to DA-18 on `dev` before PR 3 |
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

## PR 2 gate (steps for the user; nothing below was run)

Prerequisites: PR 2 committed and merged or at least committed on the branch, so `git status --porcelain` is empty and `bundle.git.commit` is the code that runs. METER_INGESTION is deployed and its data is loaded. Run with the `dev` profile. Deploy and run are user actions.

1. `databricks bundle validate -t dev --profile dev`, then `databricks bundle deploy -t dev --profile dev`.
2. Upload the weather file once: `databricks fs cp data/raw/weather_hourly_darksky.csv dbfs:/Volumes/smart_meter_dev/bronze/landing/weather/ --profile dev`.
3. Partial daily run: `databricks bundle run -t dev --profile dev smart_meter_peak_model --only refresh_silver_gold,ingest_weather,build_weather_silver,build_features,build_labels`.
   - DA-13: the `pipeline_task` of a second job starts an update. Then start `smart_meter_ingestion` and, while it runs, `bundle run ... smart_meter_peak_model --only refresh_silver_gold`: expect a refused update and a successful retry after 600 s.
   - DA-14: widgets receive the job parameters (exit value of `build_labels` shows the parameters). Override check: `--params label_threshold=1.5,coverage_min=0.90` with `--only build_labels` (expect 7.91% and 29,100), then rerun with defaults.
   - DA-15: first `build_features` run MERGEs into the `fe.create_table` table (exit value `merge`; a rerun reports 0 / 0 / 0).
   - DA-18: `SHOW TBLPROPERTIES smart_meter_dev.ml.household_features_daily` and the labels table show the 90-day `delta.*RetentionDuration` and the `smart_meter.*` properties.
   - Expect 21,165 Bronze weather rows and 36,480 rows in each ML table.
4. Training: `databricks bundle run -t dev --profile dev smart_meter_peak_model_training`.
   - DA-15: `create_training_set` works on the MERGEd table. DA-16: G-08 passes (`champion_reload_max_abs_diff` 0). DA-17: the run parameter `git_commit` is 40 hex and equals the deployed commit.
5. Full daily run: `databricks bundle run -t dev --profile dev smart_meter_peak_model` (scores 2014-02-28; exit value names feature date 2014-02-27).
6. Record the exit values, run URLs and durations in this report. Any failed DA applies its DESIGN fallback through `/iterate` before PR 3.

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

---

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

PR 2: `/build .claude/sdd/features/DESIGN_PEAK_MODEL.md` (entries 24 to 35). `/ship PEAK_MODEL` only after PR 3.
