"""Delta write helpers: change-only MERGE, ``replaceWhere`` overwrite and table properties.

ADR 0011: each PEAK_MODEL output is recomputed in full and written with one MERGE that updates a
row only when a column differs (null-safe), inserts new keys and deletes keys the recomputation
no longer produces. A rerun with no new input therefore changes 0 rows (NFR-11, AC-66).

The SQL builders return text and need no Delta; the writers need a Databricks session.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date

from pyspark.sql import DataFrame, SparkSession

MERGE_METRIC_NAMES = {
    "inserted": "numTargetRowsInserted",
    "updated": "numTargetRowsUpdated",
    "deleted": "numTargetRowsDeleted",
}
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_name(name: str) -> str:
    if not _NAME.match(name):
        raise ValueError(f"unsafe column name: {name!r}")
    return name


def merge_sql(target: str, source: str, keys: Sequence[str], columns: Sequence[str]) -> str:
    """Change-only MERGE of ``source`` (a table or view) into ``target``.

    ``columns`` lists every column of the output. The change condition compares each non-key
    column with ``<=>`` so a null on both sides is equal, and rows that did not change are not
    rewritten. Rows of the target that the source no longer produces are deleted.
    """
    if not keys:
        raise ValueError("merge_sql needs at least one key column")
    names = [_check_name(c) for c in columns]
    missing = [k for k in keys if k not in names]
    if missing:
        raise ValueError("key column(s) not in the column list: " + ", ".join(missing))
    on = " AND ".join(f"t.`{k}` = s.`{k}`" for k in keys)
    changed = " AND ".join(f"t.`{c}` <=> s.`{c}`" for c in names if c not in keys)
    matched = f"WHEN MATCHED AND NOT ({changed}) THEN UPDATE SET *\n" if changed else ""
    return (
        f"MERGE INTO {target} AS t\n"
        f"USING {source} AS s\n"
        f"ON {on}\n"
        f"{matched}"
        "WHEN NOT MATCHED THEN INSERT *\n"
        "WHEN NOT MATCHED BY SOURCE THEN DELETE"
    )


def merge_changes(
    spark: SparkSession, df: DataFrame, target: str, keys: Sequence[str], view: str
) -> dict[str, int]:
    """Run ``merge_sql`` for a recomputed DataFrame and return the MERGE metrics."""
    before = _latest_version(spark, target)
    df.createOrReplaceTempView(view)
    spark.sql(merge_sql(target, view, keys, df.columns))
    return last_merge_metrics(spark, target, after_version=before)


def parse_merge_metrics(operation_metrics: Mapping[str, str]) -> dict[str, int]:
    """Delta MERGE ``operationMetrics`` as ``inserted``, ``updated`` and ``deleted`` counts."""
    return {
        label: int(operation_metrics.get(metric, 0)) for label, metric in MERGE_METRIC_NAMES.items()
    }


def _latest_version(spark: SparkSession, table: str) -> int:
    return int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"])


def last_merge_metrics(
    spark: SparkSession, table: str, after_version: int | None = None
) -> dict[str, int]:
    """Metrics of the latest MERGE in the Delta history (later ALTERs are skipped).

    With ``after_version`` (the table version before the MERGE) only a MERGE committed after it
    counts; when Delta committed nothing, all three counts are 0, so a no-op rerun never reports
    the metrics of an earlier load.
    """
    history = spark.sql(f"DESCRIBE HISTORY {table}").where("operation = 'MERGE'")
    if after_version is not None:
        history = history.where(history["version"] > after_version)
    latest = history.orderBy(history["version"].desc()).limit(1).collect()
    if not latest:
        if after_version is not None:
            return parse_merge_metrics({})
        raise ValueError(f"no MERGE found in the history of {table}")
    return parse_merge_metrics(latest[0]["operationMetrics"])


def set_properties_sql(table: str, properties: Mapping[str, str]) -> str:
    """``ALTER TABLE ... SET TBLPROPERTIES`` with quoted keys and values."""
    if not properties:
        raise ValueError("set_properties_sql needs at least one property")

    def quote(text: str) -> str:
        return "'" + str(text).replace("\\", "\\\\").replace("'", "\\'") + "'"

    body = ", ".join(f"{quote(k)} = {quote(v)}" for k, v in properties.items())
    return f"ALTER TABLE {table} SET TBLPROPERTIES ({body})"


def replace_where_predicate(column: str, start: date, end: date) -> str:
    """Predicate for the rows of the dates ``start`` to ``end`` (inclusive) of one column."""
    if end < start:
        raise ValueError(f"replace range ends before it starts: {start} to {end}")
    name = _check_name(column)
    return f"`{name}` >= DATE'{start:%Y-%m-%d}' AND `{name}` <= DATE'{end:%Y-%m-%d}'"


def replace_where_write(df: DataFrame, table: str, predicate: str) -> None:
    """Replace the rows that match ``predicate`` by ``df`` in one transaction (AC-57).

    Delta rejects the write when ``df`` holds a row outside the predicate, so other dates cannot
    be touched by mistake.
    """
    df.write.mode("overwrite").option("replaceWhere", predicate).saveAsTable(table)
