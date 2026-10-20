"""Gold tables, the summary view and the pipeline metadata on the deployed dev environment.

Covers AC-21, AC-22, AC-25, AC-26, AC-31 and AC-35, plus the I-18 pair (a pipeline update that
starts from an empty Gold schema). Run order (runbook): the I-18 pair brackets the very first
pipeline update; the other tests run after the first full job run.
"""

from __future__ import annotations

import pytest

from smart_meter_peak_prediction import metrics

pytestmark = pytest.mark.integration

PUBLISHED_MVS = (
    ("silver", "meter_readings_evaluated"),
    ("silver", "meter_readings"),
    ("silver", "meter_readings_quarantine"),
    ("gold", "household_daily_consumption"),
    ("gold", "household_data_quality_monthly"),
)
SUMMARY_VIEW = ("gold", "household_data_quality")
TOLERANCE = 1e-9
COVERAGE_TOLERANCE = 0.001  # AC-25 against the manifest
MAX_PRODUCE_TO_GOLD_SECONDS = 24 * 3600  # AC-31


def _table_info(workspace, settings, layer: str, name: str):
    return workspace.tables.get(full_name=settings.table(layer, name))


def test_ac21_daily_consumption_matches_silver_recomputation(sql, settings, workspace) -> None:
    silver = settings.table("silver", "meter_readings")
    daily = settings.table("gold", "household_daily_consumption")
    households = settings.table("silver", "households")
    row = sql.one(
        f"""WITH r AS (
  SELECT household_id, reading_date, sum(energy_kwh) AS total, max(energy_kwh) AS peak,
         count(*) AS n
  FROM {silver} GROUP BY household_id, reading_date
)
SELECT count(*) AS compared,
  count_if(d.household_id IS NULL OR r.household_id IS NULL) AS unmatched,
  count_if(abs(d.total_energy_kwh - r.total) > {TOLERANCE}
           OR abs(d.max_energy_kwh - r.peak) > {TOLERANCE}) AS value_mismatch,
  count_if(d.reading_count != r.n OR d.is_complete_day != (r.n = 48)) AS count_mismatch,
  count_if(NOT d.is_complete_day) AS incomplete_days
FROM {daily} d FULL OUTER JOIN r
  ON d.household_id = r.household_id AND d.reading_date = r.reading_date"""
    )
    assert row["compared"] > 0
    assert row["unmatched"] == row["value_mismatch"] == row["count_mismatch"] == 0
    share = 1 - row["incomplete_days"] / row["compared"]
    assert 0.985 <= share <= 0.995
    assert (
        sql.one(metrics.published_counts_sql(daily, households))["qr_10"]
        == (row["incomplete_days"])
    )
    assert (
        _table_info(workspace, settings, "gold", "household_daily_consumption").table_type.value
        == "MATERIALIZED_VIEW"
    )


def test_ac22_monthly_quality_matches_independent_recomputation(sql, settings) -> None:
    silver = settings.table("silver", "meter_readings")
    monthly = settings.table("gold", "household_data_quality_monthly")
    start, end = settings.study_start_date_sql, settings.study_end_date_sql
    households = sql.scalar(f"SELECT count(DISTINCT household_id) FROM {monthly}")
    months = sql.scalar(
        f"SELECT count(*) FROM (SELECT explode(sequence(trunc({start}, 'MM'), "
        f"trunc({end}, 'MM'), interval 1 month)))"
    )
    keys = sql.one(
        f"SELECT count(*) AS n, count(DISTINCT household_id, reading_month) AS distinct_keys "
        f"FROM {monthly}"
    )
    assert households == 60
    assert keys["n"] == keys["distinct_keys"] == households * months
    row = sql.one(
        f"""WITH f AS (
  SELECT household_id, reading_ts, energy_kwh,
    lag(reading_ts) OVER (PARTITION BY household_id ORDER BY reading_ts) AS prev_ts
  FROM {silver}
), a AS (
  SELECT household_id, trunc(reading_ts, 'MM') AS reading_month,
    count(*) AS observed, count_if(energy_kwh = 0) AS zeros,
    count_if((unix_seconds(reading_ts) - unix_seconds(prev_ts)) / 1800 - 1 > 0) AS gaps,
    min(reading_ts) AS first_ts, max(reading_ts) AS last_ts
  FROM f GROUP BY household_id, trunc(reading_ts, 'MM')
)
SELECT count(*) AS compared,
  count_if(m.household_id IS NULL) AS missing_in_monthly,
  count_if(m.household_id IS NOT NULL AND NOT (
    m.observed_readings = coalesce(a.observed, 0)
    AND m.zero_readings = coalesce(a.zeros, 0)
    AND m.gap_count = coalesce(a.gaps, 0)
    AND m.first_reading_ts <=> a.first_ts
    AND m.last_reading_ts <=> a.last_ts
    AND m.expected_readings = CAST(48 * (datediff(least(last_day(m.reading_month), {end}),
                                                  greatest(m.reading_month, {start})) + 1) AS INT)
  )) AS mismatching
FROM {monthly} m FULL OUTER JOIN a
  ON m.household_id = a.household_id AND m.reading_month = a.reading_month"""
    )
    assert row["compared"] >= keys["n"]
    assert row["missing_in_monthly"] == 0
    assert row["mismatching"] == 0


