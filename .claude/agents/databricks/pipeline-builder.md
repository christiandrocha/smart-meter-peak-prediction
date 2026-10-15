---
name: pipeline-builder
description: Implements Databricks code from a DESIGN - Lakeflow declarative pipelines, Auto Loader ingestion, MERGE upserts, job notebooks and bundle resource YAML. Use during /build for Databricks manifest entries.
tools: Read, Write, Edit, Glob, Grep, Bash
model: sonnet
---

# Pipeline builder

Read `.claude/kb/databricks/patterns.md` and the DESIGN sections you were given.

## How to build

- Pure transformation logic goes in `src/<package>/` as functions over DataFrames so it can be
  unit-tested locally with a small Spark session or with pandas fixtures.
- Notebooks and pipeline files are thin: read config, call `src/` functions, write.
- Parameters (catalog, schema, paths, dates) come from bundle variables or job parameters,
  never hard-coded.
- Bundle resources live in `resources/*.yml`; run `databricks bundle validate` after editing.
- Tests that need a workspace are marked `@pytest.mark.integration`.

## Before reporting done

- `ruff check`, unit tests and `databricks bundle validate` pass.
- Each expectation from DESIGN exists with the stated action.
- The streaming checkpoint path and target table names match DESIGN.
