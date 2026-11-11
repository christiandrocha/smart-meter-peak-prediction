# CHANGE: AC-119 fixture on an empty archive

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC119_EMPTY_ARCHIVE |
| **Date** | 2026-11-11 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/ac119-empty-archive` |
| **Status** | Complete |
| **Source** | Follow-up AC119_FIXTURE F-01 (`.claude/sdd/follow-ups/F_AC119_FIXTURE_01.md`, triage: every criterion `Yes`), from AC119_FIXTURE I-01 |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

The AC119_FIXTURE tests run the AC-119 archive simulation on a fixture feature over a copy of
the real archive. AC119_FIXTURE AC-176 cites the first archived folder, and
`first_archived_spec` in `tests/test_check_specs.py` asserts that one exists. In a project with
an empty `archive/`, which is a new project from the template, AC-176 fails instead of running
(AC119_FIXTURE I-01). Measured on 2026-11-11 on a copy of `main` (181ae67) with `archive/`
emptied and an empty allowlist: `1 failed, 1 passed` for `-k "ac176 or ac177"`, the failure
being the assertion in `first_archived_spec`. So the test file cannot be ported to the template
as it is.

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-only origin/main...HEAD` on a029454 lists only `.claude/sdd/archive/AC119_FIXTURE/CHANGE_AC119_FIXTURE.md`, `.claude/sdd/features/CHANGE_AC119_EMPTY_ARCHIVE.md`, `.claude/sdd/follow-ups/F_AC119_FIXTURE_01.md`, `tests/test_check_specs.py`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD`: `M` for the archived AC119_FIXTURE CHANGE document and the test file, `A` for this document and the follow-up file; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: under `archive/` only `AC119_FIXTURE/CHANGE_AC119_FIXTURE.md` changes, one line (Issues row of AC119_FIXTURE I-01); rules (b) and (c) read an archived CHANGE document as a BUILD_REPORT (`.claude/sdd/README.md`, CHANGE track); no archived DEFINE or DESIGN |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor any file under `.claude/sdd/templates/`; `tests/test_check_specs.py` is a test of the gates, not a gate |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`: empty (0 lines) |

---

## Scope

**In scope:**
- A helper in `tests/test_check_specs.py` that returns the source archive and the spec to cite:
  the source's first archived folder when there is one; otherwise a copy of the source's
  allowlist plus one generated valid folder, `CITED_AC119`, in `tmp_path`.
- AC-176 and AC-177 use that helper and keep their names, so on this repository they still
  run over the real archive and cite its first folder.
- One new test that forces the empty-archive path (a source built in `tmp_path` with an empty
  `archive/` and an empty allowlist) and runs both the positive and the unprefixed case on it.
- Closing AC119_FIXTURE F-01: the follow-up file and the Issues row of AC119_FIXTURE I-01.

**Out of scope:**
- Porting the test file to the template repository: a separate step, which this change makes
  possible.
- The repository-state test `test_ac119_final_status_feature_docs_pass_the_archive_rules`:
  unchanged, including its skip.
