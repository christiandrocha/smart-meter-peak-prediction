"""Household projection and rules QR-13 to QR-15 (AC-15, AC-18)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from support import builders as b
from support.harness import ExpectationFailed, build_update, rows

from smart_meter_peak_prediction import bronze, metrics, silver
from smart_meter_peak_prediction.config import Settings

INGESTED = datetime(2024, 2, 2, 2, 2, 2, tzinfo=UTC)


def test_ac18_households_are_typed_and_renamed(spark) -> None:
    source = spark.createDataFrame(
        [("MAC000002 ", " Std", "ACORN-E ", "Affluent", " block_11", None, ("/v/h.csv",))],
        schema="LCLid string, stdorToU string, Acorn string, Acorn_grouped string, file string, "
        "_rescued_data string, _metadata struct<file_path:string>",
    )
    bronze_rows = bronze.project_files_households(source)
    out = silver.households(silver.households_checked(bronze_rows))
    assert out.columns == [
        "household_id",
        "tariff",
        "acorn_category",
        "acorn_group",
        "source_block",
        "_ingested_at",
    ]
    assert {f.name: f.dataType.simpleString() for f in out.schema.fields}["_ingested_at"] == (
        "timestamp"
    )
    row = rows(out)[0]
    assert row["household_id"] == "MAC000002"  # trimmed
    assert (row["tariff"], row["acorn_category"], row["source_block"]) == (
        "Std",
        "ACORN-E",
        "block_11",
    )
    assert row["_ingested_at"] is not None
    # `_ingested_at` is copied from Bronze, not recomputed
    fixed = b.bronze_households(spark, [b.household_row("MAC000009", ingested_at=INGESTED)])
    copied = rows(silver.households(silver.households_checked(fixed)))[0]
    assert copied["_ingested_at"] == INGESTED


def test_ac15_household_rules_qr13_fail_qr14_qr15_warn(spark) -> None:
    good = [
        b.household_row("MAC000001"),
        b.household_row("MAC000002", "ToU", "ACORN-A", "Comfortable"),
    ]
    invalid = [
        b.household_row("MAC000003", "Std", "ACORN-Q", "Unknown"),  # QR-14
        b.household_row("MAC000004", "Flat", "ACORN-J", "Adversity"),  # QR-15
    ]
    update = build_update(spark, [], [], good + invalid)
    assert update.households.count() == 4  # invalid values are kept and counted
    assert update.warn_counts["qr_14_acorn_group_valid"] == 1
    assert update.warn_counts["qr_15_tariff_valid"] == 1

    # the published-table counts of metrics.py agree (daily table is empty here)
    update.register_views()
    sql = metrics.published_counts_sql("daily", "households")
    counts = spark.sql(sql).collect()[0].asDict()
    assert (counts["qr_14"], counts["qr_15"]) == (1, 1)


@pytest.mark.parametrize(
    "rows_",
    [
        [b.household_row("MAC000001"), b.household_row("MAC000001", ingested_at=INGESTED)],
        [b.household_row(None)],
    ],
    ids=["duplicate-id", "null-id"],
)
def test_ac15_qr13_fails_on_duplicate_or_null_household_id(spark, rows_) -> None:
    with pytest.raises(ExpectationFailed) as failure:
        build_update(spark, [], [], rows_)
    assert failure.value.expectation == "qr_13_household_key_unique"


def test_ac15_qr13_compares_trimmed_ids(spark) -> None:
    with pytest.raises(ExpectationFailed):
        build_update(spark, [], [], [b.household_row("MAC000001"), b.household_row(" MAC000001")])


def test_ac18_settings_do_not_change_household_columns() -> None:
    assert silver.HOUSEHOLD_COLUMNS == [
        "household_id",
        "tariff",
        "acorn_category",
        "acorn_group",
        "source_block",
        "_ingested_at",
    ]
    assert Settings().table("silver", "households") == "smart_meter_dev.silver.households"
