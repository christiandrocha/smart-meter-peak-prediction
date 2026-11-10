# CHANGE: AC-119 archive simulation on a fixture feature

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC119_FIXTURE |
| **Date** | 2026-11-10 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/ac119-fixture` |
| **Status** | Complete |
| **Source** | Follow-up AC66_BOTH_LEGS F-06 (`.claude/sdd/follow-ups/F_AC66_BOTH_LEGS_06.md`, triage: every criterion `Yes`) |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

SPEC_ARCHIVE_GATES AC-119 simulates the archive rules of `scripts/check_specs.py` on the
documents of `features/` and `reports/` that are in their final status, over a temporary copy of
the real archive. When no such document exists, which is the normal state between features, the
test skips (`pytest.skip`) and the simulation code (`simulate_archive`) is not exercised at all.
After the AC66_ZERO_NEW_RUNS ship on 2026-11-10 the default run reports `789 passed, 1 skipped`
again. The same test had caught, a few hours earlier, an unprefixed cross-spec citation in the
AC66_ZERO_NEW_RUNS DESIGN (rule c), so the gap is real: between features nothing proves that the
simulation still works.

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-only origin/main...HEAD` on e07f9d7 lists only `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md`, `.claude/sdd/features/CHANGE_AC119_FIXTURE.md`, `.claude/sdd/follow-ups/F_AC66_BOTH_LEGS_06.md`, `tests/test_check_specs.py`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD`: `M` for the SHIPPED record and the test file, `A` for this document and the follow-up file; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: under `archive/` only `AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` changes, one line (Follow-ups row AC66_BOTH_LEGS F-06); no archived DEFINE or DESIGN |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor any file under `.claude/sdd/templates/`; `tests/test_check_specs.py` is a test of the gates, not a gate |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`: empty (0 lines) |

---

## Scope

**In scope:**
- Two new tests in `tests/test_check_specs.py` that run the AC-119 simulation on a fixture
  feature (`FIXTURE_AC119`) built in `tmp_path`, over a copy of the real archive, with no skip:
  one positive (a valid DEFINE, DESIGN and BUILD_REPORT in their final status, with a correctly
  prefixed cross-spec citation, give no error) and one negative (the same feature with one
  unprefixed cross-spec citation gives exactly one rule (c) error).
- The cited spec is taken from the copied archive (the first folder name in sorted order), so
  the fixture does not hard-code a feature of this repository.
- Closing AC66_BOTH_LEGS F-06: the follow-up file and the Follow-ups row of the AC66_BOTH_LEGS
  SHIPPED record.

**Out of scope:**
- The repository-state test `test_ac119_final_status_feature_docs_pass_the_archive_rules`: it
  is kept byte-equal, including its skip, because it is the only test that checks the next real
  feature's documents before they are archived.
- A repository with an empty `archive/` (a new project from the template): the fixture needs at
  least one archived folder to cite. The template port is a separate follow-up.
