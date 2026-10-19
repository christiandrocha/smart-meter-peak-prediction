"""Silver tables and the evaluation table on the deployed dev environment.

Covers AC-11 to AC-14, AC-18 to AC-20 and AC-34 on the seed-42 sample. Run after the first full job
run and before the AC-09 replay (runbook): the exact counts are those of a run with no replay.
"""

from __future__ import annotations

import pytest

from smart_meter_peak_prediction import metrics
from smart_meter_peak_prediction.bronze import BRONZE_TABLES

pytestmark = pytest.mark.integration

# Names that must carry a leading underscore wherever they appear (AC-19, no exceptions).
PROCESSING_NAMES = {
    "ingested_at",
    "ingestion_path",
    "source_ref",
    "source_file",
    "rescued_data",
    "topic",
    "partition",
    "offset",
    "kafka_timestamp",
    "produced_at",
}
SOURCE_NAMES = {"LCLid", "tstp", "energy(kWh/hh)"}
CONTRACT_STEMS = (
    "silver_meter_readings_evaluated",
    "silver_meter_readings",
    "silver_meter_readings_quarantine",
    "silver_households",
    "gold_household_daily_consumption",
    "gold_household_data_quality_monthly",
    "gold_household_data_quality",
)
DST_DAYS = ("2013-03-31", "2013-10-27")  # UTC dates of the clock changes in the sample period


def _expected_quarantine(manifest: dict) -> int:
    counts = manifest["counts"]
    return counts["historical_non_numeric_rows"] + counts["stream_non_numeric_rows"]


def test_ac11_reconciliation_classifies_every_bronze_row(sql, settings, config_manifest) -> None:
    result = sql.one(
        metrics.reconciliation_sql(
            settings.table("silver", "meter_readings_evaluated"),
            settings.table("silver", "meter_readings"),
            settings.table("silver", "meter_readings_quarantine"),
            settings,
        )
    )
    counts = config_manifest["counts"]
    quarantined = _expected_quarantine(config_manifest)
    assert result["bronze_rows"] == counts["total_rows"]
    assert result["in_quarantine"] == quarantined
    assert result["out_of_period"] == 0
    assert result["is_duplicate"] == 0
    assert result["in_silver"] == counts["total_rows"] - quarantined
    assert result["unclassified"] == 0
    assert result["double_classified"] == 0


def test_ac12_update_rule_counts_match_quarantine_rows(assert_rule_totals_consistent) -> None:
    """Totals over the current state after the latest update (no time window, DA-01 fallback)."""
    assert_rule_totals_consistent()


def test_ac13_silver_invariants(sql, settings) -> None:
    silver = settings.table("silver", "meter_readings")
    quarantine = settings.table("silver", "meter_readings_quarantine")
    row = sql.one(
        f"""SELECT
  (SELECT count(*) FROM (SELECT 1 FROM {silver} GROUP BY household_id, reading_ts
                         HAVING count(*) > 1)) AS duplicate_keys,
  (SELECT count_if(unix_micros(reading_ts) % 1800000000 != 0) FROM {silver}) AS off_grid,
  (SELECT count_if(energy_kwh < 0) FROM {silver}) AS negative,
  (SELECT count_if(energy_kwh IS NULL OR isnan(energy_kwh)) FROM {silver}) AS null_energy,
  (SELECT count_if(NOT (reading_ts >= {settings.study_start_sql}
                        AND reading_ts < {settings.study_end_exclusive_sql})) FROM {silver})
    AS out_of_period,
  (SELECT count(*) FROM {silver} s JOIN {quarantine} q ON s._source_ref = q._source_ref)
    AS quarantined_refs"""
    )
    assert row == dict.fromkeys(row, 0)


def test_ac14_cutoff_rows_once_with_ingestion_path(sql, settings) -> None:
    silver = settings.table("silver", "meter_readings")
    cutoff = settings.cutoff_sql
    wrong_path = sql.scalar(
        f"SELECT count_if((_ingestion_path = 'files' AND reading_ts >= {cutoff}) "
        f"OR (_ingestion_path = 'kafka' AND reading_ts < {cutoff})) FROM {silver}"
    )
    assert wrong_path == 0
    boundary = sql.one(
        f"""SELECT
  count_if(reading_ts = {cutoff} - INTERVAL 30 MINUTES AND _ingestion_path = 'files') AS last_file,
  count_if(reading_ts = {cutoff} AND _ingestion_path = 'kafka') AS first_kafka,
  count_if(reading_ts IN ({cutoff} - INTERVAL 30 MINUTES, {cutoff})) AS both_slots,
  (SELECT count(*) FROM (SELECT 1 FROM {silver}
     WHERE reading_ts IN ({cutoff} - INTERVAL 30 MINUTES, {cutoff})
     GROUP BY household_id, reading_ts HAVING count(*) > 1)) AS repeated
FROM {silver}"""
    )
    assert boundary["last_file"] > 0
    assert boundary["first_kafka"] > 0
    assert boundary["both_slots"] == boundary["last_file"] + boundary["first_kafka"]
    assert boundary["repeated"] == 0


