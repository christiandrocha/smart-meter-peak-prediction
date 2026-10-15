# 0004. One Lakeflow pipeline for Silver and Gold, with a rule-evaluation materialized view feeding quarantine and metrics

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-15 |
| **Deciders** | Christian |
| **Related** | METER_INGESTION; FR-07 to FR-12, FR-14, NFR-03, NFR-04, NFR-07; AC-11, AC-12, AC-15, AC-16, AC-26, AC-30, AC-34; Q-04, Q-07, OD-01; OD-02, OD-04, OD-06; ADR 0001, 0005 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

**Pipeline shape.** Q-07 fixed one triggered serverless Lakeflow pipeline for Silver and Gold, run
as a task of the daily job, with Bronze ingestion in job tasks (Free Edition allows one active
pipeline per type). OD-01 (user decision, 2026-10-15) made `silver.meter_readings` and
`silver.meter_readings_quarantine` materialized views recomputed over Bronze.

**Rule actions.** Q-04 fixed the rule actions:
- Drop rules (QR-02, QR-03, QR-04, QR-05, QR-07) write every dropped row to
  `silver.meter_readings_quarantine`, with `rule_name` (the first failed rule, in the precedence
  QR-07, QR-02, QR-03, QR-04, QR-05) and `failed_rules` (all failed rules).
- Per-rule counts count a row under every rule in `failed_rules`. They cover the Bronze rows that
  the update evaluated (AC-12, AC-34).
- The study-period filter (SF-01) and duplicates (QR-09) are counted, not quarantined.

**Platform facts.**
- `expect_or_drop` discards rows without exposing them, so it cannot feed a quarantine by itself.
- Two independent queries, expectations on one and an inverse filter on the other, can disagree.
- Expectations are not supported on pipeline views.
- `CREATE VIEW` in a pipeline is available in the default publishing mode (Databricks pipeline
  SQL reference).
- Per-update expectation counts are recorded in the pipeline event log (`flow_progress` events,
  `details:flow_progress:data_quality:expectations`). The log can be published to a Unity Catalog
  table with the pipeline `event_log` setting.

## Decision drivers

- Quarantine rows and per-rule counts must agree by construction (AC-12).
- Every rule has one SQL definition, used by the pipeline, the local tests and the reconciliation
  queries.
- Per-update counts must be queryable within 5 minutes, without extra jobs (NFR-07).
- No processing-time columns in Silver or Gold derived from the pipeline run, so a full refresh
  reproduces identical content (AC-27).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Private rule-evaluation MV: computes `failed_rules`, scope and dedup rank once; Silver and quarantine MVs filter it; counter expectations on it; event log published to UC** | One evaluation per row; counts and quarantine derive from the same column of the same refresh; standard event log | One extra private MV (a second copy of the Bronze rows, about 1.7 M); full recompute on every update |
| `expect_all_or_drop` on Silver plus an inverse-rule query for the quarantine | Uses the native drop action | Two evaluations of each rule; multi-rule rows and null handling can diverge; drop count is per row, not per rule |
| Separate metrics table written by the pipeline | Counts next to the data | Needs an update identifier and a processing timestamp inside the pipeline, which breaks AC-27 determinism |

For OD-04 (`gold.household_data_quality`), three options were compared:
- **Chosen:** a persisted view defined with `CREATE VIEW` in a SQL source file of the same
  pipeline.
- A materialized view: more storage and a refresh for a 60-row derivation.
- A UC view created by the setup task: outside the pipeline, against AC-26.

## Decision

We will run one triggered serverless pipeline, `smart_meter_silver_gold`, that publishes to the
Silver and Gold schemas by fully qualified names.

**Evaluation and routing.**
- A private materialized view, `meter_readings_evaluated`, reads both Bronze reading tables in
  batch. It computes the parsed columns, `failed_rules`, `rule_name`, the scope flag and the
  `row_number()` dedup rank (ADR 0005).
- `silver.meter_readings` and `silver.meter_readings_quarantine` are materialized views that
  filter it.

**Expectations.**
- Counter expectations (`expect`, warn) on `meter_readings_evaluated` test
  `NOT array_contains(failed_rules, 'QR-nn')` for each drop rule, plus SF-01 and QR-09.
- The fail rules QR-01, QR-06 and INV-01 are `expect_or_fail` on the same MV. Because it is
  upstream of every published reading view, a violation fails the update before the published
  views refresh, and their previous contents remain.

**Summary view.** `gold.household_data_quality` is a persisted view in a pipeline SQL file. Its
contract checks run as `expect_or_fail` on a private materialized view that reads it.

**Counts.** The event log is published to `<catalog>.<silver_schema>.pipeline_event_log` and is
the single source of per-update counts (OD-06). Spike 04 must show three things on Free Edition:
- expectations on a materialized view report per-rule metrics in the event log;
- a row failing two counters is counted under both;
- whether a refresh evaluates all rows or only changed rows (DA-01).

Fallbacks are listed in ADR 0001.

**Trade-off.** We accept recomputing Silver and Gold on every update instead of processing them
incrementally, at about 1.7 M rows. The revisit trigger is in ADR 0005: refresh longer than
15 minutes, or Bronze larger than 50 M rows.

## Consequences

- **Positive:** Quarantine rows and per-rule counts cannot disagree. The rule catalog is one
  Python module. Counts per update come from a documented, queryable source. There are no
  streaming checkpoints in Silver.
- **Negative:**
  - Drop rules are implemented as routing plus counter expectations, so the pipeline UI shows
    them as warn expectations, not drop. Operators read this ADR to interpret the UI.
  - Each update re-reads all of Bronze.
- **What would make us revisit this:** Native quarantine support in Lakeflow expectations, more
  than one pipeline allowed on the platform, event log publication becoming unavailable, or the
  ADR 0005 revisit trigger.
