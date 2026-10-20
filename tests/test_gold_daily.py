"""Daily consumption, QR-10 to QR-12 and DST days (AC-15, AC-20, AC-21)."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pytest
from support import builders as b
from support.harness import ExpectationFailed, build_update, check_rules, rows

from smart_meter_peak_prediction import gold, metrics, rules
from smart_meter_peak_prediction.config import Settings

T = datetime(2013, 1, 1, tzinfo=UTC)


def test_ac15_qr10_and_qr12_warn_counts(spark) -> None:
    files = (
        b.day_rows("MAC000001", T, count=48)  # complete day
        + b.day_rows("MAC000001", T + timedelta(days=1), count=30)  # the incomplete day
        + b.day_rows("MAC999999", T, count=48)  # well formed but unknown household
    )
    update = build_update(spark, files, [], [b.household_row("MAC000001")])
    assert update.warn_counts["qr_10_complete_day"] == 1
    assert update.warn_counts["qr_12_known_household"] == 1
    # the same totals from the published tables through metrics.py
    update.register_views()
    counts = spark.sql(metrics.published_counts_sql("daily", "households")).collect()[0]
    assert (counts.qr_10, counts.qr_12) == (1, 1)
    # incomplete days and orphans are kept
    assert update.daily.count() == 3
    assert {r["household_id"] for r in rows(update.orphan.where("NOT is_known_household"))} == {
        "MAC999999"
    }


def test_ac15_qr11_fails_on_49_readings_for_one_day(spark) -> None:
    day = datetime(2013, 1, 1).date()
    silver = spark.createDataFrame(
        [("MAC000001", T + timedelta(minutes=i), day, 0.1) for i in range(49)],
        schema="household_id string, reading_ts timestamp, reading_date date, energy_kwh double",
    )
    daily = gold.daily_consumption(silver)
    with pytest.raises(ExpectationFailed) as failure:
        check_rules(daily, rules.DAILY, Settings())
    assert failure.value.expectation == "qr_11_at_most_48_readings"
    assert failure.value.failed_rows == 1


@pytest.mark.parametrize(
    "day", [datetime(2013, 3, 31, tzinfo=UTC), datetime(2013, 10, 27, tzinfo=UTC)]
)
def test_ac20_dst_change_days_have_48_utc_readings(spark, day) -> None:
    files = []
    for offset in (-1, 0, 1):  # the neighbouring days and the change day itself
        files += b.day_rows("MAC000001", day + timedelta(days=offset), count=48)
    update = build_update(spark, files, [])
    per_day = {r["reading_date"]: r["reading_count"] for r in rows(update.daily)}
    assert len(per_day) == 3
    assert set(per_day.values()) == {48}
    assert all(r["is_complete_day"] for r in rows(update.daily))
    # no local-time shift: the UTC slot at 01:00 exists exactly once on the change day
    slots = update.silver.where(f"reading_date = DATE'{day:%Y-%m-%d}'")
    assert (
        slots.where(f"reading_ts = CAST('{day:%Y-%m-%d} 01:00:00+00:00' AS TIMESTAMP)").count() == 1
    )


def test_ac21_daily_aggregates_match_recomputation(spark) -> None:
    energies = {
        ("MAC000001", 0): [0.1 * (i % 7) + 0.013 * i for i in range(48)],
        ("MAC000001", 1): [0.5 + 0.001 * i for i in range(20)],
        ("MAC000002", 0): [0.0] * 48,
        ("MAC000002", 2): [2.25],
    }
    files = []
    for (household, day), values in energies.items():
        for slot, value in enumerate(values):
            files.append(
                b.file_row(
                    household,
                    moment=T + timedelta(days=day, minutes=30 * slot),
                    energy_kwh_raw=f" {value!r} ",
                )
            )
    update = build_update(spark, files, [])
    got = {(r["household_id"], r["reading_date"]): r for r in rows(update.daily)}
    assert len(got) == len(energies)
    for (household, day), values in energies.items():
        row = got[(household, (T + timedelta(days=day)).date())]
        assert math.isclose(row["total_energy_kwh"], math.fsum(values), abs_tol=1e-9)
        assert math.isclose(row["max_energy_kwh"], max(values), abs_tol=1e-9)
        assert row["reading_count"] == len(values)
        assert row["is_complete_day"] is (len(values) == 48)
    assert update.daily.schema["reading_count"].dataType.simpleString() == "int"


def test_ac21_daily_is_grouped_by_household_and_utc_day_only(spark) -> None:
    files = defaultdict(list)
    for household in ("MAC000001", "MAC000002"):
        files[household] = b.day_rows(household, T, count=5)
    update = build_update(spark, files["MAC000001"] + files["MAC000002"], [])
    assert update.daily.count() == 2
    assert update.daily.columns == gold.DAILY_COLUMNS
