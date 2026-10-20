# DESIGN: Meter Ingestion

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | METER_INGESTION |
| **Date** | 2026-10-15 |
| **Author** | Christian |
| **Source** | DEFINE_METER_INGESTION.md (status Ready for Design); contracts in `docs/contracts/`; ADRs 0001 to 0006; user answers of 2026-10-15 to the six design questions |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

---

## Overview

A port of the committed sampling spike turns the Kaggle files into the seed-42 sample: monthly
historical CSVs, one stream CSV and a household CSV, all byte-identical to the spike output. The
selection is pinned in `config/sample_households.csv` and the reference counts and checksums in
`config/sample_manifest.json`. Historical and household files land in a Unity Catalog Volume and
are ingested incrementally by Auto Loader. A Dockerised producer replays the stream file to Aiven
Kafka, and Structured Streaming consumes it. Both paths write append-only Bronze tables in job
tasks (`availableNow`), and Bronze is the only replay source.

One triggered serverless Lakeflow pipeline recomputes Silver and Gold as materialized views from
Bronze on every update:
- A published evaluation table, `silver.meter_readings_evaluated` (ops dataset, DA-01 fallback),
  parses every Bronze reading once, lists its failed rules and deduplicates with `row_number()`.
- It also deduplicates dropped rows by a content-identity key (`_dedup_key`), so a replayed invalid
  message is counted as a duplicate and not quarantined again (QR-09 b).
- `silver.meter_readings` and `silver.meter_readings_quarantine` filter the evaluation table.
- Per-rule, scope and duplicate counts are table totals computed by `metrics.py` from the
  `failed_rules`, `is_out_of_scope` and `is_duplicate` columns of the evaluation table. The same
  rules also run as warn expectations, which only add observability in the published event log.

Delivery is one feature in three pull requests. PR 1 is a gate that validates the environment
before the lakehouse code is built.

---

## Architecture

