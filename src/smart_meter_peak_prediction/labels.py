"""Label library: the D-19 label of T, the D-27 / D-34 eligibility window and its reasons.

``ml.household_labels_daily`` has one row per household of ``silver.households`` per target date
T = D + 1, for every feature date D of the feature table (FR-21, FR-22). The label uses the same
baseline function as the feature ``median_energy_kwh_same_weekday_8w`` (``features.py``).

Eligibility of T uses only monthly quality rows of the E latest study months whose last day is
before T, so appending later months never changes a decision for T on or before the first day of
the next month (AC-46). When the history is insufficient, coverage and zero share are not
evaluated and ``insufficient_history`` is the only reason.
"""

from __future__ import annotations

from datetime import date, timedelta

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from smart_meter_peak_prediction import features
from smart_meter_peak_prediction.peak_config import PeakParameters

# ml.household_labels_daily (DEFINE inline schema): column -> Spark SQL type.
LABEL_COLUMNS = {
    "household_id": "string",
    "target_date": "date",
    "feature_date": "date",
    "total_energy_kwh": "double",
    "baseline_energy_kwh": "double",
    "baseline_day_count": "int",
    "label_consumption_spike": "int",
    "eligibility_month_count": "int",
    "coverage_ratio_3m": "double",
    "zero_share_3m": "double",
    "is_eligible": "boolean",
    "ineligibility_reasons": "array<string>",
}
KEY_COLUMNS = ["household_id", "target_date"]
NOT_NULL_COLUMNS = ("household_id", "target_date", "is_eligible")
REASONS = ("insufficient_history", "low_coverage", "high_zero_share")


class LabelQualityError(Exception):
    """QR-19 was violated."""


def _eligibility(
    grid: DataFrame, monthly: DataFrame, households: DataFrame, params: PeakParameters
) -> DataFrame:
    """Window sums per ``(household_id, target_date)`` from the dense monthly facts."""
    e = params.eligibility_months
    known = monthly.join(households.select("household_id"), "household_id", "inner").select(
        "household_id",
        F.col("reading_month").alias("_month"),
        "expected_readings",
        "observed_readings",
        "zero_readings",
    )
    window_months = grid.select("household_id", "target_date").withColumn(
        "_month",
        F.explode(
            F.expr(
                "sequence(add_months(trunc(target_date, 'MM'), "
                f"-{e}), add_months(trunc(target_date, 'MM'), -1), interval 1 month)"
            )
        ),
    )
    return (
        window_months.join(known, ["household_id", "_month"], "left")
        .groupBy("household_id", "target_date")
        .agg(
            F.count("expected_readings").cast("int").alias("eligibility_month_count"),
            F.sum("expected_readings").alias("_expected"),
            F.sum("observed_readings").alias("_observed"),
            F.sum("zero_readings").alias("_zero"),
        )
    )


