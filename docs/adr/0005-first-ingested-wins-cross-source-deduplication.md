# 0005. First-ingested-wins deduplication with `row_number()` in materialized views

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-15 |
| **Deciders** | Christian |
| **Related** | METER_INGESTION; FR-07, FR-09, FR-13, NFR-01, NFR-02, NFR-03; AC-09, AC-11, AC-13, AC-17, AC-27, AC-30; QR-09; OD-01, OD-03; ADR 0004, 0006 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

Readings reach Silver from two Bronze tables. Kafka delivery is at-least-once, and a full replay
of the stream file must leave Silver unchanged while reporting every replayed row as a duplicate
(AC-09). QR-09 fixes the winner of a key `(household_id, reading_ts)`: the earliest
`_ingested_at`, then the smallest `_source_ref`. The same winners must be chosen on a re-run
(AC-17) and on a full refresh from Bronze (AC-27). The seed-42 sample has about 1.7 M Bronze
reading rows, and the daily job must finish in 60 minutes on Free Edition (AC-30). On
2026-10-15 the user decided that Silver `meter_readings` and `meter_readings_quarantine` are
materialized views recomputed over Bronze, with `row_number()` deduplication, while Bronze stays
incremental (DEFINE OD-01).

`_source_ref` (OD-03) must identify a Bronze row. Auto Loader file metadata (`_metadata`) gives
the file path but no row index for CSV, so the file reference uses the path plus the raw key
text, as the Silver contract describes.

## Decision drivers

- A deterministic winner, independent of input order and partitioning.
- A per-update duplicate count.
- Rebuildable from Bronze alone, with the same result for a normal update and a full refresh.
- Low operational and conceptual complexity at the v0.1 volume.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Materialized views: `row_number()` over the key, ordered by `(_ingested_at, _source_ref)`, in a private evaluation MV; Silver keeps rank 1 and losers are counted by a warn expectation** | Exactly the QR-09 order, ties included; no streaming state or checkpoints in Silver; a normal update and a full refresh are the same computation (AC-27); self-healing if Bronze changes | Silver is recomputed over all of Bronze on every update instead of incrementally |
| Streaming tables plus a winner set computed in batch and joined stream-static | Incremental Silver | Relies on `_ingested_at` growing with ingestion order; more moving parts (stream-static join, checkpoints) |
| AUTO CDC (SCD Type 1) with `sequence_by` | Native incremental upserts | Keeps the highest sequence, so `_ingested_at` and the string `_source_ref` must be encoded in inverse order. Equal sequences per key are not allowed. Reports no duplicate count |
| `dropDuplicatesWithinWatermark` | Native streaming operator | Keeps the first row the engine sees, not the earliest ingested; ties are arbitrary (AC-17 fails); needs a watermark spanning the study period |

## Decision

We will define `_source_ref` as follows:
- file rows: `files:` + `_source_file` + `#` + raw `household_id` + `#` + `reading_ts_raw`;
- Kafka rows: `kafka:` + the value of `_topic` + `/` + `_partition` + `/` + `_offset`
  left-padded with zeros to 20 digits, so string order matches offset order.

A private materialized view `meter_readings_evaluated` reads both Bronze tables in batch, parses
them and evaluates the rules. For rows with no failed rule inside the study period, it computes
`row_number() OVER (PARTITION BY household_id, reading_ts ORDER BY _ingested_at, _source_ref)`.
`silver.meter_readings` is a materialized view of rank-1 rows, and the warn expectation
`qr_09_first_ingested_wins` counts rows with rank greater than 1. The fail expectation
`inv_01_source_ref_unique` (`count(*) OVER (PARTITION BY _source_ref) = 1`) guarantees that the
ordering key is unique, so the ranking is deterministic.

**Trade-off.** We accept a full recompute of Silver on every update instead of incremental
processing, because at about 1.7 M rows the recompute takes minutes and removes streaming state
from Silver entirely.

**Revisit trigger.** Move Silver to a streaming table with AUTO CDC when either of these happens:
- the pipeline refresh exceeds 15 minutes;
- Bronze exceeds 50 M rows.

## Consequences

- **Positive:** AC-09, AC-17 and AC-27 follow from one deterministic definition. There are no
  Silver checkpoints to lose. Rule or period changes take effect on the next update without a
  manual full refresh.
- **Negative:** Refresh cost grows linearly with Bronze. Per-update expectation counts describe
  the rows the update evaluated (all rows under a full recompute), not only new input (AC-12).
  Downstream Gold views are recomputed as well.
- **What would make us revisit this:** The revisit trigger above, or a business rule that
  prefers one ingestion path over the other.
