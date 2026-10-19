"""Settings tests: layouts, names and time literals (AC-04, AC-16, AC-28)."""

from __future__ import annotations

from datetime import UTC, datetime

from smart_meter_peak_prediction.config import Settings, parse_utc, timestamp_sql


def test_ac28_main_layout_names_are_fully_qualified() -> None:
    s = Settings()
    assert s.bronze_files_readings == "smart_meter_dev.bronze.files_meter_readings"
    assert s.bronze_kafka_readings == "smart_meter_dev.bronze.kafka_meter_readings"
    assert s.table("silver", "meter_readings_evaluated") == (
        "smart_meter_dev.silver.meter_readings_evaluated"
    )
    assert s.landing_readings_path == (
        "/Volumes/smart_meter_dev/bronze/landing/readings/historical"
    )
    assert s.checkpoint("kafka_meter_readings") == (
        "/Volumes/smart_meter_dev/bronze/checkpoints/kafka_meter_readings"
    )


def test_ac28_fallback_layout_uses_workspace_catalog_and_layer_suffix() -> None:
    s = Settings.fallback_layout()
    assert s.table("gold", "household_daily_consumption") == (
        "workspace.smart_meter_dev_gold.household_daily_consumption"
    )
    assert s.volume_path("landing", "households") == (
        "/Volumes/workspace/smart_meter_dev_bronze/landing/households"
    )


def test_ac04_pipeline_configuration_round_trips_and_overrides_defaults() -> None:
    s = Settings(cutoff="2013-11-01T00:00:00Z", catalog="workspace")
    config = s.to_pipeline_configuration()
    assert config["smart_meter.cutoff"] == "2013-11-01T00:00:00Z"
    assert Settings.from_pipeline_configuration(config) == s
    # unknown keys and empty values are ignored, defaults fill the rest
    partial = Settings.from_pipeline_configuration(
        {"smart_meter.catalog": "x", "smart_meter.cutoff": "", "spark.sql.session.timeZone": "UTC"}
    )
    assert partial.catalog == "x"
    assert partial.cutoff == Settings().cutoff


def test_ac16_study_period_literals_are_utc_and_end_is_exclusive() -> None:
    s = Settings()
    assert s.study_start_ts == datetime(2012, 7, 1, tzinfo=UTC)
    assert s.study_end_exclusive_ts == datetime(2014, 3, 1, tzinfo=UTC)
    assert s.cutoff_ts == datetime(2013, 12, 1, tzinfo=UTC)
    assert s.cutoff_sql == "CAST('2013-12-01 00:00:00+00:00' AS TIMESTAMP)"


def test_ac16_parse_utc_normalises_offsets_and_naive_values() -> None:
    assert parse_utc("2013-12-01T01:00:00+01:00") == datetime(2013, 12, 1, tzinfo=UTC)
    assert parse_utc("2013-12-01 00:00:00") == datetime(2013, 12, 1, tzinfo=UTC)
    assert timestamp_sql(parse_utc("2014-02-28")).startswith("CAST('2014-02-28 00:00:00+00:00'")


def test_ac04_unknown_prefixed_configuration_key_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="smart_meter.cuttoff"):
        Settings.from_pipeline_configuration({"smart_meter.cuttoff": "2013-11-01T00:00:00Z"})
