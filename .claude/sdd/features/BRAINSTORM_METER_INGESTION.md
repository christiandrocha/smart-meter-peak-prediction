# BRAINSTORM: Meter Ingestion

> Phase 0. Explore intent and approaches before capturing requirements.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | METER_INGESTION |
| **Date** | 2026-10-15 |
| **Author** | Christian |
| **Status** | Ready for Define |

Allowed status values: `Exploring`, `Ready for Define`.

Target release: v0.1 (first of two features of the end-to-end thin slice). This document was split
out of `BRAINSTORM_SMART_METER_ML_FOUNDATION.md` on 2026-10-15 (see *Change Log*). Discovery
decisions and approach selection were made on 2026-10-06 and revised on 2026-10-07; profiling
evidence was regenerated on 2026-10-15 over 9 reading blocks and the full household file.

The ML half of the original scope (label, features, training, model, scoring) lives in
`BRAINSTORM_PEAK_MODEL.md`. The hand-off between the two features is described in *Hand-off to
PEAK_MODEL*.

---

## Initial Idea

**Raw input:** A utility running a smart meter programme receives half-hourly consumption readings
continuously from meters, while historical readings exist as files. Both paths must converge on one
governed, quality-checked reading table on Databricks, with household master data alongside, so that
downstream consumers (first of all a peak-prediction model) can rely on it.

The emphasis is on the data foundation: reproducible sample, batch and streaming ingestion
converging on one table, data quality enforced in the pipeline and measured per household, and
lineage from the raw reading onwards.

**Context observed:**

| Aspect | Observation | Implication |
|---|---|---|
| Existing code or data | Repository initialised from the project template: `scripts/profile_data.py`, `scripts/check_specs.py`, an empty `src/` package, a placeholder bundle (`databricks.yml`, `resources/jobs.yml`). No ADRs beyond the template. `spikes/` is empty. Source data lives under the git-ignored `data/` folder | Nothing to reuse in `src/`. The sampling script and its `plan.json` referenced below are not yet in the repository; they must be added (as a spike or as FR-01 code) before the sample numbers are reproducible |
| Existing conventions | `docs/conventions/naming.md` defines table and column patterns (`household_id`, `reading_ts`, `kafka_meter_readings`, `files_meter_readings`) | Answered Q-06: the convention is adopted; `LCLid` becomes `household_id` from Bronze onwards, including the Kafka event contract |
| Platform constraints | Databricks Free Edition (`.claude/kb/databricks/free-edition.md`): serverless only, outbound internet restricted to trusted domains, max 5 concurrent job tasks, one active pipeline per type, daily fair-usage quota | Streaming is scheduled `AvailableNow` micro-batches; external broker reachability must be proven by a spike; small sample |
| Relevant modules / KBs | `databricks` (Asset Bundles, Unity Catalog, Lakeflow, Auto Loader), `kafka` (topic contracts in `docs/contracts/`, Bronze keeps payload plus topic, partition, offset) | Every topic gets a contract from `docs/contracts/_topic_template.yaml`; the Bronze stream table is the replay source, not Kafka |

---

## Discovery Questions & Answers

All answers were given by the user during discovery (decisions D-01 to D-15 and D-17 in *Key
Decisions*). Questions about ML framing and consumers moved to `BRAINSTORM_PEAK_MODEL.md`.

| # | Question | Answer | Impact |
|---|---|---|---|
| 1 | Purpose: what should this feature deliver? | A reproducible sample, batch and stream ingestion into one Silver table with expectations, a household dimension, a daily consumption Gold table and measured per-household data quality facts | Every ingestion layer exists in v0.1, each kept minimal |
| 2 | Consumers: who reads the output? | The `PEAK_MODEL` feature reads Gold `household_daily_consumption` and `household_data_quality`; no other consumer in v0.1 | Gold contracts are the interface between the two features (D-17, D-18) |
| 3 | Constraints: which platform and budget? | Databricks Free Edition, serverless only (D-03); Kafka on the Aiven free tier (D-12) | Quota-aware design, scheduled micro-batches, environment assumptions validated by spikes |
| 4 | Data source: which dataset? | Smart Meters in London, `halfhourly_dataset` long format (D-01, D-04) | One row per reading maps directly to one Kafka event |
| 5 | Scale: how much data? | 60 households, 20 per ACORN group, stratified by group and tariff (D-06, D-07); size is a parameter | Fits the Free Edition quota; stratification is mandatory (F-01) |
| 6 | Time scope: which period and how is it split between batch and stream? | Study period 2012-07-01 to 2014-02-28 (D-08); historical `tstp < 2013-12-01`, stream `tstp >= 2013-12-01` (D-09) | Explicit, testable boundary; reconciliation test at the cutoff |
| 7 | Master data: how does household data arrive? | Static file in v0.1; Postgres with Debezium CDC in v0.2 (D-14) | No SCD in v0.1 |
| 8 | Naming: which conventions? | `docs/conventions/naming.md` (answered Q-06) | `household_id`, `kafka_meter_readings`, `files_meter_readings`, no ADR needed |

