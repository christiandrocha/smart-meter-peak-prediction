# BUILD REPORT: AC-97 Timing Evidence

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC97_TIMING_EVIDENCE |
| **Date** | 2026-11-04 |
| **Source** | DESIGN_AC97_TIMING_EVIDENCE.md |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

The status stays `In Progress` until AC-106 (and the live part of AC-97) run on dev.

---

## Summary

The live AC-97 test now keeps an in-memory record of the update it starts, the refused run and its
check task, the rerun and the end of the update, and writes it as `out/evidence/ac97_timing.json`
in an outer `finally` (also when an assertion fails or the platform raises). The computing is done
by pure, SDK-free helpers in `tests/support/ac97_timing.py`, and a new live test
`test_ac106_*` reads the file back and cross-checks it with the platform. Manifest entries 1 to 8
are done and verified locally (15 new unit tests, 508 passed in total before the review fixes); entry 9 (CHANGELOG) is for
`/ship`. The build was deployed to dev and the live AC-97 and AC-106 tests passed on 2026-11-04 (margin
after the read 32 s; the update ended 59 s after creation).

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | `tests/support/ac97_timing.py` | Created | `ruff check`/`format`; `tests/test_ac97_timing.py` (AC-100 to AC-103) |
| 2 | `tests/test_ac97_timing.py` | Created (11 tests) | pytest: 11 passed |
| 3 | `tests/integration/test_ingestion_guard_live.py` | Modified (AC-97 new shape, `_wait_pipeline_idle(watch=)`, capture and read helpers, `test_ac106_*`, docstring) | ruff; collection (5 tests, AC-97 and AC-106 present); AC-104/AC-105 AST tests; live Pass (AC-97, AC-106) |
| 4 | `tests/test_integration_layout.py` | Modified (`AC_NAME` `\d{2,3}`, failure text, `EXPECTED_ACS` 106, `::test_ac106_` collected) | pytest: 6 passed |
| 5 | `docs/runbooks/meter_ingestion.md` | Modified (subsection "AC-97 timing evidence", row H pointer) | `test_ac104_runbook_*`; shipped `test_ingestion_guard_docs.py` (4 passed, unmodified) |
| 6 | `pyproject.toml` | Modified (`version = "0.4.1"`) | `test_ac105_production_files_*` |
| 7 | `src/smart_meter_peak_prediction/__init__.py` | Modified (only `__version__ = "0.4.1"`) | `test_ac105_production_files_*` (digest and byte comparison with `v0.4.0`) |
| 8 | `tests/test_ac97_timing_docs.py` | Created (4 tests) | pytest: 4 passed |

Not in the manifest of this build: `CHANGELOG.md` (entry 9, `/ship`). `tests/integration/conftest.py`,
`pipeline_guard.py`, the bundle, notebooks and `docs/runbooks/peak_model.md` are untouched.

Golden values of AC-105, computed from tag `v0.4.0` with the functions of `test_ac97_timing_docs.py`
(`tagged_paths`, `tagged`, `tree_digest`, `assert_texts`), not typed by hand: tree digest of the 38
files under `src/smart_meter_peak_prediction/`, `resources/`, `notebooks/` and `databricks.yml`
(version line normalised to 0.4.0) `258a24c28e3cf0babd75cd3b19c2eea635985f5ac24cd2a8fe73816e2a771f8c`;
11 `assert` statements of the shipped AC-97 function (`V040_AC97_ASSERTS`).

---

## Acceptance Criteria Evidence

Unit evidence is from `.venv/bin/pytest` (508 passed, 90 deselected, 0 failures; 15 new unit tests:
11 + 4).

