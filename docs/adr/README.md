# Architecture Decision Records

One file per decision, numbered in order. Create new records with `/adr "<title>"`.
Records are never deleted; a reversed decision is marked `Superseded by NNNN`.

| # | Title | Status | Date |
|---|---|---|---|
| 0000 | [Template](0000-template.md) | - | - |
| 0001 | [Runtime environment constraints for Free Edition and Aiven](0001-runtime-environment-constraints.md) | Accepted | 2026-10-15 |
| 0002 | [Aiven Kafka with SASL_SSL SCRAM and credentials in a secret scope](0002-aiven-kafka-with-sasl-scram-and-secret-scope.md) | Accepted | 2026-10-15 |
| 0003 | [Unity Catalog layout `smart_meter_dev` created by an idempotent setup task](0003-unity-catalog-layout-and-setup-task.md) | Accepted | 2026-10-15 |
| 0004 | [One Lakeflow pipeline for Silver and Gold, with a rule-evaluation materialized view feeding quarantine and metrics](0004-single-lakeflow-pipeline-with-quarantine-routing.md) | Accepted | 2026-10-15 |
| 0005 | [First-ingested-wins deduplication with `row_number()` in materialized views](0005-first-ingested-wins-cross-source-deduplication.md) | Accepted | 2026-10-15 |
| 0006 | [Bronze tables, not Kafka, are the replay and reprocessing source](0006-bronze-tables-as-replay-source.md) | Accepted | 2026-10-15 |
