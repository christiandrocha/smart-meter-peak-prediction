"""Feature library: the dense household x date grid, the shared baseline and the D-28 features.

``ml.household_features_daily`` has exactly one row per household of ``silver.households`` per
feature date D, from the study start to the latest Gold ``reading_date`` (FR-20). Because the grid
is dense, a row offset in a ``ROWS`` window equals a day offset, and the point-in-time lookup of
the Feature Engineering client (as-of semantics, ADR 0007) always finds the row dated exactly
T - 1 and never an older one. Every value of a row dated D uses only data dated D or earlier
(NFR-12).

The same-weekday baseline is computed once here and reused by ``labels.py``, so the feature
``median_energy_kwh_same_weekday_8w`` is by construction the D-19 baseline of T = D + 1.
"""

from __future__ import annotations

from datetime import date

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from smart_meter_peak_prediction.peak_config import PeakParameters
from smart_meter_peak_prediction.weather import daily_temperature

# ml.household_features_daily (DEFINE inline schema): column -> Spark SQL type.
FEATURE_TABLE_COLUMNS = {
    "household_id": "string",
    "feature_date": "date",
    "total_energy_kwh_1d": "double",
    "max_energy_kwh_1d": "double",
    "avg_energy_kwh_7d": "double",
    "avg_energy_kwh_28d": "double",
    "median_energy_kwh_same_weekday_8w": "double",
    "complete_day_share_28d": "double",
    "target_weekday": "int",
    "target_month": "int",
    "acorn_group": "string",
    "tariff": "string",
    "mean_temperature_c_1d": "double",
    "temperature_hour_count_1d": "int",
}
KEY_COLUMNS = ["household_id", "feature_date"]
FEATURE_VALUE_COLUMNS = [c for c in FEATURE_TABLE_COLUMNS if c not in KEY_COLUMNS]
NOT_NULL_COLUMNS = (
    "household_id",
    "feature_date",
    "complete_day_share_28d",
    "temperature_hour_count_1d",
)


class DensityError(Exception):
    """G-10: an output is not exactly households x dates with unique keys."""


# ----------------------------------------------------------------------------- grid
def latest_reading_date(daily: DataFrame) -> date:
    """Latest ``reading_date`` of ``gold.household_daily_consumption``."""
    latest = daily.agg(F.max("reading_date")).first()[0]
    if latest is None:
        raise ValueError("gold.household_daily_consumption is empty: no feature dates to build")
    return latest


def date_grid(spark: SparkSession, start: date, end: date) -> DataFrame:
    """One row per UTC date from ``start`` to ``end`` inclusive, column ``feature_date``."""
    return spark.sql(
        f"SELECT explode(sequence(DATE'{start:%Y-%m-%d}', DATE'{end:%Y-%m-%d}', "
        "interval 1 day)) AS feature_date"
    )


def base_frame(
    households: DataFrame, daily: DataFrame, study_start: date, end: date | None = None
) -> DataFrame:
    """Dense grid joined with the Gold day of D.

    Columns: ``household_id``, ``feature_date``, ``acorn_group``, ``tariff``, ``total``, ``max``
    (as stored, null without a Gold row) and ``complete`` (false without a Gold row).
    """
    end = end or latest_reading_date(daily)
    spark = households.sparkSession
    grid = households.select("household_id", "acorn_group", "tariff").crossJoin(
        date_grid(spark, study_start, end)
    )
    gold = daily.select(
        "household_id",
        F.col("reading_date").alias("feature_date"),
        F.col("total_energy_kwh").alias("total"),
        F.col("max_energy_kwh").alias("max"),
        F.col("is_complete_day").alias("_is_complete_day"),
    )
    return grid.join(gold, ["household_id", "feature_date"], "left").select(
        "household_id",
        "feature_date",
        "acorn_group",
        "tariff",
        "total",
        "max",
        F.coalesce("_is_complete_day", F.lit(False)).alias("complete"),
    )


def household_window() -> Window:
    return Window.partitionBy("household_id").orderBy("feature_date")


# ----------------------------------------------------------------------------- baseline
def same_weekday_baseline(base: DataFrame, params: PeakParameters) -> DataFrame:
    """Add ``baseline_energy_kwh`` and ``baseline_day_count`` of T = D + 1 to the dense frame.

    Candidate k is the complete day T - 7k = D - (7k - 1) for k = 1 to ``label_lookback_weeks``.
    The most recent ``baseline_day_count`` (N) complete candidates are taken, and the baseline
    is their median (the middle value for odd N, the mean of the two middle values for even N).
    It is null when fewer than N complete candidates exist.
    """
    window = household_window()
    complete_total = F.when(F.col("complete"), F.col("total"))
    candidates = [
        F.lag(complete_total, 7 * k - 1).over(window)
        for k in range(1, params.label_lookback_weeks + 1)
    ]
    n = params.baseline_day_count
    return (
        base.withColumn("_found", F.filter(F.array(*candidates), lambda x: x.isNotNull()))
        .withColumn("baseline_day_count", F.least(F.size("_found"), F.lit(n)).cast("int"))
        .withColumn(
            "baseline_energy_kwh",
            F.when(F.size("_found") >= n, _median_of_latest("_found", n)),
        )
        .drop("_found")
    )


