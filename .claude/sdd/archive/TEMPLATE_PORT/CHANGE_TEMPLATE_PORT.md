# CHANGE: Port the SDD tooling to the template repository

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | TEMPLATE_PORT |
| **Date** | 2026-11-09 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/template-port` |
| **Status** | Complete |
| **Source** | SMALL_CHANGE_TRACK F-02 and SPEC_ARCHIVE_GATES F-01; follow-up file `.claude/sdd/follow-ups/F_SMALL_CHANGE_TRACK_02.md`. User decisions of 2026-11-09: full resync of the generic tooling, `git.md` in the template without the R1 exception, work committed on a local branch of the template repository for review |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

The template repository (`~/Documents/sdd-data-template`, local only, branch `master`, last commit
67e0f12 of 2026-10-13) still has the SDD tooling this project started from on 2026-10-15
(3216532). Measured on 2026-11-09 with `diff` against this repository's `main` (51ee69c):

- `scripts/check_specs.py` differs by 413 lines and `tests/test_check_specs.py` by 726: the
  template has neither the archive checks (SPEC_ARCHIVE_GATES), the CHANGE phase
  (SMALL_CHANGE_TRACK) nor the `Fail` result-cell fix (eb935de).
- `CHANGE_TEMPLATE.md` and `FOLLOW_UP_TEMPLATE.md` are missing; `SHIPPED_TEMPLATE.md` has no
  `Pull Requests and Branches` and no `Self-Review`; there is no `follow-ups/` folder and no
  `citation_allowlist.json`.
- `docs/conventions/git.md` has no rules for agents and still names `feat/` branches;
  `CLAUDE.md` has neither the CHANGE track line nor rule 8; `.claude/sdd/README.md`,
  `docs/conventions/naming.md` and `ship-agent.md` are behind.
- `.pre-commit-config.yaml` pins ruff v0.6.9 with the old `ruff` hook id and runs the
  `check-specs` hook with `language: system` (71dc451 moved it to its own environment);
  `pyproject.toml` has `ruff>=0.6` (46462fd pins 0.17.0).

A new project created from the template today would start without any of this.

Moreover, one test assumes this repository's data: `test_ac119_folder_name_collision_fails_without_merging`
takes the first folder of the real `archive/`, which a new project does not have (`IndexError` in a
trial copy on 2026-11-09).

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

The criteria are measured on this repository, which the PR changes. The template repository has
no SDD process of its own (empty `archive/` and `features/`, plain commits); its changes are
copies of code and rules already specified, built and gated here, recorded in Evidence by commit
SHA.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD` on 251e5f4: `M` `.claude/sdd/archive/SMALL_CHANGE_TRACK/SHIPPED_2026-11-06.md`, `M` `.claude/sdd/archive/SPEC_ARCHIVE_GATES/SHIPPED_2026-11-05.md`, `A` `.claude/sdd/features/CHANGE_TEMPLATE_PORT.md`, `A` `.claude/sdd/follow-ups/F_SMALL_CHANGE_TRACK_02.md`, `M` `tests/test_check_specs.py`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | Same output: no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: the two archived files are SHIPPED documents, changed only in the Follow-ups rows SMALL_CHANGE_TRACK F-02 (line 108) and SPEC_ARCHIVE_GATES F-01 (line 98); no DEFINE or DESIGN |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | `git diff --stat origin/main...HEAD -- scripts/check_specs.py .claude/sdd/templates` is empty; only `tests/test_check_specs.py` changes (a test helper and one test) |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml` is empty |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening (adding rules, raising requirements, fixing wording without changing the effect) is `Yes`. Relaxing (removing a rule, narrowing what needs confirmation, widening what is allowed without it, weakening a check) is `Relaxing` and needs the Rule Changes section below. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md` is empty. In the template the port only adds rules (hardening): the rules for agents of 4699d1e and R2, without the R1 exception, so `--force-with-lease` stays on the confirmation list |

---

## Scope

**In scope (template repository, local branch `sync/project-tooling`):**
- Copied unchanged from this repository: `scripts/check_specs.py`, `tests/test_check_specs.py`,
  `.claude/sdd/templates/SHIPPED_TEMPLATE.md`, `CHANGE_TEMPLATE.md`, `FOLLOW_UP_TEMPLATE.md`,
  `.claude/agents/workflow/ship-agent.md`, `docs/conventions/naming.md`.
