"""SQL builders for counts, reconciliation and checksums (FR-09, NFR-07, DA-01 fallback).

Rule, scope and duplicate counts are **table totals over the current state** of
``silver.meter_readings_evaluated``: the table is recomputed from all of Bronze whenever it is
refreshed and is unchanged when the platform skips an update as up to date, so the totals do not
depend on the event log (spike 04, ADR 0001). There is no per-update delta; where an acceptance
criterion compares an input with its effect, take the totals before and after.

Each builder returns one SQL string that works on Databricks SQL and on local Spark. Table names
are passed in, so tests can run the same SQL over temporary views.
"""

from __future__ import annotations

from smart_meter_peak_prediction.config import Settings
from smart_meter_peak_prediction.rules import DROP_RULE_PRECEDENCE


def count_column(rule_id: str) -> str:
    """Result column of a rule total, for example ``QR-03`` -> ``qr_03``."""
    return rule_id.lower().replace("-", "_")


def rule_counts_sql(evaluated: str) -> str:
    """One row of totals over the evaluation table.

    Columns: ``evaluated_rows``; one column per drop rule (``qr_02`` ...), counting the rows
    whose ``failed_rules`` contain it (a row failing two rules counts under both); ``sf_01``
    (rows outside the study period); ``qr_09`` (duplicates); ``quarantine_rows`` (rows failing
    at least one drop rule); ``silver_rows`` (rows with ``is_silver``).
    """
    per_rule = ",\n  ".join(
        f"count_if(array_contains(failed_rules, '{rule}')) AS {count_column(rule)}"
        for rule in sorted(DROP_RULE_PRECEDENCE)
    )
    return f"""SELECT
  count(*) AS evaluated_rows,
  {per_rule},
  count_if(is_out_of_scope) AS sf_01,
  count_if(is_duplicate) AS qr_09,
  count_if(size(failed_rules) > 0) AS quarantine_rows,
  count_if(is_silver) AS silver_rows
FROM {evaluated}"""


def published_counts_sql(daily: str, households: str) -> str:
    """One row with QR-10, QR-12, QR-14 and QR-15 totals over the published tables.

    - ``qr_10``: days with ``is_complete_day = false`` in daily consumption.
    - ``qr_12``: households of daily consumption that are absent from ``silver.households``.
    - ``qr_14``: households with an ``acorn_group`` outside the allowed values.
    - ``qr_15``: households with a ``tariff`` outside the allowed values.
    """
    return f"""SELECT
  (SELECT count_if(NOT is_complete_day) FROM {daily}) AS qr_10,
  (SELECT count(*) FROM (SELECT DISTINCT household_id FROM {daily}) d
     WHERE NOT EXISTS (SELECT 1 FROM {households} h WHERE h.household_id = d.household_id))
    AS qr_12,
  (SELECT count_if(acorn_group IS NULL
                   OR acorn_group NOT IN ('Affluent', 'Comfortable', 'Adversity'))
     FROM {households}) AS qr_14,
  (SELECT count_if(tariff IS NULL OR tariff NOT IN ('Std', 'ToU')) FROM {households}) AS qr_15"""


def reconciliation_sql(evaluated: str, silver: str, quarantine: str, settings: Settings) -> str:
    """Classify every evaluated (Bronze) row by ``_source_ref`` (AC-11).

    The classes are computed from the published tables and from the row itself, not from the
    flags of the evaluation table, so the query checks the routing:

    - ``in_silver``: the ``_source_ref`` is in ``silver.meter_readings``;
    - ``in_quarantine``: the ``_source_ref`` is in the quarantine;
    - ``is_duplicate``: not in either, and the key ``(household_id, reading_ts)`` is in Silver
      under another ``_source_ref`` with an earlier or equal ``_ingested_at``;
    - ``out_of_period``: ``reading_ts`` is outside the study period.

    Returns one row: ``bronze_rows``, one count per class, ``unclassified`` and
    ``double_classified`` (both must be 0).
    """
    start, end = settings.study_start_sql, settings.study_end_exclusive_sql
    return f"""WITH classified AS (
  SELECT
    e._source_ref,
    EXISTS (SELECT 1 FROM {silver} s WHERE s._source_ref = e._source_ref) AS in_silver,
    EXISTS (SELECT 1 FROM {quarantine} q WHERE q._source_ref = e._source_ref) AS in_quarantine,
    (e.reading_ts IS NOT NULL AND NOT (e.reading_ts >= {start} AND e.reading_ts < {end}))
      AS out_of_period,
    EXISTS (SELECT 1 FROM {silver} s
            WHERE s.household_id = e.household_id AND s.reading_ts = e.reading_ts
              AND s._source_ref <> e._source_ref AND s._ingested_at <= e._ingested_at)
      AS has_earlier_winner
  FROM {evaluated} e
), labelled AS (
  SELECT *,
    (NOT in_silver AND NOT in_quarantine AND NOT out_of_period AND has_earlier_winner)
      AS is_duplicate
  FROM classified
), counted AS (
  SELECT *,
    (CAST(in_silver AS INT) + CAST(in_quarantine AS INT) + CAST(is_duplicate AS INT)
     + CAST(out_of_period AS INT)) AS classes
  FROM labelled
)
SELECT
  count(*) AS bronze_rows,
  count_if(in_silver) AS in_silver,
  count_if(in_quarantine) AS in_quarantine,
  count_if(is_duplicate) AS is_duplicate,
  count_if(out_of_period) AS out_of_period,
  count_if(classes = 0) AS unclassified,
  count_if(classes > 1) AS double_classified
FROM counted"""


def table_checksum_sql(table: str, columns: list[str]) -> str:
    """Order-independent checksum: row count and the sum of a row hash (AC-09, AC-27).

    ``xxhash64`` over the listed columns, summed as ``DECIMAL(38,0)`` so the sum cannot
    overflow and does not depend on row order or partitioning.
    """
    if not columns:
        raise ValueError("table_checksum_sql needs at least one column")
    cols = ", ".join(f"`{c}`" for c in columns)
    return (
        f"SELECT count(*) AS row_count, "
        f"sum(cast(xxhash64({cols}) AS DECIMAL(38,0))) AS checksum FROM {table}"
    )


def event_log_failed_records_sql(event_log: str, update_id: str | None = None) -> str:
    """Optional run observability: failed records per expectation from the published event log.

    Present only for updates that refreshed the dataset (spike 04, DA-01 partial). No acceptance
    criterion depends on it; use the totals above instead.
    """
    where = "event_type = 'flow_progress'"
    if update_id is not None:
        if not all(ch.isalnum() or ch == "-" for ch in update_id):
            raise ValueError("update_id must be alphanumeric with dashes")
        where += f" AND origin.update_id = '{update_id}'"
    return f"""SELECT origin.update_id AS update_id, exp.name AS expectation,
  sum(exp.failed_records) AS failed_records
FROM (
  SELECT origin, explode(from_json(
    details:flow_progress.data_quality.expectations,
    'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>'
  )) AS exp
  FROM {event_log}
  WHERE {where}
)
GROUP BY origin.update_id, exp.name"""
