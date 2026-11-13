# FOLLOW-UP: RESET_GUARD F-01 - project interpreter in the reset command

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | RESET_GUARD F-01 |
| **Source spec** | RESET_GUARD |
| **Source finding** | none (Lessons Learned, platform row of the SHIPPED document) |
| **Source documents** | `.claude/sdd/archive/RESET_GUARD/SHIPPED_2026-11-12.md` (Follow-ups row F-01, line 142) |
| **Created** | 2026-11-13 |
| **Status** | Closed |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

The first live attempt of RESET_GUARD AC-202 (2026-11-12) failed before the script ran: the user's
machine has no bare `python`, only the project interpreter `.venv/bin/python`. The reset commands
that a person copies still name the bare `python`:

- `docs/runbooks/peak_model.md`, lines 207 and 208 (section 8) and 256 and 257 (section 9);
- the usage block of the `scripts/reset_peak_model_outputs.py` docstring, lines 39 and 40;
- `RESET_COMMAND` in `tests/support/ac66_rules.py` (line 31), which the AC-66 legs print in their
  "next: the user runs ..." refusal lines.

The dry-run commands also do not show the exit code, which AC-202 needs (`0` or `2`).

The AC-202 text itself is in the archived RESET_GUARD DEFINE (line 181) and DESIGN (U-09); it is a
record of the shipped gate and is not changed (E4).

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | `docs/runbooks/peak_model.md`, `scripts/reset_peak_model_outputs.py` (docstring only), `tests/support/ac66_rules.py`, `tests/test_ac66_legs_docs.py`, one new unit test, SDD documents |
| E2 | No change under `docs/contracts/` | Yes | None predicted |
| E3 | No new ADR | Yes | Text of commands only; no decision that outlives the change |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | AC-202 in the archived DEFINE and DESIGN stays as shipped; only the SHIPPED Follow-ups row F-01 is annotated |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None predicted |
| E6 | No change under `tests/integration/` | Yes | `tests/support/` is outside `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None predicted |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | Neither file changes |

Decision: CHANGE track (`CHANGE_RESET_COMMAND_VENV.md`).

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | Runbook sections 8 and 9, the script docstring and `RESET_COMMAND` | A unit test reads them | Every reset command names `.venv/bin/python`, none names a bare `python`, and each dry-run command ends with `; echo "exit $?"` |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, none inherited (a person sees the shell error at once; nothing is dropped) |
| **Priority** | Now |
| **Target** | Next release |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | pending (the PR of `change/reset-command-venv`; a closure PR records its number after the merge) |
| **Merge commit** | pending |
| **Work done in** | `CHANGE_RESET_COMMAND_VENV.md` |
| **Source rows updated** | `.claude/sdd/archive/RESET_GUARD/SHIPPED_2026-11-12.md:142`, Follow-ups row F-01: the item text ends with the bold "Closed 2026-11-13 by RESET_COMMAND_VENV" sentence and the target reads "Closed (next release)". The SHIPPED Follow-ups table has no Follow-up cell, so the row was never a rule (b) warning |
| **check_specs.py after the update** | `78 document(s) checked, 0 error(s), 9 warning(s)` on the change branch, the same nine warnings as on `main` (other archived documents); none names RESET_GUARD |

---

## Self-Review

- **Weak points:** other commands in the repository (`python scripts/check_specs.py` in
  `CLAUDE.md` and the CHANGE template, `python scripts/prepare_sample.py`) also name the bare
  `python`; they are out of scope here and recorded as an issue of the CHANGE document.
- **Risks:** `.venv/bin/python` assumes the virtual environment is at the repository root, which
  is where the project creates it.
- **Next step:** after the merge, a closure PR records the PR number and merge commit above (read with `gh pr view`). RESET_COMMAND_VENV I-01 holds the remaining bare `python` commands.
