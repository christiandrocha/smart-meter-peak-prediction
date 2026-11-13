# CHANGE: Project interpreter in the reset command

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | RESET_COMMAND_VENV |
| **Date** | 2026-11-13 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/reset-command-venv` |
| **Status** | Complete |
| **Source** | Follow-up RESET_GUARD F-01 (`.claude/sdd/follow-ups/F_RESET_GUARD_01.md`, triage: every criterion `Yes`) |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

The first live attempt of RESET_GUARD AC-202 (2026-11-12) failed before the script ran, because
the user's machine has no bare `python`; the project interpreter is `.venv/bin/python` (the
virtual environment that `README.md` creates at the repository root). Measured on `main`
(92b268d), six command lines and one constant name the bare `python`:

- `docs/runbooks/peak_model.md`: lines 207 and 208 (section 8) and 256 and 257 (section 9);
- `scripts/reset_peak_model_outputs.py`: the docstring usage block, lines 39 and 40;
- `tests/support/ac66_rules.py`: `RESET_COMMAND` (line 31), printed by the AC-66 legs in their
  "next: the user runs ..." lines.

None of the dry-run commands shows the exit code, which the live gate reads (`0` or `2`). The
runbook of the ingestion job already names the project interpreter (`.venv/bin/pytest`).

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD` on f1b4b21: `M` `.claude/sdd/archive/RESET_GUARD/SHIPPED_2026-11-12.md`, `A` `.claude/sdd/features/CHANGE_RESET_COMMAND_VENV.md`, `A` `.claude/sdd/follow-ups/F_RESET_GUARD_01.md`, `M` `docs/runbooks/peak_model.md`, `M` `scripts/reset_peak_model_outputs.py`, `M` `tests/support/ac66_rules.py`, `M` `tests/test_ac66_legs_docs.py`, `A` `tests/test_reset_command_venv.py`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | Same output: `A` only for this document, the follow-up file and the new unit test; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: under `archive/` only the Follow-ups row RESET_GUARD F-01 of the SHIPPED document (line 142), one line; no archived DEFINE or DESIGN |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor any file under `.claude/sdd/templates/` |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/integration/` (`tests/support/ac66_rules.py` is outside it) |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`: empty (0 lines) |

---

## Scope

**In scope:**
- The four reset command lines of `docs/runbooks/peak_model.md` (sections 8 and 9) and the two of
  the script docstring: `.venv/bin/python` instead of `python`; each dry-run line ends with
  `; echo "exit $?"`. Section 9 says in one sentence why the project interpreter is named.
- `RESET_COMMAND` in `tests/support/ac66_rules.py`: `.venv/bin/python` (the legs print it).
- The shipped AC66_BOTH_LEGS AC-160 test (`tests/test_ac66_legs_docs.py`) picks the docstring's
  `--confirm` line with `ln.strip().startswith("python")`, which no longer matches. Its filter
  becomes "the line runs `scripts/reset_peak_model_outputs.py` with `--confirm`"; its assertions
  are unchanged.
- A new unit test that pins the command text (AC-203 to AC-205).
- Closing RESET_GUARD F-01: the follow-up file and the SHIPPED Follow-ups row.

**Out of scope:**
- The AC-202 text in the archived RESET_GUARD DEFINE and DESIGN, and the AC-202 record in the
  archived BUILD_REPORT: they record the shipped gate as run (E4).
- Other commands that name the bare `python` (`scripts/check_specs.py` in `CLAUDE.md`, the README
  and the CHANGE template; `scripts/prepare_sample.py`; `scripts/profile_data.py`): recorded as
  RESET_COMMAND_VENV I-01.
