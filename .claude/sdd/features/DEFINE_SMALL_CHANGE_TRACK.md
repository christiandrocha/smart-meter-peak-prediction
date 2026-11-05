# DEFINE: Small Change Track

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SMALL_CHANGE_TRACK |
| **Date** | 2026-11-05 |
| **Author** | christiandrocha (with Claude Code) |
| **Source** | SDD process retrospective of 2026-11-05 (Step 1), measured on `main` 0a9b26b; no BRAINSTORM: small feature cycle, as SPEC_ARCHIVE_GATES |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

---

## Problem Statement

Every change to tooling or process documents either goes through the full four-document cycle or
through no spec at all. Of the 8 PRs from #35 to #42, 3 (#35, #36, #38) changed no production
file, contract, ADR, shipped design, gate or live test, and were run as single PRs with no spec
document, so nothing checked their requirements or evidence. Separately, `scripts/check_specs.py`
loads only files whose name starts with a phase prefix (`scripts/check_specs.py:149`, loop over
`features/` and `reports/`): any other `.md` there is ignored without a warning, so a broken
document with an invalid status, a placeholder and no sections passes with 0 errors (prototype
run of 2026-11-05).

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| Author of a small tooling or process change | One document instead of four, with the same evidence discipline | `CHANGE_<FEATURE>.md` from the new template |
| Reviewer | Knows the change was eligible for the short track and has evidence on a named commit | The Eligibility and Evidence sections, checked by `check_specs.py` |
| Author of any spec document | A misnamed document in `features/` or `reports/` fails instead of being skipped | `check_specs.py` error |
| Template repository maintainer | The same track in new projects | Follow-up F-02 |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| A short, checked track for eligible changes | A valid CHANGE document passes and an invalid one fails, rule by rule | Every rule has a valid and an invalid test case |
| No silently skipped documents | Unrecognized `.md` names in `features/` and `reports/` | Error for each; 0 today (measured 2026-11-05: both folders hold only `.gitkeep`) |
| No red CI on day one | Errors on the real repository after the build | 0 |

---

## Scope

**In scope:**
- An error for every `.md` file directly in `features/` or `reports/` whose name does not start
  with a phase prefix.
- A new phase `CHANGE`: one document `CHANGE_<FEATURE>.md` that replaces DEFINE, DESIGN,
  BUILD_REPORT and SHIPPED for eligible changes, with the eligibility criteria E1 to E8 below.
- An explicit final status per phase.
- Archive folders that hold a single `Complete` CHANGE document, with no SHIPPED document.
- Rules (b) and (c) of SPEC_ARCHIVE_GATES applied to archived CHANGE documents.
- The CHANGE template, the AC-119 self-test of SPEC_ARCHIVE_GATES extended to CHANGE documents,
  and the README, `docs/conventions/git.md` and `CLAUDE.md` lines that describe the track.

**Out of scope:**
- Checking E1 to E8 against the actual `git diff` of a PR; the document records the
  `git diff --name-only` output as evidence (follow-up F-01).
- The follow-up task template (retrospective Step 2) and any change to a confirmation rule
  (retrospective Step 3).
- The template repository port (follow-up F-02, together with SPEC_ARCHIVE_GATES F-01).
- Editing archived documents; no change to `src/`, `resources/`, `notebooks/`, `pipelines/` or
  `databricks.yml`; no version bump.

### Eligibility criteria for the CHANGE track

A change is eligible only when every criterion holds for the files the PR changes.

