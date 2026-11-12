# BUILD REPORT: Reset Guard

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | RESET_GUARD |
| **Date** | 2026-11-12 |
| **Source** | DESIGN_RESET_GUARD.md |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

Status stays `In Progress` until AC-202 (live dry run on `dev`, user-run, C-31) is pasted below.
Manifest entries 1 to 13 (the build PR) are done; entries 14 to 19 belong to `/ship`. Nothing was
committed, pushed or run against Databricks.

---

## Summary

The job-only mode (`check_jobs`) was appended to `pipeline_guard.py` (additions only), and the
reset script now builds one injectable workspace client, runs every check (time zone, row counts,
idle check as the last read) before the first DROP, prints each refusal as one
`refused, nothing dropped: ...` line with exit 2, and exits 1 on a failed DROP. About 100 unit
cases on fakes cover `main()` without the SDK; three shipped pins were narrowed per DA-68; version
0.8.0. The live dry run (AC-202) is pending the user.

---

## Files Changed

Atomic set: entries 1 to 7, 12 and 13 must land in one commit (entry 1 breaks the AC-105 and
AC-161 pins, entry 2 breaks the AC-161 and AC-171 pins, the bump depends on R1).

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | `src/smart_meter_peak_prediction/pipeline_guard.py` | Modified (177 inserted lines, 0 removed) | ruff; `test_ingestion_guard.py` AC-92 additions-only; `test_reset_guard_library.py` |
| 2 | `scripts/reset_peak_model_outputs.py` | Modified | ruff; `test_peak_reset_script.py` (3 plan tests, unchanged); `test_reset_guard.py` |
| 3 | `tests/support/reset_fakes.py` | Created | used by entries 4, 5 |
| 4 | `tests/test_reset_guard_library.py` | Created | pytest (34 cases); V073 goldens computed from tag v0.7.3 |
| 5 | `tests/test_reset_guard.py` | Created | pytest (83 cases); mutation check: removing the idle check fails 43 cases, a drop failure returning 0 fails AC-196 |
| 6 | `tests/test_ac97_timing_docs.py` | Modified (R1) | pytest; assert count of the AC-105 test 6 = v0.7.3; `V040_TREE_SHA256` recomputed from v0.4.0 |
| 7 | `tests/test_ac66_legs_docs.py` | Modified (R2, R3) | pytest; assert counts 6 and 4 = v0.7.3; `V060_TREE_SHA256`, `V060_RESET_SHA256`, `V070_RESET_SHA256` recomputed from v0.6.0 and v0.7.0 |
| 8 | `docs/runbooks/peak_model.md` | Modified | AC-201 test; AC66_BOTH_LEGS AC-160, AC66_ZERO_NEW_RUNS AC-172, PEAK_MODEL_CONCURRENCY AC-79 tests green |
| 9 | `tests/test_reset_guard_docs.py` | Created | pytest |
| 10 | `docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md` | Modified (note) | check_specs |
| 11 | `docs/adr/README.md` | Modified (row 0014 Proposed) | check_specs |
| 12 | `pyproject.toml` | Modified (0.8.0) | AC-105 test; dependencies unchanged |
| 13 | `src/smart_meter_peak_prediction/__init__.py` | Modified (0.8.0) | AC-105 test |

Not modified: `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py`, `tests/test_peak_reset_script.py`, `resources/`, `notebooks/`, `pipelines/`, `databricks.yml` (`git diff v0.7.3` empty).

---

## Acceptance Criteria Evidence

