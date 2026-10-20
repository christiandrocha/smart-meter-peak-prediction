"""Silver rules, quarantine, scope, cutoff, reconciliation and counts.

AC-11 to AC-16 and AC-34, over the local pipeline harness (same rule catalog and functions as
the pipeline). Counts are table totals from ``metrics.py`` over the evaluation output.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from support import builders as b
from support.builders import mixed_fixture
from support.harness import ExpectationFailed, rows, run_update, totals

from smart_meter_peak_prediction import metrics
from smart_meter_peak_prediction.config import Settings

SETTINGS = Settings()
T = datetime(2013, 1, 1, tzinfo=UTC)
K = datetime(2013, 12, 1, tzinfo=UTC)


def update(spark, files=(), kafka=(), households=None, settings=SETTINGS):
    hh = b.bronze_households(spark, households) if households is not None else None
    return run_update(
        spark, settings, b.bronze_files(spark, files), b.bronze_kafka(spark, kafka), hh
    )


def test_ac11_every_bronze_row_classified_exactly_once(spark) -> None:
    files, kafka = mixed_fixture()
    u = update(spark, files, kafka)
    u.register_views()
    sql = metrics.reconciliation_sql("evaluated", "silver", "quarantine", SETTINGS)
    result = spark.sql(sql).collect()[0].asDict()
    assert result["bronze_rows"] == len(files) + len(kafka)
    assert result["unclassified"] == 0
    assert result["double_classified"] == 0
    assert result["in_silver"] == 3
    assert result["in_quarantine"] == 5  # QR-03, QR-04, QR-05, QR-02 and QR-07
    assert result["is_duplicate"] == 2
    assert result["out_of_period"] == 1


def test_ac12_rule_counts_equal_quarantine_failed_rules_per_update(spark) -> None:
    """Name kept from the DESIGN. Two updates: normal and full refresh (shuffled input)."""
    files, kafka = mixed_fixture()
    first = update(spark, files, kafka)
    shuffled_files, shuffled_kafka = list(files), list(kafka)
    random.Random(7).shuffle(shuffled_files)  # noqa: S311
    random.Random(7).shuffle(shuffled_kafka)  # noqa: S311
    refreshed = update(spark, shuffled_files, shuffled_kafka)

    results = []
    for u in (first, refreshed):
        t = totals(u)
        results.append(t)
        assert t["evaluated_rows"] == len(files) + len(kafka)
        exploded = {
            r["rule"]: r["n"]
            for r in rows(
                u.quarantine.selectExpr("explode(failed_rules) AS rule")
                .groupBy("rule")
                .count()
                .withColumnRenamed("count", "n")
            )
        }
        for rule in ("QR-02", "QR-03", "QR-04", "QR-05", "QR-07"):
            assert t[metrics.count_column(rule)] == exploded.get(rule, 0), rule
        assert t["quarantine_rows"] == u.quarantine.count()
        assert t["silver_rows"] == u.silver.count()
        assert t["sf_01"] == 1
        assert t["qr_09"] == 2
    assert results[0] == results[1]


def test_ac13_silver_invariants_hold_on_mixed_fixture(spark) -> None:
    files, kafka = mixed_fixture()
    u = update(spark, files, kafka)
    silver = u.silver
    assert silver.count() == 3
    assert silver.groupBy("household_id", "reading_ts").count().where("count > 1").count() == 0
    assert silver.where("unix_micros(reading_ts) % 1800000000 != 0").count() == 0
    assert silver.where("energy_kwh < 0 OR energy_kwh IS NULL").count() == 0
    assert (
        silver.where(
            "reading_ts < TIMESTAMP'2012-07-01 00:00:00' "
            "OR reading_ts >= TIMESTAMP'2014-03-01 00:00:00'"
        ).count()
        == 0
    )
    quarantined = {r._source_ref for r in u.quarantine.select("_source_ref").collect()}
    assert not quarantined & {r._source_ref for r in silver.select("_source_ref").collect()}


def test_ac14_cutoff_boundary_rows_appear_once_with_correct_path(spark) -> None:
    files = [b.file_row("MAC000001", moment=K - timedelta(minutes=30))]
    kafka = [b.kafka_row(b.kafka_payload("MAC000001", moment=K), offset=1)]
    u = update(spark, files, kafka)
    got = {
        r["reading_ts"]: r["_ingestion_path"]
        for r in rows(u.silver.select("reading_ts", "_ingestion_path"))
    }
    assert got == {K - timedelta(minutes=30): "files", K: "kafka"}
    assert u.silver.count() == 2


@pytest.mark.parametrize(
    ("rule", "files", "kafka"),
    [
        ("QR-02", [b.file_row(reading_ts_raw="garbage")], []),
        ("QR-03", [b.file_row(moment=T + timedelta(minutes=15))], []),
        ("QR-04", [b.file_row(energy_kwh_raw="Null")], []),
        ("QR-05", [b.file_row(energy_kwh_raw="-0.5")], []),
        ("QR-07", [], [b.kafka_row("{broken", offset=9)]),
    ],
)
def test_ac15_each_drop_rule_quarantines_its_row(spark, rule, files, kafka) -> None:
    bad_ingested = datetime(2024, 3, 3, 3, 3, 3, tzinfo=UTC)
    files = [{**f, "_ingested_at": bad_ingested} for f in files]
    kafka = [{**k, "_ingested_at": bad_ingested} for k in kafka]
    good = b.file_row("MAC000003", moment=T + timedelta(hours=5))
    u = update(spark, [good, *files], kafka)
    quarantined = rows(u.quarantine)
    assert len(quarantined) == 1
    assert quarantined[0]["rule_name"] == rule
    assert quarantined[0]["failed_rules"] == [rule]
    assert quarantined[0]["_ingested_at"] == bad_ingested
    assert u.silver.count() == 1  # only the good row
    assert u.warn_counts[f"{rule.lower().replace('-', '_')}_" + _suffix(rule)] == 1


def _suffix(rule: str) -> str:
    return {
        "QR-02": "timestamp_parses",
        "QR-03": "on_30_min_grid",
        "QR-04": "energy_numeric",
        "QR-05": "energy_non_negative",
        "QR-07": "payload_parses",
    }[rule]


def test_ac15_warn_rule_qr08_keeps_row_and_counts_one(spark) -> None:
    u = update(spark, [b.file_row("MAC000001", rescued='{"extra":"x"}')])
    assert u.silver.count() == 1
    assert u.quarantine.count() == 0
    assert u.warn_counts["qr_08_no_rescued_data"] == 1


@pytest.mark.parametrize(
    ("expectation", "files", "kafka"),
    [
        ("qr_01_household_id_shape", [b.file_row(None)], []),
        ("qr_01_household_id_shape", [b.file_row("MAC12345")], []),
        ("qr_01_household_id_shape", [b.file_row("mac000002")], []),
        ("qr_01_household_id_shape", [b.file_row("MAC0000021")], []),
        (
            "qr_01_household_id_shape",
            [],
            [b.kafka_row(b.kafka_payload("MAC1234567"), offset=1)],
        ),
        (
            "qr_06_path_matches_cutoff",
            [b.file_row("MAC000001", moment=K + timedelta(days=1))],
            [],
        ),
        (
            "qr_06_path_matches_cutoff",
            [],
            [b.kafka_row(b.kafka_payload("MAC000001", moment=K - timedelta(days=1)), offset=1)],
        ),
    ],
)
def test_ac15_fail_rules_qr01_qr06_abort_update(spark, expectation, files, kafka) -> None:
    good = b.file_row("MAC000009", moment=T)
    with pytest.raises(ExpectationFailed) as failure:
        update(spark, [good, *files], kafka)
    assert failure.value.expectation == expectation  # the update returns nothing: 0 rows written


def test_ac15_trimmed_household_id_is_valid(spark) -> None:
    u = update(spark, [b.file_row(" MAC000002 ")])
    assert rows(u.silver)[0]["household_id"] == "MAC000002"


def test_ac15_well_formed_unknown_household_passes_silver(spark) -> None:
    u = update(spark, [b.file_row("MAC999999")])
    assert [r["household_id"] for r in rows(u.silver)] == ["MAC999999"]


def test_ac16_study_period_boundaries_and_scope_count(spark) -> None:
    files = [
        b.file_row("MAC000001", moment=datetime(2012, 7, 1, tzinfo=UTC)),  # first slot: in
        b.file_row("MAC000001", moment=datetime(2012, 6, 30, 23, 30, tzinfo=UTC)),  # out
    ]
    kafka = [
        b.kafka_row(
            b.kafka_payload("MAC000001", moment=datetime(2014, 2, 28, 23, 30, tzinfo=UTC)),
            offset=1,
        ),  # last slot: in
        b.kafka_row(
            b.kafka_payload("MAC000001", moment=datetime(2014, 3, 1, tzinfo=UTC)), offset=2
        ),  # out
    ]
    u = update(spark, files, kafka)
    kept = {r["reading_ts"] for r in rows(u.silver.select("reading_ts"))}
    assert kept == {datetime(2012, 7, 1, tzinfo=UTC), datetime(2014, 2, 28, 23, 30, tzinfo=UTC)}
    assert u.quarantine.count() == 0  # the outer rows are nowhere
    assert totals(u)["sf_01"] == 2


def test_ac16_study_period_follows_settings_without_code_change(spark) -> None:
    narrow = Settings(study_start="2013-01-01", study_end="2013-01-01")
    files = [
        b.file_row("MAC000001", moment=T),
        b.file_row("MAC000001", moment=T + timedelta(days=1)),
    ]
    u = update(spark, files, settings=narrow)
    assert u.silver.count() == 1
    assert totals(u)["sf_01"] == 1


def test_ac34_row_failing_qr03_and_qr04_has_one_quarantine_row_counted_twice(spark) -> None:
    base_files = [b.file_row("MAC000001", moment=T)]
    both = b.file_row("MAC000001", moment=T + timedelta(minutes=15), energy_kwh_raw="Null")
    without = update(spark, base_files)
    with_row = update(spark, [*base_files, both])
    quarantined = rows(with_row.quarantine)
    assert len(quarantined) == 1
    assert quarantined[0]["rule_name"] == "QR-03"
    assert quarantined[0]["failed_rules"] == ["QR-03", "QR-04"]
    before, after = totals(without), totals(with_row)
    assert after["qr_03"] == before["qr_03"] + 1
    assert after["qr_04"] == before["qr_04"] + 1
    assert after["quarantine_rows"] == before["quarantine_rows"] + 1


def test_ac34_timestamp_and_energy_failures_are_both_listed(spark) -> None:
    """A row whose timestamp does not parse and whose energy is Null fails QR-02 and QR-04."""
    u = update(spark, [b.file_row("MAC000001", reading_ts_raw="garbage", energy_kwh_raw="Null")])
    assert rows(u.quarantine)[0]["failed_rules"] == ["QR-02", "QR-04"]
