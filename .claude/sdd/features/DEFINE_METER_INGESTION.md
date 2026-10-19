# DEFINE: Meter Ingestion

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | METER_INGESTION |
| **Date** | 2026-10-15 |
| **Author** | Christian |
| **Source** | `BRAINSTORM_METER_INGESTION.md` (status Ready for Define), including the answers to Q-04, Q-05, Q-06, Q-07, Q-10 and Q-11 of 2026-10-15; `BRAINSTORM_PEAK_MODEL.md` for the boundary |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

Target release: v0.1, first of the two features of the end-to-end thin slice. The consumer feature
`PEAK_MODEL` reads the interface tables fixed here (see *Hand-off to PEAK_MODEL*).

---

## Problem Statement

Half-hourly smart meter readings reach the platform through two paths, historical files and a live
Kafka stream, and carry real defects: literal `Null` values, off-grid timestamps, padded text,
dead meters, gaps and staggered start dates (F-02 to F-07). Without one reconciled, quality-checked
reading table, a household dimension, daily consumption with completeness and measured
per-household quality facts, every downstream consumer (first `PEAK_MODEL`) would have to repeat
cleaning and quality checks, and nobody could prove that a reading was neither lost nor counted
twice.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| `PEAK_MODEL` feature (labels, features, training exclusions) | Daily consumption with completeness, household attributes, point-in-time quality facts with stable names | `gold.household_daily_consumption`, `gold.household_data_quality_monthly`, `gold.household_data_quality`, `silver.households` (contracts in `docs/contracts/`) |
| Data platform operator | One-command deployment, idempotent re-runs, per-rule quality counts, inspectable dropped rows, within Free Edition limits | Asset Bundle `dev` target, daily job, `silver.meter_readings_quarantine`, per-rule totals over the published evaluation table `silver.meter_readings_evaluated` (the pipeline event log stays for run observability only) |
| Reviewer or auditor | Trace any Silver or dropped row back to its raw record and source | `_source_ref`, `_ingestion_path`, `_ingested_at`; Bronze `_source_file` and `_topic`/`_partition`/`_offset` |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Reproducible sample | SHA-256 of every sample file and the manifest across two runs of the same plan | 100% identical (AC-01) |
| Lossless convergence of both paths | Bronze rows not classified as Silver, quarantined, duplicate (valid or dropped) or out of study period | 0 rows (AC-11) |
| No reading lost or duplicated at the cutoff | Keys from both paths; boundary readings missing from Silver | 0 and 0 (AC-14) |
| Every dropped row inspectable | Dropped rows that are neither a quarantine row nor a counted quarantine duplicate; quarantine rows without a matching per-rule count | 0 and 0 (AC-11, AC-12) |
| Trustworthy interface for PEAK_MODEL | Gold and quality values that differ from an independent recomputation from Silver | 0 rows (AC-21 to AC-25) |
| Operable on Free Edition | Wall-clock time of one daily ingestion run on the seed-42 sample | <= 60 minutes, no quota stop (AC-30) |

---

## Scope

**In scope:**
- Sampling script and committed plan (seed 42, 60 households, stratified by ACORN group and tariff) producing historical monthly CSVs, one stream CSV, the household file for the sampled households and a manifest with checksums.
- Local replay producer (Docker) publishing the stream sample to Aiven Kafka topic `meter-readings`.
- Bronze `files_meter_readings` (incremental file ingestion from a UC Volume), Bronze `kafka_meter_readings` (Structured Streaming, `AvailableNow`) and Bronze `files_households`.
- Silver `meter_readings` and `meter_readings_quarantine` as materialized views recomputed over Bronze, with explicit cross-source deduplication and the quality rules of Q-04, and Silver `households`.
- Gold materialized views `household_daily_consumption` and `household_data_quality_monthly`, and the summary view `household_data_quality`.
- One triggered serverless Lakeflow pipeline for Silver and Gold; Bronze ingestion in job tasks; one daily job deployed from the Asset Bundle (`dev` target), with Kafka secrets in a secret scope.
- Spikes for A-02, A-03, A-05, A-06, A-09 and A-10 and the ADR recording their results, including the catalog fallback if A-09 fails.

