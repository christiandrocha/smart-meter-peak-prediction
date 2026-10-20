# BRAINSTORM: Peak Model

> Phase 0. Explore intent and approaches before capturing requirements.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL |
| **Date** | 2026-10-15 |
| **Author** | Christian |
| **Status** | Exploring |

Allowed status values: `Exploring`, `Ready for Define`.

Target release: v0.1 (second of two features of the end-to-end thin slice).

**This document is deliberately incomplete.** It was split out of
`BRAINSTORM_SMART_METER_ML_FOUNDATION.md` on 2026-10-15 and carries forward the decisions and
analysis that are already settled. Its own `/brainstorm` session will complete it later: weather
and holiday profiling, confirmation of the consumer, the approach comparison, and the feature,
split and model questions. Sections that still need that session are marked *To complete in the
PEAK_MODEL brainstorm*.

The feature depends on `BRAINSTORM_METER_INGESTION.md`, which delivers Gold
`household_daily_consumption` and `household_data_quality`.

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

Answers inherited from the original discovery (2026-10-06/07) and the answers of 2026-10-15.
*To complete in the PEAK_MODEL brainstorm:* open questions about the feature set, ranges and model.

| # | Question | Answer | Impact |
|---|---|---|---|
| 1 | ML framing: which prediction task? | Binary classification: does a household exceed its usual daily consumption on the next day (D-05), with a same-weekday baseline and a 1.3x threshold (D-16, label decision below) | Label defined at daily grain; forecasting deferred to v0.3 |
| 2 | Consumers: who reads the output? | Answered Q-08 (2026-10-15): a demand-response team (hypothetical) reads the next day's at-risk households once per day. Daily batch scoring writes a Gold predictions table with `household_id`, `target_date`, `score`, `label`, `model_version`, `scored_at`. No real-time consumer in v0.1 | Batch scoring only; serving endpoint out of scope. The consumer is hypothetical; confirm in the PEAK_MODEL brainstorm whether any service-level expectation exists |
| 3 | Which households may be trained on? | Answered Q-09 (2026-10-15): exclude a household when coverage < 80% or zero share >= 90%; both are parameters. `PEAK_MODEL` owns and applies these thresholds on top of `household_data_quality` from `METER_INGESTION` | Matches the seed-42 sample and catches MAC004067 and MAC004672 (F-05, F-06, F-13) |
| 4 | Which external data enriches the features? | Hourly weather and UK bank holidays as dimensions (see *Weather and holidays*) | Weather timezone must be confirmed (A-07) before any join |
| 5 | Feature set, train / validation / test ranges, model family | Not decided | To complete in the PEAK_MODEL brainstorm (Q-02, Q-03, Q-12) |

---

## Sample Data Inventory

| Type | Location | Volume | Notes |
|---|---|---|---|
| Input data: daily consumption | Gold `household_daily_consumption` from `METER_INGESTION` | One row per household-day; seed-42 sample: 60 households | Includes `is_complete_day`; 99.1% of household-days complete |
| Input data: household quality facts | `household_data_quality` from `METER_INGESTION` | One row per household | Coverage ratio, zero share, first / last reading, gap count; no exclusion flag |
| Input data: household attributes | Silver households from `METER_INGESTION` | 60 rows for seed 42 | `acorn_group`, `tariff`; static in v0.1 |
| Input data: weather | `data/raw/weather_hourly_darksky.csv` | Hourly, 2011-11 to 2014-03 | Not yet profiled; timezone unconfirmed (A-07) |
| Input data: calendar | `data/raw/uk_bank_holidays.csv` | UK bank holidays 2012-2014 | Not yet profiled |
| Expected output | Gold predictions table (consumer: Q-08) | One row per eligible household per `target_date` | Schema set in `/define` |
| Ground truth | Derived from readings | N/A | Label computed from the readings themselves; no external ground truth |

Not used in v0.1: `daily_dataset`, `hhblock_dataset`, `weather_daily_darksky.csv`,
`acorn_details.csv`.

**Profiling findings** relevant to this feature are inherited from `BRAINSTORM_METER_INGESTION.md`
with the same IDs (F-05 dead meters, F-06 coverage, F-07 staggered start and end, F-10 UTC
readings, F-12 tariff mix, F-13 low coverage). New findings for weather and holidays:

