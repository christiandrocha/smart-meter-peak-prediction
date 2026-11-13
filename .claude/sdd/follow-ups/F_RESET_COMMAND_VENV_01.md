# FOLLOW-UP: RESET_COMMAND_VENV F-01 - project commands name the tools in .venv/bin

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | RESET_COMMAND_VENV F-01 |
| **Source spec** | RESET_COMMAND_VENV |
| **Source finding** | RESET_COMMAND_VENV I-01 |
| **Source documents** | `.claude/sdd/archive/RESET_COMMAND_VENV/CHANGE_RESET_COMMAND_VENV.md` (Issues row I-01, line 140; a CHANGE folder has no SHIPPED document) |
| **Created** | 2026-11-13 |
| **Status** | Closed |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

RESET_COMMAND_VENV I-01: after the reset commands, other project commands still name a bare
`python` (`scripts/check_specs.py` in `CLAUDE.md`, `.claude/sdd/README.md` and the workflow agent
and command files; `scripts/prepare_sample.py`; `scripts/profile_data.py`). The setup step itself
runs `python -m venv .venv` (`README.md:167`, `docs/runbooks/meter_ingestion.md:92`), which fails
first on a machine with no `python`. `pytest`, `ruff`, `pre-commit` and `pip` are also listed
bare; they work only in an activated environment, and agents never activate it.

User decision (2026-11-13): every copyable project command names `.venv/bin/<tool>`, and the
files the CHANGE track cannot touch are recorded as one new finding.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | `src/smart_meter_peak_prediction/producer.py` (usage docstring) is left out and recorded |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | Text of commands only |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | Archived documents record commands as run; only the archived CHANGE Issues row I-01 is annotated |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | `scripts/check_specs.py` (usage line) and the BUILD_REPORT and CHANGE templates are left out and recorded |
| E6 | No change under `tests/integration/` | Yes | `tests/integration/conftest.py` (one message) is left out and recorded |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | `CLAUDE.md` changes only in the Commands block (tool paths); no rule for agents changes, nothing is relaxed |

Decision: CHANGE track (`CHANGE_VENV_COMMANDS.md`).

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | `CLAUDE.md`, `README.md`, `.claude/sdd/README.md`, the runbooks, the agent and command files, the scripts other than `check_specs.py` and the local-data tests | A unit test scans them | No command starts with a bare `python`, `pytest`, `ruff`, `pre-commit` or `pip`; the setup creates the environment with `python3 -m venv .venv` |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from RESET_COMMAND_VENV I-01 |
| **Priority** | Now |
| **Target** | Next release |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | pending (the PR of `change/venv-commands`; a closure PR records its number after the merge) |
| **Merge commit** | pending |
| **Work done in** | `CHANGE_VENV_COMMANDS.md` |
| **Source rows updated** | `.claude/sdd/archive/RESET_COMMAND_VENV/CHANGE_RESET_COMMAND_VENV.md:140`, Issues row I-01: the Follow-up cell starts with "Closed 2026-11-13 by VENV_COMMANDS", so rule (b) no longer warns for it |
| **check_specs.py after the update** | `79 document(s) checked, 0 error(s), 9 warning(s)` on the change branch with this document still in `features/`: the RESET_COMMAND_VENV I-01 warning is gone. Once `CHANGE_VENV_COMMANDS.md` is archived, its own open VENV_COMMANDS I-01 adds one warning |

---

## Self-Review

- **Weak points:** the scan is a regex over prose and code; a new bare command written in an
  unusual form (for example after a `$ ` prompt) is not caught.
- **Risks:** a person who activates the environment now types longer commands than needed; the
  commands still work.
- **Next step:** after the merge, a closure PR records the PR number and merge commit above (read with `gh pr view`). VENV_COMMANDS I-01 holds what the CHANGE track could not change.