- Any change to `scripts/check_specs.py`, its rules or the templates.
- A release: test only; it ships with the next release.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-176 | The real archive and allowlist copied to `tmp_path`, plus the fixture feature `FIXTURE_AC119` (DEFINE `Ready for Design`, DESIGN `Ready for Build`, BUILD_REPORT `Complete`) whose DESIGN cites an archived spec's finding with that spec's folder name directly in front | `simulate_archive` adds it and `check_specs.run` runs on `tmp_path` | The errors list is empty; the three fixture documents and the generated SHIPPED are in `archive/FIXTURE_AC119/`; the test has no skip path and does not read `features/` or `reports/` |
| AC-177 | The same fixture, with one citation of the same finding ID without the spec name in front | The same simulation runs | Exactly one error, a rule (c) error naming `archive/FIXTURE_AC119/DESIGN_FIXTURE_AC119.md` and that ID; no other error |
| AC-178 | The changed test file | `pytest tests/test_check_specs.py` and the full `pytest` run on a repository with no document in a final status | AC-176 and AC-177 pass; the repository-state AC-119 test is unchanged (`git diff` shows no line of it) and still skips; `ruff` and `check_specs.py` pass |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-176 | Unit | `tests/test_check_specs.py::test_ac176_fixture_feature_passes_the_archive_simulation` | Builds the three fixture documents as `check_specs.Doc` objects from the existing builders (`define_doc`, `design_doc`, `build_doc`), cites the made-up finding number 90 in the DESIGN text, with the first archived folder name directly in front (a finding the fixture itself does not define; its BUILD_REPORT defines only the first one), calls `simulate_archive(tmp_path, docs)`, asserts the added names and `check_specs.run(tmp_path).errors == []` |
| AC-177 | Unit | `tests/test_check_specs.py::test_ac177_unprefixed_citation_in_the_fixture_fails_rule_c` | Same fixture with finding 90 cited without the folder name; asserts one error that contains `DESIGN_FIXTURE_AC119.md` and the "cited 1x without its spec prefix" text for finding 90, and ends with `(rule c)` (exact message under the Evidence table) |
| AC-178 | Command | `pytest tests/test_check_specs.py -rs`; `pytest`; `git diff origin/main...HEAD -- tests/test_check_specs.py`; `ruff check . && ruff format --check .`; `python scripts/check_specs.py` | The summary shows the two new tests passed and the repository-state test skipped; the diff adds lines only after the AC-119 safeguard test |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `tests/test_check_specs.py` | Modify | Add a fixture builder and the AC-176 and AC-177 tests after the AC-119 tests |
| 2 | `.claude/sdd/follow-ups/F_AC66_BOTH_LEGS_06.md` | Create, then close | The follow-up task file (Closure filled in the closure PR) |
| 3 | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` | Modify (one row) | Follow-ups row AC66_BOTH_LEGS F-06: target cell points to AC119_FIXTURE |
| 4 | `.claude/sdd/features/CHANGE_AC119_FIXTURE.md` | Create, then move to `archive/AC119_FIXTURE/` | This document |

---

## Evidence

Evidence commit: e07f9d7

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/AC119_FIXTURE/`). `python scripts/check_specs.py` runs again
on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-176 | Pass | `tests/test_check_specs.py::test_ac176_fixture_feature_passes_the_archive_simulation` passed on e07f9d7 (cited spec: the first archived folder, `AC66_BOTH_LEGS`, as `AC66_BOTH_LEGS I-90`) |
| AC-177 | Pass | `::test_ac177_unprefixed_citation_in_the_fixture_fails_rule_c` passed: one error, the rule (c) message for finding 90 in `DESIGN_FIXTURE_AC119.md` (exact text below) |
| AC-178 | Pass | `pytest -q -rs tests/test_check_specs.py`: `116 passed, 1 skipped` (`SKIPPED [1] tests/test_check_specs.py:647: no document of features/ or reports/ is in its phase's final status`); full `pytest -q -rs`: `791 passed, 1 skipped, 92 deselected, 1 xfailed` (789 before plus the two new tests); `git diff -U0 origin/main...HEAD -- tests/test_check_specs.py` has one hunk, `@@ -670,0 +671,52 @@`, after the AC-119 safeguard test, so the repository-state test is unchanged; `ruff check .` and `ruff format --check .` clean; `python scripts/check_specs.py`: `69 document(s) checked, 0 error(s), 12 warning(s)` |

The AC-177 error, verbatim (fenced, so that rule (c) does not read it as a citation):

```text
.claude/sdd/archive/FIXTURE_AC119/DESIGN_FIXTURE_AC119.md: I-90 cited 1x without its spec prefix and not in .claude/sdd/citation_allowlist.json (rule c)
```

In a `Complete` document `check_specs.py` reports `Fail` and `Not run` as errors. A deliberate
deferral is written `Deferred: <reason>`: the check accepts it and lists it as a warning, so it
stays visible without blocking the change. `Deferred` without a reason is an error.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The fixture needs at least one archived folder to cite; a project with an empty `archive/` would fail AC-176 rather than skip | Low | Accepted for this repository (twelve archived folders); revisit when the test is ported to the template |

---

## Self-Review

- **Weak points:** The fixture proves the simulation and the archive rules over the real archive,
  not that the next real feature's documents pass; the repository-state test keeps that role and
  its skip. The negative case covers rule (c) only, the rule that failed on 2026-11-10.
- **Risks:** Taking the cited spec from the copied archive makes the fixture depend on the
  archive's folder names; a folder renamed later still works, an empty archive does not (I-01).
- **What I would do differently:** Read the exact rule (c) message before writing the assertion: the first AC-177 run failed because the message ends with `(rule c)`, not `rule (c)`. And run `check_specs.py` on this document in its archive place before the final commit: the move surfaced two rule (c) errors in it (the made-up finding written as an ID, and one unprefixed follow-up), which the AC-176 fixture would have caught as well.
- **Next improvement:** After the merge, record the PR number and merge commit in `F_AC66_BOTH_LEGS_06.md` with a closure PR.
