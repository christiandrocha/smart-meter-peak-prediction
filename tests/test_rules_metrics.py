"""Rule catalog and metrics SQL builders (AC-12, AC-15, AC-27). Extra to the manifest."""

from __future__ import annotations

import re

import pytest
from support import builders as b
from support.harness import build_update, totals

from smart_meter_peak_prediction import metrics, rules
from smart_meter_peak_prediction.config import Settings

SETTINGS = Settings()


def test_ac12_expectation_names_follow_rule_id_prefix_convention() -> None:
    for rule in rules.RULES:
        stem = rule.rule_id.lower().replace("-", "_")
        if rule.rule_id.startswith(("QR-", "SF-", "INV-")):
            assert rule.name.startswith(stem + "_"), rule.name
        assert re.fullmatch(r"[a-z0-9_]+", rule.name)
    names = [r.name for r in rules.RULES]
    assert len(names) == len(set(names))
    assert len({r.rule_id for r in rules.RULES}) == len(rules.RULES)


def test_ac12_every_drop_rule_has_a_counter_on_the_evaluation_dataset() -> None:
    warn = rules.expect_all(rules.EVALUATED, SETTINGS)
    fail = rules.expect_all_or_fail(rules.EVALUATED, SETTINGS)
    for rule_id in (*rules.DROP_RULE_PRECEDENCE, "SF-01", "QR-08", "QR-09"):
        assert rules.rule_by_id(rule_id).name in warn, rule_id
    assert set(fail) == {
        "qr_01_household_id_shape",
        "qr_06_path_matches_cutoff",
        "inv_01_source_ref_unique",
    }
    assert not set(warn) & set(fail)


def test_ac15_fail_rules_of_the_design_are_attached_as_fail() -> None:
    fail_ids = {r.rule_id for r in rules.RULES if r.attach == "fail"}
    assert {"QR-01", "QR-06", "INV-01", "QR-11", "QR-13"} <= fail_ids
    warn_ids = {r.rule_id for r in rules.RULES if r.attach == "warn"}
    assert {"QR-08", "QR-10", "QR-12", "QR-14", "QR-15"} <= warn_ids


def test_ac12_expectation_names_map_back_to_rule_ids() -> None:
    assert rules.rule_id_of_expectation("qr_03_on_30_min_grid") == "QR-03"
    assert rules.rule_id_of_expectation("unknown") is None


def test_ac16_qr06_uses_the_cutoff_of_the_settings() -> None:
    custom = Settings(cutoff="2013-11-01T00:00:00Z")
    assert "2013-11-01 00:00:00+00:00" in rules.rule_by_id("QR-06").predicate(custom)
    assert "2013-12-01" in rules.rule_by_id("QR-06").predicate(SETTINGS)


def test_ac12_rule_counts_sql_covers_every_drop_rule_scope_and_duplicates() -> None:
    sql = metrics.rule_counts_sql("silver.meter_readings_evaluated")
    for rule_id in rules.DROP_RULE_PRECEDENCE:
        assert f"array_contains(failed_rules, '{rule_id}')" in sql
    assert "is_out_of_scope" in sql
    assert "is_duplicate" in sql
    assert "FROM silver.meter_readings_evaluated" in sql
    assert "event_log" not in sql  # counts are table totals, not event-log reads


def test_ac12_event_log_query_is_optional_observability_and_rejects_odd_update_ids() -> None:
    assert "flow_progress" in metrics.event_log_failed_records_sql("cat.silver.pipeline_event_log")
    with pytest.raises(ValueError, match="update_id"):
        metrics.event_log_failed_records_sql("log", "x' OR '1'='1")


def test_ac27_checksum_is_order_independent_and_detects_a_changed_value(spark) -> None:
    left = spark.createDataFrame([("a", 1), ("b", 2), ("c", 3)], "k string, v int")
    right = spark.createDataFrame([("c", 3), ("a", 1), ("b", 2)], "k string, v int").repartition(3)
    other = spark.createDataFrame([("a", 1), ("b", 2), ("c", 4)], "k string, v int")
    for name, df in (("left", left), ("right", right), ("other", other)):
        df.createOrReplaceTempView(f"chk_{name}")

    def digest(name: str):
        row = spark.sql(metrics.table_checksum_sql(f"chk_{name}", ["k", "v"])).collect()[0]
        return row.row_count, row.checksum

    assert digest("left") == digest("right")
    assert digest("left") != digest("other")
    with pytest.raises(ValueError, match="at least one column"):
        metrics.table_checksum_sql("t", [])


def test_ac12_totals_are_unchanged_by_a_second_identical_update(spark) -> None:
    """No per-update delta exists: an update with no new input leaves the totals as they were."""
    files = [b.file_row("MAC000001", moment=b.T_FILES, energy_kwh_raw="Null")]
    first = totals(build_update(spark, files, []))
    second = totals(build_update(spark, files, []))
    assert first == second
    assert first["qr_04"] == 1