---

## Sample Data Inventory

| Type | Location | Volume | Notes |
|---|---|---|---|
| Input data: readings | `data/raw/halfhourly_dataset/halfhourly_dataset/block_*.csv` (Kaggle, `jeanmidev` copy) | 112 blocks, about 50 households each; profiled 9 blocks: 13,059,525 rows, 450 households | `LCLid, tstp, energy(kWh/hh)`, all text; report `docs/profiling/halfhourly_readings.md` |
| Input data: households | `data/raw/informations_households.csv` | 5,566 rows | `LCLid, stdorToU, Acorn, Acorn_grouped, file`; report `docs/profiling/informations_households.md` |
| Derived sample (seed 42) | Output of the sampling script (not yet in the repository) | Historical: 1,432,405 rows in 17 monthly files (about 63 MB), including 60 `Null` system rows. Stream: 247,569 rows (about 11 MB), no non-numeric values | 60 households, 6 blocks; 99.1% of household-days have all 48 readings |
| Expected output | Gold `household_daily_consumption` and `household_data_quality` | One row per household-day / per household | Schemas set in `/define` |
| Ground truth | Row counts from the sampling manifest | N/A | Bronze and Silver counts are reconciled against the manifest |

Weather (`weather_hourly_darksky.csv`) and calendar (`uk_bank_holidays.csv`) files are inputs of
`PEAK_MODEL`, not of this feature. Not used in v0.1: `daily_dataset`, `hhblock_dataset`,
`weather_daily_darksky.csv`, `acorn_details.csv` (wide format or group-level indicators).

**Final sample (seed 42):**

| Item | Value |
|---|---|
| Blocks | Affluent: `block_11`, `block_17`; Comfortable: `block_49`, `block_69`; Adversity: `block_82`, `block_104` |
| Households | 60 (20 per group); 16 `Std` + 4 `ToU` per group = 20% ToU |
| ACORN subgroups | 6 (D, E, F, H, L, Q), two per group |
| Excluded candidates | 27 (26 low coverage, 1 no readings in period) |
| Full days | 99.1% of household-days have all 48 readings |

**Profiling findings** (start from `scripts/profile_data.py`; reports in `docs/profiling/`):

Sources: **HH** = `docs/profiling/halfhourly_readings.md` (9 blocks, 2026-10-15);
**HI** = `docs/profiling/informations_households.md` (2026-10-15);
**EX** = earlier exploratory profiling on blocks 0, 100 and 110 plus the household file, and the
sampling run for seed 42 (2026-10-06/07). Report-local IDs are given in brackets, e.g. HH F-05.
The 9-block report covers blocks 0, 11, 17, 49, 69, 82, 100, 104 and 110: the exploratory blocks (0, 100, 110) plus the six sample blocks (confirmed, Q-10).

