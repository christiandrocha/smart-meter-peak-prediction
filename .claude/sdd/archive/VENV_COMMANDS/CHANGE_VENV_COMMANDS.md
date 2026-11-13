# CHANGE: Project commands name the tools in .venv/bin

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | VENV_COMMANDS |
| **Date** | 2026-11-13 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/venv-commands` |
| **Status** | Complete |
| **Source** | Follow-up RESET_COMMAND_VENV F-01 (`.claude/sdd/follow-ups/F_RESET_COMMAND_VENV_01.md`, from RESET_COMMAND_VENV I-01; triage: every criterion `Yes`) |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

The user's machine has no bare `python`, and agents run commands in a shell that never activates
the virtual environment. Measured on `main` (10c283a), outside the archive: the setup step runs
`python -m venv .venv` (`README.md:167`, `docs/runbooks/meter_ingestion.md:92`), which fails before
`.venv` exists, and 59 lines in 16 files hold a command that starts with a bare `python`,
`pytest`, `ruff`, `pre-commit` or `pip`: `CLAUDE.md` (Commands), `README.md`, both runbooks,
`.claude/sdd/README.md`, five agent and command files, the usage text of three scripts, the
"next" line the reset script prints, and three local-data test docstrings. RESET_COMMAND_VENV fixed
only the reset commands.

User decision (2026-11-13): every copyable project command names `.venv/bin/<tool>` (the form
`docs/runbooks/meter_ingestion.md` already used for `.venv/bin/pytest`); the setup uses
`python3 -m venv .venv`; the files this track cannot touch are recorded as one finding.

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD` on c5b49a1: `M` the five agent and command files under `.claude/agents/` and `.claude/commands/workflow/`, `.claude/sdd/README.md`, `.claude/sdd/archive/RESET_COMMAND_VENV/CHANGE_RESET_COMMAND_VENV.md`, `CLAUDE.md`, `README.md`, `docs/runbooks/meter_ingestion.md`, `docs/runbooks/peak_model.md`, `scripts/prepare_sample.py`, `scripts/profile_data.py`, `scripts/reset_peak_model_outputs.py`, the three `tests/local_data/` files, `tests/test_ac66_legs_docs.py`; `A` `.claude/sdd/features/CHANGE_VENV_COMMANDS.md`, `.claude/sdd/follow-ups/F_RESET_COMMAND_VENV_01.md`, `tests/test_venv_commands.py`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | Same output: `A` only for this document, the follow-up file and the new unit test; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: under `archive/` only the Issues row RESET_COMMAND_VENV I-01 of the archived CHANGE document (line 140), one line; no archived DEFINE or DESIGN |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor any file under `.claude/sdd/templates/` |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md`: empty. `git diff -U0 origin/main...HEAD -- CLAUDE.md`: hunks `@@ -49,4 +49,4 @@` and `@@ -54 +54 @@`, both inside the Commands block (lines 48 to 55); the golden rules (lines 29 to 44) are unchanged, so no agent rule changes |

---

## Scope

**In scope:**
- `.venv/bin/<tool>` for every copyable `python`, `pytest`, `ruff`, `pre-commit` and `pip` command
  in `CLAUDE.md` (Commands block only), `README.md`, `docs/runbooks/meter_ingestion.md`,
  `docs/runbooks/peak_model.md`, `.claude/sdd/README.md`,
  `.claude/agents/databricks/pipeline-builder.md`, `.claude/agents/workflow/build-agent.md`,
  `.claude/commands/workflow/define.md`, `design.md` and `iterate.md`, the usage text and messages of
  `scripts/prepare_sample.py` and `scripts/profile_data.py`, the printed "next" line of
  `scripts/reset_peak_model_outputs.py` and the docstrings of `tests/local_data/`.
- Setup: `python3 -m venv .venv` and `.venv/bin/pip install ...` in `README.md` and
  `docs/runbooks/meter_ingestion.md`; the README says once why the commands name `.venv/bin/`.
- The shipped AC66_ZERO_NEW_RUNS AC-172 test (`tests/test_ac66_legs_docs.py`) finds the leg
  command lines with `line.startswith("pytest ")`; it now reads `.venv/bin/pytest `. Its
  assertions are unchanged.
- A new unit test that scans the files above (AC-207, AC-208).
- Closing RESET_COMMAND_VENV F-01: the follow-up file and the archived Issues row I-01.

**Out of scope (recorded as VENV_COMMANDS I-01):**
- `scripts/check_specs.py` (usage line and one message) and the BUILD_REPORT and CHANGE templates
  (E5), `src/smart_meter_peak_prediction/producer.py` (E1), `tests/integration/conftest.py` (E6).
- `.github/workflows/ci.yml` and `.pre-commit-config.yaml`: CI provides `python` and pre-commit
  runs its hook in its own environment, so both work as they are.
- `CHANGELOG.md`, the archive and `spikes/`: records of what was run.
- `docker/producer/Dockerfile`: `pip` inside the image is correct.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-207 | The in-scope files (`CLAUDE.md`, `README.md`, `.claude/sdd/README.md`, `docs/runbooks/*.md`, `.claude/agents/**/*.md`, `.claude/commands/**/*.md`, `scripts/*.py` except `check_specs.py`, `tests/local_data/*.py`) | A unit test scans every line for `python`, `pytest`, `ruff`, `pre-commit` or `pip` followed by a space at a line start or after a backtick, quote, space, parenthesis or colon | No match; `CLAUDE.md` holds the four commands `.venv/bin/ruff check . && .venv/bin/ruff format --check .`, `.venv/bin/pytest`, `.venv/bin/python scripts/check_specs.py` and `.venv/bin/pre-commit run --all-files` |
| AC-208 | `README.md` and `docs/runbooks/meter_ingestion.md` | The test reads the setup step | Both create the environment with `python3 -m venv .venv` followed by `.venv/bin/pip install -e`; neither holds `python -m venv` |
| AC-209 | The changed files | The full `pytest`, `ruff check . && ruff format --check .`, `.venv/bin/python scripts/check_specs.py` and `git diff -U0 origin/main...HEAD -- tests/test_ac66_legs_docs.py scripts/` | 0 failures and 0 errors; the AC-172 test diff changes only its filter; the script diffs touch only docstrings and message strings |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-207 | Unit | `tests/test_venv_commands.py::test_ac207_copyable_commands_name_the_venv_tools` | Regex scan of the listed files; the found list must be empty; four `in` checks on `CLAUDE.md`. On a copy of `main` it fails |
| AC-208 | Unit | `tests/test_venv_commands.py::test_ac208_setup_creates_the_venv_with_python3` | Substring checks on both setup steps; `python -m venv` absent. On a copy of `main` it fails |
| AC-209 | Command | `pytest -q -rs`; `ruff check . && ruff format --check .`; `.venv/bin/python scripts/check_specs.py`; `git diff -U0 origin/main...HEAD -- tests/test_ac66_legs_docs.py scripts/` | Summaries and hunks pasted in Evidence |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `CLAUDE.md` | Modify | Commands block |
| 2 | `README.md` | Modify | Setup, sample and integration commands; one sentence on `.venv/bin/` |
| 3 | `docs/runbooks/meter_ingestion.md` | Modify | Setup cell and command lines |
| 4 | `docs/runbooks/peak_model.md` | Modify | Integration, pre-commit and pip commands |
| 5 | `.claude/sdd/README.md` | Modify | `check_specs.py` command |
| 6 | `.claude/agents/databricks/pipeline-builder.md`, `.claude/agents/workflow/build-agent.md` | Modify | `ruff` and `check_specs.py` commands |
| 7 | `.claude/commands/workflow/define.md`, `design.md`, `iterate.md` | Modify | `check_specs.py` command |
| 8 | `scripts/prepare_sample.py`, `scripts/profile_data.py` | Modify | Usage text and the install hint |
| 9 | `scripts/reset_peak_model_outputs.py` | Modify | The printed "next" line |
| 10 | `tests/local_data/test_peak_seed42.py`, `test_pipeline_seed42.py`, `test_sample_seed42.py` | Modify | Docstrings |
| 11 | `tests/test_ac66_legs_docs.py` | Modify | Filter of the AC-172 test |
| 12 | `tests/test_venv_commands.py` | Create | AC-207, AC-208 |
| 13 | `.claude/sdd/follow-ups/F_RESET_COMMAND_VENV_01.md` | Create | Follow-up file, closed in this PR |
| 14 | `.claude/sdd/archive/RESET_COMMAND_VENV/CHANGE_RESET_COMMAND_VENV.md` | Modify | Issues row I-01 annotated as closed |
| 15 | `.claude/sdd/features/CHANGE_VENV_COMMANDS.md` | Create | This document; moved to `archive/VENV_COMMANDS/` when `Complete` |

---

## Evidence

Evidence commit: c5b49a1

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/VENV_COMMANDS/`). `python scripts/check_specs.py` runs again on
the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-207 | Pass | `pytest -q tests/test_venv_commands.py`: `2 passed`. The same file on a copy of `main` (10c283a, `git archive`) gives `2 failed`; on `main` the scan finds 59 lines in 16 in-scope files |
| AC-208 | Pass | Same run: `README.md` and `docs/runbooks/meter_ingestion.md` create the environment with `python3 -m venv .venv` and install with `.venv/bin/pip install -e`; no `python -m venv` |
| AC-209 | Pass | Full `pytest -q -rs` on the build tree: `919 passed, 1 skipped, 92 deselected, 1 xfailed` (917 on `main` plus the two new tests; the skip is the repository-state test of `test_check_specs.py`). `ruff check .`: `All checks passed!`; `ruff format --check .`: `134 files already formatted`. `.venv/bin/python scripts/check_specs.py`: `79 document(s) checked, 0 error(s), 9 warning(s)` before the archive move. `git diff -U0 origin/main...HEAD -- tests/test_ac66_legs_docs.py scripts/`: `tests/test_ac66_legs_docs.py` one hunk `@@ -517 +517,2 @@` (the AC-172 filter, split in two lines for the line length); `scripts/prepare_sample.py` `@@ -3 +3,2 @@` and `@@ -9,3 +10,4 @@` (docstring); `scripts/profile_data.py` `@@ -18 +18 @@`, `@@ -21 +21 @@` (docstring) and `@@ -37 +37 @@` (the install hint string); `scripts/reset_peak_model_outputs.py` `@@ -318 +318 @@` (the printed next line) |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | Bare commands this track cannot change: `scripts/check_specs.py` (usage line 37 and the `pip install pyyaml` hint, E5), `.claude/sdd/templates/BUILD_REPORT_TEMPLATE.md` (spec check row) and `CHANGE_TEMPLATE.md` (D-91 paragraph, E5), `src/smart_meter_peak_prediction/producer.py` (usage docstring, E1), `tests/integration/conftest.py` (sample hint, E6) | Low | Open: needs the full cycle (E1, E5, E6), not scheduled |

---

## Self-Review

- **Weak points:** the scan is a regex: a bare command in an unusual form (after a `$ ` prompt,
  or a tool not in the list) is not caught. The scope list in the test is explicit, so a new
  runbook folder needs adding.
- **Risks:** `.venv/bin/` assumes the environment at the repository root, as the README creates
  it. A person with an activated environment types longer commands than needed; they still work.
- **What I would do differently:** fix every copyable command in RESET_COMMAND_VENV instead of
  only the reset command, so the two changes would have been one.
- **Next improvement:** VENV_COMMANDS I-01 in a full cycle, together with any other gate change.
