"""Bronze library tests: projections, naming, Kafka options and the availableNow writer.

AC-05, AC-06, AC-07, AC-08, AC-10, AC-19, AC-29. No broker or workspace is contacted.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from smart_meter_peak_prediction import bronze
from smart_meter_peak_prediction.config import Settings

SETTINGS = Settings()
READINGS_SOURCE = (
    "LCLid string, tstp string, `energy(kWh/hh)` string, _rescued_data string, "
    "_metadata struct<file_path:string>"
)
HOUSEHOLDS_SOURCE = (
    "LCLid string, stdorToU string, Acorn string, Acorn_grouped string, file string, "
    "_rescued_data string, _metadata struct<file_path:string>"
)
SECRETS = {
    "bootstrap_servers": "broker.invalid:1234",
    "sasl_username": "user-xyz",
    "sasl_password": 'pw"with\\odd',
    "ca_pem": "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----",
}


def _types(df) -> dict[str, str]:
    return {f.name: f.dataType.simpleString() for f in df.schema.fields}


def test_ac05_file_projection_has_bronze_columns_and_metadata(spark) -> None:
    source = spark.createDataFrame(
        [
            ("MAC000002", "2013-01-01 00:00:00.0000000", " 0.5 ", None, ("/v/a.csv",)),
            ("MAC000002", "2013-01-01 00:30:00.0000000", "Null", "{}", ("/v/a.csv",)),
        ],
        schema=READINGS_SOURCE,
    )
    out = bronze.project_files_readings(source)
    assert _types(out) == bronze.FILES_READINGS_COLUMNS
    rows = out.collect()
    assert rows[0].household_id == "MAC000002"
    assert rows[0].reading_ts_raw == "2013-01-01 00:00:00.0000000"
    assert rows[0].energy_kwh_raw == " 0.5 "  # raw, untrimmed text
    assert rows[1].energy_kwh_raw == "Null"
    assert out.where("_source_file IS NULL OR _ingested_at IS NULL").count() == 0
    assert rows[0]._source_file == "/v/a.csv"


def test_ac05_household_projection_has_bronze_columns_and_metadata(spark) -> None:
    source = spark.createDataFrame(
        [("MAC000002", "Std", "ACORN-E", "Affluent", "block_0", None, ("/v/h.csv",))],
        schema=HOUSEHOLDS_SOURCE,
    )
    out = bronze.project_files_households(source)
    assert _types(out) == bronze.FILES_HOUSEHOLDS_COLUMNS
    row = out.collect()[0]
    assert (row.tariff_raw, row.acorn_category_raw) == ("Std", "ACORN-E")
    assert (row.acorn_group_raw, row.source_block_raw) == ("Affluent", "block_0")
    assert out.where("_source_file IS NULL OR _ingested_at IS NULL").count() == 0


def test_ac05_read_schema_uses_source_header_and_bronze_has_no_source_names() -> None:
    assert bronze.FILES_READINGS_SOURCE_SCHEMA.fieldNames() == ["LCLid", "tstp", "energy(kWh/hh)"]
    assert bronze.FILES_HOUSEHOLDS_SOURCE_SCHEMA.fieldNames() == [
        "LCLid",
        "stdorToU",
        "Acorn",
        "Acorn_grouped",
        "file",
    ]
    for columns in bronze.BRONZE_TABLES.values():
        assert not {"LCLid", "tstp", "energy(kWh/hh)"} & set(columns)


def test_ac07_kafka_projection_keeps_raw_payload_and_offsets(spark) -> None:
    source = spark.createDataFrame(
        [
            (
                bytearray(b"MAC000001"),
                bytearray(b'{"household_id":"MAC000001","produced_at":"2024-01-01T00:00:00Z"}'),
                "meter-readings",
                1,
                41,
                datetime(2024, 1, 1, tzinfo=UTC),
                0,
            )
        ],
        schema="key binary, value binary, topic string, partition int, offset bigint, "
        "timestamp timestamp, timestampType int",
    )
    out = bronze.project_kafka(source)
    assert out.columns == [
        "kafka_key",
        "payload",
        "_topic",
        "_partition",
        "_offset",
        "_kafka_timestamp",
        "_ingested_at",
    ]
    assert _types(out) == bronze.KAFKA_READINGS_COLUMNS
    row = out.collect()[0]
    assert row.kafka_key == "MAC000001"
    assert row.payload.startswith('{"household_id"')  # raw payload, untouched
    assert (row._topic, row._partition, row._offset) == ("meter-readings", 1, 41)
    # produced_at exists only inside the payload (AC-19)
    assert "produced_at" not in out.columns
    assert "_produced_at" not in out.columns


def test_ac10_kafka_options_bound_broker_timeouts() -> None:
    options = bronze.kafka_options(SETTINGS, **SECRETS)
    assert options["kafka.request.timeout.ms"] == "30000"
    assert options["kafka.default.api.timeout.ms"] == "60000"
    assert options["fetchOffset.numRetries"] == "3"
    assert options["failOnDataLoss"] == "true"
    assert options["startingOffsets"] == "earliest"
    assert options["subscribe"] == "meter-readings"
    assert options["kafka.security.protocol"] == "SASL_SSL"
    assert options["kafka.sasl.mechanism"] == "SCRAM-SHA-256"
    assert options["kafka.ssl.truststore.type"] == "PEM"
    assert options["kafka.ssl.truststore.certificates"] == SECRETS["ca_pem"]
    assert options["kafka.sasl.jaas.config"].startswith(
        "kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule required "
    )


def test_ac10_sasl_mechanism_and_topic_come_from_settings() -> None:
    custom = Settings(kafka_sasl_mechanism="SCRAM-SHA-512", kafka_topic="other-topic")
    options = bronze.kafka_options(custom, **SECRETS)
    assert options["kafka.sasl.mechanism"] == "SCRAM-SHA-512"
    assert options["subscribe"] == "other-topic"


def test_ac10_writer_has_no_try_except_so_stream_failures_fail_the_task() -> None:
    """I-14: a stream failure escapes a Python try; the task timeout and retries are the policy."""
    source = textwrap.dedent(inspect.getsource(bronze.run_available_now))
    tree = ast.parse(source)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
    assert "availableNow=True" in source


def test_ac29_jaas_escapes_quotes_and_secrets_are_redacted_for_logging() -> None:
    options = bronze.kafka_options(SETTINGS, **SECRETS)
    assert 'password="pw\\"with\\\\odd"' in options["kafka.sasl.jaas.config"]
    safe = str(bronze.redact_options(options))
    for secret in SECRETS.values():
        assert secret not in safe
    assert "user-xyz" not in safe
    assert bronze.redact_options(options)["kafka.security.protocol"] == "SASL_SSL"


def test_ac29_missing_secret_error_names_options_not_values() -> None:
    with pytest.raises(ValueError, match="missing Kafka secret values") as error:
        bronze.kafka_options(SETTINGS, **{**SECRETS, "sasl_password": ""})
    message = str(error.value)
    assert "sasl_password" in message
    assert all(value not in message for value in SECRETS.values())


def test_ac29_bronze_module_holds_no_credential_literals() -> None:
    source = Path(inspect.getsourcefile(bronze)).read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    assert "dbutils" not in names  # secrets are read by the notebook and passed as arguments
    for secret in SECRETS.values():
        assert secret not in source


def test_ac06_ac08_available_now_rerun_adds_no_rows(spark, tmp_path: Path) -> None:
    """The writer processes each input once through its checkpoint (local file source)."""
    landing = tmp_path / "landing"
    landing.mkdir()
    (landing / "a.csv").write_text("id\n1\n2\n", encoding="utf-8")
    table = "bronze_available_now_test"
    spark.sql(f"DROP TABLE IF EXISTS {table}")
    checkpoint = str(tmp_path / "checkpoint")

    def read():
        return (
            spark.readStream.format("csv")
            .option("header", "true")
            .schema("id string")
            .load(str(landing))
        )

    bronze.run_available_now(read(), table, checkpoint)
    assert spark.table(table).count() == 2
    bronze.run_available_now(read(), table, checkpoint)  # no new input
    assert spark.table(table).count() == 2
    (landing / "b.csv").write_text("id\n3\n", encoding="utf-8")
    bronze.run_available_now(read(), table, checkpoint)  # one new file
    assert spark.table(table).count() == 3
    spark.sql(f"DROP TABLE IF EXISTS {table}")