| ID | Finding | Evidence | Implication |
|---|---|---|---|
| F-14 | Weather and holiday files not profiled | Not yet run through `scripts/profile_data.py` | *To complete in the PEAK_MODEL brainstorm:* profile both files (use `--start-id 14` where the report continues the numbering) before choosing weather features |

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
- **A-07 (pending):** weather timestamps are UTC, like the readings (F-10). Until validated,
  weather features are optional; a readings-only feature set must be sufficient for the thin slice.
- Observed weather of the target day used as a feature assumes a perfect forecast and inflates
  metrics; whether a forecast stand-in is acceptable is an open question.

---

## Approaches Explored

*To complete in the PEAK_MODEL brainstorm.* Candidate comparisons, none selected yet:

| Topic | Options to compare | Notes |
|---|---|---|
| Feature computation and storage | Unity Catalog feature table with a time-series key and point-in-time lookup vs a plain Delta table with a manual as-of join | Feature Engineering availability on Free Edition is unverified (A-12) |
| Weather in v0.1 | Readings-only core, add mean temperature of the feature day after A-07, or use observed temperature of the target day as a forecast stand-in | See *Weather and holidays* |
| Model family | Gradient boosted trees vs logistic regression baseline | Determinism and quota (OD) to discuss |
| Operating threshold | Maximum F1 vs a minimum precision the consumer can act on | Depends on the consumer |

---

## Selected Approach

| Attribute | Value |
|---|---|
| **Chosen** | Not selected yet |
| **Confirmed by** | Pending, PEAK_MODEL brainstorm |
| **Reasoning** | The approach comparison is part of the PEAK_MODEL brainstorm |

**Carried-forward flow (draft, from the original architecture):**