def _median_of_latest(found: str, n: int) -> Column:
    """Median of the first ``n`` (most recent) elements of the array column ``found``."""
    chosen = F.array_sort(F.slice(found, 1, n))
    if n % 2 == 1:
        return F.get(chosen, n // 2)
    return (F.get(chosen, n // 2 - 1) + F.get(chosen, n // 2)) / F.lit(2.0)


# ----------------------------------------------------------------------------- features
def build_features(
    households: DataFrame,
    daily: DataFrame,
    silver_weather: DataFrame,
    params: PeakParameters,
    study_start: date,
) -> DataFrame:
    """The full ``ml.household_features_daily`` content (FR-20) in table column order."""
    base = same_weekday_baseline(base_frame(households, daily, study_start), params)
    window = household_window()
    days_7 = window.rowsBetween(-6, 0)
    days_28 = window.rowsBetween(-27, 0)
    complete_total = F.when(F.col("complete"), F.col("total"))
    featured = (
        base.withColumn("avg_energy_kwh_7d", F.avg(complete_total).over(days_7))
        .withColumn("avg_energy_kwh_28d", F.avg(complete_total).over(days_28))
        .withColumn(
            "complete_day_share_28d",
            F.sum(F.when(F.col("complete"), 1).otherwise(0)).over(days_28) / F.lit(28.0),
        )
    )
    temperature = daily_temperature(silver_weather).withColumnRenamed(
        "weather_date", "feature_date"
    )
    target = F.date_add("feature_date", 1)
    return (
        featured.join(temperature, "feature_date", "left")
        .select(
            "household_id",
            "feature_date",
            F.col("total").alias("total_energy_kwh_1d"),
            F.col("max").alias("max_energy_kwh_1d"),
            "avg_energy_kwh_7d",
            "avg_energy_kwh_28d",
            F.col("baseline_energy_kwh").alias("median_energy_kwh_same_weekday_8w"),
            "complete_day_share_28d",
            (F.weekday(target) + 1).cast("int").alias("target_weekday"),
            F.month(target).cast("int").alias("target_month"),
            "acorn_group",
            "tariff",
            "mean_temperature_c_1d",
            F.coalesce("temperature_hour_count_1d", F.lit(0))
            .cast("int")
            .alias("temperature_hour_count_1d"),
        )
        .select(*FEATURE_TABLE_COLUMNS)
    )


# ----------------------------------------------------------------------------- checks
def check_density(
    df: DataFrame,
    households: DataFrame,
    start: date,
    end: date,
    date_column: str,
    name: str,
) -> int:
    """G-10: rows = households x dates and unique ``(household_id, date)`` keys. Returns rows."""
    n_households = households.select("household_id").distinct().count()
    n_days = (end - start).days + 1
    stats = df.agg(
        F.count(F.lit(1)).alias("rows"),
        F.countDistinct("household_id", date_column).alias("keys"),
        F.min(date_column).alias("first"),
        F.max(date_column).alias("last"),
    ).first()
    expected = n_households * n_days
    if stats["rows"] != expected or stats["keys"] != expected:
        raise DensityError(
            f"G-10 {name}: {stats['rows']} rows and {stats['keys']} unique keys, expected "
            f"{n_households} households x {n_days} dates = {expected}"
        )
    if stats["first"] != start or stats["last"] != end:
        raise DensityError(
            f"G-10 {name}: dates {stats['first']} to {stats['last']}, expected {start} to {end}"
        )
    return expected


def check_features(df: DataFrame, households: DataFrame, study_start: date, end: date) -> int:
    """G-10 for the feature table, plus the not-null columns of the contract."""
    rows = check_density(df, households, study_start, end, "feature_date", "features")
    for column in NOT_NULL_COLUMNS:
        if df.where(F.col(column).isNull()).limit(1).count():
            raise DensityError(f"features: column {column} holds a null")
    return rows


def feature_table_properties(params: PeakParameters) -> dict[str, str]:
    """Baseline parameters of the build, stored as table properties (cross-checked at training)."""
    return params.feature_properties()


# ----------------------------------------------------------------------------- lookup (1B)
def explicit_lookup(rows: DataFrame, features: DataFrame) -> DataFrame:
    """Join ``rows`` (``household_id``, ``target_date``) to the feature row dated T - 1.

    This is the 1B fallback and the test oracle of the Feature Engineering lookup. A missing
    feature row gives nulls.
    """
    lookup = features.select(
        "household_id",
        F.col("feature_date").alias("_lookup_date"),
        *FEATURE_VALUE_COLUMNS,
    )
    return (
        rows.withColumn("_lookup_date", F.date_sub("target_date", 1))
        .join(lookup, ["household_id", "_lookup_date"], "left")
        .drop("_lookup_date")
    )