def test_ac18_silver_households_seed42(sql, settings) -> None:
    households = settings.table("silver", "households")
    row = sql.one(f"SELECT count(*) AS n, count(DISTINCT household_id) AS ids FROM {households}")
    assert row == {"n": 60, "ids": 60}
    published = sql.one(
        metrics.published_counts_sql(
            settings.table("gold", "household_daily_consumption"), households
        )
    )
    assert published["qr_14"] == 0  # every acorn_group is valid
    assert published["qr_15"] == 0  # every tariff is valid
    groups = {
        r["acorn_group"]: r["n"]
        for r in sql.rows(f"SELECT acorn_group, count(*) AS n FROM {households} GROUP BY 1")
    }
    assert groups == {"Affluent": 20, "Comfortable": 20, "Adversity": 20}


def test_ac19_deployed_columns_match_contracts(sql, settings, contracts) -> None:
    mismatches: dict[str, object] = {}
    column_names: set[str] = set()

    def deployed(table: str) -> list[tuple[str, str]]:
        catalog, schema, name = table.split(".")
        rows = sql.rows(
            "SELECT column_name, full_data_type "
            f"FROM {catalog}.information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{name}' ORDER BY ordinal_position"
        )
        return [(r["column_name"], r["full_data_type"].lower()) for r in rows]

    for stem in CONTRACT_STEMS:
        actual = deployed(contracts.table(stem, settings))
        column_names.update(name for name, _ in actual)
        if actual != contracts.columns(stem):
            mismatches[stem] = actual
    for name, columns in BRONZE_TABLES.items():
        actual = deployed(settings.table("bronze", name))
        column_names.update(col for col, _ in actual)
        if actual != [(col, str(kind).lower()) for col, kind in columns.items()]:
            mismatches[f"bronze.{name}"] = actual
    assert not mismatches, mismatches
    assert not column_names & SOURCE_NAMES
    assert not column_names & PROCESSING_NAMES  # each of these exists only with a leading "_"


@pytest.mark.parametrize("dst_day", DST_DAYS)
def test_ac20_dst_days_have_48_readings(sql, settings, dst_day) -> None:
    silver = settings.table("silver", "meter_readings")
    row = sql.one(
        f"""WITH per_day AS (
  SELECT household_id, reading_date, count(*) AS n FROM {silver}
  WHERE reading_date BETWEEN date_sub(DATE'{dst_day}', 1) AND date_add(DATE'{dst_day}', 1)
  GROUP BY household_id, reading_date
), wide AS (
  SELECT household_id,
    max(IF(reading_date = date_sub(DATE'{dst_day}', 1), n, NULL)) AS before_n,
    max(IF(reading_date = DATE'{dst_day}', n, NULL)) AS day_n,
    max(IF(reading_date = date_add(DATE'{dst_day}', 1), n, NULL)) AS after_n
  FROM per_day GROUP BY household_id
)
SELECT count_if(before_n = 48 AND after_n = 48) AS eligible,
       count_if(before_n = 48 AND after_n = 48 AND day_n = 48) AS ok
FROM wide"""
    )
    assert row["eligible"] > 0
    assert row["ok"] == row["eligible"]


def test_ac34_seed42_offgrid_null_rows_counted_under_both_rules(
    sql, settings, config_manifest
) -> None:
    expected = _expected_quarantine(config_manifest)
    totals = sql.one(metrics.rule_counts_sql(settings.table("silver", "meter_readings_evaluated")))
    assert totals["qr_03"] == expected
    assert totals["qr_04"] == expected
    quarantine = settings.table("silver", "meter_readings_quarantine")
    row = sql.one(
        f"""SELECT count(*) AS n, count(DISTINCT _source_ref) AS refs,
  count_if(array_contains(failed_rules, 'QR-03') AND array_contains(failed_rules, 'QR-04'))
    AS both_rules,
  count_if(rule_name = 'QR-03') AS first_rule
FROM {quarantine}"""
    )
    assert row == {"n": expected, "refs": expected, "both_rules": expected, "first_rule": expected}
