# 0006. Bronze tables, not Kafka, are the replay and reprocessing source

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-15 |
| **Deciders** | Christian |
| **Related** | METER_INGESTION; FR-04, FR-05, FR-13, NFR-02, NFR-09; AC-06, AC-08, AC-10, AC-27; ADR 0002, 0005 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

The Aiven free tier keeps messages for a short, fixed retention and powers off after inactivity
(C-03). Landed CSV files can be removed from the Volume and Free Edition workspaces can be deleted.
FR-13 requires every Silver and Gold table to be rebuildable from Bronze alone, and AC-27 requires
a full refresh with the Kafka service powered off to reproduce identical contents. The Kafka module
rule says Bronze keeps the raw payload plus topic, partition and offset.

## Decision drivers

- Reprocessing must not depend on topic retention or on files still being in the landing Volume.
- Bronze ingestion must be idempotent (AC-06, AC-08) and must not advance on failure (AC-10).
- Bronze must keep raw values so that new rules can be applied retroactively.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Append-only Bronze Delta tables with raw text, payload and `_`-prefixed Kafka coordinates, written by job tasks outside the pipeline; the pipeline reads Bronze only** | Independent of retention; a pipeline full refresh cannot truncate Bronze; raw values preserved | Storage holds a second copy of the raw data |
| Replay from Kafka with a long retention | No second copy | Not available on the free tier; couples reprocessing to the broker being on |
| Bronze as streaming tables inside the pipeline | One deployable unit | A pipeline full refresh would re-read Kafka and the Volume, violating FR-13 and AC-27 |

## Decision

We will keep `bronze.files_meter_readings`, `bronze.files_households` and
`bronze.kafka_meter_readings` as append-only Delta tables (`delta.appendOnly = true`), created with
explicit DDL by the setup task and written by `availableNow` streams in job tasks with one
checkpoint per stream in Volume `bronze.checkpoints`. The Kafka stream starts from `earliest` on an
empty checkpoint and keeps `failOnDataLoss = true`, so a retention gap fails loudly instead of
silently skipping offsets. The Kafka metadata columns are `_topic`, `_partition`, `_offset` and
`_kafka_timestamp`; `kafka_key` and `payload` keep their names, and `produced_at` stays inside the
raw payload. Bronze stays incremental, while Silver and Gold are materialized views recomputed
from Bronze only (ADR 0005), so every pipeline update, and any explicit full refresh, reads only
Bronze. Deleting a Bronze checkpoint or table is a recovery action documented in the runbook and
is always followed by a pipeline update.

## Consequences

- **Positive:** AC-27 holds with the broker off; topic retention only bounds how long the consumer
  may be down, not reprocessing.
- **Negative:** If the consumer is down longer than the retention, messages are lost to the
  lakehouse and the Kafka task fails until an operator re-produces them from the stream sample
  file; this is accepted for v0.1.
- **What would make us revisit this:** A broker with long or tiered retention, or Bronze volume
  large enough that a second copy matters.
