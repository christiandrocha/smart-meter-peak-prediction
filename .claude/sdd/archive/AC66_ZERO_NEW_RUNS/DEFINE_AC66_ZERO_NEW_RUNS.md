# DEFINE: AC-66 Zero New Runs

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_ZERO_NEW_RUNS |
| **Date** | 2026-11-10 |
| **Author** | Christian |
| **Source** | Follow-up AC66_BOTH_LEGS F-03 (`.claude/sdd/follow-ups/F_AC66_BOTH_LEGS_03.md`: triage full cycle because E6 is `No`, done criterion DC-01; no BRAINSTORM: small feature cycle); archived AC66_BOTH_LEGS DEFINE (FR-86, FR-87, FR-90, NFR-44, AC-158, AC-161, AC-162, AC-164, D-92, D-94, D-97), DESIGN (DA-47, G-46, G-47, Rule API, live plan, Self-Review), BUILD_REPORT (AC-162 and AC-164 rows, live run record, AC66_BOTH_LEGS I-02, Self-Review) and SHIPPED_2026-11-09 (Follow-ups row AC66_BOTH_LEGS F-03, lesson "Spec (live assertions)", lesson "Build review (side-effect order)"); code read on 2026-11-10: `tests/support/ac66_rules.py` (`run_leg`, `precondition`), `tests/integration/test_peak_data.py` (AC-66 section), `tests/integration/conftest.py` (`workspace`, `peak_job`, `PeakRunner`, `full_runs`), `tests/test_ac66_rules.py`, `tests/test_ac66_legs_docs.py` (AC-159 and AC-161 checks, `V060_*` constants), `resources/smart_meter_peak_model.job.yml`, `databricks.yml`, `docs/runbooks/peak_model.md` (sections 8 and 9) |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: v0.7.1 (patch, D-99; confirmed by the user in Q-35). This feature closes
AC66_BOTH_LEGS F-03.

**ID numbering.** IDs continue the project-wide series: FR-96, NFR-48, AC-165, C-26, A-53, D-99,
Q-35 and OD-46 (last used: FR-95, NFR-47, AC-164, C-25, A-52, D-98, Q-34 and OD-45 in
AC66_BOTH_LEGS; OD-46 was named there as not used). Checked on 2026-11-10 with a repository-wide
search for higher numbers of each series (none found). Every ID of another spec is written with
that spec's name in front; unprefixed IDs are this feature's own.

---

## Problem Statement

AC66_BOTH_LEGS AC-162 and AC66_BOTH_LEGS AC-164 claim that a refused AC-66 leg (the rebuild leg
with the three tables present, the rerun leg with them dropped) starts no job run, and
AC66_BOTH_LEGS NFR-44 claims that a leg that passes starts exactly one. The live leg tests do not
check either claim: on 2026-11-09 the operator read the newest run of `smart_meter_peak_model` with
the CLI before and after each refusal (`457575248055458` and `323617648524483`, unchanged), and
AC66_BOTH_LEGS AC-158 (d) proves the "no runner call" order only on fakes. A regression that starts
a run and then refuses (or a leg that starts a second run) would pass every automated check and be
seen only by an operator who looks, at a cost of one unplanned job run per occurrence and a
release gate whose "0 new runs" rests on a manual reading.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Live-test operator (runs the AC-66 evidence order on `dev`) | A refusal that proves by itself that it started no run, and a pass that proves it started exactly its own run, without CLI reads around each step | The leg tests' failure message (refusal) and reported line (pass); `docs/runbooks/peak_model.md` sections 8 and 9 |
| User who runs the reset (the only person allowed to drop the three tables) | Know which live step needs the reset, and that only one does | AC-175, runbook section 9 |
| Build report author and release reviewer | Copy the run ids and counts from the test output into the BUILD_REPORT instead of an operator reading | The refusal messages and pass lines of AC-173 to AC-175 |
| CI (`pytest` without the integration marker) | Prove the run-count rule and the side-effect order of `run_leg` without a workspace | Unit tests on fakes (AC-165 to AC-172) |
| Scheduled jobs `smart_meter_peak_model`, `smart_meter_ingestion`, `smart_meter_peak_model_training` | No change in behaviour; two more read requests per leg against the Jobs API | Unchanged notebooks, bundle and library (C-26) |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| A refusal proves "0 new runs" itself | Refusals of either leg (CI fakes and live) that report success while a run of the peak job id was started between the two reads | 0 (AC-166, AC-167, AC-173, AC-175) |
| A pass proves "exactly its own run" | Passing legs for which the new runs of the peak job id are not exactly the one run id in the leg record | 0 (AC-168, AC-174, AC-175); Q-37 answered Yes |
| No operator CLI reads of the run list | `databricks jobs list-runs` commands in the live plan of this feature's DESIGN and BUILD_REPORT used for AC-173 to AC-175 evidence | 0 |
| No extra job runs | Job runs of the full live sequence of AC-173 to AC-175 | 2 (as AC66_BOTH_LEGS NFR-44) |
| Shipped behaviour kept | AC66_BOTH_LEGS unit tests (AC-154 to AC-161) that fail, or that lose an assertion | 0 (AC-171) |
| No production change | Byte differences of `src/`, `resources/`, `notebooks/`, `databricks.yml` against tag `v0.6.0` | 0 (AC-171, D-100) |

