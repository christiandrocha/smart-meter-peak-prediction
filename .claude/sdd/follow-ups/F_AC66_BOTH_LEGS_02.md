# FOLLOW-UP: AC66_BOTH_LEGS F-02 - an old verdict file after a failing evidence save

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC66_BOTH_LEGS F-02 |
| **Source spec** | AC66_BOTH_LEGS |
| **Source finding** | AC66_BOTH_LEGS I-05 |
| **Source documents** | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` (Follow-ups row F-02), `.claude/sdd/archive/AC66_BOTH_LEGS/BUILD_REPORT_AC66_BOTH_LEGS.md` (Issues row I-05) |
| **Created** | 2026-11-10 |
| **Status** | Dropped |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC66_BOTH_LEGS F-02: "AC66_BOTH_LEGS I-05 (Low, open): `Evidence.save` is not atomic, so an old
verdict file can survive a failing save and the verdict test still fails in that case. Write to a
temporary file in the same folder and `os.replace` it, with a test".

`Evidence.save` (`tests/integration/conftest.py`) serializes the payload and then writes
`<name>.json` with `Path.write_text`. The verdict test
(`tests/integration/test_peak_data.py::test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot`)
saves the verdict record and only then asserts `verdict.passed`. The leg records are removed by
`run_leg` before the job run (AC66_BOTH_LEGS OD-43); the verdict file is not.

Checked on 2026-11-10 on main e2c4f33 with a copy of `Evidence.save` and of the proposed atomic
version (`tempfile.mkstemp` in the same folder, then `os.replace`). Each case starts from an old
verdict file with `"verdict": "pass"` and saves a new `"fail"` verdict that fails as shown:

```text
shipped  serialization          save raised RuntimeError file left: pass
shipped  read-only folder       save raised PermissionError file left: pass
shipped  write error mid-file   save raised OSError    file left: unparseable ('{\n  "saved')
atomic   serialization          save raised RuntimeError file left: pass
atomic   read-only folder       save raised PermissionError file left: pass
atomic   write error mid-file   save raised OSError    file left: pass
```

Three facts follow:

- The proposed fix does not remove the risk it names: with an atomic write the old `pass` survives
  every failing save, as it does today in two of the three cases.
- In the mid-write case the atomic write is worse: today the file is left visibly unparseable;
  with `os.replace` a stale `pass` stays.
- In every case `save` raises before the assertion, so the verdict test fails and pytest reports
  the error. No code reads `ac66_verdict.json`; it is evidence that the operator copies into a
  BUILD_REPORT after a passing verdict.

The fix that would remove a stale verdict in all three cases is to remove the verdict file before
the evaluation, as `run_leg` does for the leg records. It changes the live test module, so it needs
the full cycle, for a file that is read only by a person after a green run.

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
| E6 | No change under `tests/integration/` | Yes | None for the drop. The proposed fix and the alternative would both be `No` (full cycle) |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: no work to do; dropped (Closure).

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | An old verdict file and a failing save of the new verdict | The verdict test runs | The test fails and pytest reports the save error. Met by the shipped code (evidence in Problem), so no change is made |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from AC66_BOTH_LEGS I-05 |
| **Priority** | Now |
| **Target** | Dropped on 2026-11-10 |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #67 (branch `change/drop-ac66-both-legs-f02`), recorded by a closure PR as in `F_AC66_BOTH_LEGS_05.md`; branch removed (remote by GitHub on merge, local with `git branch -d`) |
| **Merge commit** | 01ddf3d, read with `gh pr view 67 --json state,mergedAt,mergeCommit`: `MERGED`, 2026-11-10T20:04:13Z |
| **Work done in** | Dropped: the verdict test fails in every failing-save case, no code reads the verdict file, and the proposed atomic write keeps the stale `pass` in every case and turns the mid-write case into a stale `pass` (evidence in Problem). The user chose to drop it on 2026-11-10 rather than remove the old verdict before the evaluation (full cycle) or apply the atomic write |
| **Source rows updated** | `.claude/sdd/archive/AC66_BOTH_LEGS/BUILD_REPORT_AC66_BOTH_LEGS.md`, Issues row I-05: the Follow-up cell starts with "Dropped 2026-11-10"; `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md`, Follow-ups row F-02: the target cell reads "Dropped 2026-11-10" |
| **check_specs.py after the update** | `69 document(s) checked, 0 error(s), 10 warning(s)`; the rule (b) warning for AC66_BOTH_LEGS I-05 is gone (11 before), so AC66_BOTH_LEGS has no open finding left |

---

## Self-Review

- **Weak points:** A stale `ac66_verdict.json` with `pass` can still be on disk after a red verdict
  run. Only a person who copies the file without looking at the test result would be misled.
- **Risks:** The probe used copies of the save code, not the live fixture; the copy of
  `Evidence.save` is line for line the shipped one.
- **Next step:** None. If the verdict file ever gets an automated reader, remove it before the
  evaluation in that change.