| ID | Finding | Evidence | Implication |
|---|---|---|---|
| F-01 | Blocks are homogeneous by ACORN group | EX: 95 of 112 blocks contain a single ACORN subgroup. HI: `file` has 112 distinct blocks | Taking "the first N blocks" biases the sample; stratified block selection is mandatory |
| F-02 | Literal `Null` energy values, one per household | HH F-02: 450 literal `Null` of 13,059,525 rows (<0.01%) across 450 households. EX: in blocks 0, 100, 110 all at 2012-12-18 around 15:13. Sample: 60 `Null` rows for 60 households | System event, not a meter fault; drop in Silver with a counted expectation |
| F-03 | Timestamps off the 30-minute grid | HH F-05: 450 off-grid rows, example 2012-12-19 12:37:27. EX: example 2012-12-18 15:13:42, on the same rows as F-02. **Refinement:** the event is not a single instant; off-grid rows appear on at least two dates (2012-12-18 and 2012-12-19). The 450 off-grid count equals the 450 `Null` count, but HH does not confirm they are the same rows | Expectation on the grid (minute in 0 or 30, second 0) rather than on a fixed timestamp; verify co-occurrence with F-02 in Databricks |
| F-04 | Energy stored as whitespace-padded text | HH F-03: 13,059,075 padded values, e.g. `' 0 '`; EX: `" 0.288 "` | Trim and cast between Bronze and Silver; Bronze keeps raw strings |
| F-05 | Dead or faulty meters | HH F-08: 2 households with >= 90% zeros, MAC004067 (100% zero) and MAC004672 (91% zero); 1 household with constant energy. EX: same pattern (one 100%, one 91%) | `household_data_quality` reports the zero share per household as a measured fact; the exclusion decision belongs to `PEAK_MODEL` |
| F-06 | Reading gaps and per-household coverage | HH F-06: 450 households, median coverage 99.8%, min 75.0%, 1 below 80%. **Refinement:** EX reported the worst household at about 19% missing; the 9-block profile shows up to 25% missing | `household_data_quality` reports coverage ratio and gap count; `warn` expectation on gaps; any threshold is a parameter owned by the consumer |
| F-07 | Staggered start and end per household | HH F-07: starts 2011-11-23 to 2013-07-04, ends 2012-06-26 to 2014-02-28; readings span 2011-11-23 13:00 to 2014-02-28 00:00. **Refinement:** EX reported starts from 2011-12; the 9-block profile shows starts from 2011-11-23 | Fixed study window (D-08); first and last reading per household in `household_data_quality`; absence is not zero consumption |
| F-08 | Invalid ACORN labels | HI: `Acorn` has 49 `ACORN-U` and 2 `ACORN-`; `Acorn_grouped` the same | Excluded from sampling |
| F-09 | No duplicate keys | HH F-04: `(LCLid, tstp)` unique, 0 duplicates in 13,059,525 rows. HI F-09: `LCLid` unique, 0 duplicates in 5,566 rows | Idempotency can be asserted with row counts; Silver dedup key `(household_id, reading_ts)` |
| F-10 | Reading timestamps are UTC | EX: DST transition days have exactly 48 readings | Readings stay in UTC end to end; the weather timezone check (A-07) belongs to `PEAK_MODEL` |
| F-11 | Source header not Delta/SQL safe | HH F-01: column `energy(kWh/hh)` | Positional schema in Bronze; rename to `energy_kwh` in Silver |
| F-12 | Tariff mix varies by block | EX: ToU share per block ranges 0% to 64%; 21 blocks have none. HI: population 4,443 `Std`, 1,123 `ToU` (about 20% ToU) | Sample tariff mix depends on the blocks drawn; seed 42 yields 20% ToU, matching the population; the manifest reports the mix on every run |
| F-13 | Low coverage is the main exclusion reason | EX (sampling run): 26 of 27 excluded candidates fell below 80% coverage in the study period, none as dead meters in the planned blocks | Coverage threshold drives sample composition; keep it a parameter. Note: HH coverage (F-06) is measured over each household's own span, not the study period, so the two numbers are not directly comparable |

---

## Approaches Explored

The main architectural choice is how streaming readings reach the lakehouse. The dataset and the
Kafka broker were compared separately and are summarised after the approaches.

### Approach A: Local producer replays readings into Kafka, Structured Streaming consumes (recommended)

A local Python producer (Docker) replays post-cutoff readings into an Aiven Kafka topic
`meter-readings`, keyed by household and preserving event time. A Databricks job consumes the topic
with Structured Streaming (`AvailableNow`) into the Bronze table `kafka_meter_readings`. Historical
files are ingested by Auto Loader from a UC Volume into `files_meter_readings`. Silver unions both.

