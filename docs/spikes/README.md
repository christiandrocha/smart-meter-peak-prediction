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
| 00 (`spikes/databricks/00_setup_catalog.py`) | Can Free Edition create catalog `smart_meter_dev` (A-09), and does deploy work before the catalog exists (DA-06)? | Pending (written, not run) | 0001 |
| 01 (`spikes/databricks/01_spike_autoloader.py`) | Does Auto Loader ingest the source-header CSVs from a Volume, with no rescued data and 0 rows on rerun? (A-02) | Pending (written, not run) | 0001 |
| 02 (`spikes/databricks/02_spike_kafka_consume.py`) | Do secret scopes, SASL_SSL SCRAM with an inline PEM CA and `availableNow` work? (A-03, A-05, DA-09; A-06 from the Aiven console) | Pending (written, not run) | 0001 |
| 03 (`spikes/databricks/03_spike_kafka_unreachable.py`) | Does the Kafka source fail within the timeouts when the broker is off, leaving the checkpoint unchanged? (DA-05) | Pending (written, not run) | 0001 |
| 04 (`spikes/databricks/04_spike_lakeflow_pipeline/`) | Triggered serverless pipeline, MV expectation metrics, private datasets, `CREATE VIEW`, UTC, imports, fail-rule abort and 1.68 M row timing (A-10, DA-01 to DA-03, DA-07, DA-08, DA-10, AC-15) | Pending (written, not run) | 0001 |
