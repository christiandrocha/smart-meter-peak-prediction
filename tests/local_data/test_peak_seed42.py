"""Local-data tests (marker ``local_data``): PEAK_MODEL libraries over the real seed-42 sample.

Gold is built by the METER_INGESTION harness from ``data/sample/seed42`` (Bronze simulated from the
CSV files, as in ``test_pipeline_seed42.py``). ``features.py`` and ``labels.py`` run on it, and the
raw hourly weather file runs through ``weather.py`` under UTC and Europe/London session time zones.
The oracle for the label and eligibility figures is
``spikes/local/a17_peak_labels_eligibility.py`` (ADR 0007); it is not imported here.

  pytest -m local_data tests/local_data/test_peak_seed42.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType
from support.harness import run_update

from smart_meter_peak_prediction import bronze, features, labels, weather
from smart_meter_peak_prediction.config import Settings
from smart_meter_peak_prediction.peak_config import PeakParameters

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample" / "seed42"
WEATHER_FILE = ROOT / "data" / "raw" / "weather_hourly_darksky.csv"
SETTINGS = Settings()
STUDY_START = date(2012, 7, 1)
DST_DAYS = (date(2012, 3, 25), date(2012, 10, 28), date(2013, 3, 31), date(2013, 10, 27))
SPLITS = {
    "train": (date(2012, 7, 29), date(2013, 7, 31)),
    "validation": (date(2013, 8, 1), date(2013, 11, 30)),
    "test": (date(2013, 12, 1), date(2014, 2, 27)),
}


def _files(spark: SparkSession, pattern: str, schema) -> DataFrame:
    return (
        spark.read.option("header", "true")
        .schema(
            StructType(list(schema.fields)).add("_corrupt", "string")
        )  # add() mutates; copy first
        .csv(pattern)
        .drop("_corrupt")
        .withColumn("_rescued_data", F.lit(None).cast("string"))
        .withColumn("_metadata", F.struct(F.input_file_name().alias("file_path")))
    )


def _kafka(spark: SparkSession, path: str) -> DataFrame:
    raw = spark.read.option("header", "true").csv(path)
    event = raw.select(
        F.col("LCLid").alias("household_id"),
        F.date_format(
            F.to_timestamp("tstp", "yyyy-MM-dd HH:mm:ss.SSSSSSS"), "yyyy-MM-dd'T'HH:mm:ss'Z'"
        ).alias("reading_ts"),
        F.expr("try_cast(trim(`energy(kWh/hh)`) AS DOUBLE)").alias("energy_kwh"),
        F.lit("replay").alias("source"),
        F.lit("2024-01-01T12:00:00Z").alias("produced_at"),
    )
    return event.select(
        F.col("household_id").cast("binary").alias("key"),
        F.to_json(F.struct(*event.columns)).cast("binary").alias("value"),
        F.lit("meter-readings").alias("topic"),
        F.lit(0).alias("partition"),
        F.monotonically_increasing_id().alias("offset"),
        F.current_timestamp().alias("timestamp"),
    )


def _weather_bronze(spark: SparkSession) -> DataFrame:
    assert WEATHER_FILE.is_file(), "data/raw/weather_hourly_darksky.csv is needed (Kaggle file)"
    raw = _files(spark, str(WEATHER_FILE), weather.WEATHER_SOURCE_SCHEMA)
    return weather.project_weather(raw)


@pytest.fixture(scope="module")
def update(spark):
    assert SAMPLE.is_dir(), "build data/sample/seed42 first (scripts/prepare_sample.py build)"
    spark.conf.set("spark.sql.codegen.wholeStage", "true")
    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.conf.set("spark.sql.shuffle.partitions", "8")
    files = bronze.project_files_readings(
        _files(spark, str(SAMPLE / "historical" / "*.csv"), bronze.FILES_READINGS_SOURCE_SCHEMA)
    )
    kafka = bronze.project_kafka(_kafka(spark, str(SAMPLE / "stream" / "readings_stream.csv")))
    households = bronze.project_files_households(
        _files(
            spark,
            str(SAMPLE / "dimensions" / "households_sample.csv"),
            bronze.FILES_HOUSEHOLDS_SOURCE_SCHEMA,
        )
    )
    result = run_update(spark, SETTINGS, files, kafka, households)
    yield result
    spark.conf.set("spark.sql.codegen.wholeStage", "false")
    spark.conf.set("spark.sql.adaptive.enabled", "false")
    spark.conf.set("spark.sql.shuffle.partitions", "2")


@pytest.fixture(scope="module")
def silver_weather(spark) -> weather.WeatherSilver:
    return weather.silver_weather(_weather_bronze(spark))


@pytest.fixture(scope="module")
def feature_table(update, silver_weather) -> DataFrame:
    built = features.build_features(
        update.households, update.daily, silver_weather.frame, PeakParameters(), STUDY_START
    )
    return built.cache()


@pytest.fixture(scope="module")
def label_table(update) -> DataFrame:
    built = labels.build_labels(
        update.households, update.daily, update.monthly, PeakParameters(), STUDY_START
    )
    return built.cache()


def _share(df: DataFrame) -> float:
    return 100 * df.agg(F.avg("label_consumption_spike")).first()[0]


# ----------------------------------------------------------------------------- AC-37
def test_ac37_raw_weather_file_same_in_utc_and_london(spark) -> None:
    """The raw file gives the same instants whatever the session time zone."""
    results = {}
    try:
        for zone in ("UTC", "Europe/London"):
            spark.conf.set("spark.sql.session.timeZone", zone)
            silver = weather.silver_weather(_weather_bronze(spark))
            epoch = silver.frame.select(
                F.col("weather_ts").cast("long").alias("epoch"), "temperature_c"
            )
            per_day = {
                row["d"]: row["n"]
                for row in epoch.withColumn(
                    "d", F.expr("date_from_unix_date(CAST(floor(epoch / 86400) AS INT))")
                )
                .groupBy("d")
                .agg(F.count(F.lit(1)).alias("n"))
                .collect()
            }
            bounds = epoch.agg(F.min("epoch"), F.max("epoch"), F.countDistinct("epoch")).first()
            values = sorted((r["epoch"], r["temperature_c"]) for r in epoch.collect())
            results[zone] = (silver.row_count, silver.duplicate_count, bounds, per_day, values)
    finally:
        spark.conf.set("spark.sql.session.timeZone", "UTC")
    utc, london = results["UTC"], results["Europe/London"]
    assert utc == london  # counts, bounds, per-day counts and every (instant, temperature) pair
    row_count, duplicates, bounds, per_day, values = utc
    assert row_count == 21_165
    assert duplicates == 0
    assert bounds[2] == 21_165  # unique weather_ts
    from datetime import UTC, datetime

    assert datetime.fromtimestamp(bounds[0], UTC) == datetime(2011, 11, 1, 0, 0, tzinfo=UTC)
    assert datetime.fromtimestamp(bounds[1], UTC) == datetime(2014, 3, 31, 22, 0, tzinfo=UTC)
    assert len(values) == 21_165
    for day in DST_DAYS:
        assert per_day[day] == 24, day


# ----------------------------------------------------------------------------- AC-39
def test_ac39_seed42_temperature_hour_counts(silver_weather) -> None:
    counts = {
        row["weather_date"]: row["temperature_hour_count_1d"]
        for row in weather.daily_temperature(silver_weather.frame).collect()
    }
    day = STUDY_START
    short = {date(2013, 9, 9), date(2013, 9, 10)}
    while day <= date(2014, 2, 28):
        assert counts.get(day) == (23 if day in short else 24), day
        day += timedelta(days=1)


# ----------------------------------------------------------------------------- AC-41
def test_ac41_seed42_tables_have_36480_rows(feature_table, label_table) -> None:
    for name, df, column, first, last in (
        ("features", feature_table, "feature_date", date(2012, 7, 1), date(2014, 2, 28)),
        ("labels", label_table, "target_date", date(2012, 7, 2), date(2014, 3, 1)),
    ):
        stats = df.agg(
            F.count(F.lit(1)).alias("rows"),
            F.countDistinct("household_id", column).alias("keys"),
            F.countDistinct("household_id").alias("households"),
            F.min(column).alias("first"),
            F.max(column).alias("last"),
        ).first()
        assert stats["rows"] == stats["keys"] == 60 * 608 == 36_480, name
        assert stats["households"] == 60, name
        assert (stats["first"], stats["last"]) == (first, last), name


# ----------------------------------------------------------------------------- AC-44
def test_ac44_seed42_label_counts(label_table) -> None:
    labelled = label_table.where("label_consumption_spike IS NOT NULL")
    assert labelled.count() == 33_093
    assert 14.5 <= _share(labelled) <= 14.7
    bounds = labelled.agg(F.min("target_date"), F.max("target_date")).first()
    assert (bounds[0], bounds[1]) == (date(2012, 7, 29), date(2014, 2, 27))
    # QR-19 itself ran (and would have raised) inside build_labels. The output also shows that a
    # label exists only with a total and a full baseline, and that it is 0 or 1.
    invalid = label_table.where(
        F.col("label_consumption_spike").isNotNull()
        & (
            F.col("total_energy_kwh").isNull()
            | (F.col("baseline_day_count") != PeakParameters().baseline_day_count)
            | ~F.col("label_consumption_spike").isin(0, 1)
        )
    )
    assert invalid.count() == 0
    assert (
        label_table.where(F.col("is_eligible") != (F.size("ineligibility_reasons") == 0)).count()
        == 0
    )


# ----------------------------------------------------------------------------- AC-47
def test_ac47_seed42_eligible_rows_per_split(label_table) -> None:
    eligible = label_table.where("label_consumption_spike IS NOT NULL AND is_eligible")
    expected = {"train": (16_969, 14.0), "validation": (7_170, 15.8), "test": (5_116, 13.6)}
    for split, (start, end) in SPLITS.items():
        rows = eligible.where(F.col("target_date").between(F.lit(start), F.lit(end)))
        count, share = rows.count(), _share(rows)
        n, rate = expected[split]
        assert count == n, split
        assert abs(share - rate) <= 0.1 + 1e-9, (split, share)
    assert eligible.agg(F.min("target_date")).first()[0] >= date(2012, 10, 1)
    last_ineligible = label_table.where(
        "label_consumption_spike IS NOT NULL AND NOT is_eligible"
    ).agg(F.max("target_date"))
    assert last_ineligible.first()[0] == date(2013, 10, 31)


# ----------------------------------------------------------------------------- AC-63
def test_ac63_threshold_1_5_and_coverage_0_90(update, label_table) -> None:
    """The same code with other parameters (no code change): share 7.91%, 29,100 eligible."""
    params = PeakParameters(label_threshold=1.5, coverage_min=0.90)
    changed = labels.build_labels(
        update.households, update.daily, update.monthly, params, STUDY_START
    )
    labelled = changed.where("label_consumption_spike IS NOT NULL")
    default_labelled = label_table.where("label_consumption_spike IS NOT NULL")
    share = _share(labelled)
    assert abs(share - 7.9) <= 1.0
    assert abs(share - 7.91) <= 0.01
    assert share < _share(default_labelled)
    eligible = labelled.where("is_eligible").count()
    assert eligible == 29_100
    assert eligible <= 29_255  # eligible labelled rows of the default run
    assert labels.label_table_properties(params)["smart_meter.label_threshold"] == "1.5"
    assert labels.label_table_properties(params)["smart_meter.coverage_min"] == "0.9"
