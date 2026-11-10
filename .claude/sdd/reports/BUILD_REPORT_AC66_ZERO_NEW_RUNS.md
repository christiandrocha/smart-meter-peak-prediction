# BUILD REPORT: AC-66 Zero New Runs

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_ZERO_NEW_RUNS |
| **Date** | 2026-11-10 |
| **Source** | DESIGN_AC66_ZERO_NEW_RUNS.md (Ready for Build) |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

Status rule applied: the CI criteria AC-165 to AC-172 are `Pass`. AC-173 to AC-175 and the A-53
and A-54 checks are `Not run` (live gate, run in a separate step after the user confirms), so the
build stays `In Progress`.

---

## Summary

Both AC-66 legs now read the run ids of `smart_meter_peak_model` through a required `runs`
keyword before anything else and again after the refusal or the job run, and compare them by run
id (`count_runs`). A clean refusal ends with `0 new runs of smart_meter_peak_model`; a refusal
during which a run started, a wrong run count on the pass path and an unreadable list each fail
with their own message; a pass prints one line with its run id. `PeakRunner.run_ids` is the live
reader (one list request, one page of 25, every state). Nothing under `src/`, `resources/`,
`notebooks/`, `databricks.yml` or the reset script changed. The live gate is not run yet.

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | `tests/support/ac66_rules.py` | Modified (`RUN_JOB_NAME`, `RunCount`, `run_ids`, `count_runs`, message helpers, `run_leg` with `runs`) | `ruff`; `tests/test_ac66_rules.py` |
| 2 | `tests/integration/conftest.py` | Modified (`islice`, `PeakRunner.RUN_LIST_LIMIT`, `PeakRunner.run_ids`) | `ruff`; `test_ac170_run_ids_reads_one_page_...`; AST test |
| 3 | `tests/test_ac66_rules.py` | Modified (fakes, `Logged`, AC-165 to AC-170 tests, review additions) | 78 shipped-era plus new tests, all pass |
| 4 | `tests/integration/test_peak_data.py` | Modified (`runs=` in both calls, docstrings) | `ruff`; AC-159 and AC-170 AST tests; no live run |
| 5 | `docs/runbooks/peak_model.md` | Modified (`-rP` on 3 lines, section 8 paragraph, section 9 paragraph) | AC-160 and AC-172 tests |
| 6 | `tests/test_ac66_legs_docs.py` | Modified (AC-170 AST, AC-171, AC-172, `V070_*` constants from tag `v0.7.0`) | `pytest tests/test_ac66_legs_docs.py` |

Entries 7 to 9 (CHANGELOG, follow-up closure, SHIPPED row) are "Update at /ship" and were not
touched. Commits (branch `build/ac66-zero-new-runs`, not pushed): `8b7b9b2` (entries 1 to 4 in
one commit, as the Delivery Plan requires), `327e358` (runbook), `5b21218` (docs tests),
`3b1d90d` (code-review gaps).

---

## Acceptance Criteria Evidence