**Out of scope:**
- Label, exclusion thresholds and exclusion decisions, features, temporal splits, training, UC model registration, lineage to a model, scoring, predictions table (`PEAK_MODEL`).
- Weather and UK bank-holiday files (`PEAK_MODEL`).
- Household master data in Postgres with Debezium CDC, SCD Type 2 and point-in-time joins against it (v0.2).
- Monitoring and alerting on ingestion quality metrics over time (v0.3).
- Ingestion beyond scheduled `AvailableNow` micro-batches; a deployed `prod` environment (documented only); larger samples for benchmarks.
- `acorn_details.csv`, `daily_dataset`, `hhblock_dataset`, `weather_daily_darksky.csv` (not planned).

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system shall provide a sampling script driven by a committed plan (seed, households per ACORN group, study period, cutoff, sample-composition coverage and zero-share limits) that selects households stratified by ACORN group and tariff, excludes `ACORN-U`, `ACORN-`, dead meters and low-coverage candidates, and writes a manifest with row counts per file, per-household study-period coverage and zero share, tariff mix, excluded candidates with reasons and SHA-256 checksums of every output file. | Must |
| FR-02 | The system shall split the sample by the cutoff into historical files (`reading_ts < cutoff`, one CSV per month) and one stream file (`reading_ts >= cutoff`), with default cutoff 2013-12-01T00:00:00Z and study period 2012-07-01 to 2014-02-28, and write the household file restricted to the sampled households. | Must |
| FR-03 | The system shall replay the stream file to topic `meter-readings` per its contract, keyed by `household_id`, in event-time order, at a configurable replay speed, with an idempotent producer and the energy value kept nullable rather than dropped. | Must |
| FR-04 | The system shall ingest historical reading files from a UC Volume into `bronze.files_meter_readings`, keeping raw strings under renamed columns plus `_rescued_data`, `_source_file` and `_ingested_at`, processing each file once. | Must |
| FR-05 | The system shall consume topic `meter-readings` on a schedule with an `AvailableNow`-style trigger into `bronze.kafka_meter_readings`, keeping key (`kafka_key`), raw `payload`, `_topic`, `_partition`, `_offset`, `_kafka_timestamp` and `_ingested_at`. | Must |
| FR-06 | The system shall ingest the household file into `bronze.files_households` and publish `silver.households` with rules QR-13 to QR-15. | Must |
| FR-07 | The system shall build `silver.meter_readings` as a materialized view recomputed over both Bronze reading tables (Bronze stays incremental): parse, trim, cast and rename to the naming conventions; leave rows outside the study period out as a counted scope transformation; apply rules QR-01 to QR-08 with the actions of Q-04; and deduplicate explicitly on `(household_id, reading_ts)` so that the first ingested row wins. | Must |
| FR-08 | The system shall expose, as the materialized view `silver.meter_readings_quarantine`, every row dropped by a Silver drop rule, once per content identity (the dedup key of QR-09): when the same dropped content reaches Bronze again (a replayed Kafka message, a re-landed file), only the earliest-ingested row (then smallest `_source_ref`) is quarantined and each repeat is counted as a duplicate (QR-09) and not quarantined again. Each quarantine row carries its raw values, the first failed rule in precedence order (`rule_name`), every failed rule (`failed_rules`) and `_ingested_at`; per-rule quality metrics count a quarantined row under every rule in `failed_rules`, and a repeat does not raise any per-rule count. | Must |
| FR-09 | The system shall make queryable, as table totals over the current state of the published evaluation table `silver.meter_readings_evaluated`, the count of rows failing each rule, rows quarantined, rows left out by the study-period filter and duplicates removed. | Must |
| FR-10 | The system shall publish `gold.household_daily_consumption` as a materialized view with daily total, half-hour maximum, reading count and `is_complete_day` (48 readings) per household and UTC day, with rules QR-10 to QR-12. | Must |
| FR-11 | The system shall publish `gold.household_data_quality_monthly` as a materialized view as a dense table: one row for every study-period month per household in the union of `silver.households` and the households with any `silver.meter_readings` row (so orphans appear), carrying the non-null boolean `has_household_record` (true when the household is in `silver.households`), including months with `observed_readings = 0`, including months with `observed_readings = 0`, holding `expected_readings`, `observed_readings`, `zero_readings`, `gap_count`, `first_reading_ts` and `last_reading_ts`, where each month's values depend only on readings up to the end of that month. Missing slots in a month are `expected_readings - observed_readings`; `gap_count` is the number of gap events closed in that month. | Must |
| FR-12 | The system shall publish `gold.household_data_quality`, derived only from the monthly table, with `coverage_ratio_study_period`, `coverage_ratio_active_span`, `zero_share`, `gap_count`, `first_reading_ts`, `last_reading_ts` and `has_household_record` per household, and no threshold, flag or exclusion decision. | Must |
| FR-13 | The system shall rebuild every Silver and Gold table from Bronze alone, without reading Kafka or re-landing files. | Must |
| FR-14 | The system shall deploy from the Databricks Asset Bundle to the `dev` target one daily job that runs file ingestion, Kafka ingestion and one triggered serverless Lakeflow pipeline update for Silver and Gold. | Must |
| FR-15 | The system shall read Kafka credentials only from a Databricks secret scope (lakehouse) or an ignored local `.env` (producer). | Must |
| FR-16 | The system shall expose sample size, study period, cutoff and replay speed as parameters, changeable without code changes. | Must |
| FR-17 | The system shall place all objects in catalog `smart_meter_dev` with schemas `bronze`, `silver`, `gold` and `ml` (empty, for `PEAK_MODEL`) and Volumes `landing` and `checkpoints` in `bronze`; if the catalog cannot be created (A-09), it shall use the fallback `workspace.smart_meter_dev_<layer>` recorded in an ADR. | Must |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Reproducibility | The same plan and raw files produce byte-identical sample outputs; rebuilding from Bronze produces identical Silver, quarantine and Gold contents (AC-01, AC-27). |
| NFR-02 | Idempotency | Re-running any ingestion step or pipeline update with no new input changes 0 rows; re-delivered Kafka messages, valid or invalid, change 0 Silver rows and 0 quarantine rows and raise no per-rule count (AC-06, AC-08, AC-09). |
| NFR-03 | Cost | One daily ingestion run on the seed-42 sample (about 1.68 million readings) finishes in <= 60 minutes wall-clock and is never stopped by the Free Edition daily quota (AC-30). |
| NFR-04 | Platform limits | Serverless only; at most 5 job tasks can run concurrently; exactly 1 Lakeflow pipeline; streams use `AvailableNow`-style triggers (AC-28). |
| NFR-05 | Security | 0 credentials, private keys or broker passwords in tracked files, bundle YAML or notebooks (AC-29). |
| NFR-06 | Time handling | All timestamps are UTC; event time (`reading_ts`, `reading_date`, `reading_month`) and processing time (`_ingested_at`, `_produced_at`, `_kafka_timestamp`) are separate columns (AC-19, AC-20). |
| NFR-07 | Observability | Per-rule counts, quarantine counts, scope-filter counts and duplicate counts are queryable as table totals over the evaluation table once each pipeline update ends, and a full refresh gives the same totals (AC-12). |
| NFR-08 | Freshness | A reading produced to Kafka is in Silver and Gold at the end of the next daily run, <= 24 h after production (AC-31). |
| NFR-09 | Recoverability | Because Free Edition accounts may be deleted, the workspace state is rebuildable from the repository, the raw Kaggle files and the secret values alone (AC-27, AC-28). |

---

## Data Contracts

Catalog `smart_meter_dev` (Q-05). Interface tables for `PEAK_MODEL` have contract files in
`docs/contracts/`; the rest are inline.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| Sample files (historical monthly CSVs, stream CSV, household CSV, `manifest.json`) | METER_INGESTION | One row per source reading or household; one manifest entry per output file | `(household_id, reading_ts)`; `household_id`; file path | On plan change | Inline |
| `meter-readings` (Kafka topic) | METER_INGESTION | One message per half-hourly reading | Message key `household_id`; dedup key `(household_id, reading_ts)` | Replay speed parameter | `docs/contracts/meter-readings.yaml` |
| `bronze.files_meter_readings` | METER_INGESTION | One row per CSV line ingested | `(_source_file, household_id, reading_ts_raw)` | Daily | Inline |
| `bronze.kafka_meter_readings` | METER_INGESTION | One row per Kafka message consumed | `(_topic, _partition, _offset)` | Daily | Inline |
| `bronze.files_households` | METER_INGESTION | One row per CSV line ingested | `(_source_file, household_id)` | On file arrival | Inline |
| `silver.meter_readings` (materialized view) | METER_INGESTION | One row per household per half-hour reading | `(household_id, reading_ts)` | Daily, <= 24 h | `docs/contracts/silver_meter_readings.yaml` |
| `silver.meter_readings_quarantine` (materialized view) | METER_INGESTION | One row per distinct dropped content identity (the earliest-ingested dropped Bronze row; repeats are counted duplicates) | `_source_ref`; also unique on the dedup key `_dedup_key` | Daily, <= 24 h | `docs/contracts/silver_meter_readings_quarantine.yaml` |
| `silver.households` | METER_INGESTION | One row per sampled household | `household_id` | On file arrival | `docs/contracts/silver_households.yaml` |
| `gold.household_daily_consumption` (materialized view) | METER_INGESTION | One row per household per UTC day with at least one reading | `(household_id, reading_date)` | Daily, <= 24 h | `docs/contracts/gold_household_daily_consumption.yaml` |
| `gold.household_data_quality_monthly` (materialized view) | METER_INGESTION | One row per household (in `silver.households` or with any Silver reading) per UTC month of the study period | `(household_id, reading_month)` | Daily, <= 24 h | `docs/contracts/gold_household_data_quality_monthly.yaml` |
| `gold.household_data_quality` (view) | METER_INGESTION | One row per household | `household_id` | Daily, <= 24 h | `docs/contracts/gold_household_data_quality.yaml` |

