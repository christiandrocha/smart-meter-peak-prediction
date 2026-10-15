# BUILD REPORT: Meter Ingestion

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | METER_INGESTION |
| **Date** | 2026-10-15 |
| **Source** | DESIGN_METER_INGESTION.md |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

---

## Summary

This report covers **PR 1 (manifest entries 1 to 23), local entries only**. The local sampling port, CLI, producer, Docker files, plan, pyproject and `.env.example` changes, A-08 check and their tests are done and verified against `data/raw`. The Databricks and Kafka spikes (00 to 04) are written but not run, because the CLI profiles are expired and no credentials are available; ADR 0001 keeps them Pending. PR 2a, 2b and 3 are not started: PR 2 is gated on the spike results recorded in ADR 0001, with `/iterate` for any failure.

---

## Files Changed

State legend: done, written-not-run, partial, not started.

| # | PR | File | Action | State and verification |
|---|---|---|---|---|
| 1 | PR 1 | spikes/local/a08_offgrid_null_cooccurrence.py | Created | done: Ran on data/raw: A-08 PASS (see AC-11) |
| 2 | PR 1 | spikes/databricks/00_setup_catalog.py | Created | written-not-run: py_compile; not executed (no credentials) |
| 3 | PR 1 | spikes/databricks/01_spike_autoloader.py | Created | written-not-run: py_compile; not executed |
| 4 | PR 1 | spikes/databricks/02_spike_kafka_consume.py | Created | written-not-run: py_compile; not executed |
| 5 | PR 1 | spikes/databricks/03_spike_kafka_unreachable.py | Created | written-not-run: py_compile; not executed |
| 6 | PR 1 | spikes/databricks/04_spike_lakeflow_pipeline/pipeline.py | Created | written-not-run: py_compile; not executed (needs the `dlt` runtime) |
| 7 | PR 1 | spikes/databricks/04_spike_lakeflow_pipeline/summary_view.sql | Created | written-not-run: not executed |
| 8 | PR 1 | spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py | Created | written-not-run: py_compile; SDK calls unverified against a live workspace |
| 9 | PR 1 | docs/adr/0001-runtime-environment-constraints.md | Modified | partial: Added the A-08 row (Pass). Spike results for A-02, A-03, A-05, A-06, A-09, A-10, DA-xx stay Pending with the pass criteria intact |
| 10 | PR 1 | docs/spikes/README.md | Modified | partial: Rows for the sampling spike and A-08 (Pass); spikes 00 to 04 recorded as Pending (written, not run) |
| 11 | PR 1 | docs/adr/0002 to 0006 (conditional) | - | not started: No spike outcome exists yet, so nothing to adjust |
| 12 | PR 1 | pyproject.toml | Modified | done: Extras sample, producer, integration; dev adds pyspark and keeps pyyaml; markers integration and local_data; addopts excludes both. |
| 13 | PR 1 | `.env.example` | Modified | done: Placeholders KAFKA_TOPIC, REPLAY_SPEED, SAMPLE_STREAM_FILE, DATABRICKS_WAREHOUSE_ID, no values |
| 14 | PR 1 | config/sample_plan.json | Created | done: Loaded by tests; recomputed blocks equal it (local_data test) |
| 15 | PR 1 | src/smart_meter_peak_prediction/sampling.py | Created | done: ruff; tests/test_sampling.py; local_data tests; outputs byte-identical to pinned checksums |
| 16 | PR 1 | scripts/prepare_sample.py | Created | done: ruff; CLI run on data/raw; tests/test_sampling.py |
| 17 | PR 1 | src/smart_meter_peak_prediction/producer.py | Created | done: ruff; tests/test_producer.py; `--dry-run` over the real stream file (247,569 events). No broker contacted |
| 18 | PR 1 | docker/producer/Dockerfile | Created | written-not-run: Not built: docker build is the user's step (see Pending on the user) |
| 19 | PR 1 | .dockerignore | Created | done: Reviewed by hand; excludes .env, data/, *.pem, .git |
| 20 | PR 1 | tests/test_sampling.py | Created | done: 11 passed |
| 21 | PR 1 | tests/local_data/test_sample_seed42.py | Created | done: `pytest -m local_data`: 6 passed against data/raw |
| 22 | PR 1 | tests/test_producer.py | Created | done: 13 passed |
| 23 | PR 1 | tests/test_runtime_adr.py | Created | done (1 red by design): check_specs test passes; the ADR-results test fails until the user records spike results |