| AC | Result | Evidence |
|---|---|---|
| AC-100 | Pass | `test_ac97_timing.py::test_ac100_margins_are_whole_utc_seconds_for_every_input_form` (4 forms: ISO `Z`, ISO `+02:00`, epoch ms, aware datetime in `+02:00`; 27 s and 98 s each), `::test_ac100_helpers_import_no_sdk_and_read_no_clock` (AST) |
| AC-101 | Pass | `::test_ac101_missing_naive_or_early_end_never_raises` (cases a to e plus the builder on odd inputs) |
| AC-102 | Pass | `::test_ac102_parser_reads_the_library_busy_message` (messages rendered by `pipeline_guard.check_pipeline`, one and two active updates, ANSI-wrapped task error text), `::test_ac102_parser_returns_nulls_for_other_messages`, `::test_ac102_end_event_pick_requires_the_update_and_its_final_state` |
| AC-103 | Pass | `::test_ac103_record_has_exactly_the_contract_fields` (19 fields, types, byte-stable JSON, fallbacks, passing check), `::test_ac103_missing_inputs_give_nulls_and_incomplete_and_no_secret` |
| AC-104 | Pass | `test_ac97_timing_docs.py::test_ac104_runbook_explains_the_timing_evidence`, `::test_ac104_failure_hint_and_note_name_the_evidence_file` (AST of the AC-97 function: `except BaseException` with `add_note`, outermost `finally` with `evidence.save(ac97_timing.EVIDENCE_NAME, ...)`, `failure_hint` in the `AssertionError` handler); shipped AC-99 docs tests pass unmodified |
| AC-105 | Pass | `::test_ac105_production_files_equal_v040_except_the_version` (tag present locally, so also compared with `git show`), `::test_ac105_shipped_ac97_asserts_and_mechanics_are_kept` (11 asserts kept, one `start_update(full_refresh=False)`, two `peak_runner.run(only=subset)`, `subset = [CHECK, REFRESH]`); `pytest` 0 failures; `check_specs.py` 0 errors |
| AC-106 | Pass | Live. Needs deploy and the commands in the live-test plan below. Unit side: `test_integration_layout.py::test_integration_tests_cover_every_in_scope_ac` and `::test_integration_tests_are_collected_but_deselected_by_default` (both pass; `::test_ac106_` is collected). Live, 2026-11-04, after `bundle validate` and `bundle deploy -t dev` (exit 0, build `19bd0a1`): AC-97 passed (142 s), then `test_ac106_ac97_timing_evidence_matches_the_platform` passed (6 s). `out/evidence/ac97_timing.json`: update `1bb3c498-6f34-4303-98ad-ebd8c40f2ade` created 18:51:29Z; refused run 474092262377864, check task 115041889552750 started 18:51:30Z, read 18:51:56Z (update `INITIALIZING`, pipeline `RUNNING`), ended 18:52:01Z, FAILED; update `COMPLETED` at 18:52:28Z (`update_end_source` `platform`); rerun 501180431336170, check and refresh SUCCESS; `read_after_creation_seconds` 27, `update_outlived_read_seconds` 32, outcome `refused` |