| ID | Criterion | How it is shown |
|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | `git diff --name-only origin/main...HEAD` |
| E2 | No contract change: nothing under `docs/contracts/` | Same output |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` | `git diff --name-status origin/main...HEAD` |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`); annotating archived BUILD_REPORT or SHIPPED rows is allowed | Same output |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read | Same output |
| E6 | No change under `tests/integration/` (no live evidence needed) | Same output |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change | `git diff origin/main...HEAD -- pyproject.toml` |
| E8 | No weakening of an agent rule. Scope: `docs/conventions/git.md` and the rules for agents in `CLAUDE.md` (the Git and PR rules and any rule about destructive commands or confirmation; today golden rule 8, `CLAUDE.md:37-41`). In that scope the change must not remove a rule; replace "requires confirmation" by "does not", or narrow what needs confirmation; widen the list of commands or actions allowed without confirmation; or weaken a check (for example stop requiring a state read, an exit code or an `ls-remote`). It is eligible only if it adds rules, raises requirements, or fixes wording without changing the effect. In doubt, it is not eligible | The E8 evidence cites the diff of the affected rules (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`), or states that the scope is untouched |

Measured on #35 to #42 (retrospective, 2026-11-05): E1 to E7 hold for #35, #36 and #38 only.

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-74 | Every `.md` file directly in `.claude/sdd/features/` or `.claude/sdd/reports/` whose name does not start with a known phase prefix followed by `_` shall be an error naming the file; other files (such as `.gitkeep`) are ignored | Must |
| FR-75 | A new phase `CHANGE` shall be recognized for `CHANGE_<FEATURE>.md`, with the required sections Metadata, Problem Statement, Eligibility, Scope, Acceptance Criteria, Test Strategy, File Manifest, Evidence, Issues & Follow-ups and Self-Review, and the statuses `Draft`, `Ready for Build` and `Complete`; past `Draft`, the existing placeholder and non-empty Self-Review rules apply | Must |
| FR-76 | The final status of each phase shall be stated explicitly: BRAINSTORM `Ready for Define`, DEFINE `Ready for Design`, DESIGN `Ready for Build`, BUILD_REPORT `Complete`, CHANGE `Complete` | Must |
| FR-77 | Past `Draft`, the Eligibility section of a CHANGE document shall have exactly one row for each of E1 to E8, each with the result `Yes` and a non-empty evidence cell; a missing row, a duplicate row, any other result or an empty evidence cell is an error naming the criterion | Must |
| FR-78 | In a CHANGE document past `Draft`, every AC of Acceptance Criteria shall appear in Test Strategy; when `Complete`, every AC shall also appear in Evidence, no Evidence row shall start with `Fail`, and the Evidence section shall name the commit the evidence was generated on (`Evidence commit` followed by a hexadecimal SHA of 7 to 40 characters) | Must |
| FR-79 | An archive folder that contains `CHANGE_<FOLDER>.md` shall contain no other `.md` file and no SHIPPED document, and its CHANGE document shall be `Complete` (rule a); every other archive folder keeps the SPEC_ARCHIVE_GATES rule (a) | Must |
| FR-80 | Rule (b) shall warn for `Open` rows of the `## Issues & Follow-ups` section of archived CHANGE documents, and rule (c) shall read archived CHANGE documents, as for BUILD_REPORT documents | Must |
| FR-81 | `.claude/sdd/templates/CHANGE_TEMPLATE.md` shall exist with exactly the CHANGE sections and the Eligibility rows E1 to E8 | Must |
| FR-82 | `.claude/sdd/README.md` shall describe the CHANGE track, its criteria and the unrecognized-name rule; `docs/conventions/git.md` shall name the branch `change/<feature-kebab>` for the track and `spec/`, `build/`, `ship/` for full specs (today it says `feat/<feature-kebab>`, `docs/conventions/git.md:20`); `CLAUDE.md` "How work is done here" shall name the track | Should |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-39 | Reproducibility | Results depend only on paths and file contents, as SPEC_ARCHIVE_GATES NFR-35 |
| NFR-40 | Dependencies | Standard library only; the hook dependencies stay `pyyaml>=6` |
| NFR-41 | Compatibility | The real repository gives 0 errors after the build, with the same 2 warnings as today unless a finding changes |
| NFR-42 | Messages | Every new error names the file, the rule and the value found (criterion ID, AC ID or file name) |

---

## Data Contracts

No dataset or message. No new repository data file.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| None | - | - | - | - | - |

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-120 | The repository after the build | `python scripts/check_specs.py` runs | Exit code 0 and 0 errors (unit test on the repository root); the full output, generated on the final build head with its SHA, is in the BUILD_REPORT |
| AC-121 | Fixtures with `NOTES.md` in `features/`, `draft.md` in `reports/`, a `.gitkeep` and valid phase names | The checker runs | One error for each of the two `.md` files, naming it; `.gitkeep` and the valid names give none |
| AC-122 | A valid CHANGE document in `Draft`, `Ready for Build` and `Complete`, and copies without a section, with a placeholder past `Draft` and with an empty Self-Review | The checker runs on each | The valid ones pass; each copy gives one error naming the file and the rule |
| AC-123 | The checker module | The final statuses are read | They equal FR-76 for all five phases, and a CHANGE document in `Ready for Build` is not final |
| AC-124 | CHANGE documents past `Draft` with all of E1 to E8 `Yes` and evidence, without the E8 row, with E3 twice, with E5 `No`, and with an empty E8 evidence cell | The checker runs on each | The first passes; each other gives one error naming the criterion |
| AC-125 | CHANGE documents: an AC missing from Test Strategy (`Ready for Build`); `Complete` with an AC missing from Evidence, with a `Fail` row, and without an `Evidence commit` SHA; and a valid `Complete` one | The checker runs on each | Each invalid one gives one error naming the AC or the rule; the valid one passes |
| AC-126 | Archive folders: one with a single `Complete` CHANGE document; one whose CHANGE document is `Ready for Build`; one with a CHANGE document and a SHIPPED document; one with a CHANGE document and a DEFINE | The checker runs | The first passes with no SHIPPED; each other gives one rule (a) error naming the folder |
| AC-127 | An archived CHANGE document with an `Open` row in Issues & Follow-ups, an unprefixed foreign ID, and its own F-NN rows cited in its text | The checker runs with an empty allowlist | One rule (b) warning for the `Open` row; one rule (c) error for the foreign ID; the own IDs pass |
| AC-128 | `.claude/sdd/templates/CHANGE_TEMPLATE.md` | It is copied to `features/` as a `Draft` CHANGE document and its headings are read | No missing-section error, its `##` headings equal the CHANGE section list, and its Eligibility table has the rows E1 to E8 |
| AC-129 | The SPEC_ARCHIVE_GATES AC-119 self-test with a `Complete` CHANGE document and a `Ready for Build` CHANGE document in a temporary `features/` | The self-test helper selects and simulates them | Only the `Complete` one is added, as a folder without a generated SHIPPED document, and the simulated archive gives 0 errors |
| AC-130 | `.claude/sdd/README.md`, `docs/conventions/git.md` and `CLAUDE.md` after the build | A unit test reads them | The README names the CHANGE track, E1 to E8 and the unrecognized-name rule; `git.md` names `change/` and `spec/`, `build/`, `ship/`; `CLAUDE.md` names the CHANGE track |

---

## Decisions and Open Items

### Decided by the user

| ID | Decision | Source |
|---|---|---|
| D-83 | The retrospective runs in three steps; Step 1 (this spec) is a full cycle in three PRs (`spec/`, `build/`, `ship/`), because it changes the gates and cannot use the track it creates | User, 2026-11-05 |
| D-84 | No rule of `CLAUDE.md` or `docs/conventions/git.md` changes in this spec; confirmation rules change only in Step 3, through E8 (since D-86, any relaxation is outside the CHANGE track; Q-31) | User, 2026-11-05 |
| D-86 | E8 as defined in the eligibility table: within `docs/conventions/git.md` and the agent rules of `CLAUDE.md`, a change that removes a rule, reduces or narrows confirmation, widens what is allowed without confirmation, or weakens a check is not eligible; adding rules, raising requirements or fixing wording without changing the effect is eligible; in doubt, not eligible; the E8 evidence cites the diff of the affected rules | User, 2026-11-05 (answer to Q-29) |

### Derived in this phase (not yet confirmed by the user)

| ID | Decision | Reason |
|---|---|---|
| D-85 | Criteria E1 to E7 as proposed in the retrospective, with E5 narrowed to the templates that the script or the tests read | The follow-up task template of Step 2 is read by neither, so it can use the track |
| D-87 | One document only: no BUILD_REPORT and no SHIPPED for the track; the CHANGE document moves to `archive/<FEATURE>/` in the last commit of the same PR | A SHIPPED document for one PR would be nearly empty, and a PR cannot record its own merge commit (SPEC_ARCHIVE_GATES template feedback) |
| D-88 | The unrecognized-name error is part of this spec, not a separate earlier change | Same file and tests; the new phase needs it so that a misnamed CHANGE document is caught |
| D-89 | `Evidence commit` with a SHA is required in a `Complete` CHANGE document | Lesson of SPEC_ARCHIVE_GATES: the Build Evidence was generated on an intermediate commit |

### Questions for the user

| ID | Question |
|---|---|
| Q-29 | "E8" was not defined in the retrospective proposal; this DEFINE first read it as a rule about `gh api` evidence. **Answered 2026-11-05 by the user: E8 is the no-weakening criterion (D-86).** |
| Q-30 | The four retrospective decisions were not answered one by one; this DEFINE follows the recommendations (D-85, D-87, D-88). Confirm, or name the ones to change |
| Q-31 | Under D-86, the relaxations listed in the retrospective Step 3 table (stop deleting merged remote branches, force push on `main`, CI check before merge) reduce confirmations, so they are not eligible for the CHANGE track. Should Step 3 be a full spec (DEFINE, DESIGN, BUILD_REPORT, SHIPPED), or another process the user approves? |

---

## Pre-registered Findings and Follow-ups

| ID | Kind | Statement | Recorded in |
|---|---|---|---|
| F-01 | Follow-up | Check E1 to E8 against the actual `git diff` of a PR in CI, instead of only reading the Eligibility rows | SHIPPED |
| F-02 | Follow-up | Port the track to the template repository, together with SPEC_ARCHIVE_GATES F-01 | SHIPPED |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-20 | Constraint | No archived document is edited | Yes (SPEC_ARCHIVE_GATES C-17 rule) |
| C-21 | Constraint | `check_specs.py` keeps its invocation by the hook and CI | Yes (`.pre-commit-config.yaml:28`, `.github/workflows/ci.yml:33`) |
| A-43 | Assumption | `features/` and `reports/` hold no unrecognized `.md` file today | Yes: `ls -a`, 2026-11-05: only `.gitkeep` in both |
| A-44 | Assumption | No file named `CHANGE_*` exists | Yes: `git ls-files`, 2026-11-05 |
| A-45 | Assumption | The final status is derived today as the first status marked past draft | Yes: `scripts/check_specs.py:401-404` |
| A-46 | Assumption | The AC-119 self-test writes a SHIPPED document into every simulated folder | Yes: `tests/test_check_specs.py:632` |
| A-47 | Assumption | Rule (b) reads only archived BUILD_REPORT documents today | Yes: `scripts/check_specs.py:588` |
| A-48 | Assumption | Each new rule gives 0 hits on the real repository and fires on a broken example | Yes: throwaway prototype of FR-74 to FR-80 on `git archive a8dbac3`, 2026-11-05: 0 for every rule; with one broken example per rule: FR-74 1, FR-75 1, FR-76 1, FR-77 2, FR-78 2, FR-79 1, FR-80 3 |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Measured on #35 to #42 and by a prototype |
| Users | 3 | Author, reviewer, template maintainer |
| Scope | 3 | Criteria and out-of-scope items listed |
| Acceptance criteria | 3 | A valid and an invalid case for each rule |
| Constraints | 1 | Q-30 and Q-31 open (Q-29 answered) |
| **Total** | **13/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:** E1 to E8 are declared in the document and only their presence is checked;
  nothing compares them with the real `git diff` (F-01). E8 is a judgement on the meaning of a rules diff; the checker sees only the declared result and evidence.
- **Risks:** The unrecognized-name error turns any stray note in `features/` into a red CI; this
  is intended, but notes must live elsewhere (`notes/`, which git ignores).
- **What I would do differently:** Ask the four retrospective decisions one by one before writing
  the DEFINE, instead of following the recommendations (Q-30).
- **Next improvement:** Decide F-01 after the first two CHANGE documents, when the cost of
  declaring the criteria by hand is known.

---

## Next Step

`/design .claude/sdd/features/DEFINE_SMALL_CHANGE_TRACK.md`

---

## Change Log

| Date | Change | Reason | Impact |
|---|---|---|---|
| 2026-11-05 | First version, Ready for Design | Retrospective Step 1, user decisions of 2026-11-05 | DESIGN to follow |
| 2026-11-05 | Q-29 answered: E8 is the no-weakening criterion (D-86, now decided by the user); FR-77 and AC-124 require a non-empty evidence cell; D-84 notes the consequence for Step 3 and Q-31 asks for its process; A-48 records the rule prototypes | User answer of 2026-11-05 on PR #43 | DESIGN G-41, AC-124 test, template rows and open items updated in the same commit |