- **Pros:** Producers live outside the lakehouse, as real meters do; no workspace quota spent on
  producing; exercises a real network path, authentication and offsets.
- **Cons:** Depends on a local machine running; external broker reachability and auth on serverless
  must be validated (A-01, A-03, A-06); free-tier service powers off after inactivity.
- **Why recommended:** Most realistic event path at zero cost, and it keeps the quota for ingestion
  and the downstream model feature.

### Approach B: Producer as a Databricks job

The same producer runs as a scheduled job inside the workspace and writes to Kafka.

- **Pros:** Simpler operation: no local machine or Docker; everything deploys from one bundle.
- **Cons:** The lakehouse emits events only to consume them back; spends daily quota and one of the 5
  concurrent task slots; less representative of devices outside the platform.

### Approach C: Readings through Postgres with Debezium CDC

Readings are inserted into Postgres and captured by Debezium into Kafka.

- **Pros:** Exercises CDC end to end.
- **Cons:** CDC on append-only telemetry adds components without benefit; CDC is better applied
  where records change (household tariff), which is planned for v0.2 (D-14).

### Dataset comparison

| Option | Verdict | Reason |
|---|---|---|
| **Smart Meters in London** | **Selected** | Real, high-volume IoT data with multiple sources, real quality issues and absolute timestamps |
| Azure Predictive Maintenance | Rejected | Synthetic and small; would need artificial augmentation |
| Olist E-Commerce | Rejected | Rich relational model but no natural event stream |
| Retailrocket events | Rejected | Good event stream, weak case for file ingestion |
| IEEE-CIS Fraud | Rejected | Relative timestamps prevent real event-time handling and point-in-time joins |
| Flight Delays 2015 | Rejected | Single year limits temporal splits; weather requires an external source |
| H&M Recommendations | Rejected | Competition data rules restrict use in a public repository |

### Kafka broker comparison

| Option | Verdict | Reason |
|---|---|---|
| **Aiven for Apache Kafka, free tier** | **Selected** | Permanent free plan; 5 topics x 2 partitions; enough throughput for 60 households |
| Confluent Cloud | Rejected | Credit-based trial; organisation suspended when it ends |
| Redpanda Serverless | Rejected | Time-limited trial credits |

---

## Selected Approach

| Attribute | Value |
|---|---|
| **Chosen** | Approach A, with Smart Meters in London and Aiven free tier |
| **Confirmed by** | Christian, 2026-10-07 (scope split confirmed 2026-10-15) |
| **Reasoning** | Realistic producer placement outside the lakehouse, zero cost, no quota spent on producing; the dataset offers real quality issues and absolute UTC timestamps |

**Architecture (v0.1, ingestion half):**

```text
                 Kaggle CSVs
                      |
           sampling script (local)
          /           |            \
  historical/     stream/       dimensions/
  monthly CSVs    one CSV       households
       |              |              |
   UC Volume     producer (Docker)   UC Volume
       |              |              |
  Auto Loader    Aiven Kafka         |
       |         topic meter-readings|
       |              |              |
       |      Structured Streaming   |
       |       (Trigger.AvailableNow)|
       v              v              v
  Bronze readings  Bronze readings  Bronze households
  (files)          (Kafka)
          \        /                 |
     Silver readings              Silver households
     (union, dedup, expectations)    |
          |        \                /
          |         Gold household_daily_consumption
          |
     Silver/Gold household_data_quality
                      |
              hand-off to PEAK_MODEL
```

**Data flow and contracts (draft):**

- Kafka event, topic `meter-readings`, JSON value, key = household id: household id (string),
  reading timestamp (ISO-8601 UTC, event time), energy in kWh (double, nullable when the source
  value is not numeric), `source` = `replay`, `produced_at` (ISO-8601 UTC, ingestion clock, never
  event time). Contract goes to `docs/contracts/meter-readings.yaml` from the topic template.
- Bronze readings from files: household id, raw timestamp and raw energy as strings,
  `_rescued_data`, `_source_file`, `_ingested_at`.
- Bronze readings from Kafka: key, raw JSON payload, topic, partition, offset, Kafka timestamp,
  `_ingested_at`.