### Inline schemas

Names follow `docs/conventions/naming.md`. `LCLid` is `household_id` from Bronze onwards (Q-06);
`tstp` and `energy(kWh/hh)` never appear as column names (F-11).

| Table | Columns (type) |
|---|---|
| Sample reading files | Original source header `LCLid`, `tstp`, `energy(kWh/hh)` as source text (CSV), so outputs stay byte-identical to the spike and to the checksums in `config/sample_manifest.json`; renamed to `household_id`, `reading_ts`, `energy_kwh` from Bronze onwards (Q-06); manifest lists file, rows, SHA-256, per-household coverage and zero share, tariff mix, exclusions with reasons |
| `bronze.files_meter_readings` | `household_id` (string), `reading_ts_raw` (string), `energy_kwh_raw` (string), `_rescued_data` (string), `_source_file` (string), `_ingested_at` (timestamp) |
| `bronze.kafka_meter_readings` | `kafka_key` (string), `payload` (string), `_topic` (string), `_partition` (int), `_offset` (bigint), `_kafka_timestamp` (timestamp), `_ingested_at` (timestamp) |
| `bronze.files_households` | `household_id`, `tariff_raw`, `acorn_category_raw`, `acorn_group_raw`, `source_block_raw` (all string), `_rescued_data`, `_source_file` (string), `_ingested_at` (timestamp) |

### Quality rules (Q-04)

Bronze carries no rules and keeps every received row as raw text. The study-period filter is a
scope transformation (SF-01), not a quality rule. Drop rules are evaluated in the precedence order
QR-07, QR-02, QR-03, QR-04, QR-05; `rule_name` in the quarantine is the first failed one and
`failed_rules` lists all. Fail rules QR-01 and QR-06 apply to every row whose payload passed QR-07.

| ID | Layer and table | Rule | Action | Evidence |
|---|---|---|---|---|
| SF-01 | Silver `meter_readings` | `reading_ts` within the study period (default 2012-07-01T00:00Z inclusive to 2014-03-01T00:00Z exclusive); rows outside are left out of Silver and quarantine and counted as a table total (`is_out_of_scope`) | scope filter (counted) | D-08, F-07 |
| QR-01 | Silver `meter_readings` | `household_id` not null and matching `^MAC[0-9]{6}$` (equivalent to `^MAC\d{6}$`) | fail | Q-04 |
| QR-02 | Silver `meter_readings` | Raw timestamp parses to a timestamp | drop to quarantine | F-04 |
| QR-03 | Silver `meter_readings` | `reading_ts` on the 30-minute grid (minute 0 or 30, second 0) | drop to quarantine | F-03 |
| QR-04 | Silver `meter_readings` | Trimmed raw energy parses as a number | drop to quarantine | F-02, F-04 |
| QR-05 | Silver `meter_readings` | `energy_kwh >= 0` | drop to quarantine | Physical bound |
| QR-06 | Silver `meter_readings` | Files rows have `reading_ts < cutoff`; Kafka rows have `reading_ts >= cutoff` | fail | D-09 |
| QR-07 | Silver input from Kafka | Payload is a JSON object that parses with the `meter-readings` value schema (before the union) | drop to quarantine | Topic contract |
| QR-08 | Silver input from files | `_rescued_data` is null | warn | Schema drift |
| QR-09 | Silver `meter_readings` and `meter_readings_quarantine` | Deduplicate with `row_number()` ordered by `_ingested_at`, then `_source_ref`; rank 1 wins (earliest `_ingested_at`, then smallest `_source_ref`). (a) Valid rows: partition on `(household_id, reading_ts)`; losers are left out of Silver. (b) Dropped rows (failed at least one drop rule): partition on the dedup key `_dedup_key` (see *Dedup key of dropped rows*); losers are left out of the quarantine and of every per-rule count. All losers are counted in one table total (`is_duplicate`); the part that comes from dropped rows is also queryable alone (`is_quarantine_duplicate`) | dedup (counted) | F-09, at-least-once delivery, I-15 |
| QR-10 | Gold `household_daily_consumption` | `is_complete_day` (48 readings); incomplete days kept and counted | warn | F-06 |
| QR-11 | Gold `household_daily_consumption` | `reading_count <= 48` | fail | Impossible after QR-03 and QR-09 |
| QR-12 | Gold `household_daily_consumption` | Well-formed `household_id` that exists in `silver.households` (orphans kept and counted) | warn | Q-04 |
| QR-13 | Silver `households` | `household_id` not null and unique | fail | HI F-09 |
| QR-14 | Silver `households` | `acorn_group` in (`Affluent`, `Comfortable`, `Adversity`) | warn | F-08 |
| QR-15 | Silver `households` | `tariff` in (`Std`, `ToU`) | warn | HI distributions |

### Dedup key of dropped rows (QR-09 b, QD-01)

The key is a content identity that is equal for a replay of the same record and does not depend on
offset, file name or file position. It always starts with the ingestion path (`files:` or
`kafka:`), so a files row and a Kafka row never share a key. The rule is deterministic and uses
raw values as received (no trimming or parsing, so it also works for rows that fail QR-02 or
QR-07):

