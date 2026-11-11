# CHANGE: Port the AC-119 fixture tests to the template repository

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | TEMPLATE_PORT_AC119 |
| **Date** | 2026-11-11 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/template-port-ac119` |
| **Status** | Complete |
| **Source** | Follow-up AC119_EMPTY_ARCHIVE F-01 (`.claude/sdd/follow-ups/F_AC119_EMPTY_ARCHIVE_01.md`, triage: every criterion `Yes`), from AC119_EMPTY_ARCHIVE I-01. Template work on a local branch of the template repository for review, as in TEMPLATE_PORT |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

The template repository (`~/Documents/sdd-data-template`, local only, `master` at d520e24) has
the `tests/test_check_specs.py` of TEMPLATE_PORT (this repository's 28ad101). It lacks the
AC119_FIXTURE tests (b1f73df) and the AC119_EMPTY_ARCHIVE empty-archive path (a3e2f5b), 101
lines, so a new project from the template does not run the AC-119 archive simulation between
features (AC119_EMPTY_ARCHIVE I-01). Measured on 2026-11-11: the template's file is
byte-identical to 28ad101; `scripts/check_specs.py` and the SDD templates are byte-identical to
this repository's `main`; no other generic tooling file changed since the port.

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

The criteria are measured on this repository, which the PR changes, as in TEMPLATE_PORT. The
template repository has no SDD process of its own; its change is a byte-for-byte copy of a file
already specified, built and gated here, recorded in Evidence by commit SHA.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD` on 61462e2: `M` `.claude/sdd/archive/AC119_EMPTY_ARCHIVE/CHANGE_AC119_EMPTY_ARCHIVE.md`, `A` `.claude/sdd/features/CHANGE_TEMPLATE_PORT_AC119.md`, `A` `.claude/sdd/follow-ups/F_AC119_EMPTY_ARCHIVE_01.md`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml`. Template: `git diff --name-only master...sync/ac119-tests` lists only `tests/test_check_specs.py` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | Same output: `A` only for this document and the follow-up file; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: under `archive/` only `AC119_EMPTY_ARCHIVE/CHANGE_AC119_EMPTY_ARCHIVE.md` changes, one line (Issues row of AC119_EMPTY_ARCHIVE I-01); rules (b) and (c) read an archived CHANGE document as a BUILD_REPORT; no archived DEFINE or DESIGN |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor a template here; in the template only `tests/test_check_specs.py` changes, and its `scripts/check_specs.py` stays byte-identical to this repository's |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty; template: not in the branch's file list |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`: empty (0 lines); template: neither in the branch's file list |

---

## Scope

**In scope (template repository, local branch `sync/ac119-tests`):**
- `tests/test_check_specs.py`, copied byte for byte from this repository's `main`.

**In scope (this repository):**
- The follow-up file and the Issues row of AC119_EMPTY_ARCHIVE I-01.

**Out of scope:**
- Moving the template's `master`: the user reviews the branch first, as in TEMPLATE_PORT.
- Any other template file, a remote or CI for the template (TEMPLATE_PORT I-02).
- The project's AC numbers in the template's test names (TEMPLATE_PORT I-01): kept, so that the
  file stays byte-identical.
- A release: no test or code of this repository changes.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-182 | The template branch `sync/ac119-tests` | `cmp` runs on `tests/test_check_specs.py` and `scripts/check_specs.py` against this repository's final head | Both are byte-identical; the branch changes only `tests/test_check_specs.py` against `master` |
| AC-183 | The same branch, whose `archive/` is empty | `ruff check .`, `ruff format --check .`, `pytest -rs`, `pytest -k "ac176 or ac177 or ac179"`, `python scripts/check_specs.py` and `pre-commit run --all-files` run | All pass; the three fixture tests pass on the empty archive; the only skip is the repository-state AC-119 test; `check_specs.py` reports 0 errors and 0 warnings |
| AC-184 | A scratch clone of the branch | `python scripts/init_project.py` runs with all three modules, then `pytest`, the three fixture tests, `check_specs.py` and `ruff check .` | The project is generated, every test passes, the fixture tests pass, and the checker reports 0 errors |
| AC-185 | This repository on the final head | `python scripts/check_specs.py` runs, and the follow-up file and the source row are read | 0 errors; the warning for AC119_EMPTY_ARCHIVE I-01 is gone; the follow-up file is `Closed` and the source row names the template commit |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-182 | Command | `cmp` per file; `git diff --name-only master...sync/ac119-tests` in the template | Exit 0 for each file; one file listed |
| AC-183 | Command | The six commands on the template branch | Output pasted in Evidence |
| AC-184 | Command | `git clone -b sync/ac119-tests` into the scratch folder, `init_project.py --name "Port Check" --modules databricks,kafka,mlflow --author Test`, then the four commands | Output pasted in Evidence |
| AC-185 | Command | `check_specs.py`; `grep` on the follow-up file and the source row | Output pasted in Evidence and in the PR description |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | Template: `tests/test_check_specs.py` | Modify (copy) | AC-182 to AC-184 |
| 2 | `.claude/sdd/follow-ups/F_AC119_EMPTY_ARCHIVE_01.md` | Create, then close | The follow-up task file (AC-185) |
| 3 | `.claude/sdd/archive/AC119_EMPTY_ARCHIVE/CHANGE_AC119_EMPTY_ARCHIVE.md` | Modify (one row) | Issues row of AC119_EMPTY_ARCHIVE I-01 names the template commit (AC-185) |
| 4 | `.claude/sdd/features/CHANGE_TEMPLATE_PORT_AC119.md` | Create, then move to `archive/TEMPLATE_PORT_AC119/` | This document |

