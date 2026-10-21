# BRAINSTORM: Peak Model

> Phase 0. Explore intent and approaches before capturing requirements.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL |
| **Date** | 2026-10-15 |
| **Author** | Christian |
| **Status** | Ready for Define |

Allowed status values: `Exploring`, `Ready for Define`.

Target release: v0.1 (second of two features of the end-to-end thin slice).

Split out of `BRAINSTORM_SMART_METER_ML_FOUNDATION.md` on 2026-10-15 with the decisions and
analysis already settled, and completed in the PEAK_MODEL brainstorm of 2026-10-20: weather and
holiday profiling, the A-07 and A-15 checks, the approach comparison, the answers of the user
(D-23 to D-34) and the user's confirmation of the Selected Approach. Spike 05 (A-04, A-12, A-16)
must pass, or the D-32 fallback be chosen, before `/design`.

The feature depends on the shipped `METER_INGESTION`
(`.claude/sdd/archive/METER_INGESTION/`), whose interface is `gold.household_daily_consumption`,
`gold.household_data_quality_monthly`, `gold.household_data_quality` and `silver.households`
(contracts in `docs/contracts/`).

---

## Initial Idea

**Raw input:** A utility's demand-response team wants to know, once per day, which households are
likely to consume well above their usual level the next day. Using the governed daily consumption
and per-household data quality facts produced by `METER_INGESTION`, enriched with weather and UK
holidays, build point-in-time correct features and a label, train and register a model, and
batch-score households into a predictions table.

The emphasis is on a governed ML data path rather than on model accuracy: point-in-time correct
training sets, temporal splits, lineage from raw reading to model version, and a registered model
promoted by alias.

**Context observed:**

| Aspect | Observation | Implication |
|---|---|---|
| Existing code or data | Empty `src/` package; no feature, training or scoring code. Weather and holiday files exist under the git-ignored `data/raw/` | Everything is new; inputs from `METER_INGESTION` must exist first |
| Existing conventions | `docs/conventions/naming.md` defines `household_id`, `label_<target>` and table patterns | Label column `label_consumption_spike`; contract names to be aligned in `/define` |
| Platform constraints | Databricks Free Edition: serverless only, daily fair-usage quota, no online tables, limited model serving (`.claude/kb/databricks/free-edition.md`) | Batch scoring instead of serving; small models; features computed in jobs |
| Relevant modules / KBs | `mlflow` (UC registry with `champion` / `challenger` aliases, temporal splits, point-in-time training sets), `databricks` | Models registered in Unity Catalog and promoted with aliases, not stages |

---

## Discovery Questions & Answers

Answers inherited from the original discovery (2026-10-06/07), the answers of 2026-10-15, and the
answers of the PEAK_MODEL brainstorm of 2026-10-20 (rows 5 to 14, asked one at a time, each with
options and a recommendation; the user chose the recommended option every time).

| # | Question | Answer | Impact |
|---|---|---|---|
| 1 | ML framing: which prediction task? | Binary classification: does a household exceed its usual daily consumption on the next day (D-05), with a same-weekday baseline and a 1.3x threshold (D-16, label decision below) | Label defined at daily grain; forecasting deferred to v0.3 |
| 2 | Consumers: who reads the output? | Answered Q-08 (2026-10-15): a demand-response team (hypothetical) reads the next day's at-risk households once per day. Daily batch scoring writes a Gold predictions table with `household_id`, `target_date`, `score`, `label`, `model_version`, `scored_at`. No real-time consumer in v0.1 | Batch scoring only; serving endpoint out of scope. Service-level expectation answered in row 6 |
| 3 | Which households may be trained on? | Answered Q-09 (2026-10-15): exclude a household when coverage < 80% or zero share >= 90%; both are parameters. `PEAK_MODEL` owns and applies these thresholds on top of `household_data_quality` from `METER_INGESTION` | Catches MAC004067 and MAC004672 in the full population (F-05, F-06, F-13). Note 2026-10-20: neither is in the seed-42 sample, where the whole-period rule excludes 0 of 60 (F-26); the point-in-time window decides who is excluded (F-27, Q-14) |
| 4 | Which external data enriches the features? | Hourly weather and UK bank holidays as dimensions (see *Weather and holidays*) | Weather timezone validated (A-07, F-20). Refined by rows 7 and 8: weather enters v0.1, holidays do not |
| 5 | How does the demand-response team use the daily output (operating threshold, consumer confirmation)? | Option A (2026-10-20): `label` is `score >= t`, where t maximises F1 on the validation range and is stored with the model version; `score` is always written so the team can also rank | D-23. Flag volume varies with the season (F-28) |
| 6 | Timing expectation for the daily run? | Option A (2026-10-20): no deadline beyond "after the daily Gold refresh, in the same job" | D-24, refined by D-33 (the PEAK_MODEL job, after the Silver/Gold pipeline update). No SLA test; ordering after the Gold refresh is the only timing requirement (see Q-17) |
| 7 | Q-13: weather in v0.1? | Option B (2026-10-20): mean temperature of feature day D over UTC hours from the hourly file | D-25. PEAK_MODEL owns Bronze and Silver hourly weather; no target-day weather |
| 8 | Holiday flag in v0.1? | Option A (2026-10-20): out of v0.1 | D-26. The corrupted file (F-24) is not ingested in v0.1 |
| 9 | Q-14: point-in-time exclusion window and denominator? | Option B (2026-10-20): per target date T, coverage and zero share over the 3 complete months before T; 3 is a parameter | D-27. Same rule for training and scoring; see F-30 for its effect on early target dates |
| 10 | Q-02: minimum feature set? | Option A (2026-10-20): total and max energy of D, 7- and 28-day averages, same-weekday baseline for D + 1, share of complete days in the last 28, target weekday and month, ACORN group and tariff, plus mean temperature of D | D-28. One row per household per feature date D for target date D + 1 |
| 11 | Q-03: split ranges? | Option A (2026-10-20): train 2012-07-29 to 2013-07-31, validation 2013-08-01 to 2013-11-30, test 2013-12-01 to 2014-02-27 | D-29. Ranges are parameters (F-28, F-29, F-30) |
| 12 | Q-12: model family and determinism? | Option B (2026-10-20): scikit-learn `HistGradientBoostingClassifier` with a fixed seed; the ratio rule (day D over its same-weekday baseline) logged as a reference metric only | D-30. One registered model |
| 13 | Scoring run semantics? | Option A (2026-10-20): parameter `target_date`, default the day after the latest complete Gold day, plus one backfill over the test range; a rerun overwrites only the rows of that `target_date` | D-31 |
| 14 | Feature storage and runtime? | Option A (2026-10-20): UC feature table with a point-in-time lookup, computed by serverless job tasks; fallback plain Delta tables with an explicit join if spike 05 fails A-12 | D-32 |
| 15 | Q-17: which job runs the PEAK_MODEL tasks? | Answered 2026-10-20: a separate PEAK_MODEL job that depends on the Silver/Gold pipeline (triggers or follows it); the shipped `METER_INGESTION` job is not changed | D-33; refines D-24 |
| 16 | Q-16: accept the label loss of the strict 3-month window, or allow a shorter window? | Answered 2026-10-20: strict 3-month window, D-27 unchanged; 16,969 training labels; August and September 2012 leave training | D-34. F-31: the removed labels are 16.6% positive against 14.4% for all training labels |

