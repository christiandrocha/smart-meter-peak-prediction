# DEFINE: AC-66 Both Legs

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_BOTH_LEGS |
| **Date** | 2026-11-09 |
| **Author** | Christian |
| **Source** | Follow-up PEAK_MODEL F-15 (`.claude/sdd/follow-ups/F_PEAK_MODEL_15.md`: triage full cycle because E6 is `No`, done criterion DC-01; no BRAINSTORM: small feature cycle); archived PEAK_MODEL DEFINE (AC-66, NFR-10, NFR-11, NFR-17), DESIGN (AC-66 Test Strategy rows, manifest entry 41, guard PEAK_MODEL G-12), BUILD_REPORT (AC-66 rows, live evidence of 2026-10-22) and SHIPPED_2026-10-22 (Follow-ups row PEAK_MODEL F-15, lesson "Spec (partial legs)"); `tests/integration/test_peak_data.py` (module docstring, AC-66 section); `Evidence` in `tests/integration/conftest.py`; `scripts/reset_peak_model_outputs.py` and `tests/test_peak_reset_script.py`; `docs/runbooks/peak_model.md` (sections 8 and 9); `tests/test_integration_layout.py` |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: v0.7.0 (minor, D-92; confirmed by the user in Q-34). This feature closes PEAK_MODEL F-15.

**ID numbering.** IDs continue the project-wide series: FR-84, NFR-43, AC-154, C-22, A-49, D-92,
OD-41 and Q-32 (last used: FR-83, NFR-42, C-21, A-48, D-91, OD-40 and Q-31 in SMALL_CHANGE_TRACK;
AC-153 in TEMPLATE_PORT). PEAK_MODEL AC-66 is the requirement this feature enforces; it keeps its
ID and its text, and every other ID of another spec is written with that spec's name in front.
Unprefixed IDs are this feature's own.

---

## Problem Statement

PEAK_MODEL AC-66 needs two legs against one first build: a rerun of the weather Silver, feature
and label steps with no new input, and a rebuild from Bronze weather and the METER_INGESTION
tables after the three outputs are dropped. The one live `after` test
(`test_ac66_after_rerun_and_rebuild_checksums_equal`) chooses its mode from whether the three
tables exist and passes in either mode, so a sequence with only the rerun leg is green. That
happened on 2026-10-22: the build run passed with `rebuild_after_reset` false, and the rebuild leg
was proved only by a separate run during `/ship`, after the ship review caught the gap. The cost
is a release gate that can report PEAK_MODEL AC-66 as passed while half of it (the recoverability
promise of PEAK_MODEL NFR-17) was never exercised, and nothing in the evidence shows it.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Live-test operator (runs the PEAK_MODEL evidence order on `dev`) | Run each AC-66 leg in the right table state, get an immediate refusal (no job run) in the wrong state, and get one verdict that is green only when both legs passed against the current snapshot | The three AC-66 tests and their messages; `out/evidence/ac66_*.json`; `docs/runbooks/peak_model.md` sections 8 and 9 |
| User who runs the reset (the only person allowed to drop the three tables) | Know when in the sequence to run `scripts/reset_peak_model_outputs.py --confirm`, and what to run after it | Runbook section 9; the script's printed next step |
| Build report author and release reviewer | Mark PEAK_MODEL AC-66 `Pass` only from a passing verdict, and cite both legs' values from files written during the run | The verdict record and the two leg records, copied into the BUILD_REPORT live-evidence rows |
| CI (`pytest` without the integration marker) | Prove the verdict and precondition rules without a workspace | Unit tests on fixture records (AC-154 to AC-161) |
| Scheduled jobs `smart_meter_peak_model` and `smart_meter_ingestion` | No change in behaviour | Unchanged notebooks, bundle and library (C-22) |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| AC-66 green only with both legs | Evidence states with only one passing leg (or none) for which the verdict passes | 0 (AC-155, AC-163) |
| No stale evidence accepted | Leg records tied to another snapshot, saved before the current snapshot, in the wrong order, not passed, or with values that contradict the snapshot, for which the verdict passes | 0 (AC-156) |
| Wrong state is cheap | Job runs started by a leg whose table state is wrong | 0 (AC-157, AC-162, AC-164) |
| AC-66 not weakened | Leg assertions of the shipped test at `v0.6.0` (rerun: MERGE 0 / 0 / 0; rebuild: inserted equal to the snapshot counts; both: counts and checksums equal to the snapshot) missing from the new legs | 0 (AC-158, AC-163, AC-164) |
| No production change | Byte differences of `src/`, `resources/`, `notebooks/`, `databricks.yml`, and of the reset script's guard code, against tag `v0.6.0` | 0 (AC-161) |
| No extra cost | Job runs of a full live sequence beyond the two that the shipped test needed for both legs | 0 (NFR-44) |

---

## Scope

