# Spec-Driven Development workflow

Every non-trivial change goes through phases. Each phase produces one document, and the next
phase starts only when the previous document passes its gate.

```text
/brainstorm  ->  features/BRAINSTORM_{FEATURE}.md      (optional, Phase 0)
/define      ->  features/DEFINE_{FEATURE}.md          (Phase 1)
/design      ->  features/DESIGN_{FEATURE}.md          (Phase 2)
/build       ->  code + reports/BUILD_REPORT_{FEATURE}.md  (Phase 3)
/ship        ->  archive/{FEATURE}/SHIPPED_{YYYY-MM-DD}.md (Phase 4)
/iterate     ->  updates any of the documents above, with a change log
/adr         ->  docs/adr/NNNN-title.md                (any phase)
```

Small tooling or process changes that meet every criterion E1 to E8 below use the CHANGE track
instead: one document, `features/CHANGE_{FEATURE}.md`, from `templates/CHANGE_TEMPLATE.md`.

## Phase gates

| Phase | Gate to leave the phase | Status value when the gate passes |
|---|---|---|
| Brainstorm | At least 3 discovery questions answered, 2+ approaches compared, one selected by the user, YAGNI list written | `Ready for Define` |
| Define | Clarity score >= 12/15, every acceptance criterion measurable and numbered `AC-NN` | `Ready for Design` |
| Design | Every `AC-NN` mapped to a test, file manifest complete, decisions recorded as ADRs | `Ready for Build` |
| Build | Every manifest file created and verified, every `AC-NN` has evidence | `Complete` |
| Ship | Lessons learned and follow-ups recorded, documents archived | `Shipped` |

`scripts/check_specs.py` enforces the mechanical part of these gates in CI:
required sections, valid status, no unfilled placeholders after the draft stage,
and acceptance-criteria traceability from DEFINE to DESIGN to BUILD_REPORT. It also checks
the structure of ADRs (`docs/adr/`) and data contracts (`docs/contracts/`).

Shipped features in `archive/` are checked as well (SPEC_ARCHIVE_GATES):

- the rules above, with traceability inside each `archive/<FEATURE>/` folder;
- every archived document is in its phase's final status, and each folder has exactly one
  `SHIPPED_YYYY-MM-DD.md` with status `Shipped`;
- SHIPPED documents: the file-name date equals the `Shipped on` row, every template section is
  present including a non-empty Self-Review, and from the cut-off date 2026-11-05 also
  `Pull Requests and Branches` and no unfilled placeholders (the date always comes from the file
  name, never from file times);
- a warning for each archived finding whose Follow-up cell starts with `Open`;
- a finding ID from another spec is cited with that spec's name in front, for example
  `INGESTION_GUARD I-13` (a soft wrap between the two is fine, a blank line is not). Existing
  unprefixed citations are frozen with exact counts in `citation_allowlist.json`; a count that
  differs or an entry that matches nothing is an error, so update the entry in the same change.

## CHANGE track

One document replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. Statuses: `Draft`,
`Ready for Build`, `Complete`; the final status of every phase is explicit in `check_specs.py`.
The change is eligible only when every criterion holds for the files the PR changes (the
`git diff` output is pasted as evidence in the Eligibility table):

| ID | Criterion |
|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No change under `docs/contracts/` |
| E3 | No new ADR |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read |
| E6 | No change under `tests/integration/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate: hardening is `Yes`; relaxing is `Relaxing` and needs a `## Rule Changes` section (before and after with `file:line`, `gh api` output, `User OK: YYYY-MM-DD`). In doubt, it is relaxing |

`check_specs.py` checks the rows, the `## Rule Changes` parts, AC traceability (Acceptance
Criteria, Test Strategy, Evidence) and an `Evidence commit <SHA>` line in a `Complete` document.
In a `Complete` document an Evidence result of `Fail` or `Not run` is an error. A deliberate
deferral is written `Deferred: <reason>`: it is accepted and listed as a warning in the output, so
it stays visible; `Deferred` without a reason is an error.
It does not read the git history. These process rules are therefore yours to follow:

- STOP for the user's explicit OK on the rules diff before any commit that changes
  `docs/conventions/git.md` or `CLAUDE.md` (E8 `Relaxing`).
- The `Evidence commit` is the last commit of the PR that touches files other than the CHANGE
  document. The final commit touches only the CHANGE document (status `Complete` and the move to
  `archive/{FEATURE}/`). Run `python scripts/check_specs.py` again on the final head and put its
  output in the PR description.

A change folder in `archive/` holds only `CHANGE_{FEATURE}.md` with status `Complete`, and no
SHIPPED document. Rules (b) and (c) read it as they read a BUILD_REPORT.

Any other `.md` file directly in `features/` or `reports/` whose name has no phase prefix is an
error (unrecognized name). Notes go in `notes/`, which git ignores.

## Follow-ups

A follow-up (`F-NN` in a SHIPPED Follow-ups table, or an open finding of a BUILD_REPORT or CHANGE
document) gets its own file when someone picks it up:

1. Copy `templates/FOLLOW_UP_TEMPLATE.md` to `follow-ups/F_<SPEC>_<NN>.md`, status `Open`. Cite the
   follow-up and its finding with the spec prefix (`SMALL_CHANGE_TRACK F-05`).
2. Triage it against E1 to E8. Every row `Yes` (E8 may be `Relaxing`) means the CHANGE track; any
   `No` or `Unknown` means the full cycle. In doubt, full cycle.
3. Write the done criterion; it becomes an acceptance criterion of the CHANGE document or spec
   that does the work. Set severity, priority and target (or "Not scheduled" with a reason).
4. Close it in the PR that does the work: fill Closure, set the status to `Closed` (or `Dropped`
   with a reason), and update the source rows so that their Follow-up cell no longer starts with
   `Open`; rule (b) of `check_specs.py` then stops warning. Read the merge commit with
   `gh pr view` after the merge.

`check_specs.py` does not read `follow-ups/`: the file and the source rows are kept in step by
hand.

## Rules

1. Specs describe *what* and *why* before code describes *how*. Code written before the spec
   is allowed only as a spike (see `docs/spikes/README.md`).
2. One feature per document set. `{FEATURE}` is UPPER_SNAKE_CASE and identical across phases.
3. Change an approved document only through `/iterate`, which logs the change and checks what
   it invalidates downstream.
4. Decisions that outlive the feature (technology choice, data layout, contract) become ADRs.
5. Every phase document ends with a **Self-Review**: weak points, risks, trade-offs and the
   concrete improvement you would make next. A document without it does not pass the gate.

## Folders

| Folder | Content |
|---|---|
| `templates/` | One template per phase, plus `CHANGE_TEMPLATE.md` for the CHANGE track and `FOLLOW_UP_TEMPLATE.md` for follow-up tasks. Agents copy them; do not edit them per feature |
| `features/` | Active feature documents |
| `reports/` | Build reports |
| `archive/` | Shipped features, one folder per feature |
| `follow-ups/` | One file per follow-up task, `F_<SPEC>_<NN>.md`, from `templates/FOLLOW_UP_TEMPLATE.md`; not read by `check_specs.py` |
