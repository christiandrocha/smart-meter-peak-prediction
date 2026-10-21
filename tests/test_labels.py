"""Label library: D-19 label, D-27 / D-34 eligibility and QR-19 (AC-41, AC-43 to AC-47, AC-63)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pyspark.sql import functions as F
from support import peak_builders as pb

from smart_meter_peak_prediction import features, labels
from smart_meter_peak_prediction.peak_config import PeakParameters


def evaluate(spark, households, daily, monthly, params=None, start=pb.AC45_STUDY_START):
    return labels.evaluate_labels(
        pb.household_frame(spark, households),
        pb.daily_frame(spark, daily),
        pb.monthly_frame(spark, monthly),
        params or PeakParameters(),
        start,
    )


def by_key(df) -> dict:
    return {(r["household_id"], r["target_date"]): r.asDict() for r in df.collect()}


@pytest.fixture(scope="module")
def ac45_labels(spark):
    fixture = pb.ac45_fixture()
    return by_key(evaluate(spark, fixture.households, fixture.daily, fixture.monthly))


# ----------------------------------------------------------------------------- AC-41
def test_ac41_label_grid_is_dense_with_target_date_plus_one(spark) -> None:
    start = date(2013, 1, 1)
    households = [pb.household_row("H1"), pb.household_row("H2"), pb.household_row("H3")]
    daily = pb.daily_series("H1", start, 60) + pb.daily_series("H2", start, 45)
    monthly = pb.monthly_series("H1", date(2012, 10, 1), date(2013, 3, 1))
    h_df, d_df = pb.household_frame(spark, households), pb.daily_frame(spark, daily)
    m_df = pb.monthly_frame(spark, monthly)
    params = PeakParameters()

    table = labels.build_labels(h_df, d_df, m_df, params, start)
    feature_table = features.build_features(
        h_df, d_df, pb.silver_weather_frame(spark, pb.hourly_silver(start, 60)), params, start
    )

    label_keys = {(r[0], r[1]) for r in table.select("household_id", "target_date").collect()}
    shifted = {
        (r[0], r[1] + timedelta(days=1))
        for r in feature_table.select("household_id", "feature_date").collect()
    }
    assert label_keys == shifted
    assert table.count() == 3 * 60
    assert table.where(F.col("feature_date") != F.date_sub("target_date", 1)).count() == 0
    assert [(f.name, f.dataType.simpleString()) for f in table.schema.fields] == list(
        labels.LABEL_COLUMNS.items()
    )


# ----------------------------------------------------------------------------- AC-43
def test_ac43_hand_computed_label_cases(spark) -> None:
    fixture = pb.ac43_fixture()
    table = by_key(evaluate(spark, fixture.households, fixture.daily, [], start=pb.AC43_START))

    differing = []
    for hid, (label, baseline, count) in fixture.expected.items():
        row = table[(hid, pb.AC43_T)]
        if row["label_consumption_spike"] != label or row["baseline_day_count"] != count:
            differing.append(hid)
        elif (baseline is None) != (row["baseline_energy_kwh"] is None):
            differing.append(hid)
        elif baseline is not None and abs(row["baseline_energy_kwh"] - baseline) > 1e-9:
            differing.append(hid)
    assert differing == []
    got = [table[(hid, pb.AC43_T)]["label_consumption_spike"] for hid in fixture.expected]
    assert got == [0, 1, None, None, None, 1]


def test_ac43_exact_bound_is_not_a_spike_and_threshold_is_a_parameter(spark) -> None:
    fixture = pb.ac43_fixture()
    strict = by_key(evaluate(spark, fixture.households, fixture.daily, [], start=pb.AC43_START))
    assert strict[("C1", pb.AC43_T)]["total_energy_kwh"] == (
        pb.LABEL_THRESHOLD * strict[("C1", pb.AC43_T)]["baseline_energy_kwh"]
    )
    higher = by_key(
        evaluate(
            spark,
            fixture.households,
            fixture.daily,
            [],
            PeakParameters(label_threshold=1.5),
            pb.AC43_START,
        )
    )
    assert higher[("C2", pb.AC43_T)]["label_consumption_spike"] == 0
    assert higher[("C6", pb.AC43_T)]["label_consumption_spike"] == 1  # 19.3 > 1.5 x 11.0


# ----------------------------------------------------------------------------- AC-45
def eligibility(rows: dict, hid: str, target: date) -> dict:
    return rows[(hid, target)]


def test_ac45_eligibility_fixture_cases(ac45_labels) -> None:
    rows = ac45_labels

    # full history: T = 2012-09-30 has only two window months, T = 2012-10-01 has three
    short = eligibility(rows, "FULL", date(2012, 9, 30))
    assert short["ineligibility_reasons"] == ["insufficient_history"]
    assert short["eligibility_month_count"] == 2
    assert short["coverage_ratio_3m"] is None
    assert short["zero_share_3m"] is None
    assert not short["is_eligible"]
    full = eligibility(rows, "FULL", date(2012, 10, 1))
    assert full["is_eligible"]
    assert full["ineligibility_reasons"] == []
    assert full["eligibility_month_count"] == 3

    # late starter (first reading 2012-10-15)
    assert eligibility(rows, "LATE", date(2012, 9, 30))["ineligibility_reasons"] == [
        "insufficient_history"
    ]
    for target in (date(2012, 10, 1), date(2012, 11, 15), date(2012, 12, 31)):
        assert "low_coverage" in eligibility(rows, "LATE", target)["ineligibility_reasons"]
    ready = eligibility(rows, "LATE", date(2013, 1, 15))
    assert ready["is_eligible"]
    assert ready["coverage_ratio_3m"] == pytest.approx(78 / 92, abs=1e-12)

    # dead meter: zero share 0.95 over the window
    dead = eligibility(rows, "DEAD", date(2013, 1, 15))
    assert dead["ineligibility_reasons"] == ["high_zero_share"]
    assert dead["zero_share_3m"] == pytest.approx(0.95, abs=1e-3)

    # coverage exactly 0.80 is eligible, 0.7999 is not
    at_bound = eligibility(rows, "COV80", date(2013, 1, 15))
    assert at_bound["is_eligible"]
    assert at_bound["coverage_ratio_3m"] == 0.8
    below = eligibility(rows, "COV7999", date(2013, 1, 15))
    assert below["ineligibility_reasons"] == ["low_coverage"]

    # zero share exactly 0.90 is not eligible
    assert eligibility(rows, "ZERO90", date(2013, 1, 15))["ineligibility_reasons"] == [
        "high_zero_share"
    ]


def test_ac45_coverage_threshold_is_a_parameter(spark) -> None:
    fixture = pb.ac45_fixture()
    strict = by_key(
        evaluate(
            spark,
            fixture.households,
            fixture.daily,
            fixture.monthly,
            PeakParameters(coverage_min=0.90),
        )
    )
    assert strict[("COV80", date(2013, 1, 15))]["ineligibility_reasons"] == ["low_coverage"]
    assert strict[("LATE", date(2013, 1, 15))]["ineligibility_reasons"] == ["low_coverage"]
    assert strict[("FULL", date(2013, 1, 15))]["is_eligible"]


# ----------------------------------------------------------------------------- AC-46
def test_ac46_appending_later_months_keeps_eligibility_up_to_month_start(spark) -> None:
    fixture = pb.ac45_fixture()
    first_of_next = date(2013, 1, 1)  # M = 2012-12
    upto_m = [m for m in fixture.monthly if m["reading_month"] < first_of_next]
    later = [
        pb.monthly_row(h["household_id"], date(2013, 1, 1), observed=0, zero=0)
        for h in fixture.households
    ]
    kinds = ("is_eligible", "ineligibility_reasons", "coverage_ratio_3m", "zero_share_3m")

    base = by_key(evaluate(spark, fixture.households, fixture.daily, upto_m))
    extended = by_key(evaluate(spark, fixture.households, fixture.daily, upto_m + later))

    stable = [key for key in base if key[1] <= first_of_next]
    assert len(stable) > 60
    assert [k for k in stable if any(base[k][c] != extended[k][c] for c in kinds)] == []
    # the appended month does change a later target date, so the comparison is not vacuous
    later_key = ("FULL", date(2013, 2, 1))
    assert any(base[later_key][c] != extended[later_key][c] for c in kinds)


# ----------------------------------------------------------------------------- AC-47 and QR-19
def test_ac47_ineligible_rows_have_reasons_and_eligible_rows_none(ac45_labels) -> None:
    rows = list(ac45_labels.values())
    assert any(r["is_eligible"] for r in rows)
    assert any(not r["is_eligible"] for r in rows)
    for row in rows:
        reasons = row["ineligibility_reasons"]
        assert row["is_eligible"] == (len(reasons) == 0)
        assert set(reasons) <= set(labels.REASONS)
        assert reasons == [r for r in labels.REASONS if r in reasons]  # fixed order
        if "insufficient_history" in reasons:
            assert reasons == ["insufficient_history"]


def test_ac44_qr19_check_reports_a_violation(spark) -> None:
    fixture = pb.ac43_fixture()
    params = PeakParameters()
    households = pb.household_frame(spark, fixture.households)
    daily = pb.daily_frame(spark, fixture.daily)
    evaluated = labels.evaluate_labels(
        households, daily, pb.monthly_frame(spark, []), params, pb.AC43_START
    )
    end = features.latest_reading_date(daily)
    assert labels.check_labels(evaluated, params, households, pb.AC43_START, end) > 0

    spike_without_baseline = evaluated.withColumn(
        "label_consumption_spike",
        F.when(F.col("baseline_day_count") < 4, F.lit(1)).otherwise(
            F.col("label_consumption_spike")
        ),
    )
    with pytest.raises(labels.LabelQualityError, match="QR-19"):
        labels.check_labels(spike_without_baseline, params, households, pb.AC43_START, end)
    flipped = evaluated.withColumn("is_eligible", ~F.col("is_eligible"))
    with pytest.raises(labels.LabelQualityError, match="QR-19"):
        labels.check_labels(flipped, params, households, pb.AC43_START, end)


def test_ac63_label_parameters_are_recorded_as_table_properties() -> None:
    params = PeakParameters(label_threshold=1.5, coverage_min=0.90)
    properties = labels.label_table_properties(params)
    assert properties["smart_meter.label_threshold"] == "1.5"
    assert properties["smart_meter.coverage_min"] == "0.9"
    assert properties["smart_meter.baseline_day_count"] == "4"
    assert set(properties) == {
        f"smart_meter.{name}"
        for name in (
            "label_threshold",
            "baseline_day_count",
            "label_lookback_weeks",
            "coverage_min",
            "zero_share_max",
            "eligibility_months",
        )
    }