---

## Sample Data Inventory

| Type | Location | Volume | Notes |
|---|---|---|---|
| Input data: daily consumption | Gold `household_daily_consumption` from `METER_INGESTION` | One row per household-day; seed-42 sample: 60 households | Includes `is_complete_day`; 99.1% of household-days complete |
| Input data: household quality facts | `household_data_quality` from `METER_INGESTION` | One row per household | Coverage ratio, zero share, first / last reading, gap count; no exclusion flag |
| Input data: household attributes | Silver households from `METER_INGESTION` | 60 rows for seed 42 | `acorn_group`, `tariff`; static in v0.1 |
| Input data: weather | `data/raw/weather_hourly_darksky.csv` | 21,165 hourly rows, 2011-11-01 00:00 to 2014-03-31 22:00, 12 columns, one location | Profiled 2026-10-20 (`docs/profiling/weather_hourly_darksky.md`, F-14 to F-16, F-20 to F-23); timestamps are UTC (F-20) |
| Input data: calendar | `data/raw/uk_bank_holidays.csv` | 25 rows, 2012 to 2014 | Profiled 2026-10-20 (`docs/profiling/uk_bank_holidays.md`, F-17 to F-19, F-24, F-25); 6 of 25 dates have day and month transposed (F-24) |
| Expected output | Gold predictions table (consumer: Q-08) | One row per eligible household per `target_date` | Schema set in `/define` |
| Ground truth | Derived from readings | N/A | Label computed from the readings themselves; no external ground truth |

Not used in v0.1: `daily_dataset`, `hhblock_dataset`, `weather_daily_darksky.csv`,
`acorn_details.csv`.

**Profiling findings** relevant to this feature are inherited from `BRAINSTORM_METER_INGESTION.md`
with the same IDs (F-05 dead meters, F-06 coverage, F-07 staggered start and end, F-10 UTC
readings, F-12 tariff mix, F-13 low coverage). New findings of 2026-10-20: F-14 to F-19 come from
`scripts/profile_data.py` (reports `docs/profiling/weather_hourly_darksky.md` and
`docs/profiling/uk_bank_holidays.md`). F-20 to F-29 come from a manual check of what the script
cannot see: time zone, calendar correctness, and the effect of the quality and label rules on the
seed-42 sample.

| ID | Finding | Evidence | Implication |
|---|---|---|---|
| F-14 | Empty `pressure` values in hourly weather | 13 of 21,165 rows (0.06%) are `''`; all other columns have no null-like values | Not a v0.1 feature candidate; if used later, keep as null and count it |
| F-15 | Hourly weather key `time` is unique | 0 duplicates in 21,165 rows | Idempotency can be asserted by row counts |
| F-16 | Hourly weather time range | 2011-11-01 00:00:00 to 2014-03-31 22:00:00, rows not sorted in the file | Covers the study period (2012-07-01 to 2014-02-28) plus the 8-week label lookback and any feature lookback |
| F-17 | Holiday column name not Delta/SQL safe | `Bank holidays` | Positional schema in Bronze, rename in Silver |
| F-18 | Holiday key unique | 0 duplicates in 25 rows | Row counts assert idempotency |
| F-19 | Holiday time range as stored | 2012-02-01 to 2014-12-26; no 2011 rows | Raw range is misleading because of F-24 |
| F-20 | Hourly weather timestamps are UTC (evidence for A-07) | The four DST transition days 2012-03-25, 2012-10-28, 2013-03-31, 2013-10-27 each have exactly 24 hourly rows with 0 duplicate keys (local time would give 23 and 25). The daily file of the same source gives June median sunrise 03:45 and sunset 20:21, December 08:01 and 15:54; London is about 04:45 / 21:20 BST in June and 08:00 / 15:55 GMT in December, so the source writes UTC. The first hour with a `-day` icon is 04 in June and 09 in December, consistent with UTC | Hourly weather joins the UTC readings without conversion; A-07 validated on the file. The Bronze ingest must parse with session time zone UTC so this stays true |
| F-21 | Daily weather file uses Europe/London day boundaries | Daily `time` is 23:00 UTC for 100% of April to September rows and 00:00 for November to February (9% of March and 88% of October rows at 23:00, the DST change months) | `weather_daily_darksky.csv` does not match UTC days; daily weather features, if any, are aggregated from the hourly file over UTC days (confirms the file is not used in v0.1) |
| F-22 | Hourly weather nearly complete, single location | 21,165 of 21,167 expected hours; the only gap is 2013-09-09 23:00 and 2013-09-10 00:00 (2 hours). One series for all households (London) | A UTC daily mean over the available hours is safe; record hour count per day; no per-household weather |
| F-23 | `precipType` is never empty | rain 20,370, snow 795, no "none" value, including clear-sky hours | `precipType` does not mean precipitation happened; do not use it as a rain flag |
| F-24 | Holiday dates corrupted: day and month transposed in 6 of 25 rows, and 2 types swapped | Stored `2012-02-01` (Wednesday) is New Year substitute day 2012-01-02 (Monday); `2012-05-06` (Sunday) is the Jubilee 2012-06-05; `2012-07-05` (Thursday) is Early May 2012-05-07; `2012-09-04` (Tuesday) is Easter Monday 2012-04-09; `2013-01-04` (Friday) is Easter Monday 2013-04-01; `2013-06-05` (Wednesday) is Early May 2013-05-06. Also `2012-04-06` is labelled "Spring bank holiday (substitute day)" but is Good Friday, and `2012-06-04` is labelled "Good Friday" but is the moved Spring bank holiday. All 2014 rows are correct. Apostrophes are stored as `?` (4 type values) | The file cannot be used as is. A holiday feature needs a corrected, committed calendar with each correction documented, or must wait |
| F-25 | Few holidays inside the study period | Corrected calendar: 12 holidays in 2012-07-01 to 2014-02-28 (2.0% of 608 days); 3 in the draft test range (2013-12-25, 2013-12-26, 2014-01-01). The file as stored gives 14 in-period dates, 4 of them wrong (2012-07-05, 2012-09-04, 2013-01-04, 2013-06-05) and misses 2 (2013-04-01, 2013-05-06) | A holiday flag has about 8 training occurrences and 3 test occurrences; low value for v0.1, and holiday days also enter label baselines |
| F-26 | The seed-42 sample has no dead meters | Whole-period coverage < 80% or zero share >= 90%: 0 of 60 households. MAC004067 and MAC004672 are not in the sample; the sampling plan excludes dead meters (`METER_INGESTION` FR-01, manifest thresholds 0.8 / 0.9) | The note on Q-09 that the thresholds "catch MAC004067 and MAC004672" applies to the full population, not to seed 42; exclusion tests need a fixture |
| F-27 | Point-in-time coverage over all study months before a boundary excludes late starters | Coverage = observed / expected over the months before the boundary (monthly table, Q-14): before 2013-08-01, 11 of 60 households fall below 80% (0.703 to 0.779) with zero share 0.0; all start between 2012-09-26 and 2012-10-26 and have no gaps after that. Before 2013-12-01, 6 remain below 80% (0.773 to 0.795). Over the whole period, 0 | The denominator decides the eligible set: a study-period denominator removes 18% of the sample from training because they joined late, not because their meters are bad. Q-14 must choose the window and denominator |
| F-28 | D-19 labels on seed 42, recomputed independently | 33,093 labelled household-days, 14.6% positive, first 2012-07-29, last 2014-02-27. Draft ranges: train 20,716 (14.4%), validation 7,261 (16.0%), test 5,116 (13.6%). By month: 25.1% (2012-10), 8.5% (2013-02), 8.8% (2013-06), 18.7% (2013-10), 15.4% to 15.5% (2013-12, 2014-01), 9.2% (2014-02). Computed by a scratch script outside the repository | Consistent with the inherited 14.7% (0.1 pp gap). The draft test range is not the lowest-rate period; the risk "test range winter only (lowest positive rate)" is weaker than stated |
| F-29 | The draft test start equals the Kafka cutoff | Test range starts 2013-12-01; `METER_INGESTION` cutoff is 2013-12-01T00:00Z (C-07): every test label comes from streamed readings, its first feature day (2013-11-30) from files | Test metrics depend on a completed stream replay; evaluation must check label counts per month before reporting |
| F-30 | Effect of the D-27 exclusion rule on the draft splits (seed 42) | Training range: 16,969 of 20,716 labels eligible (81.9%); 3,054 have fewer than 3 complete months before T (all T before 2012-10-01) and 693 are excluded (12 households, mostly late starters in their first months). Validation 7,170 of 7,261 eligible, test 5,116 of 5,116. Eligible positive rates: 14.0% / 15.8% / 13.6%. Last excluded T is 2013-10-31 | The effective training range starts 2012-10-01, so August and September occur only in validation; Q-16 |
| F-31 | The labels removed by the 3-month rule are not seasonally distinct in positive rate, but they are the only late-summer months in training | See *F-31: label loss by month* below. Strict rule (D-27) removes 3,747 training labels at 15.9% positive (Jul to Sep 2012: 3,054 at 16.6%), and keeps 16,969 at 14.0%, against 14.4% for all training labels. A minimum-1-month window removes 998 and keeps 19,718 at 14.4%. August 2012 is 16.8% (validation August 2013: 13.1%), September 2012 is 16.2% (September 2013: 15.6%). The monthly rule also removes MAC000399, a seasonally inactive meter (zero share 95% to 100% in the summer months of 2012 and 2013) that the whole-period rule does not catch (F-26) | Q-16 answered by D-34 (strict window kept). Trade-off: the strict rule costs 18% of training labels and every summer-to-autumn month of 2012, the shorter window keeps them with weaker evidence per household (1 or 2 months) |