- Any change to `scripts/check_specs.py`, its rules or the templates.
- A release: test only; it ships with the next release.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-179 | A source built in `tmp_path` with an empty `archive/` and an empty allowlist, and the AC119_FIXTURE fixture feature whose DESIGN cites the cited spec's finding 90 with the spec name directly in front | The helper picks the cited spec and the AC-119 simulation runs over that source | The cited spec is `CITED_AC119`, the simulated archive holds exactly `CITED_AC119` and `FIXTURE_AC119`, and `check_specs.run` gives no error |
| AC-180 | The same empty source and the fixture with finding 90 cited without the spec name | The same simulation runs | Exactly one error, a rule (c) error naming `archive/FIXTURE_AC119/DESIGN_FIXTURE_AC119.md` and finding 90; no failure for lack of a folder to cite |
| AC-181 | The changed test file | `pytest tests/test_check_specs.py`, the full `pytest`, and `-k "ac176 or ac177"` on a copy of the repository with an empty archive and an empty allowlist | AC-176, AC-177, AC-179 and AC-180 pass on this repository; on the copy AC-176 and AC-177 pass (before: AC-176 failed); AC-176 still cites this repository's first archived folder; the repository-state AC-119 test is unchanged and still skips; `ruff` and `check_specs.py` pass |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-179 | Unit | `tests/test_check_specs.py::test_ac179_fixture_runs_on_an_empty_archive` | Builds an empty source (`archive/` with no folder, `write_allowlist` with no entry), asserts that the helper returns a generated source and `CITED_AC119`, runs the positive case through the same assertion helper as AC-176, and asserts the two folder names of the simulated archive |
| AC-180 | Unit | `tests/test_check_specs.py::test_ac179_fixture_runs_on_an_empty_archive` (same test, unprefixed case in a second `tmp_path` folder) | Runs the unprefixed case through the same assertion helper as AC-177: one error, with `DESIGN_FIXTURE_AC119.md`, the "cited 1x without its spec prefix" text for finding 90 and `(rule c)` at the end |
| AC-181 | Command | `pytest tests/test_check_specs.py -rs`; `pytest`; the empty-archive copy (`git archive` of the evidence commit into the scratch folder, `archive/` emptied, allowlist `{"version": 1, "entries": []}`, `pytest -k "ac176 or ac177"`); `git diff origin/main...HEAD -- tests/test_check_specs.py`; `ruff check . && ruff format --check .`; `python scripts/check_specs.py` | The summaries show the four tests passed and the repository-state test skipped; on the copy `2 passed`; the diff touches no line of the repository-state test |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `tests/test_check_specs.py` | Modify | The source-and-cited-spec helper, shared assertion helpers for the positive and unprefixed cases, AC-176 and AC-177 on the helper, and the AC-179/AC-180 test |
| 2 | `.claude/sdd/follow-ups/F_AC119_FIXTURE_01.md` | Create, then close | The follow-up task file (Closure filled in the closure PR) |
| 3 | `.claude/sdd/archive/AC119_FIXTURE/CHANGE_AC119_FIXTURE.md` | Modify (one row) | Issues row of AC119_FIXTURE I-01: Follow-up cell points to AC119_EMPTY_ARCHIVE |
| 4 | `.claude/sdd/features/CHANGE_AC119_EMPTY_ARCHIVE.md` | Create, then move to `archive/AC119_EMPTY_ARCHIVE/` | This document |

---

## Evidence

Evidence commit: a029454

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/AC119_EMPTY_ARCHIVE/`). `python scripts/check_specs.py` runs
again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-179 | Pass | `tests/test_check_specs.py::test_ac179_fixture_runs_on_an_empty_archive` passed on a029454: `fixture_source` returned the generated source and `CITED_AC119`, the positive case gave no error, and the simulated archive held exactly `CITED_AC119` and `FIXTURE_AC119` |
| AC-180 | Pass | Same test, unprefixed case: one error, the rule (c) message for finding 90 in `DESIGN_FIXTURE_AC119.md`, the same text as AC119_FIXTURE AC-177 |
| AC-181 | Pass | `pytest -q -rs tests/test_check_specs.py`: `117 passed, 1 skipped` (`SKIPPED [1] tests/test_check_specs.py:647: no document of features/ or reports/ is in its phase's final status`); full `pytest -q -rs`: `792 passed, 1 skipped, 92 deselected, 1 xfailed` (791 before plus the new test); AC-176 asserts that on this repository it cites the first archived folder of `ROOT`; empty-archive copy (`git archive a029454`, `archive/` emptied, allowlist with no entry): `-k "ac176 or ac177 or ac179"` gives `3 passed`, where `main` (181ae67) gave `1 failed, 1 passed` for `-k "ac176 or ac177"`; `git diff -U0 origin/main...HEAD -- tests/test_check_specs.py`: every hunk starts at line 694 or later, after the repository-state test (lines 643 to 650), so it is unchanged; `ruff check .` and `ruff format --check .` clean; `python scripts/check_specs.py`: `70 document(s) checked, 0 error(s), 10 warning(s)` |

In a `Complete` document `check_specs.py` reports `Fail` and `Not run` as errors. A deliberate
deferral is written `Deferred: <reason>`: the check accepts it and lists it as a warning, so it
stays visible without blocking the change. `Deferred` without a reason is an error.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The test file is not yet ported to the template repository, so a new project still gets the version without the empty-archive path; this change was proven on a generated source and on an emptied copy of this repository, not on the template itself | Low | Open: port the AC119_FIXTURE and AC119_EMPTY_ARCHIVE tests to the template |

---

## Self-Review

- **Weak points:** The empty-archive path is proven on a source generated in `tmp_path`, not on
  the template repository; the port is a separate step. On this repository the fallback branch of
  the helper runs only in the AC-179/AC-180 test.
- **Risks:** The generated cited folder must itself pass the archive rules; it reuses
  `valid_folder`, which other rule tests already prove valid.
- **What I would do differently:** Run `ruff` before the first test run: a combined assert
  (PT018) failed the lint once. Write the empty-archive copy as a small script from the start,
  since AC-181 runs it twice (before and at the evidence commit).
- **Next improvement:** After the merge, record the PR number and merge commit in
  `F_AC119_FIXTURE_01.md` with a closure PR; then port the tests to the template (I-01).