**In scope:**
- Two live leg tests in `tests/integration/test_peak_data.py`, a rerun leg and a rebuild leg, each
  refusing to start in the wrong table state and each saving its own evidence record tied to the
  current AC-66 snapshot (FR-84 to FR-87).
- A live AC-66 verdict test that passes only when both legs passed against the same, current
  snapshot in the PEAK_MODEL AC-66 order, and that fails naming each missing or invalid leg
  (FR-88, FR-89).
- Pure, SDK-free verdict and precondition rules with unit tests on fixture records, so the
  verdict logic runs in CI (FR-90).
- The shipped snapshot test and its file kept, so the reset guard keeps working (FR-91).
- Removal of the combined `after` test and the matching changes to `tests/test_integration_layout.py`
  (FR-92; Q-32).
- Text changes: `docs/runbooks/peak_model.md` sections 8 and 9 (new order and test names; the stale
  "then the daily job" after the reset; the rebuild leg no longer "optional"), the module docstring
  of `test_peak_data.py`, and the docstring and printed next step of
  `scripts/reset_peak_model_outputs.py` (FR-93).
- Live evidence of both halves of PEAK_MODEL F-15 DC-01 on `dev`, with the user running the reset
  (FR-95; AC-163, AC-164; Q-33).
- Release v0.7.0 with a CHANGELOG entry at `/ship` (D-92); closing the follow-up file and the
  PEAK_MODEL SHIPPED row PEAK_MODEL F-15 at `/ship`.

**Out of scope:**
- Any change to the notebooks, the library under `src/`, the bundle (`databricks.yml`,
  `resources/`) or the peak and ingestion jobs (C-22).
- Any change to the reset script's guards (`plan`, `targets`, `EXPECTED_ROWS`, `SNAPSHOT`,
  `Warehouse`, the refusal rules) unless `/design` shows it is strictly needed; such a change is
  flagged in OD-44 and needs the user's OK.
- Editing the archived PEAK_MODEL DEFINE or DESIGN (that would be `/iterate`, E4). Their AC-66
  Test Strategy row keeps naming the shipped test; this feature records that it supersedes that
  test mechanism.
- Other PEAK_MODEL follow-ups (PEAK_MODEL F-14, PEAK_MODEL F-02, PEAK_MODEL F-05), including an
  active-run check in the reset script (the open Low of the PEAK_MODEL PR 3 review).
- Splitting other before/after pairs (PEAK_MODEL AC-63, PEAK_MODEL AC-57, METER_INGESTION AC-27):
  each has one leg today. Not scheduled.
