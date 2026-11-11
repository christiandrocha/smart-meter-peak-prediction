# FOLLOW-UP: AC119_FIXTURE F-01 - the AC-119 fixture runs on an empty archive

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC119_FIXTURE F-01 |
| **Source spec** | AC119_FIXTURE |
| **Source finding** | AC119_FIXTURE I-01 |
| **Source documents** | `.claude/sdd/archive/AC119_FIXTURE/CHANGE_AC119_FIXTURE.md` (Issues row I-01; a CHANGE folder has no SHIPPED document) |
| **Created** | 2026-11-11 |
| **Status** | Closed |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC119_FIXTURE I-01: "The fixture needs at least one archived folder to cite; a project with an
empty `archive/` would fail AC-176 rather than skip". Its Follow-up cell accepted it for this
repository and deferred it to the template port.

`first_archived_spec` in `tests/test_check_specs.py` (lines 694 to 697) takes the cited spec from
the repository's `archive/` and asserts that it is not empty. Measured on 2026-11-11 on a copy of
`main` (181ae67) with `archive/` emptied and an empty allowlist, the state of a new project from
the template:

```text
FAILED tests/test_check_specs.py::test_ac176_fixture_feature_passes_the_archive_simulation
1 failed, 1 passed, 115 deselected in 0.14s
```

AC-176 fails on the assertion; AC-177 passes, because its unprefixed citation needs no cited
folder. The test file cannot be ported to the template as it is.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Predicted: `tests/test_check_specs.py` only (plus the CHANGE document, this file and one archived Issues row) |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | Only the Issues row I-01 of the archived `CHANGE_AC119_FIXTURE.md` is annotated at closure; rules (b) and (c) read an archived CHANGE document as a BUILD_REPORT (`.claude/sdd/README.md`, CHANGE track), and annotating BUILD_REPORT rows is allowed |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | The script and the templates are unchanged; only a test file changes |
| E6 | No change under `tests/integration/` | Yes | None |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: CHANGE track (every row `Yes`). Document: `CHANGE_AC119_EMPTY_ARCHIVE.md`, branch
`change/ac119-empty-archive`.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A source repository whose `archive/` has no folder | The AC-119 fixture simulation runs on it | The positive case gives no error and the unprefixed case gives exactly one rule (c) error, as on this repository's archive; nothing fails for lack of a folder to cite |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from AC119_FIXTURE I-01 |
| **Priority** | Now |
| **Target** | Next release after v0.7.1 (test only) |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #70 (branch `change/ac119-empty-archive`), recorded by a closure PR as in `F_AC66_BOTH_LEGS_06.md`; branch removed (remote by GitHub on merge, local with `git branch -d`) |
| **Merge commit** | cd4b5a9, read with `gh pr view 70 --json state,mergedAt,mergeCommit`: `MERGED`, 2026-11-11T17:11:25Z |
| **Work done in** | `CHANGE_AC119_EMPTY_ARCHIVE.md` (archived in `archive/AC119_EMPTY_ARCHIVE/`): `fixture_source` in `tests/test_check_specs.py` gives a source with an empty archive one generated folder, `CITED_AC119`, to cite, and `test_ac179_fixture_runs_on_an_empty_archive` forces that path. DC-01 is met: on 2026-11-11 the empty-archive copy of a3e2f5b gives `3 passed` for `-k "ac176 or ac177 or ac179"` (before: AC-176 failed) |
| **Source rows updated** | `.claude/sdd/archive/AC119_FIXTURE/CHANGE_AC119_FIXTURE.md:139`, Issues row I-01: the Follow-up cell reads "Closed 2026-11-11 by AC119_EMPTY_ARCHIVE"; it never started with `Open`, so rule (b) did not warn on it before |
| **check_specs.py after the update** | `70 document(s) checked, 0 error(s), 10 warning(s)` on the change branch, as on `main` plus the CHANGE document |

---

## Self-Review

- **Weak points:** The empty-archive case is proven on a generated source in `tmp_path`, not on
  the template repository itself; the port is a separate step.
- **Risks:** A fallback that this repository never takes would be untested code; the CHANGE
  document therefore adds a test that forces the empty-archive path on every run.
- **Next step:** Port the test file to the template repository, which this change makes possible.
