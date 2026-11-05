# DESIGN: Small Change Track

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SMALL_CHANGE_TRACK |
| **Date** | 2026-11-05 |
| **Author** | christiandrocha (with Claude Code) |
| **Source** | DEFINE_SMALL_CHANGE_TRACK.md (Ready for Design, 2026-11-05) |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

---

## Overview

`scripts/check_specs.py` gains a fifth phase, `CHANGE`, for one-document changes that meet the
eligibility criteria E1 to E8, and stops ignoring misnamed documents. `load_docs` reports every
unrecognized `.md` name in `features/` and `reports/`. `PHASES` gets a `CHANGE` entry, and a
literal `FINAL_STATUS` map replaces the derived one. A new `check_change` validates the
Eligibility rows and the one-document traceability (Acceptance Criteria to Test Strategy to
Evidence, with an evidence commit). In the archive, a folder with a CHANGE document is a "change
folder": that document alone, `Complete`, no SHIPPED. Rules (b) and (c) read archived CHANGE
documents. The AC-119 self-test learns to simulate CHANGE documents without a generated SHIPPED.

---

## Architecture

```text
run(root)
 |- load_docs(root)        features/, reports/: phase docs + unrecognized .md names (new: error)
 |- check_doc              existing per-document rules (CHANGE uses them via PHASES)
 |- check_change           new: Eligibility E1-E8, AC -> Test Strategy -> Evidence, commit SHA
 |- check_traceability     unchanged (DEFINE/DESIGN/BUILD_REPORT)
 |- check_adrs, check_contracts                                    (unchanged)
 '- check_archive
     load_archive          CHANGE_<FOLDER>.md recognized through PHASES (unchanged code path)
       |- check_doc, check_final_status (literal FINAL_STATUS)
       |- check_change     on archived CHANGE documents
       |- check_folder     change folder: only the CHANGE doc, no SHIPPED; else existing rule (a)
       |- open_findings    BUILD_REPORT and CHANGE (new)
       '- citation_violations / check_citations                     (unchanged; reads CHANGE)
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| `PHASES["CHANGE"]` | Sections Metadata, Problem Statement, Eligibility, Scope, Acceptance Criteria, Test Strategy, File Manifest, Evidence, Issues & Follow-ups, Self-Review; statuses `Draft` (False), `Ready for Build` (True), `Complete` (True) | dict entry | FR-75 |
| `FINAL_STATUS` (literal) | `{"BRAINSTORM": "Ready for Define", "DEFINE": "Ready for Design", "DESIGN": "Ready for Build", "BUILD_REPORT": "Complete", "CHANGE": "Complete"}`, replacing the derivation at `scripts/check_specs.py:401-404` | dict | FR-76 |
| `load_docs(root, report)` | As today, plus an error for each `.md` directly in `features/` or `reports/` whose stem matches no `<PHASE>_` prefix; `run()` passes the report | `pathlib` | FR-74 |
| `check_change(doc, report)` | Past `Draft`: Eligibility rows (G-41), AC of Acceptance Criteria present in Test Strategy; when `Complete`: AC present in Evidence, no failing Evidence row (existing `FAILING_CELL`), and an evidence commit (G-42) | `re` | FR-77, FR-78 |
| `check_folder` (extended) | A folder whose phase documents include a CHANGE document must contain only that file and no SHIPPED; otherwise the existing rule (a) | - | FR-79 |
| `check_final_status` | Unchanged code; reads the literal map, so an archived CHANGE document must be `Complete` | - | FR-76, FR-79 |
| `check_archive` (extended) | Calls `check_change` and `open_findings` for archived CHANGE documents | - | FR-80 |
| `CHANGE_TEMPLATE.md` | The ten sections, the Eligibility rows E1 to E8 with empty results, and the `Evidence commit` line | Markdown | FR-81 |
| AC-119 helper (`tests/test_check_specs.py:618`) | Final-status selection through the literal map; for a CHANGE document, a folder with that document and no generated SHIPPED | pytest helper | AC-129 |

---

## Data Model

No table, dataset or new data file.

### Parsing rules (guards)

| Rule | Where | Action | Source |
|---|---|---|---|
| G-40 A name is recognized when its stem starts with `<PHASE>_` for a phase in `PHASES`, longest phase first (as `scripts/check_specs.py:149` today); only `.md` files directly in the folder count | `load_docs` | error on an unrecognized `.md` | FR-74 |
| G-41 An Eligibility row is `^\|\s*(E[1-8])\s*\|\s*([^|]*?)\s*\|` inside `## Eligibility`; the result cell, without `*`, `_` and backticks, must equal `Yes` | `check_change` | error per missing, duplicate or non-`Yes` criterion | FR-77 |
| G-42 The evidence commit is `Evidence commit` followed, on the same line, by a word of 7 to 40 characters in `[0-9a-f]` | `check_change` | error when absent in a `Complete` document | FR-78, D-89 |
| G-43 AC rows of Acceptance Criteria, Test Strategy and Evidence are read with the existing `AC_ROW` pattern (`scripts/check_specs.py`, `ac_ids`) | `check_change` | error per missing AC | FR-78 |
| G-44 Fenced code is ignored as in every other rule (`Doc.body`) | all | ignore | NFR-39 |

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| - | No new ADR: the change is internal to the SDD tooling and reversible; decisions are D-83 to D-89 in the DEFINE and OD-36 to OD-40 below | - |

