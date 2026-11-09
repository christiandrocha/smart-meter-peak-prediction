# BUILD REPORT: AC-66 Both Legs

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_BOTH_LEGS |
| **Date** | 2026-11-09 |
| **Source** | DESIGN_AC66_BOTH_LEGS.md (Ready for Build) |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

Status rule applied: `Complete` only when every AC is `Pass` or explicitly accepted by the user.
AC-162, AC-163 and AC-164 are live criteria that need the `dev` workspace and the user-run reset
(U-06, C-23), so they are `Pending` and the status stays `In Progress`. The eight unit criteria
(AC-154 to AC-161) are `Pass`.

---

## Summary

The combined AC-66 `after` test is replaced by a rerun-leg test, a rebuild-leg test and a verdict
test, all built on a pure rule module (`tests/support/ac66_rules.py`) that holds the precondition,
the expected MERGE metrics, the leg record, the verdict and the leg procedure with every side effect
injected. `Evidence` gains `folder`, `read_text` and `remove`; the reset script keeps its guards and
changes only its docstring and two printed lines; the runbook gets the new order. Nothing under
`src/`, `resources/`, `notebooks/` or `databricks.yml` changed (AC-161, checked against tag
`v0.6.0`). The live evidence (AC-162 to AC-164) has not been run: it needs the user.

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | `tests/support/ac66_rules.py` | Created | `ruff check`, `ruff format`; `tests/test_ac66_rules.py` (78 tests after review fixes) |
| 2 | `tests/integration/conftest.py` | Modified (`Evidence`: `folder`, `read_text`, `remove`) | `ruff`; `test_ac158_real_evidence_class_keeps_its_shipped_defaults`; `tests/test_integration_layout.py` |
| 3 | `tests/test_ac66_rules.py` | Created | 78 passed |
| 4 | `tests/integration/test_peak_data.py` | Modified (docstring, helpers, three live tests, combined test removed) | `ruff`; `pytest -m integration -o addopts= --collect-only -k ac66` lists the four names (no live run); AC-159, AC-161 tests |
| 5 | `tests/test_integration_layout.py` | Modified (collection assertion: three names) | 6 passed |
| 6 | `scripts/reset_peak_model_outputs.py` | Modified (docstring lines 3 and 26 area, two printed lines) | `ruff`; `tests/test_peak_reset_script.py` 3 passed; AC-161 reset digest equals `v0.6.0` |
| 7 | `docs/runbooks/peak_model.md` | Modified (sections 8 and 9) | AC-160 tests; `check_specs.py` |
| 8 | `tests/test_ac66_legs_docs.py` | Created | 6 passed |

Entries 9 to 11 are "Update at /ship" and were not touched.

Commits (branch `build/ac66-both-legs`, not pushed): see the table at the end of the hand-off.

---

## Acceptance Criteria Evidence

| AC | Result | Evidence |
|---|---|---|
| AC-154 | Pass | `tests/test_ac66_rules.py::test_ac154_both_legs_on_the_current_snapshot_pass_deterministically`, `::test_ac154_secret_like_strings_never_reach_the_record_or_the_message`, `::test_ac154_rules_import_no_sdk_and_read_no_clock` |
| AC-155 | Pass | `::test_ac155_missing_evidence_names_each_missing_leg_or_the_snapshot` (cases a to d) |
| AC-156 | Pass | `::test_ac156_stale_out_of_order_failed_inconsistent_or_malformed_legs_fail` (cases a to j), `::test_ac156_odd_inputs_never_raise` (3 slots, text and field mutations, 10,000 `[`, NaN, 400-digit int) |
| AC-157 | Pass | `::test_ac157_precondition_over_all_table_states` (32 cases) |
| AC-158 | Pass | `::test_ac158_leg_passes_and_writes_the_full_record` (2 legs), `::test_ac158_leg_failure_leaves_no_passed_record` (2 legs x merges, assertion, BaseException), `::test_ac158_wrong_state_refuses_before_the_runner` (6 refusals, 0 runner calls, bytes equal), `::test_ac158_unsaved_failed_record_does_not_mask_the_failure`, plus an unknown-leg refusal and a check of the real `Evidence` defaults |
| AC-159 | Pass | `tests/test_ac66_legs_docs.py::test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state`; `tests/test_integration_layout.py` (6 passed) |
| AC-160 | Pass | `::test_ac160_runbook_docstring_and_script_state_the_order`, `::test_ac160_every_ac66_selector_selects_exactly_one_test` (4 selectors, one node each; `ac66_after` selects none) |
| AC-161 | Pass | `::test_ac161_production_files_and_reset_guards_equal_v060` (tag `v0.6.0` present locally, so the tag comparison also ran), `::test_ac161_snapshot_test_and_its_helpers_are_kept`, `::test_ac161_specs_are_clean`; full gates in the Verification Log |
| AC-162 | Pending (user-run live evidence) | Not run: needs the `dev` workspace. Commands in "Live evidence to run" below (step 4) |
| AC-163 | Pending (user-run live evidence) | Not run: same (step 5) |
| AC-164 | Pending (user-run live evidence) | Not run: needs the user-run reset (`--confirm`, U-06, C-23) (steps 6 and 7). The agent did not run the reset |