### F-31: label loss by month

Seed 42, D-19 labels, D-20 thresholds. "3 months" is D-27 (fewer than 3 complete months before T
means no eligibility); "min 1" uses the 1 to 3 complete months available. Removed = labelled rows
without eligibility. Computed by the same scratch script as F-28 and F-30.

| Month | Split | Labelled | Positives | Rate | Removed, 3 months | Rate kept, 3 months | Removed, min 1 | Rate kept, min 1 |
|---|---|---|---|---|---|---|---|---|
| 2012-07 | train | 127 | 24 | 18.9% | 127 (no 3 months) | - | 127 (no complete month) | - |
| **2012-08** | train | 1,460 | 246 | 16.8% | 1,460 (no 3 months) | - | 119 | 17.3% |
| **2012-09** | train | 1,467 | 237 | 16.2% | 1,467 (no 3 months) | - | 59 | 15.8% |
| 2012-10 | train | 1,516 | 381 | 25.1% | 37 | 24.9% | 37 | 24.9% |
| 2012-11 | train | 1,659 | 250 | 15.1% | 194 | 16.2% | 194 | 16.2% |
| 2012-12 | train | 1,839 | 364 | 19.8% | 338 | 20.6% | 338 | 20.6% |
| 2013-01 | train | 1,850 | 313 | 16.9% | 124 | 17.5% | 124 | 17.5% |
| 2013-02 to 2013-07 | train | 10,798 | 1,163 | 10.8% | 0 | 10.8% | 0 | 10.8% |
| **2013-08** | validation | 1,856 | 243 | 13.1% | 30 | 13.3% | 30 | 13.3% |
| **2013-09** | validation | 1,792 | 279 | 15.6% | 30 | 15.4% | 30 | 15.4% |
| 2013-10 | validation | 1,842 | 345 | 18.7% | 31 | 17.8% | 31 | 17.8% |
| 2013-11 | validation | 1,771 | 297 | 16.8% | 0 | 16.8% | 0 | 16.8% |
| 2013-12 to 2014-02 | test | 5,116 | 694 | 13.6% | 0 | 13.6% | 0 | 13.6% |
| **Training total** | train | 20,716 | 2,978 | 14.4% | 3,747 (15.9% positive) | 14.0% | 998 | 14.4% |

The validation removals (91 rows, 35% positive) are MAC000399 in its inactive summer months; a
near-zero baseline makes almost any consumption a positive label.

### Label analysis

Analysed on full days only (48 readings), over the whole study period, on the seed-42 sample.
Positive rate = share of household-days labelled 1.

| Baseline for "usual" consumption | Threshold | Positive rate |
|---|---|---|
| Median of previous 7 days | > 1.3x | 13.2% |
| Median of previous 28 days | > 1.2x / 1.3x / 1.5x | 21.3% / 14.3% / 7.3% |
| Mean of previous 28 days + k std | k = 1.0 / 1.5 | 17.6% / 9.4% |
| **Median of last 4 same-weekday days** | **> 1.2x / 1.3x / 1.5x** | **21.4% / 14.7% / 7.9%** |

| ID | Finding | Implication |
|---|---|---|
| L-01 | With calendar-day baselines, Sunday has about 22% positives vs about 12.5% on weekdays | A model would learn "tomorrow is Sunday"; metrics would look good without useful signal |
| L-02 | With the same-weekday baseline, positives are stable at 14-15% across all weekdays | Weekly cycle removed from the target |
| L-03 | Seasonality remains: October about 21.5%, February about 8.8% | The 4-week baseline lags the heating-season onset; temperature and month become strong features; the training range must span more than one season |
| L-04 | Positive rate differs by group: Affluent about 17%, Comfortable about 15%, Adversity about 11% (28-day baseline) | Report metrics per ACORN group, not only overall |

### Weather and holidays

- Hourly weather (`weather_hourly_darksky.csv`) and UK bank holidays (`uk_bank_holidays.csv`) are
  Bronze and Silver dimensions owned by this feature.
- **A-07 (validated on the source file 2026-10-20, F-20):** hourly weather timestamps are UTC, like
  the readings (F-10). Whether weather enters v0.1 is still Q-13; a readings-only feature set must
  remain sufficient for the thin slice.
- The holiday file is corrupted (F-24) and holidays are rare in the study period (F-25).
- Observed weather of the target day used as a feature assumes a perfect forecast and inflates
  metrics; whether a forecast stand-in is acceptable is an open question.

---

## Approaches Explored