PR 2a (entries 24 to 42), PR 2b (entries 43 to 52) and PR 3 (entries 53 to 60): **not started**.

---

## Acceptance Criteria Evidence

Evidence collected for PR 1. "Not started" means the criterion belongs to a later PR.

| AC | Result | Evidence |
|---|---|---|
| AC-01 | Pass (PR 1 scope) | `pytest tests/test_sampling.py`: test_ac01_* pass. `pytest -m local_data`: test_ac01_seed42_reruns_are_byte_identical and test_ac01_plan_recomputed_from_raw_equals_committed_plan pass; data-file SHA-256 equal `config/sample_manifest.json`; household CSV byte-equal `config/sample_households.csv` |
| AC-02 | Pass (PR 1 scope) | test_ac02_* (unit, 2 tests) and local_data test_ac02_src_sampling_selects_exactly_the_pinned_households and test_ac02_src_sampling_counts_match_pinned_manifest pass: 60 households, 20 per group, 16 Std and 4 ToU per group, exclusions equal the pinned list |
| AC-03 | Pass (PR 1 scope) | test_ac03_* (unit, 2 tests) and local_data test_ac03_seed42_split_counts_match_pinned_manifest pass: 1,432,405 historical and 247,569 stream rows, per-file rows and checksums equal the pinned manifest |
| AC-04 | Pass (PR 1 scope) | test_ac04_* (unit, 2 tests) and local_data test_ac04_seed42_cutoff_2013_11_01_preserves_total pass. Bundle-variable half (AC-28) is PR 2b |
| AC-05 | Not started | PR 2a/2b/3 (Bronze projections and integration) |
| AC-06 | Not started | PR 3 (integration) |
| AC-07 | Partial | Producer half passes: test_ac07_* in tests/test_producer.py (event matches the topic contract, Null energy becomes null with no row dropped, ordering, keys, delivery errors). Bronze projection and integration tests are PR 2a/3. Kafka consumption is spike 02 (written, not run) |
| AC-08 | Not started | PR 3 (integration) |
| AC-09 | Not started | PR 2a/3 (harness and integration) |
| AC-10 | Not run | Spike 03 written, not run. User command: see Pending on the user. Unit/bundle tests are PR 2a/2b |
| AC-11 | Partial | A-08 PASS on data/raw (`.venv/bin/python spikes/local/a08_offgrid_null_cooccurrence.py`): 9 blocks, 13,059,525 rows, 450 off-grid = 450 non-numeric = 450 in both; seed-42 sample in the study period: 1,679,974 rows, 60 off-grid, 60 non-numeric, 60 in both. So 60 quarantined and 1,679,914 in Silver hold. Reconciliation tests are PR 2a/3 |
| AC-12 | Not started | PR 2a/2b/3; DA-01 is spike 04 (written, not run) |
| AC-13 | Not started | PR 2a/3 |
| AC-14 | Not started | PR 2a/3 |
| AC-15 | Not run | Spike 04 `run_spike.py` (expect_or_fail abort) written, not run. Unit tests are PR 2a |
| AC-16 | Not started | PR 2a |
| AC-17 | Not started | PR 2a |
| AC-18 | Not started | PR 2a/3 |
| AC-19 | Not started | PR 2a/3 |
| AC-20 | Not started | PR 2a/3 |
| AC-21 | Not started | PR 2a/3 |
| AC-22 | Not started | PR 2a/3 |
| AC-23 | Not started | PR 2a |
| AC-24 | Not started | PR 2a/3 |
| AC-25 | Partial | PR 1 delivers the manifest fields `coverage_study_period` (Silver denominator 48 x 608 days = 29,184) and `zero_share` per household, checked in the local_data test. Summary view tests are PR 2a/3 |
| AC-26 | Not run | Spike 04 pipeline and summary_view.sql written, not run. Other tests are PR 2a/2b/3 |
| AC-27 | Not started | PR 2a/3 |
| AC-28 | Not started | PR 2b/3 (spike 00 written, not run) |
| AC-29 | Partial | Producer half passes: test_ac29_* in tests/test_producer.py (credentials from the environment only, errors name variables not values, no literal credentials). `.dockerignore` excludes .env, data, *.pem. Hygiene scan, bundle and `pre-commit run --all-files` are PR 2a/2b and not yet run. Spike notebooks read secrets with dbutils.secrets.get and redact error text |
| AC-30 | Not run | Spike 04 timing over 1.68 M rows written, not run. Bundle and integration tests are PR 2b/3 |
| AC-31 | Partial | Producer sets `produced_at` as the UTC wall clock in ISO-8601 (test_ac31_produced_at_is_utc_wall_clock_not_event_time passes). End-to-end check is PR 3 |
| AC-32 | Partial | test_ac32_check_specs_reports_no_errors passes. test_ac32_runtime_adr_records_every_spike_outcome FAILS by design: ADR 0001 still has Pending for A-02, A-03, A-05, A-06, A-09, A-10 until the user runs the spikes. A-01 is Pass |
| AC-33 | Not started | PR 2a |
| AC-34 | Not started | PR 2a/3 (A-08 holds, see AC-11) |
| AC-35 | Not started | PR 2a/3 |

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` | 33 files already formatted |
| Tests | `.venv/bin/pytest` | 52 passed, 1 failed, 6 deselected. The failure is test_ac32_runtime_adr_records_every_spike_outcome (spike results Pending, by design) |
| Local-data tests | `.venv/bin/pytest -m local_data` | 6 passed, 53 deselected (about 77 s) |
| Spec check | `.venv/bin/python scripts/check_specs.py` | 17 document(s) checked, 0 error(s), 0 warning(s) |
| A-08 | `.venv/bin/python spikes/local/a08_offgrid_null_cooccurrence.py` | PASS (see AC-11) |
| Sample build | `.venv/bin/python scripts/prepare_sample.py build --out data/sample/seed42` | 60 households, 1,432,405 historical rows in 17 files, 247,569 stream rows; data files and household CSV byte-identical to the pinned references |
| Producer dry run | `python -m smart_meter_peak_prediction.producer --dry-run --input data/sample/seed42/stream/readings_stream.csv` | 247,569 JSON lines |
| Spike syntax | `python -m py_compile spikes/databricks/**/*.py` | OK (no execution) |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| Plan key | "Whenever `blocks` is present in the plan" and "chosen blocks copied from the spike plan" (spike key is `groups`) | `config/sample_plan.json` uses `blocks`; the loader also accepts `groups` | Matches the DESIGN wording; the frozen spike plan stays loadable | No (not needed) |
| ADR 0001 table | Lists no A-08 row | Added an A-08 row with the local result (Pass) | The DESIGN asks to record A-08 where the assumption lives; no spike outcome of Databricks touched | No |
| Spike 04 helper package | Spike imports a package through `sys.path` (DA-08) | `run_spike.py` embeds the helper module as a string and uploads it, instead of an extra repo file | Keeps to the manifest file list | No |
| Failing test in a PR 1 build | Test Strategy requires ADR 0001 results for A-02 to A-10 | The test exists and fails until the spikes are run and recorded | Not skipping tests; the failure is the PR 1 gate | No |
| `pyspark` | Dev extra | Declared, not installed in `.venv` | PR 1 needs no Spark or Java | No |
| Producer CLI | `--dry-run` | Also `--input`, `--topic`, `--speed`, `--limit` | Needed to run spikes with a few events; `--limit` is not required elsewhere | No |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | DEFINE row A-08 is still `Pending`; the check passed (60 of 60) | Low | One-line `/iterate` on DEFINE to set A-08 to validated |
| I-02 | DEFINE inline schema lists the sample reading files as `household_id, reading_ts, energy_kwh`; the code and pinned checksums use the source header | Low | One-line `/iterate` (already noted in the DESIGN Self-Review) |
| I-03 | `tests/test_runtime_adr.py` fails, so CI is red on the PR 1 branch until ADR 0001 is filled | Medium | Run the spikes and record results; or open PR 1 as draft |
| I-04 | `coverage_study_period` in the manifest counts distinct on-grid timestamps with finite non-negative energy over 29,184 slots; the DESIGN does not define "observed" exactly | Low | Confirm during PR 2a when AC-25 compares Gold with the manifest |
| I-05 | Spike 04 uses SDK and Lakeflow calls that were not exercised (`private=True`, `FileLibrary`, `EventLogSpec`, `workspace.upload` with `RAW`) | Medium | Expect small fixes on first run; log them as spike edits, not as design changes |
| I-07 | Code-reviewer self-review of PR 1: 1 High (wrong `/Workspace` prefix for `spike.src_path` in run_spike.py) and several Medium/Low items fixed (stale-file cleanup in `build_sample`, DA-08/DA-01 assertions, event-log cleanup, upload wrapper, producer row validation, Dockerfile `--user` note). Full gate before Complete still pending | Low | Re-run the code-reviewer before Complete |
| I-06 | Dockerfile not built | Low | User builds it (command below) |

---

## Pending on the user

1. Auth: `databricks auth login` (profiles are expired). Create the local `.env` from `.env.example`, and the secret scope `smart_meter` (keys `kafka-bootstrap-servers`, `kafka-sasl-username`, `kafka-sasl-password`, `kafka-ca-pem`).
2. Aiven: read the SASL mechanism offered in the console (A-06) and power on the service.
3. Generate and upload the sample (already generated locally in `data/sample/seed42/`): `databricks fs cp` of two historical files to `dbfs:/Volumes/smart_meter_dev/bronze/landing/_spike/readings/` (spike 01 header).
4. Run spikes in this order and record each result in ADR 0001 and `docs/spikes/README.md`:
   - DA-06 manual deploy test (steps in the header of `spikes/databricks/00_setup_catalog.py`), then run notebook `00_setup_catalog.py`;
   - notebook `01_spike_autoloader.py`;
   - produce messages, then notebook `02_spike_kafka_consume.py`;
   - power the broker off, then notebook `03_spike_kafka_unreachable.py`;
   - `export DATABRICKS_WAREHOUSE_ID=<id>; .venv/bin/pip install -e ".[integration]"; .venv/bin/python spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py`.
5. Build the producer image: `docker build -f docker/producer/Dockerfile -t smart-meter-producer .`
6. If any of A-03, A-10, DA-01 or A-09 fails, run `/iterate` on the DESIGN before PR 2a.

---

## Self-Review

- **Weak points:** The Databricks spikes are unexecuted, so API details (Lakeflow `private=True`, event log JSON paths, SDK calls) may need small fixes on first run. The pipeline-harness ACs are not touched yet. The ADR 0001 test is red until the user records results.
- **Risks:** A failed spike (A-03, A-10, DA-01, A-09) forces `/iterate` before PR 2a. The producer was only exercised in dry-run and with fakes, never against a broker.
- **What I would do differently:** Run the spike 04 pipeline code in a dry check against a fake `dlt` before handing it over, and give the ADR test a distinct state for "spike not yet run" so CI can stay green on the PR 1 branch without skipping.
- **Next improvement:** The user runs spikes 00 to 04 and records the outcomes; then PR 2a starts.

---

## Next Step

Run the pending spikes and record results in ADR 0001. Then `/build` PR 2a. (`/ship METER_INGESTION` only after PR 3.)
