# DEFINE: Spec Archive Gates

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SPEC_ARCHIVE_GATES |
| **Date** | 2026-11-05 |
| **Author** | christiandrocha (with Claude Code) |
| **Source** | Follow-up "check_specs does not read archive/" (AC97_TIMING_EVIDENCE SHIPPED, carried since INGESTION_GUARD); discovery of 2026-11-05 (measurements quoted below); no BRAINSTORM: small feature cycle, as AC97_TIMING_EVIDENCE |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

---

## Problem Statement

`scripts/check_specs.py` reads only `.claude/sdd/features/` and `.claude/sdd/reports/`
(`scripts/check_specs.py:133`; docstring lines 15-16: "Archived documents and templates are not
checked"). Every shipped spec lives in `.claude/sdd/archive/`, and archived documents are still
edited (the 2026-11-05 `/iterate` on the archived AC97_TIMING_EVIDENCE DESIGN, PR #39), so those
edits pass the "SDD spec gates" hook and the CI step without any check. Finding IDs also restart
in every spec (METER_INGESTION I-11, AC97_TIMING_EVIDENCE I-11 and INGESTION_GUARD I-11 are three
different findings), and a citation without its spec prefix sent one
task to the wrong spec on 2026-11-05.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Author running `/iterate` or annotating an archived spec | An edit that breaks a gate fails before it is merged | pre-commit hook "SDD spec gates" (`.pre-commit-config.yaml:26-32`) and the CI step (`.github/workflows/ci.yml:32-33`) |
| Reviewer of a spec PR | Shipped documents stay in their final status and well formed | `check_specs.py` output |
| Agent or person citing a finding from another spec | Unambiguous references (`INGESTION_GUARD I-13`) | Error message naming the file and the ID |
| Template repository maintainer | The same checks in new projects | Follow-up F-01 (out of scope here) |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Archived documents are gated | Archived phase and SHIPPED documents checked on every run | All 23 current archived documents (18 phase + 5 SHIPPED) counted in the summary line |
| No red CI on day one | Errors on the current tree after the build | 0 errors |
| Existing unprefixed citations are frozen, not rewritten | Entries in the citation allowlist | 12 entries, 17 citations (measured 2026-11-05, approved D-76); every new one fails |
| Open findings are visible | Warnings on the current tree | Exactly 2 (INGESTION_GUARD I-11 and INGESTION_GUARD I-12) |

---

## Scope

**In scope:**
- Loading archived documents: phase documents (`<PHASE>_<FEATURE>.md`) and `SHIPPED_YYYY-MM-DD.md` in
  `.claude/sdd/archive/<FEATURE>/`.
- The current per-document and traceability rules applied to archived phase documents.
- New rule (a): archived documents are in the final status of their phase, and each archive folder
  has exactly one SHIPPED document.
- SHIPPED as a checked phase, with a cut-off for the template section added on 2026-11-05, and a
  required, non-empty `## Self-Review` (golden rule 6), added to the SHIPPED template.
- New rule (b): a warning for each archived finding marked `Open`.
- New rule (c): an error for an unprefixed citation of a finding ID that the citing spec does not
  define, with an allowlist for the existing ones.
- Unit tests for every new rule (a valid and an invalid case), a test that the SHIPPED template
  passes its own section rule, and the README / docstring update.

**Out of scope:**
- Porting the change to the template repository (follow-up F-01, at ship).
- The 433 unprefixed citations whose ID also exists in the citing spec (a script cannot tell which
  of them mean another spec) and the 64 citations outside `archive/` in templates, ADRs and tests
  (follow-up F-02, at ship).
- A fixed status vocabulary for findings and follow-ups (finding I-01 below records the limitation).
- Accepting a list of IDs after a single prefix in rule (c) (follow-up F-03, at ship).
- Editing archived documents. Existing citations are not rewritten (user rule of 2026-11-05).
- Any change to `src/`, `resources/`, `notebooks/` or `databricks.yml`; no version bump.

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-63 | `check_specs.py` shall load every `.md` file directly inside each folder of `.claude/sdd/archive/` as an archived document: a phase document when its name is `<PHASE>_<FOLDER>.md` for a phase in BRAINSTORM, DEFINE, DESIGN, BUILD_REPORT, and a SHIPPED document when its name starts with `SHIPPED_` | Must |
| FR-64 | The current per-document rules (required sections, allowed status, no unfilled placeholders and a non-empty Self-Review past draft, DEFINE clarity gate and AC rows) shall apply to archived phase documents unchanged | Must |
| FR-65 | Traceability (DEFINE to DESIGN Test Strategy to BUILD_REPORT evidence, Complete without failing criteria) shall apply to archived phase documents grouped by archive folder; documents in `features/` and `reports/` keep their current grouping and are never grouped with an archive folder | Must |
| FR-66 | Rule (a), error: an archived phase document shall have its phase's final status (BRAINSTORM `Ready for Define`, DEFINE `Ready for Design`, DESIGN `Ready for Build`, BUILD_REPORT `Complete`); each archive folder shall contain exactly one SHIPPED document, with status `Shipped`; any other `.md` file name in an archive folder is an error | Must |
| FR-67 | SHIPPED documents, error: the file name shall be `SHIPPED_YYYY-MM-DD.md` with a valid calendar date; the Metadata row `**Shipped on**` shall equal that date; every section of `.claude/sdd/templates/SHIPPED_TEMPLATE.md` shall be present, including `Self-Review` (added to the template by this feature, D-77), except that `Pull Requests and Branches` is required only when the file-name date is on or after the cut-off date (D-73); `## Self-Review` shall not be empty; no unfilled placeholders | Must |
| FR-68 | Rule (b), warning only: each row of the `## Issues & Follow-ups` table of an archived BUILD_REPORT whose Follow-up cell, with markdown emphasis removed, starts with the word `Open` shall produce one warning naming the spec, the ID and the severity; it never changes the exit code | Must |
| FR-69 | Rule (c), error: in an archived document, a citation `I-NN` or `F-NN` (outside fenced code, and not the first cell of a table row) whose ID is not the first cell of any table row in a document of the same archive folder shall be written as `<SPEC> <ID>`, where `<SPEC>` is the name of an archive folder followed by one space | Must |
| FR-70 | Allowlist, error: a repository file lists the existing rule (c) violations as entries of file, ID and count; for each file and ID, the measured number of rule (c) violations shall equal the entry's count; a violation without an entry, a count that differs in either direction, an entry that matches nothing, and an unreadable or malformed allowlist are errors that name the entry or the file | Must |
| FR-71 | The exit code shall stay 0 without errors and 1 with errors; warnings do not fail; the summary line counts archived documents | Must |
| FR-72 | The script docstring and the check list in `.claude/sdd/README.md` shall describe the archive rules, the allowlist and the cut-off | Should |
| FR-73 | A permanent unit test shall copy every document of `.claude/sdd/features/` and `.claude/sdd/reports/` that is in its phase's final status into a temporary `archive/<FEATURE>/`, add a generated valid SHIPPED document, and run every archive rule on it with an empty allowlist, expecting 0 errors | Must |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-35 | Reproducibility | The result depends only on file paths and file contents: never on file modification times, the clock, the locale or git metadata. Tested by changing the modification times of the fixtures (AC-112) |
| NFR-36 | Dependencies | The new rules use the Python standard library only; the hook keeps `additional_dependencies: [pyyaml>=6]` and nothing else |
| NFR-37 | Performance | A full run on the current repository finishes in under 5 s on the development machine (measured in the build and recorded in the BUILD_REPORT) |
| NFR-38 | Messages | Every new error or warning names the file (or allowlist entry), the rule and the value found, for example the ID and the actual and expected counts |

---

## Data Contracts

No dataset or message is produced or consumed. The one new repository file is the citation
allowlist (format in the DESIGN); it is read only by `check_specs.py`.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| Citation allowlist (repository file) | SPEC_ARCHIVE_GATES | One entry per archived file and cited ID | file, ID | Changed only by a reviewed PR | Inline in the DESIGN (Data Model) |

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-107 | The repository after the build, with the allowlist of 12 entries | `python scripts/check_specs.py` runs | Exit code 0 and 0 errors (asserted by a unit test on the repository root). Recorded in the BUILD_REPORT from the build run: exactly 2 warnings, for INGESTION_GUARD I-11 and INGESTION_GUARD I-12, and a summary that counts every `.md` file under `archive/` (23 at build time) in addition to the others. The warning and document counts change when later features ship, so they are build evidence, not asserted |
| AC-108 | A fixture archive folder with valid documents, and copies where an archived DEFINE lacks a required section or has a placeholder | The checker runs on each | The valid folder gives no error; each broken copy gives one error naming the file and the rule |
| AC-109 | Fixtures with the same feature name in `features/` and in an archive folder, and an archived DESIGN whose Test Strategy lacks an AC of its archived DEFINE | The checker runs | The `features/` and archive documents are not cross-checked; the missing AC in the archive folder is an error |
| AC-110 | A valid archive folder; copies with a DESIGN in `Draft`, no SHIPPED document, two SHIPPED documents, a SHIPPED status other than `Shipped`, and a misnamed file | The checker runs on each | The valid folder passes; each copy gives an error naming the folder or file and rule (a) |
| AC-111 | SHIPPED fixtures dated `SHIPPED_2026-11-04.md` without `## Pull Requests and Branches`, `SHIPPED_2026-11-05.md` without it, and `SHIPPED_2026-11-05.md` with it | The checker runs on each | The first passes, the second gives a missing-section error, the third passes |
| AC-112 | The three fixtures of AC-111 | Their modification times are set to 2026-01-01 and to 2030-01-01 and the checker runs after each | The errors and warnings are identical to AC-111 in both runs (NFR-35) |
| AC-113 | SHIPPED fixtures named `SHIPPED_2026-13-40.md` and `SHIPPED_final.md`, one whose `**Shipped on**` differs from its file-name date, one with an unfilled placeholder, one without `## Self-Review` and one with an empty `## Self-Review` | The checker runs on each | Each gives one error naming the file and the reason |
| AC-114 | An archived BUILD_REPORT with Follow-up cells `Open: ...`, `**Open**, ...`, `**Closed 2026-11-05**: ...` and `Watch the margin ...` | The checker runs | Exactly 2 warnings (the two `Open` rows) with spec, ID and severity; exit code 0 (the `Watch` row gives none: finding I-01) |
| AC-115 | Archive fixtures citing a foreign ID without a prefix, the same with `<SPEC> ` before it, an ID defined in the same folder, a foreign ID inside fenced code, and a foreign ID after a word that is not an archive folder name | The checker runs with an empty allowlist | Only the unprefixed foreign ID and the one after the unknown word are errors, each naming the file and the ID |
| AC-116 | A fixture with 3 unprefixed foreign citations of one ID in one file | The allowlist entry has count 3, then 4, then 2; then the entry is kept and the citations are removed; then the entry is removed while the citations remain; then the allowlist is missing and then malformed | Count 3 passes; counts 4 and 2, the stale entry, the missing entry, the missing file and the malformed file each give an error naming the entry or the file |
| AC-117 | The five templates, including `.claude/sdd/templates/SHIPPED_TEMPLATE.md` copied as a SHIPPED document dated on or after the cut-off, as `test_all_templates_have_required_sections` already does for the other four | The checker runs | No missing-section error for any of the five; the SHIPPED template's `##` headings equal the SHIPPED section list and include `Self-Review` |
| AC-118 | The script docstring and `.claude/sdd/README.md` after the build | A unit test reads them | Both mention `archive/`, the allowlist file name and the cut-off date |
| AC-119 | The repository's `features/` and `reports/` documents in their phase's final status (at this PR: DEFINE and DESIGN of SPEC_ARCHIVE_GATES) | The test copies them into a temporary `archive/<FEATURE>/` per feature, adds a generated SHIPPED document (fixed file-name date after the cut-off, every SHIPPED section, status `Shipped`), uses an empty allowlist and runs the checker on that root | 0 errors; documents not yet in their final status are left out, so a draft in `features/` never fails the test; when no document qualifies the test is skipped with that reason |

---

## Decisions and Open Items

### Decided by the user

| ID | Decision | Source |
|---|---|---|
| D-66 | Small feature cycle without a BRAINSTORM, delivered in three PRs (`spec/`, `build/`, `ship/`), as #32, #33 and #34 | User, 2026-11-05 |
| D-67 | `Ready for Build` is the final status of a DESIGN; rule (a) uses the gate statuses of `.claude/sdd/README.md:20-24` | User, 2026-11-05 |
| D-68 | Rule (b) is a warning, never an error; a fixed status vocabulary is out of scope (finding I-01) | User, 2026-11-05 |
| D-69 | Rule (c) uses an allowlist keyed by file, ID and count; an entry that no longer matches is an error, not a warning | User, 2026-11-05 |
| D-70 | SHIPPED becomes a checked phase with a cut-off for `Pull Requests and Branches`; the cut-off must not use the file system's modification time, and a test proves it (AC-112) | User, 2026-11-05 |
| D-71 | Out of scope, recorded as follow-ups at ship: the template-repository port (F-01); the 433 ambiguous and 64 outside-archive citations (F-02) | User, 2026-11-05 |
| D-76 | The allowlist starts with 12 entries / 17 citations (Q-27) | User, 2026-11-05 |
| D-77 | `## Self-Review` is required in SHIPPED documents; the build adds it to the SHIPPED template, and a test proves that the template passes its own section rule (Q-28) | User, 2026-11-05 |
| D-78 | Follow-up F-03, at ship: "citations in a list after a single prefix (for example INGESTION_GUARD F-02, F-03) count as violations; evaluate accepting lists in rule (c) if the pattern recurs" | User, 2026-11-05 |

### Derived in this phase (not yet confirmed by the user)

| ID | Decision | Reason |
|---|---|---|
| D-72 | The cut-off reads the date from the file name `SHIPPED_YYYY-MM-DD.md`, and FR-67 requires the `**Shipped on**` Metadata field to equal it | The name is always present and already the convention (`.claude/sdd/README.md:11`); in all 5 SHIPPED documents the field equals the file-name date (measured 2026-11-05), so the consistency rule adds no violation and makes the field usable as a cross-check. A date field alone could be missing or mistyped without a rule |
| D-73 | Cut-off date 2026-11-05 | `## Pull Requests and Branches` entered the SHIPPED template that day (PR #37, merge a4d018a). The 5 existing SHIPPED documents are dated 2026-10-20 to 2026-11-04, so none needs the section |
| D-74 | A citation counts as prefixed only in the canonical form `<SPEC> <ID>` (one space) | Measurable without reading prose. Other forms that do name the spec, such as one spec name before a list of several IDs, or an ID followed by "rule of" and the spec name, are frozen in the allowlist, not parsed |
| D-75 | An ID is defined in a spec when it is the first cell of a table row in any document of its archive folder | Covers BUILD_REPORT findings, SHIPPED follow-ups and the profiling findings (`F-NN`) of BRAINSTORM documents (14, 13 and 18 rows), which reuse the `F-` prefix (`scripts/profile_data.py:1`) |
| D-79 | The self-test (FR-73, AC-119) copies only documents in their final status, adds one generated SHIPPED document, and uses an empty allowlist | A draft in `features/` is normal during `/define` and must not turn CI red; rule (a) needs one SHIPPED per folder; the real allowlist names files that are not in the temporary root, so its entries would be stale |
| D-80 | Findings and follow-ups that this spec announces before its BUILD_REPORT and SHIPPED exist are listed in a table here (Pre-registered Findings and Follow-ups) | Under D-75 a table row defines the ID in the spec's own folder, so these IDs are not foreign citations in the AC-119 self-test or once archived; the BUILD_REPORT and SHIPPED repeat them with their outcome |

### Questions for the user

| ID | Question |
|---|---|
| Q-27 | **The allowlist count differs from the discovery report.** Discovery reported 14 unprefixed foreign citations. Under the exact FR-69 definition the count is 17 citations in 12 file-and-ID entries: 3 more inside SHIPPED follow-up rows that list several IDs after a single spec prefix, where only the first ID carries it, and 1 fewer because `DESIGN_INGESTION_GUARD.md:361` is inside fenced code. Is the allowlist of 12 entries / 17 citations approved? **Answered 2026-11-05: yes (D-76); the list pattern becomes follow-up F-03 (D-78).** |
| Q-28 | The SHIPPED template has no `## Self-Review`, although golden rule 6 asks for one in every phase document and all 5 SHIPPED documents have one. Leave it out of the required SHIPPED sections here, or add it to the template and the rule? **Answered 2026-11-05: required, and added to the template (D-77).** |

---

## Pre-registered Findings and Follow-ups

Announced now (D-80), recorded with their outcome in the BUILD_REPORT (finding) and the SHIPPED
document (follow-ups).

| ID | Kind | Statement | Recorded in |
|---|---|---|---|
| I-01 | Finding | The status of a finding or follow-up is not machine-readable; findings that are effectively open but do not start with `Open` (for example AC97_TIMING_EVIDENCE I-13, "Watch the margin in later AC-97 runs") produce no warning (D-68) | BUILD_REPORT |
| F-01 | Follow-up | Port the change to the template repository (D-71) | SHIPPED |
| F-02 | Follow-up | The 433 unprefixed citations whose ID also exists in the citing spec, and the 64 citations outside `archive/` (D-71) | SHIPPED |
| F-03 | Follow-up | Citations in a list after a single prefix (for example INGESTION_GUARD F-02, F-03) count as violations; evaluate accepting lists in rule (c) if the pattern recurs (D-78) | SHIPPED |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-17 | Constraint | No archived document is edited by this feature, and existing citations are not rewritten | Yes (user rule, 2026-11-05) |
| C-18 | Constraint | `check_specs.py` stays one script run as `python scripts/check_specs.py` by the hook and by CI, with the same arguments | Yes (`.pre-commit-config.yaml:28`, `.github/workflows/ci.yml:33`) |
| C-19 | Constraint | The template repository is separate; this project changes only its own copy | Yes |
| A-37 | Assumption | The current rules give 0 errors and 0 warnings on the 18 archived phase documents | Yes: discovery run of `check_doc` and `check_traceability` over `archive/`, 2026-11-05 |
| A-38 | Assumption | Every archived file is named `<PHASE>_<FOLDER>.md` or `SHIPPED_YYYY-MM-DD.md`, and every folder has one SHIPPED document with status `Shipped` | Yes: listing and status grep, 2026-11-05 (5 folders, 23 files) |
| A-39 | Assumption | The 5 SHIPPED documents have every template section except `Pull Requests and Branches` | Yes: section comparison, 2026-11-05 |
| A-40 | Assumption | The hook already runs when an archived document changes | Yes: `files: ^(\.claude/sdd/|docs/adr/|docs/contracts/)` (`.pre-commit-config.yaml:32`) |
| A-41 | Assumption | All 5 SHIPPED documents have a non-empty `## Self-Review` as their last section | Yes: section read, 2026-11-05 (1,022 to 1,375 characters each) |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Measured gap with file and line references |
| Users | 3 | Author, reviewer, citing agent, template maintainer |
| Scope | 3 | In and out of scope set by the user's decisions |
| Acceptance criteria | 3 | Each rule has a valid and an invalid case; AC-107 fixes the expected totals |
| Constraints | 3 | Q-27 and Q-28 answered by the user (D-76, D-77) |
| **Total** | **15/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:** Rule (c) sees only citations of IDs that the citing spec does not define; an
  unprefixed citation that means another spec but whose ID also exists locally is invisible (the 433
  in F-02). Rule (b) depends on the word `Open` (finding I-01).
- **Risks:** The allowlist can freeze a real mistake; the exact-count rule makes any later edit of
  an allowlisted file fail until the entry is updated, which is the intent but adds friction to
  `/iterate` on archived documents.
- **What I would do differently:** Measure with the exact rule definition before reporting a count
  (Q-27: the discovery said 14, the rule gives 17).
- **Next improvement:** After this ships, a status vocabulary for findings would turn rule (b) into
  a reliable gate.

---

## Next Step

`/design .claude/sdd/features/DEFINE_SPEC_ARCHIVE_GATES.md`

---

## Change Log

| Date | Change | Reason | Impact |
|---|---|---|---|
| 2026-11-05 | First version, Ready for Design | Discovery and user decisions of 2026-11-05 | DESIGN to follow |
| 2026-11-05 | Q-27 and Q-28 answered: D-76 (allowlist 12 / 17), D-77 (`## Self-Review` required in SHIPPED and added to the template; FR-67, AC-113, AC-117, scope), D-78 (follow-up F-03 on lists after one prefix); A-41 added; clarity 15/15 | User review of PR #40 | DESIGN updated in the same commit (manifest gains the SHIPPED template; AC-113 and AC-117 tests) |
| 2026-11-05 | FR-73 and AC-119: permanent self-test that archives the final-status documents of `features/` and `reports/` in a temporary root and expects 0 errors (D-79); pre-registered findings and follow-ups moved into a table (D-80), replacing the I-01 paragraph of the Self-Review | User review of PR #40 | DESIGN Test Strategy gains AC-119; build evidence section added |
