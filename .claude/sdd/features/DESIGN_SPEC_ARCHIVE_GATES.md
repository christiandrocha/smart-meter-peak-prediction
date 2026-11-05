# DESIGN: Spec Archive Gates

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SPEC_ARCHIVE_GATES |
| **Date** | 2026-11-05 |
| **Author** | christiandrocha (with Claude Code) |
| **Source** | DEFINE_SPEC_ARCHIVE_GATES.md (Ready for Design, 2026-11-05) |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

---

## Overview

`scripts/check_specs.py` gains an archive pass. `run()` keeps today's checks of `features/`,
`reports/`, ADRs and contracts unchanged. It then loads every archive folder, applies the
existing per-document and traceability rules to the archived phase documents (grouped by folder),
checks SHIPPED documents as a new phase, and adds three rules: (a) final statuses and one SHIPPED
document per folder, (b) a warning for each `Open` finding, (c) unprefixed foreign citations,
compared exactly with a JSON allowlist that freezes the 17 existing ones. Everything is computed
from paths and file contents with the standard library, so the result never depends on
modification times (NFR-35, NFR-36).

---

## Architecture

```text
run(root)
 |- load_docs(root)            features/, reports/       (unchanged)
 |- check_doc / check_traceability                       (unchanged for these docs)
 |- check_adrs / check_contracts                         (unchanged)
 '- archive pass (new)
     load_archive(root) -> per folder: phase docs, SHIPPED docs, unknown names
       |- check_doc(phase doc)              FR-64  (existing rules)
       |- check_final_status(phase doc)     FR-66  rule (a)
       |- check_folder(folder)              FR-66  one SHIPPED, no unknown names
       |- check_shipped(SHIPPED doc)        FR-67  name, date, Shipped on, sections, cut-off
       |- check_traceability(folder docs)   FR-65  one folder at a time
       |- open_findings(BUILD_REPORT)       FR-68  rule (b): warnings only
       '- citation_violations(folder docs)  FR-69  rule (c): counts per (file, ID)
            compare with load_allowlist()   FR-70  exact counts; stale entry = error
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| `Doc.folder` (new optional field, default `None`) | Marks an archived document with its archive folder; `None` for `features/` and `reports/` | dataclass field | FR-63, FR-65 |
| `load_archive(root)` | For each folder directly under `.claude/sdd/archive/`, sorted: phase documents named `<PHASE>_<FOLDER>.md`, SHIPPED documents named `SHIPPED_*.md`, and the list of other `.md` names | `pathlib`, sorted listing | FR-63, FR-66 |
| `check_final_status(doc)` | Error when an archived phase document's status is not the `True` status of its phase in `PHASES` | existing `PHASES` map | FR-66 |
| `check_folder(folder, shipped, unknown)` | Error when a folder has 0 or more than 1 SHIPPED document, or any unknown `.md` name | - | FR-66 |
| `check_shipped(doc)` | Name `SHIPPED_YYYY-MM-DD.md` parsed with `datetime.date.fromisoformat`; status `Shipped`; `**Shipped on**` equal to the name date; `SHIPPED_SECTIONS` present (including `Self-Review`), with `Pull Requests and Branches` only from `SHIPPED_CUTOFF`; non-empty `## Self-Review`; no unfilled placeholders when the name date is on or after `SHIPPED_CUTOFF` (DEFINE D-81) | `re`, `datetime.date` | FR-67, NFR-35 |
| `check_traceability(docs)` | Unchanged logic; the archive pass calls it once per folder, so archived and active documents never meet | existing function | FR-65 |
| `open_findings(doc)` | Rows of `## Issues & Follow-ups` whose Follow-up cell, without `*`, `_` and backticks, starts with `Open`: one warning each, with spec, ID and severity | `re` | FR-68 |
| `citation_violations(folder docs, specs)` | Counter of unprefixed foreign `I-NN` / `F-NN` citations per (relative file path, ID) | `re`, `collections.Counter` | FR-69 |
| `load_allowlist(root)` and `check_citations(found, allowed)` | Read the JSON file; error for every (file, ID) whose found count differs from the entry, for every entry without a match, and for a missing or malformed file when violations exist | `json` | FR-70, NFR-38 |
| `_name(where)` | For an archived document, `<FOLDER>/<file name>`, because SHIPPED file names repeat across folders | - | NFR-38 |
| `main()` / summary | Unchanged exit codes; `checked` adds the archived documents | - | FR-71 |

