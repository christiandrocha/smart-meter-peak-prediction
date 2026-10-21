"""Local-data tests (marker ``local_data``): the library over the real seed-42 sample.

Runs the Silver and Gold functions on local Spark over ``data/sample/seed42`` (build it with
``python scripts/prepare_sample.py build --out data/sample/seed42``), with the Bronze tables
simulated from the CSV files and a Kafka payload built like the producer does. It is not a
substitute for the integration tests on the workspace (PR 3), but it checks the figures of
AC-11, AC-34, AC-18, AC-21, AC-22, AC-25 and AC-35 against the pinned sample without Databricks.

  pytest -m local_data tests/local_data/test_pipeline_seed42.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType
from support.harness import rows, run_update, totals

from smart_meter_peak_prediction import bronze, metrics
from smart_meter_peak_prediction.config import Settings

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample" / "seed42"
SETTINGS = Settings()


def _files(spark: SparkSession, pattern: str, schema) -> DataFrame:
    return (
        spark.read.option("header", "true")
        .schema(StructType(list(schema.fields)).add("_corrupt", "string"))  # add() mutates
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
def manifest() -> dict:
    return json.loads((SAMPLE / "manifest.json").read_text(encoding="utf-8"))


def test_ac11_seed42_reconciliation_classifies_every_bronze_row(update, manifest) -> None:
    total = manifest["counts"]["total_rows"]
    t = totals(update)
    assert t["evaluated_rows"] == total == 1_679_974
    assert t["quarantine_rows"] == manifest["counts"]["historical_non_numeric_rows"] == 60
    assert t["silver_rows"] == 1_679_914
    assert t["sf_01"] == 0
    assert t["qr_09"] == 0
    assert t["quarantine_duplicates"] == 0
    update.register_views()
    recon = update.spark.sql(
        metrics.reconciliation_sql("evaluated", "silver", "quarantine", SETTINGS)
    ).collect()[0]
    assert recon.unclassified == 0
    assert recon.double_classified == 0
    assert recon.bronze_rows == total
    assert recon.is_quarantine_duplicate == 0


def test_ac09_seed42_quarantine_has_distinct_dedup_keys_and_no_duplicates(update) -> None:
    """QR-09 b on the real data: 60 quarantined rows, 60 distinct keys, none repeated."""
    quarantined = update.quarantine
    assert quarantined.count() == 60
    assert quarantined.select("_dedup_key").distinct().count() == 60
    assert update.evaluated.where("is_quarantine_duplicate").count() == 0
    assert all(r["_dedup_key"].startswith("files:key:") for r in rows(quarantined))


def test_ac34_seed42_offgrid_null_rows_counted_under_both_rules(update) -> None:
    t = totals(update)
    assert t["qr_03"] == 60
    assert t["qr_04"] == 60
    quarantined = rows(update.quarantine)
    assert len(quarantined) == 60
    assert {r["rule_name"] for r in quarantined} == {"QR-03"}
    assert {tuple(r["failed_rules"]) for r in quarantined} == {("QR-03", "QR-04")}


def test_ac18_seed42_households(update) -> None:
    assert update.households.count() == 60
    assert update.households.select("household_id").distinct().count() == 60
    by_group = {
        r["acorn_group"]: r["count"] for r in rows(update.households.groupBy("acorn_group").count())
    }
    assert by_group == {"Adversity": 20, "Affluent": 20, "Comfortable": 20}
    assert update.warn_counts["qr_14_acorn_group_valid"] == 0
    assert update.warn_counts["qr_15_tariff_valid"] == 0


def test_ac21_seed42_complete_day_share_in_expected_band(update) -> None:
    total = update.daily.count()
    complete = update.daily.where("is_complete_day").count()
    assert 0.985 <= complete / total <= 0.995
    assert update.warn_counts["qr_10_complete_day"] == total - complete


def test_ac22_seed42_monthly_is_dense_with_unique_keys(update) -> None:
    assert update.monthly.count() == 60 * 20
    assert update.monthly.select("household_id", "reading_month").distinct().count() == 1200
    assert update.monthly.agg(F.sum("observed_readings")).collect()[0][0] == 1_679_914


def test_ac25_seed42_summary_coverage_matches_manifest(update, manifest) -> None:
    summary = {r["household_id"]: r for r in rows(update.summary())}
    assert len(summary) == 60
    per_household = manifest["households"]["per_household"]
    worst = 0.0
    for household, facts in per_household.items():
        gap = abs(
            summary[household]["coverage_ratio_study_period"] - facts["coverage_study_period"]
        )
        worst = max(worst, gap)
        assert gap <= 0.001, household
        assert abs((summary[household]["zero_share"] or 0.0) - facts["zero_share"]) <= 0.001
    assert worst <= 0.001  # I-04: the manifest's "observed" equals the Gold observed readings


def test_ac35_seed42_has_household_record_all_true(update) -> None:
    assert update.monthly.where("NOT has_household_record").count() == 0
    assert update.summary().where("NOT has_household_record").count() == 0
    assert update.warn_counts["qr_12_known_household"] == 0