### Live evidence to run (user, on a clean checkout of this branch, same checkout for all steps)

DESIGN live plan. `out/evidence/` is git-ignored and local to one checkout (C-25). Peak job id:
`databricks jobs list --name smart_meter_peak_model -p dev`, or the Jobs UI (the job name carries
the `[dev <user>]` prefix).

```bash
export DATABRICKS_CONFIG_PROFILE=dev
# 1. deploy (bundle content equals v0.6.0); record both exit codes
databricks bundle validate -t dev -p dev ; databricks bundle deploy -t dev -p dev
# 2. ingestion and peak jobs idle; the three tables present
databricks jobs list-runs --job-id <ingestion job id> --active-only -p dev     # lists nothing
databricks jobs list-runs --job-id <peak job id> --active-only -p dev          # lists nothing
# 3. snapshot
pytest -m integration tests/integration/test_peak_data.py -k "ac66_before"
# 4. AC-162: before/after values of the peak job's newest run and of the leg file
databricks jobs list-runs --job-id <peak job id> -p dev                        # note the newest run id
sha256sum out/evidence/ac66_rebuild_leg.json                                   # or "absent"
pytest -m integration tests/integration/test_peak_data.py -k "ac66_rebuild_leg" # expected: FAILS, "refused before any job run"
databricks jobs list-runs --job-id <peak job id> -p dev                        # same newest run id
sha256sum out/evidence/ac66_rebuild_leg.json                                   # same hash (or "absent")
# 5. AC-163
pytest -m integration tests/integration/test_peak_data.py -k "ac66_rerun_leg"  # passes, 1 run
pytest -m integration tests/integration/test_peak_data.py -k "ac66_verdict"    # expected: FAILS, names the rebuild leg only
cat out/evidence/ac66_before_rebuild.json out/evidence/ac66_rerun_leg.json out/evidence/ac66_verdict.json
# 6. U-06 (user only): dry run, then drop the three tables; paste the DROP lines
python scripts/reset_peak_model_outputs.py
python scripts/reset_peak_model_outputs.py --confirm
# 7. AC-164
databricks jobs list-runs --job-id <peak job id> -p dev ; sha256sum out/evidence/ac66_rerun_leg.json
pytest -m integration tests/integration/test_peak_data.py -k "ac66_rerun_leg"   # expected: FAILS, names the three missing tables
databricks jobs list-runs --job-id <peak job id> -p dev ; sha256sum out/evidence/ac66_rerun_leg.json   # unchanged
pytest -m integration tests/integration/test_peak_data.py -k "ac66_rebuild_leg" # passes, 1 run, inserted 21,165 / 36,480 / 36,480
pytest -m integration tests/integration/test_peak_data.py -k "ac66_verdict"     # passes, empty problems
cat out/evidence/ac66_rerun_leg.json out/evidence/ac66_rebuild_leg.json out/evidence/ac66_verdict.json
```