---

## Data Model

No table or dataset. The one new file is the citation allowlist.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| `.claude/sdd/citation_allowlist.json` | Repository file | One entry per archived file and cited ID | (`file`, `id`) | - | JSON object with `version` (1) and `entries`, a list of objects with `file` (repo-relative POSIX path), `id` and `count`; entries sorted by file then ID; a duplicate (`file`, `id`) is an error |

Initial content, measured 2026-11-05 with the FR-69 definition: 12 entries, 17 citations. It is
kept in fenced code so that, once this DESIGN is archived, rule (c) does not read the listed IDs
as citations (G-34). Paths are under `.claude/sdd/archive/`.

```text
count  id     file
    1  F-10   AC97_TIMING_EVIDENCE/DEFINE_AC97_TIMING_EVIDENCE.md
    1  F-10   AC97_TIMING_EVIDENCE/SHIPPED_2026-11-04.md
    1  I-14   INGESTION_GUARD/DEFINE_INGESTION_GUARD.md
    1  I-14   INGESTION_GUARD/DESIGN_INGESTION_GUARD.md
    1  F-13   INGESTION_GUARD/SHIPPED_2026-11-04.md
    1  F-15   INGESTION_GUARD/SHIPPED_2026-11-04.md
    2  I-14   PEAK_MODEL/DESIGN_PEAK_MODEL.md
    5  F-14   PEAK_MODEL_CONCURRENCY/DEFINE_PEAK_MODEL_CONCURRENCY.md
    1  F-14   PEAK_MODEL_CONCURRENCY/DESIGN_PEAK_MODEL_CONCURRENCY.md
    1  I-14   PEAK_MODEL_CONCURRENCY/DESIGN_PEAK_MODEL_CONCURRENCY.md
    1  F-13   PEAK_MODEL_CONCURRENCY/SHIPPED_2026-10-22.md
    1  F-15   PEAK_MODEL_CONCURRENCY/SHIPPED_2026-10-22.md
```

### Parsing rules (guards)

| Rule | Where | Action | Source |
|---|---|---|---|
| G-34 Fenced code is replaced by blank lines before any search, so line positions are kept and code examples never count (as `Doc.body`, `scripts/check_specs.py:95-97`) | rules (b), (c), placeholders | ignore | FR-69 |
| G-35 A citation is `(?<![\w-])(I\|F)-\d+(?![\w-])`; the ID in the first cell of a table row (`^\|\s*ID\s*\|`) is a definition, not a citation | rule (c) | ignore definitions | FR-69, D-75 |
| G-36 Defined IDs of a folder are the first cells of table rows in all of its `.md` files | rule (c) | ignore defined IDs | D-75 |
| G-37 A citation is prefixed when the text directly before it is an archive folder name and a separator of spaces or tabs with at most one line break: `\b<SPEC>(?:[ \t]+\|[ \t]*\n[ \t]*)\Z` on the text before the ID. Anchor with `\Z`, not `$`: in Python `$` also matches before a final newline, so `<SPEC>` followed by a blank line would wrongly pass (seen in the measurement of 2026-11-05) | rule (c) | ignore prefixed | D-74 |
| G-38 Dates come only from the file name, parsed with `date.fromisoformat`; `os.stat` and the clock are never read | SHIPPED | error on an invalid date | NFR-35, D-72 |
| G-39 Allowlist paths are compared as repo-relative POSIX strings | allowlist | error on mismatch | FR-70 |

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| - | No new ADR. The change is internal to the SDD tooling, reversible, and recorded as D-66 to D-82 in the DEFINE and OD-29 to OD-35 below | - |

Design decisions:

