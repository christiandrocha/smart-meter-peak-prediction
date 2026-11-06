# CHANGE: Follow-up task template

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | FOLLOW_UP_TEMPLATE |
| **Date** | 2026-11-06 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/follow-up-template` |
| **Status** | Complete |
| **Source** | SDD process retrospective of 2026-11-05, Step 2; SMALL_CHANGE_TRACK D-85 (the template is read by neither the script nor the tests, so it can use this track) |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

Follow-ups exist only as rows in the Follow-ups table of a SHIPPED document (for example
SMALL_CHANGE_TRACK F-01, SMALL_CHANGE_TRACK F-02, SMALL_CHANGE_TRACK F-05 to SMALL_CHANGE_TRACK F-07). A row has an item and a target, but no place for
the work itself: which track it needs, what closes it, and where it was closed. Two effects,
measured on `main` 74cf210:

- When a follow-up is picked up, the triage against E1 to E8 is redone from scratch each time.
- Closing a follow-up needs an edit to the source BUILD_REPORT row, or `check_specs.py` rule (b)
  keeps warning; INGESTION_GUARD I-11 and INGESTION_GUARD I-12 still warn today. Nothing records how the
  follow-up was closed or which source row was updated.

The decision of 2026-11-06 (user): one file per follow-up in a new folder
`.claude/sdd/follow-ups/`, from a new `templates/FOLLOW_UP_TEMPLATE.md` with four parts in
addition to origin, problem and status: triage E1 to E8, done criterion, target and priority,
and closure.

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-only origin/main...HEAD` on 6d6e952 lists only `.claude/sdd/README.md`, `.claude/sdd/features/CHANGE_FOLLOW_UP_TEMPLATE.md`, `.claude/sdd/follow-ups/.gitkeep`, `.claude/sdd/templates/FOLLOW_UP_TEMPLATE.md`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD`: `M .claude/sdd/README.md`, `A` for the other three; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: no file under `.claude/sdd/archive/` changed before the final commit, which only adds this document there |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor a template read by them; `grep -rn FOLLOW_UP scripts/check_specs.py tests/` has no match (exit 1) |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`: empty (0 lines) |

E1 to E8 all `Yes`: the PR touches only `.claude/sdd/`. No new test reads the new
template, because a test that read it would make it a template "the tests read" and break E5.

---

## Scope

**In scope:**
- `.claude/sdd/templates/FOLLOW_UP_TEMPLATE.md`: a template for one follow-up task, with
  Metadata (follow-up ID with spec prefix, source spec, source finding, source documents,
  status), Problem, Triage (E1 to E8), Done Criterion, Target and Priority, Closure, and
  Self-Review.
- `.claude/sdd/follow-ups/`: the folder for follow-up files, named
  `F_<SPEC>_<NN>.md` (for example `F_SMALL_CHANGE_TRACK_05.md`), kept with a `.gitkeep`.
- `.claude/sdd/README.md`: the Folders table gains `follow-ups/`, the `templates/` row names the
  new template, and a short "Follow-ups" section says when to create a file, how to triage it,
  and that closing it means updating the source row so rule (b) stops warning.

**Out of scope:**
- Any check of follow-up files by `scripts/check_specs.py` (that would break E5; it needs a full
  cycle if wanted later).
- Creating follow-up files for existing follow-ups (SMALL_CHANGE_TRACK F-01,
  SMALL_CHANGE_TRACK F-02, SMALL_CHANGE_TRACK F-05 to SMALL_CHANGE_TRACK F-07,
  INGESTION_GUARD I-11, INGESTION_GUARD I-12): done one by one later, when each is picked up.
- Retrospective Step 3 (confirmation rules) and the template repository port
  (SMALL_CHANGE_TRACK F-02).
- `CLAUDE.md` and `docs/conventions/git.md`: unchanged, so E8 stays `Yes`.

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-132 | The new `FOLLOW_UP_TEMPLATE.md` | Its `## ` headings are listed outside fences | They are exactly, in order: Metadata, Problem, Triage, Done Criterion, Target and Priority, Closure, Self-Review |
| AC-133 | The template's Triage section | It is read | It has one row per criterion E1 to E8 and a Decision line naming `CHANGE track` or `full cycle`, with "in doubt, full cycle" |
| AC-134 | The template's Metadata | It is read | It has a Status row with the allowed values `Open`, `In Progress`, `Closed`, `Dropped`, and the follow-up ID carries the spec prefix (`<SPEC> F-NN`) |
| AC-135 | The template's Closure section | It is read | It asks for the PR, the merge commit, the CHANGE document or spec that did the work, the source row updated (`file:line`, no longer starting with `Open`), and the `check_specs.py` output after the update |
| AC-136 | A copy of the template saved as `.claude/sdd/follow-ups/F_X_01.md` | `python scripts/check_specs.py` runs | It reports 0 errors and no warning for that file: the folder is not scanned, so the file is neither an unrecognized name nor a checked document |
| AC-137 | `.claude/sdd/README.md` | It is read | The Folders table lists `follow-ups/`, the `templates/` row names `FOLLOW_UP_TEMPLATE.md`, and a Follow-ups section covers creation, triage and closure |
| AC-138 | The whole repository on the final head | `python scripts/check_specs.py`, `pytest tests/test_check_specs.py` and `pre-commit run --all-files` run | 0 errors; warnings only for INGESTION_GUARD I-11 and INGESTION_GUARD I-12 (as on `main`) and, once this document is archived, for its own findings still marked `Open` (rule b); all tests pass, all hooks pass |

