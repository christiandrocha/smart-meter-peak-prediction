# Spikes

A spike answers one environment or feasibility question before a design depends on it:
"can serverless reach the broker?", "does the registry resolve aliases here?".

## Rules

1. Code lives in `spikes/<topic>/` and is never imported by `src/` or deployed.
2. Each spike states its question and pass criteria at the top of the file.
3. Each spike ends with an assertion or an explicit pass/fail print.
4. The outcome (pass, fail, exact error, workaround) is recorded in an ADR and in the
   *Assumptions* table of the BRAINSTORM or DEFINE document that depended on it.
5. When the question is answered, the spike is frozen. Fixes go into the real implementation.

## Record

| Spike | Question | Result | ADR |
|---|---|---|---|
| Sampling (`spikes/local/prepare_sample.py`) | Does the script reproduce the seed-42 figures? (A-13) | Pass (2026-10-15): 60 households, 1,432,405 historical and 247,569 stream rows, pinned in `config/` | 0001 |
| A-08 (`spikes/local/a08_offgrid_null_cooccurrence.py`) | Are off-grid timestamps exactly the `Null` energy rows? | Pass (2026-10-15): 450 of 450 on 9 blocks; 60 of 60 in the seed-42 sample | 0001 |
| 00 (`spikes/databricks/00_setup_catalog.py`) | Can Free Edition create catalog `smart_meter_dev` (A-09), and does deploy work before the catalog exists (DA-06)? | A-09 Pass (2026-10-16): catalog and layout created, rerun clean. DA-06 Fail: deploy errors when the catalog is absent; fallback is setup first, then deploy | 0001 |
| 01 (`spikes/databricks/01_spike_autoloader.py`) | Does Auto Loader ingest the source-header CSVs from a Volume, with no rescued data and 0 rows on rerun? (A-02) | Pass (2026-10-16): 143,633 rows on run 1, 0 on run 2, no rescued data | 0001 |
| 02 (`spikes/databricks/02_spike_kafka_consume.py`) | Do secret scopes, SASL_SSL SCRAM with an inline PEM CA and `availableNow` work? (A-03, A-05, DA-09; A-06 from the Aiven console) | Pass (2026-10-16): 1,000 events read with SCRAM-SHA-256 and an inline PEM CA; `processingTime` rejected; secrets readable | 0001 |
| 03 (`spikes/databricks/03_spike_kafka_unreachable.py`) | Does the Kafka source fail within the timeouts when the broker is off, leaving the checkpoint unchanged? (DA-05) | Pass (2026-10-16): failed at once on DNS resolution with the service off (61 s run); checkpoint and table unchanged, checked directly | 0001 |
| 04 (`spikes/databricks/04_spike_lakeflow_pipeline/`) | Triggered serverless pipeline, MV expectation metrics, private datasets, `CREATE VIEW`, UTC, imports, fail-rule abort and 1.68 M row timing (A-10, DA-01 to DA-03, DA-07, DA-08, DA-10, AC-15) | 2026-10-16: 12 of 13 checks pass. A-10, DA-02, DA-03, DA-07, DA-08 pass; DA-10 63 s for 1.68 M rows; AC-15 `expect_or_fail` aborts and downstream MVs keep their contents. DA-01 partial: an update with no new input writes no expectation metrics | 0001 |
| A-17 (`spikes/local/a17_peak_labels_eligibility.py`) | Do the seed-42 label and eligibility figures follow from the written definitions (FR-21, FR-22, D-19, D-27, D-34) on top of the METER_INGESTION Silver and Gold rules? | Pass (2026-10-21): label table 36,480 rows with unique keys and 0 QR-19 violations; 33,093 labelled rows at 14.61% positive; eligible labelled rows train 16,969, validation 7,170, test 5,116; with label threshold 1.5 and coverage 0.90 the share is 7.91% on 29,100 rows | 0007 |
| 05 (`spikes/databricks/05_spike_mlflow_uc.py`, submitted by `05_spike_mlflow_uc_submit.py`) | Does MLflow register models in Unity Catalog and resolve the `champion` alias on serverless (A-04), does Feature Engineering work there (A-12) and is training deterministic across tasks (A-16)? | Pass (run 624093996306456, 2026-10-21, 234 s; Python 3.11.10, MLflow 3.17.2, scikit-learn 1.3.0, databricks-feature-engineering 0.18.2): alias load and scores identical, `create_training_set` equal to the explicit join, `fe.score_batch` identical, lineage lists the model downstream, 920 test scores identical in two tasks. A model with versions cannot be deleted until its aliases and versions are removed | 0007 |
