"""Setup statements: idempotent layout DDL and append-only Bronze tables (AC-19, AC-28)."""

from __future__ import annotations

import re

import pytest

from smart_meter_peak_prediction import bronze, catalog_setup
from smart_meter_peak_prediction.config import Settings


def test_ac28_every_setup_statement_is_idempotent() -> None:
    for statement in catalog_setup.setup_statements(Settings()):
        assert re.match(r"CREATE (CATALOG|SCHEMA|VOLUME|TABLE) IF NOT EXISTS ", statement)


def test_ac28_main_layout_objects_in_dependency_order() -> None:
    statements = catalog_setup.setup_statements(Settings())
    heads = [s.split("(")[0].strip() for s in statements]
    assert heads == [
        "CREATE CATALOG IF NOT EXISTS smart_meter_dev",
        "CREATE SCHEMA IF NOT EXISTS smart_meter_dev.bronze",
        "CREATE SCHEMA IF NOT EXISTS smart_meter_dev.silver",
        "CREATE SCHEMA IF NOT EXISTS smart_meter_dev.gold",
        "CREATE SCHEMA IF NOT EXISTS smart_meter_dev.ml",
        "CREATE VOLUME IF NOT EXISTS smart_meter_dev.bronze.landing",
        "CREATE VOLUME IF NOT EXISTS smart_meter_dev.bronze.checkpoints",
        "CREATE TABLE IF NOT EXISTS smart_meter_dev.bronze.files_meter_readings",
        "CREATE TABLE IF NOT EXISTS smart_meter_dev.bronze.files_households",
        "CREATE TABLE IF NOT EXISTS smart_meter_dev.bronze.kafka_meter_readings",
    ]


def test_ac28_fallback_layout_uses_the_same_code_with_other_names() -> None:
    statements = catalog_setup.setup_statements(Settings.fallback_layout())
    assert "CREATE SCHEMA IF NOT EXISTS workspace.smart_meter_dev_bronze" in statements
    assert any("workspace.smart_meter_dev_bronze.kafka_meter_readings" in s for s in statements)


@pytest.mark.parametrize("table", sorted(bronze.BRONZE_TABLES))
def test_ac19_bronze_ddl_matches_bronze_columns_and_is_append_only(table: str) -> None:
    ddl = catalog_setup.bronze_table_ddl(Settings(), table)
    assert "TBLPROPERTIES ('delta.appendOnly' = 'true')" in ddl
    declared = re.findall(r"^\s+`(\w+)` (\w+)", ddl, flags=re.MULTILINE)
    assert declared == [(n, t.upper()) for n, t in bronze.BRONZE_TABLES[table].items()]
    # Processing and transport columns start with an underscore; source header names are absent.
    for name, _ in declared:
        assert name not in {"LCLid", "tstp", "energy(kWh/hh)", "offset", "partition", "topic"}
