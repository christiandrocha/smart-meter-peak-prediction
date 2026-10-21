"""Table DDL of the peak model feature (FR-18, FR-21, FR-29, AC-64).

Every statement is ``CREATE TABLE IF NOT EXISTS``, so a notebook can run it on every start with the
same result. The catalog and the schemas belong to METER_INGESTION (ADR 0003): PEAK_MODEL only
checks that they exist (``require_schemas``) and never creates them.

The feature table is not created here: it is created by the Feature Engineering client with a
time-series column (``registry.ensure_feature_table``), from ``feature_table_schema``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DataType,
    DateType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from smart_meter_peak_prediction import features, labels, scoring, weather
from smart_meter_peak_prediction.config import LAYERS, Settings
from smart_meter_peak_prediction.delta_sync import set_properties_sql
from smart_meter_peak_prediction.peak_config import (
    bronze_weather_table,
    features_table,
    labels_table,
    predictions_table,
    silver_weather_table,
)

RETENTION_DAYS = 90
RETENTION_PROPERTIES = {
    "delta.logRetentionDuration": f"interval {RETENTION_DAYS} days",
    "delta.deletedFileRetentionDuration": f"interval {RETENTION_DAYS} days",
}
SPARK_TYPES: dict[str, DataType] = {
    "string": StringType(),
    "date": DateType(),
    "double": DoubleType(),
    "int": IntegerType(),
    "boolean": BooleanType(),
    "timestamp": TimestampType(),
    "array<string>": ArrayType(StringType(), containsNull=False),
}


def create_table_sql(
    table: str,
    columns: Mapping[str, str],
    not_null: Collection[str] = (),
    properties: Mapping[str, str] | None = None,
) -> str:
    """``CREATE TABLE IF NOT EXISTS`` with explicit columns and optional table properties."""
    body = ",\n  ".join(
        f"`{name}` {sql_type.upper()}{' NOT NULL' if name in not_null else ''}"
        for name, sql_type in columns.items()
    )
    sql = f"CREATE TABLE IF NOT EXISTS {table} (\n  {body}\n)"
    if properties:
        props = ", ".join(f"'{k}' = '{v}'" for k, v in properties.items())
        sql += f" TBLPROPERTIES ({props})"
    return sql


def bronze_weather_ddl(settings: Settings) -> str:
    """Append-only Bronze table (FR-18)."""
    return create_table_sql(
        bronze_weather_table(settings),
        weather.BRONZE_COLUMNS,
        properties={"delta.appendOnly": "true"},
    )


def silver_weather_ddl(settings: Settings) -> str:
    return create_table_sql(
        silver_weather_table(settings),
        weather.SILVER_COLUMNS,
        not_null=("weather_ts", "temperature_c"),
    )


def labels_ddl(settings: Settings) -> str:
    """Label and eligibility table with 90-day history retention (ADR 0011)."""
    return create_table_sql(
        labels_table(settings),
        labels.LABEL_COLUMNS,
        not_null=labels.NOT_NULL_COLUMNS,
        properties=RETENTION_PROPERTIES,
    )


def predictions_ddl(settings: Settings) -> str:
    return create_table_sql(
        predictions_table(settings),
        scoring.PREDICTION_COLUMNS,
        not_null=tuple(scoring.PREDICTION_COLUMNS),
    )


def feature_retention_sql(settings: Settings) -> str:
    """History retention of the feature table, applied after ``fe.create_table`` (ADR 0011)."""
    return set_properties_sql(features_table(settings), RETENTION_PROPERTIES)


def feature_table_schema() -> StructType:
    """Schema for ``fe.create_table`` (the contract's nullability)."""
    return StructType(
        [
            StructField(name, SPARK_TYPES[sql_type], nullable=name not in features.NOT_NULL_COLUMNS)
            for name, sql_type in features.FEATURE_TABLE_COLUMNS.items()
        ]
    )


def setup_statements(settings: Settings) -> list[str]:
    """Statements for the four plain Delta tables, in dependency order."""
    return [
        bronze_weather_ddl(settings),
        silver_weather_ddl(settings),
        labels_ddl(settings),
        predictions_ddl(settings),
    ]


def require_schemas(spark: SparkSession, settings: Settings) -> None:
    """Precondition: the catalog and every layer schema exist (created by METER_INGESTION)."""
    rows = spark.sql(f"SHOW SCHEMAS IN {settings.catalog}").collect()
    existing = {row[0] for row in rows}
    missing = [settings.schema(layer) for layer in LAYERS if settings.schema(layer) not in existing]
    if missing:
        raise RuntimeError(
            f"schema(s) {', '.join(missing)} missing in catalog {settings.catalog}: "
            "deploy and run METER_INGESTION setup first (ADR 0003)"
        )


def ensure_tables(spark: SparkSession, settings: Settings) -> list[str]:
    """Check the precondition, then run the DDL. Returns the statements that ran."""
    require_schemas(spark, settings)
    statements = setup_statements(settings)
    for statement in statements:
        spark.sql(statement)
    return statements