---

## Scope

**In scope:**
- A run-list read of the job `smart_meter_peak_model` (by its job id only) at the start of each leg
  and after its refusal or its job run, injected into `run_leg` so that the rules module keeps the
  AC66_BOTH_LEGS FR-90 property: no SDK, no I/O, no clock (FR-96, FR-100).
- The refusal path: the leg's own failure message states the count of new runs and the newest run
  id before and after; a refusal during which a run started fails with a different message
  (FR-97).
- The pass path: a passing leg also checks that exactly one new run exists and that it is the
  leg's own (FR-98; Q-37).
- Failure of either read: never reported as a clean refusal or a pass (FR-99).
- Unit tests on fakes in `tests/test_ac66_rules.py`, extending the AC66_BOTH_LEGS AC-158 style,
  including the order of the side effects (AC-165 to AC-169), a shape check of the two live leg
  tests (AC-170), compatibility and no-change checks (AC-171), and docs checks (AC-172).
- Text changes: runbook sections 8 and 9 and the module docstring of
  `tests/integration/test_peak_data.py` (FR-103).
- Live evidence on `dev` (FR-104): two live criteria without the reset (AC-173, AC-174) and one with
  the user-run reset (AC-175; Q-38).
- At `/ship`: CHANGELOG entry for the release of Q-35; the follow-up file
  `F_AC66_BOTH_LEGS_03.md` closed; the SHIPPED Follow-ups row AC66_BOTH_LEGS F-03 updated to point
  to this feature.

**Out of scope:**
- Any change under `src/`, `resources/`, `notebooks/` or to `databricks.yml`, and any change to
  `scripts/reset_peak_model_outputs.py` (C-26).