Comparison drafted 2026-10-20. The user chose one option per topic on 2026-10-20 (rows 5 to 14 of
the discovery table); the combined approach is in *Selected Approach*, confirmed by the user 2026-10-20. Free Edition constraints are from
`.claude/kb/databricks/free-edition.md`; ML patterns from `.claude/kb/mlflow/patterns.md`.

Data volume for every option: 60 households and about 33,000 labelled household-days (F-28), so
training fits in memory on one serverless node and costs little of the daily quota.

### Topic 1: Feature computation and storage (A-12)

| Option | Description | Pros | Cons |
|---|---|---|---|
| 1A: UC Feature Engineering table | `ml.household_features_daily` with primary key `(household_id, feature_date)` and `feature_date` as time-series column; `create_training_set` with a point-in-time lookup; `fe.log_model` for feature lineage; batch scoring with `fe.score_batch` | Point-in-time lookup and model-to-feature lineage come from the platform; matches the KB pattern | Availability on Free Edition serverless unverified (A-12); `databricks-feature-engineering` must be in the job environment; `score_batch` ties scoring to the FE client |
| 1B: Plain Delta tables, explicit join | Features and labels as Delta tables in `ml`; the training set is an explicit join on `feature_date = target_date - 1`; MLflow logs table names and Delta versions (and `mlflow.log_input` datasets) | No dependency on A-12; the join rule is visible and unit-testable locally | Model-to-table lineage is only what MLflow records, not the FE lineage graph; the as-of rule is our code |
| 1C: In-memory features in the training job | No feature table; the training and scoring jobs compute features from Gold each time | Simplest; fewest objects | No governed feature table; train and score code paths can drift; fails the draft lineage criterion |

Recommended: 1A, with 1B as the documented fallback if spike 05 fails A-12. **Chosen by the user 2026-10-20 (D-32).**
Because features are dated D and labels D + 1, the as-of rule is an exact-date join in both options.

### Topic 2: Where features and labels run

| Option | Description | Pros | Cons |
|---|---|---|---|
| 2A: Serverless job tasks | Python tasks in a bundle job: features, labels, training, scoring, chained | Fits "max 5 concurrent tasks" by chaining; works with 1A or 1B; no clash with the ingestion pipeline | Incremental logic and idempotency (overwrite by date range or MERGE) are our code |
| 2B: Materialized views in the `METER_INGESTION` Lakeflow pipeline | Feature and label MVs added to the existing pipeline | Declarative refresh; one pipeline | Crosses the feature boundary (D-22); FE tables cannot be MVs; training still needs a job |
| 2C: A second Lakeflow pipeline | A PEAK_MODEL pipeline for features and labels | Declarative, separate ownership | Free Edition allows one active pipeline per type; must run strictly after ingestion; needs a spike |

Recommended: 2A. **Chosen by the user 2026-10-20 (D-32).**

### Topic 3: Weather in v0.1 (Q-13)

| Option | Description | Pros | Cons |
|---|---|---|---|
| 3A: Readings only | No weather features | Simplest; no new Bronze or Silver objects | Ignores the strongest seasonal driver (L-03) |
| 3B: Observed weather of feature day D | Daily mean temperature (and optionally heating degree-days) of D over UTC hours, from the hourly file | No leakage; A-07 validated (F-20); file complete (F-22) | Adds Bronze and Silver weather objects; temperature of D is only a proxy for D + 1 |
| 3C: Observed temperature of target day D + 1 as a forecast stand-in | Uses the actual temperature of the target day | Closest to a real forecast-driven model | Assumes a perfect forecast and inflates metrics; must be labelled as such |

Recommended: 3B. **Chosen by the user 2026-10-20 (D-25);** 3C is out of scope.

### Topic 4: Holiday flag in v0.1

| Option | Description | Pros | Cons |
|---|---|---|---|
| 4A: No holiday feature in v0.1 | Defer to v0.2 | Avoids the corrupted file (F-24); 12 holidays only (F-25) | Christmas days are scored without a holiday signal |
| 4B: Corrected, committed calendar | Reference data built from the source with the 6 transpositions and 2 type swaps fixed, each listed | Holiday flag available | Feature with about 8 training and 3 test occurrences; corrections need review |
| 4C: Calendar from a library | Generate UK holidays from a package | Correct dates without manual fixes | New dependency in the job environment; ignores the source dataset |

Recommended: 4A. **Chosen by the user 2026-10-20 (D-26).**

### Topic 5: Point-in-time household exclusion (Q-14)

All options use `gold.household_data_quality_monthly` and the D-20 thresholds (coverage < 80%,
zero share >= 90%); they differ in window and denominator (F-27).

| Option | Description | Pros | Cons |
|---|---|---|---|
| 5A: Per split boundary, all study months before it | Training households: months before the validation start; evaluation and scoring: months before the test start | Simple, two computations | Excludes 11 of 60 late starters from training (F-27); scoring uses a fixed, stale window |
| 5B: Per target date, trailing N complete months | For each target date T, coverage and zero share over the N (default 3) complete months before the month of T (a month is complete once T is past its last day) | Same rule in training and scoring; late starters become eligible after N months; dead meters drop out within N months | Eligibility can change month to month; a household needs N full months of history |
| 5C: Per split boundary, active-span denominator | As 5A but expected slots counted from the first reading of the household | Keeps late starters | The monthly table has first reading per month only, so the active span is derived; a meter that dies stays eligible longer |

Recommended: 5B with N = 3 as a parameter. **Chosen by the user 2026-10-20 (D-27).**

### Topic 6: Train, validation and test ranges (Q-03)

| Option | Ranges | Labels on seed 42 | Pros | Cons |
|---|---|---|---|---|
| 6A: Draft ranges | Train 2012-07-29 to 2013-07-31; validation 2013-08-01 to 2013-11-30; test 2013-12-01 to 2014-02-27 | 20,716 / 7,261 / 5,116; 14.4% / 16.0% / 13.6% (F-28) | Train covers a full year; validation includes the heating onset; test is the streamed period (F-29) | Test is 3 winter months only; depends on the stream replay |
| 6B: Longer train, short validation | Train to 2013-09-30; validation 2013-10-01 to 2013-11-30; test unchanged | About 24,400 / 3,600 / 5,100 | More training data | Validation is two months of high positive rate; threshold tuned on a narrow season |

Recommended: 6A. **Chosen by the user 2026-10-20 (D-29).** Rolling-origin backtesting stays in v0.3 (Out of Scope).

### Topic 7: Model family and determinism (Q-12)

| Option | Description | Pros | Cons |
|---|---|---|---|
| 7A: Logistic regression | scikit-learn, scaling fitted on train only | Deterministic, interpretable, tiny | Misses interactions (month by ratio features) |
| 7B: Histogram gradient boosting (scikit-learn) | `HistGradientBoostingClassifier` with fixed `random_state` and no internal random early-stopping split | Handles non-linear ratios and categorical month; no extra dependency; deterministic with a fixed seed | Less interpretable; still needs a reference model to show it adds value |
| 7C: LightGBM | Gradient boosted trees from LightGBM | Common in industry | Extra dependency; determinism needs `deterministic=True` and fixed threads |

Recommended and **chosen by the user 2026-10-20 (D-30):** 7B registered, with a naive rule (score = ratio of day D to the
same-weekday baseline) logged as a reference metric only.

