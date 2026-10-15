# DEFINE: {Feature Name}

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | {FEATURE_NAME} |
| **Date** | {YYYY-MM-DD} |
| **Author** | {Name} |
| **Source** | {BRAINSTORM_{FEATURE_NAME}.md or other input} |
| **Status** | Draft |

Allowed status values: `Draft`, `Ready for Design`.

---

## Problem Statement

{One or two sentences: who has which problem, and what it costs them.}

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| {Role or system} | {Need} | {Table, API, model, report} |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| {Goal} | {How it is measured} | {Number} |

---

## Scope

**In scope:**
- {Item}

**Out of scope:**
- {Item, with the release that may pick it up}

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | {The system shall ...} | Must |

Priority values: `Must`, `Should`, `Could`.

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | {Cost, latency, security, reproducibility...} | {Measurable statement} |

---

## Data Contracts

For every dataset or message this feature produces or consumes. Link a file in
`docs/contracts/` when the contract is shared with other features.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| {name} | {feature or team} | {one row per ...} | {columns} | {SLA} | {path or inline} |

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-01 | {Precondition} | {Action} | {Observable, measurable result} |

Every criterion must be verifiable by a test or a query. Words such as "fast", "robust" or
"correct" need a number or a reference.

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 | Constraint | {Platform, budget, policy} | Yes |
| A-01 | Assumption | {Statement} | {Spike or pending} |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | {0-3} | {...} |
| Users | {0-3} | {...} |
| Scope | {0-3} | {...} |
| Acceptance criteria | {0-3} | {...} |
| Constraints | {0-3} | {...} |
| **Total** | **{N}/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:** {...}
- **Risks:** {...}
- **What I would do differently:** {...}
- **Next improvement:** {Concrete action}

---

## Next Step

`/design .claude/sdd/features/DEFINE_{FEATURE_NAME}.md`