| AC | Result | Evidence |
|---|---|---|
| AC-165 | Pass | `tests/test_ac66_rules.py::test_ac165_run_count_rule_over_pairs_of_reads` (8 cases), `::test_ac165_run_count_rule_never_raises_on_odd_reads` (3 leg ids), `::test_ac165_one_new_run_that_is_not_the_legs_own_is_not_own` |
| AC-166 | Pass | `::test_ac166_refusal_reads_the_run_list_twice_and_reports_0_new_runs` (6 refusals; call log `runs, read_text, exists, runs`; evidence unchanged; messages byte-equal) |
| AC-167 | Pass | `::test_ac167_a_run_started_during_a_refusal_fails_differently` (6 refusals) |
| AC-168 | Pass | `::test_ac168_pass_checks_exactly_its_own_run` (2 legs: pass, own plus foreign, none), `::test_ac168_one_foreign_run_instead_of_its_own_fails`, `::test_ac168_error_exits_make_no_second_read`, `::test_ac168_a_pass_line_that_cannot_be_written_leaves_a_failed_record` |
| AC-169 | Pass | `::test_ac169_unreadable_run_list_never_reports_a_pass` (2 legs x 4 replies), `::test_ac169_unreadable_second_read_never_reports_a_clean_refusal`, `::test_ac169_a_base_exception_from_the_reader_propagates`, `::test_ac169_a_base_exception_from_the_second_refusal_read_propagates` |
| AC-170 | Pass | `tests/test_ac66_legs_docs.py::test_ac170_both_live_legs_pass_a_reader_bound_to_the_peak_job`; `tests/test_ac66_rules.py::test_ac170_run_ids_reads_one_page_of_every_state_for_the_given_job` |
| AC-171 | Pass | `tests/test_ac66_legs_docs.py::test_ac171_v070_unit_tests_are_kept_with_their_asserts`, `::test_ac171_rule_constants_and_reset_script_equal_v070` (tag `v0.7.0` present, tag comparison ran); shipped AC66_BOTH_LEGS AC-154 to AC-161 tests green; full gates below |
| AC-172 | Pass | `::test_ac172_runbook_and_docstring_name_the_run_list_reads`, `::test_ac172_leg_command_lines_carry_rp` |
| AC-173 | Not run | Live: rebuild-leg refusal on `dev` (plan step 6) |
| AC-174 | Not run | Live: rerun-leg pass with one own run (plan step 7) |
| AC-175 | Not run | Live: user reset, then rerun-leg refusal, rebuild-leg pass, verdict (plan steps 8 and 9) |
| A-53 | Not run | Live plan step 2 |
| A-54 | Not run | Live plan step 3 (U-08 answered yes by the user on 2026-11-10) |

### Live plan (not run; commands in order)

One session, one checkout of `build/ac66-zero-new-runs`, clean tree. Profile `dev`.

```bash
export DATABRICKS_CONFIG_PROFILE=dev
# 1. deploy; record both exit codes
databricks bundle validate -t dev -p dev ; databricks bundle deploy -t dev -p dev
# 2. A-53: settings.schedule.pause_status expected PAUSED, no trigger or continuous block
databricks jobs get <peak job id> -p dev
#    if UNPAUSED, run steps 5 to 9 outside 07:45 to 08:30 UTC and record that
# 3. A-54 (U-08, not AC evidence): start the read-only task, then at once list the newest run
databricks bundle run -t dev -p dev smart_meter_peak_model --only check_pipeline_idle --no-wait
databricks jobs list-runs --job-id <peak job id> --limit 1 -p dev
#    Pass when the listed run id equals the started run's id; record both ids and the seconds
#    between the commands; wait for the run to end. On Fail apply the DA-56 fallback
#    (RUN_LIST_SETTLE_S) and record it in Deviations.
# 4. ingestion and peak jobs idle; the three tables present
# 5. snapshot
pytest -m integration tests/integration/test_peak_data.py -k "ac66_before"
# 6. AC-173 (expected to fail, refused; copy the message)
pytest -m integration -rP tests/integration/test_peak_data.py -k "ac66_rebuild_leg"
# 7. AC-174 (1 run, passes; copy the pass line and run_id of out/evidence/ac66_rerun_leg.json)
pytest -m integration -rP tests/integration/test_peak_data.py -k "ac66_rerun_leg"
# 8. U-07: the user runs the reset (dry run, then --confirm), or authorizes the agent for this one
#    run with the condition that --confirm runs only if the dry run lists exactly the three dev
#    tables; the authorization (the user's words and the date) goes into Deviations (C-27)
python scripts/reset_peak_model_outputs.py
python scripts/reset_peak_model_outputs.py --confirm
# 9. AC-175
pytest -m integration -rP tests/integration/test_peak_data.py -k "ac66_rerun_leg"    # expected: fails, refused, three missing tables
pytest -m integration -rP tests/integration/test_peak_data.py -k "ac66_rebuild_leg"  # 1 run, passes
pytest -m integration tests/integration/test_peak_data.py -k "ac66_verdict"          # passes
```

