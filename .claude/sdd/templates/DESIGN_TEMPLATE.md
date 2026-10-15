# DESIGN: {Feature Name}

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | {FEATURE_NAME} |
| **Date** | {YYYY-MM-DD} |
| **Author** | {Name} |
| **Source** | DEFINE_{FEATURE_NAME}.md |
| **Status** | Draft |

Allowed status values: `Draft`, `Ready for Build`.

---

## Overview

{Three to five sentences describing the solution.}

---

## Architecture

```text
{ASCII diagram of the data flow and components}
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| {name} | {What it does} | {Tool} | FR-01, NFR-01 |

---

## Data Model

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| {catalog.schema.table} | {bronze/silver/gold} | {...} | {...} | {...} | {...} |

Data quality rules:

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| {Expression} | {Table} | {Action} | {F-NN} |

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| {NNNN} | {Title} | {Proposed / Accepted} |

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom.

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | {path} | Create | {...} | {agent name} | - |

---

## Test Strategy

Every acceptance criterion from DEFINE appears here.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-01 | {Unit / integration / data quality / query} | {path} | {...} |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | {...} |
| Scheduling and retries | {...} |
| Monitoring and alerting | {...} |
| Secrets | {...} |
| Cost | {...} |
| Backfill / reprocessing | {...} |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| {...} | {...} | {...} |

---

## Self-Review

- **Weak points:** {...}
- **Risks:** {...}
- **What I would do differently:** {...}
- **Next improvement:** {Concrete action}

---

## Next Step

`/build .claude/sdd/features/DESIGN_{FEATURE_NAME}.md`