### Topic 8: Operating threshold and output semantics

| Option | Description | Pros | Cons |
|---|---|---|---|
| 8A: Threshold at maximum F1 on validation | The `label` column is `score >= t`, with t stored with the model version | Consumer-agnostic, simple to test | Flag volume moves with the season (positive rate 8.5% to 25%, F-28) |
| 8B: Minimum precision on validation | Lowest t whose validation precision is at least P | Matches a team that wants few false alarms | P is a business number nobody has given; may yield very few flags |
| 8C: Fixed daily capacity (top K per target date) | Flag the K (or top x%) highest-scored households each day | Stable daily volume, natural for outreach | K is a business number; precision varies with the season |

Recommended: 8A, with `score` always written so a consumer can rank. **Chosen by the user 2026-10-20 (D-23).**

### Topic 9: Scoring run semantics

| Option | Description | Pros | Cons |
|---|---|---|---|
| 9A: Parameter `target_date`, default the day after the latest complete Gold day; one backfill over the test range | Idempotent overwrite of the rows of that `target_date` | Matches "once per day"; reruns change only `scored_at` | Two modes (daily and backfill) to test |
| 9B: Score every target date on each run | Recompute the whole predictions table | One mode | More compute per run; history rewritten by every new model version |

Recommended: 9A. **Chosen by the user 2026-10-20 (D-31).**

---

## Selected Approach

| Attribute | Value |
|---|---|
| **Chosen** | Governed daily batch path: UC feature table with a point-in-time lookup, computed by serverless job tasks; one scikit-learn gradient boosting model registered in UC with alias `champion`; idempotent batch scoring per `target_date`, all in a separate PEAK_MODEL job that runs after the Silver/Gold pipeline update (options 1A, 2A, 3B, 4A, 5B, 6A, 7B, 8A, 9A; D-23 to D-33) |
| **Confirmed by** | Christian (user), 2026-10-20: approach, architecture and data flow confirmed as written, relayed through the `/brainstorm` session. Spike 05 (A-04, A-12, A-16) must pass, or the D-32 fallback be chosen, before `/design` |
| **Reasoning** | Point-in-time lookup and model-to-feature lineage come from the platform (1A); job tasks avoid the one-active-pipeline limit (2A); the data is small enough for single-node training; every rule (label, exclusion, threshold, splits) is a parameter and testable locally |

**Architecture (components, all in catalog `smart_meter_dev`):**

- Read only, from `METER_INGESTION`: `gold.household_daily_consumption`,
  `gold.household_data_quality_monthly`, `silver.households`.
- Owned here: Bronze and Silver hourly weather, the feature table and label table in `ml`, the UC
  model in `ml`, the predictions table (schema and names set in `/define`), and the PEAK_MODEL job
  with the tasks below (D-33). The job triggers or follows the Silver/Gold pipeline update; the
  shipped `METER_INGESTION` job is unchanged.
- Gate: spike 05 must pass, or the D-32 fallback be chosen, before `/design`. Under the fallback:
  - Task 2 writes a plain Delta table keyed `(household_id, feature_date)` instead of a UC feature
    table; no `create_table` or time-series key.
  - Task 4 builds the training set with an explicit join on `feature_date = target_date - 1`
    instead of `create_training_set`, logs the model with `mlflow.sklearn.log_model` plus feature
    table names and Delta versions instead of `fe.log_model`; UC lineage reaches the tables only
    through what MLflow records.
  - Task 5 joins the features dated T - 1 itself and calls `mlflow.pyfunc` on `model@champion`
    instead of `fe.score_batch`.
  Tasks 1 and 3 are the same in both variants.

**Data flow (confirmed 2026-10-20):**

```text
 PEAK_MODEL job (D-33): triggers or follows the METER_INGESTION Silver/Gold pipeline update, then:
 data/raw/weather_hourly_darksky.csv
        |  task 1: ingest weather (idempotent)
        v
 bronze weather (raw) -> silver weather_hourly (UTC)
        |
        |   gold.household_daily_consumption   silver.households   gold.household_data_quality_monthly
        |                    |                        |                         |
        v                    v                        v                         |
 task 2: features, one row per (household_id, feature_date D)                  |
        -> ml feature table, time-series key feature_date                      |
                                                                                v
 task 3: labels and eligibility, one row per (household_id, target_date T = D + 1)
        label_consumption_spike (D-19); eligible when the 3 complete months before T
        pass coverage >= 80% and zero share < 90% (D-27); reasons logged
        |
        v
 task 4 (training run): eligible labels split by target_date (D-29)
        + point-in-time lookup of features dated T - 1
        -> HistGradientBoostingClassifier, fixed seed (D-30)
        -> threshold t at max F1 on validation; test PR-AUC, precision, recall,
           per ACORN group and month; ratio-rule reference metric
        -> MLflow run -> UC model in ml, alias champion (t stored with the version)
        |
        v
 task 5 (daily, in the PEAK_MODEL job, after the Silver/Gold pipeline update): target_date parameter (D-31)
        eligible households for T -> features dated T - 1 -> model@champion
        -> predictions: household_id, target_date, score, label, model_version, scored_at
           (rows of that target_date overwritten; one backfill run over the test range)
```

---

## Key Decisions

| # | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| D-05 | ML framing: binary classification, household exceeds its usual daily consumption on the next day | Simple to evaluate; keeps focus on data engineering | Forecasting (deferred to v0.3) |
| D-16 | Label baseline: median of the last 4 same-weekday full days, threshold 1.3x | Removes the weekly cycle from the target (L-01, L-02) | Calendar-day 7- or 28-day baselines |
| D-19 | **Label (carried forward, confirmed by the user 2026-10-15):** `label_consumption_spike = 1` when the consumption of a household on day T is strictly greater than 1.3 x the median of the last 4 complete days with the same weekday as T, taken from the 8 weeks before T. No label when T is incomplete or when fewer than 4 such days exist. Threshold (1.3), number of days (4) and lookback (8 weeks) are parameters | 14.7% positives on the seed-42 sample; the same-weekday baseline removes the Sunday effect (L-01, L-02); the 8-week lookback stops stale baselines after long gaps (F-06, F-07). Alternatives: 1.2x gives 21.4% positives (milder deviations), 1.5x gives 7.9% (stricter) | Calendar-day baselines; 1.2x and 1.5x thresholds |
| D-20 | Exclusion thresholds (answered Q-09): coverage < 80% or zero share >= 90%, both parameters, applied by `PEAK_MODEL` on `household_data_quality`; excluded households are logged with their reason | Ingestion reports facts only (D-18 in `METER_INGESTION`) | Exclusion flag computed in ingestion |
| D-21 | Consumer (answered Q-08): hypothetical demand-response team reading daily batch predictions | Gives the model a concrete reader without serving infrastructure | Real-time serving endpoint |
| D-22 | Scope split of 2026-10-15: ML half of the original feature | Two features with a clean interface | One combined feature |
| D-23 | Operating threshold (answered 2026-10-20, Topic 8): `label = score >= t`, t maximises F1 on the validation range and is stored with the model version; `score` always written | Needs no business number from a hypothetical consumer; ranking stays possible | Minimum precision (8B), fixed daily capacity (8C), score only |
| D-24 | Timing (answered 2026-10-20): no deadline beyond running after the daily Gold refresh, in the same job | Hypothetical consumer, replayed historical data. Refined by D-33: "the same job" is the PEAK_MODEL job | Fixed UTC deadline, on-demand backfill for any date |
| D-25 | Weather (answered Q-13, Topic 3): mean temperature of feature day D over UTC hours of the hourly file; PEAK_MODEL owns Bronze and Silver hourly weather | No leakage; A-07 validated (F-20); file complete (F-22) | Readings only (3A); target-day temperature as a forecast stand-in (3C) |
| D-26 | Holidays (answered, Topic 4): no holiday feature and no holiday ingestion in v0.1 | Source corrupted (F-24); 12 in-period holidays (F-25) | Corrected committed calendar (4B), library calendar (4C) |
| D-27 | Point-in-time exclusion (answered Q-14, Topic 5): for each target date T, coverage and zero share over the 3 complete months before T (a month is complete when T is after its last day), from `gold.household_data_quality_monthly`; D-20 thresholds; window length is a parameter. Refines D-20, which named the whole-period view | Same rule in training and scoring; late starters become eligible after 3 months (F-27) | Per-boundary windows with study-period (5A) or active-span (5C) denominators |
| D-28 | Feature set (answered Q-02): one row per household per feature date D for target date D + 1: total and max energy of D, 7- and 28-day averages ending at D, same-weekday baseline for D + 1, share of complete days in the 28 days ending at D, target weekday and month, ACORN group, tariff, mean temperature of D | Minimal set that covers level, recent trend, weekly baseline, season and household type | Smaller ratio-only set; half-hourly shape (v0.2) |
| D-29 | Splits (answered Q-03, Topic 6): train 2012-07-29 to 2013-07-31, validation 2013-08-01 to 2013-11-30, test 2013-12-01 to 2014-02-27, by `target_date`, never shuffled; all are parameters | Train spans every month once; validation includes the heating onset; test is the streamed period (F-29) | Longer train with a two-month validation (6B) |
| D-30 | Model (answered Q-12, Topic 7): scikit-learn `HistGradientBoostingClassifier`, fixed `random_state`, no internal random early-stopping split; the ratio rule (total of D over the same-weekday baseline for D + 1) logged as a reference metric only, not registered | Non-linear ratios and month effects with no extra dependency; deterministic | Logistic regression (7A), LightGBM (7C) |
| D-31 | Scoring (answered, Topic 9): job parameter `target_date`, default the day after the latest complete Gold day; one backfill over the test range; a rerun overwrites only the rows of that `target_date` | Matches "once per day" and golden rule 4 | Rescoring every date on each run (9B) |
| D-32 | Feature storage and runtime (answered, Topics 1 and 2): UC Feature Engineering table with a time-series key and point-in-time training set, computed by chained serverless job tasks; fallback plain Delta tables with an explicit join if spike 05 fails A-12 | Platform lineage from model to features; no conflict with the one-active-pipeline limit | In-memory features (1C); Lakeflow MVs (2B, 2C) |
| D-33 | Job ownership (answered Q-17, 2026-10-20): PEAK_MODEL has its own job, deployed by the same bundle, that depends on the Silver/Gold pipeline update (it triggers the update as its first task or follows it); its scoring task runs after that update. The shipped `METER_INGESTION` job is not changed and needs no `/iterate` | Keeps the feature boundary of D-22 and the shipped feature untouched | Extending the `METER_INGESTION` daily job |
| D-34 | Exclusion window length (answered Q-16, 2026-10-20): D-27 stays strict; a target date with fewer than 3 complete months before it has no eligibility and no training row. On seed 42 this keeps 16,969 of 20,716 training labels, and the eligible training range starts 2012-10-01 | F-31: the removed labels are not seasonally distinct in positive rate (16.6% against 14.4%); every eligible household is judged on 3 full months | Minimum-1-month window (19,718 labels, weaker evidence per household) |

---

## Out of Scope (YAGNI)

| Item | Reason | Revisit in |
|---|---|---|
| Ingestion, Silver readings, daily Gold, data quality measurement | Owned by `METER_INGESTION` | `METER_INGESTION` |
| Richer features (weather sensitivity, profile deviation, half-hourly shape, calendar effects) | v0.1 needs a minimal feature set only | v0.2 |
| Point-in-time joins against a slowly changing dimension | Depends on SCD Type 2 | v0.2 |
| Forecasting formulation and backtesting by windows | Classification framing first (D-05) | v0.3 |
| Drift monitoring and retraining trigger | Needs a model in production first | v0.3 |
| Hyper-parameter search beyond one baseline model | Focus is the data foundation | v0.3 |
| Real-time model serving endpoint and online features | Free Edition serving limits; batch scoring suffices | v0.4, or documented only |
| Bank-holiday ingestion and holiday flag (D-26) | Corrupted source (F-24), 12 in-period holidays (F-25) | v0.2, with a corrected calendar |
| Target-day weather as a forecast stand-in (3C) | Assumes a perfect forecast | v0.2 as a labelled experiment, or never |
| Daily weather file `weather_daily_darksky.csv` | London-local days (F-21) | Never; aggregate the hourly file |
| Comparison models (logistic regression, LightGBM) and the challenger alias flow | One registered model in v0.1 (D-30) | v0.3 |
| Operating points tied to business numbers (minimum precision, daily capacity) | No real consumer numbers (D-23) | When a real consumer appears |
| Scoring deadline or SLA monitoring | No expectation beyond ordering (D-24) | When a real consumer appears |

**Release roadmap (model side):**

| Release | Scope |
|---|---|
| v0.1 | Label, minimal daily features, point-in-time training set, one registered model, batch scoring |
| v0.2 | Broader feature set, holiday flag from a corrected calendar, point-in-time features against the household dimension |
| v0.3 | Forecasting and temporal backtesting, monitoring |
| v0.4 | Serving |

---

## Assumptions & Open Questions

