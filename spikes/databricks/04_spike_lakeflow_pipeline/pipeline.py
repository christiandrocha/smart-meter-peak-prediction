"""Spike 04 pipeline source. STATUS: written, NOT RUN. Throwaway code, never imported by src/.

Questions answered when run_spike.py runs this pipeline (ADR 0001):
  A-10  a triggered serverless Lakeflow pipeline runs on Free Edition;
  DA-01 expectations on a materialized view report per-rule metrics in the event log and count
        a row under every expectation it fails (one row fails both QR-03 and QR-04);
  DA-02 fully qualified names in two schemas, a private dataset, a published view (see
        summary_view.sql);
  DA-07 the session time zone is UTC inside the pipeline;
  DA-08 a package synced to the workspace is importable through sys.path;
  AC-15 `expect_or_fail` aborts the update and the downstream MVs keep their contents.

Configuration keys (set by run_spike.py): spike.catalog, spike.bronze_table, spike.src_path.
The pipeline reads a spike Bronze table with columns household_id, reading_ts_raw,
energy_kwh_raw, _source_file, _ingested_at.
"""

import sys

import dlt
from pyspark.sql import Window
from pyspark.sql import functions as F

CATALOG = spark.conf.get("spike.catalog")
BRONZE = spark.conf.get("spike.bronze_table")
sys.path.insert(0, spark.conf.get("spike.src_path"))

from spike_pkg.rules import (  # noqa: E402  (DA-08: import from the synced files)
    ENERGY_SQL,
    F02_SQL,
    F03_SQL,
    F04_SQL,
    F05_SQL,
    READING_TS_SQL,
)

SILVER = f"{CATALOG}.silver"
GOLD = f"{CATALOG}.gold"


@dlt.table(name=f"{SILVER}.spike_tz_check", comment="DA-07: session time zone inside the pipeline")
@dlt.expect_or_fail("da_07_session_time_zone_is_utc", "tz = 'UTC'")
def spike_tz_check():
    return spark.range(1).select(F.expr("current_timezone()").alias("tz"))


@dlt.table(name="spike_evaluated", private=True, comment="DA-02: private dataset; DA-01 counters")
@dlt.expect("qr_03_on_30_min_grid", "NOT array_contains(failed_rules, 'QR-03')")
@dlt.expect("qr_04_energy_numeric", "NOT array_contains(failed_rules, 'QR-04')")
@dlt.expect("qr_09_first_ingested_wins", "NOT is_duplicate")
@dlt.expect_or_fail("qr_01_household_id_shape", "household_id RLIKE '^MAC[0-9]{6}$'")
@dlt.expect_or_fail("inv_01_source_ref_unique", "source_ref_row_count = 1")
def spike_evaluated():
    df = spark.read.table(BRONZE)  # batch read: materialized view
    df = (
        df.withColumn("household_id", F.expr("trim(household_id)"))
        .withColumn("reading_ts", F.expr(READING_TS_SQL))
        .withColumn("energy_kwh", F.expr(ENERGY_SQL))
        .withColumn("f02", F.expr(F02_SQL))
        .withColumn("f03", F.expr(F03_SQL))
        .withColumn("f04", F.expr(F04_SQL))
        .withColumn("f05", F.expr(F05_SQL))
        .withColumn(
            "failed_rules",
            F.expr(
                "filter(array(IF(f02,'QR-02',NULL), IF(f03,'QR-03',NULL), IF(f04,'QR-04',NULL),"
                " IF(f05,'QR-05',NULL)), x -> x IS NOT NULL)"
            ),
        )
        .withColumn("is_candidate", F.expr("size(failed_rules) = 0"))
        .withColumn(
            "_source_ref",
            F.concat_ws("#", F.lit("files:"), F.col("_source_file"), F.col("household_id"),
                        F.col("reading_ts_raw")),
        )
    )
    rank_window = Window.partitionBy("household_id", "reading_ts", "is_candidate").orderBy(
        "_ingested_at", "_source_ref"
    )
    return (
        df.withColumn("dedup_rank", F.when(F.col("is_candidate"), F.row_number().over(rank_window)))
        .withColumn("is_silver", F.expr("is_candidate AND dedup_rank = 1"))
        .withColumn("is_duplicate", F.expr("is_candidate AND dedup_rank > 1"))
        .withColumn("rule_name", F.expr("element_at(failed_rules, 1)"))
        .withColumn("source_ref_row_count", F.count("*").over(Window.partitionBy("_source_ref")))
        .withColumn("reading_date", F.to_date("reading_ts"))
    )


@dlt.table(name=f"{SILVER}.spike_readings")
def spike_readings():
    return (
        dlt.read("spike_evaluated")
        .where("is_silver")
        .select("household_id", "reading_ts", "reading_date", "energy_kwh", "_ingested_at")
    )


@dlt.table(name=f"{SILVER}.spike_quarantine")
def spike_quarantine():
    return (
        dlt.read("spike_evaluated")
        .where("size(failed_rules) > 0")
        .select("_source_ref", "rule_name", "failed_rules", "_ingested_at")
    )


@dlt.table(name=f"{GOLD}.spike_daily")
def spike_daily():
    return (
        spark.read.table(f"{SILVER}.spike_readings")  # fully qualified read across schemas
        .groupBy("household_id", "reading_date")
        .agg(F.sum("energy_kwh").alias("total_energy_kwh"), F.count("*").alias("reading_count"))
    )
