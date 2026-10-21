"""Feature library: grid density, features against an oracle, point-in-time (AC-39 to AC-42)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from statistics import median

import pytest
from support import peak_builders as pb

from smart_meter_peak_prediction import features, labels
from smart_meter_peak_prediction.peak_config import PeakParameters

START = date(2013, 1, 1)
DAYS = 100


def table_rows(df, columns=None) -> list[tuple]:
    columns = columns or df.columns
    return sorted(tuple(r[c] for c in columns) for r in df.select(*columns).collect())


def build(spark, daily_rows, households, weather_rows, params=None, start=START):
    return features.build_features(
        pb.household_frame(spark, households),
        pb.daily_frame(spark, daily_rows),
        pb.silver_weather_frame(spark, weather_rows),
        params or PeakParameters(),
        start,
    )


@pytest.fixture(scope="module")
def messy_fixture():
    """Three households over 100 days: incomplete days, missing days, a household without Gold
    rows, a Gold-only orphan, and a late starter."""
    households = [
        pb.household_row("H1", "Affluent", "Std"),
        pb.household_row("H2", "Comfortable", "ToU"),
        pb.household_row("H3", "Adversity", "Std"),  # no Gold rows at all
        pb.household_row("H4", "Adversity", "ToU"),  # starts late
    ]
    h1 = pb.daily_series(
        "H1",
        START,
        DAYS,
        lambda i: 9.0 + math.sin(i) * 3 + (i % 7),
        incomplete=[date(2013, 1, 9), date(2013, 2, 20), date(2013, 2, 27)],
        missing=[date(2013, 1, 15), date(2013, 3, 3), date(2013, 3, 4)],
    )
    h2 = pb.daily_series("H2", START, DAYS, lambda i: 4.0 + (i * 7919 % 13) / 3.0)
    h4 = pb.daily_series("H4", date(2013, 2, 10), 60, lambda i: 6.0 + (i % 5))
    orphan = pb.daily_series("ORPHAN", START, DAYS)
    weather = pb.hourly_silver(START, DAYS, skip_days=[date(2013, 1, 5), date(2013, 2, 14)])
    return households, h1 + h2 + h4 + orphan, weather


# ----------------------------------------------------------------------------- oracle
def mean_of(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def oracle(households, daily_rows, weather_rows, n: int, lookback: int, start: date) -> dict:
    """Features by the DEFINE text, written with plain dictionaries (not the library code)."""
    gold = {(r["household_id"], r["reading_date"]): r for r in daily_rows}
    end = max(r["reading_date"] for r in daily_rows)
    hours: dict[date, list[float]] = {}
    for moment, temperature in weather_rows:
        hours.setdefault(moment.astimezone(UTC).date(), []).append(temperature)
    out = {}
    for h in households:
        hid = h["household_id"]
        d = start
        while d <= end:

            def complete_total(day, hid=hid):
                row = gold.get((hid, day))
                return row["total_energy_kwh"] if row and row["is_complete_day"] else None

            row = gold.get((hid, d))
            last7 = [complete_total(d - timedelta(days=i)) for i in range(7)]
            last28 = [complete_total(d - timedelta(days=i)) for i in range(28)]
            found = [
                v
                for k in range(1, lookback + 1)
                if (v := complete_total(d - timedelta(days=7 * k - 1))) is not None
            ]
            baseline = median(found[:n]) if len(found) >= n else None
            target = d + timedelta(days=1)
            temps = hours.get(d, [])
            out[(hid, d)] = {
                "total_energy_kwh_1d": row["total_energy_kwh"] if row else None,
                "max_energy_kwh_1d": row["max_energy_kwh"] if row else None,
                "avg_energy_kwh_7d": mean_of(last7),
                "avg_energy_kwh_28d": mean_of(last28),
                "median_energy_kwh_same_weekday_8w": baseline,
                "complete_day_share_28d": sum(v is not None for v in last28) / 28,
                "target_weekday": target.isoweekday(),
                "target_month": target.month,
                "acorn_group": h["acorn_group"],
                "tariff": h["tariff"],
                "mean_temperature_c_1d": sum(sorted(temps)) / len(temps) if temps else None,
                "temperature_hour_count_1d": len(temps),
            }
            d += timedelta(days=1)
    return out


# ----------------------------------------------------------------------------- AC-39
def test_ac39_mean_temperature_matches_recomputation_and_is_order_stable(spark) -> None:
    # Temperatures whose sum depends on the order of addition in floating point.
    hours = [
        (
            datetime(2013, 1, 1, tzinfo=UTC) + timedelta(hours=i),
            math.sin(i * 0.7) * 10 / 3 + 1e-3 * (i % 5) + 0.1 * (i % 3),
        )
        for i in range(24 * 40)
    ]
    expected: dict[date, float] = {}
    for moment, temperature in hours:
        expected.setdefault(moment.date(), []).append(temperature)
    base = pb.silver_weather_frame(spark, hours)

    from smart_meter_peak_prediction import weather

    results = []
    for partitions in (1, 3, 8):
        frame = weather.daily_temperature(base.repartition(partitions))
        results.append(
            {
                r["weather_date"]: (r["mean_temperature_c_1d"], r["temperature_hour_count_1d"])
                for r in frame.collect()
            }
        )

    for day, values in expected.items():
        mean, count = results[0][day]
        assert count == 24
        assert abs(mean - sum(values) / len(values)) <= 1e-9
    assert results[0] == results[1] == results[2]  # bitwise equal for any partitioning


# ----------------------------------------------------------------------------- AC-40
@pytest.mark.parametrize(("n", "lookback"), [(4, 8), (2, 4), (3, 6)])
def test_ac40_features_match_independent_recomputation(spark, messy_fixture, n, lookback) -> None:
    households, daily_rows, weather_rows = messy_fixture
    params = PeakParameters(baseline_day_count=n, label_lookback_weeks=lookback)
    table = build(spark, daily_rows, households, weather_rows, params)
    expected = oracle(households, daily_rows, weather_rows, n, lookback, START)

    got = {(r["household_id"], r["feature_date"]): r.asDict() for r in table.collect()}
    assert got.keys() == expected.keys()
    mismatches = 0
    for key, want in expected.items():
        for column, value in want.items():
            actual = got[key][column]
            if isinstance(value, float):
                ok = actual is not None and abs(actual - value) <= 1e-9
            else:
                ok = actual == value  # includes None == None
            mismatches += not ok
    assert mismatches == 0
    # the fixture exercises the interesting cases
    assert any(v["median_energy_kwh_same_weekday_8w"] is None for v in got.values())
    assert any(v["avg_energy_kwh_28d"] is None for v in got.values())
    assert any(v["mean_temperature_c_1d"] is None for v in got.values())


def test_ac40_feature_table_columns_match_the_contract_order(spark, messy_fixture) -> None:
    households, daily_rows, weather_rows = messy_fixture
    table = build(spark, daily_rows, households, weather_rows)
    assert [(f.name, f.dataType.simpleString()) for f in table.schema.fields] == list(
        features.FEATURE_TABLE_COLUMNS.items()
    )


# ----------------------------------------------------------------------------- AC-41
def test_ac41_feature_grid_is_dense_and_density_check_fails_on_gap(spark, messy_fixture) -> None:
    households, daily_rows, weather_rows = messy_fixture
    table = build(spark, daily_rows, households, weather_rows)
    household_df = pb.household_frame(spark, households)
    end = START + timedelta(days=DAYS - 1)

    assert table.count() == 4 * DAYS  # orphan left out, household without Gold rows kept
    assert table.select("household_id", "feature_date").distinct().count() == 4 * DAYS
    assert {r[0] for r in table.select("household_id").distinct().collect()} == {
        "H1",
        "H2",
        "H3",
        "H4",
    }
    assert features.check_features(table, household_df, START, end) == 4 * DAYS

    gap = table.where("NOT (household_id = 'H2' AND feature_date = DATE'2013-02-01')")
    with pytest.raises(features.DensityError, match="G-10"):
        features.check_features(gap, household_df, START, end)
    duplicate = table.union(table.limit(1))
    with pytest.raises(features.DensityError, match="G-10"):
        features.check_features(duplicate, household_df, START, end)


def test_ac41_feature_table_not_null_columns_hold_no_null(spark, messy_fixture) -> None:
    households, daily_rows, weather_rows = messy_fixture
    table = build(spark, daily_rows, households, weather_rows)
    for column in features.NOT_NULL_COLUMNS:
        assert table.where(f"{column} IS NULL").count() == 0


# ----------------------------------------------------------------------------- AC-42
def test_ac42_changing_data_from_t_leaves_earlier_features_and_training_rows_unchanged(
    spark,
) -> None:
    target = pb.AC42_TARGET
    params = PeakParameters()

    def build_all(fixture):
        households = pb.household_frame(spark, fixture.households)
        daily = pb.daily_frame(spark, fixture.daily)
        weather = pb.silver_weather_frame(spark, fixture.weather)
        feature_table = features.build_features(households, daily, weather, params, pb.AC42_START)
        label_table = labels.build_labels(
            households, daily, pb.monthly_frame(spark, fixture.monthly), params, pb.AC42_START
        )
        rows = spark.createDataFrame(
            [("H1", target), ("H2", target)], "household_id string, target_date date"
        )
        return feature_table, label_table, features.explicit_lookup(rows, feature_table)

    before = build_all(pb.ac42_fixture())
    after = build_all(pb.ac42_fixture(altered=True))

    cutoff = f"DATE'{target:%Y-%m-%d}'"
    assert table_rows(before[0].where(f"feature_date <= {cutoff} - INTERVAL 1 DAY")) == table_rows(
        after[0].where(f"feature_date <= {cutoff} - INTERVAL 1 DAY")
    )
    assert table_rows(before[1].where(f"target_date < {cutoff}")) == table_rows(
        after[1].where(f"target_date < {cutoff}")
    )
    assert table_rows(before[2]) == table_rows(after[2])
    # the alteration is real: rows dated T or later differ
    assert table_rows(before[0].where(f"feature_date >= {cutoff}")) != table_rows(
        after[0].where(f"feature_date >= {cutoff}")
    )
    assert table_rows(before[1].where(f"target_date >= {cutoff}")) != table_rows(
        after[1].where(f"target_date >= {cutoff}")
    )


def test_ac42_explicit_lookup_returns_nulls_for_a_missing_feature_row(spark, messy_fixture) -> None:
    households, daily_rows, weather_rows = messy_fixture
    table = build(spark, daily_rows, households, weather_rows)
    rows = spark.createDataFrame(
        [("H1", date(2013, 2, 1)), ("H1", date(2012, 12, 31))],
        "household_id string, target_date date",
    )
    got = {r["target_date"]: r for r in features.explicit_lookup(rows, table).collect()}
    assert got[date(2013, 2, 1)]["complete_day_share_28d"] is not None
    assert got[date(2012, 12, 31)]["complete_day_share_28d"] is None  # T - 1 precedes the grid