- Silver readings: one row per `(household_id, reading_ts)`, deduplicated, with expectations from F-02
  to F-06 and F-09.
- Silver households: static household dimension from `informations_households.csv`, restricted to
  the sampled households.
- Gold `household_daily_consumption`: per household and UTC day, daily total, reading count and
  `is_complete_day` (48 readings).
- `household_data_quality` (Silver or Gold, layer to settle in `/define`): one row per household
  with measured facts only: coverage ratio, zero share, first and last reading, gap count. It
  carries no exclusion flag and no threshold.

---

## Hand-off to PEAK_MODEL

`PEAK_MODEL` (`BRAINSTORM_PEAK_MODEL.md`) consumes two tables produced here:

| Table | Grain | Used by PEAK_MODEL for |
|---|---|---|
| Gold `household_daily_consumption` | Household and UTC day | Label computation and daily features; `is_complete_day` decides which days can be labelled or enter a baseline |
| `household_data_quality` | Household | Applying its own exclusion thresholds (coverage < 80%, zero share >= 90%, both parameters, answered Q-09) when building the training set |

Boundary rules:

- METER_INGESTION reports facts; PEAK_MODEL owns and applies the exclusion thresholds. No
  exclusion flag, threshold or label exists in this feature.
- The label, weather, UK holidays, features, training, model registry and scoring are out of scope
  here.
- The sampling script still drops candidates with low study-period coverage or dead meters when
  composing the sample (D-07, F-13). That is a sample-composition parameter of the plan, not the
  training exclusion; the two use different denominators and are allowed to differ (see risks).
- Table and column names of both interface tables are fixed in this feature's `/define`; changes go
  through `/iterate` on both features.

---

## Key Decisions

| # | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| D-01 | Dataset: Smart Meters in London (Kaggle, `jeanmidev` copy with `halfhourly_dataset`) | Real IoT data, multiple sources, real quality issues, absolute timestamps | Six other datasets (see *Dataset comparison*) |
| D-02 | New repository; reuses naming, spec structure and bundle conventions from the `sdd-kafka-databricks` project | Independent repository; no code coupling | Not recorded |
| D-03 | Platform: Databricks Free Edition, serverless only | Zero cost; constraints recorded as ADRs | Not recorded |
| D-04 | Reading format: `halfhourly_dataset` (long) | One row per reading is the natural event shape for Kafka | `hhblock_dataset` (wide, one row per day) |
| D-06 | Sample size: 60 households, 20 per ACORN group (Affluent, Comfortable, Adversity) | Fast iteration within Free Edition quota; size is a parameter | Not recorded |
| D-07 | Sampling stratified by ACORN group and tariff; exclude `ACORN-U`, `ACORN-`, dead meters, low coverage | Blocks are homogeneous by ACORN group (F-01); quality findings F-05, F-06, F-08 | First N blocks |
| D-08 | Study period 2012-07-01 to 2014-02-28 | Window where most households are active (F-07) | Not recorded |
| D-09 | Batch/stream split: historical `tstp < 2013-12-01`, stream `tstp >= 2013-12-01` | Explicit, testable boundary | Not recorded |
| D-10 | Historical ingestion: Auto Loader from a UC Volume | Incremental file ingestion with schema control | Not recorded |
| D-11 | Stream ingestion: local Python producer (Docker) to Kafka; Structured Streaming consumes | Producers outside the lakehouse | Approaches B and C |
| D-12 | Kafka broker: Aiven for Apache Kafka, free tier | Permanent free plan | Confluent Cloud, Redpanda Serverless (trials) |
| D-13 | Kafka auth: SASL_SSL with SCRAM-SHA-256 (to confirm in the Aiven console, A-06) | No client keystore files needed on serverless | Authentication requiring client keystore files |
| D-14 | Household master data: static file in v0.1; Postgres + Debezium CDC in v0.2 | CDC adds value where records change (tariff), not for append-only readings | CDC in v0.1 |
| D-15 | Code, specs, ADRs and README in English | Public repository | Not recorded |
| D-17 | Scope split of 2026-10-15: ingestion and data quality facts here, ML in `PEAK_MODEL` | Two features with a clean interface, each reviewable and shippable on its own | One combined feature |
| D-18 | `household_data_quality` holds measured facts only; the consumer decides exclusion | Keeps ingestion free of ML-specific policy; thresholds stay parameters of the consumer | Exclusion flag computed in ingestion |