DA-38 (checked at build, throwaway test in the scratchpad, not in the repo): with pytest 9.1.1 a
failing test that calls `exc.add_note(...)` and `print(...)` before `raise` shows both the note
(`E   AC-97 timing evidence: ...` in the failure report) and the printed line (captured stdout).
Validated; the print fallback is kept as designed.

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` | 124 files already formatted |
| Tests | `.venv/bin/pytest` | 508 passed, 90 deselected, 0 failed (5 min 50 s) |
| Spec check | `.venv/bin/python scripts/check_specs.py` | 28 documents, 0 errors, 0 warnings |
| Collection | `.venv/bin/pytest --collect-only -m integration -o addopts= -q` | 70/598 collected; `test_ac97_*` and `test_ac106_*` present |
| Hooks | `pre-commit run --all-files` | Passed after one change: the hook's ruff (v0.6.9) and the dev ruff (0.17) formatted a long `assert` in `tests/test_integration_layout.py` differently; the message moved to a variable so both agree (PEAK_MODEL F-02) |
| DA-38 | Throwaway test in the scratchpad | note and printed line both shown (pytest 9.1.1) |
| Bundle | `databricks bundle validate -t dev -p dev` / `deploy` | Validation OK; deploy exit 0 (2026-11-04) |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| D-01 `Ac97Facts` fields | Dataclass of the Helper API | Same fields; module also exports `OUTCOMES`, `END_SOURCES`, `FORBIDDEN_TEXT` constants | used by the unit tests and AC-106 instead of repeating literals | No (additive) |
| D-02 AC-106 fallback | AC-106 cross-checks creation with `get_update`; DA-36 fallback `list_updates` | AC-106 helper `_update_creation_ms` tries `get_update` and falls back to `list_updates` itself | implements the DA-36 fallback named in the DESIGN | No |
| D-03 Failure path capture | `_capture_found_run` only on `AssertionError` of the runner | Same. A `pytest.fail` from `PeakRunner.run` (timeout) leaves the refused-run fields null | follows OD-27 as written; see I-03 | No |
| D-04 AC-106 test body | - | Prints the record (`AC-106 evidence: {...}`) so the values can be copied into the AC-106 row | NFR-31 / DEFINE AC-106 ask for the values in the BUILD_REPORT; the test already holds them | No |

No deviation changes the DESIGN.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | Live ACs (AC-106; live part of AC-97) not run | High (gate) | Closed 2026-11-04: AC-97 and AC-106 pass live |
| I-02 | DA-35 (event wording), DA-36 (`get_update` of a finished update) and DA-37 (busy line in the task error text) are validated only by the first live run | Medium | Closed 2026-11-04: validated by the first live run (`update_end_source` `platform`, `get_update` returned `COMPLETED`, the check's busy line parsed: `INITIALIZING`) |
| I-03 | `PeakRunner.run` timeout (`pytest.fail`) leaves the refused-run fields null (the record is still written, outcome `incomplete`) | Low | Accepted as designed (OD-27) |
| I-04 | Review (Medium): `build_record`/`evidence.save` unguarded in the outer `finally` | Medium | Fixed: wrapped, prints class and error code only |
| I-05 | Review (Medium): `_capture_refused`/`_capture_rerun` parsing unguarded | Medium | Fixed: wrapped (G-33) |
| I-06 | Review (Medium): AC-106 read null fields before asserting them | Medium | Fixed: non-null assert of the 10 fields first |
| I-07 | Review (Low): stale file passes AC-106 | Low | Fixed: file age under 30 min |
| I-08 | Review (Low): `list_runs` drained all pages | Low | Fixed: `islice(..., 5)` |
| I-09 | Review (Low): AC-105 mechanics test omitted `expect`/`require_idle`/`finally` wait | Low | Fixed |
| I-10 | Review (Low): runbook overstated `observed_terminal` resolution | Low | Fixed |
| I-11 | Review (Low): live helpers have no unit test; found-run capture may pick a run ended just before `start_update` (30 s slack) | Low | Open; follow-up |
| I-13 | The no-op update lasted 59 s on 2026-11-04, not the 125 s measured in spike 06; the margin after the read was 32 s (DA-31 still holds, but with less room than assumed) | Medium | Watch the margin in later AC-97 runs; the ladder in the runbook applies when it reaches 0 |
| I-12 | Code review result | - | `code-reviewer` subagent: no High findings; 3 Medium and 6 Low, all fixed except I-11 |

---

## Live-test plan (user-run)

Prerequisite: clean tree of the build branch, `export DATABRICKS_CONFIG_PROFILE=dev`; pipeline,
ingestion job and peak job idle. No Kafka needed, Aiven state irrelevant.

1. `databricks bundle validate -t dev -p dev` (record the exit code, expect 0)
2. `databricks bundle deploy -t dev -p dev` (exit code 0; the bundle content equals `v0.4.0` except the version string)
3. AC-97 (one no-op update, two subset runs; writes `out/evidence/ac97_timing.json`; note its wall time):
   `.venv/bin/pytest -o addopts= -m integration tests/integration/test_ingestion_guard_live.py::test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds`
4. Right after (0 runs, 3 reads):
   `.venv/bin/pytest -o addopts= -m integration tests/integration/test_ingestion_guard_live.py::test_ac106_ac97_timing_evidence_matches_the_platform`
5. Copy `out/evidence/ac97_timing.json` (also printed by the AC-106 test with `-s`) into the AC-106 row with the AC-97 wall time and run count. If AC-97 fails on timing, follow the runbook ladder ("AC-97 timing evidence"); copy each attempt's file before the next attempt.

Then set AC-106 and AC-97 (live) to Pass/Fail and the status to `Complete` only if all pass.

---

## Self-Review

- **Weak points:** the failure path of the evidence is proven by unit tests of the builder and an AST check of the wiring, not by a live failure; the AC-97 function has a third `try` level; the live helpers (`_capture_*`, `_read_update_end`, `_observe`) have no unit tests because they touch SDK objects.
- **Risks:** DA-35, DA-36 and DA-37 held on the first live run, but on one observation; the update ended 59 s after creation, so AC-97 has a 32 s margin, not the roughly 100 s the 125 s figure implied (I-13). The SDK in the local `.venv` (0.153.0) is what the live tests use, so `as_dict()` shapes were read from the SDK source, not from a response.
- **What I would do differently:** give the live helpers a tiny fake-SDK unit test so the capture code is exercised in CI.
- **Next improvement:** `/ship AC97_TIMING_EVIDENCE` with the CHANGELOG `[0.4.1]` entry.

---

## Next Step

`/ship AC97_TIMING_EVIDENCE`.
