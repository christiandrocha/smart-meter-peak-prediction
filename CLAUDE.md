# Smart Meter Peak Prediction

> Entry point for coding agents. Read this file first. `AGENTS.md` points here.

## Project

Household-level consumption peak prediction on a Databricks lakehouse, with streaming ingestion and governed ML features

| Item | Value |
|---|---|
| Python package | `src/smart_meter_peak_prediction` |
| Tests | `tests/` (pytest) |
| Specs | `.claude/sdd/` |
| Decisions | `docs/adr/` |
| Conventions | `docs/conventions/` |

## How work is done here

This project follows Spec-Driven Development. Read `.claude/sdd/README.md`.

- New feature: `/brainstorm` -> `/define` -> `/design` -> `/build` -> `/ship`.
- Changing an approved spec: `/iterate`.
- Lasting decision: `/adr`.
- Environment uncertainty (network, limits, auth): a throwaway spike in `spikes/`, recorded in
  an ADR. Spike code is never imported by `src/`.

## Golden rules

1. No code without a DESIGN in status `Ready for Build`, except spikes.
2. No secrets in code, config, notebooks or commits. Use secret scopes or a local `.env`.
3. Every acceptance criterion `AC-NN` has a test, and every test that guards an AC names it.
4. Pipelines are idempotent: re-running with the same input produces the same output.
5. Time is UTC end to end. Event time and ingestion time are different columns.
6. Every phase document ends with a Self-Review: weak points, risks, trade-offs, next step.
7. Public-facing docs (README, ADRs, specs) are written in English and describe the system,
   not the author's learning process. Personal notes go in `notes/`, which git ignores.

## Commands

```bash
ruff check . && ruff format --check .   # lint
pytest                                  # tests
python scripts/check_specs.py           # SDD gates, AC traceability, ADRs, data contracts
python scripts/profile_data.py <files> --key ... --time ... --grid 30min \
    --out docs/profiling/<dataset>.md   # F-NN findings for BRAINSTORM
pre-commit run --all-files              # everything above plus hygiene hooks
```

## Enabled modules

Stack-specific agents and knowledge bases enabled by `scripts/init_project.py`.
Consult the module KB before designing or building anything in that stack.

<!-- modules:start -->
### databricks

Databricks lakehouse: Asset Bundles, Unity Catalog, Lakeflow pipelines, Auto Loader

- Deploy with `databricks bundle validate` then `databricks bundle deploy -t dev`.
- CI validates the bundle when the repository secrets `DATABRICKS_HOST` and `DATABRICKS_TOKEN` exist; without them the job is skipped with a notice.
- Read `.claude/kb/databricks/free-edition.md` before designing for Free Edition.
- Agents: `lakehouse-architect` (design), `pipeline-builder` (build).

### kafka

Apache Kafka producers and Spark Structured Streaming consumers

- Every topic has a contract in `docs/contracts/` (key, value schema, event time field).
- Bronze keeps the raw payload plus topic, partition and offset; Kafka is not the replay source.
- Agent: `streaming-engineer`.

### mlflow

MLflow tracking and Unity Catalog model registry, feature tables, ML data preparation

- Models are registered in Unity Catalog and promoted with aliases (`champion`, `challenger`), not stages.
- Training sets are point-in-time correct; every split is temporal.
- Agent: `ml-data-engineer`.
<!-- modules:end -->