D-05 (ML framing) and D-16 (label baseline) moved to `BRAINSTORM_PEAK_MODEL.md` and keep their IDs.

---

## Out of Scope (YAGNI)

| Item | Reason | Revisit in |
|---|---|---|
| Label, features, training set, model, scoring, predictions table | Owned by `PEAK_MODEL` | `PEAK_MODEL` |
| Exclusion thresholds and exclusion decision | Owned by `PEAK_MODEL`; ingestion reports facts only (D-18) | `PEAK_MODEL` |
| Weather and UK bank holidays dimensions | Only needed for model features | `PEAK_MODEL` |
| Household master data in Postgres with Debezium CDC and SCD Type 2 | Static file is enough for the thin slice | v0.2 |
| Point-in-time joins against a slowly changing dimension | Depends on SCD Type 2 | v0.2 |
| Real-time or event-driven ingestion beyond scheduled `AvailableNow` micro-batches | Free Edition serverless limits | v0.4, or documented only |
| Larger sample for clustering and query optimisation benchmarks | Quota; not needed for correctness | Separate one-off scenario |
| `acorn_details.csv` enrichment | Group-level indicators add little at household level | Not planned |
| `daily_dataset`, `hhblock_dataset`, `weather_daily_darksky.csv` | Derivable from the selected sources | Not planned |

**Release roadmap (ingestion side):**

| Release | Scope |
|---|---|
| v0.1 | Sample, both ingestion paths, Silver with expectations, household dimension, daily Gold, data quality facts |
| v0.2 | CDC for household master data, SCD Type 2 |
| v0.3 | Monitoring of ingestion quality metrics |
| v0.4 | Scale-out scenario |

---

## Assumptions & Open Questions

| ID | Assumption or question | How it will be resolved | Status |
|---|---|---|---|
| A-01 | Serverless reaches the Aiven broker | TCP connectivity test from serverless | Validated (2026-10-06); not yet recorded in an ADR |
| A-02 | Auto Loader ingests CSVs from a UC Volume on serverless with `Trigger.AvailableNow` | Spike `spikes/databricks/01_spike_autoloader.py` | Pending |
| A-03 | Spark Kafka source authenticates with SASL_SSL and an inline PEM CA (`ssl.truststore.type=PEM`) | Spike `spikes/databricks/02_spike_kafka_consume.py` | Pending; fallback: CA file in a Volume |
| A-05 | Serverless streaming supports only `AvailableNow`-style triggers, so ingestion is scheduled micro-batch | Spike 02 plus Databricks documentation | Pending |
| A-06 | The SASL mechanism offered by Aiven is SCRAM-SHA-256 | Aiven console | Pending |
| A-08 | Off-grid timestamps (F-03) are the same rows as the `Null` values (F-02) in all blocks, not only in blocks 0, 100, 110 | Join the two conditions on the 9 profiled blocks in Databricks or locally | Pending |
| A-09 | Free Edition allows creating the catalog `smart_meter_dev` | Spike `spikes/databricks/00_setup.py` | Pending; fallback in Q-05 |
| A-10 | A triggered serverless Lakeflow Declarative Pipeline can be created and run on Free Edition, within the one-active-pipeline-per-type limit | Spike `spikes/databricks/04_spike_lakeflow_pipeline.py`, alongside spikes 01-03 | Pending |

A-04 (MLflow in UC) and A-07 (weather timezone) moved to `BRAINSTORM_PEAK_MODEL.md`.