| Row | Dedup key `_dedup_key` |
|---|---|
| Kafka row whose payload passed QR-07 | `kafka:key:` + raw `household_id` + `#` + raw `reading_ts` taken from the payload |
| Kafka row that fails QR-07 (unparseable, required field missing) | `kafka:payload:` + SHA-256 (hex) of the raw `payload` |
| Files row with a raw `household_id` and a raw `reading_ts` | `files:key:` + raw `household_id` + `#` + raw `reading_ts` |
| Files row without one of the two | `files:row:` + SHA-256 (hex) of the raw record values (`household_id`, `reading_ts`, `energy_kwh`, `_rescued_data`, null-safe, joined by a separator) |

Two dropped rows with the same key but a different energy text count as one content identity,
consistent with the valid-row key, which also ignores energy. A dropped row and a valid row never
compete: the two partitions are separate, so every Bronze row is still in exactly one class (AC-11).
The Kafka key of a payload that parses is the business key and not the payload hash, because the
replay producer stamps a new `produced_at` into every message, so a replayed payload is not
byte-identical.

### Quality fact definitions (Q-11)

- `expected_readings` = 48 x the days of the month inside the study period; 29,184 for the whole default period (608 days).
- A gap is a maximal run of one or more missing half-hour slots between two consecutive Silver readings of the same household; it is counted once, in the month of the reading that ends it. Missing slots before the first or after the last reading are not gaps (F-07).
- `coverage_ratio_study_period` = sum of `observed_readings` / sum of `expected_readings`.
- `coverage_ratio_active_span` = sum of `observed_readings` / number of half-hour slots from `first_reading_ts` to `last_reading_ts` inclusive.
- `zero_share` = sum of `zero_readings` / sum of `observed_readings`.
- These differ from the sample-composition filter in the plan (F-13) and from any exclusion rule of `PEAK_MODEL`, which applies its own thresholds on the monthly table restricted to the months before a boundary (PEAK_MODEL Q-14).

### Hand-off to PEAK_MODEL

`PEAK_MODEL` reads `gold.household_daily_consumption`, `gold.household_data_quality_monthly`,
`gold.household_data_quality` and `silver.households`. METER_INGESTION reports facts only: no
label, threshold or exclusion flag exists here (D-18). Changes to these four contracts go through
`/iterate` on both features.

---

## Acceptance Criteria

Seed-42 figures come from the brainstorm sampling run; the committed `spikes/local/prepare_sample.py`
with `spikes/local/plan.json` reproduced them exactly on 2026-10-15 (A-13). The selection is pinned in
`config/sample_households.csv` and the counts and checksums in `config/sample_manifest.json`.