Design decisions:

| ID | Decision | Reason |
|---|---|---|
| OD-36 | `CHANGE` is a regular entry of `PHASES`, so `load_docs`, `load_archive`, `check_doc` and rule (c) handle it with no new code path | Smallest change; `load_archive` already matches `<PHASE>_<FOLDER>.md` for every phase |
| OD-37 | A literal `FINAL_STATUS` map | A derived "first status past draft" picks `Ready for Build` for CHANGE (DEFINE A-45) |
| OD-38 | A change folder holds exactly one file, the CHANGE document | One form per folder keeps rule (a) simple; a SHIPPED document for one PR adds nothing (DEFINE D-87) |
| OD-39 | `load_docs` receives the report to record unrecognized names, rather than a second listing pass | The listing already happens there |
| OD-40 | E1 to E8 are checked for presence and result only; the `git diff` output is pasted as evidence | A content-only checker cannot see the PR diff; the automated check is follow-up F-01 |

---

## Delivery Plan

| PR | Branch | Content |
|---|---|---|
| 1 | `spec/small-change-track` | This DESIGN and the DEFINE (no code) |
| 2 | `build/small-change-track` | File Manifest 1 to 7 |
| 3 | `ship/small-change-track` | Archive the documents, SHIPPED with follow-ups F-01 and F-02, CHANGELOG |

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom.

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | `scripts/check_specs.py` | Modify | `CHANGE` phase, literal `FINAL_STATUS`, unrecognized names, `check_change`, change folders, rule (b) on CHANGE, docstring (FR-74 to FR-80) | build-agent | - |
| 2 | `.claude/sdd/templates/CHANGE_TEMPLATE.md` | Create | The CHANGE template (FR-81) | build-agent | 1 |
| 3 | `tests/test_check_specs.py` | Modify | AC-120 to AC-130; `test_all_templates_have_required_sections` gains the CHANGE template; the AC-119 helper learns CHANGE documents (AC-129) | build-agent | 1, 2 |
| 4 | `.claude/sdd/README.md` | Modify | The CHANGE track, E1 to E8 and the unrecognized-name rule; the `templates/` row no longer says "one template per phase" only | build-agent | 1 |
| 5 | `docs/conventions/git.md` | Modify | Branch names (`docs/conventions/git.md:20`): `change/<feature-kebab>` for the track, `spec/`, `build/`, `ship/` for full specs; no rule under "Rules for agents" changes (DEFINE D-84) | build-agent | - |
| 6 | `CLAUDE.md` | Modify | "How work is done here": one line for the CHANGE track; golden rules unchanged (DEFINE D-84) | build-agent | - |
| 7 | `.claude/sdd/reports/BUILD_REPORT_SMALL_CHANGE_TRACK.md` | Create | Evidence for every AC and the Build Evidence below | build-agent | 1 to 6 |

Read and not modified: every file under `.claude/sdd/archive/`, `.claude/sdd/citation_allowlist.json`,
the other templates, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.

---

## Test Strategy