Spike results are recorded in an ADR on runtime environment constraints
(`docs/adr/0001-runtime-environment-constraints.md`, to be created). Supporting local spikes:
`spikes/local/prepare_sample.py` (sampling plan, block selection, manifest), `spikes/local/producer/`
(producing to Aiven over SASL_SSL), `spikes/databricks/00_setup.py` (schema and Volume creation).

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Free Edition daily quota exhausted | Workspace compute stops for the day | Small sample, scheduled micro-batches, measure cost in spikes |
| Aiven free service powers off after inactivity | Stream job fails | Runbook step to power it on; Bronze holds raw payloads for reprocessing |
| Fixed, short Kafka retention | Cannot replay from the topic later | Bronze stream table is the reprocessing source |
| Cutoff boundary bugs | Duplicated or lost readings | Strict `<` / `>=` rule plus a reconciliation test |
| Sample tariff mix skewed (F-12) | Downstream models under-represent ToU households | Mix is balanced for seed 42; manifest reports it on every run; tariff-aware selection if the seed changes |
| Quality expectation tied to one timestamp (F-03) | Off-grid rows on other dates pass unnoticed | Grid-based expectation, not a hard-coded instant |
| Local producer depends on a running machine | Stream pauses when it is off | Accepted for v0.1; documented in limitations |
| Sampling script and plan not yet in the repository | Sample numbers in this document cannot be reproduced from the repository | Commit the script and `plan.json` before `/design` is finalised |
| Sampling excludes low-coverage households (F-13) while PEAK_MODEL applies its own thresholds on the sample | The two filters use different denominators, so a household can pass one and fail the other; the consumer may see fewer households than 60 | Document both definitions in the contracts; `household_data_quality` reports coverage over the study period so PEAK_MODEL can reason about it |
| Interface tables change after PEAK_MODEL starts | Rework in the consumer | Fix both contracts in `/define`; changes through `/iterate` on both features |

### Open questions for `/define`

| ID | Question | Notes |
|---|---|---|
| Q-04 | ~~Expectation actions~~ **Answered 2026-10-15:** Bronze has no rules and keeps raw rows. Silver `drop`: unparseable or off-grid timestamp, non-numeric or negative energy, invalid Kafka payload; dropped rows go to `meter_readings_quarantine` with the rule name and `_ingested_at`. Silver `fail`: invalid `household_id` (null or not matching `^MAC\d{6}$`) and a row on the wrong side of the cutoff for its ingestion path. Silver `warn`: `_rescued_data` filled. Duplicates are counted; the first ingested row wins. Gold: incomplete day `warn`, more than 48 readings per day `fail`, well-formed but unknown household (orphan) `warn`. The study-period filter is a scope transformation counted separately, not a quality rule | F-02 to F-06, F-09 |
| Q-05 | ~~Catalog layout~~ **Answered 2026-10-15:** one `dev` environment; catalog `smart_meter_dev` with schemas `bronze`, `silver`, `gold`, `ml`; Volumes `landing` and `checkpoints` in `bronze`; `prod` documented only as a catalog variable override. Fallback if catalogs cannot be created (A-09): `workspace.smart_meter_dev_<layer>`, recorded in an ADR | Free Edition limits |
| Q-07 | ~~Pipeline type~~ **Answered 2026-10-15:** one serverless, triggered Lakeflow Declarative Pipeline for Silver (readings, households, quarantine) and Gold, run as a task of the daily job; Bronze ingestion stays in job tasks. For `/design`: cross-source dedup is explicit (AUTO CDC keyed on `(household_id, reading_ts)` with a sequence that makes the first ingested row win, or `dropDuplicatesWithinWatermark`); Gold tables are materialized views; a spike validates the pipeline on Free Edition (A-10) | Free Edition limits |
| Q-11 | ~~`household_data_quality` window~~ **Answered 2026-10-15:** source of truth is Gold `household_data_quality_monthly` at grain `(household_id, month)` with `expected_readings`, `observed_readings`, `zero_readings`, `gap_count`; a `household_data_quality` summary view derived from it exposes `coverage_ratio_study_period`, `coverage_ratio_active_span`, `zero_share`, first and last `reading_ts`. The monthly grain lets PEAK_MODEL apply exclusions point-in-time; a whole-period metric would leak test-period information into training | F-06, F-13 |
| Q-06 | ~~Naming~~ **Answered 2026-10-15:** adopt `docs/conventions/naming.md` (`household_id`, `kafka_meter_readings`, `files_meter_readings`); `LCLid` is renamed to `household_id` from Bronze onwards, including the Kafka event contract. No ADR needed | Conflict found while writing the original document |
| Q-10 | ~~Profiled block set~~ **Answered 2026-10-15:** the 9-block profile covers blocks 0, 11, 17, 49, 69, 82, 100, 104, 110; list added to the report header | Confirmed by the author; consistent with 450 households (9 x 50) |