| ID | Given | When | Then |
|---|---|---|---|
| AC-01 | The committed plan (seed 42) and the raw Kaggle files | The sampling script runs twice into two empty output folders | Every output file and the manifest have identical SHA-256 checksums in both runs |
| AC-02 | The seed-42 plan | The sampling script runs | The manifest reports 60 households, 20 per ACORN group, 16 `Std` and 4 `ToU` per group, 0 with `ACORN-U` or `ACORN-`, every selected household with study-period coverage >= 80% and zero share < 90%, and a reason for each excluded candidate; the household file has exactly those 60 households; the set of selected household ids (and the 48 `Std` / 12 `ToU` split) equals `config/sample_households.csv` (source column `LCLid`), and the row counts equal those in `config/sample_manifest.json`. This holds for the sampling code ported into `src/`, not only for the spike script |
| AC-03 | The seed-42 sample | Output files and manifest are read | Every historical row has `reading_ts < 2013-12-01T00:00:00Z`, every stream row `>= 2013-12-01T00:00:00Z`, 0 keys appear in both, historical rows = 1,432,405 and stream rows = 247,569 |
| AC-04 | The plan with cutoff 2013-11-01 instead of the default | The sampling script runs with no code change | Every historical row has `reading_ts < 2013-11-01T00:00:00Z`, every stream row `>= 2013-11-01T00:00:00Z`, and historical + stream rows equal the default run's total |
| AC-05 | All historical sample files in the landing Volume and empty Bronze tables | File ingestion runs | `bronze.files_meter_readings` has exactly the manifest's historical row count (1,432,405 for seed 42), `bronze.files_households` has 60 rows, and 0 rows have null `_source_file` or `_ingested_at` |
| AC-06 | File ingestion has processed every file | File ingestion runs again with no new file | 0 rows are added to either Bronze file table |
| AC-07 | The producer has published the stream file once and the consumer starts from an empty checkpoint | Kafka ingestion runs until it stops (`AvailableNow`) | `bronze.kafka_meter_readings` has exactly 247,569 rows, `(_topic, _partition, _offset)` is unique, 0 rows have null `payload`, `_topic`, `_partition`, `_offset`, `_kafka_timestamp` or `_ingested_at`, and every payload parses with the topic contract's value schema |
| AC-08 | Kafka ingestion has consumed every available message | Kafka ingestion runs again with no new message | 0 rows are added to `bronze.kafka_meter_readings` |
| AC-09 | Silver built after AC-07; and a fixture Bronze Kafka table with valid messages and invalid messages (one failing QR-07, one failing QR-03 and QR-04, one failing QR-05) | The producer republishes the whole stream file, then Kafka ingestion and the pipeline run; on the fixture, every Kafka message is delivered again with new offsets, a later `_ingested_at` and, for payloads that parse, a different `produced_at`, and the pipeline runs | `bronze.kafka_meter_readings` grows by 247,569 rows; `silver.meter_readings` and `silver.meter_readings_quarantine` row counts and content checksums are unchanged; the duplicate total (`is_duplicate` rows of `silver.meter_readings_evaluated`) is higher than before the replay by 247,569. On the fixture, Silver and quarantine counts and checksums are unchanged, every per-rule total is unchanged, and the duplicate total is higher by the number of replayed messages, valid and invalid |
| AC-10 | The Kafka broker is unreachable (service powered off) | The daily job runs | The Kafka task ends failed within 15 minutes, `bronze.kafka_meter_readings` gains 0 rows and the checkpoint does not advance; after the broker is back, the next run ingests every pending message and AC-07's uniqueness and count checks hold |
| AC-11 | Both Bronze reading tables loaded and a pipeline update completed | A reconciliation query classifies every Bronze reading row by `_source_ref` | Every Bronze row falls in exactly one class: in `silver.meter_readings`; in `silver.meter_readings_quarantine`; duplicate (its key is in Silver under a different `_source_ref` that ranks first by `_ingested_at`, then `_source_ref`); quarantine duplicate (it failed a drop rule and its `_dedup_key` is held by a quarantine row with a different `_source_ref` that ranks first by `_ingested_at`, then `_source_ref`); or outside the study period. Unclassified rows = 0 and rows in two classes = 0. For seed 42 without replays: 60 quarantined, 0 outside the period, 0 duplicates, 0 quarantine duplicates, 1,679,914 in Silver (when A-08 holds) |
| AC-12 | The latest pipeline update has ended, and again after a full refresh | The table totals over `silver.meter_readings_evaluated` are compared with the tables | For each drop rule, the total of rows failing it that are not quarantine duplicates equals the number of quarantine rows whose `failed_rules` contains the rule (a replayed invalid row raises no per-rule total); the evaluated row count equals the rows of both Bronze reading tables; the quarantine rows equal the evaluated rows failing at least one drop rule that are not quarantine duplicates; the scope-filter and duplicate totals are present, and the duplicate total equals the Silver duplicates plus the quarantine duplicates (`is_quarantine_duplicate` rows, queryable alone); all totals are queryable once the update ends |
| AC-13 | `silver.meter_readings` after any update | Key, grid, value and period are queried | 0 duplicate `(household_id, reading_ts)`, 0 rows off the 30-minute grid, 0 rows with `energy_kwh < 0` or null, 0 rows outside the study period, 0 rows whose `_source_ref` is also in the quarantine |
| AC-14 | Silver built from both paths | Rows around the cutoff are queried | Every row with `reading_ts < 2013-12-01T00:00:00Z` has `_ingestion_path = 'files'` and every other row `'kafka'`; every reading at 2013-11-30T23:30:00Z and 2013-12-01T00:00:00Z present in the sample appears exactly once in Silver |
| AC-15 | Fixture Bronze rows, one violating each rule QR-01 to QR-08 and QR-10 to QR-15 | The pipeline runs on the fixture | Each drop rule moves exactly its row to the quarantine with that `rule_name` and `_ingested_at`; each warn rule keeps its row and reports 1; each fail rule (QR-01, QR-06, QR-13) fails the update with 0 rows committed by it; QR-11, unreachable through Silver, fails the Gold aggregation when 49 readings for one household-day are fed to it directly. QR-01 fails for a null id, `MAC12345`, `mac000002` and `MAC0000021`; `MAC999999` (well formed, not in households) passes Silver and is reported once by QR-12 |
| AC-16 | Fixture rows at 2012-06-30T23:30Z and 2012-07-01T00:00Z from files, and at 2014-02-28T23:30Z and 2014-03-01T00:00Z from Kafka | The pipeline runs | The two inner rows are in Silver; the two outer rows are in neither Silver nor quarantine; the scope-filter total (`is_out_of_scope` rows) is 2 |
| AC-17 | A fixture with two duplicate pairs on the same `(household_id, reading_ts)`: two files rows with different `_ingested_at`, where the earlier one has the larger `_source_ref`, and two Kafka rows with equal `_ingested_at` and different offsets | The pipeline runs, and again on the same input in reversed order and with a different partitioning | Silver keeps the earlier `_ingested_at` row of the first pair and the smaller `_source_ref` row of the second; the duplicate total (`is_duplicate` rows) is 2; every run keeps the same winners |
| AC-18 | Silver households built from the seed-42 sample | The table is queried | 60 rows, unique `household_id`, `acorn_group` in the 3 valid groups, `tariff` in (`Std`, `ToU`), 20 households per group |
| AC-19 | The deployed tables and the contract files | Column names and types are listed from Unity Catalog | Every table and column in *Data Contracts* exists with that name and type; 0 columns are named `LCLid`, `tstp` or `energy(kWh/hh)`; every processing-time or source-metadata column (`_ingested_at`, `_ingestion_path`, `_source_ref`, `_source_file`, `_rescued_data`, `_topic`, `_partition`, `_offset`, `_kafka_timestamp`, `_produced_at`) starts with `_` with no exceptions; 0 columns in Bronze, Silver or Gold are named `kafka_timestamp`, `topic`, `partition`, `offset` or `produced_at`; `kafka_key` and `payload` keep their names; `produced_at` exists only inside the Kafka payload (topic contract) |
| AC-20 | Silver readings on the DST change days 2013-03-31 and 2013-10-27 | Readings per household are counted per UTC day | Every household with 48 readings on both neighbouring days has exactly 48 readings on each DST change day (F-10) |
| AC-21 | `silver.meter_readings` and `gold.household_daily_consumption` | Daily aggregates are recomputed from Silver | `household_daily_consumption` is a materialized view over the Silver materialized view; for every `(household_id, reading_date)` `total_energy_kwh` and `max_energy_kwh` differ from the recomputation by <= 1e-9, `reading_count` is equal, `is_complete_day` is true exactly when `reading_count = 48`; for seed 42 the share of complete household-days is between 98.5% and 99.5% and QR-10's count equals the number of incomplete days |
| AC-22 | `silver.meter_readings` and `gold.household_data_quality_monthly` for seed 42 | Monthly facts are recomputed independently from Silver | The materialized view has 1,200 rows (60 households x 20 months, unique key); `expected_readings` is 48 x days in month (1,488 for 31 days, 1,344 for February 2014); `observed_readings`, `zero_readings`, `gap_count`, `first_reading_ts` and `last_reading_ts` equal the recomputation for 100% of rows |
| AC-23 | A fixture household with leading missing slots, a 1-slot gap and a 3-slot gap inside the same month, a gap spanning a month boundary and trailing missing slots | The monthly table is computed | `gap_count` is 2 in the month of the in-month gaps, 1 in the month of the reading closing the boundary-spanning gap, 0 elsewhere; leading and trailing missing slots count as no gap |
| AC-24 | The monthly table built from Silver up to the end of month M | Readings dated in month M + 1 or later are appended and the pipeline runs again | Every row for months <= M is unchanged (point-in-time property for PEAK_MODEL Q-14) |
| AC-25 | `gold.household_data_quality` for seed 42 and a fixture with a 100%-zero household | The view is queried and recomputed from the monthly table | One row per household; every ratio equals the recomputation within 1e-9 using the formulas in *Quality fact definitions*; the fixture household has `zero_share = 1.0`; for seed 42 every `coverage_ratio_study_period` is within 0.001 of the manifest's coverage for that household; the view has no column named like threshold, flag, excluded or label |
| AC-26 | The pipeline definition deployed | Pipeline and table metadata are read | Exactly one Lakeflow pipeline exists, serverless and triggered; `silver.meter_readings`, `silver.meter_readings_quarantine` and `silver.households` and all Gold objects are produced by it; `silver.meter_readings`, `silver.meter_readings_quarantine` and both Gold tables are materialized views |
| AC-27 | Bronze loaded and every downstream table built once | Silver and Gold are fully refreshed from Bronze only, with the Kafka service powered off | Row counts and content checksums of all Silver and Gold tables, including the quarantine, equal those before the refresh |
| AC-28 | A workspace with the `dev` profile and the repository at the feature commit | `databricks bundle validate -t dev` then `databricks bundle deploy -t dev` run | Both exit 0; the daily job and the pipeline exist, named `smart_meter_<purpose>`; no job allows more than 5 concurrent tasks; the daily schedule is defined (paused in development mode); all tables and Volumes are in catalog `smart_meter_dev`, schemas `bronze`, `silver`, `gold`, `ml`, or in the fallback layout with an Accepted ADR in `docs/adr/` that records it |
| AC-29 | The repository at the feature commit | `pre-commit run --all-files` and a scan of tracked files for the broker host, SASL username and password run | All hooks pass, including `detect-private-key`; the scan finds 0 matches outside `.env.example` placeholders; lakehouse code reads every Kafka credential through a secret scope |
| AC-30 | The seed-42 sample landed and published | The daily job runs once from Bronze ingestion to the end of the pipeline update | The job run succeeds in <= 60 minutes wall-clock and is not stopped by the Free Edition daily quota |
| AC-31 | A message produced to `meter-readings` | The next daily run completes | The reading is present in `silver.meter_readings` and reflected in `gold.household_daily_consumption` and `gold.household_data_quality_monthly`, <= 24 h after its `_produced_at` (Silver) |
| AC-32 | Spikes for A-02, A-03, A-05, A-06, A-09 and A-10 run | `docs/adr/` is read | An ADR on runtime environment constraints records the outcome of each spike and of A-01, and `scripts/check_specs.py` reports 0 errors |
| AC-33 | A fixture household in `silver.households` with readings in month M - 1 and M + 1 and none in month M, a fixture household in `silver.households` with no reading at all, and an orphan household with readings but no `silver.households` row | The monthly table is computed | A row exists for month M with `observed_readings = 0`, `zero_readings = 0`, `first_reading_ts` and `last_reading_ts` null, and `expected_readings - observed_readings` equal to all slots of M; the household without readings has a row for every study month with `observed_readings = 0`; the table has exactly (households in the union of `silver.households` and Silver readings) x study months rows, with no missing (household, month) pair |
| AC-34 | A fixture Bronze row with an off-grid timestamp and energy `Null` (fails QR-03 and QR-04, as in F-02/F-03) | The pipeline runs | Exactly one quarantine row exists for it, with `rule_name = 'QR-03'` and `failed_rules = ['QR-03', 'QR-04']`; the failure totals for QR-03 and QR-04 are each 1 higher than on the same fixture without that row |
| AC-35 | A fixture with a known household in `silver.households` with readings and an orphan household (`MAC999999`, well formed, readings in Silver, no `silver.households` row) | The pipeline runs and `gold.household_data_quality_monthly` and `gold.household_data_quality` are queried | Both objects have a non-null boolean column `has_household_record`; the orphan has a row for every study month in the monthly table and one row in the summary view, all with `has_household_record = false`; the known household has `true` in every row; filtering on `has_household_record` returns the same households as a join with `silver.households`; for seed 42 every row has `true` |