- New: `.claude/sdd/follow-ups/.gitkeep`; `.claude/sdd/citation_allowlist.json` with no entries.
- Adapted: `.claude/sdd/README.md` (no reference to this project's history),
  `docs/conventions/git.md` (rules for agents without R1; R2 only where the repository has
  `delete_branch_on_merge`; no repository name, ruleset id or PR number of this project),
  `CLAUDE.md` (CHANGE track line and rule 8 without the exception; placeholders kept),
  `.pre-commit-config.yaml` (ruff v0.17.0, `ruff-check`, `check-specs` with `language: python`;
  not the exclude of this project's pinned files), `pyproject.toml` (`ruff==0.17.0` in `dev`),
  and the template's own `README.md` (replaced by `.template/README.project.md` at init). The
  template's `CHANGELOG.md` stays empty: `init_project.py` keeps it as the new project's
  changelog.

**In scope (this repository):**
- `tests/test_check_specs.py`: `simulate_archive` takes the source root as a parameter, and the
  collision test builds its own archive folder, so the test passes on an empty archive.
- The follow-up file, and the source rows SMALL_CHANGE_TRACK F-02 and SPEC_ARCHIVE_GATES F-01.

**Out of scope:**
- This project's specs, ADRs, spikes, contracts, CI Java step, extra dependencies and
  `CHANGELOG.md` entries.
- A remote for the template repository and publishing it on GitHub.
- R1 in the template (a project adds it through its own E8 `Relaxing` change once it has a
  ruleset).
- SMALL_CHANGE_TRACK F-01 (history checks).

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-146 | The template branch `sync/project-tooling` | `cmp` runs on each copied file against this repository's final head | `scripts/check_specs.py`, `tests/test_check_specs.py`, the three templates, `ship-agent.md` and `naming.md` are byte-identical |
| AC-147 | The same branch | The SDD folders are listed | `.claude/sdd/follow-ups/.gitkeep` exists and `citation_allowlist.json` is `{"version": 1, "entries": []}` |
| AC-148 | The template's `docs/conventions/git.md` | It is read | It has the rules for agents; `git push --force-with-lease` is on the confirmation list with no exception; R2 applies only when `delete_branch_on_merge` is `true`, otherwise `git push --delete` is used with confirmation; `grep -n "26640008\|smart-meter\|#3[0-9]\|feat/"` finds nothing |
| AC-149 | The template's `CLAUDE.md`, `.claude/sdd/README.md`, `.pre-commit-config.yaml` and `pyproject.toml` | They are read | `CLAUDE.md` keeps its `{{...}}` placeholders and has the CHANGE track line and rule 8 without an exception; the README describes the archive checks, the CHANGE track and follow-ups with no reference to this project's specs other than as examples; the hooks pin ruff v0.17.0 with `ruff-check` and run `check-specs` with `language: python`; `dev` pins `ruff==0.17.0` |
| AC-150 | The template branch | `ruff check .`, `ruff format --check .`, `pytest`, `python scripts/check_specs.py` and `pre-commit run --all-files` run | All pass; `check_specs.py` reports 0 errors and 0 warnings |
| AC-151 | A copy of the template branch | `python scripts/init_project.py` runs with all three modules, then `pytest` and `python scripts/check_specs.py` | The project is generated, the tests pass and the checker reports 0 errors |
| AC-152 | This repository on the final head | `pytest tests/test_check_specs.py` runs, and the collision test runs against an empty archive | All tests pass; the collision test no longer reads the real `archive/` |
| AC-153 | This repository on the final head | `python scripts/check_specs.py` and `pre-commit run --all-files` run, and the follow-up file and the two source rows are read | 0 errors, warnings only as on `main` plus this document's own `Open` findings; the follow-up file is `Closed` with the template commit; the two source rows name the template commit |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-146 | Command | `cmp` per file, template branch head against this repository's final head | Exit 0 for each file |
| AC-147 | Command | `ls -a .claude/sdd/follow-ups` and `cat .claude/sdd/citation_allowlist.json` in the template | Output pasted in Evidence |
| AC-148 | Command | `grep -n` on the template's `git.md` for the confirmation list, R2 and the forbidden strings | Lines pasted; forbidden-string grep exits 1 |
| AC-149 | Command | `grep -n` on the four template files | Lines pasted in Evidence |
| AC-150 | Command | The five commands in the template branch | Output pasted in Evidence |
| AC-151 | Command | `init_project.py` in a scratch clone, then `pytest` and `check_specs.py` | Output pasted in Evidence |
| AC-152 | Unit | `tests/test_check_specs.py::test_ac119_folder_name_collision_fails_without_merging` | The test builds `archive/FEAT/` under `tmp_path` and passes; the template run of AC-150 is the empty-archive case |
| AC-153 | Command | `check_specs.py`, `pre-commit run --all-files`, `grep` on the follow-up file and the SHIPPED rows | Output pasted in Evidence and in the PR description |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `tests/test_check_specs.py` | Modify | `simulate_archive(..., source=ROOT)`; collision test with its own archive (AC-152) |
| 2 | Template: copied and new files of Scope | Create / Modify | AC-146, AC-147 |
| 3 | Template: `docs/conventions/git.md`, `CLAUDE.md`, `.claude/sdd/README.md`, `.pre-commit-config.yaml`, `pyproject.toml`, `README.md` | Modify | AC-148, AC-149 |
| 4 | `.claude/sdd/follow-ups/F_SMALL_CHANGE_TRACK_02.md` | Create | Follow-up record, closed with the template commit (AC-153) |
| 5 | `.claude/sdd/archive/SMALL_CHANGE_TRACK/SHIPPED_2026-11-06.md`, `.claude/sdd/archive/SPEC_ARCHIVE_GATES/SHIPPED_2026-11-05.md` | Modify | Follow-ups rows name the template commit (AC-153) |

---

## Evidence

Evidence commit: 251e5f4

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/TEMPLATE_PORT/`). `python scripts/check_specs.py` runs again
on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-146 | Pass | Template d520e24: `cmp -s` exits 0 against this repository (28ad101 for the test file, `main` for the rest) for `scripts/check_specs.py`, `tests/test_check_specs.py`, `SHIPPED_TEMPLATE.md`, `CHANGE_TEMPLATE.md`, `FOLLOW_UP_TEMPLATE.md`, `ship-agent.md`, `naming.md` |
| AC-147 | Pass | `ls -a .claude/sdd/follow-ups`: `.gitkeep`; `citation_allowlist.json`: `{"version": 1, "entries": []}` |
| AC-148 | Pass | `git.md:44-46` confirmation list includes `git push --force-with-lease` with no exception; `git.md:50-54`: when `gh api repos/<owner>/<repo> --jq .delete_branch_on_merge` returns `true`, no `git push --delete` and `git ls-remote --heads origin <branch>`; otherwise `git push origin --delete <branch>` with confirmation; merge without `--delete-branch`, local delete with `git branch -d`. `grep -n "26640008\|smart-meter\|#3[0-9]\|feat/"` exits 1. A closing bullet says a project relaxes a confirmation only through an E8 `Relaxing` CHANGE |
| AC-149 | Pass | `CLAUDE.md`: 3 lines with `{{`, CHANGE track line (22-23), rule 8 (39), `grep exception` exits 1. README: `## CHANGE track` (50), `## Follow-ups` (88), "Shipped features in `archive/` are checked as well:" (34), the allowlist "empty in a new project"; spec names only as citation examples. Hooks: `rev: v0.17.0`, `ruff-check`, `check-specs` `language: python`; `pyproject.toml:12` `"ruff==0.17.0"` |
| AC-150 | Pass | Template d520e24, ruff 0.17.0: `ruff check .` "All checks passed!"; `ruff format --check .` "34 files already formatted"; `pytest` 128 passed, 1 skipped; `check_specs.py` "0 document(s) checked, 0 error(s), 0 warning(s)"; `pre-commit run --all-files` all 9 hooks pass, after `check-yaml` got `exclude: ^modules/` (it failed on `master` too: `modules/databricks/files/databricks.yml` holds the project-slug placeholder until init) |
| AC-151 | Pass | Scratch copy: `init_project.py --name "Port Check" --modules databricks,kafka,mlflow --author Test` printed "Initialized 'Port Check' (package: port_check, ...)", placeholders replaced in 7 files; then `pytest` 121 passed, 1 skipped; `check_specs.py` 0 errors, 0 warnings; `ruff check .` exit 0; `CHANGE_TEMPLATE.md`, `FOLLOW_UP_TEMPLATE.md`, `follow-ups/` and the allowlist present; `grep` for `26640008`, the account name and this repository's name finds nothing |
| AC-152 | Pass | `pytest tests/test_check_specs.py` 114 passed, 1 skipped; the collision test builds `archive/FEAT/` under `tmp_path` (`simulate_archive(..., source=source)`) and passes alone (1 passed); in the template (empty archive) it passes within AC-150 |
| AC-153 | Pass | On the final tree: `check_specs.py` `60 document(s) checked, 0 error(s), 8 warning(s)`, exit 0; the warnings are the six of `main` and this document's own TEMPLATE_PORT I-01 and TEMPLATE_PORT I-02 (rule b). `pre-commit run --all-files`: all hooks passed. `F_SMALL_CHANGE_TRACK_02.md` status `Closed` with d520e24; the source rows at `SHIPPED_2026-11-06.md:108` and `SHIPPED_2026-11-05.md:98` name d520e24 |

In a `Complete` document `check_specs.py` reports `Fail` and `Not run` as errors. A deliberate
deferral is written `Deferred: <reason>`: the check accepts it and lists it as a warning, so it
stays visible without blocking the change. `Deferred` without a reason is an error.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The template's `tests/test_check_specs.py` keeps this project's AC numbers in test names and comments (AC-107 to AC-131); they mean nothing in a new project. Kept so that the file stays byte-identical and the next resync is a plain copy | Low | Open |
| I-02 | Nothing keeps the template in step: the next process change here drifts again until someone ports it | Low | Open |
| I-03 | The template's `check-yaml` exclude of `modules/` was a defect on the template's `master` (placeholders in module YAML), found by AC-150 and fixed in d520e24; generated projects do not have `modules/` | Low | Closed in d520e24 |

---

## Self-Review

- **Weak points:** The template has no SDD record of its own; its changes are proved only by
  commands run here. The eligibility is measured on this repository, not on the template.
- **Risks:** A file copied byte for byte may still carry a project reference that `grep` does not
  catch; AC-151 (generate a project and run its checks) is the backstop.
- **What I would do differently:** Port each process change to the template in the PR that ships
  it, instead of collecting a month of drift.
- **Next improvement:** Give the template a remote and a CI run, so AC-150 runs there on every
  change.
