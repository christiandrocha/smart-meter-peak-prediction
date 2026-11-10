# BUILD REPORT: AC-66 Zero New Runs

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_ZERO_NEW_RUNS |
| **Date** | 2026-11-10 |
| **Source** | DESIGN_AC66_ZERO_NEW_RUNS.md (Ready for Build) |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

Status rule applied: the CI criteria AC-165 to AC-172 are `Pass`, and the live criteria AC-173 to
AC-175 and the A-53 and A-54 checks are `Pass` on `dev` on 2026-11-10 (Live run record below). No
AC is partial or waived, so the build is `Complete`.

---

## Summary

Both AC-66 legs now read the run ids of `smart_meter_peak_model` through a required `runs`
keyword before anything else and again after the refusal or the job run, and compare them by run
id (`count_runs`). A clean refusal ends with `0 new runs of smart_meter_peak_model`; a refusal
during which a run started, a wrong run count on the pass path and an unreadable list each fail
with their own message; a pass prints one line with its run id. `PeakRunner.run_ids` is the live
reader (one list request, one page of 25, every state). Nothing under `src/`, `resources/`,
`notebooks/`, `databricks.yml` or the reset script changed. The live gate passed on `dev` on
2026-11-10, run by the agent with the user's authorization, including the reset (Deviations).

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
`3b1d90d` (code-review gaps), `488e3bc` (this report, CI part); the live evidence is recorded
in a later commit.

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
| AC-173 | Pass (live) | 2026-11-10, `dev`, step 6: the rebuild leg refused with the three tables present and ended `0 new runs of smart_meter_peak_model (newest run before: 263891533624085, after: 263891533624085)`; `out/evidence/ac66_rebuild_leg.json` unchanged (still dated 2026-11-09) |
| AC-174 | Pass (live) | 2026-11-10, `dev`, step 7: `AC-66 rerun leg passed: 1 new run of smart_meter_peak_model, run 559956433114287 (newest run before: 263891533624085)` in 159 s; `ac66_rerun_leg.json` `outcome` `passed`, `run_id` 559956433114287, MERGE 0 / 0 / 0 |
| AC-175 | Pass (live) | 2026-11-10, `dev`, steps 8 and 9: the reset dry run listed exactly the three `dev` tables and `--confirm` dropped them (exit 0); the rerun leg refused naming the three missing tables and ended `0 new runs of smart_meter_peak_model (newest run before: 559956433114287, after: 559956433114287)`, its record unchanged; the rebuild leg passed in 152 s with `1 new run of smart_meter_peak_model, run 1095873634832183`, `ac66_rebuild_leg.json` `run_id` 1095873634832183, inserted 21,165 / 36,480 / 36,480, updated and deleted 0; the verdict passed (`verdict` `pass`, `problems` empty) |
| A-53 | Pass (live) | 2026-11-10, step 2: `smart_meter_peak_model` (job 324283392483306) `schedule.pause_status` `PAUSED`, no `trigger` or `continuous` block, `max_concurrent_runs` 1 |
| A-54 | Pass (live) | 2026-11-10, step 3 (U-08): run 263891533624085 started with `--only check_pipeline_idle --no-wait`; the `list-runs --limit 1` right after it (4.3 s from the start command, 1.4 s list call) returned 263891533624085 `RUNNING`; the run ended `TERMINATED` `SUCCESS`. No settle wait needed (DA-56 fallback not applied) |

### Live plan (run on 2026-11-10; commands in order)

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

### Live run record (2026-11-10, `dev`, branch `build/ac66-zero-new-runs` at 488e3bc)

Run by the agent, with the user's authorization (Deviations). Times are UTC.

| Step | Result |
|---|---|
| 1 | `bundle validate -t dev` exit 0 (`Validation OK!`); `bundle deploy -t dev` exit 0 |
| 2 | A-53 Pass (see the table above) |
| 3 | A-54 Pass: started run 263891533624085, newest listed 263891533624085 `RUNNING`; ended `TERMINATED` `SUCCESS` at 15:15:20 |
| 4 | `smart_meter_peak_model` and `smart_meter_ingestion`: 0 active runs; the step 6 refusal shows the three tables present |
| 5 | `-k "ac66_before"`: 1 passed; `ac66_before_rebuild.json` written with `saved_at_ms` |
| 6 | AC-173: 1 failed, as expected (refusal, `0 new runs`) |
| 7 | AC-174: 1 passed, 15:16:29 to 15:19:09, run 559956433114287 |
| 8 | Dry run: `would DROP TABLE` for `smart_meter_dev.silver.weather_hourly`, `smart_meter_dev.ml.household_features_daily`, `smart_meter_dev.ml.household_labels_daily` (exactly the three; exit 0); `--confirm`: three `DROP` lines, exit 0, 15:19:59 |
| 9 | Rerun leg: 1 failed, as expected (refusal, three tables missing, `0 new runs`); rebuild leg: 1 passed, 15:20:28 to 15:23:01, run 1095873634832183; verdict: 1 passed, `pass`, `problems` empty. Both jobs idle afterwards |

Job runs started: 1 read-only (step 3) plus 2 data runs (steps 7 and 9), as planned.

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
| Reset run by the agent (C-27, U-07) | The user runs `scripts/reset_peak_model_outputs.py --confirm`, or authorizes the agent for one run | The agent ran the dry run and then `--confirm` once, on 2026-11-10 at 15:19:59 UTC, after the dry run listed exactly the three `dev` tables | The user's answer of 2026-11-10 to the live-gate question: "I run steps 1-9 with the reset" (authorizing the agent for the whole sequence, including `--confirm` for this one run, only if the dry run lists exactly the three dev tables) | No (per-run authorization the DESIGN provides for) |

No deviation needs `/iterate`. No line over 100 characters and no module-loading problem
occurred; `_load_conftest` keeps its `sys.modules` step (DA-59).

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | AC-173 to AC-175 and the A-53 and A-54 checks need the live `dev` run and the user's reset | High (gate for `/ship`, Q-38) | Closed 2026-11-10: all Pass live (Live run record) |
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

- **Weak points:** The live criteria rest on one run of the sequence on `dev`. The call-log tests pin the exact order of
  `run_leg`, so a harmless refactor needs the tests to change. AC-171 detects removed, not
  weakened, assertions.
- **Risks:** A-54 (a started run is listed at once) was checked once, with a 4.3 s gap; a slower
  listing on another day is covered only by the CI order proof. A foreign run during the rebuild
  leg costs a new sequence.
- **What I would do differently:** Decide I-08 (`from None`) in the DESIGN before building.
- **Next improvement:** Decide I-08 at `/ship` (follow-up or `/iterate`).

---

## Next Step

`/ship AC66_ZERO_NEW_RUNS`.