| ID | Decision | Reason |
|---|---|---|
| OD-29 | Hard-code `SHIPPED_SECTIONS` in the script instead of reading the template at run time: the nine template sections plus `Self-Review` | Tests run on `tmp_path` roots without templates; AC-117 checks that the template and the list agree, so they cannot drift silently |
| OD-34 | `## Self-Review` goes last in the SHIPPED template, after `## Archived Documents` | All 5 SHIPPED documents already have it as their last section (DEFINE A-41); golden rule 6 says every phase document ends with one |
| OD-35 | The AC-119 test copies the real archive (`shutil.copytree`) and the real allowlist into `tmp_path`, then adds each qualifying feature as a new folder with a SHIPPED document built from `SHIPPED_SECTIONS`, fixed file name `SHIPPED_2026-11-06.md` and short fixed text, instead of copying the template; before adding a folder it asserts that the name is not already in the copied archive (message names the folder) | The template has placeholders, which are errors in a `Shipped` document after the cut-off; a fixed date keeps the result independent of the clock (NFR-35) and after the cut-off, so every section is required. The real archive is needed because rule (c) recognizes a prefix only as an archive folder name (G-37); the real allowlist is needed because the copied archive keeps its 17 frozen citations (DEFINE D-79) |
| OD-30 | `SHIPPED_CUTOFF = date(2026, 11, 5)` as a constant next to `SHIPPED_SECTIONS` | D-73; a constant is visible in review and documented by FR-72 |
| OD-31 | Archive pass in the same `run()` and the same exit code; no flag | C-18: the hook and CI call the script without arguments |
| OD-32 | Allowlist in JSON at `.claude/sdd/citation_allowlist.json` | Standard library only (NFR-36); inside `.claude/sdd/`, so an edit triggers the hook (`.pre-commit-config.yaml:32`) |
| OD-33 | Exact count per (file, ID), not "at most" | D-69: a lower count means a frozen citation changed, so the entry must be updated in the same PR, which keeps the allowlist true |

---

## Delivery Plan

| PR | Branch | Content |
|---|---|---|
| 1 | `spec/spec-archive-gates` | This DESIGN and the DEFINE (no code) |
| 2 | `build/spec-archive-gates` | File Manifest 1 to 6 |
| 3 | `ship/spec-archive-gates` | Archive the four documents, SHIPPED with follow-ups F-01, F-02, F-03 and F-04, CHANGELOG |

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom.

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | `scripts/check_specs.py` | Modify | Archive pass, rules (a), (b), (c), SHIPPED phase, allowlist comparison, docstring (FR-63 to FR-72) | build-agent | - |
| 2 | `.claude/sdd/citation_allowlist.json` | Create | The 12 entries of the Data Model | build-agent | 1 |
| 3 | `.claude/sdd/templates/SHIPPED_TEMPLATE.md` | Modify | Add `## Self-Review` as the last section (D-77, OD-34) | build-agent | - |
| 4 | `tests/test_check_specs.py` | Modify | AC-107 to AC-119 (fixtures on `tmp_path`, one repository-root test, one self-test of `features/` and `reports/` as if archived); `test_all_templates_have_required_sections` gains the SHIPPED template (AC-117) | build-agent | 1, 2, 3 |
| 5 | `.claude/sdd/README.md` | Modify | Check list (`.claude/sdd/README.md:27`): archive rules, allowlist, cut-off, Self-Review in SHIPPED (FR-72) | build-agent | 1 |
| 6 | `.claude/sdd/reports/BUILD_REPORT_SPEC_ARCHIVE_GATES.md` | Create | Evidence for every AC, the dated build evidence of the section below, finding I-01 | build-agent | 1 to 5 |

Read and not modified: every file under `.claude/sdd/archive/` (C-17), `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`.

---

## Test Strategy