### Traceability (FR to AC)

| FR | Covered by |
|---|---|
| FR-01 | AC-01, AC-02 |
| FR-02 | AC-02, AC-03, AC-14 |
| FR-03 | AC-07, AC-09 |
| FR-04 | AC-05, AC-06 |
| FR-05 | AC-07, AC-08, AC-10 |
| FR-06 | AC-05, AC-18 |
| FR-07 | AC-11, AC-13, AC-14, AC-15, AC-16, AC-17, AC-19, AC-20, AC-26 |
| FR-08 | AC-09, AC-11, AC-12, AC-15, AC-26, AC-34 |
| FR-09 | AC-09, AC-12, AC-16, AC-17 |
| FR-10 | AC-21, AC-26 |
| FR-11 | AC-22, AC-23, AC-24, AC-26, AC-33, AC-35 |
| FR-12 | AC-25, AC-35 |
| FR-13 | AC-27 |
| FR-14 | AC-26, AC-28, AC-30, AC-31 |
| FR-15 | AC-29 |
| FR-16 | AC-04 |
| FR-17 | AC-28, AC-32 |

---

## Decisions and Open Items

### Decided by the user (not reopened)

| ID | Decision | Date |
|---|---|---|
| Q-04 | Expectation actions and layers as in *Quality rules*; drop rules write to `meter_readings_quarantine` with rule name and `_ingested_at`; the study-period filter is a counted scope transformation; invalid `household_id` = null or not matching `^MAC\d{6}$`, a well-formed unknown id is the Gold orphan warn | 2026-10-15 |
| Q-05 | Catalog `smart_meter_dev`, schemas `bronze`, `silver`, `gold`, `ml`; Volumes `landing` and `checkpoints` in `bronze`; `dev` only, `prod` documented as a variable override; fallback `workspace.smart_meter_dev_<layer>` recorded in an ADR | 2026-10-15 |
| Q-06 | Naming per `docs/conventions/naming.md`; `LCLid` is `household_id` from Bronze onwards, including the Kafka contract | 2026-10-15 |
| Q-07 | One triggered serverless Lakeflow pipeline for Silver and Gold, run as a task of the daily job; Bronze ingestion in job tasks; explicit cross-source dedup; Gold tables are materialized views; A-10 validated by a pipeline spike | 2026-10-15 |
| Q-10 | Profiled blocks 0, 11, 17, 49, 69, 82, 100, 104, 110 confirmed | 2026-10-15 |
| Q-11 | Quality source of truth is `household_data_quality_monthly` at `(household_id, month)`; `household_data_quality` is a summary view derived from it | 2026-10-15 |
| OD-01 | Silver `meter_readings` and `meter_readings_quarantine` are materialized views recomputed over Bronze; dedup with `row_number()` over `(household_id, reading_ts)` ordered by `_ingested_at`, `_source_ref`; Bronze stays incremental (Auto Loader and Kafka with `AvailableNow`) | 2026-10-15 |
| Q-12 | Monthly quality household set = union of `silver.households` and households with any Silver reading; `has_household_record` (non-null boolean) in the monthly table and the summary view | 2026-10-15 |
| Q-13 | Every processing-time or source-metadata column starts with `_`, no exceptions: `_kafka_timestamp`, `_topic`, `_partition`, `_offset`, `_produced_at`; `kafka_key` and `payload` keep their names; `produced_at` stays in the Kafka payload contract | 2026-10-15 |
| QD-01 | Dropped rows are deduplicated like valid rows: earliest `_ingested_at`, then smallest `_source_ref`, wins per content identity (QR-09 b, *Dedup key of dropped rows*); repeats are counted as duplicates, not quarantined again and not counted per rule. Reverses the earlier "accepted as is" of BUILD_REPORT I-15 | 2026-10-19 |
| D-01 to D-04, D-06 to D-15, D-17, D-18 | Brainstorm decisions | 2026-10-06 to 2026-10-15 |

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-01 | Resolved 2026-10-15 (see *Decided by the user*): Silver as materialized views with `row_number()` dedup; design must show AC-09, AC-17 and AC-27 hold |
| OD-02 | Resolved by the DESIGN: a shared rule-evaluation materialized view (`silver.meter_readings_evaluated`, published) computes `failed_rules` once; quarantine and Silver filter it, so AC-12 holds by construction |
| OD-03 | Exact format of `_source_ref` for file rows, and whether Auto Loader file metadata can give a row index |
| OD-04 | How `gold.household_data_quality` is materialized (persisted view vs materialized view) within the pipeline |
| OD-05 | How catalog, schemas and Volumes are created given that bundle development mode prefixes bundle-managed resources (setup task vs bundle resources) |
| OD-06 | Resolved 2026-10-16 by the DESIGN (see Change Log): counts are table totals over the published evaluation table `silver.meter_readings_evaluated`, computed by `metrics.py`; the pipeline event log stays published for run observability only (spike 04, ADR 0001, DA-01 partial) |