Questions Q-01, Q-02, Q-03, Q-08 and Q-09 moved to `BRAINSTORM_PEAK_MODEL.md`.

---

## Suggested Requirements for Define

- **Problem statement (draft):** Build a reproducible, governed ingestion foundation on Databricks
  Free Edition that brings smart meter readings from files and from Kafka into one quality-checked
  Silver table, publishes a household dimension, daily consumption totals with completeness, and
  measured per-household data quality facts, so that downstream consumers can use them without
  re-implementing cleaning or quality checks.
- **Success criteria (draft):**
  - Running the sampling script twice with the same plan produces byte-identical outputs (checksums
    in a manifest).
  - Bronze historical row count equals the manifest count; re-running ingestion with no new files or
    messages ingests 0 rows.
  - Silver row count equals the manifest total minus rows dropped by expectations, every dropped row
    accounted for; no reading duplicated or lost at the cutoff.
  - Gold `household_daily_consumption` totals and `is_complete_day` agree with a recomputation from
    Silver.
  - `household_data_quality` contains one row per household with coverage ratio, zero share, first
    and last reading and gap count, and matches an independent recomputation from Silver.
  - All ingestion jobs and pipelines deploy from a Databricks Asset Bundle.
- **Constraints:**
  - Free Edition serverless and Aiven free tier only.
  - No credentials in code, bundle files or git; Kafka secrets in a Databricks secret scope; local
    `.env` ignored.
  - Sample size, period, cutoff and replay speed are parameters, not code changes.
  - Time is UTC end to end; event time and ingestion time are separate columns.
  - Names follow `docs/conventions/naming.md`.

---

## Self-Review

- **Weak points:**
  - Several findings (F-01, F-10, F-12, F-13) come from exploratory profiling and a sampling run
    whose script and `plan.json` are not yet in the repository, so they cannot be regenerated from
    the repository today.
  - The 9-block profiling report contradicts the earlier single-instant reading of the `Null`
    event (F-03 refinement). Whether the off-grid rows and the `Null` rows coincide is unconfirmed
    (A-08), and the expected count of dropped rows depends on it.
  - Coverage numbers in F-06 (household's own span) and F-13 (study period) use different
    denominators; the definition used by `household_data_quality` is still open (Q-11).
  - The interface to `PEAK_MODEL` is described in prose only; column names are fixed later in
    `/define`.
  - The sampling script excludes households by coverage while exclusion thresholds now belong to
    `PEAK_MODEL`; the overlap is documented but not removed.
- **Risks:** Free Edition quota and the Aiven free tier are single points of failure for the stream
  path; a late change of the interface tables would ripple into the consumer feature.
- **What I would do differently:** Generate all profiling evidence through `scripts/profile_data.py`
  with the block list recorded in the report header, and commit the sampling script before writing
  numeric acceptance values.
- **Next improvement:** Commit the sampling script and plan, resolve A-08 by checking whether
  off-grid and `Null` rows coincide, then run `/define` for this feature and fix the two interface
  contracts before `PEAK_MODEL` is defined.

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-10-15 | Created by splitting `BRAINSTORM_SMART_METER_ML_FOUNDATION.md` (status Ready for Define). Ingestion scope kept: sample, Bronze (files, Kafka), Silver readings and households, Gold `household_daily_consumption`, new `household_data_quality` table (facts only). Findings F-01 to F-13, D-01 to D-04, D-06 to D-15, A-01 to A-03, A-05, A-06, A-08 and Q-04 to Q-07, Q-10 carried over with the same IDs; D-17, D-18 and Q-11 added | User decision of 2026-10-15: split into METER_INGESTION and PEAK_MODEL; exclusion thresholds owned by the consumer | `DEFINE_SMART_METER_ML_FOUNDATION.md` is no longer a valid DEFINE for either feature and must be rewritten per feature; contracts for features, predictions and (partly) weather and holiday data belong to PEAK_MODEL; the original brainstorm file is to be removed with `git rm` by the caller |

---

## Next Step

`/define .claude/sdd/features/BRAINSTORM_METER_INGESTION.md`
