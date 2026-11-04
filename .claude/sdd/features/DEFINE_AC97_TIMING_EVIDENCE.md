# DEFINE: AC-97 Timing Evidence

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC97_TIMING_EVIDENCE |
| **Date** | 2026-11-04 |
| **Author** | Christian |
| **Source** | Follow-up F-05 of `.claude/sdd/archive/INGESTION_GUARD/SHIPPED_2026-11-04.md` (no BRAINSTORM: small feature cycle); archived INGESTION_GUARD DEFINE (AC-97, A-31, OD-23), DESIGN (DA-31, OD-23 fallback ladder) and BUILD_REPORT (I-04, AC-97 row); `tests/integration/test_ingestion_guard_live.py::test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds`; `Evidence` in `tests/integration/conftest.py`; `src/smart_meter_peak_prediction/pipeline_guard.py` (pipeline-only message, `_checked_at`); `docs/runbooks/meter_ingestion.md` (Concurrency with the peak job; Evidence order rows H to J); `tests/test_integration_layout.py` |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: v0.4.1 (patch, D-60). This feature closes INGESTION_GUARD follow-up F-05.

**ID numbering.** IDs continue the project-wide series after INGESTION_GUARD: FR-54, NFR-30,
AC-100, C-14, A-33, D-60, OD-24 and Q-25 (last used: FR-53, NFR-29, AC-99, C-13, A-32, D-59,
OD-23, Q-24; Q-25 was reserved and not used). AC-100 is the first three-digit AC (see C-15).
DA-NN, I-NN and OD-NN without a feature name refer to the archived INGESTION_GUARD documents.

---

## Problem Statement

The live test of INGESTION_GUARD AC-97 proves that `check_silver_gold_idle` refuses while a
pipeline update is active, but it is only meaningful when the no-op update started by the test is
still active when the check reads the pipeline (DA-31). The test asserts the outcome and saves no
timing, so the one observed margin (update created 18:37:07Z, read 18:37:34Z on 2026-10-23, still
`WAITING_FOR_RESOURCES`) exists only in the Jobs API and in the build report text (I-04). Once the
runs are pruned, a later run that passes narrowly, or fails because the update ended early, leaves
no record of how close it was. The operator then cannot tell a timing failure from a defect in the
check.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Live-test operator (runs AC-97 on `dev`) | Know after each AC-97 run how long the update had been active when the check read it, and how long it stayed active afterwards; know what to do and what to record when AC-97 fails because the update ended early | `out/evidence/ac97_timing.json`; the AC-97 failure message; `docs/runbooks/meter_ingestion.md` |
| Build report author and reviewer of a release | Cite the AC-97 margin and run ids from a file written during the run, not from a Jobs API lookup afterwards | The evidence file, copied into the release's BUILD_REPORT live-evidence row |
| Maintainer judging DA-31 over time | Compare margins across releases and workspaces to see whether the no-op update still outlives the check | The margin fields of the evidence file as recorded in build reports |
| Scheduled jobs `smart_meter_ingestion` and `smart_meter_peak_model` | No change in behaviour | Unchanged job, pipeline, guard library and notebooks (C-14) |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Timing evidence persisted by the test | Live AC-97 executions that started the update and ended without writing the evidence file | 0 (AC-106; FR-58 for the failure path) |
| Margin readable without the Jobs API | Fields needed to recompute both margins (update creation, check read, update end) present and consistent in a file whose outcome is `refused` | 3 of 3, and both margins equal the differences of the stored timestamps exactly (AC-100, AC-106) |
| No change of production behaviour | Byte differences of `resources/`, `notebooks/`, `databricks.yml` and `src/smart_meter_peak_prediction/` (except the version string) against tag `v0.4.0` | 0 (AC-105) |
| AC-97 not weakened | `assert` statements of the shipped AC-97 test function at `v0.4.0` missing from the new test | 0 (AC-105) |
| Small test cost | Additional job runs and pipeline updates started by the AC-97 test; additional wall time | 0 runs, 0 updates; at most 30 s (NFR-31) |

---

## Scope

