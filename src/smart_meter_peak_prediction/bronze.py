"""Bronze ingestion library: Auto Loader and Kafka ``availableNow`` streams into append-only tables.

Bronze keeps every received row as raw text, under the names of the naming conventions
(``LCLid`` is ``household_id`` from here on, Q-06), plus transport metadata whose names start
with ``_``. It carries no quality rule. ``produced_at`` stays inside the raw Kafka ``payload``.

Failure handling (I-14, spike 03): a stream failure surfaces at notebook level and is not
caught by a ``try`` around ``awaitTermination``. ``run_available_now`` therefore has no
try/except; the job task timeout and retries are the failure policy (AC-10).

Credentials are passed in as arguments by the notebook (read with ``dbutils.secrets.get``).
Nothing here prints or logs option values, and error messages name options, never values.
"""

from __future__ import annotations

from collections.abc import Mapping

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.streaming import StreamingQuery
from pyspark.sql.types import StringType, StructField, StructType

from smart_meter_peak_prediction.config import Settings

RESCUED = "_rescued_data"

# Read schemas use the source header exactly (spike 01, A-02); renaming happens in the projection.
FILES_READINGS_SOURCE_SCHEMA = StructType(
    [StructField(name, StringType(), True) for name in ("LCLid", "tstp", "energy(kWh/hh)")]
)
FILES_HOUSEHOLDS_SOURCE_SCHEMA = StructType(
    [
        StructField(name, StringType(), True)
        for name in ("LCLid", "stdorToU", "Acorn", "Acorn_grouped", "file")
    ]
)

# Bronze table schemas (DEFINE inline schemas): column -> Spark SQL type.
FILES_READINGS_COLUMNS = {
    "household_id": "string",
    "reading_ts_raw": "string",
    "energy_kwh_raw": "string",
    "_rescued_data": "string",
    "_source_file": "string",
    "_ingested_at": "timestamp",
}
FILES_HOUSEHOLDS_COLUMNS = {
    "household_id": "string",
    "tariff_raw": "string",
    "acorn_category_raw": "string",
    "acorn_group_raw": "string",
    "source_block_raw": "string",
    "_rescued_data": "string",
    "_source_file": "string",
    "_ingested_at": "timestamp",
}
KAFKA_READINGS_COLUMNS = {
    "kafka_key": "string",
    "payload": "string",
    "_topic": "string",
    "_partition": "int",
    "_offset": "bigint",
    "_kafka_timestamp": "timestamp",
    "_ingested_at": "timestamp",
}
BRONZE_TABLES = {
    "files_meter_readings": FILES_READINGS_COLUMNS,
    "files_households": FILES_HOUSEHOLDS_COLUMNS,
    "kafka_meter_readings": KAFKA_READINGS_COLUMNS,
}


# ----------------------------------------------------------------------------- projections
def project_files_readings(df: DataFrame) -> DataFrame:
    """Source-header read (with ``_rescued_data`` and ``_metadata``) to the Bronze schema."""
    return df.select(
        F.col("LCLid").alias("household_id"),
        F.col("tstp").alias("reading_ts_raw"),
        F.col("`energy(kWh/hh)`").alias("energy_kwh_raw"),
        F.col(RESCUED).cast("string").alias(RESCUED),
        F.col("_metadata.file_path").alias("_source_file"),
        F.current_timestamp().alias("_ingested_at"),
    )


def project_files_households(df: DataFrame) -> DataFrame:
    return df.select(
        F.col("LCLid").alias("household_id"),
        F.col("stdorToU").alias("tariff_raw"),
        F.col("Acorn").alias("acorn_category_raw"),
        F.col("Acorn_grouped").alias("acorn_group_raw"),
        F.col("file").alias("source_block_raw"),
        F.col(RESCUED).cast("string").alias(RESCUED),
        F.col("_metadata.file_path").alias("_source_file"),
        F.current_timestamp().alias("_ingested_at"),
    )