### Added in this document

The column names `reading_month`, `first_reading_ts` and `last_reading_ts` in the monthly table
(needed to derive the summary view from the monthly table alone), the gap definition, the drop-rule
precedence, and the household rules QR-13 to QR-15 are specified here; Q-04 did not cover
household rules.

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| C-01 | Constraint | Databricks Free Edition, serverless only (D-03) | Yes |
| C-02 | Constraint | At most 5 concurrent job tasks; one active pipeline per type; daily fair-usage quota | Yes (KB, verified 2026-10-06) |
| C-03 | Constraint | Kafka on the Aiven free tier: 5 topics x 2 partitions, short retention, powers off after inactivity (D-12) | Yes |
| C-04 | Constraint | No secrets in code, bundle files, notebooks or commits; Kafka credentials in a secret scope; local `.env` ignored | Yes (golden rule 2) |
| C-05 | Constraint | Time is UTC end to end; event time and ingestion time are separate columns | Yes (golden rule 5) |
| C-06 | Constraint | Raw and sample data stay out of git (`data/` ignored); non-commercial use only | Yes |
| C-07 | Constraint | Study period 2012-07-01 to 2014-02-28; files `reading_ts < 2013-12-01`, Kafka `>=` (D-08, D-09) | Yes |
| A-01 | Assumption | Serverless reaches the Aiven broker | Validated 2026-10-06 (TCP test); ADR pending (AC-32) |
| A-02 | Assumption | Auto Loader ingests CSVs from a UC Volume on serverless with `AvailableNow` | Pending, spike 01 |
| A-03 | Assumption | The Spark Kafka source authenticates with SASL_SSL and an inline PEM CA | Pending, spike 02; fallback CA file in a Volume |
| A-05 | Assumption | Serverless streaming supports only `AvailableNow`-style triggers | Pending, spike 02 |
| A-06 | Assumption | Aiven offers SCRAM-SHA-256 | Pending, Aiven console |
| A-08 | Assumption | Off-grid timestamps (F-03) are the same rows as the `Null` values (F-02); sets the expected 60 quarantined rows in AC-11 | Validated 2026-10-15: 450/450 rows coincide in the 9 profiled blocks and 60/60 in the seed-42 study period (`spikes/local/a08_offgrid_null_cooccurrence.py`, ADR 0001) |
| A-09 | Assumption | Free Edition allows creating catalog `smart_meter_dev` | Pending, spike 00; fallback decided (Q-05) |
| A-10 | Assumption | A triggered serverless Lakeflow pipeline runs on Free Edition within the one-pipeline-per-type limit | Pending, spike 04 |
| A-13 | Assumption | The brainstorm seed-42 figures (1,432,405 / 247,569 rows, 60 households, blocks 11/17/49/69/82/104, 48 Std / 12 ToU) are reproduced by the sampling script | Validated 2026-10-15: `spikes/local/prepare_sample.py` and `plan.json` re-run reproduced them exactly; selection pinned in `config/sample_households.csv`, counts and checksums in `config/sample_manifest.json` |
| A-14 | Assumption | `tstp` marks the start of the half hour, so `reading_date` is the UTC date of `reading_ts` | Pending; applied consistently in sampling, Silver and Gold |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Concrete defects backed by profiling evidence (F-01 to F-13) and a clear consumer need |
| Users | 2 | The main consumer is the `PEAK_MODEL` feature, whose brainstorm is still Exploring; its needs (Q-14 point-in-time exclusion) are known, but may still change |
| Scope | 3 | Boundary with `PEAK_MODEL` explicit; out-of-scope items assigned to a feature or release |
| Acceptance criteria | 3 | 35 measurable criteria covering every FR, including row-level reconciliation, idempotency, quality fixtures and failure paths; all decisions behind them are settled |
| Constraints | 2 | Platform limits documented and fallbacks decided, but six environment assumptions await spikes (A-02, A-03, A-05, A-06, A-09, A-10); the sample numbers are validated (A-13) |
| **Total** | **13/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The numeric expectations in AC-02, AC-03, AC-05, AC-07, AC-11, AC-21 and AC-22 are now backed by the committed spike script (A-13 validated); the code ported into `src/` must keep selecting the pinned households (AC-02).
  - Silver as materialized views recomputes over all of Bronze; the cost on Free Edition and the meaning of counts under incremental refresh (resolved: table totals over the evaluation table, AC-12) are design risks (AC-12, AC-30). `QR-01` and `QR-06` fail rules on a materialized view need a design answer.
  - The 60 quarantined rows in AC-11 assume A-08 (off-grid rows are the `Null` rows); if not, the quarantine count rises and the Silver count falls accordingly. They also assume no two of the 60 share a raw `(household_id, reading_ts)`; otherwise the quarantine falls below 60 and the quarantine duplicates rise (a local-data check on seed 42 settles it).
  - Quarantine dedup (QR-09 b) keys on the raw business key for payloads that parse, so two dropped records with the same key but different energy text collapse into one quarantine row; the later one is only visible as a counted duplicate in the evaluation table. The seed-42 live replay holds no invalid message, so the invalid-message part of AC-09 is proven on a fixture only.
  - `coverage_ratio_study_period` can never reach 1: the data ends at 2014-02-28T00:00Z, so 47 slots of the last study day never exist (maximum about 0.998). This is a fact of the source, not a bug, but readers may misread it.
  - The monthly table adds `first_reading_ts` and `last_reading_ts` and the household rules QR-13 to QR-15, which the user decisions did not list explicitly.