**In scope:**
- The live AC-97 test writes `out/evidence/ac97_timing.json` through the shipped `Evidence` helper,
  with the update id, the update creation and end times, the check task start and end, the time and
  the states the check read (from the check's error output, or its exit value when it passed), the
  two derived margins, the refused and rerun run ids, and an outcome (D-61, D-62).
- Pure, SDK-free helpers that compute the margins, parse the check's busy message and build the
  record, with unit tests (D-63).
- The file is written also when an AC-97 assertion fails after the update was started (FR-58).
- Runbook text in `docs/runbooks/meter_ingestion.md`: where the file is, how to read the margins,
  what to do when AC-97 fails because the update ended early (the shipped ladder: rerun once; then
  start the update with `full_refresh=True`; then record AC-97 `Partial` with a direct
  `check_pipeline` read during the update), and how to record each attempt (D-65).
- A docs test for that runbook text, and the changes to shipped tests that the new test names need
  (C-15, OD-24).
- Release v0.4.1: package version 0.4.1 and a CHANGELOG entry at `/ship` (D-60).

**Out of scope:**
- Any change to the ingestion job, the pipeline, `pipeline_guard`, the notebooks, the bundle
  (`databricks.yml`, `resources/`) or the peak side (C-14). The check's message format is read, not
  changed (A-34).
- A new pass or fail threshold on the margins in AC-97 (D-64, Q-26). A later release may add one
  once several margins are recorded.
- Timing evidence for other live tests (AC-74, AC-75 and the peak-side DA-26 share the same
  mechanics). Not scheduled; the helpers of this feature can be reused.
- Other INGESTION_GUARD follow-ups (F-02, F-03, F-04, F-06 to F-10).
- Making the evidence file a durable record in the repository: `out/` stays git-ignored (C-16).

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-54 | The live AC-97 test shall write the evidence file `out/evidence/ac97_timing.json` through the shipped `Evidence.save` (so it carries `saved_at_ms`), with every field of the *AC-97 timing record* contract below. One execution writes one file; a later execution overwrites it (D-61). | Must |
| FR-55 | The system shall derive two margins from the recorded UTC timestamps by a pure function without SDK imports, I/O or clock reads: `read_after_creation_seconds` = `check_read_ts` minus `update_created_ts`, and `update_outlived_read_seconds` = `update_ended_ts` minus `check_read_ts`, both in whole seconds and signed. A margin whose input is missing or has no time zone is `null`; it is never estimated (D-63). | Must |
| FR-56 | The time and the states that the check read shall come from the check task's own output: from its error message when it refused (the FR-47 busy message of INGESTION_GUARD: "checked at" time, and for the update U the state, the pipeline state and the creation time), or from its exit value when it passed (`checked_at`, `outcome`). The parse shall not change `pipeline_guard`; a message that does not name U, or that has another shape, gives `null` read fields, not an error. | Must |
| FR-57 | The update end time shall come from the platform's record of the update, with `update_end_source` = `platform`. When the platform does not report it, the earliest time at which the test observed the update in a terminal state is recorded instead, with `update_end_source` = `observed_terminal` (an upper bound). When neither is known the time and the source are `null`. | Must |
| FR-58 | Once the AC-97 test has started the update, it shall write the evidence file before it ends, also when one of its assertions fails or the platform raises; fields not known at that point are `null`. When AC-97 fails, its failure message shall name `out/evidence/ac97_timing.json` next to the shipped ladder advice. | Must |
| FR-59 | The record shall state an `outcome`: `refused` when the check task ended `FAILED` and its message named U with a non-terminal state; `update_ended_before_check` when the check task passed (exit outcome `idle`) or `update_outlived_read_seconds` is 0 or less; `incomplete` in every other case. | Should |
| FR-60 | `docs/runbooks/meter_ingestion.md` shall state where the file is written, the meaning and sign of both margins with the reference values of 2026-10-23 (27 s after creation), that the "checked at" time is taken just after the read (so `update_outlived_read_seconds` errs low), what to do when AC-97 fails because the update ended early (rerun once; then start the update with `full_refresh=True`; then record AC-97 `Partial` with a direct `check_pipeline` read during the update), and that each attempt's file is copied into the release's BUILD_REPORT before the next attempt overwrites it. Every `--only` list in the new text that contains `refresh_silver_gold` also contains `check_silver_gold_idle` (INGESTION_GUARD AC-99). | Must |
| FR-61 | The shipped AC-97 assertions shall stay in force: every `assert` statement of the AC-97 test function at tag `v0.4.0` is present unchanged in the new test function, and the test keeps its run mechanics (one no-op update, two subset runs `check_silver_gold_idle,refresh_silver_gold`, OD-23). | Must |
| FR-62 | The release shall change only tests, docs, specs and the version: package version `0.4.1` in `pyproject.toml` and `src/smart_meter_peak_prediction/__init__.py` (set in the build, so AC-105 holds at the feature commit), and a `[0.4.1]` CHANGELOG entry at `/ship`. No other file under `src/`, `resources/`, `notebooks/` or `databricks.yml` changes (C-14). | Must |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-30 | Time handling | Every timestamp in the evidence file is UTC text matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` or `null` (the shipped `saved_at_ms` is epoch milliseconds, zone-free). Inputs with an offset or as epoch milliseconds are converted to the same UTC instant; a value without a zone is `null`, never read as local time. Margins are integers. |
| NFR-31 | Cost | The evidence adds 0 job runs and 0 pipeline updates to AC-97, at most 5 extra read-only API calls, and at most 30 s of wall time beyond the shipped test's own waits. |
| NFR-32 | Security | The evidence file and the new helpers hold 0 tokens, 0 secret values and 0 workspace URLs: no value of the record contains `https://`, `dapi` or `Bearer`. The file stays under the git-ignored `out/`. |
| NFR-33 | Reproducibility | The margin, parse and record helpers are deterministic: the same inputs give the same output, byte-equal after `json.dumps(..., sort_keys=True)`. They import no Databricks SDK module, so they run in CI. |
| NFR-34 | Compatibility | `pytest` without the integration marker reports 0 failures, including every shipped test (INGESTION_GUARD AC-84, AC-85, AC-92, AC-99 among them); `scripts/check_specs.py` reports 0 errors; the integration collection still selects `test_ingestion_guard_live.py::test_ac97_`. |

---

## Data Contracts

This feature writes no table and changes no shared contract. It writes one local evidence file and
reads platform metadata. Contracts are inline because no other feature shares them. Field names
follow `docs/conventions/naming.md` (`<event>_ts` for UTC timestamps) and the shipped evidence
files (`_seconds` for durations, `run_id`).

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| AC-97 timing record, `out/evidence/ac97_timing.json` (written) | AC97_TIMING_EVIDENCE | One execution of the live AC-97 test that started an update (the latest; overwritten per execution) | `update_id` (with `refused_run_id`) | Written during the test, before it ends (FR-58) | Inline: *AC-97 timing record* below |
| Check task output of the refused and the rerun run (read) | INGESTION_GUARD | One check task run | task `run_id` | At task end | Inline: FR-47 busy message (INGESTION_GUARD) or FR-49 exit value |
| Pipeline update U (Pipelines API, read only) | METER_INGESTION (platform metadata) | One pipeline update | `update_id` | Read live during and after the test | Inline: `update_id`, `creation_time`, `state`, end time (source per OD-26, A-33) |
| Job runs and task runs of `smart_meter_ingestion` (Jobs API, read only) | METER_INGESTION (platform metadata) | One task run | job `run_id`, task `run_id` | Read after each run ends | Inline: `start_time`, `end_time` (epoch ms), `result_state` |

**AC-97 timing record** (derived field set, D-62; one JSON object):

| Field | Type | Meaning |
|---|---|---|
| `update_id` | string | The update U the test started |
| `update_created_ts` | UTC text or null | Creation time of U as the platform reports it |
| `update_ended_ts` | UTC text or null | End time of U (FR-57) |
| `update_end_source` | `platform`, `observed_terminal` or null | Where `update_ended_ts` came from |
| `update_final_state` | string or null | Terminal state of U |
| `refused_run_id` | integer or null | Job run id of the first (refused) subset run |
| `check_task_run_id` | integer or null | Task run id of `check_silver_gold_idle` in that run |
| `check_started_ts`, `check_ended_ts` | UTC text or null | Start and end of that task run |
| `check_result` | string or null | Its result state (`FAILED` expected) |
| `check_read_ts` | UTC text or null | The check's "checked at" time (FR-56) |
| `check_read_update_state` | string or null | State of U in the check's message |
| `check_read_pipeline_state` | string or null | Overall pipeline state in the check's message |
| `read_after_creation_seconds` | integer or null | `check_read_ts` minus `update_created_ts` (FR-55) |
| `update_outlived_read_seconds` | integer or null | `update_ended_ts` minus `check_read_ts` (FR-55) |
| `rerun_run_id` | integer or null | Job run id of the second subset run |
| `rerun_check_result`, `rerun_refresh_result` | string or null | Result states of its two tasks |
| `outcome` | `refused`, `update_ended_before_check` or `incomplete` | FR-59 |
| `saved_at_ms` | integer | Added by the shipped `Evidence.save` |

---

## Acceptance Criteria

**Unit** criteria run in CI without the Databricks SDK. **Live** criteria run on the deployed
`dev` target with the integration marker; their evidence goes into the BUILD_REPORT.

| ID | Level | Given | When | Then |
|---|---|---|---|---|
| AC-100 | Unit | `update_created_ts` 2026-10-23T18:37:07Z, `check_read_ts` 2026-10-23T18:37:34Z, `update_ended_ts` 2026-10-23T18:39:12Z; the same instants given as ISO 8601 with `+02:00`, as epoch milliseconds and as aware datetimes | The margin helper runs on each form, twice | `read_after_creation_seconds` is 27 and `update_outlived_read_seconds` is 98 for every form; every returned timestamp matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` and equals the UTC instant of the input; the two runs give equal outputs |
| AC-101 | Unit | (a) end 2026-10-23T18:37:29Z before read 18:37:34Z; (b) read missing; (c) end missing; (d) creation given as a naive datetime; (e) an idle check (exit outcome `idle`) | The margin helper and the outcome rule run | (a) `update_outlived_read_seconds` is -5 and `outcome` is `update_ended_before_check`; (b) both margins `null`, `outcome` not `refused`; (c) `read_after_creation_seconds` computed, `update_outlived_read_seconds` `null`; (d) `update_created_ts` and `read_after_creation_seconds` `null`; (e) `outcome` `update_ended_before_check`. No case raises |
| AC-102 | Unit | Messages produced by the shipped `pipeline_guard` pipeline-only mode (`INGESTION_CALLER`, a fake client, fixed `now`): busy with update U in `WAITING_FOR_RESOURCES` created at a known time; busy with two active updates, U second; busy with no update listed; fail-closed; idle; an empty and an unrelated string | The message parser runs with U | For the two busy messages naming U it returns U's state, the pipeline state, U's creation time and the "checked at" time exactly as the library rendered them; for the other inputs it returns `null` for U's state and creation time without raising (the "checked at" time where the message has one) |
| AC-103 | Unit | Inputs for a refused run and a rerun (ids, task times in epoch ms, the busy message, U's times and source), and the same inputs with every optional input missing | The record builder runs | The result has exactly the fields of the *AC-97 timing record* contract (except `saved_at_ms`, added on save) with the contract types; it is JSON-serialisable; the margins equal AC-100's helper on the same timestamps; no value contains `https://`, `dapi` or `Bearer`; with inputs missing, those fields are `null` and `outcome` is `incomplete` |
| AC-104 | Unit | `docs/runbooks/meter_ingestion.md` at the feature commit, and the AC-97 failure hint of the live test | The runbook and the hint text are read | The runbook names `out/evidence/ac97_timing.json`, `read_after_creation_seconds`, `update_outlived_read_seconds`, the reference value 27 s, `full_refresh=True`, `Partial`, `check_pipeline` and `BUILD_REPORT`; every `--only` list in it with `refresh_silver_gold` contains `check_silver_gold_idle`; the AC-97 failure hint names `out/evidence/ac97_timing.json`. The shipped INGESTION_GUARD AC-99 docs tests pass unmodified |
| AC-105 | Unit | The repository at the feature commit and tag `v0.4.0` (the tag exists locally) | The trees and the AC-97 test function are compared, then `pytest` (no integration marker) and `scripts/check_specs.py` run | Every file under `resources/`, `notebooks/` and `src/smart_meter_peak_prediction/`, and `databricks.yml`, equals `v0.4.0` byte for byte, except the `__version__` line, which reads `0.4.1`; `pyproject.toml` has version `0.4.1`. Every `assert` statement of `test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds` at `v0.4.0` (compared as unparsed AST) occurs in the new AC-97 test function. `pytest` reports 0 failures; `check_specs.py` reports 0 errors |
| AC-106 | Live | The `dev` target deployed with this release; no active run of either job; the pipeline idle | The live AC-97 test runs once and passes | `out/evidence/ac97_timing.json` exists with `saved_at_ms` later than the test start; `update_id` is the update the test started; `refused_run_id` and `rerun_run_id` are the two runs of this execution and differ; `outcome` is `refused`; `check_read_update_state` is non-terminal; `update_created_ts` <= `check_read_ts`; `check_started_ts` - 1 s <= `check_read_ts` <= `check_ended_ts` + 1 s; `update_outlived_read_seconds` > 0 and `read_after_creation_seconds` >= 0, each equal to the difference of the stored timestamps; `update_end_source` is not `null`. The values are copied into the BUILD_REPORT AC-106 row |

### Traceability (FR and NFR to AC)

| Requirement | Covered by |
|---|---|
| FR-54 | AC-103, AC-106 |
| FR-55 | AC-100, AC-101, AC-103, AC-106 |
| FR-56 | AC-102, AC-106 |
| FR-57 | AC-103, AC-106 |
| FR-58 | AC-101, AC-103, AC-104 |
| FR-59 | AC-101, AC-103, AC-106 |
| FR-60 | AC-104 |
| FR-61 | AC-105, AC-106 |
| FR-62 | AC-105 |
| NFR-30 | AC-100, AC-101, AC-103 |
| NFR-31 | AC-106 (wall time and run count read from the BUILD_REPORT row) |
| NFR-32 | AC-103 |
| NFR-33 | AC-100, AC-103 |
| NFR-34 | AC-104, AC-105 |

Coverage of the required kinds: correctness AC-100, AC-102, AC-106; idempotency AC-100 (same
inputs twice), AC-106 (the file holds this execution's ids, not a previous one); data quality of
the inputs (offsets, epoch values, naive times, missing values, unrelated messages) AC-100 to
AC-103; failure paths AC-101 (update ended before the read), AC-103 (missing inputs, `incomplete`),
AC-104 (failure hint names the file); regression AC-104, AC-105.

---

## Decisions and Open Items

### Decided by the user

| ID | Statement | Where it is used |
|---|---|---|
| D-60 | Small feature cycle without a BRAINSTORM; scope is test-only plus docs (AC-97 writes an evidence file; runbook text); no change to the ingestion job, the guard library, the bundle or the peak side; release v0.4.1 (patch). Confirmed by the user for this `/define` | Metadata, Scope, FR-62, C-14 |

### Derived in this phase (not yet confirmed by the user)

| ID | Statement | Derived from | Where it is used |
|---|---|---|---|
| D-61 | The file is `out/evidence/ac97_timing.json`, written with the shipped `Evidence.save`; one file per name, overwritten by the next execution, like `ac76_run_durations.json` and `ac62_peak_run_durations.json` | Shipped evidence pattern; F-05 | FR-54, AC-106 |
| D-62 | The field set and outcome values of the *AC-97 timing record* | F-05 and the scope list; `naming.md` (`_ts`) | Data Contracts, FR-54, FR-59, AC-103 |
| D-63 | The check's read time is its own "checked at" value, taken just after `pipelines.get` returns and cut to whole seconds (`_checked_at`). Margins are whole seconds; `update_outlived_read_seconds` therefore errs low by at most about 1 s, which is the safe direction | `pipeline_guard._checked_at` and `check_pipeline` (code reading, A-35) | FR-55, FR-56, FR-60, AC-100 |
| D-64 | AC-97 keeps its shipped pass criteria; the margins are recorded, not asserted against a threshold (only the consistency of AC-106) | Scope: test-only, AC-97 not changed in meaning (FR-61) | Scope, AC-106; Q-26 |
| D-65 | A rerun is recorded by copying each attempt's file into the AC-97 (or AC-106) live-evidence row of the release's BUILD_REPORT; the runbook says how and where, but holds no log of runs (golden rule 7: runbooks describe the system) | F-05 ("record it in the runbook"), golden rule 7, C-16 | FR-60, AC-104; Q-25 |

### Questions for the user

| ID | Question | Answer (user, 2026-11-04) |
|---|---|---|
| Q-25 | F-05 says "if a rerun is needed, record it in the runbook". Should the record of a rerun be in the runbook itself (a dated row), or in the release's BUILD_REPORT with the runbook only explaining how? | BUILD_REPORT, with the runbook explaining how (D-65, confirmed) |
| Q-26 | Should a small margin be flagged, for example a warning in the test output when `update_outlived_read_seconds` is below 30 s, without failing AC-97? | No threshold in v0.4.1 (D-64, confirmed) |

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-24 | Test names for the new live AC under the shipped layout test, which accepts only `^test_ac(\d{2})_` (C-15): widen the pattern to two or three digits and add 106 to `EXPECTED_ACS`, or extend the AC-97 test under a name such as `test_ac97_ac106_...` (keeps the `test_ac97_` prefix used by the runbook and the collection check, as `test_ac98_ac74_...` does), or both. The same choice applies to unit test names `test_ac100_` to `test_ac105_` |
| OD-25 | Location and name of the SDK-free helpers (margins, parser, record builder): a module under `tests/` importable by the unit tests and the live test, with basenames unique under `tests/` (INGESTION_GUARD D-01). Not under `src/` (C-14) |
| OD-26 | Source of `update_ended_ts` (A-33): the update's terminal event in the pipeline event log, an update read, or the test's own wait loop (`_wait_pipeline_idle` polls every 10 s, which gives `observed_terminal` with 10 s resolution); which state counts as the end (`COMPLETED`, `FAILED`, `CANCELED`) |
| OD-27 | How FR-58 is met: one `finally` around the whole test that writes what is known, or writes at checkpoints; how the failure hint names the file without changing any shipped `assert` (FR-61) |
| OD-28 | Where the runbook text goes: a paragraph after the Evidence order table, a note in row H, or a subsection; and whether `docs/runbooks/peak_model.md` needs a cross-reference (default: no, the peak side is unchanged) |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 to C-07 | Constraint | Inherited from METER_INGESTION: Free Edition serverless only, daily quota, no secrets in code, UTC end to end | Yes |
| C-13 | Constraint | INGESTION_GUARD pins stay in force (ingestion job YAML digest and `v0.4.0` content, pipeline YAML and `databricks.yml` at `v0.1.0`, training job at `v0.2.0`, peak job and `check_pipeline_idle.py` at `v0.3.0`); archived SDD documents are not edited | Yes |
| C-14 | Constraint | Test-only plus docs: no change under `resources/`, `notebooks/`, `src/smart_meter_peak_prediction/` (except `__version__`) or to `databricks.yml`; the peak side is unchanged | Yes (user, D-60) |
| C-15 | Constraint | `tests/test_integration_layout.py` accepts integration test names `^test_ac(\d{2})_` only, and AC-100 is the first three-digit AC; a test named `test_ac106_...` fails `test_integration_every_test_is_marked_and_names_its_ac` unless OD-24 resolves it | Yes (code reading, 2026-11-04) |
| C-16 | Constraint | `out/evidence/` is git-ignored and local to the machine that ran the test; the durable record of a live run is the BUILD_REPORT | Yes |
| A-33 | Assumption | The Pipelines API reports when update U ended (for example the timestamp of its terminal update event), readable by the test's identity with no extra grant | **Validated (live AC-106, dev, 2026-11-04).** First AC-106 run: `update_end_source` = `platform`; update 1bb3c498-6f34-4303-98ad-ebd8c40f2ade ended `COMPLETED` at 18:52:28Z, read from the pipeline events. Single observation, dev only. Fallback (not needed): `observed_terminal` from the test's wait loop (FR-57) |
| A-34 | Assumption | The v0.4.0 busy message of the pipeline-only mode has the shape "(checked at T)" and "update U, state S, pipeline state P, created C", and does not change in this release | Validated by code reading (`PipelineReport.message`, v0.4.0); held by C-14 and checked against the library itself by AC-102 |
| A-35 | Assumption | The check's "checked at" time is computed after its single `pipelines.get` returns, in whole seconds, so it is at or after the read | Validated by code reading (`check_pipeline` builds the report after `_read_pipeline`; `_checked_at` uses `%S`) |
| A-36 | Assumption | The no-op update still outlives the check of a subset run started right after it (DA-31; one observation, 27 s after creation with the update still `WAITING_FOR_RESOURCES`) | Validated once on dev (2026-10-23); this feature records each new observation (AC-106) |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | One named gap (F-05, I-04): the AC-97 margin exists only in the Jobs API, with the observed values and the cost (a pruned run leaves no record) |
| Users | 3 | Operator, build report author and reviewer, the maintainer tracking DA-31, and the unchanged jobs, each with the place they read the outcome |
| Scope | 3 | Test-only plus docs (D-60, C-14), the field set fixed (D-62), and the excluded threshold, other live tests and follow-ups named |
| Acceptance criteria | 3 | Seven criteria: six unit (margins with fixed values, parser against the real library message, record builder, docs, no-change and assert retention) and one live with ordering and equality checks; every FR and NFR covered |
| Constraints | 2 | The end-time source (A-33) is pending until the first live run; the two-digit test-name rule (C-15) needs a design choice (OD-24) |
| **Total** | **14/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The failure path of FR-58 (file written when AC-97 fails) cannot be forced on dev. It is
    covered by unit tests of the record builder with missing inputs (AC-101, AC-103) and by the
    hint text (AC-104), not by a live failure.
  - The margins have a resolution of 1 s on the read and creation times, and of 10 s when the end
    time is only observed by the test's poll (A-33 fallback). `update_outlived_read_seconds` is
    then an upper bound on the end and the file says so (`update_end_source`).
  - The parser depends on the v0.4.0 message text (A-34). AC-102 tests it against the library's own
    output, so a later change of the message breaks the unit test, not the live run.
  - One file per name (D-61): a second attempt overwrites the first, so recording relies on the
    operator following the runbook (D-65, Q-25).
- **Risks:**
  - A-33 may fail: if no end time is reported, every AC-106 run records `observed_terminal`, and
    the margin is less precise.
  - The first three-digit AC (C-15) can break the shipped layout test if OD-24 is missed; the
    DESIGN manifest must list the change.
  - Live evidence costs quota: AC-106 reuses the AC-97 run (one no-op update, two subset runs) and
    adds no run, but it still needs one live session.
- **Trade-offs:**
  - Reading the check's own "checked at" time, rather than the task start, measures what DA-31 is
    about (the state at the read), at the price of parsing message text (A-34).
  - No threshold (D-64) keeps AC-97's meaning unchanged in a patch release; a threshold can come
    once several margins exist.
  - Helpers under `tests/` keep the release test-only (C-14), but they cannot be reused by
    production code; nothing in production needs them.
- **What I would do differently:** Have the INGESTION_GUARD DESIGN put each live timing
  assumption (DA-31) next to the evidence file that records it, so that this patch would not be
  needed.
- **Next improvement:** In `/design`, settle OD-24 first (it decides which shipped test changes),
  then OD-26 (the end-time source decides whether A-33 needs a probe before the build).

---

## Next Step

`/design .claude/sdd/features/DEFINE_AC97_TIMING_EVIDENCE.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-11-04 | Created: FR-54 to FR-62, NFR-30 to NFR-34, AC-100 to AC-106, C-14 to C-16, A-33 to A-36, D-60 (user), D-61 to D-65 (derived), Q-25, Q-26, OD-24 to OD-28. Status `Ready for Design` | Phase 1 of the SDD workflow, from INGESTION_GUARD follow-up F-05 | `/design` can start; Q-25 and Q-26 answered by the user (2026-11-04) as the defaults, so D-64 and D-65 are confirmed |
| 2026-11-04 | A-33 row set to Validated (first live AC-106 run on dev: `update_end_source` = `platform`); status-only, no requirement changed. Clarity Score and Self-Review prose left as written at define time | Live AC-106 evidence recorded in BUILD_REPORT_AC97_TIMING_EVIDENCE.md; mirrors DESIGN DA-35 | None: DESIGN already updated (DA-35 to DA-38); status unchanged |