---

## Evidence

Evidence commit: 61462e2

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/TEMPLATE_PORT_AC119/`). `python scripts/check_specs.py` runs
again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-182 | Pass | Template commit 8366859 on `sync/ac119-tests` (parent d520e24 = `master`): `cmp -s` exits 0 for `tests/test_check_specs.py` and `scripts/check_specs.py` against this repository (`main` df831af, unchanged on this branch); `git diff --name-only master...sync/ac119-tests`: `tests/test_check_specs.py` only (101 lines added) |
| AC-183 | Pass | Template branch, `archive/` holding only `.gitkeep`, ruff 0.17.0: `ruff check .` "All checks passed!"; `ruff format --check .` "34 files already formatted"; `pytest -q -rs` `131 passed, 1 skipped` (128 at TEMPLATE_PORT plus AC-176, AC-177, AC-179), the skip being the repository-state AC-119 test; `-k "ac176 or ac177 or ac179"` `3 passed`; `check_specs.py` "0 document(s) checked, 0 error(s), 0 warning(s)"; `pre-commit run --all-files`: all 9 hooks passed |
| AC-184 | Pass | Scratch clone of `sync/ac119-tests`: `init_project.py --name "Port Check" --modules databricks,kafka,mlflow --author Test` printed "Placeholders replaced in 7 file(s)."; then `pytest -q` `124 passed, 1 skipped` (121 at TEMPLATE_PORT plus three); the three fixture tests `3 passed`; `check_specs.py` "0 document(s) checked, 0 error(s), 0 warning(s)"; `ruff check .` "All checks passed!" |
| AC-185 | Pass | On 61462e2: `check_specs.py` `71 document(s) checked, 0 error(s), 10 warning(s)`; no warning names AC119_EMPTY_ARCHIVE I-01 (`grep -c` gives 0; it was one of the 11 on `main`); `F_AC119_EMPTY_ARCHIVE_01.md` status `Closed` with 8366859; the source row at `CHANGE_AC119_EMPTY_ARCHIVE.md:131` names 8366859; `pre-commit run --all-files`: all hooks passed |

In a `Complete` document `check_specs.py` reports `Fail` and `Not run` as errors. A deliberate
deferral is written `Deferred: <reason>`: the check accepts it and lists it as a warning, so it
stays visible without blocking the change. `Deferred` without a reason is an error.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The template's `master` stays at d520e24 until the user reviews `sync/ac119-tests`; until then a project created from `master` still lacks the ported tests | Low | Accepted: the user's review moves `master` (fast-forward to 8366859), as for TEMPLATE_PORT; tracked in the follow-up file |

---

## Self-Review

- **Weak points:** The template has no remote and no CI; the proof is the commands run here.
- **Risks:** The template drifts again with the next generic change (TEMPLATE_PORT I-02).
- **What I would do differently:** Port a generic test change in the PR that ships it, as
  TEMPLATE_PORT already recommended; this port was one more step only because AC119_FIXTURE and
  AC119_EMPTY_ARCHIVE did not include it.
- **Next improvement:** After the merge, record the PR number and merge commit in
  `F_AC119_EMPTY_ARCHIVE_01.md` with a closure PR; fast-forward the template's `master` on the
  user's OK.