| ID | Assumption or question | How it will be resolved | Status |
|---|---|---|---|
| A-04 | MLflow registers models in UC and resolves aliases on Free Edition serverless; a scikit-learn model with a signature loads by `models:/...@champion` | Spike `spikes/databricks/05_spike_mlflow_uc.py` (number 03 is taken by `03_spike_kafka_unreachable.py`). Hard gate: spike 05 must pass, or the D-32 fallback be chosen, before `/design` | Pending |
| A-07 | Weather timestamps are UTC, like readings (F-10) | Local profiling of the source file (F-20); a Bronze ingest test in `/build` confirms parsing with session time zone UTC | Validated 2026-10-20 on the file |
| A-12 | Databricks Feature Engineering in UC (feature tables with a time-series key, point-in-time lookup, model logging with feature lineage) is available on Free Edition serverless: `databricks-feature-engineering` installs in the job environment, `create_table` with `timeseries_columns`, `create_training_set` with `timestamp_lookup_key`, `fe.log_model` and `fe.score_batch` work, and the lineage graph shows model to feature table | Spike 05. Hard gate: spike 05 must pass, or the D-32 fallback be chosen, before `/design`, because a failure changes tasks 2, 4 and 5 (see *Selected Approach*) | Pending |
| A-16 | Training is deterministic on serverless: two runs on the same input and seed give identical scores | Spike 05 (train twice, compare), before `/design`; then a `/build` test | Pending |
| A-15 | `METER_INGESTION` delivers quality facts over a window that supports the training-range coverage definition | Checked 2026-10-20 against `docs/contracts/gold_household_data_quality_monthly.yaml` and the archived DEFINE (FR-02, SF-01, AC-24): one dense row per household per UTC month from 2012-07 to 2014-02; a month row is final once the month is ingested. The draft boundaries 2013-08-01 and 2013-12-01 are month starts, so "months before the boundary" has no partial month. Caveats: (1) a per-target-date rule can use only months completed before T, a lag of up to 31 days; (2) 2014-02 has 1,344 expected slots but at most 1,297 exist (data ends 2014-02-28T00:00), so its coverage cannot exceed 0.965; (3) the monthly table has no active-span denominator, so a late-start-aware rule derives it from `first_reading_ts` (F-27). The whole-period view `household_data_quality` is not point-in-time safe and is used for reporting only | Validated 2026-10-20 for the window; window and denominator chosen in D-27 |

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Label threshold is a business choice (L-01 to L-03) | Positive rate swings from 7.9% to 21.4% between 1.5x and 1.2x | Record the choice and the label analysis table in an ADR |
| Seasonal shift in positive rate (L-03) | A temporal split could put one season only in test; with D-27 and D-34 the eligible training labels start 2012-10-01, so August and September appear in validation only (F-30, F-31) | Evaluate per month; accepted by the user (D-34) |
| Max-F1 threshold under seasonal drift (D-23) | Daily flag volume moves with the positive rate (8.5% to 25.1%, F-28) | Report flags per month; score kept for ranking |
| Spike 05 fails A-12 | Platform feature lineage unavailable; tasks 2, 4 and 5 change | D-32 fallback; the lineage criterion becomes "MLflow records feature table names and Delta versions" |
| Test range winter only | Noisy per-group and per-month test metrics; the draft test rate is 13.6%, not the lowest (F-28) | Decide ranges (Q-03); report group and month metrics with counts |
| Holiday source corrupted (F-24) | A holiday flag built from the file as is marks 4 wrong days and misses 2 in the study period (F-25) | Not used in v0.1 (D-26); corrected calendar in v0.2 |
| Late starters excluded by a point-in-time rule (F-27) | 18% of the sample lost from training under a study-period denominator | D-27 trailing 3-month window; late starters still miss their first months (F-30) |
| Test period depends on the stream replay (F-29) | Missing or partial test labels if the replay did not finish | Check label counts per test month before reporting metrics |
| Feature leakage from the target day | Inflated metrics | Features use only data available at the end of the previous day; leakage test |
| Weather timezone mismatch (A-07) | Misaligned weather features | Validated on the file (F-20); Bronze ingest test keeps parsing in UTC; readings-only fallback |
| Hypothetical consumer | No real service-level expectations | Keep the contract minimal; revisit if a real consumer appears |
| `METER_INGESTION` interface changes | Rework here | Interface fixed in its `/define`; changes through `/iterate` on both features |

### Open questions

| ID | Question | Notes |
|---|---|---|
| Q-02 | Feature grain and minimum feature set for v0.1 | Daily grain proposed. Draft inputs from the superseded DEFINE: one row per household per feature date D for target date D + 1; total and max energy of D, 7-day and 28-day averages, the same-weekday median baseline for D + 1, share of complete days in 28 days, target weekday and month, static ACORN group and tariff; optional mean temperature of D after A-07 and a bank-holiday flag for the target date; Answered 2026-10-20: D-28 |
| Q-03 | Train, validation and test date ranges inside the study period | Must cover more than one season (L-03). Draft inputs: train 2012-07-29 to 2013-07-31, validation 2013-08-01 to 2013-11-30, test 2013-12-01 to 2014-02-27 (earliest labellable date is 2012-07-29; 2014-02-28 holds only the 00:00 reading); Answered 2026-10-20: D-29 |
| Q-12 | Model family, operating threshold rule and determinism | Baseline model only in v0.1; Answered 2026-10-20: D-30 (model) and D-23 (threshold) |
| Q-13 | Do weather features enter v0.1 or wait for v0.2 | Profiling done (F-14 to F-16, F-20 to F-23) and A-07 validated; options in Topic 3; the holiday flag is Topic 4; Answered 2026-10-20: D-25; holidays D-26 |
| Q-14 | Point-in-time household exclusion: thresholds applied to a whole-period quality metric leak test-period information into training. Exclusions must use `household_data_quality_monthly` (from METER_INGESTION) restricted to data before each split boundary or target date | Raised 2026-10-15 while settling METER_INGESTION Q-11; Answered 2026-10-20: D-27 |

| Q-16 | D-27 needs 3 complete months before T: target dates before 2012-10-01 and the first months of late starters have no eligibility (F-30). Accept the loss, or allow a shorter window when fewer months exist? | Answered 2026-10-20 by the user: strict window, D-27 unchanged (D-34). Evidence in F-31 |
| Q-17 | D-24 says "in the same job" as the daily Gold refresh. The daily job belongs to the shipped `METER_INGESTION` bundle: extend it (needs `/iterate` on `METER_INGESTION`) or give PEAK_MODEL its own job that triggers the pipeline update first? | Answered 2026-10-20 by the user: a separate PEAK_MODEL job that triggers or follows the Silver/Gold pipeline update; no `/iterate` on the shipped `METER_INGESTION` job (D-33) |
| Q-18 | Schema and names of the predictions table and the UC model (`gold` or `ml`) | For `/define`; `docs/conventions/naming.md` |

Q-01 (label threshold) is answered by D-19; Q-08 and Q-09 are answered (D-21, D-20); Q-02, Q-03,
Q-12, Q-13 and Q-14 are answered (D-23 to D-30).

---

## Suggested Requirements for Define

*Draft, updated 2026-10-20 to D-23 to D-32. To be confirmed with the Selected Approach.*

- **Problem statement (draft):** Provide a demand-response team with a once-per-day list of
  households likely to exceed their usual consumption the next day, by deriving a point-in-time
  correct label and daily features from governed consumption data, training and registering one
  model with lineage, and batch-scoring eligible households.
- **Success criteria (draft):**
  - Labels follow D-19 exactly: strictly greater than 1.3 x the same-weekday median of 4 complete
    days within 8 weeks, no label otherwise; verified against a hand-computed fixture.
  - No feature for a target day uses data from that day or later (leakage test); splits are
    temporal and never shuffled.
  - For each target date, a household is eligible only when the 3 complete months before it have
    coverage >= 80% and zero share < 90% in `gold.household_data_quality_monthly`; ineligible
    household-dates are listed with their reason; thresholds and window length are parameters
    (D-27). Verified against a fixture with a late starter and a dead meter.
  - Features follow D-28 and include the mean temperature of D over UTC hours (D-25).
  - The registered model version links to its training run and feature table in UC lineage (or,
    under the D-32 fallback, MLflow records feature table names and Delta versions); alias
    `champion` resolves; the threshold t is stored with the version (D-23).
  - Two training runs on the same input give identical scores (D-30, A-16).
  - Evaluation reports PR-AUC and precision / recall at t, overall, per ACORN group and per month,
    with counts; test PR-AUC is above the test positive rate and is compared with the ratio-rule
    reference; accuracy alone is not reported.
  - Scoring writes exactly one row per eligible household per `target_date`, and re-running it
    changes nothing except `scored_at` (D-31).
