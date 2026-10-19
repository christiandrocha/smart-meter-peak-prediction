"""Monthly data quality facts, gaps, point in time, dense rows and the summary view SQL.

AC-22 to AC-25, AC-33 and AC-35.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pandas as pd
from support import builders as b
from support.harness import build_update, rows

from smart_meter_peak_prediction import gold
from smart_meter_peak_prediction.config import Settings

DEFAULT = Settings()
JAN = Settings(study_start="2013-01-01", study_end="2013-03-31")
T = datetime(2013, 1, 1, tzinfo=UTC)


def at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def readings(household: str, moments: list[datetime], energy: str = " 0.5 ") -> list[dict]:
    return [b.file_row(household, moment=m, energy_kwh_raw=energy) for m in moments]


def month_rows(update, household: str) -> dict:
    return {
        r["reading_month"]: r for r in rows(update.monthly.where(f"household_id = '{household}'"))
    }


# ----------------------------------------------------------------------------- AC-22
def test_ac22_expected_readings_per_month(spark) -> None:
    months = {
        r["reading_month"]: r["expected_readings"] for r in rows(gold.study_months(spark, DEFAULT))
    }
    assert len(months) == 20  # July 2012 to February 2014
    assert months[datetime(2012, 7, 1).date()] == 1488
    assert months[datetime(2013, 6, 1).date()] == 1440
    assert months[datetime(2014, 2, 1).date()] == 1344  # 28 days
    assert sum(months.values()) == 29184


def test_ac22_partial_months_follow_the_study_period(spark) -> None:
    partial = Settings(study_start="2013-01-15", study_end="2013-02-10")
    months = {
        r["reading_month"]: r["expected_readings"] for r in rows(gold.study_months(spark, partial))
    }
    assert months == {
        datetime(2013, 1, 1).date(): 48 * 17,  # 15th to 31st
        datetime(2013, 2, 1).date(): 48 * 10,
    }


def _random_readings(household: str, rng: random.Random) -> list[dict]:
    rows_: list[dict] = []
    for slot in range(0, 48 * 75):  # about 75 days from 2013-01-01
        if rng.random() < 0.25:  # 25 % of the slots are missing
            continue
        energy = "0" if rng.random() < 0.2 else f"{rng.random():.3f}"
        rows_.append(
            b.file_row(
                household, moment=T + timedelta(minutes=30 * slot), energy_kwh_raw=f" {energy} "
            )
        )
    return rows_


def test_ac22_monthly_facts_match_recomputation(spark) -> None:
    rng = random.Random(5)  # noqa: S311
    files = _random_readings("MAC000001", rng) + _random_readings("MAC000002", rng)
    update = build_update(
        spark, files, [], [b.household_row("MAC000001"), b.household_row("MAC000002")], JAN
    )
    got = {(r["household_id"], r["reading_month"]): r for r in rows(update.monthly)}

    frame = pd.DataFrame(
        {
            "household_id": [r["household_id"] for r in files],
            "ts": [pd.Timestamp(r["reading_ts_raw"][:19], tz="UTC") for r in files],
            "energy": [float(r["energy_kwh_raw"]) for r in files],
        }
    ).sort_values(["household_id", "ts"])
    frame["missing"] = frame.groupby("household_id")["ts"].diff().dt.total_seconds() / 1800 - 1
    frame["month"] = frame["ts"].dt.strftime("%Y-%m-01")
    expected = {}
    for (household, month), group in frame.groupby(["household_id", "month"]):
        expected[(household, datetime.strptime(month, "%Y-%m-%d").date())] = {
            "observed_readings": len(group),
            "zero_readings": int((group["energy"] == 0).sum()),
            "gap_count": int((group["missing"] > 0).sum()),
            "first_reading_ts": group["ts"].min().to_pydatetime(),
            "last_reading_ts": group["ts"].max().to_pydatetime(),
        }
    assert len(got) == 2 * 3  # two households x three study months, dense
    compared = 0
    for key, facts in expected.items():
        for column, value in facts.items():
            assert got[key][column] == value, (key, column)
        compared += 1
    assert compared == 2 * 3  # Jan, Feb and March all have readings in this fixture


# ----------------------------------------------------------------------------- AC-23
def test_ac23_gap_count_per_month(spark) -> None:
    january = [m for m in b.half_hours(at(2013, 1, 1, 2), 48 * 31) if m <= at(2013, 1, 31, 23)]
    skipped = {at(2013, 1, 1, 3), at(2013, 1, 1, 4, 30), at(2013, 1, 1, 5), at(2013, 1, 1, 5, 30)}
    moments = [m for m in january if m not in skipped]
    # boundary-spanning gap: 23:30, 00:00 and 00:30 are missing; the reading that ends it
    # (01:00) is in February
    moments += [at(2013, 2, 1, 1), at(2013, 2, 1, 1, 30)]
    update = build_update(spark, readings("MAC000001", moments), [], None, JAN)
    months = month_rows(update, "MAC000001")
    assert months[datetime(2013, 1, 1).date()]["gap_count"] == 2  # 1-slot and 3-slot gaps
    assert months[datetime(2013, 2, 1).date()]["gap_count"] == 1  # counted where it ends
    assert months[datetime(2013, 3, 1).date()]["gap_count"] == 0  # trailing slots are not a gap
    assert months[datetime(2013, 1, 1).date()]["first_reading_ts"] == at(2013, 1, 1, 2)
    # leading slots (00:00 to 01:30 on 1 January) are not a gap either
    assert months[datetime(2013, 1, 1).date()]["observed_readings"] == len(january) - 4


# ----------------------------------------------------------------------------- AC-24
def test_ac24_appending_later_months_keeps_earlier_rows(spark) -> None:
    january = readings("MAC000001", [at(2013, 1, 1), at(2013, 1, 1, 0, 30), at(2013, 1, 5, 12)])
    january += readings("MAC000002", [at(2013, 1, 2), at(2013, 1, 31, 23, 30)], energy="0")
    later = readings("MAC000001", [at(2013, 2, 3), at(2013, 2, 3, 0, 30), at(2013, 3, 9)])
    later += readings("MAC000002", [at(2013, 2, 1)])
    households = [b.household_row("MAC000001"), b.household_row("MAC000002")]
    before = build_update(spark, january, [], households, JAN)
    after = build_update(spark, january + later, [], households, JAN)

    def state(update, month_limit):
        return sorted(
            (
                tuple(r[c] for c in gold.MONTHLY_COLUMNS)
                for r in rows(update.monthly)
                if r["reading_month"] <= month_limit
            ),
            key=lambda t: (t[0], t[2]),
        )

    limit = datetime(2013, 1, 1).date()
    assert state(before, limit) == state(after, limit)
    assert state(before, limit)  # not vacuous
    # the appended months do change their own rows
    assert state(before, datetime(2013, 3, 1).date()) != state(after, datetime(2013, 3, 1).date())


# ----------------------------------------------------------------------------- AC-33
def test_ac33_month_without_readings_has_dense_row(spark) -> None:
    update = build_update(
        spark,
        readings("MAC000001", [at(2013, 1, 1), at(2013, 1, 1, 0, 30)]),
        [],
        [b.household_row("MAC000001")],
        JAN,
    )
    months = month_rows(update, "MAC000001")
    assert len(months) == 3
    feb = months[datetime(2013, 2, 1).date()]
    assert feb["observed_readings"] == 0
    assert feb["zero_readings"] == 0
    assert feb["gap_count"] == 0
    assert feb["first_reading_ts"] is None
    assert feb["last_reading_ts"] is None
    assert feb["expected_readings"] - feb["observed_readings"] == 48 * 28  # all slots missing


def test_ac33_household_without_readings_and_orphan_are_dense(spark) -> None:
    households = [b.household_row("MAC000001"), b.household_row("MAC000002")]
    files = readings("MAC000002", [at(2013, 1, 1)]) + readings("MAC000003", [at(2013, 2, 1)])
    update = build_update(spark, files, [], households, DEFAULT)
    monthly = rows(update.monthly)
    assert len(monthly) == 3 * 20  # (union of households) x study months, no missing pair
    pairs = {(r["household_id"], r["reading_month"]) for r in monthly}
    assert len(pairs) == len(monthly)
    for household in ("MAC000001", "MAC000002", "MAC000003"):
        assert len(month_rows(update, household)) == 20
    silent = month_rows(update, "MAC000001")  # in silver.households, no reading at all
    assert {r["observed_readings"] for r in silent.values()} == {0}
    assert {r["has_household_record"] for r in silent.values()} == {True}


# ----------------------------------------------------------------------------- AC-25
def _summary_fixture(spark):
    zero_moments = b.half_hours(at(2013, 1, 1), 10)
    mixed_moments = [at(2013, 1, 1), at(2013, 1, 1, 1), at(2013, 1, 1, 2), at(2013, 2, 1)]
    files = readings("MAC000001", zero_moments, energy="0")
    files += [
        b.file_row("MAC000002", moment=m, energy_kwh_raw=e)
        for m, e in zip(mixed_moments, ["0", "1.5", "0.25", "2"], strict=True)
    ]
    households = [b.household_row(f"MAC00000{i}") for i in (1, 2, 3)]  # MAC000003 has no reading
    return build_update(spark, files, [], households, DEFAULT)


def test_ac25_summary_ratios_and_zero_share(spark) -> None:
    update = _summary_fixture(spark)
    summary = {r["household_id"]: r for r in rows(update.summary())}
    assert set(summary) == {"MAC000001", "MAC000002", "MAC000003"}
    expected_total = 29184
    # the household with only zero readings
    zero = summary["MAC000001"]
    assert zero["zero_share"] == 1.0
    assert zero["observed_readings"] == 10
    assert math.isclose(zero["coverage_ratio_study_period"], 10 / expected_total, abs_tol=1e-9)
    assert math.isclose(zero["coverage_ratio_active_span"], 1.0, abs_tol=1e-9)  # 10 of 10 slots
    # the mixed household: 4 readings, one of them zero
    mixed = summary["MAC000002"]
    assert mixed["observed_readings"] == 4
    assert math.isclose(mixed["zero_share"], 1 / 4, abs_tol=1e-9)
    span_slots = (at(2013, 2, 1) - at(2013, 1, 1)).total_seconds() / 1800 + 1
    assert math.isclose(mixed["coverage_ratio_active_span"], 4 / span_slots, abs_tol=1e-9)
    assert mixed["gap_count"] == 3  # 00:00 to 01:00, 01:00 to 02:00 and 02:00 to 1 February
    # the household without readings has null shares and a zero coverage
    silent = summary["MAC000003"]
    assert silent["zero_share"] is None
    assert silent["coverage_ratio_active_span"] is None
    assert silent["coverage_ratio_study_period"] == 0.0
    assert silent["first_reading_ts"] is None
    assert silent["expected_readings"] == expected_total
    for row in summary.values():
        assert 0 <= row["coverage_ratio_study_period"] <= 1


def test_ac25_summary_has_no_threshold_flag_or_label_columns(spark) -> None:
    update = _summary_fixture(spark)
    forbidden = ("threshold", "flag", "excluded", "label")
    for columns in (update.summary().columns, update.monthly.columns):
        assert not [c for c in columns if any(word in c for word in forbidden)]
    assert update.summary().columns == [
        "household_id",
        "has_household_record",
        "observed_readings",
        "expected_readings",
        "coverage_ratio_study_period",
        "coverage_ratio_active_span",
        "zero_share",
        "gap_count",
        "first_reading_ts",
        "last_reading_ts",
    ]


# ----------------------------------------------------------------------------- AC-35
def test_ac35_orphan_false_known_household_true(spark) -> None:
    files = readings("MAC000001", [at(2013, 1, 1)]) + readings("MAC999999", [at(2013, 1, 1)])
    update = build_update(spark, files, [], [b.household_row("MAC000001")], DEFAULT)
    monthly = rows(update.monthly)
    summary = rows(update.summary())
    assert len(month_rows(update, "MAC999999")) == 20  # the orphan has every study month
    assert [r["household_id"] for r in summary if r["household_id"] == "MAC999999"] == ["MAC999999"]
    for table in (monthly, summary):
        assert all(r["has_household_record"] is not None for r in table)
        by_household = {(r["household_id"], r["has_household_record"]) for r in table}
        assert by_household == {("MAC000001", True), ("MAC999999", False)}
    # filtering on the column equals a join with silver.households
    update.register_views()
    flagged = {r["household_id"] for r in rows(update.monthly.where("has_household_record"))}
    joined = {
        r["household_id"]
        for r in spark.sql(
            "SELECT DISTINCT m.household_id FROM monthly m JOIN households h "
            "ON m.household_id = h.household_id"
        ).collect()
    }
    assert flagged == joined == {"MAC000001"}
