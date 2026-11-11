# FOLLOW-UP: AC66_ZERO_NEW_RUNS F-01 - the first-read gate is total

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC66_ZERO_NEW_RUNS F-01 |
| **Source spec** | AC66_ZERO_NEW_RUNS |
| **Source finding** | AC66_ZERO_NEW_RUNS I-07 |
| **Source documents** | `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/SHIPPED_2026-11-10.md` (Follow-ups row F-01), `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/BUILD_REPORT_AC66_ZERO_NEW_RUNS.md` (Issues row I-07) |
| **Created** | 2026-11-11 |
| **Status** | Closed |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC66_ZERO_NEW_RUNS I-07: "the first-read gate is not total for a list subclass whose `__iter__`
raises (raw error instead of the 'could not be read' message)". AC66_ZERO_NEW_RUNS G-54 says a
read that is not a usable list of run ids stops the leg with the "could not be read" message.

`run_leg` in `tests/support/ac66_rules.py` (lines 630 to 632) gates the first read with
`run_ids(before) is None`; `run_ids` iterates the value, so an exception raised while iterating
escapes the gate. Measured on 2026-11-11 on `main` (f69fc7e) with a `list` subclass whose
`__iter__` raises `RuntimeError("no iteration")`:

```text
RuntimeError | no iteration | calls: []
count_runs: comparison rule
```

The leg stops before any other side effect, as it should, but with the raw error, whose text is
the reader's own: the leg messages print only an exception's class name, because a reader message
can hold a host name or a token (AC66_ZERO_NEW_RUNS G-57). `count_runs` stays total, as
designed (`comparison rule`). `PeakRunner.run_ids` returns a plain `list`, so there is no live
impact.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Predicted: `tests/support/ac66_rules.py`, `tests/test_ac66_rules.py`, plus this file, the CHANGE document and the two source rows |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | The fix brings the gate in line with AC66_ZERO_NEW_RUNS G-54 and keeps the designed `count_runs` result for this input (`comparison rule`, DESIGN test strategy of AC-165), so no archived DEFINE or DESIGN changes. Making `run_ids` itself total would change that result and need `/iterate`; it is not done. The SHIPPED and BUILD_REPORT rows are annotated at closure (allowed) |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None |
| E6 | No change under `tests/integration/` | Yes | `tests/support/` and `tests/test_ac66_rules.py` only; the live legs in `tests/integration/` are unchanged |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: CHANGE track (every row `Yes`). Document: `CHANGE_AC66_FIRST_READ_GATE.md`, branch
`change/ac66-first-read-gate`.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A first read that is a `list` subclass whose `__iter__` raises an `Exception` | A leg runs | It stops with the "could not be read (first read: not a list of integer run ids)" message, before any other side effect, and the message does not hold the error's text |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from AC66_ZERO_NEW_RUNS I-07 |
| **Priority** | Now |
| **Target** | Next release after v0.7.2 (test helper only) |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #75 (branch `change/ac66-first-read-gate`), recorded by a closure PR as in `F_AC119_EMPTY_ARCHIVE_01.md`; branch removed (remote by GitHub on merge, local with `git branch -d`) |
| **Merge commit** | b601e5d, read with `gh pr view 75 --json state,mergedAt,mergeCommit`: `MERGED`, 2026-11-11T19:31:19Z |
| **Work done in** | `CHANGE_AC66_FIRST_READ_GATE.md` (archived in `archive/AC66_FIRST_READ_GATE/`): fix 1222e5d adds `_usable` to `tests/support/ac66_rules.py` and gates the first read of `run_leg` with it; `run_ids` and `count_runs` are unchanged. DC-01 is met: `test_ac186_a_read_that_cannot_be_iterated_stops_at_the_first_read` passes for both legs on 1222e5d and fails on f69fc7e |
| **Source rows updated** | `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/SHIPPED_2026-11-10.md:148`, Follow-ups row F-01: the Target release cell reads "Closed 2026-11-11 by AC66_FIRST_READ_GATE"; `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/BUILD_REPORT_AC66_ZERO_NEW_RUNS.md:167`, Issues row I-07: the Follow-up cell no longer starts with `Open` |
| **check_specs.py after the update** | `72 document(s) checked, 0 error(s), 9 warning(s)` on the change branch: the rule (b) warning for AC66_ZERO_NEW_RUNS I-07 is gone |

---

## Self-Review

- **Weak points:** The input is artificial; the live reader cannot return it.
- **Risks:** A fix in `run_ids` would look simpler but change a designed result (E4); the fix
  stays in the gate.
- **Next step:** After the merge, record the PR number and merge commit with a closure PR.
