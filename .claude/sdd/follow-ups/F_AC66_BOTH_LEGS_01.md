# FOLLOW-UP: AC66_BOTH_LEGS F-01 - the first cause of a failed leg when the failed-record save raises

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC66_BOTH_LEGS F-01 |
| **Source spec** | AC66_BOTH_LEGS |
| **Source finding** | AC66_BOTH_LEGS I-04 |
| **Source documents** | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` (Follow-ups row F-01), `.claude/sdd/archive/AC66_BOTH_LEGS/BUILD_REPORT_AC66_BOTH_LEGS.md` (Issues row I-04) |
| **Created** | 2026-11-10 |
| **Status** | Dropped |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC66_BOTH_LEGS F-01: "AC66_BOTH_LEGS I-04 (Low, open): in `run_leg`, a `BaseException` raised
while saving the `failed` record replaces the original exception, so the first cause is lost from
the report. Raise the save error `from` the original, or chain it, with a test of `run_leg`".

The code is `tests/support/ac66_rules.py`, `run_leg`, the `except BaseException:` block at the end:
it saves the `failed` record inside an inner `try`, catches `Exception` from the save (reported by
class name) and then re-raises the original with a bare `raise`. A `BaseException` from the save
(an interrupt, or pytest's `Failed`) leaves the inner `try` instead.

Checked on 2026-11-10 on main f095237 with a fake store whose `save` raises a `BaseException`
subclass `Stop`, and a `run_tasks` that raises `AssertionError("run ended FAILED")`:

```text
raised: Stop save interrupted
__context__: AssertionError run ended FAILED
__cause__: None
suppress_context: False

AssertionError: run ended FAILED

During handling of the above exception, another exception occurred:

  File ".../tests/support/ac66_rules.py", line 665, in run_leg
    store.save(name, failed)
Stop: save interrupted
```

The first cause is not lost: Python's implicit chaining keeps it as `__context__`, and pytest and
the standard traceback print both, the original first. The save's `BaseException` is the one that
propagates, which is right for an interrupt. An explicit `raise ... from original` would only change
the joining sentence to "The above exception was the direct cause of the following exception".

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | No code change: this file and two archived rows only |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | Annotations of an archived BUILD_REPORT row and a SHIPPED row only (allowed) |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None |
| E6 | No change under `tests/integration/` | Yes | None |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: no work to do; dropped (Closure). Every row is `Yes`, so a CHANGE document would have
been allowed, but there is nothing for it to change.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A leg whose job run fails and whose failed-record save then raises a `BaseException` | The exception reaches pytest | The original failure is still visible in the report. Met by the shipped code (evidence in Problem), so no change is made |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from AC66_BOTH_LEGS I-04 |
| **Priority** | Now |
| **Target** | Dropped on 2026-11-10 |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | Pending: the PR of `change/drop-ac66-both-legs-f01`, recorded by a closure PR as in `F_AC66_BOTH_LEGS_06.md` |
| **Merge commit** | Pending: read with `gh pr view <N> --json state,mergedAt,mergeCommit` after the merge |
| **Work done in** | Dropped: the first cause is kept as `__context__` by implicit exception chaining and printed by pytest (evidence in Problem); the premise of AC66_BOTH_LEGS I-04 does not hold. The user chose to drop it on 2026-11-10 rather than pin the behaviour with a test or add an explicit `from` |
| **Source rows updated** | `.claude/sdd/archive/AC66_BOTH_LEGS/BUILD_REPORT_AC66_BOTH_LEGS.md`, Issues row I-04: the Follow-up cell starts with "Dropped 2026-11-10"; `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md`, Follow-ups row F-01: the target cell reads "Dropped 2026-11-10" |
| **check_specs.py after the update** | `69 document(s) checked, 0 error(s), 11 warning(s)`; the rule (b) warning for AC66_BOTH_LEGS I-04 is gone (12 before) |

---

## Self-Review

- **Weak points:** No test pins the chaining, so a later `raise ... from None` in that block would
  hide the first cause without failing any test. AC66_ZERO_NEW_RUNS already tests that a
  `BaseException` from the run reader propagates (AC-169), not this save path.
- **Risks:** None for the live runs: the save is `Evidence.save`, whose I/O and serialization errors are
  `Exception` subclasses, caught and reported by class name; only an interrupt reaches this path.
- **Next step:** None; AC66_BOTH_LEGS F-02 (atomic `Evidence.save`) stays a separate follow-up.
