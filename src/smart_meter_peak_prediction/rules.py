"""Rule catalog: the single definition of SF-01, QR-01 to QR-15, INV-01 and contract checks.

Every rule has an id, an expectation name (``<rule id in lower case>_<description>``, so event
log rows map to rule ids by prefix), a Spark SQL predicate that is true for a *valid* row, the
action of the DEFINE (``warn``, ``drop`` or ``fail``) and the dataset that evaluates it.

``attach`` is what the pipeline puts on the dataset. Drop rules and the scope filter act through
the routing of ``silver.py`` (they only filter rows into or out of the published tables), so on
the evaluation dataset they are attached as ``warn`` counters. They add observability in the
event log only: the counts used by the acceptance criteria come from ``metrics.py`` (DA-01
fallback, ADR 0004). Fail rules are attached as ``fail``.

The same SQL strings are used by the pipeline, by the local test harness and by ``metrics.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from smart_meter_peak_prediction.config import Settings

# Dataset keys. Short names of the pipeline datasets (the published ones live in silver/gold).
EVALUATED = "meter_readings_evaluated"
QUARANTINE = "meter_readings_quarantine"
HOUSEHOLDS_CHECKED = "households_checked"
HOUSEHOLDS = "households"
DAILY = "household_daily_consumption"
ORPHAN_CHECK = "daily_consumption_orphan_check"
MONTHLY = "household_data_quality_monthly"
SUMMARY_CHECK = "household_data_quality_check"

# Drop rules in precedence order: a row is routed under the first one it fails.
DROP_RULE_PRECEDENCE = ("QR-07", "QR-02", "QR-03", "QR-04", "QR-05")

GRID_MICROS = 1_800_000_000  # 30 minutes


def flag_expressions(settings: Settings) -> list[tuple[str, str]]:
    """Ordered ``(column, SQL)`` pairs: f07, f02, is_out_of_scope, f03, f04, f05.

    Each flag refers to columns computed before it, in this order. A rule is evaluated only when
    its inputs exist, so a row never fails twice for one root cause (DESIGN, Column derivations).
    """
    in_scope = (
        f"(reading_ts >= {settings.study_start_sql} "
        f"AND reading_ts < {settings.study_end_exclusive_sql})"
    )
    return [
        ("f07", "NOT payload_ok"),
        ("f02", "NOT f07 AND reading_ts IS NULL"),
        ("is_out_of_scope", f"NOT f07 AND NOT f02 AND NOT {in_scope}"),
        (
            "f03",
            "NOT f07 AND NOT f02 AND NOT is_out_of_scope "
            f"AND unix_micros(reading_ts) % {GRID_MICROS} != 0",
        ),
        (
            "f04",
            "NOT f07 AND NOT is_out_of_scope AND "
            "(energy_kwh IS NULL OR isnan(energy_kwh) OR abs(energy_kwh) = double('infinity'))",
        ),
        ("f05", "NOT f07 AND NOT is_out_of_scope AND NOT f04 AND energy_kwh < 0"),
    ]


FAILED_RULES_SQL = (
    "filter(array(IF(f07, 'QR-07', NULL), IF(f02, 'QR-02', NULL), IF(f03, 'QR-03', NULL), "
    "IF(f04, 'QR-04', NULL), IF(f05, 'QR-05', NULL)), x -> x IS NOT NULL)"
)

SqlOrBuilder = str | Callable[[Settings], str]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    dataset: str
    sql: SqlOrBuilder
    action: str  # DEFINE action: warn, drop or fail
    attach: str | None  # what the pipeline attaches to the dataset: warn, fail or None
    description: str = ""

    def predicate(self, settings: Settings) -> str:
        return self.sql(settings) if callable(self.sql) else self.sql


def _qr06(settings: Settings) -> str:
    return (
        "NOT payload_ok OR reading_ts IS NULL "
        f"OR (_ingestion_path = 'files' AND reading_ts < {settings.cutoff_sql}) "
        f"OR (_ingestion_path = 'kafka' AND reading_ts >= {settings.cutoff_sql})"
    )


_DROP_LIST = ", ".join(f"'{r}'" for r in sorted(DROP_RULE_PRECEDENCE))


def _counter(rule_id: str, name: str) -> Rule:
    """Counter on the evaluation dataset for a drop rule routed through ``failed_rules``."""
    return Rule(
        rule_id, name, EVALUATED, f"NOT array_contains(failed_rules, '{rule_id}')", "drop", "warn"
    )


RULES: tuple[Rule, ...] = (
    # --- silver.meter_readings_evaluated ---
    Rule(
        "SF-01",
        "sf_01_in_study_period",
        EVALUATED,
        "NOT is_out_of_scope",
        "drop",
        "warn",
        "scope transformation: excluded from Silver and quarantine, counted",
    ),
    Rule(
        "QR-01",
        "qr_01_household_id_shape",
        EVALUATED,
        "NOT payload_ok OR (household_id IS NOT NULL AND household_id RLIKE '^MAC[0-9]{6}$')",
        "fail",
        "fail",
    ),
    _counter("QR-02", "qr_02_timestamp_parses"),
    _counter("QR-03", "qr_03_on_30_min_grid"),
    _counter("QR-04", "qr_04_energy_numeric"),
    _counter("QR-05", "qr_05_energy_non_negative"),
    Rule("QR-06", "qr_06_path_matches_cutoff", EVALUATED, _qr06, "fail", "fail"),
    _counter("QR-07", "qr_07_payload_parses"),
    Rule("QR-08", "qr_08_no_rescued_data", EVALUATED, "_rescued_data IS NULL", "warn", "warn"),
    Rule(
        "QR-09",
        "qr_09_first_ingested_wins",
        EVALUATED,
        "NOT is_duplicate",
        "drop",
        "warn",
        "deduplication: loser (valid duplicate or repeat of a dropped record by _dedup_key) "
        "excluded from Silver and quarantine, counted",
    ),
    Rule(
        "INV-01",
        "inv_01_source_ref_unique",
        EVALUATED,
        "source_ref_row_count = 1",
        "fail",
        "fail",
        "primary key of the quarantine and Silver contracts",
    ),
    # --- silver.meter_readings_quarantine ---
    Rule(
        "QUARANTINE-01",
        "quarantine_rule_name_is_drop_rule",
        QUARANTINE,
        f"rule_name IN ({_DROP_LIST})",
        "fail",
        "fail",
    ),
    # --- households ---
    Rule(
        "QR-13",
        "qr_13_household_key_unique",
        HOUSEHOLDS_CHECKED,
        "household_id IS NOT NULL AND key_row_count = 1",
        "fail",
        "fail",
    ),
    Rule(
        "QR-14",
        "qr_14_acorn_group_valid",
        HOUSEHOLDS,
        "acorn_group IN ('Affluent', 'Comfortable', 'Adversity')",
        "warn",
        "warn",
    ),
    Rule("QR-15", "qr_15_tariff_valid", HOUSEHOLDS, "tariff IN ('Std', 'ToU')", "warn", "warn"),
    # --- gold ---
    Rule("QR-10", "qr_10_complete_day", DAILY, "is_complete_day", "warn", "warn"),
    Rule("QR-11", "qr_11_at_most_48_readings", DAILY, "reading_count <= 48", "fail", "fail"),
    Rule("QR-12", "qr_12_known_household", ORPHAN_CHECK, "is_known_household", "warn", "warn"),
    Rule(
        "MONTHLY-01",
        "monthly_observed_within_expected",
        MONTHLY,
        "observed_readings BETWEEN 0 AND expected_readings",
        "fail",
        "fail",
    ),
    Rule(
        "MONTHLY-02",
        "monthly_zero_within_observed",
        MONTHLY,
        "zero_readings BETWEEN 0 AND observed_readings",
        "fail",
        "fail",
    ),
    Rule(
        "MONTHLY-03",
        "monthly_has_household_record_not_null",
        MONTHLY,
        "has_household_record IS NOT NULL",
        "fail",
        "fail",
    ),
    Rule(
        "SUMMARY-01",
        "summary_coverage_ratio_in_range",
        SUMMARY_CHECK,
        "coverage_ratio_study_period BETWEEN 0 AND 1",
        "fail",
        "fail",
    ),
    Rule(
        "SUMMARY-02",
        "summary_zero_share_in_range",
        SUMMARY_CHECK,
        "zero_share IS NULL OR zero_share BETWEEN 0 AND 1",
        "fail",
        "fail",
    ),
)


def rules_for(dataset: str) -> list[Rule]:
    return [r for r in RULES if r.dataset == dataset]


def rule_by_id(rule_id: str) -> Rule:
    for rule in RULES:
        if rule.rule_id == rule_id:
            return rule
    raise KeyError(rule_id)


def expect_all(dataset: str, settings: Settings) -> dict[str, str]:
    """Expectations for ``dlt.expect_all`` (warn): name -> predicate."""
    return {r.name: r.predicate(settings) for r in rules_for(dataset) if r.attach == "warn"}


def expect_all_or_fail(dataset: str, settings: Settings) -> dict[str, str]:
    """Expectations for ``dlt.expect_all_or_fail``: name -> predicate."""
    return {r.name: r.predicate(settings) for r in rules_for(dataset) if r.attach == "fail"}


def rule_id_of_expectation(name: str) -> str | None:
    """Map an event-log expectation name back to its rule id."""
    for rule in RULES:
        if rule.name == name:
            return rule.rule_id
    return None