- The script's behaviour: no line of code changes, only its docstring.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-203 | Runbook sections 8 and 9, the docstring of `scripts/reset_peak_model_outputs.py` and `RESET_COMMAND` | A unit test collects every line that runs `scripts/reset_peak_model_outputs.py` | Sections 8 and 9 and the docstring hold two such lines each, `RESET_COMMAND` one; every one starts with `.venv/bin/python scripts/reset_peak_model_outputs.py`, and none of the texts holds a bare `python scripts/reset_peak_model_outputs.py` |
| AC-204 | The same lines | The test reads the dry-run lines (no `--confirm`) | Each ends its command with `; echo "exit $?"` (before any `#` comment); no `--confirm` line has it |
| AC-205 | `precondition("rebuild", ...)` in `tests/support/ac66_rules.py` with the snapshot present and all three tables present | It refuses | Its message names `.venv/bin/python scripts/reset_peak_model_outputs.py --confirm` and holds no bare `python scripts/` (the refusal path that prints `RESET_COMMAND`) |
| AC-206 | The changed files | The full `pytest`, `ruff check . && ruff format --check .`, `python scripts/check_specs.py` and `git diff origin/main...HEAD -- scripts/ tests/test_ac66_legs_docs.py` | 0 failures and 0 errors; the script diff touches only docstring lines; the AC-160 test diff changes only its filter line |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-203 | Unit | `tests/test_reset_command_venv.py::test_ac203_reset_commands_name_the_project_interpreter` | Reads section 8 and 9 of the runbook (same section split as the AC-160 test), the docstring through `ast`, and `ac66_rules.RESET_COMMAND`; counts and prefixes as stated; a regex forbids `python scripts/reset_peak_model_outputs.py` not preceded by `/` |
| AC-204 | Unit | `tests/test_reset_command_venv.py::test_ac204_dry_run_lines_show_the_exit_code` | Splits each line at ` #`; the dry-run part ends with `; echo "exit $?"`, the `--confirm` part does not contain `echo` |
| AC-205 | Unit | `tests/test_reset_command_venv.py::test_ac205_rebuild_refusal_names_the_project_interpreter` | Calls `ac66_rules.precondition("rebuild", snapshot_ok=True, present=<all True>)` and checks the message contains the full command and no bare `python scripts/` |
| AC-206 | Command | `pytest -q`; `ruff check . && ruff format --check .`; `.venv/bin/python scripts/check_specs.py`; `git diff -U0 origin/main...HEAD -- scripts/ tests/test_ac66_legs_docs.py` | Summaries and hunks pasted in Evidence |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `docs/runbooks/peak_model.md` | Modify | Four command lines, one sentence in section 9 |
| 2 | `scripts/reset_peak_model_outputs.py` | Modify | Docstring usage block only |
| 3 | `tests/support/ac66_rules.py` | Modify | `RESET_COMMAND` |
| 4 | `tests/test_ac66_legs_docs.py` | Modify | Filter of the AC-160 docstring check |
| 5 | `tests/test_reset_command_venv.py` | Create | AC-203 to AC-205 |
| 6 | `.claude/sdd/follow-ups/F_RESET_GUARD_01.md` | Create | Follow-up file, closed in this PR |
| 7 | `.claude/sdd/archive/RESET_GUARD/SHIPPED_2026-11-12.md` | Modify | Follow-ups row RESET_GUARD F-01 annotated as closed |
| 8 | `.claude/sdd/features/CHANGE_RESET_COMMAND_VENV.md` | Create | This document; moved to `archive/RESET_COMMAND_VENV/` when `Complete` |

---

## Evidence

Evidence commit: f1b4b21

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/RESET_COMMAND_VENV/`). `python scripts/check_specs.py` runs
again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-203 | Pass | `pytest -q tests/test_reset_command_venv.py`: `3 passed`. The same file on a copy of `main` (92b268d, `git archive`) gives `3 failed` (AC-203, AC-204, AC-205), so the tests detect the bare `python`. Two command lines each in runbook sections 8 and 9 and in the docstring, all starting with `.venv/bin/python scripts/reset_peak_model_outputs.py` |
| AC-204 | Pass | Same run: each dry-run command is `.venv/bin/python scripts/reset_peak_model_outputs.py; echo "exit $?"`; no `--confirm` line has `echo` |
| AC-205 | Pass | Same run: `precondition("rebuild", snapshot_ok=True, present=<all True>)` refuses and its message holds `.venv/bin/python scripts/reset_peak_model_outputs.py --confirm` |
| AC-206 | Pass | Full `pytest -q -rs`: `917 passed, 1 skipped, 92 deselected, 1 xfailed` (914 on `main` plus the three new tests; the skip is the repository-state test of `test_check_specs.py`). The run preceded ruff's PT018 fix, which split one `assert a and b` of the AC-204 test into two asserts; `pytest -q tests/test_reset_command_venv.py` after it: `3 passed`. Related files `pytest -q tests/test_reset_command_venv.py tests/test_ac66_legs_docs.py tests/test_ac66_rules.py tests/test_reset_guard_docs.py tests/test_peak_reset_script.py`: `144 passed`. `ruff check .`: `All checks passed!`; `ruff format --check .`: `134 files already formatted`. `.venv/bin/python scripts/check_specs.py`: `78 document(s) checked, 0 error(s), 9 warning(s)`. `git diff -U0 origin/main...HEAD -- scripts/ tests/test_ac66_legs_docs.py tests/support/`: hunks `@@ -38,3 +38,3 @@` (script docstring usage block only), `@@ -31 +31 @@` (`RESET_COMMAND`) and `@@ -344 +344 @@` (the AC-160 filter line only) |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | Other commands still name the bare `python`: `python scripts/check_specs.py` (`CLAUDE.md`, `README.md`, `.claude/sdd/README.md`, the CHANGE template), `python scripts/prepare_sample.py` and `python scripts/profile_data.py`. Changing `CLAUDE.md` touches the agent rules file (E8) and the CHANGE template is read by the tests (E5), so it is a separate change | Low | Closed 2026-11-13 by VENV_COMMANDS (follow-up RESET_COMMAND_VENV F-01): every copyable project command outside the archive names `.venv/bin/<tool>` and the setup uses `python3 -m venv .venv`; what the CHANGE track cannot change is carried as VENV_COMMANDS I-01 |

---

## Self-Review

- **Weak points:** the new test pins text, not behaviour: it cannot show that the command runs on
  the user's machine. The live proof is the next user-run dry run.
- **Risks:** `.venv/bin/python` assumes the virtual environment at the repository root, as
  `README.md` creates it; a user with another layout has to adapt the path. The AC-160 filter
  change touches a shipped test; its assertions stay as they were.
- **What I would do differently:** name the project interpreter in the DESIGN of RESET_GUARD,
  where the live gate's command was written.
- **Next improvement:** RESET_COMMAND_VENV I-01, the remaining bare `python` commands.
