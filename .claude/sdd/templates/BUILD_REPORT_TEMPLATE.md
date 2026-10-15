# BUILD REPORT: {Feature Name}

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | {FEATURE_NAME} |
| **Date** | {YYYY-MM-DD} |
| **Source** | DESIGN_{FEATURE_NAME}.md |
| **Status** | In Progress |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

---

## Summary

{What was built, in three sentences.}

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 1 | {path} | {Created / Modified} | {lint, test name, manual run} |

---

## Acceptance Criteria Evidence

| AC | Result | Evidence |
|---|---|---|
| AC-01 | {Pass / Fail / Not run} | {Test output, query result, run link} |

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `ruff check .` | {...} |
| Tests | `pytest` | {N passed} |
| Spec check | `python scripts/check_specs.py` | {...} |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| {...} | {...} | {...} | {...} | {Yes / No} |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | {...} | {Low / Medium / High} | {Ticket, ADR or next release} |

---

## Self-Review

- **Weak points:** {...}
- **Risks:** {...}
- **What I would do differently:** {...}
- **Next improvement:** {Concrete action}

---

## Next Step

`/ship {FEATURE_NAME}`
