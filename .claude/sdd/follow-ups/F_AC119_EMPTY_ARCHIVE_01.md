# FOLLOW-UP: AC119_EMPTY_ARCHIVE F-01 - port the AC-119 fixture tests to the template

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC119_EMPTY_ARCHIVE F-01 |
| **Source spec** | AC119_EMPTY_ARCHIVE |
| **Source finding** | AC119_EMPTY_ARCHIVE I-01 |
| **Source documents** | `.claude/sdd/archive/AC119_EMPTY_ARCHIVE/CHANGE_AC119_EMPTY_ARCHIVE.md` (Issues row I-01; a CHANGE folder has no SHIPPED document) |
| **Created** | 2026-11-11 |
| **Status** | Closed |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC119_EMPTY_ARCHIVE I-01: "The test file is not yet ported to the template repository, so a new
project still gets the version without the empty-archive path". Its Follow-up cell reads "Open:
port the AC119_FIXTURE and AC119_EMPTY_ARCHIVE tests to the template", so `check_specs.py`
warns on it (rule b).

Measured on 2026-11-11: the template repository (`~/Documents/sdd-data-template`, local only,
branch `master` at d520e24) has `tests/test_check_specs.py` byte-identical to this repository's
28ad101 (TEMPLATE_PORT). Since then two commits here changed it, b1f73df (AC119_FIXTURE) and
a3e2f5b (AC119_EMPTY_ARCHIVE): 101 lines. No other generic tooling file changed since the port
(`git log 7b50dd3..HEAD` on `scripts/`, the templates, the SDD README, the agents,
`docs/conventions/`, `CLAUDE.md`, the hook and `pyproject.toml` files lists only those two
commits and 4bc12b0, which touches this project's runbook and reset script).

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

The criteria are measured on this repository, as in TEMPLATE_PORT: the template repository has
no SDD process of its own, and its change is a copy of a file already specified, built and gated
here.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Predicted here: this file, the CHANGE document and one archived Issues row; in the template: `tests/test_check_specs.py` only |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | Only the Issues row of AC119_EMPTY_ARCHIVE I-01 in its archived CHANGE document, read as a BUILD_REPORT by rules (b) and (c) |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | Nothing in this repository; the template's `check_specs.py` and SDD templates are already byte-identical to this repository's |
| E6 | No change under `tests/integration/` | Yes | None |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None, here or in the template |

Decision: CHANGE track (every row `Yes`). Document: `CHANGE_TEMPLATE_PORT_AC119.md`, branch
`change/template-port-ac119`; template work on the local branch `sync/ac119-tests` for review,
as in TEMPLATE_PORT.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | The template's review branch, and a project generated from it | Their tests and checks run | The template's `tests/test_check_specs.py` is byte-identical to this repository's; the AC-176, AC-177 and AC-179 tests pass on the template's empty archive and in the generated project; every check passes |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from AC119_EMPTY_ARCHIVE I-01 |
| **Priority** | Now |
| **Target** | 2026-11-11 (template branch); the template's `master` moves on the user's review |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #72 (branch `change/template-port-ac119`), recorded by a closure PR as in `F_AC119_FIXTURE_01.md`; branch removed (remote by GitHub on merge, local with `git branch -d`) |
| **Merge commit** | 29cc2d0, read with `gh pr view 72 --json state,mergedAt,mergeCommit`: `MERGED`, 2026-11-11T17:52:25Z |
| **Work done in** | `CHANGE_TEMPLATE_PORT_AC119.md` (archived in `archive/TEMPLATE_PORT_AC119/`): template commit 8366859 on the local branch `sync/ac119-tests` (parent d520e24, `master` unchanged until the user's review) copies `tests/test_check_specs.py` byte for byte. DC-01 is met: on the template branch `131 passed, 1 skipped` and the three fixture tests pass on its empty archive; a project generated from it gives `124 passed, 1 skipped` |
| **Source rows updated** | `.claude/sdd/archive/AC119_EMPTY_ARCHIVE/CHANGE_AC119_EMPTY_ARCHIVE.md:131`, Issues row I-01: the Follow-up cell reads "Closed 2026-11-11 by TEMPLATE_PORT_AC119" and names 8366859, so it no longer starts with `Open` |
| **check_specs.py after the update** | `71 document(s) checked, 0 error(s), 10 warning(s)` on the change branch: the rule (b) warning for AC119_EMPTY_ARCHIVE I-01 is gone |

---

## Self-Review

- **Weak points:** The template has no remote and no CI, so the proof is the commands run here
  on its branch and on a generated project.
- **Risks:** Nothing keeps the template in step after this port (TEMPLATE_PORT I-02).
- **Next step:** The user reviews the template branch `sync/ac119-tests`; on the OK, `master` is fast-forwarded to 8366859.