Every acceptance criterion from DEFINE appears here. All tests are unit tests in
`tests/test_check_specs.py`, run by plain `pytest` and by CI.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-120 | Unit (repository) | `tests/test_check_specs.py::test_ac120_repository_has_no_errors` | `check_specs.run(ROOT).errors == []`; the full run output with the final head SHA is pasted into the BUILD_REPORT |
| AC-121 | Unit (parametrized) | `::test_ac121_unrecognized_names_fail` | `NOTES.md` in `features/` and `draft.md` in `reports/` each give one error naming the file; `.gitkeep` and valid names give none |
| AC-122 | Unit (parametrized) | `::test_ac122_change_document_rules` | Valid `Draft`, `Ready for Build` and `Complete` documents pass; missing section, placeholder past `Draft` and empty Self-Review give one error each |
| AC-123 | Unit | `::test_ac123_final_status_is_explicit` | `FINAL_STATUS` equals the FR-76 map, and `Ready for Build` is not the CHANGE final status |
| AC-124 | Unit (parametrized) | `::test_ac124_eligibility_rows` | All `Yes` passes; missing E8, duplicate E3 and E5 `No` give one error each naming the criterion |
| AC-125 | Unit (parametrized) | `::test_ac125_change_traceability_and_evidence_commit` | AC missing from Test Strategy, missing from Evidence, a `Fail` row and no `Evidence commit` each give one error; the valid `Complete` document passes |
| AC-126 | Unit (parametrized) | `::test_ac126_archived_change_folders` | A folder with one `Complete` CHANGE document passes without SHIPPED; `Ready for Build`, an extra SHIPPED and an extra DEFINE each give one rule (a) error |
| AC-127 | Unit | `::test_ac127_rules_b_and_c_read_change_documents` | One `Open` warning; one unprefixed foreign ID error; own IDs pass |
| AC-128 | Unit | `::test_all_templates_have_required_sections` (extended) and `::test_ac128_change_template_sections_and_criteria` | No missing-section error for the six templates; CHANGE headings equal the section list; rows E1 to E8 present |
| AC-129 | Unit | `::test_ac129_self_test_simulates_change_documents` | With a temporary `features/` holding a `Complete` and a `Ready for Build` CHANGE document, the helper adds only the first, as a folder without SHIPPED, and the simulated archive gives 0 errors |
| AC-130 | Unit | `::test_ac130_docs_describe_the_change_track` | README, `git.md` and `CLAUDE.md` contain the required names |

---

## Build Evidence

The BUILD_REPORT records, generated on the **final head of the build branch** and naming that
SHA (lesson of SPEC_ARCHIVE_GATES), the output of `python scripts/check_specs.py` on the
repository: the document count, the errors (0) and the warnings with their IDs (expected at design
time: 2, for INGESTION_GUARD I-11 and INGESTION_GUARD I-12), and the number of documents the AC-119
self-test added.

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | None; the hook and CI run the script as today (DEFINE C-21) |
| Scheduling and retries | Not applicable |
| Monitoring and alerting | A failing gate fails the hook and the CI `checks` job, which the `main-protection` ruleset now requires before a merge |
| Secrets | None |
| Cost | No cloud resource |
| Backfill / reprocessing | The first run covers every existing document; 0 new errors expected (DEFINE A-43, A-44) |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| E1 to E8 are self-declared | An ineligible change can be filed as a CHANGE document | The `git diff` output is pasted as evidence and reviewed; F-01 automates it |
| A stray note in `features/` now fails CI | Friction for drafts kept there | Intended (FR-74); notes go in `notes/`, which git ignores (golden rule 7) |
| Two archive folder forms | rule (a) has two branches | One test per branch (AC-126) |
| The AC-119 helper changes | The SPEC_ARCHIVE_GATES self-test could regress | AC-129 runs the helper on both kinds of folder; the existing AC-119 tests stay |

---

## Open Items for the User

| ID | Item |
|---|---|
| Q-29 | Meaning of E8 (DEFINE D-86) |
| Q-30 | Confirmation of the retrospective recommendations (DEFINE D-85, D-87, D-88) |

Either answer changes only the criteria text or the folder form, not the components.

---

## Self-Review

- **Weak points:** The track trusts the declared criteria (OD-40). The literal `FINAL_STATUS`
  duplicates information that `PHASES` also holds; AC-123 pins it.
- **Risks:** `load_docs` signature changes; every caller in the tests must still work (the tests
  call `check_specs.run`, and the AC-119 helper calls `load_docs` directly).
- **What I would do differently:** Settle Q-29 and Q-30 before the DESIGN.
- **Next improvement:** Use the track for retrospective Step 2 as its first real case.

---

## Next Step

`/build .claude/sdd/features/DESIGN_SMALL_CHANGE_TRACK.md`

---

## Change Log

| Date | Change | Reason | Impact |
|---|---|---|---|
| 2026-11-05 | First version, Ready for Build | DEFINE_SMALL_CHANGE_TRACK.md Ready for Design | Build in PR 2 after this PR is approved |
