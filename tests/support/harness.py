"""Local pipeline harness: runs the library functions in pipeline order over Bronze snapshots.

It applies the rule catalog the way the pipeline does:
- fail expectations raise ``ExpectationFailed`` (the update aborts, nothing is returned, which
  models "0 rows committed", AC-15);
- drop rules and the scope filter route rows through ``silver.py`` (counted by ``metrics.py``);
- warn expectations are evaluated too, for the wiring and catalog checks only (``warn_counts``).

Each ``run_update`` recomputes everything from the given Bronze snapshots, as the materialized
views do. The counts of the acceptance criteria are not read from ``warn_counts`` but computed
by ``metrics.py`` SQL over the evaluation DataFrame (DA-01 fallback).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from smart_meter_peak_prediction import gold, rules, silver
from smart_meter_peak_prediction.config import Settings
from support import builders

ROOT = Path(__file__).resolve().parents[2]
SUMMARY_SQL = ROOT / "pipelines" / "household_data_quality.sql"
LOCAL_GOLD_SCHEMA = "gold_test"


class ExpectationFailed(Exception):  # noqa: N818  (name fixed by the DESIGN)
    def __init__(self, dataset: str, expectation: str, failed_rows: int):
        super().__init__(f"{dataset}: expectation {expectation} failed for {failed_rows} row(s)")
        self.dataset = dataset
        self.expectation = expectation
        self.failed_rows = failed_rows


@dataclass
class Update:
    spark: SparkSession
    settings: Settings
    evaluated: DataFrame
    silver: DataFrame
    quarantine: DataFrame
    households_checked: DataFrame
    households: DataFrame
    daily: DataFrame
    orphan: DataFrame
    monthly: DataFrame
    warn_counts: dict[str, int] = field(default_factory=dict)

    def register_views(self) -> dict[str, str]:
        """Temp views so the ``metrics.py`` SQL can run over the update's tables."""
        names = {
            "evaluated": self.evaluated,
            "silver": self.silver,
            "quarantine": self.quarantine,
            "households": self.households,
            "daily": self.daily,
            "monthly": self.monthly,
        }
        for name, df in names.items():
            df.createOrReplaceTempView(name)
        return {name: name for name in names}

    def summary(self) -> DataFrame:
        return run_summary_sql(self.spark, self.monthly, self.settings)


def check_rules(
    df: DataFrame, dataset: str, settings: Settings, warn_counts: dict[str, int] | None = None
) -> dict[str, int]:
    """Evaluate every attached rule of a dataset in one pass; raise on a failing fail rule."""
    attached = [r for r in rules.rules_for(dataset) if r.attach in {"warn", "fail"}]
    if not attached:
        return {}
    aggregates = [
        F.sum(F.when(F.expr(f"coalesce(({r.predicate(settings)}), false)"), 0).otherwise(1)).alias(
            r.name
        )
        for r in attached
    ]
    row = df.agg(*aggregates).collect()[0]
    failed = {r.name: int(row[r.name] or 0) for r in attached}
    for r in attached:
        if r.attach == "fail" and failed[r.name] > 0:
            raise ExpectationFailed(dataset, r.name, failed[r.name])
    if warn_counts is not None:
        warn_counts.update({r.name: failed[r.name] for r in attached if r.attach == "warn"})
    return failed


