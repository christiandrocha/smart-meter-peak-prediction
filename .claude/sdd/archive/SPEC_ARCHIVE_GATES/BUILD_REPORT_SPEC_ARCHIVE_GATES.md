# BUILD REPORT: Spec Archive Gates

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SPEC_ARCHIVE_GATES |
| **Date** | 2026-11-05 |
| **Source** | DESIGN_SPEC_ARCHIVE_GATES.md (Ready for Build; `/iterate` commit 306c171 during this build) |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

---

## Summary

`scripts/check_specs.py` now checks `.claude/sdd/archive/`: the existing rules per archive folder,
final statuses and one SHIPPED document per folder (rule a), SHIPPED documents as a phase with the
2026-11-05 cut-off, a warning for each `Open` finding (rule b), and unprefixed citations of IDs the
citing spec does not define (rule c), compared exactly with `.claude/sdd/citation_allowlist.json`
(12 entries, 17 citations). The SHIPPED template gained `## Self-Review`, the SDD README describes
the checks, and 13 acceptance criteria (AC-107 to AC-119) have unit tests. The build stopped once
on two design gaps, which the user resolved through an `/iterate` (commit 306c171) before any code.

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | `scripts/check_specs.py` | Modified (commit d5da957) | `ruff check`, `ruff format --check`; AC-107 to AC-116, AC-118, AC-119 tests; run on the repository (Build Evidence) |
| 2 | `.claude/sdd/citation_allowlist.json` | Created (commit d5da957) | Transcribed by hand from the DESIGN Data Model, not generated; the run without it listed exactly those 12 entries and 17 citations; AC-107 |
| 3 | `.claude/sdd/templates/SHIPPED_TEMPLATE.md` | Modified (commit 237eb0f) | AC-117 (both tests) |
| 4 | `tests/test_check_specs.py` | Modified (commit c18bb0a) | 63 tests in the file pass, 43 of them for AC-107 to AC-119 (Acceptance Criteria Evidence) |
| 5 | `.claude/sdd/README.md` | Modified (commit 877e4a6) | AC-118 |
| 6 | `.claude/sdd/reports/BUILD_REPORT_SPEC_ARCHIVE_GATES.md` | Created | `check_specs.py` (traceability of this report); AC-119 includes it once `Complete` |

Not modified: every file under `.claude/sdd/archive/` (C-17), the DEFINE and DESIGN except the
approved `/iterate` commit 306c171, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.

---

## Acceptance Criteria Evidence

All tests are in `tests/test_check_specs.py` and passed in the build run of 2026-11-05.

| AC | Result | Evidence |
|---|---|---|
| AC-107 | Pass | `test_ac107_repository_has_no_errors`; repository run: 0 errors, 2 warnings, 51 documents (Build Evidence) |
| AC-108 | Pass | `test_ac108_archived_phase_doc_rules`: valid folder 0 errors; missing `## Scope` and an unfilled placeholder give one error each, named `FEAT/DEFINE_FEAT.md` |
| AC-109 | Pass | `test_ac109_traceability_per_archive_folder`: the `features/` pair with AC-03 and the archive pair are checked apart; the only error is `FEAT/DESIGN_FEAT.md: acceptance criteria without a test: AC-02` |
| AC-110 | Pass | `test_ac110_final_status_and_one_shipped_per_folder`, 6 cases: valid passes; DESIGN `Draft`, no SHIPPED, two SHIPPED, SHIPPED `Draft`, `NOTES.md` each give one `(rule a)` error |
| AC-111 | Pass | `test_ac111_shipped_cutoff_by_file_name_date`, 3 cases: 2026-11-04 without the section passes; 2026-11-05 without it fails; 2026-11-05 with it passes |
| AC-112 | Pass | `test_ac112_result_does_not_depend_on_mtime`: errors and warnings identical with file times set to 2026-01-01 and 2030-01-01 |
| AC-113 | Pass | `test_ac113_shipped_name_date_placeholders_and_self_review`, 7 cases: bad date, bad name, `Shipped on` mismatch, placeholder on the cut-off, no Self-Review and empty Self-Review give one error each; a placeholder before the cut-off gives none (DEFINE D-81) |
| AC-114 | Pass | `test_ac114_open_findings_warn_only`: exactly the 2 `Open` rows warn, with spec, ID and severity; 0 errors; `main()` returns 0 |
| AC-115 | Pass | `test_ac115_unprefixed_foreign_citations`, 10 cases: unprefixed foreign ID, unknown word, blank line and CRLF blank line fail; prefixed, own ID, fenced, soft wrap, tab and CRLF soft wrap pass |
| AC-116 | Pass | `test_ac116_allowlist_exact_counts`, 7 cases: exact count passes; count 4, count 2, stale entry, no entry, no file and malformed JSON each give the named error |
| AC-117 | Pass | `test_all_templates_have_required_sections` (all five templates, SHIPPED on the cut-off date) and `test_ac117_shipped_template_sections_equal_the_rule` (headings equal `SHIPPED_SECTIONS`, `Self-Review` last) |
| AC-118 | Pass | `test_ac118_docs_describe_the_archive_rules`: docstring and README name `archive/`, `citation_allowlist.json` and `2026-11-05` |
| AC-119 | Pass | `test_ac119_final_status_feature_docs_pass_the_archive_rules` (0 errors; document count in Build Evidence) and `test_ac119_folder_name_collision_fails_without_merging` (the safeguard refuses an existing folder and leaves the archived document unchanged) |

