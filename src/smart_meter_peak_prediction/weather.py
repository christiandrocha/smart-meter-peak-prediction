"""Weather library: Bronze projection, Silver hourly weather, daily temperature (FR-18, FR-19).

Bronze keeps the 12 source columns as raw text under snake_case names with the ``_raw`` suffix.
Silver parses the instant with an explicit ``+00:00`` offset, so ``weather_ts`` does not depend on
the session time zone (AC-37), and deduplicates on ``weather_ts`` (QR-17). The daily temperature
sums in a fixed order, so a recomputation is bitwise stable (ADR 0011).

Quality rules: QR-16 (time parses) and QR-18 parse (temperature is a finite number) raise
``WeatherQualityError`` before anything is written; QR-18 range is a counted warning.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from smart_meter_peak_prediction.bronze import RESCUED

# Source header names in file order (profile docs/profiling/weather_hourly_darksky.md).
SOURCE_COLUMNS = (
    "visibility",
    "windBearing",
    "temperature",
    "time",
    "dewPoint",
    "pressure",
    "apparentTemperature",
    "windSpeed",
    "precipType",
    "icon",
    "humidity",
    "summary",
)
WEATHER_SOURCE_SCHEMA = StructType([StructField(n, StringType(), True) for n in SOURCE_COLUMNS])

RAW_NAMES = {
    "time": "time_raw",
    "temperature": "temperature_raw",
    "apparentTemperature": "apparent_temperature_raw",
    "dewPoint": "dew_point_raw",
    "humidity": "humidity_raw",
    "pressure": "pressure_raw",
    "visibility": "visibility_raw",
    "windBearing": "wind_bearing_raw",
    "windSpeed": "wind_speed_raw",
    "precipType": "precip_type_raw",
    "icon": "icon_raw",
    "summary": "summary_raw",
}

# Bronze table schema (DEFINE inline schema): column -> Spark SQL type.
BRONZE_COLUMNS = {
    **{raw: "string" for raw in RAW_NAMES.values()},
    "_rescued_data": "string",
    "_source_file": "string",
    "_ingested_at": "timestamp",
}
RAW_COLUMNS = list(RAW_NAMES.values())

SILVER_COLUMNS = {
    "weather_ts": "timestamp",
    "temperature_c": "double",
    "_ingested_at": "timestamp",
}
DAILY_TEMPERATURE_COLUMNS = {
    "weather_date": "date",
    "mean_temperature_c_1d": "double",
    "temperature_hour_count_1d": "int",
}

TEMPERATURE_MIN_C = -30.0
TEMPERATURE_MAX_C = 45.0
EXAMPLE_LIMIT = 5

WEATHER_TS_SQL = "try_to_timestamp(concat(trim(time_raw), '+00:00'), 'yyyy-MM-dd HH:mm:ssXXX')"
TEMPERATURE_SQL = "try_cast(trim(temperature_raw) AS DOUBLE)"


class WeatherQualityError(Exception):
    """A fail rule of the Silver weather step (QR-16, QR-18 parse) was violated."""


@dataclass
class WeatherSilver:
    """Silver weather rows (lazy) and the counts of the step."""

    frame: DataFrame
    row_count: int
    duplicate_count: int  # QR-17 losers
    out_of_range_count: int  # QR-18 warn, among the kept rows


# ----------------------------------------------------------------------------- Bronze
def project_weather(df: DataFrame) -> DataFrame:
    """Source-header read (with ``_rescued_data`` and ``_metadata``) to the Bronze schema."""
    raw = [F.col(source).alias(RAW_NAMES[source]) for source in RAW_NAMES]
    return df.select(
        *raw,
        F.col(RESCUED).cast("string").alias(RESCUED),
        F.col("_metadata.file_path").alias("_source_file"),
        F.current_timestamp().alias("_ingested_at"),
    )


# ----------------------------------------------------------------------------- Silver
def _examples(df: DataFrame, column: str) -> list[str | None]:
    return [row[0] for row in df.select(column).limit(EXAMPLE_LIMIT).collect()]


def silver_weather(bronze: DataFrame) -> WeatherSilver:
    """Recompute ``silver.weather_hourly`` from all of Bronze.

    Raises ``WeatherQualityError`` (nothing returned, so nothing can be written) when a raw
    ``time`` does not parse (QR-16) or a raw temperature is not a finite number (QR-18).
    """
    parsed = bronze.withColumn("weather_ts", F.expr(WEATHER_TS_SQL)).withColumn(
        "temperature_c", F.expr(TEMPERATURE_SQL)
    )
    bad_time = parsed.where(F.col("time_raw").isNull() | F.col("weather_ts").isNull())
    bad_temperature = parsed.where(
        F.col("temperature_c").isNull()
        | F.isnan("temperature_c")
        | F.col("temperature_c").isin(float("inf"), float("-inf"))
    )
    n_bad_time, n_bad_temperature = bad_time.count(), bad_temperature.count()
    if n_bad_time:
        raise WeatherQualityError(
            f"QR-16: {n_bad_time} row(s) with a time that is not 'yyyy-MM-dd HH:mm:ss'; "
            f"first raw values: {_examples(bad_time, 'time_raw')}"
        )
    if n_bad_temperature:
        raise WeatherQualityError(
            f"QR-18: {n_bad_temperature} row(s) with a temperature that is not a number; "
            f"first raw values: {_examples(bad_temperature, 'temperature_raw')}"
        )

    # ADR 0005 order, extended by the raw values so that identical-time rows of one file and one
    # batch still have a deterministic winner (DESIGN, QR-17 rank).
    tie_break = [F.col("_ingested_at"), F.col("_source_file"), F.col("time_raw")]
    tie_break += [F.col(c) for c in RAW_COLUMNS if c != "time_raw"]
    rank = F.row_number().over(Window.partitionBy("weather_ts").orderBy(*tie_break))
    ranked = parsed.withColumn("_rank", rank)
    out_of_range = (F.col("temperature_c") < TEMPERATURE_MIN_C) | (
        F.col("temperature_c") > TEMPERATURE_MAX_C
    )
    stats = ranked.agg(
        F.count(F.lit(1)).alias("rows"),
        F.sum(F.when(F.col("_rank") > 1, 1).otherwise(0)).alias("duplicates"),
        F.sum(F.when((F.col("_rank") == 1) & out_of_range, 1).otherwise(0)).alias("out_of_range"),
    ).first()
    frame = ranked.where(F.col("_rank") == 1).select(*SILVER_COLUMNS)
    return WeatherSilver(
        frame=frame,
        row_count=int(stats["rows"] or 0) - int(stats["duplicates"] or 0),
        duplicate_count=int(stats["duplicates"] or 0),
        out_of_range_count=int(stats["out_of_range"] or 0),
    )


# ----------------------------------------------------------------------------- daily
def daily_temperature(silver_weather_df: DataFrame) -> DataFrame:
    """Hour count and mean temperature per UTC date (D-25, F-22).

    ``weather_date`` uses epoch arithmetic, so it is the UTC date whatever the session time zone.
    The mean folds the sorted temperatures, which fixes the summation order.
    """
    weather_date = F.expr(
        "date_from_unix_date(CAST(floor(unix_seconds(weather_ts) / 86400) AS INT))"
    )
    return (
        silver_weather_df.withColumn("weather_date", weather_date)
        .groupBy("weather_date")
        .agg(
            F.expr(
                "aggregate(array_sort(collect_list(temperature_c)), CAST(0 AS DOUBLE), "
                "(acc, x) -> acc + x) / count(*)"
            ).alias("mean_temperature_c_1d"),
            F.count(F.lit(1)).cast("int").alias("temperature_hour_count_1d"),
        )
        .select(*DAILY_TEMPERATURE_COLUMNS)
    )