Every acceptance criterion from DEFINE appears here. All tests are unit tests in
`tests/test_check_specs.py`, run by plain `pytest` (no marker) and by CI.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-107 | Unit (repository) | `tests/test_check_specs.py::test_ac107_repository_has_no_errors` | `check_specs.run(ROOT).errors == []` on the real tree with the allowlist; the build run's full output (2 warnings, document count) is pasted into the BUILD_REPORT |
| AC-108 | Unit | `::test_ac108_archived_phase_doc_rules` | A valid archive fixture gives no error; copies without a section or with a placeholder give one error each, naming `<FOLDER>/<file>` |
| AC-109 | Unit | `::test_ac109_traceability_per_archive_folder` | Same feature name in `features/` and `archive/` is not cross-checked; an archived DESIGN missing an AC gives the "without a test" error |
| AC-110 | Unit (parametrized) | `::test_ac110_final_status_and_one_shipped_per_folder` | Valid folder passes; DESIGN `Draft`, no SHIPPED, two SHIPPED, SHIPPED status `Draft`, and an unknown file name each give a rule (a) error |
| AC-111 | Unit (parametrized) | `::test_ac111_shipped_cutoff_by_file_name_date` | 2026-11-04 without the section passes; 2026-11-05 without it fails; 2026-11-05 with it passes |
| AC-112 | Unit | `::test_ac112_result_does_not_depend_on_mtime` | `os.utime` sets the AC-111 fixtures to 2026-01-01 and then 2030-01-01; errors and warnings equal the AC-111 result both times |
| AC-113 | Unit (parametrized) | `::test_ac113_shipped_name_date_placeholders_and_self_review` | `SHIPPED_2026-13-40.md`, `SHIPPED_final.md`, a `**Shipped on**` mismatch, a placeholder in a document dated on or after the cut-off, a missing `## Self-Review` and an empty one each give one error; a placeholder in a document dated before the cut-off gives none (DEFINE D-81) |
| AC-114 | Unit | `::test_ac114_open_findings_warn_only` | Four rows give exactly 2 warnings (spec, ID, severity); errors empty; exit code of `main()` is 0 |
| AC-115 | Unit (parametrized) | `::test_ac115_unprefixed_foreign_citations` | With an empty allowlist only the unprefixed foreign ID, the one after an unknown word and the one after a blank line (`<SPEC>` then an empty line then the ID) are errors; `<SPEC>` then a line break and indentation, and `<SPEC>` then a tab, pass |
| AC-116 | Unit (parametrized) | `::test_ac116_allowlist_exact_counts` | Count 3 passes; 4, 2, stale entry, missing entry, missing file and malformed JSON each give an error naming the entry or file |
| AC-117 | Unit | `::test_all_templates_have_required_sections` (extended, named for AC-117 in its docstring) and `::test_ac117_shipped_template_sections_equal_the_rule` | All five templates, the SHIPPED one copied as `SHIPPED_2026-11-05.md` in an archive folder, give no missing-section error; the SHIPPED template's `##` headings equal `SHIPPED_SECTIONS`, with `Self-Review` last |
| AC-118 | Unit | `::test_ac118_docs_describe_the_archive_rules` | The script docstring and `.claude/sdd/README.md` both mention `archive/`, `citation_allowlist.json` and `2026-11-05` |
| AC-119 | Unit (repository, self-test) | `::test_ac119_final_status_feature_docs_pass_the_archive_rules` | Copies the real archive and `citation_allowlist.json` into `tmp_path`, adds each `features/` and `reports/` document whose status is its phase's final status as `archive/<FEATURE>/` with the generated SHIPPED document (OD-35), runs `check_specs.run(tmp_path)` and asserts `errors == []`; prints the number of documents it added (recorded in the BUILD_REPORT); fails with a message naming the folder when `<FEATURE>` already exists in the archive; `pytest.skip` with the reason when no document qualifies. At this PR it covers the DEFINE and DESIGN of SPEC_ARCHIVE_GATES, which is the manual check of PR #40 made permanent |

---

## Build Evidence

The BUILD_REPORT records, as dated evidence (the date of the build run and the commit it ran
on), the output of `python scripts/check_specs.py` on the repository:

- the number of warnings, and the ID and spec of each (expected at design time: 2, for
  INGESTION_GUARD I-11 and INGESTION_GUARD I-12);
- the number of documents under `.claude/sdd/archive/` that the run counted (expected at design
  time: 23, that is 18 phase documents and 5 SHIPPED documents), and the summary line;
- the number of allowlist entries and citations (12 and 17);
- the number of documents the AC-119 self-test added to its temporary archive (expected at design
  time: 2, the DEFINE and DESIGN of this feature, plus 1 generated SHIPPED document).

