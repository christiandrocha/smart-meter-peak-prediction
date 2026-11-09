# FOLLOW-UP: SMALL_CHANGE_TRACK F-02 - Port the SDD tooling to the template repository

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | SMALL_CHANGE_TRACK F-02, together with SPEC_ARCHIVE_GATES F-01 |
| **Source spec** | SMALL_CHANGE_TRACK (and SPEC_ARCHIVE_GATES) |
| **Source finding** | none |
| **Source documents** | `.claude/sdd/archive/SMALL_CHANGE_TRACK/SHIPPED_2026-11-06.md` (Follow-ups row F-02), `.claude/sdd/archive/SPEC_ARCHIVE_GATES/SHIPPED_2026-11-05.md` (Follow-ups row F-01) |
| **Created** | 2026-11-09 |
| **Status** | In Progress |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

SMALL_CHANGE_TRACK F-02: "Port the track to the template repository, together with
SPEC_ARCHIVE_GATES F-01". SPEC_ARCHIVE_GATES F-01: "Port the change (script, SHIPPED template,
README check list, tests) to the template repository".

Measured on 2026-11-09: the template repository `~/Documents/sdd-data-template` (last commit
67e0f12, 2026-10-13) is a month behind. `scripts/check_specs.py` differs by 413 lines,
`tests/test_check_specs.py` by 726; `CHANGE_TEMPLATE.md` and `FOLLOW_UP_TEMPLATE.md` are missing;
`git.md`, `CLAUDE.md`, the SDD README and the pre-commit configuration are behind. Details in
`CHANGE_TEMPLATE_PORT.md`, Problem Statement.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

The criteria are applied to this repository. The template repository has no SDD process of its
own; its changes copy code and rules already gated here.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Here: `tests/test_check_specs.py`, this file, the CHANGE document, two SHIPPED rows |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | Only SHIPPED Follow-ups rows are annotated |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | Neither changes here; only a test helper |
| E6 | No change under `tests/integration/` | Yes | None |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | `pyproject.toml` unchanged here |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | Unchanged here; the template only gains rules (no R1 exception) |

Decision: CHANGE track (`.claude/sdd/features/CHANGE_TEMPLATE_PORT.md`).

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | The template branch with the port | Its checks run, and a project is generated from it with `init_project.py` | The template's checks pass with 0 errors and 0 warnings and the generated project's tests and checker pass (TEMPLATE_PORT AC-150, AC-151); the copied gate files are byte-identical to this repository (TEMPLATE_PORT AC-146) |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | none |
| **Priority** | Now |
| **Target** | 2026-11-09 |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | Planned |
| **Merge commit** | Planned |
| **Work done in** | `CHANGE_TEMPLATE_PORT.md` |
| **Source rows updated** | Planned |
| **check_specs.py after the update** | Planned |

---

## Self-Review

- **Weak points:** The template port is proved by commands, not by a gate in the template.
- **Risks:** The template drifts again with the next process change (TEMPLATE_PORT I-02).
- **Next step:** Build the port on the template branch and fill Closure.
