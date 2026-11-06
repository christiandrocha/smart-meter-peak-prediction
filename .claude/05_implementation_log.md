# 05 — Implementation Log

Chronological record of what was built, the problems found, how they were solved, and the
decisions taken during `/build` (and later fixes) that the DESIGN did not capture. Specs, build
reports and SHIPPED records in `.claude/sdd/` remain the authoritative source; this log links them.

---

## How to use this file

- Add an entry for each build session or significant implementation milestone.
- Be specific: name the file, the error message, the solution, and the commit.
- If a decision diverges from the DESIGN file manifest, record it here and in the BUILD_REPORT
  "Deviations from Design" table, and update the DESIGN through `/iterate`.
- Cite findings with their spec prefix (`SMALL_CHANGE_TRACK I-03`): IDs repeat across specs.
- Do not clean up entries: this is a chronological log, not a summary.

---

## Entry template

```
## YYYY-MM-DD — <FEATURE> — <phase or task>

### Implemented
- <artifact created or modified> (<commit>)

### Problems encountered
- <problem description>
  → Solution: <what was done to resolve it>
  → Status: resolved | open | workaround

### Decisions made during build
- <decision not captured in the DESIGN, with rationale>

### Divergences from manifest
- <what was planned vs what was actually built, and why>

### Open questions
- <anything that needs follow-up or investigation>
```

---

## 2026-11-06 — SMALL_CHANGE_TRACK — build, ship and /iterate

Spec PR #43 (merge 335d079). Build PR #44 (`build/small-change-track`, head 3a3b868) and ship
PR #45 (`ship/small-change-track`, stacked on the build branch) are open; neither is merged.
Archive: `.claude/sdd/archive/SMALL_CHANGE_TRACK/`.

### Implemented
- `scripts/check_specs.py`: `CHANGE` phase and `check_change` (Eligibility E1 to E8, the
  `## Rule Changes` gate when E8 is `Relaxing`, AC traceability, `Evidence commit` SHA when
  `Complete`); an error for each `.md` in `features/` or `reports/` without a phase prefix
  (`.gitkeep` never listed); a literal `FINAL_STATUS` map; change folders in the archive; rules
  (b) and (c) read CHANGE documents (fe6fe2f).
- `.claude/sdd/templates/CHANGE_TEMPLATE.md` (new); `.claude/sdd/README.md`,
  `docs/conventions/git.md` (branch names `spec/`, `build/`, `ship/`, `change/`; no agent rule
  changed) and `CLAUDE.md` (0033d8b).
- Code-review fixes for SMALL_CHANGE_TRACK I-01, I-02 and I-04 (0e56f72).
- Evidence results in a `Complete` CHANGE document: `Not run` is an error; `Deferred: <reason>`
  is accepted and listed as a warning; `Deferred` without a reason, or not in the colon form, is
  an error. `docs/conventions/naming.md` branch example uses `build/` and `change/` (4668af3,
  closes SMALL_CHANGE_TRACK I-03 and I-08).
- Ship: DEFINE, DESIGN and BUILD_REPORT archived, `SHIPPED_2026-11-06.md`, `CHANGELOG.md` under
  Unreleased (c379f6d, e0ba7b0).
- `/iterate` (docs only): DESIGN G-41, G-42, G-43, the `check_change` row and the Test Strategy
  match the shipped code; DEFINE FR-78 and AC-125 include `Not run` and `Deferred`; BUILD_REPORT
  findings I-05 to I-07 and I-09 closed with dispositions.

### Problems encountered
- A fenced `## Rule Changes` example in a document hid the real section, and headings were
  matched by prefix (SMALL_CHANGE_TRACK I-01).
  → Solution: headings are read from the text with fences blanked; exact heading match (0e56f72).
  → Status: resolved
- A CHANGE document with no AC rows passed (SMALL_CHANGE_TRACK I-02).
  → Solution: no AC rows in Acceptance Criteria is an error (0e56f72).
  → Status: resolved
- `Not run` evidence let a document reach `Complete` (SMALL_CHANGE_TRACK I-03).
  → Solution: user decision 2026-11-06; `Not run` blocks `Complete`, with `Deferred: <reason>`
    as the visible way out (4668af3).
  → Status: resolved
- `Fail` matched any Evidence cell, and hex words such as `defaced` counted as a SHA
  (SMALL_CHANGE_TRACK I-04).
  → Solution: only the result cell is read; the SHA must contain a digit (0e56f72).
  → Status: resolved
- The eligibility regex `\s*` before a closing pipe can consume a newline on a malformed
  three-column row (SMALL_CHANGE_TRACK I-05).
  → Status: open, not fixed (docs-only iteration); SHIPPED F-05.
- Change-folder name check (SMALL_CHANGE_TRACK I-06): already enforced, because `load_archive`
  takes a file as the CHANGE document only when its stem equals `CHANGE_<folder>` and every other
  file is a rule (a) error.
  → Status: resolved in code; a test for the misnamed-file case is missing (SHIPPED F-06).
- Loose substring asserts in the AC-126, AC-128 and AC-130 tests (SMALL_CHANGE_TRACK I-07).
  → Status: open, not fixed (docs-only iteration); SHIPPED F-07.
- The full `pytest` run in the first BUILD_REPORT predated the review-fix commit 0e56f72.
  → Solution: full suite rerun on 4668af3 (657 passed, 90 deselected, 1 xfailed) and on the
    ship head e0ba7b0 (656 passed, 1 skipped, 90 deselected, 1 xfailed; the skip is the AC-119
    self-test, which has no `features/` or `reports/` document left to simulate).
  → Status: resolved
- The build branch was pushed by the build agent although the task said not to push.
  → Solution: later commits were added on top, so the next push was a fast-forward; no force push.
  → Status: resolved

### Decisions made during build
- `Deferred: <reason>` is reported as a warning, so a deliberate deferral stays visible in the
  checker output without blocking the change (user decision 2026-11-06).
- The `## Rule Changes` example in the template is fenced, so the template headings equal the ten
  required sections (AC-128); the inner fence uses `~~~`.
- `load_docs(root, report=None)`: `report` is optional for direct callers in tests.

### Divergences from manifest
- G-41 described three captured groups; the table has four columns and the code captures ID,
  result and evidence. DESIGN corrected by `/iterate` 2026-11-06 (SMALL_CHANGE_TRACK I-09).
- Checks not in the original DESIGN (no AC rows, result cell only for `Fail`, SHA needs a digit,
  `Not run`, `Deferred`): recorded in DESIGN G-42 and G-43 by the same `/iterate`.

### Open questions
- SMALL_CHANGE_TRACK F-01: history checks in CI (E1 to E8 from the real diff, order of the E8 OK,
  D-91 evidence-commit position).
- After #44 and #45 merge: whether to fill the PR rows of the SHIPPED document, and the release tag.