- Making `out/evidence/` a durable record: it stays git-ignored (C-25).

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-84 | The system shall provide a rerun-leg live test for PEAK_MODEL AC-66. It requires the AC-66 snapshot and all three tables (`silver.weather_hourly`, `ml.household_features_daily`, `ml.household_labels_daily`) to exist at its start (FR-86). It starts the data tasks `ingest_weather`, `build_weather_silver`, `build_features` and `build_labels` once and passes only when the MERGE metrics of the three build tasks are 0 inserted, 0 updated and 0 deleted each, and the row counts and checksums of the three tables equal the snapshot. On a pass it saves the *AC-66 leg record* with `leg` = `rerun` and `outcome` = `passed`. | Must |
| FR-85 | The system shall provide a rebuild-leg live test for PEAK_MODEL AC-66. It requires the AC-66 snapshot and that none of the three tables exists at its start (FR-86). It starts the same four data tasks once and passes only when each build task's MERGE metrics are inserted equal to that table's snapshot `row_count`, 0 updated and 0 deleted, and the row counts and checksums of the three tables equal the snapshot. On a pass it saves the *AC-66 leg record* with `leg` = `rebuild` and `outcome` = `passed`. Once its precondition holds it always starts the rebuild, so a run of this leg restores the three tables whatever the state of the rerun evidence. | Must |
| FR-86 | A leg whose table state is wrong (rerun leg: any of the three tables missing; rebuild leg: any of them present; both legs: a partial state with one or two of the three present) or whose snapshot is missing shall fail before it starts any job run, with a message that names the leg, every table in the wrong state and the step to take (rerun leg after the reset: run the rebuild leg; rebuild leg before the reset: run the rerun leg, then the user-run reset script). A refused leg changes no evidence file. | Must |
| FR-87 | A leg that fails after it has started its job run (job failure, unexpected MERGE metrics, counts or checksums that differ) shall leave no record with `outcome` = `passed` for that leg, also when a passing record of an earlier execution existed. | Must |
| FR-88 | The system shall provide an AC-66 verdict live test that passes only when all hold: the snapshot exists; a rerun and a rebuild leg record exist, both with `outcome` = `passed`; each record's `snapshot_saved_at_ms` equals the snapshot's `saved_at_ms`; each record's `saved_at_ms` is later than the snapshot's; the rerun record's `saved_at_ms` is earlier than the rebuild record's (the PEAK_MODEL AC-66 order, D-95); the recorded values agree with the snapshot (rerun MERGE 0 / 0 / 0 for the three tables; rebuild inserted equal to each snapshot `row_count`, 0 updated, 0 deleted; both legs' recorded counts and checksums equal to the snapshot). The verdict starts no job run. | Must |
| FR-89 | When any condition of FR-88 fails, the verdict shall fail and name every leg that is missing, failed, stale (tied to another snapshot or saved before it), out of order or inconsistent, each with the test to run next; a missing snapshot is named with the snapshot test. Each run of the verdict saves the *AC-66 verdict record* with the outcome and the list of problems, so a failing verdict leaves evidence too. | Must |
| FR-90 | The verdict rule (FR-88, FR-89) and the precondition rule (FR-86) shall be pure functions without SDK imports, workspace calls or clock reads, taking the records and the table existence as input, so that they run in CI on fixture records. A malformed input (unparseable JSON, a missing field, a non-integer `saved_at_ms`, an unknown `leg` or `outcome`) gives a failing verdict that names the file, never an exception. | Must |
| FR-91 | The snapshot test `test_ac66_before_rebuild_snapshot` and its file `out/evidence/ac66_before_rebuild.json` (with the shipped `saved_at_ms` and per-table `row_count` and `checksum`) shall keep their names and content, so that the reset script's snapshot guard is unchanged. Saving a new snapshot makes every leg record of an older snapshot stale under FR-88. | Must |
| FR-92 | The combined test `test_ac66_after_rerun_and_rebuild_checksums_equal` shall be removed (Q-32), and no AC-66 test shall choose its assertions from the table state. Every new integration test name matches the shipped layout rule `^test_ac(\d{2,3})_`, and `tests/test_integration_layout.py` is changed only as far as the new names require (C-24). | Must |
| FR-93 | `docs/runbooks/peak_model.md` sections 8 (Evidence order) and 9 (Reset), the module docstring of `tests/integration/test_peak_data.py`, and the docstring and printed next step of `scripts/reset_peak_model_outputs.py` shall state the order snapshot, rerun leg, user-run reset with `--confirm`, rebuild leg, verdict, with selectors that pick exactly one AC-66 test each. No text says that a daily job run is needed between the reset and the rebuild leg, no text calls the rebuild leg optional, and section 9 states that the rebuild leg starts the four data tasks itself. | Must |
| FR-94 | The feature shall change no file under `src/`, `resources/`, `notebooks/` and no `databricks.yml`; the reset script's guard code and its unit tests `tests/test_peak_reset_script.py` stay as at `v0.6.0`; the archived PEAK_MODEL DEFINE and DESIGN are not edited. | Must |
| FR-95 | The live sequence of AC-162 to AC-164 shall run on `dev` with the user running the reset, and the BUILD_REPORT shall hold, for each step, the test outcome and the values of the leg and verdict records (snapshot `saved_at_ms`, MERGE metrics, counts, run ids, the verdict problems). | Must |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-43 | Time handling | Every timestamp in a leg or verdict record is UTC text matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` or `null`; `saved_at_ms` and `snapshot_saved_at_ms` are epoch milliseconds (zone-free). Ordering checks use `saved_at_ms` only, never a local time text. |
| NFR-44 | Cost | Each leg that passes its precondition starts exactly 1 job run (the four data tasks), as the shipped test did per mode; a refused leg and the verdict start 0 job runs and 0 pipeline updates. The full live sequence of AC-162 to AC-164 starts 2 job runs. |
| NFR-45 | Reproducibility | The verdict and precondition rules are deterministic: the same inputs give the same output, byte-equal after `json.dumps(..., sort_keys=True)`; the verdict record differs between two runs on the same files only in its own `saved_at_ms`. They import no Databricks SDK module. |
| NFR-46 | Security | No leg or verdict record, and no failure message, holds a token, a secret value or a workspace URL: no value contains `https://`, `dapi` or `Bearer`. Records stay under the git-ignored `out/evidence/`. |
| NFR-47 | Compatibility | `pytest` without the integration marker reports 0 failures, including every shipped test; `scripts/check_specs.py` reports 0 errors; the integration collection (`-m integration`) selects the snapshot test, both leg tests and the verdict test in `test_peak_data.py`. |

---

## Data Contracts

This feature writes no table and changes no shared contract under `docs/contracts/`. It reads the
three PEAK_MODEL tables (their contracts are unchanged) and the job run outputs, and writes local
evidence files. Contracts are inline because no other feature shares them. Field names follow
`docs/conventions/naming.md` (`<event>_ts` for UTC timestamps) and the shipped evidence files
(`saved_at_ms`, `run_id`, `row_count`, `checksum`, `merge`).

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| AC-66 snapshot, `out/evidence/ac66_before_rebuild.json` (read; written by the unchanged snapshot test) | PEAK_MODEL | One snapshot of the three tables (the latest; overwritten per execution) | `saved_at_ms` | Written by `test_ac66_before_rebuild_snapshot` before the legs | Inline: `saved_at_ms`; `silver_weather`, `features`, `labels`, each `row_count` and `checksum` (shipped) |
| AC-66 rerun leg record, `out/evidence/ac66_rerun_leg.json` (written) | AC66_BOTH_LEGS | One execution of the rerun leg that started its job run (the latest) | `leg`, `snapshot_saved_at_ms` | Written before the leg test ends | Inline: *AC-66 leg record* below |
| AC-66 rebuild leg record, `out/evidence/ac66_rebuild_leg.json` (written) | AC66_BOTH_LEGS | One execution of the rebuild leg that started its job run (the latest) | `leg`, `snapshot_saved_at_ms` | Written before the leg test ends | Inline: *AC-66 leg record* below |
| AC-66 verdict record, `out/evidence/ac66_verdict.json` (written) | AC66_BOTH_LEGS | One execution of the verdict test (the latest) | `snapshot_saved_at_ms` (with `saved_at_ms`) | Written before the verdict test ends, pass or fail | Inline: *AC-66 verdict record* below |
| Shipped `out/evidence/ac66_after_rebuild.json` | PEAK_MODEL (retired by this feature) | One execution of the removed combined test | none | No longer written; ignored by the verdict | None |
| Exit values of `build_weather_silver`, `build_features`, `build_labels` (read) | PEAK_MODEL | One task run | job `run_id`, task key | At task end | Inline: `merge` with integer `inserted`, `updated`, `deleted` (shipped, A-50) |
| `information_schema.tables` of the dev catalog (read) | Platform metadata | One table | `table_schema`, `table_name` | Read at the start of each leg | Inline: existence of the three tables (A-51) |
| `silver.weather_hourly`, `ml.household_features_daily`, `ml.household_labels_daily` (read; rebuilt by the job, not by the tests) | PEAK_MODEL | Shipped grain: one row per UTC hour; one row per household and date (twice) | Shipped keys | Daily job | `docs/contracts/` (unchanged) |

**AC-66 leg record** (D-94; one JSON object per file):

| Field | Type | Meaning |
|---|---|---|
| `leg` | `rerun` or `rebuild` | Which leg wrote the record |
| `outcome` | `passed` or `failed` | `passed` only after every assertion of the leg held (FR-87) |
| `snapshot_saved_at_ms` | integer | `saved_at_ms` of the snapshot the leg compared against (FR-91) |
| `run_id` | integer or null | Job run id of the leg's run of the four data tasks |
| `started_ts`, `ended_ts` | UTC text or null | Start and end of that job run |
| `tables_present_at_start` | object of three booleans | Existence of each of the three tables before the run |
| `merges` | object | Per table key (`silver_weather`, `features`, `labels`): `inserted`, `updated`, `deleted` from the task exit value |
| `after` | object | Per table key: `row_count` and `checksum` after the run |
| `saved_at_ms` | integer | Added by the shipped `Evidence.save` |

**AC-66 verdict record** (D-94):

| Field | Type | Meaning |
|---|---|---|
| `verdict` | `pass` or `fail` | FR-88 |
| `problems` | list of strings | Empty on `pass`; one entry per failed condition, naming the leg or the snapshot and the test to run (FR-89) |
| `snapshot_saved_at_ms` | integer or null | Of the snapshot read |
| `rerun_saved_at_ms`, `rebuild_saved_at_ms` | integer or null | Of the leg records read; `null` when missing or unreadable |
| `saved_at_ms` | integer | Added by the shipped `Evidence.save` |

---

## Acceptance Criteria

**Unit** criteria run in CI without the Databricks SDK. **Live** criteria run on the deployed
`dev` target with the integration marker, in the order AC-162, AC-163, AC-164; their evidence goes
into the BUILD_REPORT. AC-155, AC-163 and AC-164 together are PEAK_MODEL F-15 DC-01.

| ID | Level | Given | When | Then |
|---|---|---|---|---|
| AC-154 | Unit | A fixture snapshot (`saved_at_ms` 1000; counts 21,165 / 36,480 / 36,480 and three checksums), a rerun record (`passed`, `snapshot_saved_at_ms` 1000, `saved_at_ms` 2000, MERGE 0 / 0 / 0, counts and checksums equal to the snapshot) and a rebuild record (`passed`, `snapshot_saved_at_ms` 1000, `saved_at_ms` 3000, inserted 21,165 / 36,480 / 36,480, 0 updated, 0 deleted, counts and checksums equal) | The verdict rule runs twice | Both results are `pass` with an empty `problems` list and byte-equal after `json.dumps(..., sort_keys=True)`; the verdict record carries `snapshot_saved_at_ms` 1000, `rerun_saved_at_ms` 2000, `rebuild_saved_at_ms` 3000; no value contains `https://`, `dapi` or `Bearer` |
| AC-155 | Unit | The AC-154 fixtures with (a) the rebuild record absent, (b) the rerun record absent, (c) both absent, (d) the snapshot absent | The verdict rule runs | Each result is `fail`; the problems name (a) the rebuild leg and its test, and not the rerun leg; (b) the rerun leg and its test, and not the rebuild leg; (c) both legs; (d) the snapshot and `test_ac66_before_rebuild_snapshot` |
| AC-156 | Unit | The AC-154 fixtures with one change each: (a) rerun `snapshot_saved_at_ms` 900; (b) rebuild `saved_at_ms` 900 (before the snapshot); (c) rerun `saved_at_ms` 4000 (after the rebuild); (d) rebuild `outcome` `failed`; (e) rerun MERGE `updated` 1 for `features`; (f) rebuild `inserted` 21,164 for `silver_weather`; (g) a rebuild `after` checksum that differs from the snapshot; (h) a rerun file that is not valid JSON; (i) a rebuild record without `saved_at_ms`; (j) `leg` `rebuild` in the rerun file | The verdict rule runs | Each result is `fail` without an exception, and the problems name exactly the leg concerned: stale for (a) and (b), out of order for (c), failed for (d), inconsistent for (e) to (g), unreadable or malformed with the file name for (h) to (j) |
| AC-157 | Unit | All eight existence states of the three tables (all present, none present, and the six partial states), with and without the snapshot | The precondition rule runs for each leg | The rerun leg is allowed only with all three present and the snapshot; the rebuild leg only with none present and the snapshot; every refusal names the leg, each table in the wrong state (or the missing snapshot) and the next step (FR-86); the six partial states refuse both legs |
| AC-158 | Unit | Each leg procedure (the leg test body or a helper it calls) with a fake job runner and fake table reads, a snapshot as in AC-154, and a passing record of an earlier execution already in a temporary evidence folder | The leg runs with (a) the expected MERGE metrics and equal checksums; (b) for the rerun leg `inserted` 1, for the rebuild leg `inserted` 0 on one table; (c) the fake runner raising; (d) a wrong table state | (a) the leg passes and writes a record with all *AC-66 leg record* fields, `outcome` `passed` and `snapshot_saved_at_ms` 1000, with timestamps matching the NFR-43 pattern; (b) and (c) the leg fails and no record with `outcome` `passed` remains for that leg; (d) the leg fails before the fake runner is called (0 calls) and the earlier record is byte-equal to before |
| AC-159 | Unit | `tests/integration/test_peak_data.py` and `tests/test_integration_layout.py` at the feature commit | The modules are parsed and the integration tests are collected with `-m integration -o addopts=` | `test_ac66_before_rebuild_snapshot`, one rerun-leg test, one rebuild-leg test and one verdict test exist and are collected, each name matches `^test_ac(\d{2,3})_` and starts with `test_ac66_`; `test_ac66_after_rerun_and_rebuild_checksums_equal` is absent; no function in the module calls the table-existence read and then branches on its result to choose MERGE expectations; the shipped layout tests pass |
| AC-160 | Unit | `docs/runbooks/peak_model.md`, the module docstring of `test_peak_data.py` and `scripts/reset_peak_model_outputs.py` at the feature commit | The texts are read | In section 8 and in the docstring the AC-66 lines name, in this order, the snapshot test, the rerun leg, `reset_peak_model_outputs.py --confirm`, the rebuild leg and the verdict; each `-k` selector for AC-66 selects exactly one collected test; sections 8 and 9 contain no "then the daily job" (or "run the daily job") between the reset and the rebuild leg, and no "optional" next to the rebuild leg; section 9 names the rebuild leg and the verdict and says the rebuild leg starts `ingest_weather`, `build_weather_silver`, `build_features` and `build_labels` itself; the script's printed next step selects the rebuild leg only, and its usage docstring does not say to run the daily job after `--confirm` |
| AC-161 | Unit | The repository at the feature commit and tag `v0.6.0` (present locally) | The trees and the reset script are compared, then `pytest` (no integration marker) and `scripts/check_specs.py` run | Every file under `src/`, `resources/`, `notebooks/`, and `databricks.yml`, equals `v0.6.0` byte for byte; in `scripts/reset_peak_model_outputs.py` the unparsed AST of `plan`, `targets`, `Target`, `ResetRefused`, `Warehouse`, `EXPECTED_ROWS` and `SNAPSHOT` equals `v0.6.0`, and in `main` only string constants differ; `tests/test_peak_reset_script.py` and the archived `DEFINE_PEAK_MODEL.md` and `DESIGN_PEAK_MODEL.md` equal `v0.6.0`; `pytest` reports 0 failures; `check_specs.py` reports 0 errors |
| AC-162 | Live | The `dev` target deployed; `smart_meter_ingestion` idle; the three tables present; `test_ac66_before_rebuild_snapshot` has just passed | The rebuild-leg test runs | It fails before any job run (0 new runs of `smart_meter_peak_model` between its start and end, read from the Jobs API), its message names the three present tables and the reset script, and `out/evidence/ac66_rebuild_leg.json` is byte-equal to before (or still absent) |
| AC-163 | Live | The state after AC-162 | The rerun-leg test runs, then the verdict test | The rerun leg passes: MERGE 0 / 0 / 0 for `silver_weather`, `features` and `labels`, counts and checksums equal to the snapshot, and its record has `outcome` `passed` and `snapshot_saved_at_ms` equal to the snapshot's `saved_at_ms`. The verdict fails, its message and its record's `problems` name the rebuild leg (missing or stale) and do not name the rerun leg (PEAK_MODEL F-15 DC-01, first half) |
| AC-164 | Live | The state after AC-163; the user ran `scripts/reset_peak_model_outputs.py` as a dry run, then with `--confirm`, and it dropped exactly the three tables | The rerun-leg test runs, then the rebuild-leg test, then the verdict test | The rerun leg fails before any job run (0 new runs) naming the three missing tables, and `ac66_rerun_leg.json` is byte-equal to its AC-163 content; the rebuild leg passes: inserted 21,165 / 36,480 / 36,480, 0 updated, 0 deleted, counts and checksums equal to the snapshot; the verdict passes with an empty `problems` list and `snapshot_saved_at_ms` < `rerun_saved_at_ms` < `rebuild_saved_at_ms` (PEAK_MODEL F-15 DC-01, second half). The values of the three records and both run ids are copied into the BUILD_REPORT |

### Traceability (FR and NFR to AC)

| Requirement | Covered by |
|---|---|
| FR-84 | AC-158, AC-163 |
| FR-85 | AC-158, AC-164 |
| FR-86 | AC-157, AC-158, AC-162, AC-164 |
| FR-87 | AC-158 |
| FR-88 | AC-154, AC-156, AC-163, AC-164 |
| FR-89 | AC-155, AC-156, AC-163 |
| FR-90 | AC-154, AC-155, AC-156, AC-157 |
| FR-91 | AC-156 (a, b), AC-161, AC-163 |
| FR-92 | AC-159 |
| FR-93 | AC-160 |
| FR-94 | AC-161 |
| FR-95 | AC-162, AC-163, AC-164 |
| NFR-43 | AC-154, AC-158 |
| NFR-44 | AC-158 (d), AC-162, AC-164 (run counts read from the BUILD_REPORT rows) |
| NFR-45 | AC-154, AC-161 |
| NFR-46 | AC-154 |
| NFR-47 | AC-159, AC-161 |

Coverage of the required kinds: correctness AC-154, AC-163, AC-164; idempotency and reprocessing
AC-154 (same inputs twice), AC-163 (rerun with no new input changes 0 rows), AC-164 (rebuild from
Bronze equals the first build), AC-158 (d) and AC-162 (a refused leg changes nothing); data quality
of the evidence (stale, out of order, inconsistent, malformed) AC-156; failure paths AC-155,
AC-156, AC-157, AC-158 (b, c), AC-162, AC-163 (verdict fails with one leg).

---

## Decisions and Open Items

### Derived in this phase (not yet confirmed by the user)

| ID | Statement | Derived from | Where it is used |
|---|---|---|---|
| D-92 | Release v0.7.0 (minor); package version stays 0.4.1, as in v0.5.0 and v0.6.0, because no file under `src/` changes. Reason for minor rather than patch: the operator interface of the AC-66 evidence changes incompatibly (the combined test and the `-k "ac66_after"` command go away, and a one-leg sequence that was green now fails), which in a 0.x SemVer project is a minor change; AC97_TIMING_EVIDENCE was a patch (v0.4.1) because it added evidence without changing any pass criterion or command. PEAK_MODEL F-15 also names "next minor release after v0.6.0" | PEAK_MODEL F-15 target; CHANGELOG 0.4.1 to 0.6.0 | Metadata, Scope; Q-34 |
| D-93 | Small feature cycle without a BRAINSTORM: the follow-up triage gives E6 `No` (the AC-66 tests are under `tests/integration/`), so the CHANGE track does not apply | `F_PEAK_MODEL_15.md` Triage | Metadata |
| D-94 | Evidence file names and the field sets of the *AC-66 leg record* and *AC-66 verdict record*; one file per name, overwritten by the next execution, as the shipped evidence files | Shipped `Evidence` pattern; AC97_TIMING_EVIDENCE D-61 | Data Contracts, FR-84, FR-85, FR-89 |
| D-95 | The verdict requires the rerun leg before the rebuild leg, as PEAK_MODEL AC-66 reads ("run again with no new input, then rebuild ... after their outputs are dropped") and as the reset needs the tables present. A rerun after a rebuild would also show idempotency, but it is not the order the AC names | PEAK_MODEL AC-66; reset guard (tables must exist with the expected counts) | FR-88, AC-156 (c), AC-164 |
| D-96 | A leg is tied to a snapshot by the snapshot's shipped `saved_at_ms`; a new snapshot makes older leg records stale without deleting them | Shipped `Evidence.save`; PEAK_MODEL F-15 Self-Review (stale files) | FR-88, FR-91, AC-156 |
| D-97 | A leg in the wrong table state refuses before any job run and leaves the evidence untouched; a partial state (one or two tables present) refuses both legs, because neither PEAK_MODEL AC-66 leg describes it | PEAK_MODEL AC-66; NFR-44 | FR-86, AC-157, AC-162 |
| D-98 | The verdict is a live (integration-marked) test, because it reads the local evidence of the live sequence; it fails, never skips, when evidence is missing. Its logic is a pure rule, so CI proves it on fixtures | Golden rule 3; FR-90 | FR-88 to FR-90, AC-154 to AC-156 |

### Questions for the user

| ID | Question | Recommended answer |
|---|---|---|
| Q-32 | Remove the combined test `test_ac66_after_rerun_and_rebuild_checksums_equal`, or keep it as an alias? | Remove it: a test that passes on either leg is the defect, and the verdict replaces it. FR-92 and AC-159 are written for removal. **Answered 2026-11-09 by the user: remove it** |
| Q-33 | Is the live run of both legs (with the user-run reset that drops the three dev tables) required for this feature's `/ship`, or are the rerun-leg-alone failure (AC-163) and the unit proof (AC-154 to AC-158) enough? | Both, as PEAK_MODEL F-15 asks ("rerun it to confirm"). AC-164 is a Must; without it the BUILD_REPORT marks AC-164 not run and the release waits. **Answered 2026-11-09 by the user: both legs live before `/ship`** |
| Q-34 | Release level: v0.7.0 (minor, D-92) or v0.6.1 (patch, the AC97_TIMING_EVIDENCE precedent)? And should the package version stay 0.4.1? | v0.7.0, package version unchanged (D-92). **Answered 2026-11-09 by the user: v0.7.0, package version 0.4.1** |

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-41 | Test names under the layout rule `^test_ac(\d{2,3})_` and golden rule 3: keep the `test_ac66_` prefix for the legs and the verdict and name this feature's ACs after it (as `test_ac97_ac106_...`), for example `test_ac66_ac163_rerun_leg_...`; choose names so that each runbook `-k` selector picks exactly one test (FR-93); update the collection assertion of `test_integration_layout.py`, which today expects `test_peak_data.py::test_ac66_after_`, and decide whether `EXPECTED_ACS` gains 162 to 164. Unit test names `test_ac154_` to `test_ac161_` |
| OD-42 | Location and name of the pure rules (precondition, verdict, record builder): a module under `tests/` importable by the unit tests and the live tests, with a basename unique under `tests/` (INGESTION_GUARD D-01), not under `src/` (FR-94) |
| OD-43 | How FR-87 is met: remove the leg's file before the job run starts, or write an `outcome` `failed` record in a `finally`; and whether a refused leg (FR-86) may still write nothing, as required, under the chosen mechanism |
| OD-44 | Whether the reset script should also refuse when there is no passing rerun record for the current snapshot, which would enforce D-95 before the drop. That changes a guard and its unit tests (FR-94, AC-161) and needs the user's OK; default: no, the verdict enforces the order |
| OD-45 | Whether the verdict also re-reads the three tables' counts and checksums live (catches a change after the rebuild leg, costs SQL statements) or reads the files only (default, NFR-44); and whether the snapshot test should delete older leg and verdict files (default: no, D-96 detects them) |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 to C-07 | Constraint | Inherited from METER_INGESTION: Free Edition serverless only, daily quota, no secrets in code, UTC end to end | Yes |
| C-22 | Constraint | Tests, docs and specs only: no change under `src/`, `resources/`, `notebooks/` or to `databricks.yml`; the reset script's guards and their unit tests unchanged; the archived PEAK_MODEL DEFINE and DESIGN not edited (E4). At `/ship` the PEAK_MODEL SHIPPED row PEAK_MODEL F-15 and the follow-up file are updated | Yes (follow-up triage, E1 to E5 and E7 `Yes`) |
| C-23 | Constraint | `scripts/reset_peak_model_outputs.py --confirm` drops three dev tables and is run by the user only, never by an agent (its docstring and runbook section 9). AC-164 therefore needs the user in the live session; until the rebuild leg passes, the dev feature and label tables are absent and scoring on `dev` cannot run | Yes |
| C-24 | Constraint | `tests/test_integration_layout.py` accepts integration test names `^test_ac(\d{2,3})_` only and its collection check asserts `test_peak_data.py::test_ac66_after_`; renaming the AC-66 tests breaks it unless OD-41 changes it in the same commit | Yes (code reading, 2026-11-09) |
| C-25 | Constraint | `out/evidence/` is git-ignored and local to one checkout; the snapshot, both legs and the verdict must run from the same checkout; the durable record of a live run is the BUILD_REPORT | Yes |
| A-49 | Assumption | `saved_at_ms` comes from the local wall clock (`time.time()` in `Evidence.save`); the clock does not step back between the snapshot, the two legs and the verdict, so the order checks of FR-88 hold. The legs are minutes apart (the 2026-10-22 rebuild took 226 s), far above usual clock corrections | Pending: holds on one machine with NTP; a step back would make the verdict fail (safe direction), not pass |
| A-50 | Assumption | The exit values of `build_weather_silver`, `build_features` and `build_labels` keep the shipped `merge` object with integer `inserted`, `updated` and `deleted` | Validated by the live runs of 2026-10-22 (rerun 0 / 0 / 0; rebuild 21,165 / 36,480 / 36,480) and held by C-22 |
| A-51 | Assumption | Right after the reset, `information_schema.tables` reports the three tables as absent, and right after a rebuild as present, with no lag that would mislead the precondition rule | Validated once: the shipped test read the absence after the reset on 2026-10-22 (`rebuild_after_reset` true) |
| A-52 | Assumption | The rebuild from Bronze reproduces the snapshot exactly (counts and checksums), as PEAK_MODEL NFR-10 states | Validated once live (2026-10-22) and locally by `test_ac66_recomputation_with_another_partitioning_is_bitwise_equal` |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | One named gap (PEAK_MODEL F-15) with the observed event (2026-10-22, one-leg green run), its cause (mode chosen from table state) and its cost (a release gate that reports half an AC as passed) |
| Users | 3 | Operator, the user who runs the reset, build report author and reviewer, CI, and the unchanged jobs, each with the place they read the outcome |
| Scope | 3 | Test-only plus docs, with the reset guards and archived documents fenced off; Q-32 (remove the combined test) and Q-33 (live both legs for `/ship`) answered by the user on 2026-11-09 |
| Acceptance criteria | 3 | Eleven criteria: eight unit (verdict pass, missing, stale and malformed evidence, precondition states, leg failure paths with fakes, names, docs, no-change) and three live in a fixed order that is PEAK_MODEL F-15 DC-01; every FR and NFR covered |
| Constraints | 2 | The live half depends on the user-run reset (C-23); A-49 (clock order) is pending; OD-44 may touch a guard |
| **Total** | **14/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The verdict trusts local files. A hand-edited record would pass FR-88; the cross-checks of the
    recorded values against the snapshot (AC-156 e to g) catch inconsistent records, not forged
    ones. OD-45 can add a live re-read of the tables at a cost in SQL.
  - Ordering rests on one machine's wall clock (A-49). A clock step back fails the verdict, which
    is safe but confusing; the message must say which order check failed.
  - The archived PEAK_MODEL DESIGN Test Strategy row for AC-66 keeps naming the removed test.
    Archived documents are frozen (E4), so this DEFINE and the coming DESIGN are the only record
    that the mechanism changed.
  - AC-158 asks for leg procedures that run with fakes; that steers `/design` towards a testable
    leg body, which is intended but narrows the options.
- **Risks:**
  - AC-164 leaves `dev` without the feature and label tables between the reset and a passing
    rebuild leg; a failing rebuild leg blocks scoring until it is fixed or the daily job rebuilds
    the tables (C-23).
  - Renaming the tests breaks the shipped layout test and the reset script's printed hint unless
    the DESIGN manifest lists both (C-24, FR-93).
  - Q-33 makes AC-164 a release gate: until the user runs the reset, the follow-up stays
    `In Progress` and v0.7.0 waits.
- **Trade-offs:**
  - Three tests instead of one cost the operator two more commands, in exchange for an AC that
    cannot be green on one leg and a cheap refusal in the wrong state.
  - The verdict as a live test (D-98) keeps it next to the evidence it reads; the unit tests of
    the pure rule carry the proof in CI.
  - Requiring the PEAK_MODEL AC-66 order (D-95) rejects a rebuild-then-rerun sequence that would
    also show idempotency, to keep the AC text as the single rule.
- **What I would do differently:** Have PEAK_MODEL write one test per leg named in an AC from the
  start, so that no test could choose its expectations from the state it finds.
- **Next improvement:** In `/design`, settle OD-41 first (names decide the layout test, the runbook
  selectors and the script hint), then OD-43 (it decides how AC-158 b and c are met).

---

## Next Step

`/design .claude/sdd/features/DEFINE_AC66_BOTH_LEGS.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-11-09 | Created: FR-84 to FR-95, NFR-43 to NFR-47, AC-154 to AC-164, C-22 to C-25, A-49 to A-52, D-92 to D-98 (derived), Q-32 to Q-34, OD-41 to OD-45. Status `Ready for Design` | Phase 1 of the SDD workflow, from follow-up PEAK_MODEL F-15 | `/design` can start; Q-32 to Q-34 await the user's answers, and the requirements are written for the recommended answers |
| 2026-11-09 | Q-32, Q-33 and Q-34 answered by the user with the recommended answers; Scope 3, clarity 14/15 | User decisions | None: the requirements were written for these answers |