def run_update(
    spark: SparkSession,
    settings: Settings,
    files: DataFrame,
    kafka: DataFrame,
    households_bronze: DataFrame | None = None,
) -> Update:
    """One pipeline update from Bronze snapshots (a full refresh gives the same result)."""
    warn: dict[str, int] = {}
    evaluated = silver.evaluate(files, kafka, settings).cache()
    check_rules(evaluated, rules.EVALUATED, settings, warn)

    readings = silver.silver_readings(evaluated)
    quarantine = silver.quarantine(evaluated)
    check_rules(quarantine, rules.QUARANTINE, settings, warn)

    bronze_hh = (
        households_bronze if households_bronze is not None else builders.bronze_households(spark)
    )
    checked = silver.households_checked(bronze_hh)
    check_rules(checked, rules.HOUSEHOLDS_CHECKED, settings, warn)
    households = silver.households(checked)
    check_rules(households, rules.HOUSEHOLDS, settings, warn)

    daily = gold.daily_consumption(readings)
    check_rules(daily, rules.DAILY, settings, warn)
    orphan = gold.orphan_check(daily, households)
    check_rules(orphan, rules.ORPHAN_CHECK, settings, warn)

    monthly = gold.monthly_quality(readings, households, settings)
    check_rules(monthly, rules.MONTHLY, settings, warn)

    return Update(
        spark=spark,
        settings=settings,
        evaluated=evaluated,
        silver=readings,
        quarantine=quarantine,
        households_checked=checked,
        households=households,
        daily=daily,
        orphan=orphan,
        monthly=monthly,
        warn_counts=warn,
    )


def summary_select_sql(
    spark_catalog: str = "spark_catalog", gold_schema: str = LOCAL_GOLD_SCHEMA
) -> str:
    """The SELECT body of ``pipelines/household_data_quality.sql`` with names substituted."""
    text = SUMMARY_SQL.read_text(encoding="utf-8")
    text = text.replace("${smart_meter.catalog}", spark_catalog)
    text = text.replace("${smart_meter.gold_schema}", gold_schema)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    text = re.sub(r"^\s*CREATE VIEW\s+\S+\s+AS\s+", "", text, count=1, flags=re.IGNORECASE)
    return text.strip().rstrip(";")


def run_summary_sql(spark: SparkSession, monthly: DataFrame, settings: Settings) -> DataFrame:
    """Run the summary view SQL locally over a monthly DataFrame and apply the summary checks."""
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {LOCAL_GOLD_SCHEMA}")
    monthly.write.mode("overwrite").saveAsTable(
        f"{LOCAL_GOLD_SCHEMA}.household_data_quality_monthly"
    )
    result = spark.sql(summary_select_sql())
    check_rules(result, rules.SUMMARY_CHECK, settings)
    return result


def totals(update: Update) -> dict[str, int]:
    """Rule, scope and duplicate totals of ``metrics.py`` over the update's evaluation table."""
    from smart_meter_peak_prediction import metrics

    update.register_views()
    return update.spark.sql(metrics.rule_counts_sql("evaluated")).collect()[0].asDict()


def checksum(update: Update, table: str, columns: list[str]) -> tuple[int, int | None]:
    """Order-independent ``(row_count, checksum)`` of one of the update's registered views."""
    from smart_meter_peak_prediction import metrics

    update.register_views()
    row = update.spark.sql(metrics.table_checksum_sql(table, columns)).collect()[0]
    return row.row_count, row.checksum


def rows(df: DataFrame) -> list[dict]:
    """Collect rows as dicts; naive timestamps (process TZ is pinned to UTC) become aware UTC."""
    from datetime import UTC, datetime

    def fix(value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        if isinstance(value, list):
            return [fix(v) for v in value]
        return value

    return [{k: fix(v) for k, v in r.asDict().items()} for r in df.collect()]


def build_update(
    spark: SparkSession,
    files=(),
    kafka=(),
    households=None,
    settings: Settings | None = None,
    partitions: int | None = None,
) -> Update:
    """``run_update`` from lists of builder rows; ``partitions`` repartitions every Bronze input."""
    settings = settings or Settings()

    def frame(df: DataFrame) -> DataFrame:
        return df.repartition(partitions) if partitions else df

    hh = frame(builders.bronze_households(spark, households)) if households is not None else None
    return run_update(
        spark,
        settings,
        frame(builders.bronze_files(spark, files)),
        frame(builders.bronze_kafka(spark, kafka)),
        hh,
    )