Mutation check (scratch edits of `check_specs.py`, restored from git afterwards): anchoring G-37
with `$` instead of `\Z` fails the two blank-line cases of AC-115; checking SHIPPED placeholders
before the cut-off fails AC-107, AC-113 and AC-119; an "at most" allowlist count fails AC-116.

---

## Build Evidence

Required by the DESIGN section "Build Evidence" (`DESIGN_SPEC_ARCHIVE_GATES.md:183`). Dated
2026-11-05, build run on commit c18bb0a (17:21 UTC), repository root:

```text
WARN  INGESTION_GUARD/BUILD_REPORT_INGESTION_GUARD.md: open finding INGESTION_GUARD I-11 (Low) (rule b)
WARN  INGESTION_GUARD/BUILD_REPORT_INGESTION_GUARD.md: open finding INGESTION_GUARD I-12 (Low) (rule b)
51 document(s) checked, 0 error(s), 2 warning(s)
```

With this report in `reports/`, the same run counts 52 documents, with 0 errors and the same 2
warnings.

| Measure | Value on 2026-11-05 |
|---|---|
| Warnings | 2: INGESTION_GUARD I-11 (Low) and INGESTION_GUARD I-12 (Low) |
| Archived documents counted | 23: 18 phase documents and 5 SHIPPED documents (51 in total, 28 outside the archive) |
| Allowlist | 12 entries, 17 citations |
| Documents added by the AC-119 self-test | 3, from the run on the completed report: the DEFINE, the DESIGN and this BUILD_REPORT of SPEC_ARCHIVE_GATES (plus 1 generated SHIPPED document). With the report still in progress it was 2 |
| Runtime of `check_specs.py` | 0.15 s (NFR-37: under 5 s) |

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `ruff check . && ruff format --check .` | `All checks passed!`; all files already formatted |
| Tests | `pytest` | 605 passed, 90 deselected, 1 xfailed (INGESTION_GUARD I-12, expected), exit 0, on c18bb0a plus this report |
| Spec tests | `pytest tests/test_check_specs.py -s` | 63 passed; `AC-119: added 3 document(s)`; rerun after the last edit of this report |
| Spec check | `python scripts/check_specs.py` | 52 documents, 0 errors, 2 warnings (INGESTION_GUARD I-11, INGESTION_GUARD I-12), exit 0 |
| Hooks | `pre-commit run --all-files` | All hooks passed |

---

## Build Decisions