def project_kafka(df: DataFrame) -> DataFrame:
    """Kafka source columns to Bronze: raw payload, `_`-prefixed transport metadata."""
    return df.select(
        F.col("key").cast("string").alias("kafka_key"),
        F.col("value").cast("string").alias("payload"),
        F.col("topic").alias("_topic"),
        F.col("partition").alias("_partition"),
        F.col("offset").alias("_offset"),
        F.col("timestamp").alias("_kafka_timestamp"),
        F.current_timestamp().alias("_ingested_at"),
    )


# ----------------------------------------------------------------------------- readers
def auto_loader_reader(spark: SparkSession, schema: StructType, path: str) -> DataFrame:
    """Auto Loader CSV stream with the source header, rescued data column and file metadata."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("rescuedDataColumn", RESCUED)
        .schema(schema)
        .load(path)
        .select("*", "_metadata")
    )


KAFKA_SECRET_KEYS = ("bootstrap_servers", "sasl_username", "sasl_password", "ca_pem")

# Bounded broker timeouts: a broker outage fails the task in minutes, not hours (AC-10).
KAFKA_TIMEOUT_OPTIONS = {
    "kafka.request.timeout.ms": "30000",
    "kafka.default.api.timeout.ms": "60000",
    "fetchOffset.numRetries": "3",
}
_SCRAM_LOGIN_MODULE = "kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule"


def _jaas_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def kafka_options(
    settings: Settings,
    *,
    bootstrap_servers: str,
    sasl_username: str,
    sasl_password: str,
    ca_pem: str,
) -> dict[str, str]:
    """Kafka source options (DESIGN, Kafka source options). Never print the result.

    Use ``redact_options`` for anything that is logged.
    """
    missing = [
        name
        for name, value in (
            ("bootstrap_servers", bootstrap_servers),
            ("sasl_username", sasl_username),
            ("sasl_password", sasl_password),
            ("ca_pem", ca_pem),
        )
        if not value
    ]
    if missing:
        raise ValueError("missing Kafka secret values: " + ", ".join(missing))
    jaas = (
        f'{_SCRAM_LOGIN_MODULE} required username="{_jaas_value(sasl_username)}" '
        f'password="{_jaas_value(sasl_password)}";'
    )
    return {
        "kafka.bootstrap.servers": bootstrap_servers,
        "subscribe": settings.kafka_topic,
        "startingOffsets": "earliest",
        "failOnDataLoss": "true",
        "kafka.security.protocol": "SASL_SSL",
        "kafka.sasl.mechanism": settings.kafka_sasl_mechanism,
        "kafka.sasl.jaas.config": jaas,
        "kafka.ssl.truststore.type": "PEM",
        "kafka.ssl.truststore.certificates": ca_pem,
        **KAFKA_TIMEOUT_OPTIONS,
    }


SENSITIVE_OPTIONS = (
    "kafka.bootstrap.servers",
    "kafka.sasl.jaas.config",
    "kafka.ssl.truststore.certificates",
)


def redact_options(options: Mapping[str, str]) -> dict[str, str]:
    """Copy of the options that is safe to log: secret-bearing values are replaced."""
    return {k: ("[REDACTED]" if k in SENSITIVE_OPTIONS else v) for k, v in options.items()}


def kafka_reader(spark: SparkSession, options: Mapping[str, str]) -> DataFrame:
    return spark.readStream.format("kafka").options(**options).load()


# ----------------------------------------------------------------------------- writer
def run_available_now(df: DataFrame, table: str, checkpoint: str) -> StreamingQuery:
    """Process what is available into ``table`` and stop (A-05).

    Append-only, exactly-once through the checkpoint: a rerun with no new input adds 0 rows
    (AC-06, AC-08). No try/except on purpose (I-14): let the task fail.
    """
    query = (
        df.writeStream.option("checkpointLocation", checkpoint)
        .trigger(availableNow=True)
        .toTable(table)
    )
    query.awaitTermination()
    return query
