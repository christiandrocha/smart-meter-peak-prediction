# 0003. Unity Catalog layout `smart_meter_dev` created by an idempotent setup task

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-15 |
| **Deciders** | Christian |
| **Related** | METER_INGESTION; FR-17, NFR-09; AC-19, AC-28, AC-32; Q-05; ADR 0001 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

Q-05 fixed the layout: catalog `smart_meter_dev` with schemas `bronze`, `silver`, `gold` and `ml`
(empty, for PEAK_MODEL), Volumes `landing` and `checkpoints` in `bronze`; `prod` is documented as a
catalog variable override only. If Free Edition does not allow creating the catalog (A-09), the
fallback is `workspace.smart_meter_dev_<layer>`. The open design item OD-05 is how these objects
are created. Asset Bundle development mode prepends `[dev <user>]` to resources that are not files
or notebooks, and bundle-managed schemas get a name prefix in development mode, which would break
the fixed names that the data contracts and PEAK_MODEL rely on. Catalogs are not a bundle resource
the design can rely on. Free Edition accounts can be deleted, so the layout must be rebuildable
from the repository (NFR-09).

## Decision drivers

- Exact, stable names for the interface tables (contracts in `docs/contracts/`).
- Same code path for the main layout and the A-09 fallback.
- Idempotent: re-running creation changes nothing.
- `databricks bundle destroy` must not drop data.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Setup notebook task (`CREATE ... IF NOT EXISTS`) as first task of the daily job, names from bundle variables** | Exact names in development mode; one code path for both layouts; also creates the Bronze tables with explicit DDL; destroy keeps data | Objects are not tracked as bundle resources; the first deploy needs the catalog to exist before the pipeline is created (DA-06 failed), so a fresh workspace needs deploy, one manual setup run, deploy |
| Bundle `schemas` and `volumes` resources | Declarative; removed by destroy | Name prefix in development mode; catalog itself still needs another mechanism; destroy drops data |
| Manual creation in the UI | Nothing to build | Not reproducible (NFR-09); undocumented drift |

## Decision

We will create the catalog, the four schemas, the two Volumes, the three Bronze tables and the
event log schema with an idempotent setup notebook (`notebooks/setup_catalog.py`) that runs as the
first task of the daily job. Because terraform creates the pipeline in the same apply as the job and
fails when the catalog is absent (DA-06, ADR 0001), the job task cannot help on the very first
deploy. On a fresh workspace the order is: (1) `databricks bundle deploy -t dev` (files sync, pipeline
creation fails), (2) run `notebooks/setup_catalog.py` once from the synced bundle files, (3) deploy
again. Later deploys are a single deploy. Catalog and schema names come from bundle variables `catalog`,
`bronze_schema`, `silver_schema`, `gold_schema` and `ml_schema` (defaults `smart_meter_dev`,
`bronze`, `silver`, `gold`, `ml`). If A-09 fails, the `dev` target overrides them to `workspace`
and `smart_meter_dev_bronze`, `smart_meter_dev_silver`, `smart_meter_dev_gold`,
`smart_meter_dev_ml`, and this record is updated to say so; no code changes. Jobs and pipelines
keep the development-mode display prefix; their base names follow `smart_meter_<purpose>`.

## Consequences

- **Positive:** Contract names hold in development mode; the fallback is a variable override;
  rebuilding a deleted workspace is deploy, one setup notebook run, deploy, then a job run.
- **Negative:** Schemas and Volumes are not removed by `bundle destroy` (intended, but manual
  cleanup is needed to start from zero); a later `prod` target needs its own catalog variable.
- **What would make us revisit this:** Bundles gaining an option to keep exact schema and catalog
  names in development mode, or a second environment being deployed.
