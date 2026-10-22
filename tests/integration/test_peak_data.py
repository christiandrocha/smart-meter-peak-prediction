"""PEAK_MODEL data tables on dev (AC-36, 37, 39, 40, 41, 44, 47, 63, 64, 66).

Run order (runbook ``docs/runbooks/peak_model.md``, "Evidence order"): after the bootstrap run of
the daily job (weather uploaded, Gold present), run the read-only tests first; then the snapshot
pairs, each pair back to back:

- AC-63: ``before`` then ``after`` (the ``after`` test starts ``build_labels`` itself with the
  stricter parameters, checks them, and restores the defaults in a ``finally`` block).
- AC-66: ``before``; optionally the user-run reset (``scripts/reset_peak_model_outputs.py``);
  ``after`` (starts the weather, feature and label tasks itself, so no daily run is needed after
  the reset; it expects inserts equal to the snapshot counts when the tables were dropped).

Keep ``smart_meter_ingestion`` idle during the whole sequence: the tests compare against Gold.

The tests never start ``refresh_silver_gold``, so they do not collide with the ingestion job
(DA-13). Independent recomputations are written here and do not call the library under test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from smart_meter_peak_prediction.model import FEATURE_COLUMNS
from smart_meter_peak_prediction.peak_config import PeakParameters

pytestmark = pytest.mark.integration

DEFAULTS = PeakParameters()
WEATHER_ROWS = 21165
DENSE_ROWS = 36480  # 60 households x 608 days (seed 42)
DST_DAYS = ("2012-03-25", "2012-10-28", "2013-03-31", "2013-10-27")  # UK clock changes in range
SHORT_DAYS = ("2013-09-09", "2013-09-10")  # 23 hourly rows in the source (AC-39)
TOLERANCE = 1e-9
FIVE_CONTRACTS = (
    "bronze_files_weather_hourly",
    "silver_weather_hourly",
    "ml_household_features_daily",
    "ml_household_labels_daily",
    "gold_consumption_spike_predictions",
)
DATA_TASKS = ["ingest_weather", "build_weather_silver", "build_features", "build_labels"]
SNAPSHOT_TABLES = (
    ("silver_weather_hourly", "silver_weather"),
    ("ml_household_features_daily", "features"),
    ("ml_household_labels_daily", "labels"),
)


def _utc_seconds(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def _utc_date_sql(column: str = "weather_ts") -> str:
    """UTC calendar date of an instant, independent of the session time zone."""
    return f"date_from_unix_date(CAST(floor(unix_seconds({column}) / 86400) AS INT))"


# ----------------------------------------------------------------------------- AC-36
def test_ac36_bronze_weather_has_21165_rows_and_rerun_adds_none(
    sql, peak_names, peak_job, peak_runner
) -> None:
    table = peak_names.bronze_weather
    total = sql.one(
        f"SELECT count(*) AS n, count_if(_source_file IS NULL) AS no_file, "
        f"count_if(_ingested_at IS NULL) AS no_ts FROM {table}"
    )
    assert total["n"] == WEATHER_ROWS, "upload the weather file and run ingest_weather (runbook)"
    assert total["no_file"] == 0
    assert total["no_ts"] == 0

    run = peak_runner.run(peak_job, only=["ingest_weather"])
    assert run.outputs["ingest_weather"]["row_count"] == WEATHER_ROWS
    assert sql.scalar(f"SELECT count(*) FROM {table}") == WEATHER_ROWS  # the rerun added 0 rows


# ----------------------------------------------------------------------------- AC-37
def test_ac37_silver_weather_range_uniqueness_and_dst_days(sql, peak_names) -> None:
    table = peak_names.silver_weather
    shape = sql.one(
        f"SELECT count(*) AS n, count(DISTINCT weather_ts) AS distinct_ts, "
        f"unix_seconds(min(weather_ts)) AS first_s, unix_seconds(max(weather_ts)) AS last_s "
        f"FROM {table}"
    )
    assert shape["n"] == WEATHER_ROWS
    assert shape["distinct_ts"] == WEATHER_ROWS
    assert shape["first_s"] == _utc_seconds("2011-11-01T00:00:00")
    assert shape["last_s"] == _utc_seconds("2014-03-31T22:00:00")
    days = ", ".join(f"DATE'{d}'" for d in DST_DAYS)
    per_day = sql.rows(
        f"SELECT d, count(*) AS n FROM (SELECT {_utc_date_sql()} AS d FROM {table}) "
        f"WHERE d IN ({days}) GROUP BY d ORDER BY d"
    )
    assert [(row["d"], row["n"]) for row in per_day] == [(d, 24) for d in DST_DAYS]


# ----------------------------------------------------------------------------- AC-39
def test_ac39_feature_temperature_matches_silver_weather(sql, peak_names) -> None:
    mismatches = sql.scalar(
        f"""
        SELECT count(*) FROM {peak_names.features} f
        LEFT JOIN (
            SELECT {_utc_date_sql()} AS d, count(*) AS n,
                   aggregate(array_sort(collect_list(temperature_c)), 0D, (a, x) -> a + x)
                       / count(*) AS m
            FROM {peak_names.silver_weather} GROUP BY 1
        ) w ON f.feature_date = w.d
        WHERE f.temperature_hour_count_1d <> coalesce(w.n, 0)
           OR (f.mean_temperature_c_1d IS NULL) <> (w.m IS NULL)
           OR abs(f.mean_temperature_c_1d - w.m) > {TOLERANCE}
        """  # noqa: S608
    )
    assert mismatches == 0
    odd = sql.rows(
        f"SELECT feature_date, temperature_hour_count_1d AS n FROM {peak_names.features} "
        "WHERE feature_date BETWEEN DATE'2012-07-01' AND DATE'2014-02-28' "
        "AND temperature_hour_count_1d <> 24 GROUP BY 1, 2 ORDER BY 1"
    )
    assert [(row["feature_date"], row["n"]) for row in odd] == [(d, 23) for d in SHORT_DAYS]


# ----------------------------------------------------------------------------- AC-40
def _feature_oracle_sql(settings, names) -> str:
    """Independent recomputation of the 12 features from Gold, households and Silver weather.

    Written from the DESIGN feature definitions with joins and date arithmetic (no window frames),
    so it does not share the implementation of ``features.py``.
    """
    n, lookback = DEFAULTS.baseline_day_count, DEFAULTS.label_lookback_weeks
    gold = settings.table("gold", "household_daily_consumption")
    households = settings.table("silver", "households")
    start = settings.study_start_date_sql
    sorted_found = f"array_sort(slice(found, 1, {n}))"
    if n % 2:
        median = f"element_at({sorted_found}, {(n + 1) // 2})"
    else:
        median = (
            f"(element_at({sorted_found}, {n // 2}) + element_at({sorted_found}, {n // 2 + 1})) / 2"
        )
    return f"""
    WITH bounds AS (SELECT max(reading_date) AS last_day FROM {gold}),
    grid AS (
        SELECT household_id, acorn_group, tariff, explode(sequence({start}, last_day)) AS d
        FROM {households} CROSS JOIN bounds
    ),
    complete_days AS (
        SELECT household_id, reading_date, total_energy_kwh AS total
        FROM {gold} WHERE is_complete_day
    ),
    roll AS (
        SELECT g.household_id, g.d,
               avg(CASE WHEN c.reading_date >= date_sub(g.d, 6) THEN c.total END) AS avg7,
               avg(c.total) AS avg28,
               CAST(count(c.reading_date) AS DOUBLE) / 28D AS share28
        FROM grid g LEFT JOIN complete_days c
          ON c.household_id = g.household_id
         AND c.reading_date BETWEEN date_sub(g.d, 27) AND g.d
        GROUP BY g.household_id, g.d
    ),
    cand AS (
        SELECT g.household_id, g.d, k.k AS k, c.total AS total
        FROM grid g CROSS JOIN (SELECT explode(sequence(1, {lookback})) AS k) k
        JOIN complete_days c
          ON c.household_id = g.household_id AND c.reading_date = date_sub(g.d, 7 * k.k - 1)
    ),
    found AS (
        SELECT household_id, d,
               transform(array_sort(collect_list(struct(k, total))), s -> s.total) AS found
        FROM cand GROUP BY household_id, d
    ),
    med AS (
        SELECT household_id, d,
               CASE WHEN size(found) < {n} THEN NULL ELSE {median} END AS median
        FROM found
    ),
    wx AS (
        SELECT {_utc_date_sql()} AS d, count(*) AS n, avg(temperature_c) AS m
        FROM {names.silver_weather} GROUP BY 1
    ),
    expected AS (
        SELECT g.household_id, g.d, g.acorn_group, g.tariff,
               gd.total_energy_kwh AS total, gd.max_energy_kwh AS maxv,
               r.avg7, r.avg28, r.share28, m.median,
               ((dayofweek(date_add(g.d, 1)) + 5) % 7) + 1 AS weekday,
               month(date_add(g.d, 1)) AS month,
               w.m AS temp, coalesce(w.n, 0) AS temp_n
        FROM grid g
        LEFT JOIN {gold} gd ON gd.household_id = g.household_id AND gd.reading_date = g.d
        LEFT JOIN roll r ON r.household_id = g.household_id AND r.d = g.d
        LEFT JOIN med m ON m.household_id = g.household_id AND m.d = g.d
        LEFT JOIN wx w ON w.d = g.d
    )
    """


def _differs(feature: str, expected: str, exact: bool) -> str:
    left, right = f"f.{feature}", f"e.{expected}"
    if exact:
        return f"NOT ({left} <=> {right})"
    return f"(({left} IS NULL) <> ({right} IS NULL) OR abs({left} - {right}) > {TOLERANCE})"


def test_ac40_every_feature_matches_sql_recomputation(sql, settings, peak_names) -> None:
    checks = {
        "total_energy_kwh_1d": ("total", True),
        "max_energy_kwh_1d": ("maxv", True),
        "avg_energy_kwh_7d": ("avg7", False),
        "avg_energy_kwh_28d": ("avg28", False),
        "complete_day_share_28d": ("share28", False),
        "median_energy_kwh_same_weekday_8w": ("median", False),
        "target_weekday": ("weekday", True),
        "target_month": ("month", True),
        "acorn_group": ("acorn_group", True),
        "tariff": ("tariff", True),
        "mean_temperature_c_1d": ("temp", False),
        "temperature_hour_count_1d": ("temp_n", True),
    }
    assert set(checks) == set(FEATURE_COLUMNS)
    counts = ", ".join(
        f"sum(CASE WHEN {_differs(feature, expected, exact)} THEN 1 ELSE 0 END) AS `{feature}`"
        for feature, (expected, exact) in checks.items()
    )
    result = sql.one(
        _feature_oracle_sql(settings, peak_names)
        + f"""
        SELECT count(*) AS compared,
               count_if(f.household_id IS NULL OR e.household_id IS NULL) AS unmatched, {counts}
        FROM {peak_names.features} f
        FULL OUTER JOIN expected e ON f.household_id = e.household_id AND f.feature_date = e.d
        """  # noqa: S608
    )
    assert result["compared"] >= DENSE_ROWS
    assert result["unmatched"] == 0
    wrong = {name: result[name] for name in checks if result[name]}
    assert not wrong, f"features that differ from the recomputation (rows): {wrong}"


# ----------------------------------------------------------------------------- AC-41
def test_ac41_deployed_feature_and_label_keys_are_complete(sql, settings, peak_names) -> None:
    gold = settings.table("gold", "household_daily_consumption")
    households = settings.table("silver", "households")
    start = settings.study_start_date_sql
    grid = (
        f"(SELECT household_id, explode(sequence({start}, (SELECT max(reading_date) FROM {gold}))) "
        f"AS d FROM {households})"
    )
    for table, key, shift in (
        (peak_names.features, "feature_date", 0),
        (peak_names.labels, "target_date", 1),
    ):
        shape = sql.one(
            f"SELECT count(*) AS n, count(DISTINCT household_id, {key}) AS keys FROM {table}"
        )
        assert shape["n"] == DENSE_ROWS, table
        assert shape["keys"] == DENSE_ROWS, table
        gaps = sql.scalar(
            f"SELECT count(*) FROM {grid} g FULL OUTER JOIN {table} t "  # noqa: S608
            f"ON t.household_id = g.household_id AND t.{key} = date_add(g.d, {shift}) "
            "WHERE g.household_id IS NULL OR t.household_id IS NULL"
        )
        assert gaps == 0, f"{table}: keys differ from households x dates"


# ----------------------------------------------------------------------------- AC-44 / AC-47
def _qr19_violations(sql, settings, labels: str) -> int:
    gold = settings.table("gold", "household_daily_consumption")
    return sql.scalar(
        f"""
        SELECT count(*) FROM {labels} l
        LEFT JOIN {gold} g ON g.household_id = l.household_id AND g.reading_date = l.target_date
        WHERE l.label_consumption_spike NOT IN (0, 1)
           OR (l.label_consumption_spike IS NOT NULL)
              <> (coalesce(g.is_complete_day, false)
                  AND coalesce(l.baseline_day_count = {DEFAULTS.baseline_day_count}, false))
           OR l.is_eligible <> (size(l.ineligibility_reasons) = 0)
        """  # noqa: S608
    )


def test_ac44_deployed_label_counts_and_qr19(sql, settings, peak_names) -> None:
    labelled = sql.one(
        f"SELECT count(*) AS n, avg(label_consumption_spike) AS share, "
        f"CAST(min(target_date) AS STRING) AS first_t, CAST(max(target_date) AS STRING) AS last_t "
        f"FROM {peak_names.labels} WHERE label_consumption_spike IS NOT NULL"
    )
    assert labelled["n"] == 33093
    assert 0.145 <= labelled["share"] <= 0.147
    assert labelled["first_t"] == "2012-07-29"
    assert labelled["last_t"] == "2014-02-27"
    assert _qr19_violations(sql, settings, peak_names.labels) == 0


def test_ac47_deployed_eligible_rows_per_split(sql, peak_names) -> None:
    expected = {
        "train": (16969, 14.0),
        "validation": (7170, 15.8),
        "test": (5116, 13.6),
    }
    for split, (start, end) in DEFAULTS.split_ranges().items():
        row = sql.one(
            f"SELECT count(*) AS n, avg(label_consumption_spike) * 100 AS share "
            f"FROM {peak_names.labels} WHERE is_eligible AND label_consumption_spike IS NOT NULL "
            f"AND target_date BETWEEN DATE'{start}' AND DATE'{end}'"
        )
        rows, share = expected[split]
        assert row["n"] == rows, split
        assert abs(row["share"] - share) <= 0.1, split
    edges = sql.one(
        f"SELECT CAST(min(CASE WHEN is_eligible THEN target_date END) AS STRING) AS first_ok, "
        f"CAST(max(CASE WHEN NOT is_eligible THEN target_date END) AS STRING) AS last_bad "
        f"FROM {peak_names.labels} WHERE label_consumption_spike IS NOT NULL"
    )
    assert edges["first_ok"] >= "2012-10-01"
    assert edges["last_bad"] == "2013-10-31"


# ----------------------------------------------------------------------------- AC-63
def _label_properties(sql, table: str) -> dict[str, str]:
    return {row["key"]: row["value"] for row in sql.rows(f"SHOW TBLPROPERTIES {table}")}


def test_ac63_before_parameter_run_snapshot(settings, contracts, checksum, evidence) -> None:
    stem = "ml_household_labels_daily"
    columns = [name for name, _ in contracts.columns(stem)]
    state = checksum(contracts.table(stem, settings), columns)
    evidence.save("ac63_before_parameter_run", state)


def test_ac63_after_parameter_run_and_restore(
    sql, settings, contracts, checksum, evidence, peak_names, peak_job, peak_runner
) -> None:
    before = evidence.load("ac63_before_parameter_run", "test_ac63_before_parameter_run_snapshot")
    stem = "ml_household_labels_daily"
    columns = [name for name, _ in contracts.columns(stem)]
    table = contracts.table(stem, settings)
    strict = {"label_threshold": "1.5", "coverage_min": "0.90"}
    try:
        run = peak_runner.run(peak_job, params=strict, only=["build_labels"])
        parameters = run.outputs["build_labels"]["parameters"]
        assert float(parameters["smart_meter.label_threshold"]) == 1.5
        assert float(parameters["smart_meter.coverage_min"]) == 0.90
        properties = _label_properties(sql, peak_names.labels)
        assert float(properties["smart_meter.label_threshold"]) == 1.5
        assert float(properties["smart_meter.coverage_min"]) == 0.90
        ranges = " OR ".join(
            f"target_date BETWEEN DATE'{s}' AND DATE'{e}'"
            for s, e in DEFAULTS.split_ranges().values()
        )
        row = sql.one(
            f"SELECT count(*) AS n, avg(label_consumption_spike) * 100 AS share "
            f"FROM {peak_names.labels} WHERE is_eligible AND label_consumption_spike IS NOT NULL "
            f"AND ({ranges})"
        )
        assert row["n"] == 29100  # below the default 29,255
        assert abs(row["share"] - 7.9) <= 1.0
        assert row["share"] < 14.0
    finally:
        defaults = {"label_threshold": "1.3", "coverage_min": "0.80"}
        peak_runner.run(peak_job, params=defaults, only=["build_labels"])
    restored = checksum(table, columns)
    assert restored == {k: before[k] for k in ("row_count", "checksum")}


# ----------------------------------------------------------------------------- AC-64
def test_ac64_deployed_columns_match_contracts(sql, settings, contracts) -> None:
    for stem in FIVE_CONTRACTS:
        _, layer, name = contracts.load(stem)["dataset"].split(".")
        actual = sql.rows(
            f"SELECT column_name, lower(full_data_type) AS full_data_type "
            f"FROM {settings.catalog}.information_schema.columns "
            f"WHERE table_schema = '{settings.schema(layer)}' AND table_name = '{name}' "
            f"ORDER BY ordinal_position"
        )
        deployed = [(row["column_name"], row["full_data_type"]) for row in actual]
        assert deployed == contracts.columns(stem), stem


# ----------------------------------------------------------------------------- AC-66
def _state(settings, contracts, checksum) -> dict:
    state = {}
    for stem, key in SNAPSHOT_TABLES:
        columns = [name for name, _ in contracts.columns(stem)]
        state[key] = checksum(contracts.table(stem, settings), columns)
    return state


def test_ac66_before_rebuild_snapshot(settings, contracts, checksum, evidence) -> None:
    evidence.save("ac66_before_rebuild", _state(settings, contracts, checksum))


def _table_exists(sql, settings, contracts, stem: str) -> bool:
    _, layer, name = contracts.load(stem)["dataset"].split(".")
    return (
        sql.scalar(
            f"SELECT count(*) FROM {settings.catalog}.information_schema.tables "
            f"WHERE table_schema = '{settings.schema(layer)}' AND table_name = '{name}'"
        )
        == 1
    )


def test_ac66_after_rerun_and_rebuild_checksums_equal(
    sql, settings, contracts, checksum, evidence, peak_job, peak_runner
) -> None:
    """Rerun mode: 0 inserted, 0 updated, 0 deleted. Rebuild mode (after the user-run reset
    script dropped the three tables): the rebuild inserts exactly the snapshot rows. Both modes
    end with the snapshot counts and checksums."""
    before = evidence.load("ac66_before_rebuild", "test_ac66_before_rebuild_snapshot")
    rebuild = not all(_table_exists(sql, settings, contracts, stem) for stem, _ in SNAPSHOT_TABLES)
    run = peak_runner.run(peak_job, only=DATA_TASKS)
    merges = {
        "silver_weather": run.outputs["build_weather_silver"]["merge"],
        "features": run.outputs["build_features"]["merge"],
        "labels": run.outputs["build_labels"]["merge"],
    }
    for key, merge in merges.items():
        inserted = before[key]["row_count"] if rebuild else 0
        assert merge == {"inserted": inserted, "updated": 0, "deleted": 0}, (key, rebuild)
    after = _state(settings, contracts, checksum)
    assert {k: v for k, v in after.items()} == {k: before[k] for k in after}
    evidence.save("ac66_after_rebuild", {"rebuild_after_reset": rebuild, "merges": merges})