def test_ac25_summary_matches_monthly_and_manifest(sql, settings, sample_manifest) -> None:
    monthly = settings.table("gold", "household_data_quality_monthly")
    summary = settings.table(*SUMMARY_VIEW)
    row = sql.one(
        f"""WITH s AS (
  SELECT household_id, sum(observed_readings) AS o, sum(expected_readings) AS e,
         sum(zero_readings) AS z, sum(gap_count) AS g,
         min(first_reading_ts) AS first_ts, max(last_reading_ts) AS last_ts
  FROM {monthly} GROUP BY household_id
)
SELECT count(*) AS compared,
  count_if(v.household_id IS NULL OR s.household_id IS NULL) AS unmatched,
  count_if(v.observed_readings != s.o OR v.expected_readings != s.e
           OR v.gap_count != s.g) AS count_mismatch,
  count_if(abs(v.coverage_ratio_study_period - s.o / s.e) > {TOLERANCE}) AS coverage_mismatch,
  count_if(abs(coalesce(v.zero_share, -1) - coalesce(s.z / nullif(s.o, 0), -1)) > {TOLERANCE})
    AS zero_share_mismatch,
  count_if(abs(coalesce(v.coverage_ratio_active_span, -1) - coalesce(
      s.o / ((unix_seconds(s.last_ts) - unix_seconds(s.first_ts)) / 1800 + 1), -1)) > {TOLERANCE})
    AS span_mismatch
FROM {summary} v FULL OUTER JOIN s ON v.household_id = s.household_id"""
    )
    assert row["compared"] == sql.scalar(f"SELECT count(DISTINCT household_id) FROM {monthly}")
    assert row["unmatched"] == row["count_mismatch"] == 0
    assert row["coverage_mismatch"] == row["zero_share_mismatch"] == row["span_mismatch"] == 0
    assert sql.scalar(f"SELECT count(*) - count(DISTINCT household_id) FROM {summary}") == 0
    deployed = {
        r["household_id"]: r["coverage_ratio_study_period"]
        for r in sql.rows(f"SELECT household_id, coverage_ratio_study_period FROM {summary}")
    }
    for household, facts in sample_manifest["households"]["per_household"].items():
        gap = abs(deployed[household] - facts["coverage_study_period"])
        assert gap <= COVERAGE_TOLERANCE, household


def test_ac26_pipeline_and_table_metadata(workspace, settings, pipeline, evidence) -> None:
    """One bundle pipeline; every published MV reports it; the summary is a plain view.

    The DESIGN says "exactly one pipeline in the workspace". The Free Edition workspace also holds
    an unrelated, idle pipeline (I-10), so the test requires exactly one pipeline with the bundle
    name and records every pipeline name seen.
    """
    names = [p.name for p in workspace.pipelines.list_pipelines()]
    evidence.save("ac26_pipelines", {"pipelines": sorted(n for n in names if n)})
    spec = workspace.pipelines.get(pipeline.pipeline_id).spec
    assert spec.serverless is True
    assert not spec.continuous
    for layer, name in PUBLISHED_MVS:
        info = _table_info(workspace, settings, layer, name)
        assert info.table_type.value == "MATERIALIZED_VIEW", name
        assert info.pipeline_id == pipeline.pipeline_id, name
    assert _table_info(workspace, settings, *SUMMARY_VIEW).table_type.value == "VIEW"