```text
  Gold household_daily_consumption   household_data_quality   weather, holidays
                 \                          |                        /
                  label + daily features (point-in-time correct)
                                    |
                      UC feature table + training set
                  (exclusion thresholds applied here, temporal split)
                                    |
                      MLflow run -> UC model @champion
                                    |
                      batch scoring -> Gold predictions
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

**Release roadmap (model side):**

| Release | Scope |
|---|---|
| v0.1 | Label, minimal daily features, point-in-time training set, one registered model, batch scoring |
| v0.2 | Broader feature set, point-in-time features against the household dimension |
| v0.3 | Forecasting and temporal backtesting, monitoring |
| v0.4 | Serving |

---

## Assumptions & Open Questions

| ID | Assumption or question | How it will be resolved | Status |
|---|---|---|---|
| A-04 | MLflow registers models in UC and resolves aliases on Free Edition | Spike `spikes/databricks/03_spike_mlflow_uc.py` | Pending |
| A-07 | Weather timestamps are UTC, like readings (F-10) | Profiling the weather file in Databricks | Pending |
| A-12 | Databricks Feature Engineering in UC (feature tables with a time-series key, point-in-time lookup, model logging with feature lineage) is available on Free Edition serverless | Spike 03 | Pending |
| A-15 | `METER_INGESTION` delivers `household_data_quality` over a window that supports the training-range coverage definition | Align contracts in the two `/define` sessions | Pending |

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Label threshold is a business choice (L-01 to L-03) | Positive rate swings from 7.9% to 21.4% between 1.5x and 1.2x | Record the choice and the label analysis table in an ADR |
| Seasonal shift in positive rate (L-03) | A temporal split could put one season only in test | Training range covers at least one full year; evaluate per month |
| Test range winter only (lowest positive rate) | Noisy per-group and per-month test metrics | Decide ranges in the PEAK_MODEL brainstorm; report group and month metrics with counts |
| Feature leakage from the target day | Inflated metrics | Features use only data available at the end of the previous day; leakage test |
| Weather timezone mismatch (A-07) | Misaligned weather features | Validate before joining; readings-only fallback |
| Hypothetical consumer | No real service-level expectations | Keep the contract minimal; revisit if a real consumer appears |
| `METER_INGESTION` interface changes | Rework here | Interface fixed in its `/define`; changes through `/iterate` on both features |

### Open questions for the PEAK_MODEL brainstorm and `/define`

| ID | Question | Notes |
|---|---|---|
| Q-02 | Feature grain and minimum feature set for v0.1 | Daily grain proposed. Draft inputs from the superseded DEFINE: one row per household per feature date D for target date D + 1; total and max energy of D, 7-day and 28-day averages, the same-weekday median baseline for D + 1, share of complete days in 28 days, target weekday and month, static ACORN group and tariff; optional mean temperature of D after A-07 and a bank-holiday flag for the target date |
| Q-03 | Train, validation and test date ranges inside the study period | Must cover more than one season (L-03). Draft inputs: train 2012-07-29 to 2013-07-31, validation 2013-08-01 to 2013-11-30, test 2013-12-01 to 2014-02-27 (earliest labellable date is 2012-07-29; 2014-02-28 holds only the 00:00 reading) |
| Q-12 | Model family, operating threshold rule and determinism | Baseline model only in v0.1 |
| Q-13 | Do weather features enter v0.1 or wait for v0.2 | Depends on profiling (F-14) and A-07 |
| Q-14 | Point-in-time household exclusion: thresholds applied to a whole-period quality metric leak test-period information into training. Exclusions must use `household_data_quality_monthly` (from METER_INGESTION) restricted to data before each split boundary or target date | Raised 2026-10-15 while settling METER_INGESTION Q-11 |

Q-01 (label threshold) is answered by D-19; Q-08 and Q-09 are answered (D-21, D-20).

---

## Suggested Requirements for Define

*Draft. To be confirmed in the PEAK_MODEL brainstorm.*

- **Problem statement (draft):** Provide a demand-response team with a once-per-day list of
  households likely to exceed their usual consumption the next day, by deriving a point-in-time
  correct label and daily features from governed consumption data, training and registering one
  model with lineage, and batch-scoring eligible households.
- **Success criteria (draft):**
  - Labels follow D-19 exactly: strictly greater than 1.3 x the same-weekday median of 4 complete
    days within 8 weeks, no label otherwise; verified against a hand-computed fixture.
  - No feature for a target day uses data from that day or later (leakage test); splits are
    temporal and never shuffled.
  - Households with coverage < 80% or zero share >= 90% are excluded from training and listed with
    their reason; both thresholds are changeable without code changes.
  - The registered model version links to its training run and feature table in UC lineage; alias
    `champion` resolves.
  - Evaluation reports PR-AUC and precision / recall, overall and per ACORN group; test PR-AUC is
    above the test positive rate; accuracy alone is not reported.
  - Scoring writes exactly one row per eligible household per `target_date`, and re-running it
    changes nothing except `scored_at`.
- **Constraints:**
  - Free Edition serverless only.
  - No credentials in code, bundle files or git.
  - Label threshold, baseline window, lookback, split dates and exclusion thresholds are parameters.
  - Time is UTC end to end; event time and processing time are separate columns.

---

## Self-Review

- **Weak points:**
  - The document is intentionally an Exploring draft: approaches, consumer confirmation, weather
    profiling and the model questions are not done.
  - All label numbers come from a sampling run on a sample whose script is not yet in the
    repository, so they cannot be regenerated today.
  - The consumer is hypothetical (Q-08); no service-level expectations exist.
  - Weather and holiday files are not profiled; A-07 is the only check planned.
  - The draft feature set and ranges quoted in the open questions come from a superseded DEFINE
    draft and are inputs, not decisions.
- **Risks:** The label threshold moves the positive rate between 7.9% and 21.4%; seasonality can
  make a temporal split unrepresentative; Free Edition may lack Feature Engineering capabilities
  (A-12) or UC lineage.
- **What I would do differently:** Profile weather and holidays and confirm the interface tables of
  `METER_INGESTION` before writing the label analysis into a requirement.
- **Next improvement:** Run `/brainstorm` for PEAK_MODEL once `METER_INGESTION` is defined: profile
  weather and holidays, resolve A-07, compare the approaches in the table above, answer Q-02, Q-03,
  Q-12 and Q-13, then set the status to `Ready for Define`.

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-15 | Created by splitting `BRAINSTORM_SMART_METER_ML_FOUNDATION.md` (status Ready for Define). Carried over: label decision (D-05, D-16, new D-19 with the 8-week lookback confirmed by the user), exclusion thresholds (Q-09 as D-20), consumer (Q-08 as D-21), label analysis L-01 to L-04, A-04, A-07, A-12, ML risks and YAGNI items. Added F-14, A-15, Q-12, Q-13 and D-22. Status set to Exploring because approaches, weather profiling and the feature, range and model questions remain open | User decision of 2026-10-15: split into METER_INGESTION and PEAK_MODEL | No DEFINE exists for this feature; `DEFINE_SMART_METER_ML_FOUNDATION.md` is a source only until PEAK_MODEL reaches Ready for Define; contracts for features and predictions belong here; the original brainstorm file is to be removed with `git rm` by the caller |

---

## Next Step

`/brainstorm` session for PEAK_MODEL to complete this document, then
`/define .claude/sdd/features/BRAINSTORM_PEAK_MODEL.md`.