| ID | Decision | Design reference |
|---|---|---|
| BD-01 | CRLF line ends between the prefix and the ID are handled by reading every document with `Path.read_text` (universal newlines), which turns CRLF into LF before G-37 runs; no separate normalization. AC-115 writes its CRLF fixtures with `write_bytes`: a CRLF soft wrap passes and a CRLF blank line fails. Checked before the build: on raw bytes the soft wrap would fail | G-37 (`DESIGN_SPEC_ARCHIVE_GATES.md:106`), AC-115 test (`:175`); user note of 2026-11-05 |
| BD-02 | The AC-119 self-test prints how many documents it added to the temporary archive, and that number goes into this report | AC-119 test and OD-35 (`DESIGN_SPEC_ARCHIVE_GATES.md:179`, `:124`); Build Evidence (`:183`); user note of 2026-11-05 |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| Placeholders in SHIPPED, AC-119 root | Placeholders always errors in SHIPPED; AC-119 with only the new folders and an empty allowlist | Placeholders only from the cut-off; AC-119 with the real archive and allowlist and a collision safeguard | Gap A and Gap B, found before any code (finding I-02) | Yes: commit 306c171, approved by the user |
| Commit order | Manifest 4 (tests) before 5 (README) | README committed before the tests | The AC-118 test reads the README; content unchanged | No (order only) |
| Missing and malformed allowlist | "error ... for a missing or malformed file when violations exist" (`DESIGN_SPEC_ARCHIVE_GATES.md:65`) | A missing file is an error only when rule (c) finds citations; a malformed file is always an error | DEFINE FR-70 (`DEFINE_SPEC_ARCHIVE_GATES.md:94`) lists a malformed allowlist as an error without a condition; roots without an archive must not need the file | No (reading of an ambiguous sentence; recorded here) |
| Prefix search window | "the text directly before it" (G-37) | The 80 characters before the citation are searched (`PREFIX_WINDOW`) | The longest folder name has 22 characters, so the window always holds a prefix and its separator | No |
| Extra test | One AC-119 test | A second test for the folder-collision safeguard, on the same helper | The safeguard (DEFINE D-79) needs a failing case | No |
| AC-119 count | Expected 2 documents at design time (Build Evidence) | 3 (Build Evidence) | This report becomes a final-status document once `Complete`, so the self-test adds it too | No (the DESIGN gave an expectation, not a rule) |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The status of a finding or follow-up is not machine-readable; findings that are effectively open but do not start with `Open` (for example AC97_TIMING_EVIDENCE I-13, "Watch the margin in later AC-97 runs") produce no warning (DEFINE D-68) | Low | Accepted for this spec; a status vocabulary is out of scope |
| I-02 | Two design gaps found at the start of the build, before any code: the SHIPPED placeholder rule hit two archived documents (Gap A), and the AC-119 root could not recognize any real spec prefix (Gap B) | Medium | Closed: `/iterate` commit 306c171 (options A1 and B1, user decision) |
| I-03 | Discovery measured sections, dates and Self-Review of the SHIPPED documents but not the placeholder rule, which caused Gap A | Low | Lesson for the ship: measure every rule that a new phase inherits before the DEFINE |
| F-01 | Port the change to the template repository | - | Recorded at ship (DEFINE pre-registered table) |
| F-02 | The 433 ambiguous citations and the 64 outside `archive/` | - | Recorded at ship |
| F-03 | Lists of IDs after a single prefix count as rule (c) violations | - | Recorded at ship |
| F-04 | Measure ignoring inline code spans in the placeholder rule | - | Recorded at ship |

---

## Self-Review

- **Weak points:** Rule (c) is a heuristic over prose and sees only IDs that the citing spec does
  not define. Rule (b) depends on the word `Open` (I-01). The allowlist freezes 17 citations.
- **Risks:** Any edit of one of the 9 allowlisted files must update its entry in the same change;
  the error names the entry and both counts. The AC-119 self-test depends on the real archive,
  so a broken archive fails both AC-107 and AC-119.
- **What I would do differently:** Measure every inherited rule on the real data before writing
  the DEFINE (I-03), which would have caught Gap A in discovery instead of at the build.
- **Next improvement:** Ship with follow-ups F-01 to F-04 and the lesson of I-03.

---

## Next Step

`/ship SPEC_ARCHIVE_GATES`
