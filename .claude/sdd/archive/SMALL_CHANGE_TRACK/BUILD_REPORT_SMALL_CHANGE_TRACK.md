# BUILD REPORT: Small Change Track

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SMALL_CHANGE_TRACK |
| **Date** | 2026-11-06 |
| **Source** | DESIGN_SMALL_CHANGE_TRACK.md |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

---

## Summary

`scripts/check_specs.py` gained the `CHANGE` phase, a literal `FINAL_STATUS` map, an error for
every unrecognized `.md` name in `features/` and `reports/`, `check_change` (Eligibility, Rule
Changes gate, AC traceability, evidence commit), change folders in the archive, and rule (b) on
CHANGE documents. The CHANGE template, README, `git.md` and `CLAUDE.md` describe the track. The
code was last changed on commit 4668af3 (branch `build/small-change-track`), which closes
SMALL_CHANGE_TRACK I-03 and I-08 on the user's decision of 2026-11-06; the report commit that
follows touches only this file.

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | scripts/check_specs.py | Modified | ruff check and format; tests AC-120 to AC-131; `check_specs.py` 0 errors |
| 2 | .claude/sdd/templates/CHANGE_TEMPLATE.md | Created | `test_ac128_*`, `test_all_templates_have_required_sections` |
| 3 | tests/test_check_specs.py | Modified | `pytest tests/test_check_specs.py`: 105 passed |
| 4 | .claude/sdd/README.md | Modified | `test_ac130_docs_describe_the_change_track` |
| 5 | docs/conventions/git.md | Modified | same test; no rule under "Rules for agents" changed |
| 6 | CLAUDE.md | Modified | same test; golden rules unchanged |
| 7 | .claude/sdd/reports/BUILD_REPORT_SMALL_CHANGE_TRACK.md | Created | `check_specs.py` |

---

## Acceptance Criteria Evidence

| AC | Result | Evidence |
|---|---|---|
| AC-120 | Pass | `test_ac120_repository_has_no_errors`; `python scripts/check_specs.py`: 0 errors (output in Verification Log) |
| AC-121 | Pass | `test_ac121_unrecognized_names_fail` (6 cases, `.gitkeep` gives none) |
| AC-122 | Pass | `test_ac122_change_document_rules` (6 cases), `test_ac122_no_acceptance_criteria_rows_is_an_error` |
| AC-123 | Pass | `test_ac123_final_status_is_explicit` |
| AC-124 | Pass | `test_ac124_eligibility_rows` (5 cases), `test_ac124_missing_row_names_the_criterion` |
| AC-125 | Pass | `test_ac125_change_traceability_and_evidence_commit` (7 cases), `test_ac125_fail_word_in_evidence_text_is_not_a_failure` |
| AC-126 | Pass | `test_ac126_archived_change_folders` |
| AC-127 | Pass | `test_ac127_rules_b_and_c_read_change_documents` |
| AC-128 | Pass | `test_ac128_change_template_sections_and_criteria`, `test_ac128_template_copied_as_draft_has_no_missing_section`, `test_all_templates_have_required_sections` |
| AC-129 | Pass | `test_ac129_self_test_simulates_change_documents`: only the Complete document added, no SHIPPED, 0 errors |
| AC-130 | Pass | `test_ac130_docs_describe_the_change_track` |
| AC-131 | Pass | `test_ac131_relaxing_needs_the_rule_changes_gate` (6 cases), `test_ac131_template_example_fence_does_not_hide_the_real_section` |

---

## Verification Log

Evidence commit: 4668af3