```text
 LOCAL MACHINE                                         DATABRICKS FREE EDITION (serverless, dev target)
 -------------                                         ------------------------------------------------
 data/raw (Kaggle, git-ignored)
     |
 scripts/prepare_sample.py + config/sample_plan.json   (port of spikes/local/prepare_sample.py)
     |   (src: sampling.py)   checked against config/sample_households.csv and config/sample_manifest.json
     v
 data/sample/seed42/
   historical/readings_YYYY-MM.csv ------- databricks fs cp ---> /Volumes/<cat>/<bronze>/landing/readings/historical/
   dimensions/households_sample.csv ------ databricks fs cp ---> /Volumes/<cat>/<bronze>/landing/households/
   stream/readings_stream.csv
   manifest.json
     |
 docker: producer (src: producer.py)          Aiven Kafka (SASL_SSL, SCRAM)
   .env credentials  ---- topic meter-readings (2 partitions, key household_id) ----+
                                                                                    |
 Job smart_meter_ingestion (daily 06:00 UTC, paused in development mode, 1 concurrent run)
 +---------------------------------------------------------------------------------------------------+
 | [1] setup_catalog (notebook)  CREATE IF NOT EXISTS catalog, schemas, Volumes, Bronze tables        |
 |        |                     \                                                                     |
 | [2] ingest_files (notebook)   [3] ingest_kafka (notebook, secrets from scope smart_meter)          |
 |     Auto Loader availableNow      Kafka source availableNow, failOnDataLoss=true                    |
 |     -> bronze.files_meter_readings    -> bronze.kafka_meter_readings                                |
 |     -> bronze.files_households                                                                      |
 |        \                     /                                                                     |
 | [4] refresh_silver_gold (pipeline task, triggered, serverless)                                      |
 +---------------------------------------------------------------------------------------------------+
                                   |
 Pipeline smart_meter_silver_gold  v   (python: pipelines/meter_pipeline.py, sql: pipelines/household_data_quality.sql)
 +---------------------------------------------------------------------------------------------------+
 |  bronze.files_meter_readings --(batch read)--+                                                     |
 |  bronze.kafka_meter_readings --(batch read)--+--> silver.meter_readings_evaluated (MV, ops)        |
 |      parse, failed_rules, scope, row_number() over (household_id, reading_ts)                      |
 |      order by (_ingested_at, _source_ref); dropped rows: row_number() over _dedup_key;             |
 |      source_ref_row_count                                                                          |
 |      expectations: QR-01, QR-06, INV-01 fail; counters QR-02..05, QR-07, QR-08, SF-01, QR-09 warn   |
 |                 |                                   |                                              |
 |   is_silver     v                 is_quarantined    v                                              |
 |   silver.meter_readings (MV)        silver.meter_readings_quarantine (MV, rule_name check fail)    |
 |                 |                                                                                  |
 |  bronze.files_households --(batch)--> [private MV] households_checked (QR-13 fail)                 |
 |                                              --> silver.households (MV, QR-14/QR-15 warn)          |
 |                 |                                   |                                              |
 |   gold.household_daily_consumption (MV, QR-10 warn, QR-11 fail)                                    |
 |        --> [private MV] daily_consumption_orphan_check (QR-12 warn)                                 |
 |   gold.household_data_quality_monthly (MV, dense union household set x months, range checks fail)  |
 |        --> gold.household_data_quality (persisted VIEW, SQL file)                                   |
 |              --> [private MV] household_data_quality_check (ratio checks fail)                     |
 |  event log published to <cat>.<silver>.pipeline_event_log  (run observability, OD-06)              |
 |  counts: metrics.py over silver.meter_readings_evaluated (table totals, not the event log)         |
 +---------------------------------------------------------------------------------------------------+
                                   |
                         PEAK_MODEL reads gold.* and silver.households (contracts)
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Sampling library and CLI (`src/.../sampling.py`, `scripts/prepare_sample.py`, `config/sample_plan.json`) | Port of `spikes/local/prepare_sample.py` (`plan` and `build`): block choice and household selection with exclusions, cutoff split, household file, manifest extended to FR-01 | Python 3.11, pandas | FR-01, FR-02, FR-16, NFR-01 |
| Pinned sample reference (`config/sample_households.csv`, `config/sample_manifest.json`, existing inputs) | Expected seed-42 selection, counts and file checksums | CSV, JSON | FR-01, FR-02 |
| Replay producer (`src/.../producer.py`, `docker/producer/Dockerfile`) | Read stream CSV, build contract events, publish keyed by `household_id` in event-time order at `REPLAY_SPEED`, idempotent, credentials from `.env` | confluent-kafka, Docker | FR-03, FR-15, FR-16, NFR-05 |
| Settings (`src/.../config.py`) | One typed settings object (catalog, schema names, Volumes, study period, cutoff, topic, secret scope) built from job parameters or pipeline configuration; fully qualified names for main and fallback layouts | Python | FR-16, FR-17 |
| Rule catalog (`src/.../rules.py`) | Single definition of SF-01, QR-01 to QR-15, INV-01 and contract checks: id, expectation name, SQL, action, dataset | Python, Spark SQL strings | FR-07, FR-08, FR-09, NFR-07 |
| Bronze ingestion library (`src/.../bronze.py`) + notebooks `ingest_files`, `ingest_kafka` | Auto Loader and Kafka `availableNow` streams, Bronze projections (source header to Bronze names, `_`-prefixed Kafka metadata), Kafka options with SASL_SSL and bounded timeouts | Auto Loader, Spark Kafka source | FR-04, FR-05, FR-06, FR-15, NFR-02, NFR-04, NFR-06 |
| Setup notebook (`notebooks/setup_catalog.py`) | Idempotent creation of catalog, schemas, Volumes and Bronze tables (explicit DDL, append-only). Run once by hand between the two first-time deploys (DA-06), and as the first job task afterwards | Spark SQL | FR-17, NFR-09 |
| Silver library (`src/.../silver.py`) | Parsing, `_source_ref`, rule evaluation (`failed_rules`, `rule_name`, scope), `row_number()` dedup, Silver, quarantine and household projections | PySpark | FR-06, FR-07, FR-08, FR-13, NFR-06 |
| Gold library (`src/.../gold.py`) | Daily aggregation, orphan check, study months, dense monthly quality with gaps and `has_household_record` | PySpark | FR-10, FR-11 |
| Pipeline sources (`pipelines/meter_pipeline.py`, `pipelines/household_data_quality.sql`) | Thin wiring of materialized views and expectations from the rule catalog; persisted summary view | Lakeflow Declarative Pipelines (Python `dlt`, SQL) | FR-07 to FR-13, NFR-04 |
| Metrics and reconciliation (`src/.../metrics.py`) | SQL for rule, scope and duplicate counts as table totals over `silver.meter_readings_evaluated` (and, for QR-10, QR-12, QR-14, QR-15, over the published Gold and household tables), AC-11 reconciliation, order-independent table checksums; an optional event-log query for run observability | Spark SQL / Databricks SQL | FR-09, NFR-07 |
| Bundle (`databricks.yml`, `resources/*.yml`) | Variables, `dev` target, daily job, pipeline with configuration and event log | Databricks Asset Bundles | FR-14, FR-16, FR-17, NFR-04 |
| Tests (`tests/`) | Unit tests on local Spark with a pipeline harness; local-data tests on the raw files; integration tests on the dev workspace | pytest, pyspark, pandas, databricks-sdk | All AC |
| Runbook (`docs/runbooks/meter_ingestion.md`) | Secrets, sample generation and upload, produce, deploy, run, verify, recover, full refresh, prod naming | Markdown | NFR-08, NFR-09 |

---

## Data Model

All names are shown for the main layout (catalog `smart_meter_dev`). With the A-09 fallback the
catalog is `workspace` and each schema is `smart_meter_dev_<layer>` (ADR 0003). Every column that
records processing time or transport metadata starts with `_` (AC-19 has no exceptions):
`_ingested_at`, `_kafka_timestamp`, `_topic`, `_partition`, `_offset`, `_produced_at`,
`_source_file`, `_source_ref`, `_ingestion_path`, `_rescued_data`. `kafka_key` and `payload`
keep their names. `produced_at` exists only inside the Kafka payload (topic contract). Event-time
columns are `reading_ts`, `reading_date` and `reading_month`. All timestamps are UTC. The session
time zone is `UTC` in every task and in the pipeline configuration, and the pipeline asserts it
at start (DA-07).

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| Volume `smart_meter_dev.bronze.landing` | bronze | One file per sample file | Path | - | `readings/historical/`, `households/` |
| Volume `smart_meter_dev.bronze.checkpoints` | bronze | One folder per stream | Path | - | `files_meter_readings/`, `files_households/`, `kafka_meter_readings/` |
| `smart_meter_dev.bronze.files_meter_readings` | bronze | One row per CSV line | `(_source_file, household_id, reading_ts_raw)` | None; `delta.appendOnly = true` | `household_id`, `reading_ts_raw`, `energy_kwh_raw` (raw untrimmed text, renamed from source header `LCLid`, `tstp`, `energy(kWh/hh)`), `_rescued_data`, `_source_file`, `_ingested_at` |
| `smart_meter_dev.bronze.files_households` | bronze | One row per CSV line | `(_source_file, household_id)` | None; append-only | `household_id`, `tariff_raw`, `acorn_category_raw`, `acorn_group_raw`, `source_block_raw` (from `LCLid`, `stdorToU`, `Acorn`, `Acorn_grouped`, `file`), `_rescued_data`, `_source_file`, `_ingested_at` |
| `smart_meter_dev.bronze.kafka_meter_readings` | bronze | One row per Kafka message | `(_topic, _partition, _offset)` | None; append-only | `kafka_key`, `payload`, `_topic`, `_partition`, `_offset`, `_kafka_timestamp`, `_ingested_at` (DEFINE inline schema). `produced_at` stays only inside the raw `payload` |
| `smart_meter_dev.silver.meter_readings_evaluated` | silver (ops) | One row per Bronze reading row | `_source_ref` | None | Materialized view, published (DA-01 fallback). Source of the rule, scope and duplicate counts. Columns: `_source_ref`, `_ingestion_path`, `_ingested_at`, `household_id`, `household_id_raw`, `reading_ts_raw`, `energy_kwh_raw`, `reading_ts`, `energy_kwh`, `reading_date`, `_produced_at`, `payload`, `_rescued_data`, `payload_ok`, `failed_rules` (array of string, never null), `rule_name`, `is_out_of_scope`, `_dedup_key`, `dedup_rank`, `quarantine_rank`, `is_quarantine_duplicate`, `is_quarantined`, `is_duplicate` (valid duplicates and quarantine duplicates), `is_silver`, `source_ref_row_count`. Not a PEAK_MODEL input. Contract `silver_meter_readings_evaluated.yaml` (manifest 30a). Carries all reading expectations |
| `smart_meter_dev.silver.meter_readings` | silver | One row per household per half hour | `(household_id, reading_ts)` | Liquid clustering `(household_id, reading_date)` | Materialized view of `is_silver` rows; includes `_produced_at` parsed from the payload (null for file rows); contract `silver_meter_readings.yaml` |
| `smart_meter_dev.silver.meter_readings_quarantine` | silver | One row per distinct dropped content identity (earliest-ingested dropped Bronze row per `_dedup_key`) | `_source_ref`; also unique `_dedup_key` | None | Materialized view of rows with `is_quarantined`; carries `_dedup_key`; no `_produced_at` column; contract `silver_meter_readings_quarantine.yaml` |
| `households_checked` (private MV) | silver (internal) | One row per Bronze household row | - | None | Trimmed values plus `key_row_count` for QR-13 |
| `smart_meter_dev.silver.households` | silver | One row per sampled household | `household_id` | None | Materialized view over `households_checked`; contract `silver_households.yaml` |
| `smart_meter_dev.gold.household_daily_consumption` | gold | One row per household per UTC day with a reading | `(household_id, reading_date)` | Liquid clustering `(household_id, reading_date)` | Materialized view; contract `gold_household_daily_consumption.yaml` |
| `daily_consumption_orphan_check` (private MV) | gold (internal) | One row per household in daily consumption | `household_id` | None | `is_known_household` for QR-12 |
| `smart_meter_dev.gold.household_data_quality_monthly` | gold | One row per household per study month (dense) | `(household_id, reading_month)` | Liquid clustering `(household_id)` | Materialized view; household set = `silver.households` union households with any Silver reading; non-null `has_household_record` |
| `smart_meter_dev.gold.household_data_quality` | gold | One row per household | `household_id` | - | Persisted view (`CREATE VIEW` in the pipeline SQL file), derived only from the monthly table; carries `has_household_record` |
| `household_data_quality_check` (private MV) | gold (internal) | One row per household | `household_id` | None | Reads the view; carries its contract checks |
| `smart_meter_dev.silver.pipeline_event_log` | silver (ops) | One row per pipeline event | `id` | Managed by the platform | Published with the pipeline `event_log` setting; run observability only (warn counter metrics, fail-rule errors, refresh events). Not the source of any AC count; platform-managed, so it has no data contract |
| `smart_meter_dev.ml` | ml | - | - | - | Empty schema for PEAK_MODEL |

### Column derivations (Silver evaluation)

All expressions are Spark SQL strings, defined once in `silver.py` and `rules.py`. The pipeline,
the unit-test harness and the reconciliation SQL all reuse them.

| Column | Files path | Kafka path |
|---|---|---|
| `household_id` | `trim(household_id)` | `trim(parsed.household_id)` when `payload_ok`, else null |
| `household_id_raw` (quarantine `household_id`) | Bronze `household_id` as stored | `get_json_object(payload, '$.household_id')` |
| `reading_ts_raw` | Bronze `reading_ts_raw` | `get_json_object(payload, '$.reading_ts')` |
| `energy_kwh_raw` | Bronze `energy_kwh_raw` | `get_json_object(payload, '$.energy_kwh')` |
| `payload_ok` | `true` | `parsed IS NOT NULL AND parsed._corrupt_record IS NULL`, and `household_id`, `reading_ts`, `source`, `produced_at` of `parsed` are all not null. `parsed` is `from_json(payload, <contract value schema> plus _corrupt_record, mode PERMISSIVE)` |
| `reading_ts` | `coalesce(try_to_timestamp(trim(reading_ts_raw), 'yyyy-MM-dd HH:mm:ss.SSSSSSS'), try_to_timestamp(trim(reading_ts_raw), 'yyyy-MM-dd HH:mm:ss'))` | `try_to_timestamp(trim(parsed.reading_ts), "yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX")` when `payload_ok` |
| `energy_kwh` | `try_cast(trim(energy_kwh_raw) AS DOUBLE)` | `parsed.energy_kwh` when `payload_ok` |
| `reading_date` | `to_date(reading_ts)` (UTC session) | same |
| `_produced_at` (Silver only) | null | `try_to_timestamp(parsed.produced_at, "yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX")` when `payload_ok` |
| `_source_ref` (OD-03) | `concat('files:', _source_file, '#', coalesce(household_id, ''), '#', coalesce(reading_ts_raw, ''))` on raw Bronze values | `concat('kafka:', _topic, '/', cast(_partition AS STRING), '/', lpad(cast(_offset AS STRING), 20, '0'))` (values only; unaffected by the column renames) |
| `_ingestion_path` | `'files'` | `'kafka'` |
| `payload` | null | Bronze `payload` |
| `_dedup_key` (QR-09 b) | `IF(household_id_raw IS NOT NULL AND reading_ts_raw IS NOT NULL, concat('files:key:', household_id_raw, '#', reading_ts_raw), concat('files:row:', sha2(concat_ws('\u0001', coalesce(household_id_raw, '\u0000'), coalesce(reading_ts_raw, '\u0000'), coalesce(energy_kwh_raw, '\u0000'), coalesce(_rescued_data, '\u0000')), 256)))` | `IF(household_id_raw IS NOT NULL AND reading_ts_raw IS NOT NULL, concat('kafka:key:', household_id_raw, '#', reading_ts_raw), concat('kafka:payload:', sha2(payload, 256)))`, where `household_id_raw` and `reading_ts_raw` are `get_json_object(payload, '$.household_id')` and `'$.reading_ts'` (independent of `payload_ok`) |

**Dedup key rule (QD-01).** `_dedup_key` is computed from raw values as received (no trim, no
parse), so it exists for every row, including rows that fail QR-02 or QR-07, and it does not
depend on offset, file name or file position. The path prefix keeps a files row and a Kafka row
apart. For a Kafka payload whose raw `household_id` and raw `reading_ts` are both readable, the key
is the business key and not the payload hash, whether or not the payload passes QR-07 (a null
`source` or a wrong type in another field does not matter). The replay producer stamps a new
`produced_at` into every message, so a replayed payload is not byte-identical; the hash is used only
where no business key can be read (I-22, 2026-10-19). The energy text is not part of the key,
matching the valid-row key.

"Raw" and "readable" (Kafka): the raw value of a field is the result of
`get_json_object(payload, '$.<field>')` as a string: a JSON string gives its text without quotes
(escapes decoded, no trim); a number, boolean, object or array gives its JSON text as Spark renders
it; a missing field, a JSON null, a payload that is not JSON and a payload that is not an object
give NULL. "Readable" means a non-NULL result, with no type check (`"household_id": 123` gives
`123`). This is the same expression that already fills `household_id_raw` and `reading_ts_raw`, so
no `from_json` is involved and `payload_ok` is not read. For a payload that passes QR-07 the result
equals the previous rule, because both fields are then non-null strings. A NULL `payload` is not
expected (Bronze keeps the raw value); it would give a NULL key.

Rule evaluation uses the precedence QR-07, QR-02, QR-03, QR-04, QR-05. A rule is evaluated only
when its inputs exist, so a row never fails twice for one root cause.

| Flag | Expression |
|---|---|
| `f07` | `NOT payload_ok` |
| `f02` | `NOT f07 AND reading_ts IS NULL` |
| `is_out_of_scope` (SF-01) | `NOT f07 AND NOT f02 AND NOT (reading_ts >= study_start AND reading_ts < study_end + 1 day)` |
| `f03` | `NOT f07 AND NOT f02 AND NOT is_out_of_scope AND unix_micros(reading_ts) % 1800000000 != 0`. In UTC this equals minute 0 or 30 with second 0, and it also rejects sub-second offsets |
| `f04` | `NOT f07 AND NOT is_out_of_scope AND (energy_kwh IS NULL OR isnan(energy_kwh) OR abs(energy_kwh) = double('infinity'))` |
| `f05` | `NOT f07 AND NOT is_out_of_scope AND NOT f04 AND energy_kwh < 0` |
| `failed_rules` | `filter(array(IF(f07,'QR-07',NULL), IF(f02,'QR-02',NULL), IF(f03,'QR-03',NULL), IF(f04,'QR-04',NULL), IF(f05,'QR-05',NULL)), x -> x IS NOT NULL)` |
| `rule_name` | `element_at(failed_rules, 1)` (null when empty) |
| `is_candidate` | `size(failed_rules) = 0 AND NOT is_out_of_scope` |
| `dedup_rank` | `row_number() OVER (PARTITION BY household_id, reading_ts ORDER BY _ingested_at, _source_ref)`, computed over candidate rows only (null for others) |
| `is_silver` | `is_candidate AND dedup_rank = 1` |
| `quarantine_rank` | `row_number() OVER (PARTITION BY _dedup_key ORDER BY _ingested_at, _source_ref)`, computed over rows with `size(failed_rules) > 0` only (null for others). Same ordering as `dedup_rank`, so the earliest row wins and ties go to the smaller `_source_ref` |
| `is_quarantine_duplicate` | `size(failed_rules) > 0 AND quarantine_rank > 1` |
| `is_quarantined` | `size(failed_rules) > 0 AND quarantine_rank = 1` |
| `is_duplicate` | `(is_candidate AND dedup_rank > 1) OR is_quarantine_duplicate` (the QR-09 total) |
| `source_ref_row_count` | `count(*) OVER (PARTITION BY _source_ref)` (INV-01) |

Implementation note: as with `dedup_rank`, the partition also carries the eligibility flag, so rows
that are not dropped never rank against dropped rows. A valid row and a dropped row with the same
business key therefore never compete (AC-11: one class per row). Out-of-scope rows are in neither
partition. A row that fails a drop rule cannot be a candidate, so `is_silver`, `is_quarantined`,
`is_duplicate` (valid) and `is_quarantine_duplicate` are mutually exclusive with `is_out_of_scope`.

Routing works as follows:
- `silver.meter_readings` holds the rows with `is_silver`.
- `silver.meter_readings_quarantine` holds the rows with `is_quarantined`.
- Rows with `is_out_of_scope` or `is_duplicate` go to neither table and are counted.

Uniqueness of `_dedup_key` in the quarantine holds by construction (only `quarantine_rank = 1`
rows are routed) and is asserted by tests (AC-09, AC-12), not by a new expectation, so the rule
catalog and the wiring test keep their expectation set.

Examples: a row whose timestamp does not parse and whose energy is `Null` fails QR-02 and QR-04.
A row off the grid with `Null` energy fails QR-03 and QR-04 (AC-34).

**Counts (AC-12, DA-01 fallback).** Spike 04 showed that the event log carries expectation
metrics only for updates that actually refreshed a dataset: an update with no new input wrote no
metrics for the evaluation MV (ADR 0001, DA-01 partial). So the counts are not read from the event
log. They are **table totals over the current state** of `silver.meter_readings_evaluated`, which
is recomputed from all of Bronze whenever it refreshes and is unchanged when it is skipped as up
to date. `metrics.py` computes, with one query:
- per drop rule R: the rows where `array_contains(failed_rules, R) AND NOT is_quarantine_duplicate`
  (a row failing two rules is counted under both; a repeat of a dropped record is counted under
  none, so a replay raises no per-rule total);
- SF-01: the rows where `is_out_of_scope`;
- QR-09: the rows where `is_duplicate`, one total for valid duplicates and quarantine duplicates;
  `metrics.py` also returns `count_if(is_quarantine_duplicate)` as a separate figure;
- the evaluated row count: `count(*)`, which must equal the rows of both Bronze reading tables.

After any update, the table totals satisfy:
- the count for each drop rule equals the quarantine rows whose `failed_rules` contain it;
- the quarantine rows equal the evaluated rows with `size(failed_rules) > 0 AND NOT
  is_quarantine_duplicate` (the rows with `is_quarantined`);
- the SF-01 count equals the rows outside the study period;
- the QR-09 count equals all duplicates (valid duplicates plus quarantine duplicates), and
  `is_silver` rows equal `silver.meter_readings`.

There is no per-update delta in the data. Where an AC compares an input with its effect (AC-09,
AC-17, AC-34), the test takes the totals before and after the input and checks the difference, or
checks the totals on a fixture. A full refresh gives the same totals as a normal update, because
both recompute from Bronze (AC-27). The counts for QR-10, QR-12, QR-14 and QR-15 follow the same
rule: `metrics.py` computes them from the published tables (`gold.household_daily_consumption`,
`silver.households`, and the households of `gold.household_daily_consumption` that are absent from
`silver.households`), not from the event log. The warn counter expectations stay on the datasets
for observability in the event log, but no AC depends on them.

**Fail rules on materialized views (QR-01, QR-06, INV-01, QR-13, QR-11 and the contract
checks).** These are `expect_or_fail` on the dataset that computes them. `silver.meter_readings_evaluated`
and `households_checked` sit upstream of every published reading and household view. A violation
fails the flow and the update, and the downstream MVs are not refreshed in that update. Because an
MV refresh is atomic, the published tables keep their previous contents, so "0 rows committed by
it" (AC-15) holds. Spike 04 verifies this on the platform.

### Gold derivations

- `household_daily_consumption`: group Silver by `(household_id, reading_date)`.
  - `total_energy_kwh = sum(energy_kwh)`
  - `max_energy_kwh = max(energy_kwh)`
  - `reading_count = cast(count(*) AS INT)`
  - `is_complete_day = reading_count = 48`
- `household_data_quality_monthly`:
  - **Grid:** months are `sequence(trunc(study_start, 'MM'), trunc(study_end, 'MM'), interval 1 month)`, 20 for the default period. Households are the distinct ids of `silver.households` union `silver.meter_readings`. The grid is their cross join.
  - **Household flag:** `has_household_record = household_id IN silver.households`, never null.
  - **Expected readings:** `48 x` the days of the month inside `[study_start, study_end]`.
  - **Gaps:** per reading, `prev_ts = lag(reading_ts) over (partition by household_id order by reading_ts)` and `missing = (unix_seconds(reading_ts) - unix_seconds(prev_ts)) / 1800 - 1`. A gap event is `missing > 0`, assigned to the month of `reading_ts`.
  - **Aggregates:** `observed_readings`, `zero_readings` (`energy_kwh = 0`), `gap_count`, `first_reading_ts` and `last_reading_ts` per household and month, left-joined to the dense grid with zeros and null timestamps.
  - **Point in time:** each month's values depend only on readings up to the end of that month, because the lag looks backwards only (AC-24).
- `household_data_quality` (SQL view): sums of the monthly table per household.
  - `has_household_record = bool_or(has_household_record)`
  - `coverage_ratio_study_period = observed / expected`
  - `coverage_ratio_active_span = observed / ((unix_seconds(last) - unix_seconds(first)) / 1800 + 1)`, null when the household has no reading
  - `zero_share = zero / observed`, null when `observed = 0`
  - integer columns cast to `INT`

Data quality rules:

Expectation names follow the form `<rule id in lower case>_<short description>` (for example
`qr_03_on_30_min_grid`), so event log rows map to rule ids by prefix. A "counter" is a warn
expectation whose failures are, by construction, the rows routed by that rule. Counters are kept
for observability in the event log (they report only for updates that refreshed the dataset);
the counts used by the ACs come from `metrics.py` over `silver.meter_readings_evaluated`. In the
table below, `meter_readings_evaluated` means `silver.meter_readings_evaluated`.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| SF-01 study period (`NOT is_out_of_scope`), counter `sf_01_in_study_period` | `meter_readings_evaluated` | `drop` as scope transformation: row excluded from Silver and quarantine, counted as the `is_out_of_scope` total | D-08, F-07 |
| QR-01 `NOT payload_ok OR (household_id IS NOT NULL AND household_id RLIKE '^MAC[0-9]{6}$')` | `meter_readings_evaluated` | `fail` | Q-04 |
| QR-02 timestamp parses, counter `NOT array_contains(failed_rules, 'QR-02')` (counters stay on `failed_rules`; they are event-log observability only and may count a replayed repeat, the AC counts come from `metrics.py`) | `meter_readings_evaluated` | `drop` to quarantine | F-04 |
| QR-03 on 30-minute grid, counter on `'QR-03'` | `meter_readings_evaluated` | `drop` to quarantine | F-03 |
| QR-04 trimmed energy parses as a finite number, counter on `'QR-04'` | `meter_readings_evaluated` | `drop` to quarantine | F-02, F-04 |
| QR-05 `energy_kwh >= 0`, counter on `'QR-05'` | `meter_readings_evaluated` | `drop` to quarantine | Physical bound |
| QR-06 `NOT payload_ok OR reading_ts IS NULL OR (_ingestion_path = 'files' AND reading_ts < cutoff) OR (_ingestion_path = 'kafka' AND reading_ts >= cutoff)` | `meter_readings_evaluated` | `fail` | D-09 |
| QR-07 payload parses with the topic value schema, counter on `'QR-07'` | `meter_readings_evaluated` | `drop` to quarantine | Topic contract |
| QR-08 `_rescued_data IS NULL` | `meter_readings_evaluated` | `warn` | Schema drift |
| QR-09 `NOT is_duplicate`, counter `qr_09_first_ingested_wins` | `meter_readings_evaluated` | `drop` as deduplication: loser (valid duplicate, or repeat of a dropped record by `_dedup_key`) excluded from Silver and quarantine, counted as the `is_duplicate` total; a quarantine duplicate raises no per-rule total | F-09, at-least-once delivery, I-15 |
| INV-01 `source_ref_row_count = 1` | `meter_readings_evaluated` | `fail` | Primary key of quarantine and Silver contracts (design invariant) |
| Quarantine `rule_name IN ('QR-02','QR-03','QR-04','QR-05','QR-07')` | `silver.meter_readings_quarantine` | `fail` | Quarantine contract || QR-10 `is_complete_day` | `gold.household_daily_consumption` | `warn` | F-06 |
| QR-11 `reading_count <= 48` | `gold.household_daily_consumption` | `fail` | Impossible after QR-03 and QR-09 |
| QR-12 `is_known_household` (one row per household, so the count is orphan households) | `daily_consumption_orphan_check` | `warn` | Q-04 |
| QR-13 `household_id IS NOT NULL AND key_row_count = 1` | `households_checked` (upstream of `silver.households`) | `fail` | HI F-09 |
| QR-14 `acorn_group IN ('Affluent','Comfortable','Adversity')` | `silver.households` | `warn` | F-08 |
| QR-15 `tariff IN ('Std','ToU')` | `silver.households` | `warn` | HI distributions |
| Monthly `observed_readings BETWEEN 0 AND expected_readings` | `gold.household_data_quality_monthly` | `fail` | Monthly contract |
| Monthly `zero_readings BETWEEN 0 AND observed_readings` | `gold.household_data_quality_monthly` | `fail` | Monthly contract |
| Monthly `has_household_record IS NOT NULL` | `gold.household_data_quality_monthly` | `fail` | User decision 2026-10-15 (union household set) |
| Summary `coverage_ratio_study_period BETWEEN 0 AND 1` | `household_data_quality_check` | `fail` | Summary contract |
| Summary `zero_share IS NULL OR zero_share BETWEEN 0 AND 1` | `household_data_quality_check` | `fail` | Summary contract |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-01 | Silver is materialized views over Bronze. In the private MV `meter_readings_evaluated`, `row_number()` over `(household_id, reading_ts)`, ordered by `(_ingested_at, _source_ref)` among valid in-scope rows, keeps rank 1. Losers are counted by `qr_09_first_ingested_wins` (ADR 0005, user decision 2026-10-15) | Implements QR-09 literally, ties included, and is deterministic for any input order (AC-17). Every update is a recompute from Bronze, so full refresh and incremental updates agree (AC-27). Replays always rank after the originals (AC-09), for dropped rows too through `_dedup_key` and `quarantine_rank` (QD-01, 2026-10-19). Trade-off: Silver is recomputed on every update instead of incrementally, which is accepted at about 1.7 M rows. Revisit trigger: when the pipeline refresh exceeds 15 minutes or Bronze exceeds 50 M rows, move Silver to a streaming table with AUTO CDC |
| OD-02 | The MV `silver.meter_readings_evaluated`, published to Unity Catalog as an ops table (DA-01 fallback applied), computes `failed_rules` once. The quarantine and Silver MVs filter it. `metrics.py` counts per rule, scope and duplicates from its `failed_rules`, `is_out_of_scope` and `is_duplicate` columns. Each drop rule keeps one counter expectation on the same MV, testing `array_contains(failed_rules, ...)`, for event-log observability only (ADR 0004). Schema `silver` because it is a Silver-stage intermediate that shares the pipeline default schema, the Silver contract set and the Silver lineage, and it needs no new schema or setup DDL; the name carries no layer suffix, and the contract marks it `ops` (not for PEAK_MODEL) | Counts and quarantine rows derive from the same column of the same refresh, so AC-12 and AC-34 hold by construction, and the totals do not depend on whether the platform skipped an update (DA-01 partial, spike 04: no metrics for an unchanged update). Cost: a second copy of the Bronze rows (about 1.7 M rows, with `payload`) is stored and visible in the catalog |
| OD-03 | Files: `files:<_source_file>#<raw household_id>#<reading_ts_raw>`. Kafka: `kafka:<topic>/<partition>/<offset padded to 20>`, built from the values of `_topic`, `_partition` and `_offset`. Uniqueness is enforced by INV-01 | Auto Loader `_metadata` exposes file path, name, size, block and modification time, but no CSV row index. The raw key is unique per file (F-09). Padding makes string order equal offset order |
| OD-04 | Persisted view via `CREATE VIEW` in `pipelines/household_data_quality.sql`, with its contract checks on a private MV that reads it | Matches the contract (`object_type: view`), and 60 rows need no storage. `CREATE VIEW` is supported in pipelines that use the default publishing mode (Databricks pipeline SQL reference). Fallback: a materialized view, through `/iterate` (DA-02) |
| OD-05 | An idempotent setup notebook runs as the first job task, and once by hand on a fresh workspace between two deploys (DA-06). Names come from bundle variables, and the Bronze tables are created by explicit DDL (ADR 0003) | Development mode prefixes bundle-managed resource names, which would break the contract names. The same code serves the fallback layout, and `bundle destroy` keeps data |
| OD-06 | Revised 2026-10-16 (DA-01 partial). Counts are table totals computed by `metrics.py` from `silver.meter_readings_evaluated` (OD-02) and the published Gold and household tables. The pipeline `event_log` setting still publishes the event log to `<catalog>.<silver_schema>.pipeline_event_log` (DA-03 passed), as run observability: warn counter metrics and refresh events for updates that refreshed a dataset, fail-rule errors for diagnosing an aborted update, and update timing. `metrics.py` may expose one optional query (sum of `failed_records` per expectation by `origin.update_id`), documented as present only for updates that refreshed the dataset. No AC test asserts on it | Spike 04: an update with no new input wrote no expectation metrics, so per-update event-log counts are unreliable as a source of truth. Table totals keep the data tables free of processing-time columns (AC-27) and are testable at any time, with no 5-minute window. Fallback for the event log: the hidden default event log table (DA-03) |

### Assumption dependencies

| Assumption | Decisions depending on it | Spike (manifest #) | Fallback |
|---|---|---|---|
| A-02 | Auto Loader in `ingest_files`, with read schema names equal to the source header (`LCLid`, `tstp`, `energy(kWh/hh)`) | 3 | `COPY INTO` per file; or `header=false` with a positional schema, dropping the header line in the projection |
| A-03 | Inline PEM truststore | 4 | CA file in Volume `checkpoints/_certs`, `kafka.ssl.truststore.location` |
| A-05 | `availableNow` everywhere | 4 | None needed |
| A-06 | `SCRAM-SHA-256` | Aiven console, recorded with 4 | Variable `kafka_sasl_mechanism` |
| A-08 | 60 quarantined rows in AC-11 | 1 | AC-11 figures updated through `/iterate` |
| A-09 | Catalog `smart_meter_dev` | 2 | `workspace.smart_meter_dev_<layer>` by variables |
| A-10 | Triggered serverless pipeline | 6 to 8 | None inside the scope (would reopen Q-07) |
| A-13 | Seed-42 figures | Resolved: `spikes/local/prepare_sample.py` reproduces them; pinned in `config/sample_households.csv` and `config/sample_manifest.json` | - |
| A-14 | `reading_date` = UTC date of `reading_ts` | None possible | Accepted, documented in ADR 0001 |
| DA-01 | OD-02, OD-06, AC-09, AC-12, AC-16, AC-17, AC-34: MV expectations report per-rule metrics in the event log on Free Edition and count a row under every failed expectation. Spike 04 also records whether a refresh evaluates all rows or only changed rows | 6 to 8 | Partial (2026-10-16, ADR 0001). Held: per-rule `failed_records` appear in the published event log, a row failing two rules is counted under both, and the duplicate is counted once under `qr_09_first_ingested_wins`. Failed: a second update with no new input wrote no expectation metrics and no `num_output_rows` (most likely skipped as up to date), so per-update counts exist only for updates that refreshed the MV. **Fallback applied:** `silver.meter_readings_evaluated` is published as a UC table, and `metrics.py` computes rule, scope and duplicate counts from its `failed_rules`, `is_out_of_scope` and `is_duplicate` columns as table totals (OD-02, OD-06). The event log is kept for observability only |
| DA-02, DA-03, DA-07, DA-08 | Multi-schema publishing, private datasets and `CREATE VIEW`; event log publication; UTC; imports | 6 to 8 | ADR 0001 |
| DA-05 | AC-10 timing | 5 | Task timeout 840 s |
| DA-10 | AC-30 with a full recompute of Silver and Gold | 6 to 8 (timing over 1.7 M synthetic rows) | Streaming Silver with AUTO CDC through `/iterate` (ADR 0005 revisit trigger) |
| DA-06 | First deploy order | 2 | Failed on 2026-10-16 (ADR 0001): `bundle deploy` syncs the files, then terraform stops with `Catalog 'smart_meter_dev' does not exist.` The fallback applies: on a fresh workspace, (1) `databricks bundle deploy -t dev` (syncs files; pipeline creation fails), (2) run `notebooks/setup_catalog.py` once from the synced files, (3) `databricks bundle deploy -t dev` again. Later deploys are a single deploy. The `setup_catalog` job task cannot help on the first deploy, because terraform creates the pipeline in the same apply, before any job run |
| DA-09 | Secret scope on Free Edition | 4 | None (would block the Kafka path) |

### Bundle and job layout

```yaml
# databricks.yml (sketch; full file built from manifest entry 49)
variables:
  catalog:              { default: smart_meter_dev }
  bronze_schema:        { default: bronze }
  silver_schema:        { default: silver }
  gold_schema:          { default: gold }
  ml_schema:            { default: ml }
  study_start:          { default: "2012-07-01" }
  study_end:            { default: "2014-02-28" }
  cutoff:               { default: "2013-12-01T00:00:00Z" }
  kafka_topic:          { default: meter-readings }
  kafka_sasl_mechanism: { default: SCRAM-SHA-256 }
  secret_scope:         { default: smart_meter }
targets:
  dev: { mode: development, default: true }
  # prod: documented only (catalog smart_meter_prod, mode production, no name prefix), not deployed in v0.1

# resources/smart_meter_ingestion.job.yml (sketch)
jobs:
  smart_meter_ingestion:
    name: smart_meter_ingestion
    max_concurrent_runs: 1
    timeout_seconds: 3600
    schedule: { quartz_cron_expression: "0 0 6 * * ?", timezone_id: UTC }
    email_notifications: { on_failure: ["${workspace.current_user.userName}"] }
    tasks:
      - task_key: setup_catalog        # notebook, timeout 600, max_retries 1
      - task_key: ingest_files         # depends_on setup_catalog, timeout 1800, max_retries 1
      - task_key: ingest_kafka         # depends_on setup_catalog, timeout 840, max_retries 0
      - task_key: refresh_silver_gold  # pipeline_task, depends_on both ingest tasks, timeout 2700, full_refresh false

# resources/smart_meter_silver_gold.pipeline.yml (sketch)
pipelines:
  smart_meter_silver_gold:
    name: smart_meter_silver_gold
    serverless: true
    continuous: false
    channel: CURRENT
    catalog: ${var.catalog}
    schema: ${var.silver_schema}
    event_log: { catalog: ${var.catalog}, schema: ${var.silver_schema}, name: pipeline_event_log }
    configuration:
      spark.sql.session.timeZone: UTC
      smart_meter.src_path: ${workspace.file_path}/src
      smart_meter.catalog: ${var.catalog}
      # plus schema names, study_start, study_end, cutoff
    libraries:
      - file: { path: ../pipelines/meter_pipeline.py }
      - file: { path: ../pipelines/household_data_quality.sql }
```

**Concurrency and failure handling.** At most two tasks run concurrently (the two ingestion
tasks). The Kafka task is configured with `max_retries: 0` and an 840 s timeout, so a broker outage fails it within
15 minutes (AC-10). Live runs showed two attempts of this task per failed job run (probable cause:
the serverless automatic retry, not verified; ADR 0001, DA-12), so "no retry" means configured, not
guaranteed; both attempts fail without writing, and the 15-minute bound held. The pipeline task runs only when both ingestion tasks succeed. A failed Kafka
run therefore leaves Silver unchanged, and the next daily run catches up.

**Development-mode names.** Development mode shows the job and the pipeline as
`[dev <user>] smart_meter_ingestion` and `[dev <user>] smart_meter_silver_gold`. The AC-28 test
strips the prefix with the anchored pattern `^\[dev [^\]]+\] ` and asserts that the remainder
equals the base name exactly. The runbook documents that a `prod` target, deployed in production
mode, has no prefix.

**Kafka source options.**

| Option | Value |
|---|---|
| `subscribe` | the topic (variable `kafka_topic`) |
| `startingOffsets` | `earliest` |
| `failOnDataLoss` | `true` |
| `kafka.security.protocol` | `SASL_SSL` |
| `kafka.sasl.mechanism` | variable `kafka_sasl_mechanism` |
| `kafka.sasl.jaas.config` | built with the `kafkashaded.` SCRAM login module from secret values |
| `kafka.ssl.truststore.type` | `PEM` |
| `kafka.ssl.truststore.certificates` | from the secret `kafka-ca-pem` |
| `kafka.request.timeout.ms` | `30000` |
| `kafka.default.api.timeout.ms` | `60000` |
| `fetchOffset.numRetries` | `3` |

The Bronze projection renames `topic`, `partition`, `offset` and `timestamp` to `_topic`,
`_partition`, `_offset` and `_kafka_timestamp`. It keeps `produced_at` only inside `payload`;
Silver parses it into `_produced_at`.

### Sampling and producer behaviour

**Port of the sampling spike.** `sampling.py` ports `spikes/local/prepare_sample.py` without
changing its algorithm:
- **Plan step.** `random.Random(seed)` shuffles the candidate blocks per group, where a candidate
  block is one whose households, ignoring `ACORN-U` and `ACORN-`, all belong to the group. It
  prefers blocks with distinct dominant ACORN subgroups and takes `blocks_per_group` of them.
- **Build step.** `random.Random(seed)` is created again for the build. For each group:
  - the readings of its blocks are restricted to `[period_start, period_end]`;
  - quality is computed on on-grid readings, with coverage = distinct timestamps /
    (`(end - start) / 30 min + 1`) and the zero ratio;
  - the candidates are shuffled;
  - candidates are excluded with a reason: `no readings in period`, `dead meter` (zero ratio above
    0.9) or `low coverage` (below 0.8);
  - the remaining candidates fill the tariff quotas, where the ToU quota is the population ToU
    share times 20, rounded (4); a shortfall in one tariff is filled from the other.

`config/sample_plan.json` holds the full plan:
- the seed;
- `blocks_per_group` and the chosen blocks, copied from `spikes/local/plan.json`;
- `households_per_group`, `period_start`, `period_end`, `cutoff`, `max_zero_ratio` and
  `min_coverage`.

`config/sample_plan.json` is the source of truth for the plan. `spikes/local/plan.json` is a frozen
historical copy and is never updated. The pinned-households test (AC-02, selection equals
`config/sample_households.csv`) guards against drift between the two.

**Overrides and drift guard.** CLI `--set key=value` overrides any plan field without code
changes (AC-04, FR-16). Whenever `blocks` is present in the plan, `build` reuses it. If `plan`
recomputes blocks that differ from the committed plan, it fails.

**Byte-identical outputs.** Output files are byte-identical to the spike output: same file names
(`historical/readings_YYYY-MM.csv`, `stream/readings_stream.csv`,
`dimensions/households_sample.csv`), same source header (`LCLid,tstp,energy(kWh/hh)` and
`LCLid,stdorToU,Acorn,Acorn_grouped,file`), raw string values (`dtype=str`), same sort order, and
`\n` line endings pinned explicitly. The spike's weather and bank-holiday dimension files are not
ported, because they belong to PEAK_MODEL.

**Manifest.** `manifest.json` keeps the spike's keys and adds the FR-01 items:
- per-household `selection_coverage` (spike denominator) and `zero_share`;
- per-household `coverage_study_period` with the Silver denominator (`48 x` study days, used by
  AC-25);
- the tariff mix per group;
- the SHA-256 of the household file.

It is written with sorted keys, two-space indent, floats rounded to 6 decimals and no timestamp.
The checksums of the data files equal those in `config/sample_manifest.json`.

**Producer.**
- **Input:** reads `readings_stream.csv` (source header) and maps `LCLid` to `household_id`.
- **Event fields:**
  - `reading_ts`: converted to ISO-8601 with `Z`; raw text is passed through when it does not
    parse, so QR-02 catches it.
  - `energy_kwh`: a finite float or `null`.
  - `source`: `replay`.
  - `produced_at`: the UTC wall clock.
- **Ordering and delivery:**
  - sorts by `(reading_ts, household_id)` and keys messages by `household_id`;
  - `enable.idempotence = true`, `acks = all`;
  - pacing by `REPLAY_SPEED` (event seconds per wall second, `0` = no pacing);
  - exits non-zero on any delivery error.
- **Testing:** `--dry-run` writes JSON lines to stdout.

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| 0001 | Runtime environment constraints for Free Edition and Aiven (A-01 validated, A-13 resolved; spikes pending; fallbacks) | Proposed |
| 0002 | Aiven Kafka with SASL_SSL SCRAM and credentials in a secret scope | Proposed |
| 0003 | Unity Catalog layout `smart_meter_dev` created by an idempotent setup task (OD-05, A-09 fallback) | Proposed |
| 0004 | One Lakeflow pipeline for Silver and Gold, with a rule-evaluation materialized view feeding quarantine and metrics (OD-02, OD-04, OD-06) | Proposed |
| 0005 | First-ingested-wins deduplication with `row_number()` in materialized views (OD-01, OD-03) | Proposed |
| 0006 | Bronze tables, not Kafka, are the replay and reprocessing source | Proposed |

---

## Delivery Plan

The feature ships as three pull requests. PR 2 is split into 2a and 2b so that each PR stays at
or below about 25 files. The BUILD_REPORT has one file for the whole feature and stays
`In Progress` until PR 3. It records which PR delivered each file and each AC's evidence.

| PR | Scope | Manifest entries | Files |
|---|---|---|---|
| PR 1 (gate) | Spikes, ADR results, sampling port, plan, producer and their tests | 1 to 23 | 22, plus up to 5 conditional ADR updates (entry 11) |
| PR 2a | Library modules, summary SQL, CI Java, unit tests | 24 to 42, plus 30a | 20 |
| PR 2b | Notebooks, pipeline, bundle, wiring and bundle tests | 43 to 52 | 10 (one of them a deletion) |
| PR 3 | Integration tests, runbook, README; integration and manual evidence | 53 to 60 | 8 |

**Gate after PR 1.** PR 2a starts only when ADR 0001 records results for every spike. If any of
the following assumptions fails, this DESIGN is updated through `/iterate` before PR 2a, and PR 2
is built against the validated design:
- A-03 (inline PEM truststore);
- A-10 (triggered pipeline on Free Edition);
- DA-01 (MV expectation metrics in the event log on Free Edition);
- A-09 (`CREATE CATALOG`).

A fallback that is purely a configuration change still needs that `/iterate`, so that the DESIGN
stays the source of truth. Examples are the A-06 mechanism variable and the A-09 variable
overrides.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Package path
`src/smart_meter_peak_prediction/` is abbreviated `pkg/`. Agents:
- `pipeline-builder`: Databricks code and the bundle;
- `streaming-engineer`: Kafka producer and consumer;
- `build-agent`: everything else.

Existing inputs, read by the build and not created or modified by it:
- `config/sample_households.csv`: pinned seed-42 selection.
- `config/sample_manifest.json`: reference counts and checksums.
- `spikes/local/prepare_sample.py` and `spikes/local/plan.json`: source of the port; never imported by `src/`.

| # | PR | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|---|
| 1 | 1 | `spikes/local/a08_offgrid_null_cooccurrence.py` | Create | A-08: on the 9 profiled blocks, check that off-grid `tstp` rows are exactly the `Null` energy rows. Prints counts and PASS/FAIL (AC-11) | build-agent | - |
| 2 | 1 | `spikes/databricks/00_setup_catalog.py` | Create | A-09 and DA-06: create catalog, schemas and Volumes; record whether deploy works before the catalog exists (AC-28, AC-32) | pipeline-builder | - |
| 3 | 1 | `spikes/databricks/01_spike_autoloader.py` | Create | A-02: Auto Loader CSV from a Volume with `availableNow`. The read schema uses the source header names, including `energy(kWh/hh)`, with `_rescued_data` and `_metadata.file_path`; renames before writing. A second run ingests 0 rows (AC-05, AC-06, AC-32) | pipeline-builder | 2 |
| 4 | 1 | `spikes/databricks/02_spike_kafka_consume.py` | Create | A-03, A-05, DA-09 (A-06 read from the Aiven console): read secrets from the scope, SASL_SSL SCRAM with an inline PEM CA, `availableNow` into a scratch table with `_`-prefixed metadata (AC-07, AC-29, AC-32) | streaming-engineer | 2 |
| 5 | 1 | `spikes/databricks/03_spike_kafka_unreachable.py` | Create | DA-05: with the service powered off, measure time to failure with the planned timeouts; the checkpoint stays unchanged (AC-10, AC-32) | streaming-engineer | 4 |
| 6 | 1 | `spikes/databricks/04_spike_lakeflow_pipeline/pipeline.py` | Create | A-10, DA-01, DA-02, DA-07, DA-08. Private MV with `row_number()` dedup and warn counters, including a row that fails two counters. Event log reports per-rule metrics for MV expectations on Free Edition (held); the check that a second update with no new input reports the same totals failed (DA-01 partial, ADR 0001), which led to the table-totals fallback. `expect_or_fail` aborts with 0 rows committed and downstream MVs keep their contents. Fully qualified names in two schemas, `sys.path` import, session time zone. Also times one update over a synthetic Bronze of 1.7 M rows, to check early that a full recompute fits AC-30 (AC-12, AC-15, AC-26, AC-30, AC-34) | pipeline-builder | 2 |
| 7 | 1 | `spikes/databricks/04_spike_lakeflow_pipeline/summary_view.sql` | Create | DA-02: `CREATE VIEW` published to UC from a pipeline SQL file (AC-25, AC-26) | pipeline-builder | 6 |
| 8 | 1 | `spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py` | Create | Creates the spike pipeline with `event_log` publication (DA-03) through databricks-sdk, runs two updates, asserts the outcomes, prints PASS/FAIL, then deletes the pipeline, since only one pipeline per type is allowed (AC-12, AC-32) | pipeline-builder | 6, 7 |
| 9 | 1 | `docs/adr/0001-runtime-environment-constraints.md` | Update | Record every spike result and applied fallback; the user moves it to Accepted (AC-32) | build-agent | 1 to 8 |
| 10 | 1 | `docs/spikes/README.md` | Update | Spike record rows for spikes 00 to 04, A-08 and the sampling spike (AC-32) | build-agent | 9 |
| 11 | 1 | `docs/adr/0002-...` to `0006-...` (only those affected) | Update (conditional) | Adjust to spike outcomes, for example the A-09 fallback in 0003 or the DA-02 fallback in 0004. The user sets the status (AC-28, AC-32) | build-agent | 9 |
| 12 | 1 | `pyproject.toml` | Update | Extras `sample` (pandas), `producer` (confluent-kafka), `integration` (databricks-sdk). Dev adds pyspark (>=3.5,<4.1) and pyyaml. Markers `integration` and `local_data`; `addopts = -m 'not integration and not local_data'` | build-agent | - |
| 13 | 1 | `.env.example` | Update | Add `KAFKA_TOPIC`, `REPLAY_SPEED`, `SAMPLE_STREAM_FILE` and `DATABRICKS_WAREHOUSE_ID` placeholders, with no values (AC-29) | build-agent | - |
| 14 | 1 | `config/sample_plan.json` | Create | Full committed plan: the seed and blocks from `spikes/local/plan.json`, plus period, cutoff and thresholds from the spike defaults (AC-01 to AC-04) | build-agent | - |
| 15 | 1 | `pkg/sampling.py` | Create | Port of the spike's `plan` and `build` with pinned output bytes and the extended manifest (AC-01 to AC-04, AC-25) | build-agent | 12, 14 |
| 16 | 1 | `scripts/prepare_sample.py` | Create | CLI: `plan` and `build` subcommands, `--plan`, `--set key=value`, `--raw-dir`, `--out` (AC-01, AC-04) | build-agent | 15 |
| 17 | 1 | `pkg/producer.py` | Create | Event building per the topic contract, ordering, pacing, confluent-kafka config from the environment, delivery checks, `--dry-run`, `python -m` entry point (AC-07, AC-09, AC-29, AC-31) | streaming-engineer | 12 |
| 18 | 1 | `docker/producer/Dockerfile` | Create | python:3.11-slim, installs the package with the `producer` extra. Credentials only via `--env-file .env`; the sample and the CA are mounted read-only (AC-07, AC-29) | streaming-engineer | 17 |
| 19 | 1 | `.dockerignore` | Create | Exclude `.env`, `data/`, `*.pem` and `.git` from the build context (AC-29) | streaming-engineer | 18 |
| 20 | 1 | `tests/test_sampling.py` | Create | Unit tests on a synthetic raw dataset (AC-01 to AC-04) | build-agent | 15, 16 |
| 21 | 1 | `tests/local_data/test_sample_seed42.py` | Create | Marker `local_data`: exact selection equals `config/sample_households.csv`; counts and checksums equal `config/sample_manifest.json` (AC-01 to AC-04) | build-agent | 15, 16 |
| 22 | 1 | `tests/test_producer.py` | Create | Contract conformance, null energy, ordering, environment-only credentials (AC-07, AC-29) | streaming-engineer | 17 |
| 23 | 1 | `tests/test_runtime_adr.py` | Create | ADR 0001 records a result for A-01, A-02, A-03, A-05, A-06, A-09 and A-10; `check_specs.run` reports 0 errors (AC-32) | build-agent | 9 |
| 24 | 2a | `.github/workflows/ci.yml` | Update | `actions/setup-java` (Temurin 17) before the tests, so local Spark runs in CI; stays free of secrets (AC-29) | build-agent | 12 |
| 25 | 2a | `pkg/config.py` | Create | `Settings` dataclass built from job parameters or pipeline configuration; fully qualified table, Volume and checkpoint names for the main and fallback layouts; study and cutoff literals (AC-04, AC-16, AC-28) | pipeline-builder | 12 |
| 26 | 2a | `pkg/rules.py` | Create | Rule catalog: id, expectation name, SQL builder (settings-aware), action, dataset; precedence; helpers that return the dicts for `expect_all` and `expect_all_or_fail` (AC-12, AC-15, AC-16, AC-34) | pipeline-builder | 25 |
| 27 | 2a | `pkg/bronze.py` | Create | Source-header CSV read schemas and Bronze renames; projections with `_metadata.file_path`, `current_timestamp()` and `_`-prefixed Kafka metadata; Auto Loader reader; Kafka options builder; `availableNow` writer with checkpoint (AC-05 to AC-08, AC-10, AC-19, AC-29) | streaming-engineer | 25 |
| 28 | 2a | `pkg/silver.py` | Create | Parse expressions, `_source_ref`, `_dedup_key`, rule evaluation, `row_number()` dedup for valid rows (`dedup_rank`) and dropped rows (`quarantine_rank`, `is_quarantine_duplicate`, `is_quarantined`), INV-01 count, Silver, quarantine and household projections (AC-09, AC-11, AC-13 to AC-18, AC-20, AC-27, AC-34) | pipeline-builder | 26 |
| 29 | 2a | `pkg/gold.py` | Create | Daily aggregation, orphan check, study months, dense monthly quality with gaps and `has_household_record` (AC-21 to AC-24, AC-33, AC-35) | pipeline-builder | 28 |
| 30 | 2a | `pkg/metrics.py` | Create | SQL builders: rule, scope and duplicate counts as table totals over `silver.meter_readings_evaluated` (`array_contains(failed_rules, R) AND NOT is_quarantine_duplicate`, `is_out_of_scope`, `is_duplicate`, `is_quarantine_duplicate`, `count(*)`), QR-10/12/14/15 counts over the published tables, AC-11 reconciliation with the class quarantine duplicate, order-independent checksums (`count(*)`, `sum(cast(xxhash64(...) AS DECIMAL(38,0)))`), plus one optional event-log observability query (AC-09, AC-11, AC-12, AC-16, AC-17, AC-27, AC-34) | pipeline-builder | 26, 28 |
| 30a | 2a | `docs/contracts/silver_meter_readings_evaluated.yaml` | Create (updated 2026-10-19 with `_dedup_key`, `quarantine_rank`, `is_quarantine_duplicate`, `is_quarantined`; the quarantine contract `silver_meter_readings_quarantine.yaml` gained `_dedup_key`) | `kind: table` contract for the published evaluation MV (`object_type: materialized view`, owner METER_INGESTION, `primary_key: [_source_ref]`, columns of the Data Model row, consumer: metrics and reconciliation, marked ops and not for PEAK_MODEL). `check_specs.py` validates it (AC-12, AC-19) | build-agent | 28 |
| 31 | 2a | `pipelines/household_data_quality.sql` | Create | `CREATE VIEW` of the summary from the monthly table, with configuration substitution for names and `has_household_record` (AC-25, AC-35) | pipeline-builder | 29 |
| 32 | 2a | `tests/conftest.py` | Create | Session `spark` fixture: `local[2]`, `spark.sql.session.timeZone=UTC`, 2 shuffle partitions | build-agent | 12 |
| 33 | 2a | `tests/support/builders.py` | Create | Builders for Bronze file, Kafka and household rows; rule, DST and gap fixtures | build-agent | 32 |
| 34 | 2a | `tests/support/harness.py` | Create | Local pipeline harness: runs the `silver.py` and `gold.py` functions in pipeline order over Bronze DataFrame snapshots and applies the rule catalog (drop routing, fail raises `ExpectationFailed`). It exposes the evaluation DataFrame, which tests pass to the `metrics.py` count SQL; the warn expectations are also evaluated, for the wiring and catalog checks only. Each "update" recomputes from the given Bronze snapshot, as the MVs do | build-agent | 26, 28, 29, 33 |
| 35 | 2a | `tests/test_bronze.py` | Create | Projections, naming and Kafka options (AC-05, AC-07, AC-10, AC-19, AC-29) | streaming-engineer | 27 |
| 36 | 2a | `tests/test_silver_readings.py` | Create | Rules, quarantine, scope, cutoff, reconciliation, counts (AC-11 to AC-16, AC-34) | pipeline-builder | 34 |
| 37 | 2a | `tests/test_silver_dedup.py` | Create | Ranking, ties, replays, determinism under input order (AC-09, AC-11, AC-17, AC-27) | pipeline-builder | 34 |
| 38 | 2a | `tests/test_silver_households.py` | Create | Household projection and QR-13 to QR-15 (AC-15, AC-18) | pipeline-builder | 34 |
| 39 | 2a | `tests/test_gold_daily.py` | Create | Daily aggregates, QR-10 to QR-12, DST days (AC-15, AC-20, AC-21) | pipeline-builder | 34 |
| 40 | 2a | `tests/test_gold_quality.py` | Create | Monthly facts, gaps, point in time, dense rows, union household set, summary SQL (AC-22 to AC-25, AC-33, AC-35) | pipeline-builder | 31, 34 |
| 41 | 2a | `tests/test_contract_schemas.py` | Create | Library output schemas (including the evaluation table, contract 30a) equal the contract YAML names and types; naming rule without exceptions (AC-19) | build-agent | 27, 28, 29 |
| 42 | 2a | `tests/test_secrets_hygiene.py` | Create | Scans `git ls-files` for the broker host, SASL user and password (values from the local environment when set) and for generic credential patterns (AC-29) | build-agent | - |
| 43 | 2b | `notebooks/setup_catalog.py` | Create | Idempotent `CREATE CATALOG/SCHEMA/VOLUME/TABLE IF NOT EXISTS`, with Bronze DDL and `delta.appendOnly` (AC-19, AC-28) | pipeline-builder | 25, 27 |
| 44 | 2b | `notebooks/ingest_files.py` | Create | Auto Loader `availableNow` streams for readings, then households, each with its own checkpoint (AC-05, AC-06) | pipeline-builder | 27, 43 |
| 45 | 2b | `notebooks/ingest_kafka.py` | Create | Secrets from the scope; Kafka `availableNow` stream into Bronze; never prints options (AC-07, AC-08, AC-10, AC-29) | streaming-engineer | 27, 43 |
| 46 | 2b | `pipelines/meter_pipeline.py` | Create | Thin wiring: settings from configuration, UTC assertion, published MVs (including `silver.meter_readings_evaluated`, by fully qualified name, no `private=True`) and private check MVs, all expectations from `rules.py` (AC-11 to AC-18, AC-20 to AC-24, AC-26, AC-27, AC-33 to AC-35) | pipeline-builder | 26, 28, 29, 31 |
| 47 | 2b | `resources/jobs.yml` | Delete | Remove the template example job | pipeline-builder | - |
| 48 | 2b | `resources/smart_meter_silver_gold.pipeline.yml` | Create | Serverless, triggered pipeline with configuration, event log publication and libraries (AC-26, AC-28) | pipeline-builder | 31, 46 |
| 49 | 2b | `databricks.yml` | Update | Bundle variables for layout, period, cutoff, topic, mechanism and scope; `dev` target; `prod` documented in comments only (AC-04, AC-28) | pipeline-builder | 48 |
| 50 | 2b | `resources/smart_meter_ingestion.job.yml` | Create | Daily job with four tasks, dependencies, timeouts, retries, `max_concurrent_runs: 1`, UTC schedule and failure email (AC-10, AC-28, AC-30, AC-31) | pipeline-builder | 43, 44, 45, 48, 49 |
| 51 | 2b | `tests/test_pipeline_wiring.py` | Create | Imports `pipelines/meter_pipeline.py` with a recording fake `dlt` module; checks datasets, MV kinds and expectations against `rules.py` (AC-12, AC-26) | pipeline-builder | 46 |
| 52 | 2b | `tests/test_bundle_config.py` | Create | Parses the bundle YAML: one serverless triggered pipeline, names, schedule, concurrency, timeouts, secret usage, variables equal to the plan defaults (AC-10, AC-26, AC-28 to AC-30) | pipeline-builder | 48, 49, 50 |
| 53 | 3 | `tests/integration/conftest.py` | Create | databricks-sdk client (CLI profile or environment), SQL through the Statement Execution API on the Free Edition warehouse, settings, manifest loader, evidence snapshots in `out/evidence/` | build-agent | 12, 30 |
| 54 | 3 | `tests/integration/test_bronze_ingestion.py` | Create | AC-05 to AC-08, AC-10 | streaming-engineer | 53 |
| 55 | 3 | `tests/integration/test_silver_tables.py` | Create | AC-11 to AC-14, AC-18 to AC-20, AC-34 | pipeline-builder | 53 |
| 56 | 3 | `tests/integration/test_gold_tables.py` | Create | AC-21, AC-22, AC-25, AC-26, AC-31, AC-35 | pipeline-builder | 53 |
| 57 | 3 | `tests/integration/test_reprocessing.py` | Create | Two-step snapshot tests for AC-09, AC-24, AC-27 | pipeline-builder | 53 |
| 58 | 3 | `tests/integration/test_deployment.py` | Create | AC-28 and AC-30 through the jobs, pipelines and tables APIs | pipeline-builder | 53 |
| 59 | 3 | `docs/runbooks/meter_ingestion.md` | Create | Runbook covering (AC-09, AC-10, AC-27, AC-28): secret scope setup; sample generation and upload; Aiven power-on; producer run; deploy (first-deploy order of DA-06: deploy, run `setup_catalog.py` from the synced files, deploy again; including `prod` without name prefix); job run; evidence order for integration tests; broker outage; full refresh; Bronze reset | build-agent | 50, 58 |
| 60 | 3 | `README.md` | Update | Architecture summary, quick start, links to the runbook, contracts and ADRs | build-agent | 59 |

---

## Test Strategy

Every acceptance criterion from DEFINE appears here. Levels:
- **Unit:** pytest with local Spark or pure Python; runs in CI.
- **Local data:** pytest marker `local_data`; needs `data/raw`.
- **Integration:** pytest marker `integration`; runs against the deployed `dev` target.
- **Manual / evidence:** a scripted operator step from the runbook whose output is pasted into
  the build report.

Every test name contains its AC id (golden rule 3). Integration tests that need a before and an
after state store a snapshot in `out/evidence/` in a `*_before` test and compare it in the
`*_after` test. The runbook gives the order. Rule, scope and duplicate counts are table totals
from `metrics.py` over `silver.meter_readings_evaluated` (see *Column derivations*, DA-01
fallback). An AC that compares an input with its effect compares totals before and after, or
totals on a fixture. No test reads counts from the event log.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-01 | Unit | `tests/test_sampling.py::test_ac01_same_plan_produces_identical_checksums` | Synthetic raw blocks, two runs into two temp folders; the SHA-256 of every file and of the manifest are equal |
| AC-01 | Local data | `tests/local_data/test_sample_seed42.py::test_ac01_seed42_reruns_are_byte_identical` | Two runs on the real raw files are identical, and the data-file checksums equal `config/sample_manifest.json` |
| AC-02 | Unit | `tests/test_sampling.py::test_ac02_selection_respects_strata_and_exclusions` | Synthetic data with invalid ACORN, dead and low-coverage households: quotas met, exclusions recorded with reasons, household file equals the selection |
| AC-02 | Local data | `tests/local_data/test_sample_seed42.py::test_ac02_src_sampling_selects_exactly_the_pinned_households` | The `src/` port (not the spike) selects the same set of ids (`LCLid`) and the same attributes as `config/sample_households.csv`: 60 households, 20 per group, 16 Std and 4 ToU per group (48 / 12 in total), and none with `ACORN-U` or `ACORN-`. Every exclusion has a reason, and the household file holds exactly these 60 |
| AC-02 | Local data | `tests/local_data/test_sample_seed42.py::test_ac02_src_sampling_counts_match_pinned_manifest` | Total, historical, stream and non-numeric row counts, plus per-file rows, equal `config/sample_manifest.json`. Selected households have coverage >= 0.8 and zero share < 0.9 |
| AC-03 | Unit | `tests/test_sampling.py::test_ac03_split_respects_cutoff_without_overlap` | Strict `<` / `>=` split, with no key in both outputs |
| AC-03 | Local data | `tests/local_data/test_sample_seed42.py::test_ac03_seed42_split_counts_match_pinned_manifest` | 1,432,405 historical and 247,569 stream rows; per-file rows and checksums equal `config/sample_manifest.json` |
| AC-04 | Unit | `tests/test_sampling.py::test_ac04_cutoff_override_moves_boundary_without_code_change` | `--set cutoff=2013-11-01 00:00:00` through the CLI moves the boundary, and the totals are unchanged |
| AC-04 | Local data | `tests/local_data/test_sample_seed42.py::test_ac04_seed42_cutoff_2013_11_01_preserves_total` | Same on the real data |
| AC-05 | Unit | `tests/test_bronze.py::test_ac05_file_projection_has_bronze_columns_and_metadata` | The source-header read is renamed to the Bronze schema, with non-null `_source_file` and `_ingested_at` |
| AC-05 | Integration | `tests/integration/test_bronze_ingestion.py::test_ac05_bronze_file_counts_match_manifest` | Row counts equal the manifest (1,432,405 and 60); 0 rows with null metadata |
| AC-06 | Integration | `tests/integration/test_bronze_ingestion.py::test_ac06_rerun_file_ingestion_adds_no_rows` | Snapshot the counts, rerun task `ingest_files`; the counts are unchanged |
| AC-07 | Unit | `tests/test_producer.py::test_ac07_event_matches_topic_contract_schema` | Dry-run events parse with the contract value schema; types and nullability match the contract |
| AC-07 | Unit | `tests/test_producer.py::test_ac07_non_numeric_energy_becomes_null_not_dropped` | `Null` and padded values produce `energy_kwh = null` or a float; the event count equals the input rows |
| AC-07 | Unit | `tests/test_bronze.py::test_ac07_kafka_projection_keeps_raw_payload_and_offsets` | The Kafka projection yields exactly `kafka_key`, `payload`, `_topic`, `_partition`, `_offset`, `_kafka_timestamp` and `_ingested_at` (no `produced_at` outside the payload) |
| AC-07 | Integration | `tests/integration/test_bronze_ingestion.py::test_ac07_kafka_bronze_count_uniqueness_and_payload_parse` | 247,569 rows; `(_topic, _partition, _offset)` unique; 0 nulls; every payload has `payload_ok` |
| AC-08 | Integration | `tests/integration/test_bronze_ingestion.py::test_ac08_rerun_kafka_ingestion_adds_no_rows` | Rerun task `ingest_kafka` with no new message; the count is unchanged |
| AC-09 | Unit | `tests/test_silver_dedup.py::test_ac09_replayed_messages_counted_as_duplicates_and_silver_unchanged` | Harness: the Bronze snapshot gains every Kafka row again with a later `_ingested_at`. Silver and quarantine checksums are equal, and the QR-09 total from `metrics.py` (`is_duplicate` rows of the evaluation output) rises by the number of replayed rows |
| AC-09 | Unit | `tests/test_silver_dedup.py::test_ac09_replayed_invalid_messages_not_quarantined_again` (replaces the I-15 test that documented re-quarantine) | Fixture with valid and invalid Kafka messages (QR-07 with an unparseable payload, QR-07 with a readable key, QR-03 plus QR-04, QR-05). Every message is delivered again with new offsets, a later `_ingested_at` and, for payloads that carry a `produced_at`, a different `produced_at`. Silver and quarantine counts and checksums are unchanged, every per-rule total is unchanged, the QR-09 total rises by the number of replayed messages, and the first-ingested row is the one kept in the quarantine |
| AC-09 | Unit | `tests/test_silver_dedup.py::test_ac09_dedup_key_is_per_path_and_offset_independent` | `_dedup_key` is equal for a replay and different for a files row and a Kafka row with the same raw values; a payload that is not JSON, not an object, or lacks or nulls `household_id` or `reading_ts` hashes the payload; a files row without a household id or timestamp uses the record hash |
| AC-09 | Unit | `tests/test_silver_dedup.py::test_ac09_replayed_partially_parseable_invalid_payload_not_quarantined_again` | A payload that fails QR-07 but has a readable `household_id` and `reading_ts` (null `source`; a second case with a wrong type in `energy_kwh`) is delivered again with new offsets, a later `_ingested_at` and a new `produced_at`. The key is `kafka:key:<household_id>#<reading_ts>` for both rows, the quarantine keeps the first row only, quarantine counts and checksums are unchanged, no per-rule total rises, and the QR-09 total rises by the replays. A non-object JSON payload (for example an array) keeps the `kafka:payload:` hash key |
| AC-09 | Integration | `tests/integration/test_reprocessing.py::test_ac09_before_replay_snapshot` and `::test_ac09_after_replay_silver_unchanged` | The `_before` test stores the QR-09 total (rows with `is_duplicate` in `silver.meter_readings_evaluated`) and the Silver and quarantine counts and checksums. After the replay and a pipeline update, Bronze Kafka has grown by 247,569; Silver and quarantine counts and checksums are unchanged; the QR-09 total is higher by 247,569 (247,569 for a seed-42 run with no earlier duplicates). The seed-42 stream holds no invalid message, so the invalid-message clause of AC-09 is proven by the unit tests above (fixture AC), with no extra live step |
| AC-10 | Unit | `tests/test_bronze.py::test_ac10_kafka_options_bound_broker_timeouts` | The options contain the request and API timeouts and the retry count |
| AC-10 | Unit | `tests/test_bundle_config.py::test_ac10_kafka_task_fails_within_15_minutes` | `ingest_kafka` has `timeout_seconds <= 900` and `max_retries = 0`; the pipeline task depends on it |
| AC-10 | Manual / evidence | Runbook "Broker outage" + `tests/integration/test_bronze_ingestion.py::test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged` | Power off Aiven and run the job: the task fails within 15 min (possibly in two attempts, ADR 0001 DA-12), and the Bronze count and checkpoint offsets are unchanged. After power-on the topic is empty and its offsets are reset (ADR 0001 DA-11), so recovery is a Kafka reset (drop the Kafka Bronze table and its checkpoint, re-produce the sample); the next run then passes the AC-07 checks |
| AC-11 | Unit | `tests/test_silver_readings.py::test_ac11_every_bronze_row_classified_exactly_once` | Harness on a mixed fixture that includes a replayed invalid row: the reconciliation SQL from `metrics.py` (five classes: Silver, quarantine, duplicate, quarantine duplicate, outside the period) returns 0 unclassified and 0 double-classified rows |
| AC-11 | Unit | `tests/test_silver_dedup.py::test_ac11_source_ref_unique_per_bronze_row` | `_source_ref` follows the specified formats and is unique; INV-01 fails on a duplicated CSV line |
| AC-11 | Integration | `tests/integration/test_silver_tables.py::test_ac11_reconciliation_classifies_every_bronze_row` | Seed 42: 60 quarantined (or the A-08 result), 0 outside the period, 0 duplicates, 0 quarantine duplicates, 1,679,914 in Silver, 0 unclassified |
| AC-12 | Unit | `tests/test_silver_readings.py::test_ac12_rule_counts_equal_quarantine_failed_rules_per_update` (name kept) | Harness over two updates (normal and full refresh). After each, the table totals from `metrics.py` over the evaluation output satisfy: the evaluated row count equals the Bronze rows; per-rule counts equal the quarantine rows whose `failed_rules` contain the rule (the fixture includes a replayed invalid row, which raises no per-rule count); the quarantine rows equal the rows failing at least one drop rule that are not quarantine duplicates; scope and duplicate totals are present, and the duplicate total equals the valid duplicates plus the quarantine duplicates. Both updates give equal totals |
| AC-12 | Unit | `tests/test_pipeline_wiring.py::test_ac12_pipeline_expectations_match_rule_catalog` | Every counter and fail expectation of `rules.py` is attached to `silver.meter_readings_evaluated` with the stated action, and that dataset is declared published (fully qualified name, not private) |
| AC-12 | Integration | `tests/integration/test_silver_tables.py::test_ac12_update_rule_counts_match_quarantine_rows` (name kept) | On the current state after the latest update, and again after a full refresh: `count(*)` of `silver.meter_readings_evaluated` equals the rows of both Bronze reading tables. Per-rule totals from `metrics.py` equal the rows of `silver.meter_readings_quarantine` exploded by `failed_rules`, and `_dedup_key` is unique in the quarantine. The `is_out_of_scope` and `is_duplicate` totals are present, `is_duplicate` equals the valid duplicates plus `is_quarantine_duplicate`, and `is_silver` rows equal `silver.meter_readings`. No time window applies, because the totals are table state (event log not read) |
| AC-13 | Unit | `tests/test_silver_readings.py::test_ac13_silver_invariants_hold_on_mixed_fixture` | Silver has no duplicate keys and no off-grid, negative, null-energy, out-of-period or quarantined-ref rows |
| AC-13 | Integration | `tests/integration/test_silver_tables.py::test_ac13_silver_invariants` | The same five queries on the deployed table |
| AC-14 | Unit | `tests/test_silver_readings.py::test_ac14_cutoff_boundary_rows_appear_once_with_correct_path` | Rows at 2013-11-30T23:30Z (files) and 2013-12-01T00:00Z (Kafka) appear once, with the right path |
| AC-14 | Integration | `tests/integration/test_silver_tables.py::test_ac14_cutoff_rows_once_with_ingestion_path` | The path matches the side of the cutoff; boundary readings from the sample are present exactly once |
| AC-15 | Unit | `tests/test_silver_readings.py::test_ac15_each_drop_rule_quarantines_its_row` | Parametrized QR-02, QR-03, QR-04, QR-05, QR-07: exactly that row is quarantined, with that `rule_name` and its `_ingested_at` |
| AC-15 | Unit | `tests/test_silver_readings.py::test_ac15_warn_rule_qr08_keeps_row_and_counts_one` | The row with `_rescued_data` is in Silver; count 1 |
| AC-15 | Unit | `tests/test_silver_readings.py::test_ac15_fail_rules_qr01_qr06_abort_update` | Parametrized null id, `MAC12345`, `mac000002`, `MAC0000021`, a files row after the cutoff and a Kafka row before it: the harness raises and nothing is written |
| AC-15 | Unit | `tests/test_silver_readings.py::test_ac15_well_formed_unknown_household_passes_silver` | `MAC999999` is in Silver |
| AC-15 | Unit | `tests/test_gold_daily.py::test_ac15_qr10_and_qr12_warn_counts` | The incomplete day is reported once; `MAC999999` is reported once by QR-12 |
| AC-15 | Unit | `tests/test_gold_daily.py::test_ac15_qr11_fails_on_49_readings_for_one_day` | 49 readings fed directly to the daily aggregation fail QR-11 |
| AC-15 | Unit | `tests/test_silver_households.py::test_ac15_household_rules_qr13_fail_qr14_qr15_warn` | A duplicate id fails; an invalid group and an invalid tariff are counted once each and kept |
| AC-15 | Manual / evidence | Spike 04 output recorded in ADR 0001 (`spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py`) | Proves on the platform that `expect_or_fail` aborts with 0 rows committed. Counters report per rule and double-count a row failing two rules, but not for an update that skips the refresh (DA-01 partial), which is why the AC counts come from the evaluation table |
| AC-16 | Unit | `tests/test_silver_readings.py::test_ac16_study_period_boundaries_and_scope_count` | 2012-07-01T00:00Z and 2014-02-28T23:30Z are in Silver; the two outer rows are nowhere; the SF-01 total (`is_out_of_scope` rows, from `metrics.py`) is 2 |
| AC-17 | Unit | `tests/test_silver_dedup.py::test_ac17_earlier_ingested_at_wins_and_tie_uses_smaller_source_ref` | Two duplicate pairs, each on its own `(household_id, reading_ts)`: two files rows with different `_ingested_at`, where the earlier has the larger `_source_ref` (the earlier row wins, not the smaller ref), and two Kafka rows with equal `_ingested_at` and different offsets (the smaller `_source_ref` wins). A files and a Kafka row cannot share a key, because QR-06 admits files rows before the cutoff and Kafka rows at or after it. The QR-09 total (`is_duplicate` rows, from `metrics.py`) is 2 |
| AC-17 | Unit | `tests/test_silver_dedup.py::test_ac17_rerun_keeps_same_winners` | The same input run again, in reversed order and with a different partitioning, keeps the same winners (identical Silver) and the total 2 |
| AC-18 | Unit | `tests/test_silver_households.py::test_ac18_households_are_typed_and_renamed` | Contract columns from the source-header file, trimmed values, `_ingested_at` copied |
| AC-18 | Integration | `tests/integration/test_silver_tables.py::test_ac18_silver_households_seed42` | 60 unique rows, valid groups and tariffs, 20 per group |
| AC-19 | Unit | `tests/test_contract_schemas.py::test_ac19_output_schemas_match_contracts` | Library outputs (Bronze projections, Silver, quarantine, Gold) equal each contract's names and types |
| AC-19 | Unit | `tests/test_contract_schemas.py::test_ac19_no_source_column_names_and_processing_columns_prefixed` | No `LCLid`, `tstp` or `energy(kWh/hh)` in any table. Every processing-time or transport-metadata column starts with `_`, with no exceptions (`_kafka_timestamp`, `_topic`, `_partition`, `_offset`, `_produced_at`) |
| AC-19 | Integration | `tests/integration/test_silver_tables.py::test_ac19_deployed_columns_match_contracts` | `information_schema.columns` equals the contracts (including `silver_meter_readings_evaluated.yaml`) and the inline Bronze schemas, with the same naming rule |
| AC-20 | Unit | `tests/test_gold_daily.py::test_ac20_dst_change_days_have_48_utc_readings` | A fixture with source text across 2013-03-31 and 2013-10-27 has 48 readings per UTC day after parsing |
| AC-20 | Integration | `tests/integration/test_silver_tables.py::test_ac20_dst_days_have_48_readings` | Households with 48 readings on both neighbouring days have 48 on each DST day |
| AC-21 | Unit | `tests/test_gold_daily.py::test_ac21_daily_aggregates_match_recomputation` | Totals and maxima within 1e-9, counts equal, flag exact |
| AC-21 | Integration | `tests/integration/test_gold_tables.py::test_ac21_daily_consumption_matches_silver_recomputation` | MV type and recomputation; complete-day share between 98.5% and 99.5%; the QR-10 total from `metrics.py` (days with `is_complete_day = false`) equals the incomplete days |
| AC-22 | Unit | `tests/test_gold_quality.py::test_ac22_expected_readings_per_month` | 1,488 for 31-day months, 1,344 for February 2014, 29,184 in total |
| AC-22 | Unit | `tests/test_gold_quality.py::test_ac22_monthly_facts_match_recomputation` | An independent pandas recomputation equals the Spark output |
| AC-22 | Integration | `tests/integration/test_gold_tables.py::test_ac22_monthly_quality_matches_independent_recomputation` | 1,200 rows, unique key, SQL recomputation equal for 100% of rows |
| AC-23 | Unit | `tests/test_gold_quality.py::test_ac23_gap_count_per_month` | Leading slots, 1-slot and 3-slot gaps, a boundary-spanning gap and trailing slots give 2, 1 and 0 |
| AC-24 | Unit | `tests/test_gold_quality.py::test_ac24_appending_later_months_keeps_earlier_rows` | Rows for months <= M are identical after M + 1 readings are appended |
| AC-24 | Integration | `tests/integration/test_reprocessing.py::test_ac24_before_kafka_snapshot` and `::test_ac24_after_kafka_months_up_to_november_unchanged` | Snapshot after a files-only build, then compare after the Kafka months arrive |
| AC-25 | Unit | `tests/test_gold_quality.py::test_ac25_summary_ratios_and_zero_share` | Runs the SQL body of `household_data_quality.sql` locally: ratios within 1e-9; the 100%-zero household has `zero_share = 1.0` |
| AC-25 | Unit | `tests/test_gold_quality.py::test_ac25_summary_has_no_threshold_flag_or_label_columns` | Column names contain none of threshold, flag, excluded or label (`has_household_record` is a fact, not a flag in this sense: the test checks the forbidden substrings) |
| AC-25 | Integration | `tests/integration/test_gold_tables.py::test_ac25_summary_matches_monthly_and_manifest` | One row per household; the recomputation is equal; coverage is within 0.001 of the manifest's `coverage_study_period` |
| AC-26 | Unit | `tests/test_pipeline_wiring.py::test_ac26_pipeline_defines_all_silver_and_gold_objects` | The fake `dlt` records the Silver, quarantine, households and Gold datasets. `silver.meter_readings`, `silver.meter_readings_quarantine` and both Gold tables are declared as MVs (batch `@dlt.table` over batch reads), with no streaming reads |
| AC-26 | Unit | `tests/test_bundle_config.py::test_ac26_single_serverless_triggered_pipeline` | One pipeline resource, `serverless: true`, `continuous: false` |
| AC-26 | Integration | `tests/integration/test_gold_tables.py::test_ac26_pipeline_and_table_metadata` | Exactly one pipeline with the bundle's pipeline name (development prefix stripped); every pipeline name seen is saved as evidence; the tables report this pipeline id; `silver.meter_readings_evaluated`, both Silver reading tables and both Gold tables have type `MATERIALIZED_VIEW` |
| AC-27 | Unit | `tests/test_silver_dedup.py::test_ac27_rebuild_is_identical_for_any_input_order` | The harness recomputes from the same Bronze with shuffled row order and repartitioning; Silver, quarantine and Gold checksums are identical |
| AC-27 | Integration | `tests/integration/test_reprocessing.py::test_ac27_before_full_refresh_snapshot` and `::test_ac27_after_full_refresh_checksums_equal` | Kafka service off; pipeline full refresh; counts and checksums of all Silver and Gold objects are equal |
| AC-28 | Unit | `tests/test_bundle_config.py::test_ac28_job_and_pipeline_names_and_schedule` | Names are exactly `smart_meter_ingestion` and `smart_meter_silver_gold`; schedule present |
| AC-28 | Unit | `tests/test_bundle_config.py::test_ac28_no_more_than_five_concurrent_tasks` | The maximum width of the task DAG is <= 5 |
| AC-28 | Unit | `tests/test_bundle_config.py::test_ac28_layout_variables_match_sample_plan` | Catalog and schema defaults are as in Q-05; period and cutoff equal `config/sample_plan.json` |
| AC-28 | Integration | `tests/integration/test_deployment.py::test_ac28_deployed_job_pipeline_and_catalog_layout` | After `bundle validate` and the first-deploy sequence of DA-06 (deploy, setup notebook, deploy; manual; exit codes in the evidence, with the first deploy expected to fail on a fresh workspace and the second to succeed), the deployed names, with `^\[dev [^\]]+\] ` stripped, equal the base names exactly. The schedule is paused, and the objects are in the catalog layout, or in the fallback layout recorded in an Accepted ADR 0003 |
| AC-29 | Unit | `tests/test_secrets_hygiene.py::test_ac29_tracked_files_contain_no_kafka_credentials` | No broker host, SASL user or password values (from the local `.env` when present) and no credential patterns in tracked files outside `.env.example` |
| AC-29 | Unit | `tests/test_bundle_config.py::test_ac29_bundle_reads_kafka_credentials_from_secret_scope` | The bundle YAML holds only the scope name; `ingest_kafka` reads every credential with `dbutils.secrets.get` |
| AC-29 | Unit | `tests/test_producer.py::test_ac29_producer_reads_credentials_from_environment_only` | The producer config is built from environment variables only |
| AC-29 | Manual / evidence | `pre-commit run --all-files` | All hooks pass, including `detect-private-key` |
| AC-30 | Unit | `tests/test_bundle_config.py::test_ac30_job_timeout_within_60_minutes` | Job `timeout_seconds <= 3600` |
| AC-30 | Integration | `tests/integration/test_deployment.py::test_ac30_daily_job_run_within_60_minutes` | The latest full job run succeeded, with duration <= 3600 s and no quota termination. The pipeline task duration is recorded separately and compared with the 15-minute revisit trigger of ADR 0005 |
| AC-30 | Manual / evidence | Spike 04 timing over 1.7 M synthetic rows, recorded in ADR 0001 | Early evidence, before PR 2, that a full recompute fits the budget |
| AC-31 | Integration | `tests/integration/test_gold_tables.py::test_ac31_produced_reading_reaches_silver_and_gold_within_24h` | Sampled Silver Kafka rows appear in daily and monthly Gold, and job run end minus `_produced_at` is <= 24 h |
| AC-32 | Unit | `tests/test_runtime_adr.py::test_ac32_runtime_adr_records_every_spike_outcome` | ADR 0001 has a non-pending result for A-01, A-02, A-03, A-05, A-06, A-09 and A-10 |
| AC-32 | Unit | `tests/test_runtime_adr.py::test_ac32_check_specs_reports_no_errors` | `check_specs.run(root)` returns 0 errors |
| AC-33 | Unit | `tests/test_gold_quality.py::test_ac33_month_without_readings_has_dense_row` | The row for month M has 0 observed, 0 zero, null timestamps and missing slots equal to all slots |
| AC-33 | Unit | `tests/test_gold_quality.py::test_ac33_household_without_readings_and_orphan_are_dense` | A `silver.households` household with no reading has a row for every study month with `observed_readings = 0`. An orphan with readings also has every month. Total rows = (union of households) x study months, with no missing pair |
| AC-34 | Unit | `tests/test_silver_readings.py::test_ac34_row_failing_qr03_and_qr04_has_one_quarantine_row_counted_twice` | One quarantine row with `rule_name = 'QR-03'` and `failed_rules = ['QR-03', 'QR-04']`; the QR-03 and QR-04 totals from `metrics.py` are each 1 higher than on the same fixture without that row, and the quarantine holds the row once |
| AC-34 | Integration | `tests/integration/test_silver_tables.py::test_ac34_seed42_offgrid_null_rows_counted_under_both_rules` | The seed-42 off-grid `Null` rows are counted under QR-03 and QR-04 in the `metrics.py` totals over `silver.meter_readings_evaluated` and quarantined once each (when A-08 holds) |
| AC-35 | Unit | `tests/test_gold_quality.py::test_ac35_orphan_false_known_household_true` | The orphan `MAC999999` (readings in Silver, no `silver.households` row) has a row for every study month and one summary row, all with `has_household_record = false`. The known household is `true` in every row. The column is non-null in both objects, and filtering on it returns the same households as a join with `silver.households` |
| AC-35 | Integration | `tests/integration/test_gold_tables.py::test_ac35_seed42_has_household_record_all_true` | For seed 42, every monthly and summary row has `has_household_record = true`; the filter result equals the join with `silver.households` |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | `databricks bundle validate -t dev`, then `databricks bundle deploy -t dev`. Development mode adds the display prefix, pauses the schedule and sets the pipeline to `development: true`. On a fresh workspace the first deploy takes three steps (DA-06): deploy (files sync, pipeline creation fails because the catalog is absent), run `notebooks/setup_catalog.py` once from the synced bundle files (`.bundle/<name>/dev/files`; idempotent), deploy again; later deploys are a single deploy. The `setup_catalog` job task keeps the catalog in place for reruns and the fallback layout, but cannot help on the first deploy. CI runs `bundle validate` only (never `deploy`), so it does not depend on the catalog. CI validates the bundle when the repository secrets exist. The spike pipeline is deleted before the bundle pipeline is deployed. The runbook notes that a `prod` target (production mode) deploys without the name prefix |
| Scheduling and retries | Daily at 06:00 UTC, paused in development mode; run on demand with `databricks bundle run -t dev smart_meter_ingestion`. `max_concurrent_runs: 1`. Retries: setup 1, files 1 (idempotent through the checkpoint), Kafka 0 (AC-10; the next daily run is the retry; configured value, the platform ran the task twice in live failures, ADR 0001 DA-12), pipeline 0 (fail rules must not be retried blindly). Timeouts: 600 / 1800 / 840 / 2700 s; job 3600 s |
| Monitoring and alerting | Failure email to the deploying user. Rule, scope and duplicate counts are table totals from `silver.meter_readings_evaluated` through `metrics.py` (NFR-07), queryable at any time after an update. `pipeline_event_log` adds run observability (counter metrics for updates that refreshed a dataset, fail-rule errors, timing). The quarantine table supports row inspection. Trend monitoring is v0.3 (out of scope) |
| Secrets | Scope `smart_meter` with keys `kafka-bootstrap-servers`, `kafka-sasl-username`, `kafka-sasl-password` and `kafka-ca-pem`, created with `databricks secrets create-scope` and `put-secret` (runbook). The producer uses the git-ignored `.env`. Nothing goes in YAML, code or notebooks, and the options are never printed (ADR 0002) |
| Cost | Bronze ingestion is incremental. Every pipeline update recomputes Silver and Gold over all of Bronze: about 1.7 M rows, or 1.9 M after one full replay, with two window passes and a few aggregations. Expected in minutes on serverless; AC-30 leaves 2700 s for the pipeline task inside the 3600 s job, and spike 04 measures it first. Spikes run once. Target <= 60 min per run (AC-30); the job timeout stops runaway runs before the quota does. Revisit trigger: refresh > 15 min or Bronze > 50 M rows (ADR 0005) |
| Backfill / reprocessing | Every update recomputes Silver and Gold from Bronze; a full refresh does the same explicitly (FR-13, ADR 0006). New historical files land under a new name, and Auto Loader picks them up. Kafka replay comes from Bronze, never from the topic. A Bronze reset (drop the table and its checkpoint) is followed by a pipeline update. Changing the study period or cutoff needs only a redeploy and a pipeline update |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| Silver and Gold are recomputed on every update instead of incrementally | Refresh time grows linearly with Bronze | Accepted at about 1.7 M rows. Revisit trigger in ADR 0005: refresh > 15 min or Bronze > 50 M rows means moving to a streaming table with AUTO CDC |
| Counts are table totals over the current evaluation state, not per-update deltas (AC-12, DA-01 fallback) | Readers may expect deltas | Defined in *Column derivations*; tests compare totals, and compare totals before and after an input where an AC concerns an effect |
| The platform skips the refresh of an MV with no new input, so the event log has no expectation metrics for that update (DA-01 partial, spike 04) | Event-log counts exist only for updates that refreshed the MV, and cannot back NFR-07 or AC-12 | Applied: `silver.meter_readings_evaluated` is published and `metrics.py` counts from its `failed_rules`, `is_out_of_scope` and `is_duplicate` columns. The event log and the warn counters stay as observability only. Cost: one more stored copy of the Bronze rows (about 1.7 M), visible in the catalog and excluded from PEAK_MODEL inputs by its ops marking |
| Fixture ACs (AC-15, AC-16, AC-17, AC-23, AC-33, AC-34, AC-35) are proven by a local harness | The harness could diverge from Lakeflow semantics | Same rule catalog and functions in both. The wiring test uses a fake `dlt`. Spike 04 proves the platform semantics, and the seed-42 integration tests cover the same code paths. AC-17 now uses a files pair and a Kafka pair (a cross-path pair is impossible under QR-06) |
| A spike fails (A-02, A-03, A-09, A-10, DA-01 to DA-09) | Rework | The PR 1 gate triggers `/iterate` before PR 2. The fallbacks in ADR 0001 are configuration-level; a failure of A-10 reopens Q-07 |
| The source header `energy(kWh/hh)` in the Auto Loader read schema | Rescue or name matching could misbehave | Spike 01 tests exactly this; the fallback is a positional read |
| Aiven retention is shorter than a consumer outage | Messages are lost to the lakehouse, and `failOnDataLoss` fails the task | Accepted for v0.1 (ADR 0006); re-produce from the stream sample file. A power-off of the free service empties the topic and resets its offsets (ADR 0001, DA-11), which blocks the checkpoint until a Kafka reset (runbook "Broker outage") |
| `from_json` partial-result behaviour differs between local Spark and the serverless runtime | QR-07 edge cases could be classified differently | `_corrupt_record` plus required-field checks. The integration seed contains only valid payloads. The edge is documented |
| Quarantine dedup keys on the raw business key (QD-01) | Two dropped records with the same key but different energy text collapse into one quarantine row; the second is visible only as a counted duplicate in the evaluation table. Raw (untrimmed) values mean two padding variants of one reading are two identities | Accepted, consistent with the valid-row key. The evaluation table keeps every row, so nothing is lost. A seed-42 local-data check confirms that the 60 quarantined rows have 60 distinct keys (AC-11) |
| Kafka key and payload `household_id` disagree | Ordering per household is not guaranteed for that message | Not a rule in DEFINE. The producer derives both from one field. Noted for v0.3 monitoring |
| The persisted view in a pipeline is a newer feature | The summary view could fail to publish | Spike 04; fallback is a materialized view, through `/iterate` |

---

## Self-Review

- **Weak points:**
  - The DEFINE inline schema still lists the sample reading files as `household_id, reading_ts,
    energy_kwh`. The committed spike, and its pinned checksums, use the original source header
    (`LCLid,tstp,energy(kWh/hh)`), and this design keeps it so that the outputs stay
    byte-identical. Renaming happens in Bronze, which matches Q-06. That DEFINE row needs a
    one-line `/iterate`.
  - Spike 04 showed that an update with no new input writes no expectation metrics, so counts are
    now table totals from the published evaluation table. DEFINE was aligned on 2026-10-16
    (AC-12, NFR-07, SF-01 and QR-09 speak of table totals, with no time window).
  - Fixture-based ACs run against a local harness, and spike 04 is the only on-platform proof of
    expectation semantics.
  - Quarantine dedup (QD-01, 2026-10-19): the live seed-42 replay has no invalid message, so the
    invalid-message part of AC-09 is proven only by the unit harness; the `_dedup_key` for a
    Kafka payload with a readable raw `household_id` and `reading_ts` is the raw business key
    (QR-07 failures included, I-22), because the producer's `produced_at` makes a replayed payload
    differ byte for byte. Remaining gap: a payload with an unreadable key field still hashes the
    whole payload, so a replay of one that also carries a new `produced_at` (for example a null
    `reading_ts` with `produced_at` set) is quarantined again; the stream producer always writes
    both key fields, so this needs a hand-crafted message. A second `row_number()` pass is added to the
    evaluation MV; its cost is small next to the first, but AC-30 timing should be re-read after
    PR 2 is rebuilt.
  - The sampling selection uses the spike's coverage denominator (29,137 slots), while AC-25
    compares against the Silver denominator (29,184). The manifest carries both fields to keep
    them apart.
- **Risks:** Platform capabilities are still unproven (DA-01 to DA-09 and the DEFINE assumptions,
  in particular MV expectation metrics on Free Edition), and the free broker powers off.
- **What I would do differently:** With more budget, I would use a paid workspace with a second
  pipeline per target, so every fixture AC runs on Lakeflow itself. I would also move Silver to
  streaming tables with AUTO CDC and a change data feed from the start, so the design is ready for
  larger volumes.
- **Next improvement:** Build PR 1, run spikes 00 to 04 and A-08, and record the results in ADR
  0001. Run the `local_data` tests against the pinned config files. Then pass the PR 1 gate (or
  run `/iterate`) before PR 2a.

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-10-16 | DA-06 recorded as failed and its fallback applied: the first deploy on a fresh workspace is (1) `bundle deploy -t dev` (files sync, pipeline creation fails), (2) run `notebooks/setup_catalog.py` once from the synced files, (3) `bundle deploy -t dev` again; later deploys are a single deploy. Updated the Components row for the setup notebook, OD-05, the DA-06 row, the AC-28 evidence, the Operational Concerns deployment row and the runbook manifest entry (59). The `setup_catalog` job task stays and notes that it cannot help on the first deploy. A-09 passed, so the main layout stays | Spike 00 (2026-10-16, ADR 0001): terraform creates the pipeline in the same apply and fails with `Catalog 'smart_meter_dev' does not exist.`; the files were synced before the error | Manifest 59 (runbook) and 58 (AC-28 evidence); README deploy notes; ADR 0003 text; no code or architecture change; BUILD_REPORT must record the three-step deploy as evidence |
| 2026-10-16 | DA-01 recorded as partial and its fallback applied: `meter_readings_evaluated` is published as `silver.meter_readings_evaluated` (ops table, contract `silver_meter_readings_evaluated.yaml`, new manifest entry 30a), and `metrics.py` computes rule, scope and duplicate counts as table totals from its `failed_rules`, `is_out_of_scope` and `is_duplicate` columns (QR-10, QR-12, QR-14, QR-15 counts from the published tables). Counter expectations stay as event-log observability only; the published event log stays for observability (OD-06 revised). Updated Overview, architecture, Components, Data Model, *Counts*, rule table notes, OD-02, OD-06, DA-01 row, manifest 6, 30, 34, 41, 46, delivery plan (PR 2a is 20 files), test strategy rows AC-09, AC-12, AC-16, AC-17, AC-19, AC-21, AC-26, AC-34, monitoring and risks. AC IDs and test names unchanged; AC-09, AC-12 and AC-34 are re-expressed as table totals (before/after totals instead of "the event log reports") | Spike 04 (2026-10-16, ADR 0001): per-rule `failed_records` and double counting held, but an update with no new input wrote no expectation metrics and no `num_output_rows`, most likely because the refresh was skipped, so event-log counts exist only for updates that refreshed the MV | Manifest 30 (`metrics.py`), new 30a (contract), 28 and 46 (publish the evaluation table, fully qualified), 34, 36, 37, 51, 55, 57 (totals instead of event log); ADR 0004 text; ADR 0005 wording ("private"); DEFINE AC-12, NFR-07, SF-01, QR-09 wording ("per update", "within 5 minutes") needs `/iterate`; BUILD_REPORT must record the DA-01 outcome and the AC-12 re-expression |
| 2026-10-19 | Quarantine dedup (QD-01, DEFINE QR-09 b, FR-08, AC-09, AC-11, AC-12): `meter_readings_evaluated` gains `_dedup_key`, `quarantine_rank`, `is_quarantine_duplicate` and `is_quarantined`; `is_duplicate` now covers valid duplicates and quarantine duplicates; the quarantine holds `is_quarantined` rows and carries `_dedup_key`; per-rule totals exclude quarantine duplicates. Dedup key rule: path prefix plus raw business key (Kafka payload that parses, files row with household id and timestamp), else SHA-256 of the raw payload (Kafka, QR-07) or of the raw record values (files). Updated Overview, architecture, Data Model, Column derivations, Counts, QR-09 row, OD-01, manifest 28, 30, 30a, test strategy rows AC-09 (two new unit tests; the integration row notes the seed-42 limit), AC-11, AC-12, AC-17, risks and Self-Review. AC-17 test text follows the new DEFINE wording (files pair plus Kafka pair; no cross-path pair, which QR-06 makes impossible). I-18 fallback (derive `household_data_quality_check` from the monthly table if the Python dataset cannot read the SQL view) recorded in the build report only; no DESIGN change, no DESIGN text mentions I-18 | User decisions 2026-10-19: I-15 reopened (NFR-02 and AC-09 must hold for invalid messages), I-21 closed, I-18 fallback decided | Rebuild `pkg/silver.py` (28), `pkg/rules.py` (26, `NOT is_duplicate` stays, comments), `pkg/metrics.py` (30: per-rule filter, quarantine-duplicate total, AC-11 reconciliation class), `tests/support/harness.py` (34) if it lists columns, tests 36, 37, 41, integration tests for AC-11, AC-12 and AC-09 queries (55, 57), contracts quarantine and 30a, `docs/runbooks/meter_ingestion.md` line on re-quarantine, ADR 0004 and 0005 wording; the PR 2a, PR 2b (wiring/column list) and PR 3 branches are affected; DESIGN status stays Ready for Build because this entry updates it consistently |
| 2026-10-19 | Kafka `_dedup_key` rule (I-22): `kafka:key:<raw household_id>#<raw reading_ts>` whenever both raw values are non-NULL results of `get_json_object(payload, '$.household_id')` and `'$.reading_ts'` (independent of `payload_ok`, so QR-07 failures with a readable key are included); `kafka:payload:<sha2-256 of payload>` only when either is NULL (not JSON, not an object, missing or JSON null). "Raw" and "readable" defined in Column derivations (non-string JSON values give their JSON text, no type check). Files rule unchanged. Updated the `_dedup_key` derivation, Dedup key rule, AC-09 test rows (fixture list, key test, new `test_ac09_replayed_partially_parseable_invalid_payload_not_quarantined_again`) and the Self-Review (remaining gap for unreadable keys) | User decision 2026-10-19, closes BUILD_REPORT I-22: a payload failing QR-07 that still parses partially was keyed by the payload hash, and the new `produced_at` of a replay made it quarantine again (NFR-02, AC-09) | Rebuild `pkg/silver.py` (28: `KAFKA_DEDUP_KEY_SQL` tests `household_id_raw IS NOT NULL AND reading_ts_raw IS NOT NULL` instead of `payload_ok`), tests 36 and 37 (`test_silver_dedup.py`: new test, extend the key test and the AC-09 fixture), `tests/test_silver_readings.py` AC-11 and AC-12 fixtures if they assert the QR-07 key; contracts quarantine and 30a; ADR 0005 line 87 and runbook line 357 wording; DESIGN status stays Ready for Build |
| 2026-10-20 | Outage and retry wording (BUILD_REPORT I-23): the Kafka task is "configured with `max_retries: 0`" instead of "has no retry" (Concurrency and failure handling, Scheduling and retries row); the AC-10 evidence row and the Aiven-retention risk row state that a power-off of the free service empties the topic and resets offsets, so recovery is a Kafka reset and not a resume at checkpoint offsets (ADR 0001 DA-11). Observed: `ingest_kafka` ran twice per failed job run despite `max_retries: 0`; probable cause serverless automatic retry, NOT verified (ADR 0001 DA-12); follow-up: check the serverless retry setting. No config fix invented. AC IDs, test names and the manifest unchanged | Live steps D and E (2026-10-20): power-off emptied the topic, the next run failed on `failOnDataLoss` and left an uncommitted offsets batch; two attempts per failed run | No code, test or bundle change is required for AC-10, which holds (task failed within seconds, Bronze and checkpoint unchanged). Possible later build step, only after the retry check and a DESIGN decision: bundle YAML comment "No retry (AC-10)" in `resources/smart_meter_ingestion.job.yml` (manifest 50) (the assertion `max_retries == 0` in `tests/test_bundle_config.py::test_ac10_kafka_task_fails_within_15_minutes` checks the configured value only and stays valid). Runbook and ADR 0001 updated in the same iterate. DESIGN status stays Ready for Build because the change is consistent; PRs #2 to #4 unaffected in code |
| 2026-10-20 | Test Strategy row for `tests/integration/test_gold_tables.py::test_ac26_pipeline_and_table_metadata`: "Exactly one pipeline in the workspace" becomes "Exactly one pipeline with the bundle's pipeline name (development prefix stripped); every pipeline name seen is saved as evidence". No other workspace-wide pipeline-count wording in this DESIGN (the spike manifest row 8 deletes the spike pipeline because of the one-pipeline-per-type limit, which is unrelated and unchanged). AC IDs, test names and the manifest unchanged (SHIPPED follow-up F-03) | DEFINE AC-26 now scopes the check to the pipeline the bundle deploys; the Free Edition workspace is shared and holds an unrelated idle pipeline (BUILD_REPORT I-10); the implemented test and its `pipeline` fixture already check this | None for code, tests or bundle: the test and the `pipeline` fixture in `tests/integration/conftest.py` already match; BUILD_REPORT deviation "AC-26 pipeline count" marked as updated; DESIGN status stays Ready for Build |

---

## Next Step

`/build .claude/sdd/features/DESIGN_METER_INGESTION.md`
