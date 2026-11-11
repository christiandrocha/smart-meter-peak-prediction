# CHANGE: AC-66 first-read gate for a read that cannot be iterated

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_FIRST_READ_GATE |
| **Date** | 2026-11-11 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/ac66-first-read-gate` |
| **Status** | Complete |
| **Source** | Follow-up AC66_ZERO_NEW_RUNS F-01 (`.claude/sdd/follow-ups/F_AC66_ZERO_NEW_RUNS_01.md`, triage: every criterion `Yes`), from AC66_ZERO_NEW_RUNS I-07 |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

`run_leg` in `tests/support/ac66_rules.py` gates the first run-list read with
`run_ids(before) is None` (lines 630 to 632). `run_ids` iterates the value, so a `list` subclass
whose `__iter__` raises escapes the gate with the raw exception instead of the "could not be
read" message that AC66_ZERO_NEW_RUNS G-54 and the DA-52 message shapes require
(AC66_ZERO_NEW_RUNS I-07). Measured on 2026-11-11 on `main` (f69fc7e): `run_leg("rerun", ...)`
with such a read raises `RuntimeError: no iteration` and calls nothing else; `count_runs` on the
same read gives `comparison rule`, as designed. The raw error carries the reader's text, which
the leg messages leave out on purpose (G-57: class names only). No live impact: the live reader
returns a plain `list`.

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD` on 9bcd3c9: `M` `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/BUILD_REPORT_AC66_ZERO_NEW_RUNS.md`, `M` `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/SHIPPED_2026-11-10.md`, `A` `.claude/sdd/features/CHANGE_AC66_FIRST_READ_GATE.md`, `A` `.claude/sdd/follow-ups/F_AC66_ZERO_NEW_RUNS_01.md`, `M` `tests/support/ac66_rules.py`, `M` `tests/test_ac66_rules.py`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | Same output: `A` only for this document and the follow-up file; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: under `archive/` only the Follow-ups row of AC66_ZERO_NEW_RUNS F-01 (SHIPPED, line 148) and the Issues row of AC66_ZERO_NEW_RUNS I-07 (BUILD_REPORT, line 167), one line each; no archived DEFINE or DESIGN. The fix implements G-54 as written and keeps the designed `count_runs` result for this read (`comparison rule`, DESIGN test strategy of AC-165) |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor any file under `.claude/sdd/templates/` |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`: empty (0 lines) |

---

## Scope

**In scope:**
- A private helper in `tests/support/ac66_rules.py` that tells whether a read is usable and
  turns an `Exception` raised while checking it into "unusable"; `run_leg` gates the first read
  with it. A `BaseException` that is not an `Exception` still propagates (G-54).
- Unit tests in `tests/test_ac66_rules.py` for both legs.
- Closing AC66_ZERO_NEW_RUNS F-01: the follow-up file, the SHIPPED Follow-ups row and the
  BUILD_REPORT Issues row.

**Out of scope:**
- `run_ids` and `count_runs`: unchanged, so `count_runs` keeps `comparison rule` for this read
  and the shipped AC-165 test stays byte-equal.
- The second reads: they already go through `count_runs`, which is total.
- `raise ... from error` versus `from None` (AC66_ZERO_NEW_RUNS F-02, needs `/iterate`).
- `tests/integration/` and the live legs: no live run is needed.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-186 | A first read that is a `list` subclass whose `__iter__` raises `RuntimeError` with a secret-looking text | The rerun or the rebuild leg runs | It raises `AssertionError` with "the run list of smart_meter_peak_model could not be read (first read: not a list of integer run ids)"; the only call is the one read; no evidence file changes; the message does not hold the error's text and has no cause |
| AC-187 | A first read whose `__iter__` raises a `BaseException` that is not an `Exception` | The leg runs | That exception propagates unchanged and nothing else is called (G-54) |
| AC-188 | The changed files | `pytest tests/test_ac66_rules.py tests/test_ac66_legs_docs.py`, the full `pytest`, `git diff`, `ruff` and `check_specs.py` | All pass; the AC-165 test that expects `comparison rule` is unchanged; `run_ids` and `count_runs` are unchanged; the shipped AC66_BOTH_LEGS AC-154 import check and the AC66_ZERO_NEW_RUNS AC-171 checks pass |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-186 | Unit | `tests/test_ac66_rules.py::test_ac186_a_read_that_cannot_be_iterated_stops_at_the_first_read` | Parametrized over both legs; `Fakes` with reply 1 = a list subclass raising `RuntimeError("token=s3cr3t")` from `__iter__`; asserts the message, `fakes.calls == ["runs"]`, the evidence files byte-equal, `s3cr3t` absent, `__cause__ is None` |
| AC-187 | Unit | `tests/test_ac66_rules.py::test_ac187_a_base_exception_while_iterating_the_first_read_propagates` | Same, with `__iter__` raising the module's `Stop` (`BaseException`); `pytest.raises(Stop)` and `fakes.calls == ["runs"]` |
| AC-188 | Command | `pytest -q tests/test_ac66_rules.py tests/test_ac66_legs_docs.py`; `pytest -q -rs`; `git diff -U0 origin/main...HEAD -- tests/`; `ruff check . && ruff format --check .`; `python scripts/check_specs.py` | Summaries pasted; the diff shows no line of `run_ids`, `count_runs` or the AC-165 tests |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `tests/support/ac66_rules.py` | Modify | The usable-read helper and the first-read gate of `run_leg` |
| 2 | `tests/test_ac66_rules.py` | Modify | AC-186 and AC-187 tests |
| 3 | `.claude/sdd/follow-ups/F_AC66_ZERO_NEW_RUNS_01.md` | Create, then close | The follow-up task file |
| 4 | `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/SHIPPED_2026-11-10.md`, `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/BUILD_REPORT_AC66_ZERO_NEW_RUNS.md` | Modify (one row each) | The rows of AC66_ZERO_NEW_RUNS F-01 (SHIPPED Follow-ups) and AC66_ZERO_NEW_RUNS I-07 (BUILD_REPORT Issues) point to AC66_FIRST_READ_GATE |
| 5 | `.claude/sdd/features/CHANGE_AC66_FIRST_READ_GATE.md` | Create, then move to `archive/AC66_FIRST_READ_GATE/` | This document |

---

## Evidence

Evidence commit: 9bcd3c9

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/AC66_FIRST_READ_GATE/`). `python scripts/check_specs.py`
runs again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-186 | Pass | `tests/test_ac66_rules.py::test_ac186_a_read_that_cannot_be_iterated_stops_at_the_first_read[rerun]` and `[rebuild]` passed on 9bcd3c9 (fix 1222e5d); with `tests/support/ac66_rules.py` of f69fc7e both fail (`2 failed, 2 passed` for `-k "ac186 or ac187"`), so the test guards the fix |
| AC-187 | Pass | `::test_ac187_a_base_exception_while_iterating_the_first_read_propagates[rerun]` and `[rebuild]` passed: the same `Stop` object propagates and `fakes.calls == ["runs"]`. It passes on f69fc7e as well: it guards that the new gate does not swallow a BaseException |
| AC-188 | Pass | `pytest -q tests/test_ac66_rules.py tests/test_ac66_legs_docs.py`: `137 passed` (AC66_BOTH_LEGS AC-154 import and clock check and AC66_ZERO_NEW_RUNS AC-171 checks among them); full `pytest -q -rs`: `796 passed, 1 skipped, 92 deselected, 1 xfailed` (792 before plus the four new cases); `git diff -U0 origin/main...HEAD -- tests/` has three hunks: `@@ -535,0 +536,12 @@` (the helper, after `_as_run_id`), `@@ -631 +643 @@` (the gate line of `run_leg`) and `@@ -1025,0 +1026,47 @@` (the tests at the end of the file), so `run_ids` (lines 500 to 504), `count_runs` (507 to 525) and the AC-165 tests are unchanged; `ruff check .` and `ruff format --check .` clean; `python scripts/check_specs.py`: `72 document(s) checked, 0 error(s), 9 warning(s)` |

In a `Complete` document `check_specs.py` reports `Fail` and `Not run` as errors. A deliberate
deferral is written `Deferred: <reason>`: the check accepts it and lists it as a warning, so it
stays visible without blocking the change. `Deferred` without a reason is an error.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The first read is checked twice, once by the gate and once inside `count_runs`; a read that changes while it is iterated could pass the gate and then fail `count_runs`, which reports `comparison rule`, never a pass or a clean refusal | Low | Accepted: no live reader can return such a read |

---

## Self-Review

- **Weak points:** The input is artificial; the live reader cannot return it.
- **Risks:** A gate that checks the read twice (once in the gate, once in `count_runs`) could see
  two answers from a read that changes while it is iterated; `count_runs` then reports
  `comparison rule`, never a pass or a clean refusal.
- **What I would do differently:** Read the archived DESIGN test strategy before choosing where
  to fix: the first idea, a total `run_ids`, would have changed the designed AC-165 result
  (`comparison rule`) and needed `/iterate`.
- **Next improvement:** After the merge, record the PR number and merge commit in
  `F_AC66_ZERO_NEW_RUNS_01.md` with a closure PR, and add the CHANGELOG entry there.