Paste into the rows above: the three test outcomes per step, the values of the leg and verdict
records (snapshot `saved_at_ms`, merges, counts, run ids, problems), the run ids before and after
each refused leg, and the DROP lines. DA-47 assumption (the CLI lists runs newest first) is checked
at step 4; fallback is the Jobs UI run list. A failed rebuild leg can leave a partial state: run
`smart_meter_peak_model` in full, then restart at step 3 (runbook section 9).

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `ruff check . && ruff format --check .` | `All checks passed!`; `128 files already formatted` |
| Tests | `pytest` (default, no integration marker) | 737 passed, 92 deselected, 1 xfailed (the shipped strict xfail), 0 failed |
| Spec check | `python scripts/check_specs.py` | 63 document(s) checked, 0 error(s), 8 warning(s) (pre-existing) |
| Pre-commit | `pre-commit run --all-files` | all hooks Passed (run again at the final commit) |
| Collection | `pytest -m integration -o addopts= --collect-only -k ac66 tests/integration/test_peak_data.py` | 4/14 collected: the four AC-66 names; no live test run |
| Tag | `git tag -l v0.6.0` | `v0.6.0` present; AC-161 golden constants computed from it |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| DA-44 loading the conftest by path | Load `tests/integration/conftest.py` under a private name | Also registers the module in `sys.modules` under that name before executing it | `dataclasses` resolves string annotations through `sys.modules`; without it the load fails with `AttributeError`. Mechanical fix | No (small mechanical fix) |
| Reset script usage line | Line 26: `--confirm  # drop; then the rebuild leg (-k ac66_rebuild_leg)` | `--confirm  # drop; then -k ac66_rebuild_leg` | The design text is 111 characters, over the 100-character ruff limit; same content, `daily job` still absent (AC-160) | No (mechanical) |
| `test_peak_data.py` module docstring first line | AC list in the first line gains "AC66_BOTH_LEGS AC-162 to AC-164" | The AC list line is unchanged; a second line names the AC66_BOTH_LEGS live criteria | The one-line version is over 100 characters | No (mechanical) |
| Leg-test and docs-test details not fixed by the DESIGN | `run_leg` checks | `run_leg` refuses an unknown leg before any read; the `AC-158` tests add an unknown-leg case and a check of `Evidence` defaults | Covers G-46 "unknown leg" and DA-44 "defaults unchanged" explicitly | No (within the design) |

No deviation needs `/iterate`.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | AC-162, AC-163, AC-164 not run (live, user-run reset). Build status stays `In Progress` until their evidence is pasted | High (gate for `/ship`, Q-33) | The user runs the sequence above; then this report is completed |
| I-02 | DA-47 (CLI lists runs newest first) not yet checked | Low | Checked at live plan step 4 |
| I-03 | `code-reviewer`: no High. Medium (3) and Low findings fixed: after-state mismatch through `run_leg`, preflight-before-remove test, runbook section 9 states the rerun leg comes first, snapshot wording, dead assertion replaced by exact timestamps and `after` values, unreadable snapshot case, G-52 drop test | Medium | Fixed in commit f113d88. Left as is (Low, accepted): a `BaseException` during the failed-record save replaces the original; `Evidence.save` is non-atomic so an old verdict file can survive a failing save (the test still fails) |

---

## Self-Review

- **Weak points:** The three live criteria are unproven until the user runs the sequence. The
  AC-159 AST rules check the shape of today's live tests (a lambda passed as `exists=`). The
  verdict still trusts local files (accepted in the DEFINE). The "0 new runs" of AC-162 and AC-164
  is read by the operator, not asserted by the test.
- **Risks:** Between the reset and a passing rebuild leg, `dev` has no feature and label tables
  (C-23); a failing rebuild leg leaves a partial state that both legs refuse until a full run of
  `smart_meter_peak_model`. Clock order (A-49) rests on one machine's wall clock.
- **What I would do differently:** Have the leg tests read the job run list before and after a
  refusal and assert "0 new runs" themselves.
- **Next improvement:** Run the live sequence, paste the evidence, set the status `Complete`, then
  `/ship`.

---

## Next Step

User runs the live sequence (AC-162 to AC-164); then `/ship AC66_BOTH_LEGS`.