- **Constraints:**
  - Free Edition serverless only.
  - No credentials in code, bundle files or git.
  - Label threshold, baseline window, lookback, split dates, exclusion thresholds, exclusion
    window and `target_date` are parameters.
  - Single-node scikit-learn; no extra ML dependency beyond the Feature Engineering client.
  - Time is UTC end to end; event time and processing time are separate columns.

---

## Self-Review

- **Weak points:**
  - All eleven option answers of 2026-10-20 took the agent's recommended option, and the user's
    answers and confirmation reached this document through the `/brainstorm` coordinator, not
    first hand.
  - Spike 05 (A-04, A-12, A-16) has not run; the platform half of the approach (feature table,
    lineage, `score_batch`) is unverified until it does.
  - D-34 keeps the strict window: 18% of the training labels and all of August and September 2012
    leave training (F-30, F-31); the effect on model quality is unmeasured.
  - All label numbers come from a sampling run on a sample whose script is not yet in the
    repository, so they cannot be regenerated today.
  - The consumer is hypothetical (Q-08); no service-level expectations exist.
  - Weather and holidays are profiled (2026-10-20), but the holiday corrections in F-24 were
    checked against known UK bank holiday dates by hand, not against an official source file.
  - F-26 to F-28 come from a scratch script outside the repository, so they cannot be regenerated
    from the repository today either.
  - F-30 and F-31 also come from the scratch script.
  - Q-18 (schema and names of the predictions table and the UC model) is left to `/define`.
  - The max-F1 threshold is tuned on four validation months with a higher positive rate (16.0%)
    than test (13.6%), so test precision and recall at t may differ from validation.
- **Risks:** The label threshold moves the positive rate between 7.9% and 21.4%; seasonality can
  make a temporal split unrepresentative, and D-34 leaves late summer out of training; Free
  Edition may lack Feature Engineering capabilities (A-12) or UC lineage, which changes tasks 2, 4
  and 5; a 60-household sample gives noisy per-group and per-month metrics.
- **Trade-offs:** Platform lineage (1A) over a simpler explicit join (1B), with 1B kept as the
  fallback; a strict eligibility window over more training rows; a consumer-agnostic max-F1
  threshold over business-driven operating points.
- **What I would do differently:** Profile weather and holidays and confirm the interface tables of
  `METER_INGESTION` before writing the label analysis into a requirement.
- **Next improvement:** Commit the label and eligibility computation used for F-26 to F-31 as a
  local spike (`spikes/local/`) so the numbers can be regenerated, then run `/define`. Run spike 05
  before `/design`; it must pass, or the D-32 fallback be chosen.

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-15 | Created by splitting `BRAINSTORM_SMART_METER_ML_FOUNDATION.md` (status Ready for Define). Carried over: label decision (D-05, D-16, new D-19 with the 8-week lookback confirmed by the user), exclusion thresholds (Q-09 as D-20), consumer (Q-08 as D-21), label analysis L-01 to L-04, A-04, A-07, A-12, ML risks and YAGNI items. Added F-14, A-15, Q-12, Q-13 and D-22. Status set to Exploring because approaches, weather profiling and the feature, range and model questions remain open | User decision of 2026-10-15: split into METER_INGESTION and PEAK_MODEL | No DEFINE exists for this feature; `DEFINE_SMART_METER_ML_FOUNDATION.md` is a source only until PEAK_MODEL reaches Ready for Define; contracts for features and predictions belong here; the original brainstorm file is to be removed with `git rm` by the caller |
| 2026-10-20 | Brainstorm preparation: profiled hourly weather and bank holidays (`docs/profiling/weather_hourly_darksky.md`, `docs/profiling/uk_bank_holidays.md`); replaced the F-14 placeholder with F-14 to F-29; A-07 validated on the file (F-20); A-15 checked against the shipped contracts (validated for the window, denominator open); drafted Topics 1 to 9 of the approach comparison without selecting any; added a note on the Q-09 answer (F-26) and four risks. Status stays Exploring | `METER_INGESTION` shipped 2026-10-20, so its contracts can be checked; preparation before the user dialogue | None yet. Q-14 now has to choose a window and denominator (F-27); a holiday feature cannot use the source file as is (F-24) |
| 2026-10-20 | Recorded the user's answers to the ten queued questions (discovery rows 5 to 14, D-23 to D-32); marked the chosen option per topic; Q-02, Q-03, Q-12, Q-13, Q-14 answered; added F-30, A-16, Q-16 to Q-18, risks and YAGNI rows; drafted *Selected Approach*, architecture and data flow, pending the user's confirmation; renamed the planned MLflow and Feature Engineering spike from 03 to 05 because `spikes/databricks/03_spike_kafka_unreachable.py` already uses 03; updated *Suggested Requirements for Define* and *Self-Review*. Status stays Exploring | User answers of 2026-10-20 | D-27 refines D-20 (monthly table, trailing window). `/define` inherits Q-16 to Q-18 and A-04, A-12, A-16 |
| 2026-10-20 | User feedback before confirmation: added F-31 (label loss by month under the 3-month rule and a minimum-1-month variant); Q-16 kept open with that evidence; Q-17 answered as D-33 (separate PEAK_MODEL job after the Silver/Gold pipeline update, no `/iterate` on `METER_INGESTION`), discovery row 15, D-24 refined; spike 05 made a hard gate before `/design` in *Selected Approach*, Assumptions and Next Step, with the fallback differences of tasks 2, 4 and 5. Status stays Exploring | User feedback of 2026-10-20 | `/define` inherits Q-16 and Q-18; `/design` is blocked until spike 05 passes or the fallback is chosen |
| 2026-10-20 | Q-16 answered (strict 3-month window, D-27 unchanged) as discovery row 16 and D-34; user confirmed the Selected Approach and data flow (D-33, spike 05 gate); *Confirmed by* set; moved D-33 from the discovery table, where it had been inserted by mistake, to *Key Decisions*; replaced the "deliberately incomplete" header and pointed the dependency at the archived `METER_INGESTION` and its contracts (SHIPPED F-08); risks, Self-Review and Next Step updated. Status set to Ready for Define: gate checked (16 discovery answers, 9 topics with 2 or 3 options each, one option per topic chosen and the combination confirmed by the user, YAGNI list, profiling, open assumptions with their spike, Self-Review) | User decisions of 2026-10-20 | `/define` starts from this document; Q-18 open for `/define`; spike 05 must pass or the D-32 fallback be chosen before `/design` |

---

## Next Step

`/define .claude/sdd/features/BRAINSTORM_PEAK_MODEL.md` (Q-18 is resolved there).

**Hard gate before `/design`:** spike 05 (A-04, A-12, A-16) must pass, or the D-32 fallback be
chosen, because a failed A-12 changes tasks 2, 4 and 5.
