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
| 0007 | [PEAK_MODEL runtime and data assumptions](0007-peak-model-runtime-and-data-assumptions.md) | Accepted | 2026-10-21 |
| 0008 | [PEAK_MODEL jobs: the daily job runs the shared Silver/Gold pipeline first, training runs in a separate on-demand job](0008-peak-model-jobs-and-pipeline-dependency.md) | Proposed | 2026-10-21 |
| 0009 | [Decision threshold stored as a model version tag, highest threshold wins ties](0009-decision-threshold-as-model-version-tag.md) | Proposed | 2026-10-21 |
| 0010 | [Next-day consumption spike label: strictly above 1.3 x the median of the last 4 complete same-weekday days within 8 weeks](0010-consumption-spike-label-definition.md) | Proposed | 2026-10-21 |
| 0011 | [Dense ML tables written by change-only MERGE; training sets kept as run artifacts, not tables](0011-dense-ml-tables-and-run-artifact-training-sets.md) | Proposed | 2026-10-21 |