def evaluate_labels(
    households: DataFrame,
    daily: DataFrame,
    monthly: DataFrame,
    params: PeakParameters,
    study_start: date,
) -> DataFrame:
    """Labels and eligibility of every household and target date, plus ``is_target_complete``.

    ``is_target_complete`` is not a table column; it is kept so that ``check_labels`` can verify
    QR-19 against the completeness of T.
    """
    n, e = params.baseline_day_count, params.eligibility_months
    base = features.same_weekday_baseline(
        features.base_frame(households, daily, study_start), params
    )
    target_day = daily.select(
        "household_id",
        F.col("reading_date").alias("target_date"),
        F.col("total_energy_kwh").alias("_target_total"),
        F.col("is_complete_day").alias("_target_complete"),
    )
    grid = (
        base.withColumn("target_date", F.date_add("feature_date", 1))
        .join(target_day, ["household_id", "target_date"], "left")
        .withColumn("is_target_complete", F.coalesce("_target_complete", F.lit(False)))
        .withColumnRenamed("_target_total", "total_energy_kwh")
    )
    window = _eligibility(grid, monthly, households, params)
    joined = grid.join(window, ["household_id", "target_date"], "left")

    count = F.col("eligibility_month_count")
    full = count == e
    coverage = F.when(full, F.col("_observed") / F.col("_expected"))
    zero_share = F.when(full & (F.col("_observed") > 0), F.col("_zero") / F.col("_observed"))
    reasons = F.filter(
        F.array(
            F.when(count < e, F.lit(REASONS[0])),
            F.when(full & (coverage < F.lit(params.coverage_min)), F.lit(REASONS[1])),
            F.when(
                full & (zero_share.isNull() | (zero_share >= F.lit(params.zero_share_max))),
                F.lit(REASONS[2]),
            ),
        ),
        lambda x: x.isNotNull(),
    )
    spike = F.when(
        F.col("total_energy_kwh") > F.lit(params.label_threshold) * F.col("baseline_energy_kwh"),
        F.lit(1),
    ).otherwise(F.lit(0))
    label = F.when(F.col("is_target_complete") & (F.col("baseline_day_count") == n), spike)
    return (
        joined.withColumn("coverage_ratio_3m", coverage)
        .withColumn("zero_share_3m", zero_share)
        .withColumn("ineligibility_reasons", reasons)
        .withColumn("is_eligible", F.size("ineligibility_reasons") == 0)
        .withColumn("label_consumption_spike", label.cast("int"))
        .withColumn("eligibility_month_count", F.coalesce(count, F.lit(0)).cast("int"))
        .select(*LABEL_COLUMNS, "is_target_complete")
    )


def table_columns(evaluated: DataFrame) -> DataFrame:
    """The evaluated frame in table column order, without helper columns."""
    return evaluated.select(*LABEL_COLUMNS)


def check_labels(
    evaluated: DataFrame,
    params: PeakParameters,
    households: DataFrame,
    study_start: date,
    end: date,
) -> int:
    """QR-19 and G-10. ``end`` is the latest feature date. Raises before anything is written.

    - the label is null, 0 or 1, and non-null exactly when T is complete and the baseline day
      count equals N;
    - ``is_eligible`` is true exactly when ``ineligibility_reasons`` is empty;
    - the table is dense: households x target dates T = D + 1 with unique keys (G-10).
    """
    violations = evaluated.agg(
        F.sum(
            F.when(
                ~F.col("label_consumption_spike").isin(0, 1)
                & F.col("label_consumption_spike").isNotNull(),
                1,
            ).otherwise(0)
        ).alias("bad_value"),
        F.sum(
            F.when(
                F.col("label_consumption_spike").isNotNull()
                != (
                    F.col("is_target_complete")
                    & (F.col("baseline_day_count") == params.baseline_day_count)
                ),
                1,
            ).otherwise(0)
        ).alias("bad_presence"),
        F.sum(
            F.when(
                F.col("is_eligible") != (F.size("ineligibility_reasons") == 0),
                1,
            ).otherwise(0)
        ).alias("bad_eligibility"),
    ).first()
    found = {name: int(count or 0) for name, count in violations.asDict().items() if count}
    if found:
        raise LabelQualityError(f"QR-19 violations: {found}")
    return features.check_density(
        evaluated,
        households,
        study_start + timedelta(days=1),
        end + timedelta(days=1),
        "target_date",
        "labels",
    )


def build_labels(
    households: DataFrame,
    daily: DataFrame,
    monthly: DataFrame,
    params: PeakParameters,
    study_start: date,
) -> DataFrame:
    """Compute, check (QR-19, G-10) and return the label table content in column order."""
    evaluated = evaluate_labels(households, daily, monthly, params, study_start)
    check_labels(evaluated, params, households, study_start, features.latest_reading_date(daily))
    return table_columns(evaluated)


def label_table_properties(params: PeakParameters) -> dict[str, str]:
    """Label and eligibility parameters of the build (FR-31), stored as table properties."""
    return params.label_properties()
