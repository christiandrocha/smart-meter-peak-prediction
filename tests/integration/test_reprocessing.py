"""Two-step snapshot tests for AC-09, AC-24 and AC-27 (and AC-12 after a full refresh).

Each pair stores a snapshot in ``out/evidence/`` in the ``*_before`` test and compares it in the
``*_after`` test. Do the real operation between the two (runbook, "Evidence order"):

- AC-24: ``before`` after a files-only build (no Kafka row in Silver); ``after`` once Kafka loaded.
- AC-09: ``before`` after the first full load; replay the stream again, run the job; ``after``.
- AC-27: ``before``; full refresh of the pipeline (Aiven may be off); ``after``.
"""

from __future__ import annotations

import pytest

from smart_meter_peak_prediction import metrics
from smart_meter_peak_prediction.rules import DROP_RULE_PRECEDENCE

pytestmark = pytest.mark.integration

REPLAYED_ROWS_KEY = "stream_rows"
AC27_OBJECTS = (
    ("silver_meter_readings_evaluated", "table"),
    ("silver_meter_readings", "table"),
    ("silver_meter_readings_quarantine", "table"),
    ("silver_households", "table"),
    ("gold_household_daily_consumption", "table"),
    ("gold_household_data_quality_monthly", "table"),
    ("gold_household_data_quality", "view"),
)


def _contract_checksum(contracts, checksum, settings, stem: str) -> dict:
    columns = [name for name, _ in contracts.columns(stem)]
    return checksum(contracts.table(stem, settings), columns)


# ----------------------------------------------------------------------------- AC-09
def _ac09_state(sql, settings, contracts, checksum) -> dict:
    evaluated = settings.table("silver", "meter_readings_evaluated")
    totals = sql.one(metrics.rule_counts_sql(evaluated))
    return {
        "kafka_rows": sql.scalar(f"SELECT count(*) FROM {settings.bronze_kafka_readings}"),
        "qr_09": totals["qr_09"],
        # every per-rule total, which a replay must not raise (the stream holds no invalid
        # message, so the quarantine-duplicate total stays equal as well)
        "per_rule": {
            metrics.count_column(rule): totals[metrics.count_column(rule)]
            for rule in sorted(DROP_RULE_PRECEDENCE)
        },
        "quarantine_duplicates": totals["quarantine_duplicates"],
        "silver": _contract_checksum(contracts, checksum, settings, "silver_meter_readings"),
        "quarantine": _contract_checksum(
            contracts, checksum, settings, "silver_meter_readings_quarantine"
        ),
    }


def test_ac09_before_replay_snapshot(sql, settings, contracts, checksum, evidence) -> None:
    state = _ac09_state(sql, settings, contracts, checksum)
    assert state["kafka_rows"] > 0, "load the Kafka messages once before the replay test"
    evidence.save("ac09_before_replay", state)


def test_ac09_after_replay_silver_unchanged(
    sql, settings, contracts, checksum, evidence, config_manifest
) -> None:
    """After the second replay and a pipeline update: Bronze grew, Silver did not."""
    before = evidence.load("ac09_before_replay", "test_ac09_before_replay_snapshot")
    after = _ac09_state(sql, settings, contracts, checksum)
    replayed = config_manifest["counts"][REPLAYED_ROWS_KEY]  # every stream row, once more
    assert after["kafka_rows"] == before["kafka_rows"] + replayed
    assert after["silver"] == before["silver"]
    assert after["quarantine"] == before["quarantine"]
    assert after["qr_09"] == before["qr_09"] + replayed
    assert after["per_rule"] == before["per_rule"]
    assert after["quarantine_duplicates"] == before["quarantine_duplicates"]


# ----------------------------------------------------------------------------- AC-24
def _earlier_months_sql(settings, contracts, table: str) -> str:
    """Per-month row count and checksum of the months before the cutoff month."""
    columns = ", ".join(
        f"`{name}`" for name, _ in contracts.columns("gold_household_data_quality_monthly")
    )
    cutoff_month = f"DATE'{settings.cutoff_ts:%Y-%m-01}'"
    return (
        f"SELECT cast(reading_month AS STRING) AS reading_month, count(*) AS row_count, "
        f"cast(sum(cast(xxhash64({columns}) AS DECIMAL(38,0))) AS STRING) AS checksum "
        f"FROM {table} WHERE reading_month < {cutoff_month} GROUP BY reading_month "
        f"ORDER BY reading_month"
    )


def _kafka_rows_in_silver(sql, settings) -> int:
    silver = settings.table("silver", "meter_readings")
    return sql.scalar(f"SELECT count(*) FROM {silver} WHERE _ingestion_path = 'kafka'")


def test_ac24_before_kafka_snapshot(sql, settings, contracts, evidence) -> None:
    """Files-only state: Silver has no Kafka row yet."""
    assert _kafka_rows_in_silver(sql, settings) == 0, "Kafka rows are already in Silver"
    monthly = settings.table("gold", "household_data_quality_monthly")
    months = sql.rows(_earlier_months_sql(settings, contracts, monthly))
    assert months, "no earlier month in the monthly table: run the files-only build first"
    evidence.save("ac24_before_kafka", {"months": months})


def test_ac24_after_kafka_months_up_to_november_unchanged(
    sql, settings, contracts, evidence
) -> None:
    before = evidence.load("ac24_before_kafka", "test_ac24_before_kafka_snapshot")
    assert _kafka_rows_in_silver(sql, settings) > 0, "the Kafka months have not arrived"
    monthly = settings.table("gold", "household_data_quality_monthly")
    assert sql.rows(_earlier_months_sql(settings, contracts, monthly)) == before["months"]
    later = sql.scalar(
        f"SELECT sum(observed_readings) FROM {monthly} "
        f"WHERE reading_month >= DATE'{settings.cutoff_ts:%Y-%m-01}'"
    )
    assert later > 0


# ----------------------------------------------------------------------------- AC-27, AC-12
def _snapshot_all(contracts, checksum, settings) -> dict:
    return {
        stem: _contract_checksum(contracts, checksum, settings, stem) for stem, _ in AC27_OBJECTS
    }


def test_ac27_before_full_refresh_snapshot(contracts, checksum, settings, evidence) -> None:
    state = _snapshot_all(contracts, checksum, settings)
    assert all(entry["row_count"] > 0 for entry in state.values()), state
    evidence.save("ac27_before_full_refresh", {"objects": state})


def test_ac27_after_full_refresh_checksums_equal(
    workspace, pipeline, contracts, checksum, settings, evidence
) -> None:
    """A full refresh recomputes everything from Bronze and gives the same tables."""
    before = evidence.load("ac27_before_full_refresh", "test_ac27_before_full_refresh_snapshot")
    updates = workspace.pipelines.list_updates(pipeline.pipeline_id, max_results=10).updates or []
    latest = max(updates, key=lambda u: u.creation_time)
    assert latest.full_refresh, "the latest pipeline update was not a full refresh"
    assert latest.creation_time > before["saved_at_ms"], "run the full refresh after the snapshot"
    assert latest.state.value == "COMPLETED"
    assert _snapshot_all(contracts, checksum, settings) == before["objects"]


def test_ac12_totals_consistent_after_full_refresh(assert_rule_totals_consistent, evidence) -> None:
    """The AC-12 totals hold again after the full refresh (run after the AC-27 pair)."""
    evidence.load("ac27_before_full_refresh", "test_ac27_before_full_refresh_snapshot")
    assert_rule_totals_consistent()
