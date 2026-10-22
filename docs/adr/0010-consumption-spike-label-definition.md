# 0010. Next-day consumption spike label: strictly above 1.3 x the median of the last 4 complete same-weekday days within 8 weeks

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-21 |
| **Deciders** | Christian |
| **Related** | PEAK_MODEL; FR-20, FR-21, FR-31; AC-43, AC-44, AC-63; D-05, D-16, D-19; L-01 to L-04; F-28; ADR 0007 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

The model predicts whether a household consumes "well above its usual level" on the next day
(D-05). What "usual" means and how far above it counts as a spike is a business choice: it decides
the positive rate, the seasonal behaviour of the target and what the model can learn. The user
decided the label on 2026-10-15 (D-19). The brainstorm risk table and the DEFINE Self-Review ask for
that choice and its evidence to be recorded as a decision that outlives the feature, because any
later model (v0.2 features, v0.3 forecasting) is compared against it.

Label analysis (seed-42 sample, full days only, whole study period; brainstorm *Label analysis*):

| Baseline for "usual" consumption | Threshold | Positive rate |
|---|---|---|
| Median of previous 7 days | > 1.3x | 13.2% |
| Median of previous 28 days | > 1.2x / 1.3x / 1.5x | 21.3% / 14.3% / 7.3% |
| Mean of previous 28 days + k std | k = 1.0 / 1.5 | 17.6% / 9.4% |
| **Median of last 4 same-weekday days** | **> 1.2x / 1.3x / 1.5x** | **21.4% / 14.7% / 7.9%** |

Findings:
- L-01: calendar-day baselines give about 22% positives on Sundays against about 12.5% on weekdays.
- L-02: the same-weekday baseline keeps positives at 14% to 15% on every weekday.
- L-03: seasonality remains (about 21.5% in October, 8.8% in February).
- L-04: the positive rate differs by ACORN group (Affluent about 17%, Adversity about 11%).

With the DEFINE definitions, the committed spike `spikes/local/a17_peak_labels_eligibility.py`
gives 33,093 labelled household-days at 14.61% positive. With threshold 1.5 it gives 7.91% (ADR 0007).

## Decision drivers

- The target must not encode the weekly cycle; otherwise a model scores well by learning
  "tomorrow is Sunday" (L-01).
- The positive rate should leave enough positives per month and per ACORN group for evaluation on
  60 households.
- A stale or partial baseline must not create labels after long gaps (F-06, F-07).
- The rule must be computable from Gold daily facts alone and testable on a hand-computed fixture.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Same-weekday median of the last 4 complete days within 8 weeks, threshold strictly greater than 1.3x; no label when T is incomplete or fewer than 4 such days exist** | Weekly cycle removed (L-02); 14.6% positives; the lookback limits stale baselines; robust to one outlier day (median) | Seasonality remains (L-03); the baseline lags the heating onset; households with irregular weekly patterns get few labels |
| Same-weekday median, threshold 1.2x | More positives (21.4%) | Milder deviations count as spikes, and the label is closer to noise |
| Same-weekday median, threshold 1.5x | Clearer spikes | 7.9% positives, which leaves few positives per month and group on 60 households |
| Calendar-day median of 7 or 28 days | Simpler, more labels | Encodes the weekly cycle (L-01) |
| Mean + k standard deviations over 28 days | Adapts to household variance | Sensitive to outliers; weekly cycle stays in the baseline |

## Decision

We record D-19 as the label of PEAK_MODEL v0.1: `label_consumption_spike = 1` when the total of
target day T is strictly greater than 1.3 x the median of the totals of the last 4 complete days with
the weekday of T among T - 7, T - 14, ..., T - 56. It is 0 when T is complete, 4 such days exist and
the total is at or below the bound. It is null when T is not complete or fewer than 4 such days
exist. The threshold, the day count and the lookback are parameters (FR-31). Their values for each
build are stored as table properties of `ml.household_labels_daily` and logged with every training
run. The label analysis above is the reference for any later change.

## Consequences

- **Positive:** A stable weekday-neutral target, documented with its alternatives. A later release can
  show its effect against the same table.
- **Negative:** The seasonal swing in the positive rate (L-03) carries into flag volumes at a fixed
  t (D-23). A parameter change (for example AC-63's 1.5) rewrites the label table and needs a
  retrain. The models registered before it are not comparable to the models after it.
- **What would make us revisit this:** a real consumer defining a spike in business terms (kWh or
  cost), a forecasting formulation (v0.3), or per-segment thresholds becoming necessary after the
  per-ACORN metrics are reviewed.