- Changing the leg or verdict record fields or file names of AC66_BOTH_LEGS D-94 (D-103; OD-48
  may revisit it with the user's OK).
- Telling a foreign run apart by its trigger, creator or task list (Q-36 recommends against it).
- A test-side check that the leg file is byte-equal after a refusal: AC66_BOTH_LEGS AC-158 (d)
  proves it in CI and it is not part of AC66_BOTH_LEGS F-03. Not scheduled.
- AC66_BOTH_LEGS F-01 (exception chaining in `run_leg`) and AC66_BOTH_LEGS F-02 (atomic
  `Evidence.save`), unless the user answers Q-39 Yes.
- Moving the AC66_BOTH_LEGS AC-161 pin from `v0.6.0` to `v0.7.0` (D-100).
- "0 new runs" checks for other live tests that refuse (for example PEAK_MODEL_CONCURRENCY
  refusals). Not scheduled.

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-96 | Each AC-66 leg shall read the run list of the job `smart_meter_peak_model`, selected by the job id that the `peak_job` fixture resolves and by no other job id, twice: the first read before any other side effect of the leg (before the snapshot and table-existence reads), the second after the refusal decision (refusal path) or after the leg's job run has ended (pass path). Each read includes runs in every life-cycle state (pending, running, finished). A run is *new* when its run id is in the second read and not in the first (D-102). | Must |
| FR-97 | A leg refused under AC66_BOTH_LEGS FR-86 shall fail with a message that keeps the AC66_BOTH_LEGS G-46 refusal text and adds `0 new runs of smart_meter_peak_model` and the newest run id of the first and of the second read (or `none` when the job has no run). When one or more new runs are found, the leg shall fail with a message whose first line names the leg, does not contain `refused before any job run`, and lists every new run id. In both cases the evidence files are unchanged (AC66_BOTH_LEGS FR-86 kept). | Must |
| FR-98 | A leg that started its job run shall pass only when the new runs are exactly one run and its run id equals the leg's run id; otherwise it fails as in AC66_BOTH_LEGS FR-87 (no record with `outcome` `passed` remains for that leg) with a message that lists every new run id and the leg's run id. On a pass, the leg reports one line that contains `1 new run of smart_meter_peak_model` and the run id, visible in the test output. Q-37 answered Yes by the user on 2026-11-10. | Must |
| FR-99 | When the first read raises or returns a value that is not a list of integer run ids, the leg shall fail before the table-existence read, the preflight, the record removal and the runner, with a message that says the run list could not be read, and change no evidence file. When the second read raises or returns such a value, the leg shall fail with a message that says the count of new runs could not be confirmed and does not contain `0 new runs`; on the refusal path the evidence files are unchanged, on the pass path the leg's record has `outcome` `failed`. | Must |
| FR-100 | The comparison of the two reads (the set of new run ids and the decision "0 new runs" or "exactly the leg's run") shall be a pure, total function in `tests/support/ac66_rules.py` without SDK imports, workspace calls, file access or clock reads; it never raises on any input. The run-list read is an injected callable of `run_leg`, and both live leg tests pass a reader bound to the peak job id. | Must |
| FR-101 | The shipped AC66_BOTH_LEGS behaviour shall be kept: the four AC-66 live test names and the four runbook selectors; the evidence file names and the fields of the *AC-66 leg record* and *AC-66 verdict record* (AC66_BOTH_LEGS D-94); the refusal text start `AC-66 <leg> leg refused before any job run:` for a refusal with 0 new runs; every test function of `tests/test_ac66_rules.py` and `tests/test_ac66_legs_docs.py` at tag `v0.7.0` kept by name with no assertion removed (calls may gain the new reader argument). | Must |
| FR-102 | The feature shall change no file under `src/`, `resources/`, `notebooks/`, no `databricks.yml` and not `scripts/reset_peak_model_outputs.py`; `_state`, `_table_exists`, `SNAPSHOT_TABLES`, `DATA_TASKS` and `test_ac66_before_rebuild_snapshot` in `test_peak_data.py` stay as hashed by AC66_BOTH_LEGS AC-161; the AC66_BOTH_LEGS AC-161 constants and tag stay as at `v0.7.0` (D-100). | Must |
| FR-103 | `docs/runbooks/peak_model.md` (section 8 paragraph on AC-66 refusals; section 9 "If a leg refuses or fails") and the module docstring of `tests/integration/test_peak_data.py` shall state that each leg reads the runs of `smart_meter_peak_model` before and after, that a refusal fails differently when a run was started, and (per Q-37) that a pass checks for exactly its own run. No text tells the operator to read `list-runs` around an AC-66 leg. | Should |
| FR-104 | The live criteria AC-173 to AC-175 shall run on `dev` from one checkout, and the BUILD_REPORT shall hold for each step the test outcome, the refusal message or pass line with its run ids, and (for AC-175) the user's reset output. | Must |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-48 | Cost | Each leg adds exactly 2 run-list reads (one Jobs API list request each), 0 job runs and 0 SQL statements to the shipped leg; the full live sequence of AC-173 to AC-175 still starts 2 job runs (AC66_BOTH_LEGS NFR-44 unchanged). |
| NFR-49 | Security | No message or reported line of this feature holds a token, a workspace URL, a run page URL or a user name: no value contains `https://`, `dapi`, `Bearer` or `@`. Messages hold run ids, counts and the job name only. |
| NFR-50 | Reproducibility | The comparison rule is deterministic: the same two reads and leg run id give the same result, byte-equal after `json.dumps(..., sort_keys=True)`, and new run ids are listed in ascending order. The changed `tests/support/ac66_rules.py` still passes the shipped AC66_BOTH_LEGS AC-154 import and clock check unchanged (no `databricks`, `time`, `os`, `pathlib`, `subprocess`, `datetime` import; no `now`, `utcnow`, `time`, `open`, `sleep` call). |
| NFR-51 | Time handling | New runs are decided by run id only, never by comparing a run's start time with the local clock (golden rule 5, AC66_BOTH_LEGS A-49); any time shown in a message is UTC text matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`. |
| NFR-52 | Compatibility | `pytest` without the integration marker reports 0 failures, including every shipped test; `scripts/check_specs.py` reports 0 errors; `pytest -m integration -o addopts= --collect-only -k ac66 tests/integration/test_peak_data.py` collects the same four AC-66 names as at `v0.7.0`. |

---

## Data Contracts

This feature writes no table, no evidence file and no shared contract under `docs/contracts/`
(D-103). It reads one platform listing and keeps the AC66_BOTH_LEGS evidence files as they are.
Contracts are inline because no other feature shares them.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| Run list of the job `smart_meter_peak_model` (read, Jobs API) | Platform (job owned by PEAK_MODEL) | One job run | `run_id` (scoped by the peak `job_id`) | Read twice per leg: at its start and after its refusal or job run | Inline: per run, the integer `run_id`; runs in every life-cycle state; newest first (A-55). No other field is required by the rule; any field shown in a message follows NFR-49 and NFR-51 |
| AC-66 snapshot, leg records and verdict record, `out/evidence/ac66_*.json` (read and written as shipped) | AC66_BOTH_LEGS | As in the AC66_BOTH_LEGS DEFINE Data Contracts | As shipped (`saved_at_ms`; `leg`, `snapshot_saved_at_ms`) | As shipped | Inline in the archived AC66_BOTH_LEGS DEFINE; unchanged (FR-101, D-103) |
| Refusal message and pass line of a leg (test output, copied into the BUILD_REPORT) | AC66_ZERO_NEW_RUNS | One leg execution | Leg name with the newest run id of the second read | Written when the leg test ends | Inline: leg name; count of new runs; newest run id of each read (or `none`); every new run id; on the pass path the leg's run id (FR-97, FR-98) |

---

## Acceptance Criteria

**CI** criteria run in `pytest` without the Databricks SDK or a workspace, on fakes. **Live**
criteria run on the deployed `dev` target with the integration marker, in the order AC-173,
AC-174, AC-175; their evidence goes into the BUILD_REPORT. Only AC-175 needs the user-run reset.
AC-173 and AC-175 together are AC66_BOTH_LEGS F-03 DC-01. The order of the side effects is part of
the criteria (lesson "Build review (side-effect order)" of the AC66_BOTH_LEGS SHIPPED record).

| ID | Level | Given | When | Then |
|---|---|---|---|---|
| AC-165 | CI | Pairs of reads as lists of run ids: (a) `[3, 2, 1]` and `[3, 2, 1]`; (b) `[3, 2, 1]` and `[4, 3, 2, 1]`; (c) `[]` and `[7]`; (d) `[3, 2, 1]` and `[5, 4, 3, 2]` (page shifted by two new runs); (e) a second read holding `True`, `"4"`, `None`, a float or a nested list; (f) a first read that is not a list | The comparison rule runs twice on each pair, with leg run id none (refusal) and 4 (pass) | (a) 0 new runs; (b) new `[4]`, "exactly the leg's run" true for leg run 4, false for none; (c) new `[7]`; (d) new `[4, 5]` in ascending order, "exactly the leg's run" false; (e) and (f) an unreadable result naming which read, never an exception; the two results of each pair are byte-equal after `json.dumps(..., sort_keys=True)` |
| AC-166 | CI | Each leg with fakes in each wrong state of AC66_BOTH_LEGS AC-158 (d) (rerun with no table present, rebuild with all present, each leg in one partial state, each leg without the snapshot); a fake run list `[30, 20, 10]` that does not change; an earlier `passed` record of the leg in a temporary evidence folder; a call log shared by the fakes | `run_leg` runs, twice in a row | Each run raises `AssertionError` starting `AC-66 <leg> leg refused before any job run:` and containing `0 new runs of smart_meter_peak_model` and `30` as newest run of both reads; the call log is: run-list read, table-existence read, run-list read (exactly 2 run-list reads, the first before any other call, the second last); runner, state read and preflight 0 calls; the earlier record's bytes and the folder listing equal to before; the two messages are byte-equal |
| AC-167 | CI | As AC-166, but the fake table-existence read appends run id 40 to the fake run list (a leg that starts a run and then refuses) | `run_leg` runs | It raises `AssertionError` whose first line names the leg, contains `40` and `new run`, and does not contain `refused before any job run`; the earlier record's bytes and the folder listing are equal to before; runner and preflight 0 calls |
| AC-168 | CI | Each leg in its right state with the AC66_BOTH_LEGS AC-158 (a) fakes (expected merges, state equal to the snapshot), a fake run list `[30, 20, 10]`, and a call log | `run_leg` runs with (a) a runner that appends its run id 42 to the list; (b) a runner that appends 42 and a foreign 43; (c) a runner that returns run id 42 and appends nothing | (a) The leg passes, writes the AC66_BOTH_LEGS AC-158 (a) record with `run_id` 42, reports one line with `1 new run of smart_meter_peak_model` and `42`; the call log has the first run-list read before the snapshot read and the second after the runner and before the `passed` save. (b) and (c) the leg raises, its message lists the new run ids (`42, 43` or none) and `42`, the leg file has `outcome` `failed` and no record with `outcome` `passed` remains for that leg |
| AC-169 | CI | Each leg with fakes: (a) a first run-list read that raises (`RuntimeError`) or returns a non-list; (b) a refusal state with a second read that raises; (c) the right state with a second read that raises, after the runner returned run 42 | `run_leg` runs | (a) It raises with a message that says the run list could not be read; table-existence read, preflight, runner and state read 0 calls; evidence bytes and listing equal to before. (b) It raises with a message that says the count of new runs could not be confirmed and does not contain `0 new runs`; evidence unchanged. (c) It raises; the leg file has `outcome` `failed` and no record with `outcome` `passed` remains. No case reports a pass |
| AC-170 | CI | `tests/integration/test_peak_data.py` at the feature commit | The module is parsed | Both `ac66_rules.run_leg` calls pass a run-list reader; each reader is built from the `peak_job` fixture's job id and uses neither the `job` (ingestion) nor the `training_job` fixture; neither reader excludes active runs; the shipped AC66_BOTH_LEGS AC-159 test passes |
| AC-171 | CI | The repository at the feature commit, tags `v0.6.0` and `v0.7.0` present locally or the shipped golden constants | The trees are compared, then `pytest` (no integration marker) and `scripts/check_specs.py` run | Every file under `src/`, `resources/`, `notebooks/`, and `databricks.yml` equals `v0.6.0` byte for byte (AC66_BOTH_LEGS AC-161 green with its `v0.6.0` constants); `scripts/reset_peak_model_outputs.py` equals `v0.7.0`; every test function of `tests/test_ac66_rules.py` and `tests/test_ac66_legs_docs.py` at `v0.7.0` exists with the same name and at least as many `assert` statements; `RECORD_FIELDS`, `VERDICT_FIELDS`, `LEG_NAMES`, `SNAPSHOT_NAME`, `VERDICT_NAME` and the four test-name constants of `ac66_rules` equal `v0.7.0`; `pytest` reports 0 failures; `check_specs.py` reports 0 errors |
| AC-172 | CI | `docs/runbooks/peak_model.md` and the module docstring of `test_peak_data.py` at the feature commit | The texts are read | Section 9 "If a leg refuses or fails" and the docstring name the run list of `smart_meter_peak_model` read before and after a leg, and the message of a refusal during which a run started; sections 8 and 9 contain no `list-runs` in a line or paragraph that names an AC-66 leg; the shipped AC66_BOTH_LEGS AC-160 tests pass |
| AC-173 | Live | `dev` deployed from the build branch; `smart_meter_ingestion` and `smart_meter_peak_model` idle; the three tables present; `test_ac66_before_rebuild_snapshot` has just passed | The rebuild-leg test runs | It fails with the refusal message naming the three present tables and containing `0 new runs of smart_meter_peak_model` with equal newest run ids for both reads; no operator CLI read of the run list is used; the message is copied into the BUILD_REPORT (AC66_BOTH_LEGS F-03 DC-01, rebuild leg). No reset needed |
| AC-174 | Live | The state after AC-173 | The rerun-leg test runs | It passes as AC66_BOTH_LEGS AC-163 requires (MERGE 0 / 0 / 0, counts and checksums equal to the snapshot), and its reported line contains `1 new run of smart_meter_peak_model` and the run id equal to `run_id` in `out/evidence/ac66_rerun_leg.json`. No reset needed |
| AC-175 | Live | The state after AC-174; the user ran `scripts/reset_peak_model_outputs.py` as a dry run, then with `--confirm`, and it dropped exactly the three tables | The rerun-leg test runs, then the rebuild-leg test, then the verdict test | The rerun leg fails with the refusal message naming the three missing tables and containing `0 new runs of smart_meter_peak_model` with equal newest run ids for both reads (AC66_BOTH_LEGS F-03 DC-01, rerun leg); the rebuild leg passes as AC66_BOTH_LEGS AC-164 requires and reports `1 new run of smart_meter_peak_model` with the run id equal to `run_id` in `ac66_rebuild_leg.json`; the verdict passes with an empty `problems` list; the three tables are present again. The messages, lines and the reset output are copied into the BUILD_REPORT |

### Traceability (FR and NFR to AC)

| Requirement | Covered by |
|---|---|
| FR-96 | AC-166, AC-168, AC-170 |
| FR-97 | AC-166, AC-167, AC-173, AC-175 |
| FR-98 | AC-168, AC-174, AC-175 |
| FR-99 | AC-165 (e, f), AC-169 |
| FR-100 | AC-165, AC-170, AC-171 (NFR-50 check) |
| FR-101 | AC-166 (refusal text start), AC-171 |
| FR-102 | AC-171 |
| FR-103 | AC-172 |
| FR-104 | AC-173, AC-174, AC-175 |
| NFR-48 | AC-166 (exactly 2 reads), AC-168 (a); live run count read from the BUILD_REPORT rows of AC-173 to AC-175 |
| NFR-49 | AC-166 to AC-169 (each message and line checked for `https://`, `dapi`, `Bearer`, `@`) |
| NFR-50 | AC-165, AC-171 |
| NFR-51 | AC-165 (ids only); AC-166 to AC-169 (any time text matches the pattern) |
| NFR-52 | AC-171 |

Coverage of the required kinds: correctness AC-165, AC-166, AC-168 (a), AC-173 to AC-175;
idempotency and reprocessing AC-165 (same reads twice), AC-166 (a refusal run twice gives the same
message and changes nothing), AC-175 (rebuild restores the tables with exactly one run); data
quality of the read AC-165 (e, f), AC-169 (a); failure paths AC-167 (a run started during a
refusal), AC-168 (b, c), AC-169.

---

## Decisions and Open Items

### Derived in this phase (not yet confirmed by the user)

| ID | Statement | Derived from | Where it is used |
|---|---|---|---|
| D-99 | Release v0.7.1 (patch); the package version stays 0.4.1, because no file under `src/` changes (AC66_BOTH_LEGS D-92). Reason for patch: no command, selector, evidence file or record field changes, and the new checks fail only where the shipped AC66_BOTH_LEGS AC-162, AC-164 and NFR-44 already called the outcome wrong; this matches the AC97_TIMING_EVIDENCE patch precedent (evidence added, no pass criterion of a correct run changed), not the AC66_BOTH_LEGS minor case (a green one-leg sequence turned red) | AC66_BOTH_LEGS D-92; follow-up target "Next release after v0.7.0" | Metadata; Q-35 |
| D-100 | The AC66_BOTH_LEGS AC-161 pin stays on tag `v0.6.0`. Production files at `v0.7.0` equal `v0.6.0` (AC66_BOTH_LEGS AC-161 passed on the ship commit), so moving the pin would change only the tag name in a shipped test, with the same golden constants. The AC66_BOTH_LEGS SHIPPED record says the pin moves with the next feature that changes production files; this one does not | AC66_BOTH_LEGS SHIPPED, Decisions to Carry Forward and AC66_BOTH_LEGS F-04 | FR-102, AC-171 |
| D-101 | Small feature cycle without a BRAINSTORM: the follow-up triage gives E6 `No` (the leg tests are under `tests/integration/`), so the CHANGE track does not apply | `F_AC66_BOTH_LEGS_03.md` Triage | Metadata |
| D-102 | A run is new when its run id appears in the second read and not in the first; start times are not compared with the local clock. Only runs of the peak job id count, so ingestion and training runs are never counted | NFR-51; AC66_BOTH_LEGS A-49 (clock); the three jobs have different ids | FR-96, AC-165 |
| D-103 | No new evidence file and no new record field: the counts and run ids go into the refusal message and the pass line, which the BUILD_REPORT copies. A refused leg keeps writing nothing (AC66_BOTH_LEGS FR-86) | AC66_BOTH_LEGS D-94 and FR-86; AC66_BOTH_LEGS AC-158 asserts the record field set | Data Contracts, FR-97, FR-98; OD-48 |

### Questions for the user

| ID | Question | Recommended answer |
|---|---|---|
| Q-35 | Release level: v0.7.1 (patch, D-99) or v0.8.0 (minor)? And should the package version stay 0.4.1? | v0.7.1, package version 0.4.1 (D-99). Choose v0.8.0 if you count any new failing condition of a live test as an incompatible operator change. **Answered 2026-11-10 by the user: v0.7.1 (patch), package version 0.4.1** |
| Q-36 | A run of `smart_meter_peak_model` started by someone else between the two reads (another operator, a manual UI run) looks like a run started by the leg. Accept that risk, or tell such runs apart (by trigger type, creator or task list)? | Accept it: count every new run of the peak job id only (D-102), fail the leg and list the run ids, and rerun the leg once the cause is known. Filtering by creator or by the `only=` task list would hide exactly the regression the check exists for, because the leg runs as the operator and with the same tasks. The daily schedule is paused on `dev` by development mode (A-53), and the ingestion and training jobs have other job ids. The window is seconds on a refusal and about 3 minutes on a pass. **Answered 2026-11-10 by the user: accept the risk; count every new run of the peak job id and fail the leg** |
| Q-37 | Should the pass path also assert that exactly one new run exists and that it is the leg's own (FR-98), or only the refusal path? | Yes, both paths: AC66_BOTH_LEGS NFR-44 claims exactly one run per passing leg and nothing checks it today, and the reads are the same two. Cost: a foreign run during a pass fails the leg; for the rebuild leg that means a new snapshot, rerun leg, reset and rebuild leg. If you answer No, FR-98 and AC-174 are marked `Removed` through `/iterate` and AC-168 keeps only the refusal cases. **Answered 2026-11-10 by the user: yes, a passing leg checks for exactly its own run** |
| Q-38 | Is AC-175 (the rerun-leg refusal on `dev`, which needs you to run `scripts/reset_peak_model_outputs.py --confirm`) required before `/ship`, or are AC-173 (rebuild-leg refusal, no reset) and the CI proof of both legs (AC-166, AC-167) enough? | Required, as in AC66_BOTH_LEGS Q-33: the rerun-leg refusal is the AC66_BOTH_LEGS AC-164 claim that the operator read by hand, and the rebuild leg of AC-175 also restores the tables and shows the pass-path check on the second leg. You run the reset yourself, or authorize the agent for that one run with the dry-run condition, recorded in the BUILD_REPORT Deviations table. If you answer No, AC-175 becomes `Deferred: <reason>` at build and AC66_BOTH_LEGS F-03 closes on the rebuild-leg refusal only. **Answered 2026-11-10 by the user: AC-175 live is required before `/ship`** |
| Q-39 | `run_leg` changes in this feature. Take AC66_BOTH_LEGS F-01 (keep the original exception when saving the `failed` record raises) and AC66_BOTH_LEGS F-02 (atomic `Evidence.save`) into this scope? | No: keep this feature to AC66_BOTH_LEGS F-03, so that its ACs stay about run counts. AC66_BOTH_LEGS F-01 and AC66_BOTH_LEGS F-02 stay `Not scheduled` (Low) in the AC66_BOTH_LEGS SHIPPED record. Answer Yes only if you want one change to `run_leg` instead of two; then `/iterate` adds one FR and one CI AC for each. **Answered 2026-11-10 by the user: no, keep this feature to AC66_BOTH_LEGS F-03** |

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-46 | How the run-list reader enters `run_leg` (a required keyword, or an optional one whose default the live tests cannot use) and how the live tests build it (`workspace` with `peak_job.job_id`, or a method on `PeakRunner`), so that AC-170 can check it and the shipped AC66_BOTH_LEGS AC-158 tests keep their assertions (FR-101) |
| OD-47 | Which Jobs API listing and page size the reader uses (runs in every life-cycle state, newest first; not the `completed_only=True` of the shipped `full_runs` fixture), and what happens when more runs start during a leg than one page holds (A-55); whether `max_concurrent_runs: 1` of the peak job changes what a foreign run looks like on the pass path |
| OD-48 | Whether the pass-path count is better kept in the leg record as well (needs a change to AC66_BOTH_LEGS D-94, to `RECORD_FIELDS` and to the AC66_BOTH_LEGS AC-158 field-set assertion, and the user's OK); default: message and pass line only (D-103) |
| OD-49 | The exact message shapes for FR-97 to FR-99 (first lines, how the newest run ids are shown, the exception type), keeping the AC66_BOTH_LEGS G-46 text start for a clean refusal so the AC66_BOTH_LEGS AC-157 and AC-158 tests stay green, and keeping the original exception visible when the second read fails on the pass path |
| OD-50 | Where the second read sits on the pass path relative to the state read and the checks of `check_leg` (FR-96 fixes only "after the job run ended and before the `passed` save"), and whether a pass-path count failure is reported together with `check_leg` problems or alone |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| METER_INGESTION C-01 to C-07 | Constraint | Inherited: Free Edition serverless only, daily quota, no secrets in code, UTC end to end | Yes |
| C-26 | Constraint | Tests, docs and specs only: no change under `src/`, `resources/`, `notebooks/`, to `databricks.yml` or to `scripts/reset_peak_model_outputs.py`; the archived AC66_BOTH_LEGS DEFINE and DESIGN are not edited (E4); at `/ship` the SHIPPED Follow-ups row AC66_BOTH_LEGS F-03 and the follow-up file are updated | Yes (follow-up triage, E1 to E5 and E7 `Yes`) |
| C-27 | Constraint | `scripts/reset_peak_model_outputs.py --confirm` drops three dev tables and is run by the user; an agent runs it only when the user authorizes that run, and the authorization is recorded in the BUILD_REPORT Deviations table with the user's words and the date (AC66_BOTH_LEGS C-23 and its SHIPPED lesson). Only AC-175 needs it; between the reset and a passing rebuild leg, scoring on `dev` cannot run | Yes |
| C-28 | Constraint | The shipped AC66_BOTH_LEGS AC-159 test fixes the shape of the live leg tests (exactly two `ac66_rules.run_leg` calls with a constant `leg=`; `_tables_present` only inside the `exists=` lambda) and the AC66_BOTH_LEGS AC-154 test fixes the imports and calls allowed in `ac66_rules.py`; the new reader must fit both without weakening them (FR-101) | Yes (code reading of `tests/test_ac66_legs_docs.py` and `tests/test_ac66_rules.py`, 2026-11-10) |
| C-29 | Constraint | `out/evidence/` is git-ignored and local to one checkout; AC-173 to AC-175 run from the same checkout; the BUILD_REPORT is the durable record (AC66_BOTH_LEGS C-25) | Yes |
| A-53 | Assumption | On `dev` nothing but a person starts `smart_meter_peak_model`: its schedule is paused by development mode, and no job has a `run_job_task`, file-arrival or continuous trigger that starts it | Partly: code reading on 2026-11-10 (`resources/smart_meter_peak_model.job.yml` comment "paused by development mode", `databricks.yml` `mode: development`, no other trigger under `resources/`); the deployed `pause_status` is to be read once at build |
| A-54 | Assumption | A run started with `jobs.run_now` is listed by the Jobs API run list of its job (in a pending or running state) as soon as `run_now` has returned, so the second read sees a run started a few seconds earlier | Pending: the pass path of AC-174 shows the leg's own run in the second read (after it ended), not the delay right after `run_now`; a lag would hide a regression (unsafe direction). To be checked at build or in a spike if `/design` needs it |
| A-55 | Assumption | The run list is returned newest first, and fewer runs start during one leg than one page of the listing holds | Partly: the CLI listed newest first on 2026-11-09 (AC66_BOTH_LEGS DA-47, AC66_BOTH_LEGS I-02); the SDK listing and the page size are settled by OD-47 |
| A-56 | Assumption | A task retry inside a job run keeps the job run id, so a leg's own run counts as one new run even when a task is retried | Pending: consistent with the live runs of 2026-11-09 (one run id per leg); to be confirmed against the peak job's retry settings at `/design` |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | One named gap (AC66_BOTH_LEGS F-03) with the observed evidence (operator CLI reads of 2026-11-09 with the run ids), its cause (the leg tests do not read the run list) and its cost (an unplanned run unseen by any automated check) |
| Users | 3 | Operator, the user who runs the reset, BUILD_REPORT author and reviewer, CI and the three unchanged jobs, each with the place they read the outcome |
| Scope | 3 | Test-only plus docs, production and reset script fenced off, live steps kept to one reset; Q-35 to Q-39 answered by the user on 2026-11-10 (v0.7.1; foreign runs fail the leg; pass path checked; AC-175 live before `/ship`; AC66_BOTH_LEGS F-01 and AC66_BOTH_LEGS F-02 out of scope) |
| Acceptance criteria | 3 | Eleven criteria: eight CI (the pure rule, refusal with and without a started run, pass path, read failures, live test shape, compatibility and no change, docs), each with the order of side effects where it matters, and three live criteria in a fixed order, of which only one needs the reset; every FR and NFR covered |
| Constraints | 2 | A-54 (listing lag right after `run_now`) is pending and is in the unsafe direction; A-53 needs one read of the deployed schedule; C-28 narrows how the reader may be added |
| **Total** | **14/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The check proves "no new run of the peak job id appeared between two reads", not "this leg did
    not call `run_now`". A run started by a regression that the listing does not yet show (A-54)
    would pass; CI covers the call order with fakes (AC-166, AC-167), the live check only the
    listing.
  - A foreign run in the window fails the leg (Q-36). That is the safe direction, but on the pass
    path of the rebuild leg it costs a full new sequence with a reset (Q-37).
  - The evidence of a refusal lives only in the test output copied into the BUILD_REPORT (D-103);
    a missed copy loses it, as with the operator reads it replaces.
  - AC-171 counts `assert` statements to show that no assertion was removed; that catches removal,
    not a weakened condition. Review still has to read the diff of the two shipped test files.
- **Risks:**
  - AC-175 leaves `dev` without the feature and label tables between the reset and a passing
    rebuild leg (C-27); a failing rebuild leg leaves a partial state that both legs refuse until a
    full run of `smart_meter_peak_model`.
  - Adding a parameter to `run_leg` touches every AC66_BOTH_LEGS AC-158 test call; a careless
    default could let a live test skip the check silently. AC-170 and OD-46 guard it.
  - If Q-35 is answered v0.8.0, D-99 changes; nothing else depends on it before `/ship`.
- **Trade-offs:**
  - Counting every new run of the job id (instead of filtering) accepts rare false failures to keep
    the check able to see the regression it targets.
  - Two Jobs API reads per leg (NFR-48) buy an automated "0 new runs" and remove two operator reads
    per refused leg from the live plan.
  - Keeping the record contract (D-103) avoids changes to the verdict and AC66_BOTH_LEGS AC-158, at
    the price of evidence that lives in messages rather than files.
- **What I would do differently:** Write "starts no run" claims of a live AC together with the read
  that proves them in the first DEFINE (AC66_BOTH_LEGS AC-162 named "read from the Jobs API" but no
  FR asked the test to do it), so that the DESIGN could not move it to the operator.
- **Next improvement:** In `/design`, settle OD-46 first
  (it decides how AC-170 and the shipped AC-158 tests change), then OD-47 with a one-off read of the
  deployed peak job's schedule and a check of A-54.

---

## Next Step

`/design .claude/sdd/features/DEFINE_AC66_ZERO_NEW_RUNS.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-11-10 | Created: FR-96 to FR-104, NFR-48 to NFR-52, AC-165 to AC-175, C-26 to C-29, A-53 to A-56, D-99 to D-103 (derived), Q-35 to Q-39, OD-46 to OD-50. Status `Ready for Design` | Phase 1 of the SDD workflow, from follow-up AC66_BOTH_LEGS F-03 | `/design` can start once Q-35 to Q-39 are answered; the requirements are written for the recommended answers |
| 2026-11-10 | Q-35 to Q-39 answered by the user, each with the recommended answer; Clarity Scope 2 to 3 (total 14/15) | User answers in the define session | None: the requirements were written for these answers |
