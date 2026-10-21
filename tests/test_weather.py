"""Weather library: Bronze projection, Silver step, QR rules, daily temperature (AC-36 to AC-39)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pyspark.sql import functions as F
from support import peak_builders as pb

from smart_meter_peak_prediction import features, weather
from smart_meter_peak_prediction.peak_config import PeakParameters

DST_DAYS = [date(2012, 3, 25), date(2012, 10, 28), date(2013, 3, 31), date(2013, 10, 27)]


@pytest.fixture
def session_time_zone(spark):
    """Restore the UTC session time zone after a test that changes it."""
    yield spark
    spark.conf.set("spark.sql.session.timeZone", "UTC")


def epoch_seconds(frame) -> list[int]:
    return sorted(r[0] for r in frame.select(F.unix_seconds("weather_ts")).collect())


def instants(frame) -> list[datetime]:
    return sorted(r[0].replace(tzinfo=UTC) for r in frame.select("weather_ts").collect())


# ----------------------------------------------------------------------------- AC-36
def test_ac36_bronze_projection_keeps_raw_columns_and_metadata(spark) -> None:
    source = spark.createDataFrame(
        [
            (
                "10.0",
                "200",
                "9.46",
                "2011-11-01 00:00:00",
                "5.0",
                "1011.0",
                "9.5",
                "3.1",
                "rain",
                "clear-night",
                "0.81",
                "Clear",
                None,
            )
        ],
        schema=", ".join(f"`{n}` string" for n in (*weather.SOURCE_COLUMNS, "_rescued_data")),
    ).withColumn(
        "_metadata", F.struct(F.lit("/Volumes/c/b/landing/weather/w.csv").alias("file_path"))
    )

    projected = weather.project_weather(source)

    assert [(f.name, f.dataType.simpleString()) for f in projected.schema.fields] == list(
        weather.BRONZE_COLUMNS.items()
    )
    row = projected.first().asDict()
    assert row["time_raw"] == "2011-11-01 00:00:00"
    assert row["temperature_raw"] == "9.46"
    assert row["wind_bearing_raw"] == "200"
    assert row["visibility_raw"] == "10.0"
    assert row["apparent_temperature_raw"] == "9.5"
    assert row["dew_point_raw"] == "5.0"
    assert row["summary_raw"] == "Clear"
    assert row["_source_file"] == "/Volumes/c/b/landing/weather/w.csv"
    assert row["_ingested_at"] is not None
    assert row["_rescued_data"] is None


def test_ac36_raw_names_cover_every_source_column_once() -> None:
    assert set(weather.RAW_NAMES) == set(weather.SOURCE_COLUMNS)
    assert len(set(weather.RAW_NAMES.values())) == 12
    assert [c.name for c in weather.WEATHER_SOURCE_SCHEMA] == list(weather.SOURCE_COLUMNS)


# ----------------------------------------------------------------------------- AC-37
def test_ac37_weather_ts_is_independent_of_session_time_zone(spark, session_time_zone) -> None:
    rows = []
    for d in DST_DAYS:
        rows += pb.hourly_weather_rows(d, 1)

    def run(zone: str):
        spark.conf.set("spark.sql.session.timeZone", zone)
        result = weather.silver_weather(pb.weather_bronze_frame(spark, rows))
        daily = weather.daily_temperature(result.frame)
        counts = {r["weather_date"]: r["temperature_hour_count_1d"] for r in daily.collect()}
        return epoch_seconds(result.frame), counts, result.row_count

    in_utc = run("UTC")
    in_london = run("Europe/London")

    assert in_utc == in_london
    assert in_utc[2] == 24 * len(DST_DAYS)
    assert in_utc[1] == dict.fromkeys(DST_DAYS, 24)
    first = datetime(2012, 3, 25, tzinfo=UTC)
    assert in_utc[0][0] == int(first.timestamp())


# ----------------------------------------------------------------------------- AC-38
def test_ac38_unparseable_time_fails_before_write(spark) -> None:
    rows = pb.hourly_weather_rows(date(2013, 1, 1), 1) + [
        pb.weather_bronze_row("2013-13-01 00:00:00")
    ]
    written: list = []

    def step(bronze, write) -> None:
        write(weather.silver_weather(bronze).frame)

    with pytest.raises(weather.WeatherQualityError, match=r"QR-16.*2013-13-01 00:00:00"):
        step(pb.weather_bronze_frame(spark, rows), written.append)
    assert written == []


def test_ac38_null_time_fails_before_write(spark) -> None:
    bronze = pb.weather_bronze_frame(spark, [pb.weather_bronze_row(None)])
    with pytest.raises(weather.WeatherQualityError, match="QR-16"):
        weather.silver_weather(bronze)


def test_ac38_non_numeric_temperature_fails_before_write(spark) -> None:
    for bad in ("warm", "", None, "NaN"):
        bronze = pb.weather_bronze_frame(spark, [pb.weather_bronze_row("2013-01-01 00:00:00", bad)])
        with pytest.raises(weather.WeatherQualityError, match="QR-18"):
            weather.silver_weather(bronze)


def test_ac38_duplicate_time_keeps_earlier_ingested_and_counts_one(spark) -> None:
    earlier = datetime(2024, 1, 1, tzinfo=UTC)
    later = earlier + timedelta(days=1)
    rows = [
        pb.weather_bronze_row("2013-01-01 00:00:00", "9.0", ingested_at=later, source_file="/b"),
        pb.weather_bronze_row("2013-01-01 00:00:00", "5.0", ingested_at=earlier, source_file="/a"),
        pb.weather_bronze_row("2013-01-01 01:00:00", "6.0"),
    ]
    result = weather.silver_weather(pb.weather_bronze_frame(spark, rows))

    kept = {r["weather_ts"].replace(tzinfo=UTC): r for r in result.frame.collect()}
    assert result.duplicate_count == 1
    assert result.row_count == 2
    assert kept[datetime(2013, 1, 1, tzinfo=UTC)]["temperature_c"] == 5.0
    assert kept[datetime(2013, 1, 1, tzinfo=UTC)]["_ingested_at"].replace(tzinfo=UTC) == earlier

    # a tie on time, ingestion time and file resolves the same way for any input order
    tie = [
        pb.weather_bronze_row("2013-01-01 00:00:00", "11.5"),
        pb.weather_bronze_row("2013-01-01 00:00:00", "10.5"),
    ]
    winners = set()
    for ordered in (tie, tie[::-1]):
        silver = weather.silver_weather(pb.weather_bronze_frame(spark, ordered))
        winners.add(silver.frame.first()["temperature_c"])
        assert silver.duplicate_count == 1
    assert winners == {10.5}


def test_ac38_temperature_50_is_kept_and_warn_count_is_one(spark) -> None:
    rows = [
        pb.weather_bronze_row("2013-07-01 12:00:00", "50.0"),
        pb.weather_bronze_row("2013-07-01 13:00:00", "20.0"),
        pb.weather_bronze_row("2013-01-01 00:00:00", "-30.0"),  # on the bound: not counted
        pb.weather_bronze_row("2013-01-01 01:00:00", "45.0"),  # on the bound: not counted
    ]
    result = weather.silver_weather(pb.weather_bronze_frame(spark, rows))

    assert result.out_of_range_count == 1
    assert 50.0 in [r["temperature_c"] for r in result.frame.collect()]
    assert result.row_count == 4


def test_ac38_silver_schema_has_the_contract_columns(spark) -> None:
    result = weather.silver_weather(
        pb.weather_bronze_frame(spark, [pb.weather_bronze_row("2013-01-01 00:00:00")])
    )
    assert [(f.name, f.dataType.simpleString()) for f in result.frame.schema.fields] == list(
        weather.SILVER_COLUMNS.items()
    )


# ----------------------------------------------------------------------------- AC-39
def test_ac39_day_without_weather_has_count_0_and_null_mean(spark) -> None:
    start = date(2013, 1, 1)
    skipped = date(2013, 1, 5)
    daily = pb.daily_frame(spark, pb.daily_series("H1", start, 8))
    households = pb.household_frame(spark, [pb.household_row("H1")])
    hourly = pb.silver_weather_frame(spark, pb.hourly_silver(start, 8, skip_days=[skipped]))

    table = features.build_features(households, daily, hourly, PeakParameters(), start)
    by_date = {r["feature_date"]: r for r in table.collect()}

    assert by_date[skipped]["temperature_hour_count_1d"] == 0
    assert by_date[skipped]["mean_temperature_c_1d"] is None
    assert by_date[date(2013, 1, 4)]["temperature_hour_count_1d"] == 24
    assert by_date[date(2013, 1, 4)]["mean_temperature_c_1d"] is not None
