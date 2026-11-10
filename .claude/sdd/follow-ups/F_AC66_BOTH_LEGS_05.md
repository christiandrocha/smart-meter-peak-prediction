# FOLLOW-UP: AC66_BOTH_LEGS F-05 - the AC-159 shape checks and a refactor of the live AC-66 tests

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC66_BOTH_LEGS F-05 |
| **Source spec** | AC66_BOTH_LEGS |
| **Source finding** | none |
| **Source documents** | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` (Follow-ups row F-05; DESIGN and BUILD_REPORT Self-Review) |
| **Created** | 2026-11-10 |
| **Status** | Dropped |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC66_BOTH_LEGS F-05: "The AC-159 AST rules check the shape of today's live tests (a lambda passed
as `exists=`). A legitimate refactor of the live tests needs this test to change too".

`tests/test_ac66_legs_docs.py::test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state`
guards the PEAK_MODEL F-15 defect (a test that chooses its mode from the table state) by parsing
`tests/integration/test_peak_data.py`: exactly two direct calls of `ac66_rules.run_leg`, one per
leg test with a constant `leg=`; `exists=` is a `lambda`; `_table_exists` is called only in
`_tables_present`, and `_tables_present` is used only inside those lambdas. AC66_ZERO_NEW_RUNS
AC-170 (`test_ac170_both_live_legs_pass_a_reader_bound_to_the_peak_job`) checks `runs=` the same
way.

Checked on 2026-11-10 on main eb3510e: a copy of the live module in which both leg tests call one
shared helper `_run_leg(leg, ...)` (the helper holds the single `run_leg` call, with the same
keyword arguments), run through the two test functions with `LIVE` pointed at the copy:

```text
shipped test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state PASS
shipped test_ac170_both_live_legs_pass_a_reader_bound_to_the_peak_job PASS
refactored test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state FAIL at line 250 : assert len(run_legs) == 2
refactored test_ac170_both_live_legs_pass_a_reader_bound_to_the_peak_job FAIL at line 440 : assert seen == 2
```

So the follow-up describes a real cost, but it is the cost of a structural guard: a check that
accepted the helper would have to follow the constant `leg` through a call, which is the kind of
indirection a mode-by-state test could hide behind. Loosening only `exists=` (for example to accept
`functools.partial`) would not make the helper refactor pass.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | No code change: this file and one archived SHIPPED row only |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | Annotation of an archived SHIPPED row only (allowed) |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None |
| E6 | No change under `tests/integration/` | Yes | None |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: no work to do; dropped as an accepted trade-off (Closure).

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A future change that refactors the live AC-66 leg tests | Its unit tests run | AC-159 (and AC66_ZERO_NEW_RUNS AC-170) fail on the shape checks and are updated in that same change, keeping the guard against a test that chooses its mode from the table state. No change is made now |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | none |
| **Priority** | Later |
| **Target** | Dropped on 2026-11-10: accepted trade-off; the refactoring change updates the checks |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #65 (branch `change/drop-ac66-both-legs-f05`), recorded by a closure PR as in `F_AC66_BOTH_LEGS_01.md`; branch removed (remote by GitHub on merge, local with `git branch -d`) |
| **Merge commit** | c2dabc6, read with `gh pr view 65 --json state,mergedAt,mergeCommit`: `MERGED`, 2026-11-10T19:34:37Z |
| **Work done in** | Dropped: the shape checks are the mechanism of the AC-159 guard; a looser check that passes the likely refactor (one shared helper) would weaken it, and loosening `exists=` alone does not pass that refactor (evidence in Problem). The user chose to drop it on 2026-11-10 rather than loosen `exists=` and `runs=` or leave it unscheduled |
| **Source rows updated** | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md`, Follow-ups row F-05: the target cell reads "Dropped 2026-11-10". F-05 has no BUILD_REPORT finding row, so rule (b) never warned on it |
| **check_specs.py after the update** | `69 document(s) checked, 0 error(s), 11 warning(s)`, as on `main` (no warning was tied to F-05) |

---

## Self-Review

- **Weak points:** The cost stays: whoever refactors the live leg tests meets two failing unit tests
  and must understand why they exist. Their docstrings and the PEAK_MODEL F-15 history explain it.
- **Risks:** Someone could "fix" the failing checks by deleting them in a refactor; a reviewer of
  that change has to catch it.
- **Next step:** None.
