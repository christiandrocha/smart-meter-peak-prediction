"""Gold library: daily consumption, orphan check, study months and dense monthly data quality.

All functions take DataFrames of the published Silver tables and return DataFrames, so the
pipeline and the local test harness run the same code. Gold holds facts only: no threshold, no
exclusion flag and no label (PEAK_MODEL decides). Months and days are UTC calendar units.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from smart_meter_peak_prediction.config import Settings

SLOTS_PER_DAY = 48
SLOT_SECONDS = 1800

DAILY_COLUMNS = [
    "household_id",
    "reading_date",
    "total_energy_kwh",
    "max_energy_kwh",
    "reading_count",
    "is_complete_day",
]
MONTHLY_COLUMNS = [
    "household_id",
    "has_household_record",
    "reading_month",
    "expected_readings",
    "observed_readings",
    "zero_readings",
    "gap_count",
    "first_reading_ts",
    "last_reading_ts",
]


def daily_consumption(silver: DataFrame) -> DataFrame:
    """``gold.household_daily_consumption``: one row per household per UTC day with a reading."""
    return (
        silver.groupBy("household_id", "reading_date")
        .agg(
            F.sum("energy_kwh").alias("total_energy_kwh"),
            F.max("energy_kwh").alias("max_energy_kwh"),
            F.count(F.lit(1)).cast("int").alias("reading_count"),
        )
        .withColumn("is_complete_day", F.col("reading_count") == SLOTS_PER_DAY)
        .select(*DAILY_COLUMNS)
    )


def orphan_check(daily: DataFrame, households: DataFrame) -> DataFrame:
    """Private ``daily_consumption_orphan_check``: one row per household in daily consumption.

    QR-12 counts the rows with ``is_known_household = false`` (orphans are kept and counted).
    """
    known = households.select("household_id").distinct().withColumn("_known", F.lit(True))
    return (
        daily.select("household_id")
        .distinct()
        .join(known, "household_id", "left")
        .select("household_id", F.coalesce("_known", F.lit(False)).alias("is_known_household"))
    )


def study_months(spark: SparkSession, settings: Settings) -> DataFrame:
    """One row per UTC month of the study period with its expected number of readings.

    ``expected_readings`` is 48 x the days of the month inside ``[study_start, study_end]``.
    """
    start, end = settings.study_start_date_sql, settings.study_end_date_sql
    return spark.sql(
        f"""
        SELECT month AS reading_month,
               CAST({SLOTS_PER_DAY} * (datediff(least(last_day(month), {end}),
                                                greatest(month, {start})) + 1) AS INT)
                 AS expected_readings
        FROM (SELECT explode(sequence(trunc({start}, 'MM'), trunc({end}, 'MM'),
                                      interval 1 month)) AS month)
        """
    )


def monthly_quality(silver: DataFrame, households: DataFrame, settings: Settings) -> DataFrame:
    """``gold.household_data_quality_monthly``: dense household x study-month facts.

    The household set is the union of ``silver.households`` and the households with any Silver
    reading, so an orphan and a household without readings both get every study month
    (AC-33, AC-35). A gap event is a step between two consecutive Silver readings of a household
    larger than one slot; it belongs to the month of the reading that ends it. The lag looks
    backwards only, so a month's values depend on readings up to the end of that month (AC-24).
    """
    spark = silver.sparkSession
    months = study_months(spark, settings)
    known = households.select("household_id").distinct().withColumn("_known", F.lit(True))
    ids = households.select("household_id").union(silver.select("household_id")).distinct()
    grid = (
        ids.join(known, "household_id", "left")
        .withColumn("has_household_record", F.coalesce("_known", F.lit(False)))
        .drop("_known")
        .crossJoin(months)
    )

    ordered = Window.partitionBy("household_id").orderBy("reading_ts")
    facts = (
        silver.select("household_id", "reading_ts", "energy_kwh")
        .withColumn("prev_ts", F.lag("reading_ts").over(ordered))
        .withColumn(
            "missing_slots",
            (F.unix_seconds("reading_ts") - F.unix_seconds("prev_ts")) / SLOT_SECONDS - 1,
        )
        .withColumn("reading_month", F.trunc("reading_ts", "MM"))
        .groupBy("household_id", "reading_month")
        .agg(
            F.count(F.lit(1)).alias("observed_readings"),
            F.sum(F.when(F.col("energy_kwh") == 0, 1).otherwise(0)).alias("zero_readings"),
            F.sum(F.when(F.col("missing_slots") > 0, 1).otherwise(0)).alias("gap_count"),
            F.min("reading_ts").alias("first_reading_ts"),
            F.max("reading_ts").alias("last_reading_ts"),
        )
    )
    dense = grid.join(facts, ["household_id", "reading_month"], "left")
    return dense.select(
        "household_id",
        "has_household_record",
        "reading_month",
        "expected_readings",
        F.coalesce("observed_readings", F.lit(0)).cast("int").alias("observed_readings"),
        F.coalesce("zero_readings", F.lit(0)).cast("int").alias("zero_readings"),
        F.coalesce("gap_count", F.lit(0)).cast("int").alias("gap_count"),
        "first_reading_ts",
        "last_reading_ts",
    )
