# Smart Meter Peak Prediction

Household-level consumption peak prediction on a Databricks lakehouse, with streaming ingestion and governed ML features

## Problem

<!-- One paragraph: who needs this, what it enables, what it costs without it. -->

## Architecture

<!-- Diagram and a short walkthrough of the data flow. Link the DESIGN documents. -->

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
cp .env.example .env   # fill in locally; never commit
pytest
```

## Repository layout

| Path | Content |
|---|---|
| `src/smart_meter_peak_prediction/` | Pipeline and feature logic (tested) |
| `tests/` | Unit and integration tests |
| `.claude/sdd/` | Feature specifications (brainstorm, define, design, build, ship) |
| `docs/adr/` | Architecture decision records |
| `docs/contracts/` | Data contracts |
| `docs/profiling/` | Data profiles of the sources |
| `spikes/` | Feasibility checks; not part of the product |

## Design decisions

See [`docs/adr/`](docs/adr/README.md).

## Known limitations & roadmap

<!-- What this version does not do, and what the next releases add. -->

## License

Released under the MIT License. See [LICENSE](LICENSE).
