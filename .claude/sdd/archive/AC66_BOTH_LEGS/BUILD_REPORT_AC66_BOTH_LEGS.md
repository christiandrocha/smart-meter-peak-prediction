# BUILD REPORT: AC-66 Both Legs

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_BOTH_LEGS |
| **Date** | 2026-11-09 |
| **Source** | DESIGN_AC66_BOTH_LEGS.md (Ready for Build) |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

Status rule applied: `Complete` only when every AC is `Pass` or explicitly accepted by the user.
All eleven criteria are `Pass`: the eight unit criteria (AC-154 to AC-161) in CI, and the three
live criteria (AC-162 to AC-164) on the `dev` workspace on 2026-11-09. The user authorized the
agent to run the live sequence and the reset (U-06) for this run, with the condition that
`--confirm` ran only if the dry run listed exactly the three `dev` tables.

---

## Summary

The combined AC-66 `after` test is replaced by a rerun-leg test, a rebuild-leg test and a verdict
test, all built on a pure rule module (`tests/support/ac66_rules.py`) that holds the precondition,
the expected MERGE metrics, the leg record, the verdict and the leg procedure with every side effect
injected. `Evidence` gains `folder`, `read_text` and `remove`; the reset script keeps its guards and
changes only its docstring and two printed lines; the runbook gets the new order. Nothing under
`src/`, `resources/`, `notebooks/` or `databricks.yml` changed (AC-161, checked against tag
`v0.6.0`). The live evidence (AC-162 to AC-164) passed on `dev` on 2026-11-09: each leg refused
before any job run in the wrong state, the rerun leg merged nothing, the rebuild leg inserted the
snapshot rows with equal checksums, and the verdict passed.

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
| AC-162 | Pass | Live, `dev`, 2026-11-09. Tables present. Newest `smart_meter_peak_model` run before: `457575248055458`; `out/evidence/ac66_rebuild_leg.json` absent. `test_ac66_rebuild_leg_...` failed with `AC-66 rebuild leg refused before any job run: silver.weather_hourly is present; ml.household_features_daily is present; ml.household_labels_daily is present; next: run the rerun leg (...), then the user runs python scripts/reset_peak_model_outputs.py --confirm`. After: newest run `457575248055458`, no active run, leg file still absent |
| AC-163 | Pass | Live, `dev`. `test_ac66_rerun_leg_...` passed (173 s), 1 run `323617648524483` (19:05:24Z to 19:07:45Z): MERGE inserted/updated/deleted 0/0/0 for `silver_weather`, `features`, `labels`; after = snapshot (21,165 / 36,480 / 36,480, checksums `2187688113305464081404` / `1034414841800262757266` / `364256581191297641381`); `snapshot_saved_at_ms` 1794251049629, record `saved_at_ms` 1794251282200, `outcome` `passed`. `test_ac66_verdict_...` then failed naming only `rebuild leg: missing: out/evidence/ac66_rebuild_leg.json is missing` (`verdict` `fail`, `rerun_saved_at_ms` 1794251282200, `rebuild_saved_at_ms` null) |
| AC-164 | Pass | Live, `dev`. Reset dry run listed exactly `smart_meter_dev.silver.weather_hourly`, `smart_meter_dev.ml.household_features_daily`, `smart_meter_dev.ml.household_labels_daily`; `--confirm` printed `DROP  DROP TABLE smart_meter_dev.silver.weather_hourly`, `DROP  DROP TABLE smart_meter_dev.ml.household_features_daily`, `DROP  DROP TABLE smart_meter_dev.ml.household_labels_daily` (exit 0). Rerun leg then failed with `AC-66 rerun leg refused before any job run: silver.weather_hourly is missing; ml.household_features_daily is missing; ml.household_labels_daily is missing; next: ... run the rebuild leg (...)`; newest run `323617648524483` and `ac66_rerun_leg.json` sha256 `e2ed5267...b73c` equal before and after. `test_ac66_rebuild_leg_...` passed (148 s), 1 run `709940216068554` (19:09:41Z to 19:11:36Z), tables absent at start, inserted 21,165 / 36,480 / 36,480 (updated and deleted 0), after = snapshot counts and checksums, `outcome` `passed`, `saved_at_ms` 1794251512101. `test_ac66_verdict_...` passed: `verdict` `pass`, `problems` `[]` |

