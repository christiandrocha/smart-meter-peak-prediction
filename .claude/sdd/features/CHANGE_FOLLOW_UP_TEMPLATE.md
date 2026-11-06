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
| **Status** | Ready for Build |
| **Source** | SDD process retrospective of 2026-11-05, Step 2; SMALL_CHANGE_TRACK D-85 (the template is read by neither the script nor the tests, so it can use this track) |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

Follow-ups exist only as rows in the Follow-ups table of a SHIPPED document (for example
SMALL_CHANGE_TRACK F-01, F-02, F-05 to F-07). A row has an item and a target, but no place for
the work itself: which track it needs, what closes it, and where it was closed. Two effects,
measured on `main` 74cf210:

- When a follow-up is picked up, the triage against E1 to E8 is redone from scratch each time.
- Closing a follow-up needs an edit to the source BUILD_REPORT row, or `check_specs.py` rule (b)
  keeps warning; INGESTION_GUARD I-11 and I-12 still warn today. Nothing records how the
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
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | Planned: the manifest touches only `.claude/sdd/`; the `git diff` output replaces this line at Complete |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Planned: the manifest touches only `.claude/sdd/`; the `git diff` output replaces this line at Complete |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | Planned: the manifest touches only `.claude/sdd/`; the `git diff` output replaces this line at Complete |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Planned: the manifest touches only `.claude/sdd/`; the `git diff` output replaces this line at Complete |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Planned: the manifest touches neither `scripts/check_specs.py` nor `tests/`; the `git diff` and a `grep -rn FOLLOW_UP scripts/check_specs.py tests/` with no match replace this line at Complete |
| E6 | No change under `tests/integration/` (same output) | Yes | Planned: the manifest touches only `.claude/sdd/`; the `git diff` output replaces this line at Complete |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | Planned: the manifest touches only `.claude/sdd/`; the `git diff` output replaces this line at Complete |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs a Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Yes | Planned: `docs/conventions/git.md` and `CLAUDE.md` are not in the manifest; the empty `git diff` replaces this line at Complete |

Planned: E1 to E8 all `Yes`. The manifest touches only `.claude/sdd/`. No new test reads the new
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
- Creating follow-up files for existing follow-ups (SMALL_CHANGE_TRACK F-01, F-02, F-05 to F-07,
  INGESTION_GUARD I-11, I-12): done one by one later, when each is picked up.
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
| AC-138 | The whole repository on the final head | `python scripts/check_specs.py`, `pytest tests/test_check_specs.py` and `pre-commit run --all-files` run | 0 errors; warnings only for INGESTION_GUARD I-11 and I-12 (as on `main`) and, once this document is archived, for its own findings still marked `Open` (rule b); all tests pass, all hooks pass |

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

Evidence commit: filled at Complete

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/FOLLOW_UP_TEMPLATE/`). `python scripts/check_specs.py` runs
again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-132 | Not run | Build not done yet |
| AC-133 | Not run | Build not done yet |
| AC-134 | Not run | Build not done yet |
| AC-135 | Not run | Build not done yet |
| AC-136 | Not run | Build not done yet |
| AC-137 | Not run | Build not done yet |
| AC-138 | Not run | Build not done yet |

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
- **What I would do differently:** Nothing yet. This is the first real use of the CHANGE track, so
  the evidence steps themselves are part of what is being tested.
- **Next improvement:** Create the first follow-up file when SMALL_CHANGE_TRACK F-05 to F-07 are
  picked up, and check whether the triage shortens the next CHANGE document.
