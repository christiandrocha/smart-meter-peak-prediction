"""Lakeflow pipeline `smart_meter_silver_gold`: thin wiring of the Silver and Gold datasets.

All logic lives in `src/smart_meter_peak_prediction` (silver.py, gold.py, rules.py) and is tested
locally. This file only declares the datasets and attaches the expectations of the rule catalog
(ADR 0004):

- every dataset is a materialized view (batch reads, `@dlt.table`), recomputed from Bronze on each
  update (ADR 0005); there are no streaming reads;
- `silver.meter_readings_evaluated` is published (fully qualified name, not private): the counts
  of `metrics.py` are table totals over it (DA-01 fallback, ADR 0001);
- `households_checked`, `daily_consumption_orphan_check` and `household_data_quality_check` are
  private datasets that only carry fail or warn expectations;
- `gold.household_data_quality` is a persisted view created by `household_data_quality.sql`.

Warn and fail expectations come from `rules.expect_all` and `rules.expect_all_or_fail`; the warn
counters add observability in the published event log only.

Settings come from the pipeline configuration (keys `smart_meter.*`, set by the bundle). The
session time zone must be UTC (DA-07, golden rule 5); the pipeline fails at definition time if it
is not.
"""

import sys

import dlt

# `spark` is provided by the pipeline runtime.
_src_path = spark.conf.get("smart_meter.src_path", "")
if _src_path and _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from smart_meter_peak_prediction import gold, rules, silver  # noqa: E402
from smart_meter_peak_prediction.config import PIPELINE_PREFIX, Settings  # noqa: E402

_session_tz = spark.conf.get("spark.sql.session.timeZone")
assert _session_tz == "UTC", f"session time zone must be UTC (DA-07), found {_session_tz!r}"

_SETTING_FIELDS = (
    "catalog",
    "bronze_schema",
    "silver_schema",
    "gold_schema",
    "ml_schema",
    "study_start",
    "study_end",
    "cutoff",
)
# No default: a missing key must fail the update, not fall back to another catalog.
SETTINGS = Settings.from_pipeline_configuration(
    {PIPELINE_PREFIX + name: spark.conf.get(PIPELINE_PREFIX + name) for name in _SETTING_FIELDS}
)

EVALUATED_FQN = SETTINGS.table("silver", rules.EVALUATED)
SILVER_READINGS_FQN = SETTINGS.table("silver", "meter_readings")
QUARANTINE_FQN = SETTINGS.table("silver", rules.QUARANTINE)
HOUSEHOLDS_FQN = SETTINGS.table("silver", rules.HOUSEHOLDS)
DAILY_FQN = SETTINGS.table("gold", rules.DAILY)
MONTHLY_FQN = SETTINGS.table("gold", rules.MONTHLY)
SUMMARY_VIEW_FQN = SETTINGS.table("gold", "household_data_quality")


def _expectations(dataset: str):
    """Decorator that attaches the warn and fail expectations of the rule catalog."""
    warn = rules.expect_all(dataset, SETTINGS)
    fail = rules.expect_all_or_fail(dataset, SETTINGS)

    def decorate(fn):
        if warn:
            fn = dlt.expect_all(warn)(fn)
        if fail:
            fn = dlt.expect_all_or_fail(fail)(fn)
        return fn

    return decorate


# ----------------------------------------------------------------------------- silver readings
@dlt.table(
    name=EVALUATED_FQN,
    comment="Ops table: every Bronze reading row with its failed rules, scope, dedup ranks and "
    "dedup key. "
    "Source of the rule, scope and duplicate counts. Not a PEAK_MODEL input.",
)
@_expectations(rules.EVALUATED)
def meter_readings_evaluated():
    return silver.evaluate(
        spark.read.table(SETTINGS.bronze_files_readings),
        spark.read.table(SETTINGS.bronze_kafka_readings),
        SETTINGS,
    )


@dlt.table(
    name=SILVER_READINGS_FQN,
    comment="One row per household per half hour, first ingested wins.",
    cluster_by=["household_id", "reading_date"],
)
def meter_readings():
    return silver.silver_readings(spark.read.table(EVALUATED_FQN))


@dlt.table(
    name=QUARANTINE_FQN,
    comment="Bronze reading rows that failed a drop rule.",
)
@_expectations(rules.QUARANTINE)
def meter_readings_quarantine():
    return silver.quarantine(spark.read.table(EVALUATED_FQN))


# ----------------------------------------------------------------------------- households
@dlt.table(name=rules.HOUSEHOLDS_CHECKED, private=True)
@_expectations(rules.HOUSEHOLDS_CHECKED)
def households_checked():
    return silver.households_checked(spark.read.table(SETTINGS.bronze_files_households))


@dlt.table(name=HOUSEHOLDS_FQN, comment="One row per sampled household.")
@_expectations(rules.HOUSEHOLDS)
def households():
    return silver.households(dlt.read(rules.HOUSEHOLDS_CHECKED))


# ----------------------------------------------------------------------------- gold
@dlt.table(
    name=DAILY_FQN,
    comment="One row per household per UTC day with a reading.",
    cluster_by=["household_id", "reading_date"],
)
@_expectations(rules.DAILY)
def household_daily_consumption():
    return gold.daily_consumption(spark.read.table(SILVER_READINGS_FQN))


@dlt.table(name=rules.ORPHAN_CHECK, private=True)
@_expectations(rules.ORPHAN_CHECK)
def daily_consumption_orphan_check():
    return gold.orphan_check(spark.read.table(DAILY_FQN), spark.read.table(HOUSEHOLDS_FQN))


@dlt.table(
    name=MONTHLY_FQN,
    comment="One row per household per study month, dense, facts only.",
    cluster_by=["household_id"],
)
@_expectations(rules.MONTHLY)
def household_data_quality_monthly():
    return gold.monthly_quality(
        spark.read.table(SILVER_READINGS_FQN), spark.read.table(HOUSEHOLDS_FQN), SETTINGS
    )


# `gold.household_data_quality` (persisted view) is created by household_data_quality.sql. The
# private dataset below reads it to carry its contract checks.
@dlt.table(name=rules.SUMMARY_CHECK, private=True)
@_expectations(rules.SUMMARY_CHECK)
def household_data_quality_check():
    return spark.read.table(SUMMARY_VIEW_FQN)