| Step | Command | Result |
|---|---|---|
| Lint | `ruff check . && ruff format --check .` | All checks passed; 125 files formatted |
| Tests (spec checker) | `pytest tests/test_check_specs.py` on 4668af3 | 115 passed |
| Tests (full) | `pytest` on 4668af3 | 657 passed, 90 deselected, 1 xfailed |
| Spec check | `python scripts/check_specs.py` on 4668af3 | 56 document(s) checked, 0 error(s), 2 warning(s): INGESTION_GUARD I-11, INGESTION_GUARD I-12 |
| Self-test | AC-119 on the real repository | no document of `features/` or `reports/` is final yet, so it adds none (the AC-119 test skips by its own existing rule); AC-129 covers CHANGE |
| Hooks | `pre-commit run --all-files` | all hooks Passed (9 of 9) |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| G-41 regex | Three captured groups | Four columns: ID, criterion, result, evidence; result is group 2, evidence group 3 | The template and the DEFINE table have a criterion column | DESIGN updated via /iterate 2026-11-06 (G-41) |
| Template Rule Changes | Optional section | Fenced example inside Eligibility, so the template headings equal the ten sections (AC-128) | A real `## Rule Changes` heading would break the heading equality | No |
| `check_change` | AC-125 as listed | Also errors on no AC rows, tests only the result cell for `Fail`, and requires a digit in the SHA | Code-review findings | DESIGN updated via /iterate 2026-11-06 (G-42, G-43) |
| Evidence results | FR-78 forbids `Fail` in a Complete CHANGE document | Also errors on `Not run` and on `Deferred` without a reason; `Deferred: <reason>` passes and is listed as a warning | SMALL_CHANGE_TRACK I-03, user decision 2026-11-06 | DESIGN updated via /iterate 2026-11-06 (G-43) |
| `load_docs` | `load_docs(root, report)` | `report` is optional | Direct callers in tests | No |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | Code review (Medium): a fenced `## Rule Changes` example hid the real section; headings matched by prefix | Medium | Fixed in 0e56f72 with a test |
| I-02 | Code review (Medium): a CHANGE document with no AC rows passed | Medium | Fixed in 0e56f72 with a test |
| I-03 | Code review (Medium): `Not run` in Evidence passes a Complete document (FR-78 forbids only `Fail`) | Medium | Fixed in 4668af3 with tests (user decision 2026-11-06: `Not run` blocks `Complete`; `Deferred: <reason>` passes and is listed) |
| I-04 | Code review (Low): `Fail` matched any Evidence cell; SHA matched hex words | Low | Fixed in 0e56f72 with tests |
| I-05 | Code review (Low): eligibility regex `\s*` can cross lines on a malformed 3-column row | Low | Not fixed: the cell classes exclude the newline, so a cell stays on one line, but the `\s*` before each closing pipe can still consume a newline, so a malformed three-column row still reads into the next row; this iteration changed documents only and the cell has no test; tracked as SMALL_CHANGE_TRACK F-05 in SHIPPED_2026-11-06.md |
| I-06 | Code review (Low): change folder does not check the document name or that there is exactly one | Low | Resolved: `load_archive` takes a file as the CHANGE document only when its stem equals `CHANGE_<folder>`, so at most one file can match, and `check_folder` reports every other file in a change folder (SHIPPED, other phase, misnamed) as a rule (a) error; the AC-126 test covers the SHIPPED and DEFINE cases, the misnamed-file case has no dedicated test (SMALL_CHANGE_TRACK F-06 narrowed to that test gap in SHIPPED_2026-11-06.md) |
| I-07 | Code review (Low): loose substring asserts in AC-128/AC-130; AC-126 selects errors by substring | Low | Not fixed: the asserts are unchanged in `tests/test_check_specs.py` (`needle in text` in `test_ac128_change_template_sections_and_criteria` and `test_ac130_docs_describe_the_change_track`, error selection by `f in e.split(":")[0]` in `test_ac126_archived_change_folders`) and this iteration changes documents only; tracked as SMALL_CHANGE_TRACK F-07 in SHIPPED_2026-11-06.md |
| I-08 | Code review (Low): `docs/conventions/naming.md:42` example says `feat/...` | Low | Fixed in 4668af3 (`build/` and `change/` examples) |
| I-09 | Code review (Low): G-41 text of the DESIGN is stale | Low | Fixed by /iterate 2026-11-06 (DESIGN G-41), together with the extra checks of I-02, I-04 and I-03 (DESIGN G-42, G-43) |

Code review (`code-reviewer`): 0 High, 3 Medium, 8 Low. Mediums I-01 and I-02 and the Lows in I-04
were fixed; I-03 and I-08 were fixed afterwards on the user's decision; the rest are recorded
above with their disposition.

---

## Self-Review

- **Weak points:** E1 to E8 are only checked as declared (DESIGN OD-40). The Rule Changes gate
  checks presence of parts, not their truth. I-05 (row regex) and I-07 (loose asserts) remain
  unfixed gaps, tracked as SMALL_CHANGE_TRACK F-05 and F-07.
- **Risks:** The unrecognized-name error fails any stray note in `features/`. The tests for
  AC-129 exercise a helper that lives in the test file.
- **What I would do differently:** Prototype the template against `check_change` before writing
  the DESIGN regex; the fenced-example trap was found only in review.
- **Next improvement:** Ship with follow-ups F-01 (history checks) and F-02 (template port), and
  close I-05 and I-07 later; I-09 was closed by `/iterate` on 2026-11-06.

---

## Next Step

`/ship SMALL_CHANGE_TRACK`

---

## Change Log

| Date | Change | Reason | Impact |
|---|---|---|---|
| 2026-11-06 | Deviations table: DESIGN-updated column set for G-41, the extra `check_change` checks and the `Not run` / `Deferred` rule; findings I-05 to I-07 closed with a disposition (I-06 resolved, I-05 and I-07 not fixed); I-09 fixed | `/iterate` on the DESIGN, user request 2026-11-06, docs only | Status stays Complete. SHIPPED Follow-ups SMALL_CHANGE_TRACK F-05, SMALL_CHANGE_TRACK F-06, SMALL_CHANGE_TRACK F-07 and SMALL_CHANGE_TRACK F-09 updated; no code changed |
