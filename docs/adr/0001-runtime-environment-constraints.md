# 0001. Runtime environment constraints for Free Edition and Aiven

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-15 |
| **Deciders** | Christian |
| **Related** | METER_INGESTION; NFR-03, NFR-04, NFR-09; AC-28, AC-30, AC-32; ADR 0002, 0003, 0004, 0006 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

METER_INGESTION runs on Databricks Free Edition (serverless only, at most 5 concurrent job tasks,
one active pipeline per pipeline type, daily fair-usage quota, outbound internet restricted;
`.claude/kb/databricks/free-edition.md`, verified 2026-10-06) and consumes an Aiven for Apache
Kafka free-tier service (5 topics x 2 partitions, short retention, powers off after inactivity).
The design in `DESIGN_METER_INGESTION.md` depends on environment capabilities that are only partly
proven. This record lists each one, the spike that answers it, the pass criterion and the fallback
already built into the design, so that a failed spike changes configuration, not architecture.

| ID | Assumption | Spike | Pass criterion | Result | Fallback |
|---|---|---|---|---|---|
| A-01 | Serverless reaches the Aiven broker | TCP test (2026-10-06) | TCP connection to broker host and port succeeds | Pass (2026-10-06) | - |
| A-02 | Auto Loader ingests CSVs from a UC Volume on serverless with `availableNow` | `spikes/databricks/01_spike_autoloader.py` | Two runs over the same files: the first ingests every row and the second ingests 0. A read schema named after the source header (`LCLid`, `tstp`, `energy(kWh/hh)`) leaves `_rescued_data` null | Pending | Batch `COPY INTO` from the Volume in the same task (idempotent per file); for the header, a positional read with `header=false` that drops the header line |
| A-03 | Spark Kafka source authenticates with SASL_SSL and an inline PEM CA | `spikes/databricks/02_spike_kafka_consume.py` | `availableNow` read of the topic returns the produced messages | Pending | CA stored as a file in Volume `bronze.checkpoints/_certs` and passed with `kafka.ssl.truststore.location` |
| A-05 | Serverless streaming supports only `availableNow`-style triggers | spike 02 | `processingTime` trigger rejected or not used; `availableNow` completes and stops | Pending | None needed: the design only uses `availableNow` |
| A-06 | Aiven offers SCRAM-SHA-256 | Aiven console | Mechanism listed for the service user | Pending | Bundle variable `kafka_sasl_mechanism` set to the offered SCRAM variant (no code change) |
| A-08 | Off-grid `tstp` rows (QR-03) are exactly the `Null` energy rows (QR-04); sets the 60 quarantined rows in AC-11 | `spikes/local/a08_offgrid_null_cooccurrence.py` | The set of off-grid rows equals the set of non-numeric energy rows, on the 9 profiled blocks and on the seed-42 sample | Pass (2026-10-15). 9 blocks, 13,059,525 rows: 450 off-grid, 450 non-numeric, 450 in both, 0 in only one. Seed-42 sample in the study period, 1,679,974 rows: 60 off-grid, 60 non-numeric, 60 in both. AC-11 keeps 60 quarantined and 1,679,914 in Silver | AC-11 figures updated through `/iterate` |
| A-09 | Free Edition allows creating catalog `smart_meter_dev` | `spikes/databricks/00_setup_catalog.py` | `CREATE CATALOG IF NOT EXISTS smart_meter_dev` succeeds | Pending | Layout `workspace.smart_meter_dev_<layer>` through bundle variables (ADR 0003) |
| A-10 | A triggered serverless Lakeflow pipeline runs on Free Edition | `spikes/databricks/04_spike_lakeflow_pipeline/` | Spike pipeline update completes; deleted afterwards so one pipeline remains | Pending | None inside the decided scope; would reopen Q-07 through `/iterate` |
| A-13 | The seed-42 figures are reproduced by the sampling script | `spikes/local/prepare_sample.py` with `spikes/local/plan.json` | 60 households, 1,432,405 historical and 247,569 stream rows | Pass (2026-10-15). Selection pinned in `config/sample_households.csv`; counts and checksums in `config/sample_manifest.json` | - |
| DA-01 | Expectations on a materialized view report per-rule metrics in the event log on Free Edition, and count a row under every expectation it fails | spike 04 | A row failing two `expect` rules on a private MV increments `failed_records` of both. A second update with no new input is run, and the evaluated row count is recorded (full recompute or only changed rows) | Pending | Publish the evaluation MV as a UC table and compute the counts from its `failed_rules`, scope and duplicate columns in `metrics.py` |
| DA-02 | One pipeline publishes to several schemas by fully qualified names, supports private datasets and publishes `CREATE VIEW` | spike 04 | Tables in `silver` and `gold`, a private table not visible in UC, a view visible in UC | Pending | View: materialized view (contract `object_type` change through `/iterate`). Schemas: all objects in `silver`, Gold exposed as UC views created by the setup task |
| DA-03 | Pipeline setting `event_log` publishes the event log to a UC table | spike 04 | Table exists and holds `flow_progress` rows of the update | Pending | Query the hidden default event log table of the pipeline |
| DA-04 | (Withdrawn 2026-10-15) Stream-static join with a pipeline MV | - | - | Not needed: Silver is materialized views (ADR 0005) | - |
| DA-10 | A full recompute of Silver and Gold over about 1.7 M Bronze rows fits the AC-30 budget | spike 04 | One update over 1.7 M synthetic rows finishes well inside 2700 s (target under 15 min) | Pending | Streaming Silver with AUTO CDC, through `/iterate` (ADR 0005 revisit trigger) |
| DA-05 | The Kafka source fails within configured client timeouts when the broker is off | `spikes/databricks/03_spike_kafka_unreachable.py` | Query fails in under 10 minutes; checkpoint unchanged | Pending | Task `timeout_seconds` stops the task before 15 minutes |
| DA-06 | `databricks bundle deploy` creates the pipeline before the target catalog exists | spike 00 | Deploy succeeds on a workspace without the catalog | Pending | Run `notebooks/setup_catalog.py` once from the workspace after the file sync, then deploy again |
| DA-07 | Serverless pipelines and job tasks honour `spark.sql.session.timeZone = UTC` | spike 04 | `current_timezone()` returns `UTC` inside a pipeline dataset | Pending | Explicit-zone parsing (`' +0000'` appended to the raw text) and `to_date` with an explicit zone |
| DA-08 | Pipeline sources and notebook tasks import `smart_meter_peak_prediction` from the synced bundle files via `sys.path` | spike 04 | Import succeeds in the spike pipeline | Pending | Build a wheel with bundle `artifacts` and add it to the pipeline and task environments |
| DA-09 | Databricks-backed secret scopes are available on Free Edition and readable from serverless tasks | spike 02 | `dbutils.secrets.get` returns the values (redacted in output) | Pending | None that keeps NFR-05; would block the Kafka path |