---

## Test Strategy

No unit test reads the new template, so that E5 holds (a test that read it would make it a gate).
Each criterion is proved by a command whose output goes in Evidence.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-132 | Command | `python -c` that strips fences with `check_specs.FENCE` and lists `check_specs.HEADING` matches of the template | Output equals the seven headings in order |
| AC-133 | Command | `grep -nE '^\| E[1-8] ' .claude/sdd/templates/FOLLOW_UP_TEMPLATE.md` and `grep -n 'Decision' ...` | Eight rows E1 to E8 and the Decision line with both tracks and the in-doubt rule |
| AC-134 | Command | `grep -n 'Status\|F-NN' .claude/sdd/templates/FOLLOW_UP_TEMPLATE.md` | Status row with the four values; ID pattern with the spec prefix |
| AC-135 | Command | `grep -n -A12 '^## Closure' .claude/sdd/templates/FOLLOW_UP_TEMPLATE.md` | The five closure items are present |
| AC-136 | Command | Copy the template to `follow-ups/F_X_01.md`, run `python scripts/check_specs.py`, then remove the copy | Same summary line as without the copy: 0 errors, 2 warnings, none naming `F_X_01.md` |
| AC-137 | Command | `grep -n 'follow-ups/\|FOLLOW_UP_TEMPLATE\|## Follow-ups' .claude/sdd/README.md` | The three README parts are present |
| AC-138 | Command | The three commands on the final head | Output pasted in Evidence and in the PR description |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `.claude/sdd/templates/FOLLOW_UP_TEMPLATE.md` | Create | The follow-up task template (AC-132 to AC-135) |
| 2 | `.claude/sdd/follow-ups/.gitkeep` | Create | Keeps the empty folder in git |
| 3 | `.claude/sdd/README.md` | Modify | Folders table, `templates/` row and a Follow-ups section (AC-137) |
| 4 | `.claude/sdd/features/CHANGE_FOLLOW_UP_TEMPLATE.md` | Create, then move to `archive/FOLLOW_UP_TEMPLATE/` | This document (D-91: the final commit touches only this document) |

---

## Evidence

Evidence commit: 6d6e952

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/FOLLOW_UP_TEMPLATE/`). `python scripts/check_specs.py` runs
again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-132 | Pass | Headings outside fences (`check_specs.FENCE`, `check_specs.HEADING`): `['Metadata', 'Problem', 'Triage', 'Done Criterion', 'Target and Priority', 'Closure', 'Self-Review']` |
| AC-133 | Pass | `grep -nE '^\| E[1-8] '` gives eight rows E1 to E8 (lines 39 to 46); line 48 the Decision line naming both the CHANGE track and the full cycle; line 50 `In doubt, full cycle.` |
| AC-134 | Pass | Line 13 `**Follow-up**` with the spec prefix (spec name, then `F-` and the number); line 18 `**Status** | Open`; line 20 allowed values `Open`, `In Progress`, `Closed`, `Dropped` |
| AC-135 | Pass | Closure rows: Pull request, Merge commit (read with `gh pr view`), Work done in, Source rows updated (`file:line`, no longer starting with `Open`), check_specs.py after the update |
| AC-136 | Pass | Without the copy: `58 document(s) checked, 0 error(s), 2 warning(s)`. With the template copied to `follow-ups/F_X_01.md`: the same line, exit 0, and `F_X_01` in no output line. Copy removed afterwards |
| AC-137 | Pass | README line 87 `## Follow-ups` (creation, triage, closure in four steps); line 121 `templates/` row names `FOLLOW_UP_TEMPLATE.md`; line 125 Folders row `follow-ups/` |
| AC-138 | Pass | On the final tree: `check_specs.py` `58 document(s) checked, 0 error(s), 4 warning(s)`, exit 0; the warnings are INGESTION_GUARD I-11, INGESTION_GUARD I-12 and this document's own FOLLOW_UP_TEMPLATE I-01 and I-02 (rule b). `pytest tests/test_check_specs.py`: 114 passed, 1 skipped (the AC-119 self-test, no `features/` or `reports/` document left). `pre-commit run --all-files`: all hooks passed. The first run on this tree found 5 errors in this document (quoted template braces read as placeholders; unprefixed citations, rule c), fixed before this commit |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | Follow-up files are not checked by any gate: a file can miss a section or keep `Open` after the work is done, and nothing warns | Low | Open: accepted by the decision of 2026-11-06 (option a); a check would need a full cycle because it changes `check_specs.py` |
| I-02 | The source row and the follow-up file can disagree (one `Closed`, the other `Open`), because the Closure step is a process rule | Low | Open: the template asks for both updates in the same PR |

---

## Self-Review

- **Weak points:** The ACs are proved by commands, not by unit tests, because a test that read the
  template would break E5. The follow-up files have no automatic check (I-01).
- **Risks:** Two places can describe one follow-up, the SHIPPED row and the file, and drift
  apart (I-02). The `F_<SPEC>_<NN>.md` name repeats the spec prefix rule by convention only.
- **What I would do differently:** Write the Eligibility evidence as "Planned" from the start. At
  `Ready for Build` the checker already requires a non-empty evidence cell, before any diff exists,
  so the first CHANGE document had to fill it with the plan and replace it at `Complete`.
- **Next improvement:** Create the first follow-up file when SMALL_CHANGE_TRACK F-05 to SMALL_CHANGE_TRACK F-07 are
  picked up, and check whether the triage shortens the next CHANGE document.
