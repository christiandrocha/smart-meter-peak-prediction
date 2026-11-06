# 06 — Retrospective

Structured analysis of each iteration: what worked, what did not, what was learned, technical
debt, and improvements for the next cycle. The SHIPPED document of each feature holds its formal
lessons; this file collects them across features.

---

## How to use this file

- One section per feature iteration or release.
- Reference specific artifacts, ACs, findings (with spec prefix) and ADRs.
- Technical debt must name a target (release, follow-up ID, or "not scheduled" with a reason).
- Improvements feed the next DEFINE or the template repository.
- Do not delete previous retrospectives.

---

## Retrospective template

```
## <FEATURE> — <iteration name> — YYYY-MM-DD

### Context
<what was the goal of this iteration>

### What worked well
- <observation> → <why it mattered>

### What did not work
- <observation> → <root cause> → <what to do differently>

### Learned
- <insight gained that was not obvious at design time>

### Technical debt
| ID | Description | Severity | Target |
|----|-------------|----------|--------|
| TD-01 | <description> | High/Medium/Low | <release or follow-up> |

### Metrics observed
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| <metric> | <observed> | <expected> | on-track / off-track |

### Improvements for next iteration
- [ ] <concrete improvement with rationale>

### AC validation results
| AC | Result | Notes |
|----|--------|-------|
| AC-01 | pass/fail/pending | <observation> |
```

---

## SMALL_CHANGE_TRACK — CHANGE track, build, ship and /iterate — 2026-11-06

### Context
Step 1 of the SDD retrospective of 2026-11-05: a CHANGE track (one `CHANGE_<FEATURE>.md`
instead of DEFINE, DESIGN, BUILD_REPORT and SHIPPED) for small tooling or process changes that
meet E1 to E8, checked by `scripts/check_specs.py`, plus an error for unrecognized document names
in `features/` and `reports/`. Spec #43 merged; build #44 and ship #45 open, not merged.

### What worked well
- The code review before `Complete` found three Medium gaps (SMALL_CHANGE_TRACK I-01 to I-03)
  that the AC tests missed → each was fixed with a dedicated test before merge.
- Deciding I-03 with an explicit way out (`Deferred: <reason>` as a warning) → strict on silent
  gaps, without blocking a change on a criterion that deliberately cannot run yet.
- `check_specs.py` rule (b) made open findings visible as warnings → the `/iterate` closed them
  with written dispositions, and the warnings fell from 6 to the 2 INGESTION_GUARD ones.

### What did not work
- The DEFINE test table gave one valid and one invalid case per rule → adversarial forms (fenced
  examples, empty tables, every non-expected result value) were not listed → list them in the
  DEFINE for every new checker rule.
- G-41 described three captured groups for a four-column table, and the build treated the
  difference as mechanical → the DESIGN stayed stale until `/iterate` → update the DESIGN
  through `/iterate` whenever a regex or column count changes during build.
- The first full `pytest` run predated the review-fix commit → evidence mixed commits → run the
  full suite on the final code head and name that SHA in the Verification Log.
- `docs/conventions/naming.md` kept the old `feat/` example (SMALL_CHANGE_TRACK I-08) → the
  scope did not search for the old value of a renamed convention → grep for it at DEFINE time.
- A subagent pushed the build branch although told not to → the "no push" instruction is only
  a prompt instruction → check `git ls-remote` after each delegated build.

### Learned
- A document check that accepts a free-text result cell needs an explicit list of accepted and
  rejected values; anything unlisted passes silently.
- Archived documents are not frozen in practice: rule (b) warnings can only be cleared by
  editing the archived BUILD_REPORT, so `/iterate` on archived documents is part of the process.

### Technical debt
| ID | Description | Severity | Target |
|----|-------------|----------|--------|
| TD-01 | Eligibility regex `\s*` can cross lines on a malformed row (SMALL_CHANGE_TRACK I-05) | Low | SHIPPED F-05, not scheduled |
| TD-02 | No test for a misnamed file in a change folder; the behaviour is already enforced (SMALL_CHANGE_TRACK I-06) | Low | SHIPPED F-06, test only |
| TD-03 | Loose substring asserts in the AC-126, AC-128 and AC-130 tests (SMALL_CHANGE_TRACK I-07) | Low | SHIPPED F-07, not scheduled |
| TD-04 | E1 to E8, the order of the E8 OK and D-91 are declared, not checked against git history | Medium | SHIPPED F-01, not scheduled |

### Metrics observed
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Full `pytest` on the build code (4668af3) | 657 passed, 90 deselected, 1 xfailed | all pass | on-track |
| `tests/test_check_specs.py` | 115 passed | all pass | on-track |
| `check_specs.py` after `/iterate` | 57 documents, 0 errors, 2 warnings | 0 errors | on-track |
| Code review findings | 0 High, 3 Medium, 8 Low | 0 High open | on-track |

### Improvements for next iteration
- [ ] Add the adversarial-case list to the DEFINE template's test table (template repository).
- [ ] Use the CHANGE track for the follow-up template (retrospective Step 2), which shows whether
  F-01 is worth its cost.
- [ ] Close TD-01 to TD-03 in one small CHANGE document.

### AC validation results
| AC | Result | Notes |
|----|--------|-------|
| AC-120 | pass | repository has no errors |
| AC-121 | pass | unrecognized names; `.gitkeep` never listed |
| AC-122 | pass | includes the no-AC-rows case |
| AC-123 | pass | literal `FINAL_STATUS` |
| AC-124 | pass | eligibility rows E1 to E8 |
| AC-125 | pass | includes `Not run` and `Deferred` cases |
| AC-126 | pass | archived change folders |
| AC-127 | pass | rules (b) and (c) on CHANGE documents |
| AC-128 | pass | template sections and criteria |
| AC-129 | pass | self-test simulates CHANGE documents |
| AC-130 | pass | docs describe the track |
| AC-131 | pass | Rule Changes gate when E8 is `Relaxing` |