def test_ac26_i18_before_first_update_gold_schema_is_empty(workspace, settings, evidence) -> None:
    """I-18: record that Gold holds no object before the first pipeline update.

    Run it after the second deploy and before the first update of the pipeline, or after dropping
    the Gold objects (runbook, "Update from an empty Gold schema").
    """
    gold = settings.qualified_schema("gold")
    catalog, schema = gold.split(".")
    objects = [t.name for t in workspace.tables.list(catalog_name=catalog, schema_name=schema)]
    assert objects == [], f"the Gold schema is not empty: {objects}"
    evidence.save("ac26_i18_before_first_update", {"gold_objects": objects})


def test_ac26_i18_after_first_update_summary_view_exists_and_update_completed(
    workspace, settings, pipeline, evidence
) -> None:
    """I-18: the Python check dataset reads the SQL-created view in the same pipeline.

    If this fails with an unresolved view, the decided fallback (2026-10-19) is to derive the check
    from the monthly table, a DESIGN change applied through ``/iterate``.
    """
    before = evidence.load(
        "ac26_i18_before_first_update", "test_ac26_i18_before_first_update_gold_schema_is_empty"
    )
    updates = workspace.pipelines.list_updates(pipeline.pipeline_id, max_results=25).updates or []
    later = [u for u in updates if u.creation_time and u.creation_time >= before["saved_at_ms"]]
    assert later, "no pipeline update after the snapshot"
    first = min(later, key=lambda u: u.creation_time)
    assert first.state.value == "COMPLETED", f"first update ended {first.state.value}"
    assert _table_info(workspace, settings, *SUMMARY_VIEW).table_type.value == "VIEW"
    daily = _table_info(workspace, settings, "gold", "household_daily_consumption")
    assert daily.table_type.value == "MATERIALIZED_VIEW"


def test_ac31_produced_reading_reaches_silver_and_gold_within_24h(sql, settings, full_runs) -> None:
    silver = settings.table("silver", "meter_readings")
    daily = settings.table("gold", "household_daily_consumption")
    monthly = settings.table("gold", "household_data_quality_monthly")
    produced = sql.one(
        f"SELECT count(*) AS n, count_if(_produced_at IS NULL) AS missing_produced_at, "
        f"unix_millis(min(_produced_at)) AS first_ms, unix_millis(max(_produced_at)) AS last_ms "
        f"FROM {silver} WHERE _ingestion_path = 'kafka'"
    )
    assert produced["n"] > 0
    assert produced["missing_produced_at"] == 0
    missing = sql.one(
        f"""SELECT
  (SELECT count(*) FROM (SELECT DISTINCT household_id, reading_date FROM {silver}
                         WHERE _ingestion_path = 'kafka') k
     LEFT ANTI JOIN {daily} d
     ON d.household_id = k.household_id AND d.reading_date = k.reading_date) AS days,
  (SELECT count(*) FROM (SELECT DISTINCT household_id, trunc(reading_ts, 'MM') AS m
                         FROM {silver} WHERE _ingestion_path = 'kafka') k
     LEFT ANTI JOIN {monthly} g
     ON g.household_id = k.household_id AND g.reading_month = k.m
        AND g.observed_readings > 0) AS months"""
    )
    assert missing == {"days": 0, "months": 0}
    # The run that delivered the readings: the earliest successful full run (all four tasks)
    # ending after the last reading was produced. Delay counts from the earliest produced reading.
    ends = [r.end_time for r in full_runs() if r.end_time and r.end_time >= produced["last_ms"]]
    assert ends, "no successful job run finished after the last reading was produced"
    delay_s = (min(ends) - produced["first_ms"]) / 1000
    assert delay_s <= MAX_PRODUCE_TO_GOLD_SECONDS, f"delay {delay_s:.0f} s"


def test_ac35_seed42_has_household_record_all_true(sql, settings) -> None:
    monthly = settings.table("gold", "household_data_quality_monthly")
    summary = settings.table(*SUMMARY_VIEW)
    households = settings.table("silver", "households")
    for table in (monthly, summary):
        row = sql.one(
            f"SELECT count_if(NOT has_household_record) AS false_rows, "
            f"count_if(has_household_record IS NULL) AS null_rows FROM {table}"
        )
        assert row == {"false_rows": 0, "null_rows": 0}, table
    only_flag = sql.scalar(
        f"SELECT count(*) FROM (SELECT household_id FROM {monthly} WHERE has_household_record "
        f"EXCEPT SELECT household_id FROM {households})"
    )
    only_join = sql.scalar(
        f"SELECT count(*) FROM (SELECT household_id FROM {households} "
        f"EXCEPT SELECT household_id FROM {monthly} WHERE has_household_record)"
    )
    assert only_flag == only_join == 0
