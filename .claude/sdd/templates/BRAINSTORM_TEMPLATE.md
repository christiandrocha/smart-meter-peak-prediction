# BRAINSTORM: {Feature Name}

> Phase 0. Explore intent and approaches before capturing requirements.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | {FEATURE_NAME} |
| **Date** | {YYYY-MM-DD} |
| **Author** | {Name} |
| **Status** | Exploring |

Allowed status values: `Exploring`, `Ready for Define`.

---

## Initial Idea

**Raw input:** {The idea or request as stated}

**Context observed:**

| Aspect | Observation | Implication |
|---|---|---|
| Existing code or data | {What already exists} | {What to reuse or avoid} |
| Platform constraints | {Environment limits} | {What they rule out} |
| Relevant modules / KBs | {databricks, kafka, ...} | {Patterns to consult} |

---

## Discovery Questions & Answers

| # | Question | Answer | Impact |
|---|---|---|---|
| 1 | {Purpose} | {Answer} | {How it shapes the solution} |
| 2 | {Users / consumers} | {Answer} | {Impact} |
| 3 | {Constraints} | {Answer} | {Impact} |

Minimum 3 questions, asked one at a time.

---

## Sample Data Inventory

| Type | Location | Volume | Notes |
|---|---|---|---|
| Input data | {Path or URL} | {Rows / size} | {Format, quality findings} |
| Expected output | {Path or N/A} | {N} | {Schema} |
| Ground truth | {Path or N/A} | {N} | {How it was verified} |

**Profiling findings** (start from `scripts/profile_data.py`; reports in `docs/profiling/`):

| ID | Finding | Evidence | Implication |
|---|---|---|---|
| F-01 | {Finding} | {Numbers, examples} | {What the pipeline must do} |

---

## Approaches Explored

### Approach A: {Name} (recommended)

{Description}

- **Pros:** {...}
- **Cons:** {...}
- **Why recommended:** {...}

### Approach B: {Name}

{Description}

- **Pros:** {...}
- **Cons:** {...}

---

## Selected Approach

| Attribute | Value |
|---|---|
| **Chosen** | Approach {A/B} |
| **Confirmed by** | {Name, date} |
| **Reasoning** | {Why} |

---

## Key Decisions

| # | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| D-01 | {Decision} | {Why} | {What was not done} |

---

## Out of Scope (YAGNI)

| Item | Reason | Revisit in |
|---|---|---|
| {Item} | {Why not now} | {Release or never} |

---

## Assumptions & Open Questions

| ID | Assumption or question | How it will be resolved | Status |
|---|---|---|---|
| A-01 | {Assumption} | {Spike, doc, stakeholder} | Pending |

---

## Suggested Requirements for Define

- **Problem statement (draft):** {One sentence}
- **Success criteria (draft):** {Measurable outcomes}
- **Constraints:** {List}

---

## Self-Review

- **Weak points:** {...}
- **Risks:** {...}
- **What I would do differently:** {...}
- **Next improvement:** {Concrete action}

---

## Next Step

`/define .claude/sdd/features/BRAINSTORM_{FEATURE_NAME}.md`
