"""Typed settings for the meter ingestion feature (FR-16, FR-17).

One ``Settings`` object carries catalog and schema names, Volume names, the study period, the
Kafka cutoff, the topic and the secret scope. It is built from job parameters (notebooks) or
from the pipeline configuration (keys prefixed ``smart_meter.``). Fully qualified names work for
the main layout (catalog ``smart_meter_dev``) and for the A-09 fallback (``workspace`` with
schemas ``smart_meter_dev_<layer>``, ADR 0003) by changing values only.

All times are UTC. Time literals are rendered with an explicit ``+00:00`` offset, so they do not
depend on the session time zone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta

PIPELINE_PREFIX = "smart_meter."
DEFAULT_CATALOG = "smart_meter_dev"
LAYERS = ("bronze", "silver", "gold", "ml")
LANDING_VOLUME = "landing"
CHECKPOINTS_VOLUME = "checkpoints"

BRONZE_FILES_READINGS = "files_meter_readings"
BRONZE_FILES_HOUSEHOLDS = "files_households"
BRONZE_KAFKA_READINGS = "kafka_meter_readings"


def parse_utc(value: str | datetime | date) -> datetime:
    """Parse an ISO date or timestamp as UTC (naive values are taken as UTC)."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text.replace(" ", "T", 1))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def timestamp_sql(value: datetime) -> str:
    """Spark SQL timestamp literal for a UTC instant, independent of the session time zone."""
    utc = value.astimezone(UTC)
    return f"CAST('{utc:%Y-%m-%d %H:%M:%S}+00:00' AS TIMESTAMP)"


@dataclass(frozen=True)
class Settings:
    catalog: str = DEFAULT_CATALOG
    bronze_schema: str = "bronze"
    silver_schema: str = "silver"
    gold_schema: str = "gold"
    ml_schema: str = "ml"
    study_start: str = "2012-07-01"
    study_end: str = "2014-02-28"
    cutoff: str = "2013-12-01T00:00:00Z"
    kafka_topic: str = "meter-readings"
    kafka_sasl_mechanism: str = "SCRAM-SHA-256"
    secret_scope: str = "smart_meter"  # noqa: S105  (scope name, not a secret)

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_mapping(cls, values: Mapping[str, str], prefix: str = "") -> Settings:
        """Build settings from a mapping; unknown keys are ignored, missing keys use defaults.

        ``prefix`` selects the namespace of the pipeline configuration (``smart_meter.``).
        Job parameters use the bare field names (prefix ``""``).
        """
        known = {f.name for f in fields(cls)}
        unknown = [
            key
            for key in values
            if key.startswith(prefix) and prefix and key[len(prefix) :] not in known
        ]
        if unknown:
            raise ValueError("unknown settings key(s): " + ", ".join(sorted(unknown)))
        picked = {
            key[len(prefix) :]: str(value)
            for key, value in values.items()
            if key.startswith(prefix) and key[len(prefix) :] in known and str(value) != ""
        }
        return cls(**picked)

    @classmethod
    def from_pipeline_configuration(cls, values: Mapping[str, str]) -> Settings:
        return cls.from_mapping(values, prefix=PIPELINE_PREFIX)

    @classmethod
    def fallback_layout(cls, catalog: str = "workspace", base: str = "smart_meter_dev") -> Settings:
        """A-09 fallback: one schema per layer named ``<base>_<layer>`` in an existing catalog."""
        return cls(
            catalog=catalog,
            bronze_schema=f"{base}_bronze",
            silver_schema=f"{base}_silver",
            gold_schema=f"{base}_gold",
            ml_schema=f"{base}_ml",
        )

    def to_pipeline_configuration(self) -> dict[str, str]:
        return {PIPELINE_PREFIX + f.name: getattr(self, f.name) for f in fields(self)}

    # ------------------------------------------------------------------ period and cutoff
    @property
    def study_start_ts(self) -> datetime:
        return parse_utc(self.study_start)

    @property
    def study_end_exclusive_ts(self) -> datetime:
        """First instant after the study period: ``study_end`` + 1 day, 00:00 UTC."""
        return parse_utc(self.study_end) + timedelta(days=1)

    @property
    def cutoff_ts(self) -> datetime:
        return parse_utc(self.cutoff)

    @property
    def study_start_sql(self) -> str:
        return timestamp_sql(self.study_start_ts)

    @property
    def study_end_exclusive_sql(self) -> str:
        return timestamp_sql(self.study_end_exclusive_ts)

    @property
    def cutoff_sql(self) -> str:
        return timestamp_sql(self.cutoff_ts)

    @property
    def study_start_date_sql(self) -> str:
        return f"DATE'{self.study_start_ts:%Y-%m-%d}'"

    @property
    def study_end_date_sql(self) -> str:
        return f"DATE'{parse_utc(self.study_end):%Y-%m-%d}'"

    # ------------------------------------------------------------------ names
    def schema(self, layer: str) -> str:
        if layer not in LAYERS:
            raise ValueError(f"unknown layer '{layer}', expected one of {', '.join(LAYERS)}")
        return getattr(self, f"{layer}_schema")

    def qualified_schema(self, layer: str) -> str:
        return f"{self.catalog}.{self.schema(layer)}"

    def table(self, layer: str, name: str) -> str:
        return f"{self.qualified_schema(layer)}.{name}"

    @property
    def bronze_files_readings(self) -> str:
        return self.table("bronze", BRONZE_FILES_READINGS)

    @property
    def bronze_files_households(self) -> str:
        return self.table("bronze", BRONZE_FILES_HOUSEHOLDS)

    @property
    def bronze_kafka_readings(self) -> str:
        return self.table("bronze", BRONZE_KAFKA_READINGS)

    def volume_path(self, volume: str, *parts: str) -> str:
        base = f"/Volumes/{self.catalog}/{self.bronze_schema}/{volume}"
        return "/".join([base, *[p.strip("/") for p in parts if p]])

    @property
    def landing_readings_path(self) -> str:
        return self.volume_path(LANDING_VOLUME, "readings", "historical")

    @property
    def landing_households_path(self) -> str:
        return self.volume_path(LANDING_VOLUME, "households")

    def checkpoint(self, stream: str) -> str:
        return self.volume_path(CHECKPOINTS_VOLUME, stream)