| AC | Result | Evidence |
|---|---|---|
| AC-189 | Pass | `test_reset_guard.py::test_ac189_an_active_run_of_either_peak_job_refuses_both_modes` (18 cases), `::test_ac189_a_run_without_start_time_is_shown_not_started`; `test_reset_guard_library.py::test_ac189_check_jobs_reports_every_active_run` |
| AC-190 | Pass | `test_reset_guard.py::test_ac190_an_unreadable_peak_job_fails_closed` (9 cases); `test_reset_guard_library.py::test_ac190_lookup_fails_closed_on_every_ambiguity` (8 cases) |
| AC-191 | Pass | `test_reset_guard.py::test_ac191_confirm_with_both_jobs_idle_drops_the_three_tables_in_order` (plain and Enum states) |
| AC-192 | Pass | `test_ac192_connection_failures_print_one_refusal_line` (12 cases), `test_ac192_missing_sdk_refuses_through_the_default_factory`, `test_ac192_a_failed_count_query_is_labelled_row_counts` |
| AC-193 | Pass | `test_ac193_every_check_completes_before_the_first_drop`, `..._each_failing_check_refuses_without_a_drop`, `..._count_and_idle_problems_share_one_line` |
| AC-194 | Pass | `test_ac194_dry_run_checks_the_jobs_and_sends_only_select` |
| AC-195 | Pass | `test_ac195_no_option_or_variable_skips_the_idle_check` |
| AC-196 | Pass | `test_ac196_a_failed_drop_stops_and_exits_1` |
| AC-197 | Pass | `test_reset_guard_library.py::test_ac197_*` (assert counts, modes byte-equal v0.7.3, read-call sets, reader parity over 19 cases, reset imports guard, bundle files); shipped AC-92 tests, `test_pipeline_guard.py`, `test_peak_reset_script.py`, and the three re-pinned tests green |
| AC-198 | Pass | `test_ac198_only_read_calls_before_the_first_drop_and_no_secret_in_output` (10 scenarios incl. redacted secret) |
| AC-199 | Pass | `test_ac199_two_runs_give_equal_output_and_change_nothing` |
| AC-200 | Pass | `test_ac200_idle_check_reads_at_most_4_calls_per_job_and_never_sleeps`, `..._runs_read_are_capped_at_25_per_job`, `..._client_is_built_with_the_shipped_limits`; library `test_ac200_job_only_mode_reads_one_page_and_25_runs` |
| AC-201 | Pass | `test_reset_guard_docs.py::test_ac201_runbook_and_docstring_state_the_idle_check` |
| AC-202 | Not run | Live, user-run (C-31, Q-42). After `databricks bundle validate -t dev -p dev` and `databricks bundle deploy -t dev -p dev` from this branch, with both peak jobs idle, the three tables at expected counts and `out/evidence/ac66_before_rebuild.json` present, run `DATABRICKS_CONFIG_PROFILE=dev python scripts/reset_peak_model_outputs.py` (no `--confirm`), then `echo $?`. Paste the full output and exit code here. Expected: exit 0, two `idle check: job ... (job id <id>): 0 active runs` lines, three `would DROP TABLE smart_meter_dev...` lines, the `dry run:` line |

### AC-202 live record (pending)

```text
(user pastes output and exit code)
```

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `ruff check .` | `All checks passed!` |
| Format | `ruff format --check .` | `133 files already formatted` |
| Tests | `pytest` | 915 passed, 92 deselected, 1 xfailed |
| Spec check | `python scripts/check_specs.py` | `75 document(s) checked, 0 error(s), 9 warning(s)` (warnings pre-existing, rule b) |

Full default run: `915 passed, 92 deselected, 1 xfailed, 9 warnings in 413.19s (0:06:53)` (0 failures; integration and local_data deselected).

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| Count-query failure label | Line shapes: other count error prints `row counts: <err>` | Added `except StatementFailed` in `main` so a failed count statement is also labelled `row counts: SQL failed: ...` | `StatementFailed` subclasses `ResetRefused` and would otherwise print without the label (code-reviewer I-02) | No (mechanical, matches the line-shape table) |
| Reset `# noqa: BLE001` | not shown | added on `except Exception` lines | ruff BLE001 | No |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | AC-202 needs the user's live dry run (gate for `/ship`, Q-42) | High (gate) | Open: command in the AC table |
| I-02 | `code-reviewer` Medium: failed count statement printed without the `row counts:` label | Medium | Fixed in this build (`test_ac192_a_failed_count_query_is_labelled_row_counts`) |
| I-03 | `code-reviewer` Medium: AC-196 failed once from a stale `.pyc` (same-second edit, same size) | Medium | Closed: `__pycache__` cleared, rerun green; fresh checkouts unaffected |
| I-04 | `code-reviewer` Low: `assert code in (0, 1, 2)` in AC-198 test is loose | Low | Accepted: exit codes are asserted in the AC-189 to AC-196 tests |
| I-05 | `code-reviewer` Low: AC-192 factory case checked only the prefix | Low | Fixed: full line asserted |
| I-06 | `code-reviewer` Low: AC-193 time-zone and idle cases use `in` | Low | Accepted: the exact line is asserted in the count and AC-189 tests |
| I-07 | `code-reviewer` Low: AC-199 uses `git status` | Low | Accepted: tests already depend on git (tag pins) |
| I-08 | `code-reviewer` Low: `UTC_ZONES` is case-sensitive | Low | Accepted: refuses, the safe direction |

No High finding from the review.

---

## Self-Review

- **Weak points:** AC-202 is not yet shown; the busy and unreadable paths are proven on fakes only. `_read_named_job` is a copy kept honest by the parity test. The re-pinned tests no longer catch accidental changes to `pipeline_guard.py`/`Warehouse`/`main`; AC-197 and AC-92 cover that.
- **Risks:** `jobs.list(limit=100)` and `Config(profile=...)` with the local SDK are first exercised live by AC-202 (A-57, DA-60, DA-63). A stale `.pyc` can hide edits made in the same second.
- **What I would do differently:** run the full suite once before the live gate on a clean `__pycache__` and keep the mutation checks as tests.
- **Next improvement:** the user runs AC-202; then record it here, set status `Complete`, and `/ship`.

---

## Next Step

User runs AC-202, then `/ship RESET_GUARD`.