Copy into the rows above: for each step the test outcome, the refusal message or pass line with
its run ids, `run_id` of each leg record, the verdict record and the reset output. Steps 5 to 9
start 2 job runs; step 3 starts 1 read-only run outside the sequence. No `list-runs` read is used
for AC-173 to AC-175 evidence.

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `ruff check . && ruff format --check .` | `All checks passed!`; `128 files already formatted` |
| Tests | `pytest` (no integration marker) | 790 passed, 92 deselected, 1 xfailed (the shipped strict xfail), 9 warnings, 0 failed |
| Spec check | `python scripts/check_specs.py` | 67 document(s) checked, 0 error(s), 10 warning(s) (pre-existing) |
| Tag | `git tag -l v0.7.0` | `v0.7.0` present; AC-171 constants computed from it |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| Entry 6 test for `-rP` | AC-172 covers the texts | Added `test_ac172_leg_command_lines_carry_rp` | Code review: DA-55 requires `-rP` on the leg lines and no test guarded it | No (within the design) |
| Extra unit tests | AC-165 to AC-169 test list | Added the foreign-run-instead-of-own, BaseException, no-second-read and failing-pass-line tests | Code review Medium findings | No (within the design) |
| `Fakes.runs` raises `BaseException` | `Exception` or value | The fake raises any `BaseException` reply | Needed to test that `Stop` propagates (G-54) | No (mechanical) |

No deviation needs `/iterate`. No line over 100 characters and no module-loading problem
occurred; `_load_conftest` keeps its `sys.modules` step (DA-59).

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | AC-173 to AC-175 and the A-53 and A-54 checks need the live `dev` run and the user's reset | High (gate for `/ship`, Q-38) | Open: live plan above |
| I-02 | `code-reviewer` Medium: no test for one new run that is not the leg's own (`own` could weaken to `len(new) == 1`) | Medium | Fixed in `3b1d90d` (`test_ac165_one_new_run_...`, `test_ac168_one_foreign_run_...`) |
| I-03 | `code-reviewer` Medium: no test that a `BaseException` from `runs()` propagates | Medium | Fixed in `3b1d90d` (AC-169 BaseException tests) |
| I-04 | `code-reviewer` Medium: no test of "no second read" on `exists()`, `preflight()` and `run_tasks()` error exits (DA-54) | Medium | Fixed in `3b1d90d` (`test_ac168_error_exits_make_no_second_read`) |
| I-05 | `code-reviewer` Low: a failing pass line (DA-55) untested | Low | Fixed in `3b1d90d` |
| I-06 | `code-reviewer` Low: `-rP` on the leg lines unguarded | Low | Fixed in `3b1d90d` (`test_ac172_leg_command_lines_carry_rp`) |
| I-07 | `code-reviewer` Low: the first-read gate is not total for a list subclass whose `__iter__` raises (raw error instead of the "could not be read" message); `PeakRunner` returns a plain list | Low | Open: accepted, no live impact |
| I-08 | `code-reviewer` Low: `raise ... from error` keeps the reader exception, so pytest prints its text in the terminal although the message does not hold it (G-57, DA-52 specify the cause) | Low | Open: needs `/iterate` on DA-52 if the user wants `from None` |
| I-09 | `code-reviewer` Low: AC-171 working-tree check is `>=` on assert counts; exact equality only when the tag exists | Low | Accepted trade-off (DA-57) |

No High finding.

---

## Self-Review

- **Weak points:** The live criteria are not run. The call-log tests pin the exact order of
  `run_leg`, so a harmless refactor needs the tests to change. AC-171 detects removed, not
  weakened, assertions.
- **Risks:** A-54 (a started run is listed at once) is unchecked until live step 3; the CI order
  proof carries it until then. A foreign run during the rebuild leg costs a new sequence.
- **What I would do differently:** Decide I-08 (`from None`) in the DESIGN before building.
- **Next improvement:** Run the live plan after the user confirms, then fill AC-173 to AC-175.

---

## Next Step

Live gate (plan above), then set the status and `/ship AC66_ZERO_NEW_RUNS`.