A-14 (`tstp` marks the start of the half hour) cannot be validated by a spike; the dataset
documentation does not state it. The design applies it consistently (`reading_date` is the UTC
date of `reading_ts`); if it proves false, `reading_date` shifts by one slot at midnight and is
corrected through `/iterate`.

## Decision drivers

- Zero cost: Free Edition and the Aiven free tier only.
- Each unproven capability must have a fallback that keeps the acceptance criteria reachable.
- Spikes are throwaway and never imported by `src/` (`docs/spikes/README.md`).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Run all spikes first, record outcomes here, design with explicit fallbacks** | Build starts with known constraints; fallbacks are configuration changes | Spikes cost part of one day of quota |
| Build directly and fix problems as they appear | No spike effort | Failures surface late, inside production code, and may force redesign |
| Move to a paid workspace | Fewer limits | Violates the zero-cost constraint (D-03) |

## Decision

We will run spikes 00 to 04 and the Aiven console check before any `src/` code that depends on
them, record each result in the table above, and apply the listed fallback for any failed
assumption without changing the architecture of `DESIGN_METER_INGESTION.md`.

## Consequences

- **Positive:** Environment risk is front-loaded; AC-32 becomes a mechanical check of this record.
- **Negative:** The record must be updated by hand; the spike pipeline must be deleted before the
  bundle pipeline is deployed (one active pipeline per type).
- **What would make us revisit this:** A change in Free Edition limits, a move to a paid
  workspace, or any spike failing without a working fallback.
