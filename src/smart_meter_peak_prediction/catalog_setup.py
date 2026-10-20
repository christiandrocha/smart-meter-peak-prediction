"""Statements of the idempotent setup notebook (FR-17, NFR-09, ADR 0003).

Every statement is ``CREATE ... IF NOT EXISTS``, so the notebook can run as the first job task and
once by hand between the two first-time deploys (DA-06) with the same result. The Bronze tables
are created by explicit DDL and are append-only (``delta.appendOnly``). Names come from
``Settings``, so the main layout and the A-09 fallback layout use the same code.

The notebook ``notebooks/setup_catalog.py`` only executes what ``setup_statements`` returns; the
statement text is tested without a workspace.
"""

from __future__ import annotations

from smart_meter_peak_prediction.bronze import BRONZE_TABLES
from smart_meter_peak_prediction.config import (
    CHECKPOINTS_VOLUME,
    LANDING_VOLUME,
    LAYERS,
    Settings,
)


def bronze_table_ddl(settings: Settings, table: str) -> str:
    columns = BRONZE_TABLES[table]
    body = ",\n  ".join(f"`{name}` {sql_type.upper()}" for name, sql_type in columns.items())
    return (
        f"CREATE TABLE IF NOT EXISTS {settings.table('bronze', table)} (\n  {body}\n) "
        "TBLPROPERTIES ('delta.appendOnly' = 'true')"
    )


def setup_statements(settings: Settings) -> list[str]:
    """Catalog, schemas, Volumes and Bronze tables, in dependency order."""
    statements = [f"CREATE CATALOG IF NOT EXISTS {settings.catalog}"]
    statements += [
        f"CREATE SCHEMA IF NOT EXISTS {settings.qualified_schema(layer)}" for layer in LAYERS
    ]
    statements += [
        f"CREATE VOLUME IF NOT EXISTS {settings.qualified_schema('bronze')}.{volume}"
        for volume in (LANDING_VOLUME, CHECKPOINTS_VOLUME)
    ]
    statements += [bronze_table_ddl(settings, table) for table in BRONZE_TABLES]
    return statements