- **Risks:** Free Edition may not support a capability assumed in A-02, A-03, A-05, A-09 or A-10; A-09 has a decided fallback, the others would change the design. Expectation metrics and quarantine rows produced by different flows could disagree (AC-12 detects it). The Aiven service powering off makes AC-10 likely in practice.
- **What I would do differently:** Commit the sampling script and plan and resolve A-08 before writing numeric acceptance values.
- **Next improvement:** Commit the sampling script and `plan.json`, run spikes 00 to 04, record them in the runtime ADR, then run `/design` resolving OD-01 to OD-06.

---

## Next Step

`/design .claude/sdd/features/DEFINE_METER_INGESTION.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-15 | Silver `meter_readings` and `meter_readings_quarantine` are materialized views over Bronze (FR-07, FR-08, scope, data contract table, QR-09 wording, AC-21, AC-26); OD-01 resolved; OD-02 reworded; AC-12 wording adapted to recomputed views | User decision: Silver as MVs with `row_number()` dedup; Bronze stays incremental | DESIGN: remove AUTO CDC / streaming-table Silver, show AC-09, AC-17, AC-27 hold with MVs, answer how QR-01 and QR-06 fail rules and per-update counts work on MVs (AC-12, AC-15), re-check AC-30 runtime |
| 2026-10-15 | Monthly quality household set = union of `silver.households` and households with Silver readings (FR-11, AC-33); new column `has_household_record` in monthly table and summary view (FR-11, FR-12); new AC-35; traceability updated | User decision: orphans must get quality rows and be filterable without a join | DESIGN: monthly and summary SQL, tests for AC-33 (extra fixtures) and AC-35 |
| 2026-10-15 | AC-19 has no exceptions; renamed Bronze Kafka columns `topic`, `partition`, `offset`, `kafka_timestamp` to `_topic`, `_partition`, `_offset`, `_kafka_timestamp` (FR-05, key, inline schema, AC-07); Silver gains `_produced_at` (AC-31, NFR-06); `produced_at` stays in the Kafka payload; `_source_ref` definition uses `_topic/_partition/_offset` | User decision on naming | DESIGN: Bronze Kafka schema and `_source_ref` builder, payload parsing to `_produced_at`, AC-19 column-name test (list from Unity Catalog), AC-07 and AC-31 tests |
| 2026-10-15 | A-13 Validated; AC-02 extended: ported sampling code must select exactly `config/sample_households.csv` and match `config/sample_manifest.json`; AC section intro updated | Spike script and plan committed and re-run, reproducing seed-42 figures | DESIGN: add an AC-02 test comparing the `src/` sampling output with the pinned config files |
| 2026-10-15 | Contracts: `silver_meter_readings` (MV, `_produced_at`, `_source_ref`), `silver_meter_readings_quarantine` (MV, `_source_ref`), `gold_household_data_quality_monthly` and `gold_household_data_quality` (`has_household_record`, household set); `meter-readings` unchanged except consumer note. All kept at version 1 | Additive per each contract's policy; no consumer is deployed yet and no existing column of a contract file was renamed (the renames are in inline Bronze schemas) | PEAK_MODEL DEFINE should note the new `has_household_record` column and filter on it where orphans matter |
| 2026-10-15 | Sample reading files keep the original source header `LCLid,tstp,energy(kWh/hh)`; renaming starts in Bronze | Byte-identical outputs to the committed spike and pinned checksums; consistent with Q-06 (rename from Bronze onwards) | None; DESIGN already assumes the original header |
| 2026-10-15 | A-08 Validated | Local spike: off-grid and non-numeric rows coincide (450/450 in 9 blocks, 60/60 in the seed-42 study period) | None; AC-11 keeps 60 quarantined and 1,679,914 Silver rows |
| 2026-10-16 | Counts are table totals over the current state of the published `silver.meter_readings_evaluated`, not per-update counts from the event log: FR-09, NFR-07 ("queryable as table totals once the update ends", no 5-minute window), SF-01 and QR-09 ("counted as a table total"), AC-09, AC-12 (checked after the latest update and after a full refresh), AC-16, AC-17, AC-34 ("update's count" becomes total or total before/after), stakeholder row, Self-Review; OD-02 and OD-06 marked resolved by the DESIGN. AC IDs and what each AC guards are unchanged. A-08 row already Validated (BUILD_REPORT I-01 was stale) | DESIGN DA-01 fallback (Change Log 2026-10-16): spike 04 (ADR 0001, DA-01 partial) showed an update with no new input writes no expectation metrics to the event log | DESIGN already agrees (its Self-Review note on AC-12 and NFR-07 is now closed); tests keep their names; BUILD_REPORT I-01 and I-11 to be closed; no DESIGN status change |
| 2026-10-19 | Quarantine is idempotent under replays (QD-01): FR-08, NFR-02, QR-09 (now a: valid rows, b: dropped rows by dedup key), new section *Dedup key of dropped rows*, data contract row of the quarantine (grain, key), goals table, AC-09 (adds an invalid-message fixture clause and per-rule totals unchanged), AC-11 (new class quarantine duplicate; seed 42: 0 quarantine duplicates), AC-12 (per-rule totals exclude quarantine duplicates; duplicate total = Silver duplicates + quarantine duplicates), traceability (FR-08 and FR-09 gain AC-09), Self-Review. AC-17 replaced with the user's wording: the cross-path pair was impossible under QR-06, so the fixture has a files pair and a Kafka pair, run again in reversed order and with other partitioning. AC IDs unchanged | User decisions 2026-10-19: I-15 reopened because replayed invalid messages were quarantined again, contradicting NFR-02 and AC-09 (which held for seed 42 only because it has no invalid message); I-21 closed | DESIGN: evaluation table gains `_dedup_key`, `quarantine_rank`, `is_quarantine_duplicate`, `is_quarantined`, and `is_duplicate` covers both kinds; rebuild `silver.py`, `rules.py`, `metrics.py` and tests for AC-09, AC-11, AC-12, AC-17; contracts for the quarantine and evaluation tables; runbook and ADR 0005 wording |
