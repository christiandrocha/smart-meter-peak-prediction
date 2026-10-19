"""Library output schemas equal the data contracts; naming rule without exceptions (AC-19).

Covers the Bronze projections, the evaluation table (contract 30a), Silver, the quarantine,
households and Gold. Names and types are compared in order; contract columns that are not
nullable must hold no null on a mixed fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from support import builders as b
from support.harness import build_update

from smart_meter_peak_prediction import bronze, silver

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "contracts"
SOURCE_NAMES = {"LCLid", "tstp", "energy(kWh/hh)"}
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
# Inline Bronze schemas of DEFINE_METER_INGESTION.md (Data Contracts, Inline schemas).
INLINE_BRONZE = {
    "files_meter_readings": {
        "household_id": "string",
        "reading_ts_raw": "string",
        "energy_kwh_raw": "string",
        "_rescued_data": "string",
        "_source_file": "string",
        "_ingested_at": "timestamp",
    },
    "kafka_meter_readings": {
        "kafka_key": "string",
        "payload": "string",
        "_topic": "string",
        "_partition": "int",
        "_offset": "bigint",
        "_kafka_timestamp": "timestamp",
        "_ingested_at": "timestamp",
    },
    "files_households": {
        "household_id": "string",
        "tariff_raw": "string",
        "acorn_category_raw": "string",
        "acorn_group_raw": "string",
        "source_block_raw": "string",
        "_rescued_data": "string",
        "_source_file": "string",
        "_ingested_at": "timestamp",
    },
}


def contract(name: str) -> dict:
    return yaml.safe_load((CONTRACTS / f"{name}.yaml").read_text(encoding="utf-8"))


def contract_columns(name: str) -> list[tuple[str, str]]:
    return [(c["name"], c["type"]) for c in contract(name)["schema"]]


def schema_of(df) -> list[tuple[str, str]]:
    return [(f.name, f.dataType.simpleString()) for f in df.schema.fields]


@pytest.fixture(scope="module")
def outputs(spark):
    files, kafka = b.mixed_fixture()
    households = [b.household_row("MAC000001"), b.household_row("MAC000002", "ToU")]
    files += b.day_rows("MAC000003", b.T_FILES, count=10, source_file="/v/other.csv")
    update = build_update(spark, files, kafka, households)
    return {
        "silver_meter_readings_evaluated": update.evaluated,
        "silver_meter_readings": update.silver,
        "silver_meter_readings_quarantine": update.quarantine,
        "silver_households": update.households,
        "gold_household_daily_consumption": update.daily,
        "gold_household_data_quality_monthly": update.monthly,
        "gold_household_data_quality": update.summary(),
    }


CONTRACT_NAMES = [
    "silver_meter_readings_evaluated",
    "silver_meter_readings",
    "silver_meter_readings_quarantine",
    "silver_households",
    "gold_household_daily_consumption",
    "gold_household_data_quality_monthly",
    "gold_household_data_quality",
]


@pytest.mark.parametrize("name", CONTRACT_NAMES)
def test_ac19_output_schemas_match_contracts(outputs, name) -> None:
    assert schema_of(outputs[name]) == contract_columns(name)


@pytest.mark.parametrize("name", CONTRACT_NAMES)
def test_ac19_non_nullable_contract_columns_hold_no_null(outputs, name) -> None:
    df = outputs[name]
    assert df.count() > 0
    for column in contract(name)["schema"]:
        if column["nullable"] is False:
            assert df.where(f"`{column['name']}` IS NULL").count() == 0, column["name"]


def test_ac19_bronze_schemas_equal_inline_definitions() -> None:
    assert bronze.BRONZE_TABLES == INLINE_BRONZE


def test_ac19_evaluated_contract_documents_the_data_model_and_is_ops_only() -> None:
    evaluated = contract("silver_meter_readings_evaluated")
    assert evaluated["primary_key"] == ["_source_ref"]
    assert evaluated["object_type"].startswith("materialized view")
    assert "not for PEAK_MODEL" in evaluated["audience"]
    assert [c for c, _ in contract_columns("silver_meter_readings_evaluated")] == (
        silver.EVALUATED_COLUMNS
    )


def test_ac19_kafka_value_schema_fields_equal_the_topic_contract() -> None:
    topic = contract("meter-readings")
    fields = [c["name"] for c in topic["value"]["schema"]]
    parsed = [part.split()[0] for part in silver.KAFKA_VALUE_SCHEMA.split(",") if part.strip()]
    assert parsed == [*fields, "_corrupt_record"]


def _all_columns(outputs) -> dict[str, list[str]]:
    columns = {name: [c for c, _ in schema_of(df)] for name, df in outputs.items()}
    columns.update({f"bronze.{t}": list(cols) for t, cols in bronze.BRONZE_TABLES.items()})
    return columns


def test_ac19_no_source_column_names_and_processing_columns_prefixed(outputs) -> None:
    for table, columns in _all_columns(outputs).items():
        assert not SOURCE_NAMES & set(columns), table
        assert not PROCESSING_NAMES & set(columns), f"{table}: processing column without _"
    # every contract file follows the same rule, whether or not the library produces it
    for path in sorted(CONTRACTS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = (
            (data.get("value") or {}).get("schema") if data["kind"] == "topic" else data["schema"]
        )
        names = {c["name"] for c in schema}
        if data["kind"] == "table":
            assert not SOURCE_NAMES & names, path.name
            assert not PROCESSING_NAMES & names, path.name


def test_ac19_underscore_columns_cover_the_documented_list(outputs) -> None:
    present = {c for cols in _all_columns(outputs).values() for c in cols if c.startswith("_")}
    expected = {
        "_ingested_at",
        "_ingestion_path",
        "_source_ref",
        "_source_file",
        "_rescued_data",
        "_topic",
        "_partition",
        "_offset",
        "_kafka_timestamp",
        "_produced_at",
    }
    assert expected <= present
    assert all(re.fullmatch(r"_[a-z_]+", c) for c in present)
    # kafka_key and payload keep their names; produced_at exists only inside the payload
    assert {"kafka_key", "payload"} <= set(bronze.KAFKA_READINGS_COLUMNS)
    assert "produced_at" not in present
