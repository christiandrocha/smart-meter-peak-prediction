"""Builders for Bronze test rows and fixtures (files, Kafka, households).

Rows follow the Bronze schemas of ``smart_meter_peak_prediction.bronze``. Timestamps are UTC.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

from pyspark.sql import DataFrame, SparkSession

from smart_meter_peak_prediction import bronze

T0 = datetime(2013, 1, 1, tzinfo=UTC)
INGESTED = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _ddl(columns: dict[str, str]) -> str:
    return ", ".join(f"`{name}` {kind}" for name, kind in columns.items())


def files_ts(moment: datetime) -> str:
    """Source text of a files-path timestamp (7 fractional digits, as in the Kaggle files)."""
    return f"{moment:%Y-%m-%d %H:%M:%S}.0000000"


def kafka_ts(moment: datetime) -> str:
    return f"{moment:%Y-%m-%dT%H:%M:%S}Z"


def file_row(
    household_id: str | None = "MAC000001",
    reading_ts_raw: str | None = None,
    energy_kwh_raw: str | None = " 0.5 ",
    *,
    moment: datetime = T0,
    source_file: str = "/Volumes/c/b/landing/readings/historical/readings_2013-01.csv",
    ingested_at: datetime = INGESTED,
    rescued: str | None = None,
) -> dict:
    return {
        "household_id": household_id,
        "reading_ts_raw": files_ts(moment) if reading_ts_raw is None else reading_ts_raw,
        "energy_kwh_raw": energy_kwh_raw,
        "_rescued_data": rescued,
        "_source_file": source_file,
        "_ingested_at": ingested_at,
    }


def kafka_payload(
    household_id: str | None = "MAC000001",
    reading_ts: str | None = None,
    energy_kwh: float | None = 0.5,
    *,
    moment: datetime = datetime(2013, 12, 1, tzinfo=UTC),
    source: str | None = "replay",
    produced_at: str | None = "2024-01-01T12:00:00.123456Z",
) -> str:
    event = {
        "household_id": household_id,
        "reading_ts": kafka_ts(moment) if reading_ts is None else reading_ts,
        "energy_kwh": energy_kwh,
        "source": source,
        "produced_at": produced_at,
    }
    return json.dumps({k: v for k, v in event.items() if v is not None or k == "energy_kwh"})


def kafka_row(
    payload: str | None = None,
    *,
    offset: int = 0,
    partition: int = 0,
    topic: str = "meter-readings",
    ingested_at: datetime = INGESTED,
    key: str | None = "MAC000001",
) -> dict:
    return {
        "kafka_key": key,
        "payload": kafka_payload() if payload is None else payload,
        "_topic": topic,
        "_partition": partition,
        "_offset": offset,
        "_kafka_timestamp": ingested_at,
        "_ingested_at": ingested_at,
    }


def household_row(
    household_id: str | None = "MAC000001",
    tariff: str | None = "Std",
    acorn_category: str | None = "ACORN-E",
    acorn_group: str | None = "Affluent",
    source_block: str | None = "block_0",
    *,
    ingested_at: datetime = INGESTED,
    source_file: str = "/Volumes/c/b/landing/households/households_sample.csv",
) -> dict:
    return {
        "household_id": household_id,
        "tariff_raw": tariff,
        "acorn_category_raw": acorn_category,
        "acorn_group_raw": acorn_group,
        "source_block_raw": source_block,
        "_rescued_data": None,
        "_source_file": source_file,
        "_ingested_at": ingested_at,
    }


def _frame(spark: SparkSession, rows: Sequence[dict], columns: dict[str, str]) -> DataFrame:
    data = [tuple(row.get(name) for name in columns) for row in rows]
    return spark.createDataFrame(data, schema=_ddl(columns))


def bronze_files(spark: SparkSession, rows: Iterable[dict] = ()) -> DataFrame:
    return _frame(spark, list(rows), bronze.FILES_READINGS_COLUMNS)


def bronze_kafka(spark: SparkSession, rows: Iterable[dict] = ()) -> DataFrame:
    return _frame(spark, list(rows), bronze.KAFKA_READINGS_COLUMNS)


def bronze_households(spark: SparkSession, rows: Iterable[dict] = ()) -> DataFrame:
    return _frame(spark, list(rows), bronze.FILES_HOUSEHOLDS_COLUMNS)


def half_hours(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(minutes=30 * i) for i in range(count)]


def day_rows(
    household_id: str,
    day: datetime,
    *,
    count: int = 48,
    energy: float = 0.25,
    source_file: str = "/Volumes/c/b/landing/readings/historical/readings_2013-01.csv",
    skip: Iterable[int] = (),
) -> list[dict]:
    """File rows for one UTC day: ``count`` consecutive slots from midnight, minus ``skip``."""
    skipped = set(skip)
    return [
        file_row(
            household_id,
            moment=moment,
            energy_kwh_raw=f" {energy} ",
            source_file=source_file,
        )
        for i, moment in enumerate(half_hours(day, count))
        if i not in skipped
    ]