These counts change as later features ship and findings close, so they are evidence of the build
date, not values asserted by a test (AC-107 asserts only 0 errors).

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | None. The script runs in the "SDD spec gates" hook and in CI as today (C-18) |
| Scheduling and retries | Not applicable |
| Monitoring and alerting | A failing gate fails the hook and the CI `checks` job; warnings are printed with `WARN` |
| Secrets | None read or written |
| Cost | No cloud resource; NFR-37 caps the run at 5 s locally |
| Backfill / reprocessing | The first run covers the whole archive; the allowlist freezes the existing rule (c) cases |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| The allowlist freezes 17 citations that a reader may still misread | Low: they stay as they are (C-17) | F-02 at ship lists them with the 433 ambiguous ones |
| Exact counts make any edit of an allowlisted file fail until its entry is updated | Friction on `/iterate` of those 9 files | The error names the entry and both counts, so the fix is one line in the same PR |
| Rule (c) cannot see ambiguous citations whose ID also exists locally | The 433 stay unchecked | Out of scope (D-71, F-02); the memory rule asks agents to prefix |
| Rule (b) misses open findings that do not start with `Open` | False sense of completeness | Recorded as finding I-01; warnings never fail the build |
| A blank line between the spec name and the ID breaks the canonical prefix (G-37) | Rare in prose; a soft wrap (one line break) keeps the prefix, which covers the case that happened once while writing this DESIGN | The error names the file and ID; the AC-119 self-test catches it before the spec is archived; AC-115 tests the soft wrap, the tab and the blank line |
| Rule (c) counts IDs listed after a single prefix as violations | 3 of the 17 frozen citations are of this kind | Follow-up F-03: accept lists if the pattern recurs |
| The placeholder rule matches paths with the FEATURE token in braces quoted in prose, such as Template Feedback | New SHIPPED documents (dated on or after the cut-off) fail on such quotes | Follow-up F-04: measure ignoring inline code spans (DEFINE D-82); until then, write such paths without braces |
| The AC-119 self-test depends on the real archive and allowlist | A broken archive fails AC-119 as well as AC-107 | Intended: the self-test proves that the new folders fit the real archive; the failure message names the cause |
| A new archive folder with a non-standard file (for example notes) fails rule (a) | The ship PR must follow the naming | Matches the ship agent's own output; the error names the file |

---

## Open Items for the User

| ID | Item |
|---|---|
| Q-27 | **Answered 2026-11-05:** 12 entries / 17 citations approved (DEFINE D-76); lists after one prefix become follow-up F-03 (D-78) |
| Q-28 | **Answered 2026-11-05:** `## Self-Review` required in SHIPPED and added to the template (DEFINE D-77; manifest 3, OD-34) |

No open item remains for the build.

---

## Self-Review

- **Weak points:** The citation rule is a heuristic over prose. It catches only IDs that the
  citing spec does not define, and only the canonical prefix form counts.
- **Risks:** Hard-coding `SHIPPED_SECTIONS` and the cut-off ties the script to the current
  template; AC-117 catches drift, but the template repository will need the same change (F-01).
- **What I would do differently:** Settle the exact rule definition before discovery counts, so
  that the numbers in the report and in the allowlist agree from the start (Q-27).
- **Next improvement:** A status vocabulary for findings, so that rule (b) can become an error
  for archived features that still have open High findings.

---

## Next Step

`/build .claude/sdd/features/DESIGN_SPEC_ARCHIVE_GATES.md`

---

## Change Log

| Date | Change | Reason | Impact |
|---|---|---|---|
| 2026-11-05 | First version, Ready for Build | DEFINE_SPEC_ARCHIVE_GATES.md Ready for Design | Build in PR 2 after this PR is approved |
| 2026-11-05 | Q-27 and Q-28 answered: `SHIPPED_SECTIONS` gains `Self-Review` (OD-29, OD-34), manifest gains the SHIPPED template (now 6 files), AC-113 and AC-117 tests extended, F-03 in the delivery plan and the risks; open items closed | User review of PR #40 (DEFINE D-76 to D-78) | Status stays Ready for Build |
| 2026-11-05 | AC-119 self-test (OD-35) in the Test Strategy and manifest 4; new section Build Evidence (dated warning count, archive document count, allowlist size in the BUILD_REPORT) | User review of PR #40 (DEFINE FR-73, D-79, D-80) | Status stays Ready for Build |
| 2026-11-05 | G-37 accepts a soft wrap (whitespace with at most one line break) between `<SPEC>` and the ID, anchored with `\Z`; risk row and AC-115 test updated | User review of PR #40 (DEFINE FR-69, D-74, AC-115) | Allowlist unchanged: 12 entries / 17 citations; status stays Ready for Build |
| 2026-11-05 | `/iterate` during the build. Gap A (option A1): `check_shipped` applies the placeholder rule only from `SHIPPED_CUTOFF`; AC-113 test gains the before-cut-off case; risk row and follow-up F-04 in the delivery plan. Gap B (option B1): AC-119 copies the real archive and the real allowlist, fails on a folder-name collision and prints the number of documents it added (OD-35, Test Strategy, Build Evidence) | Build stopped on two gaps (DEFINE D-79, D-81, D-82) | Status stays Ready for Build; the build resumes after this commit |