### Live run record (2026-11-09, `dev`, run by the agent with the user's authorization)

- Profile `dev`; jobs `smart_meter_peak_model` `324283392483306`, `smart_meter_ingestion`
  `801565150507596`. Both had no active run before the deploy.
- `databricks bundle validate -t dev -p dev`: `Validation OK!`, exit 0;
  `databricks bundle deploy -t dev -p dev`: `Deployment complete!`, exit 0.
- Snapshot `test_ac66_before_rebuild_snapshot`: passed; `saved_at_ms` 1794251049629.
- DA-47 checked (I-02): `databricks jobs list-runs` listed runs newest first
  (start times 1793883466661, 1793812305949, 1793812021068).
- Final evidence files (`out/evidence/`, git-ignored), sha256:

```text
d07a2d106fae56ce9d263c21587b7d3d4b04800d8a9902405f8e911d1560d118  out/evidence/ac66_before_rebuild.json
e2ed52677519334b4fbc4c57bb98f046e1b61f7a1f17fe82a63a917ad631b73c  out/evidence/ac66_rerun_leg.json
6ead4d596df760fb8f05b5912dde4203ff2474eeb3d45be01496f54888d4089e  out/evidence/ac66_rebuild_leg.json
0bbd0addaff2a5c2a80f7bb2f8dd321517a8fe9d53c0c420e741c8deaee62d3a  out/evidence/ac66_verdict.json
```

### Live evidence sequence (on one checkout of this branch, same checkout for all steps)

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
| I-01 | AC-162, AC-163, AC-164 needed the live `dev` run and the reset | High (gate for `/ship`, Q-33) | Resolved 2026-11-09: all three `Pass` (Acceptance Criteria Evidence, Live run record) |
| I-02 | DA-47 (CLI lists runs newest first) not yet checked | Low | Resolved 2026-11-09: checked at live step 4, runs listed newest first |
| I-03 | `code-reviewer`: no High. Medium (3) and Low findings fixed: after-state mismatch through `run_leg`, preflight-before-remove test, runbook section 9 states the rerun leg comes first, snapshot wording, dead assertion replaced by exact timestamps and `after` values, unreadable snapshot case, G-52 drop test | Medium | Fixed in commit f113d88. The two Low findings left are I-04 and I-05 |
| I-04 | `code-reviewer` (Low): in `run_leg`, a `BaseException` raised while saving the `failed` record replaces the original exception, so the first cause is lost from the report | Low | Dropped 2026-11-10 (AC66_BOTH_LEGS F-01, `F_AC66_BOTH_LEGS_01.md`): implicit chaining keeps the original as `__context__` and pytest prints it; nothing is lost. Original proposal: raise the save error from the original (`raise ... from`) or chain it, with a test of `run_leg` |
| I-05 | `code-reviewer` (Low): `Evidence.save` is not atomic, so an old verdict file can survive a failing save; the verdict test still fails in that case | Low | Open: write to a temporary file in the same folder and `os.replace` it, with a test |

---

## Self-Review

- **Weak points:** The live criteria rest on one run on `dev` (2026-11-09). The
  AC-159 AST rules check the shape of today's live tests (a lambda passed as `exists=`). The
  verdict still trusts local files (accepted in the DEFINE). The "0 new runs" of AC-162 and AC-164
  is read by the operator, not asserted by the test.
- **Risks:** Between the reset and a passing rebuild leg, `dev` has no feature and label tables
  (C-23); a failing rebuild leg leaves a partial state that both legs refuse until a full run of
  `smart_meter_peak_model`. Clock order (A-49) rests on one machine's wall clock.
- **What I would do differently:** Have the leg tests read the job run list before and after a
  refusal and assert "0 new runs" themselves.
- **Next improvement:** I-04 and I-05 (open Low findings); then `/ship`.

---

## Next Step

Build PR from `build/ac66-both-legs` (after the user authorizes the push); then
`/ship AC66_BOTH_LEGS`.
