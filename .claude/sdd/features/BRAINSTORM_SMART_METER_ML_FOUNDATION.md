# BRAINSTORM: Smart Meter ML-Ready Data Foundation

> Phase 0. Explore intent and approaches before capturing requirements.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | SMART_METER_ML_FOUNDATION |
| **Date** | 2026-10-15 |
| **Author** | Christian |
| **Status** | Ready for Define |

Allowed status values: `Exploring`, `Ready for Define`.

Target release: v0.1 (end-to-end thin slice). Discovery decisions and approach selection were
made on 2026-10-06 and revised on 2026-10-07 (final sample and label analysis). Profiling evidence
was regenerated on 2026-10-15 over 9 reading blocks and the full household file.

---

## Initial Idea

**Raw input:** A utility running a smart meter programme needs an ML-ready data foundation on
Databricks. Half-hourly consumption readings arrive continuously from meters, historical readings
exist as files, and household master data plus weather enrich both. The foundation must deliver
governed, reproducible features and a registered model that flags households likely to exceed their
usual consumption the next day.

The emphasis is on the data foundation rather than on model accuracy: batch and streaming ingestion
converging on one table, data quality enforced in the pipeline, point-in-time correct features, and
lineage from raw reading to model version.

**Context observed:**

| Aspect | Observation | Implication |
|---|---|---|
| Existing code or data | Repository initialised from the project template: `scripts/profile_data.py`, `scripts/check_specs.py`, an empty `src/` package, a placeholder bundle (`databricks.yml`, `resources/jobs.yml`). No ADRs beyond the template. `spikes/` is empty. Source data lives under the git-ignored `data/` folder | Nothing to reuse in `src/`. The sampling script and its `plan.json` referenced below are not yet in the repository; they must be added (as a spike or as FR-01 code) before the sample numbers are reproducible |
| Existing conventions | `docs/conventions/naming.md` defines table and column patterns (`household_id`, `reading_ts`, `kafka_meter_readings`, `files_meter_readings`, `label_<target>`) | The draft contract names (`lcl_id`, `bronze_readings_historical`, `bronze_readings_stream`) do not follow it; `/define` must align them (see open questions) |
| Platform constraints | Databricks Free Edition (`.claude/kb/databricks/free-edition.md`): serverless only, outbound internet restricted to trusted domains, max 5 concurrent job tasks, one active pipeline per type, daily fair-usage quota, no online tables, limited model serving | Streaming is scheduled `AvailableNow` micro-batches; batch scoring instead of real-time serving; external broker reachability must be proven by a spike; small sample |
| Relevant modules / KBs | `databricks` (Asset Bundles, Unity Catalog, Lakeflow, Auto Loader), `kafka` (topic contracts in `docs/contracts/`, Bronze keeps payload plus topic, partition, offset), `mlflow` (UC registry with aliases, temporal splits, point-in-time training sets) | Every topic gets a contract from `docs/contracts/_topic_template.yaml`; Bronze stream table is the replay source, not Kafka; models promoted with `champion` / `challenger` aliases |

---

## Discovery Questions & Answers

All answers were given by the user during discovery (decisions D-01 to D-16 in *Key Decisions*).

| # | Question | Answer | Impact |
|---|---|---|---|
| 1 | Purpose: what should the first release deliver? | An end-to-end thin slice: reproducible sample, batch and stream ingestion into one Silver table with expectations, minimal daily features, one registered model, batch scoring | Breadth over depth; every layer exists in v0.1, each kept minimal |
| 2 | ML framing: which prediction task? | Binary classification: does a household exceed its usual daily consumption tomorrow (D-05), with a same-weekday baseline and a 1.3x threshold (D-16) | Label defined at daily grain; forecasting deferred to v0.3 |
| 3 | Consumers: who reads the output? | A Gold predictions table written by a batch scoring job using the `champion` model, plus the UC feature table for training. No real-time consumer in v0.1 | Batch scoring only; serving endpoint out of scope. Consumer: a demand-response team (hypothetical) reading daily predictions (Q-08) |
| 4 | Constraints: which platform and budget? | Databricks Free Edition, serverless only (D-03); Kafka on the Aiven free tier (D-12) | Quota-aware design, scheduled micro-batches, environment assumptions validated by spikes |
| 5 | Data source: which dataset? | Smart Meters in London, `halfhourly_dataset` long format (D-01, D-04) | One row per reading maps directly to one Kafka event |
| 6 | Scale: how much data? | 60 households, 20 per ACORN group, stratified by group and tariff (D-06, D-07); size is a parameter | Fits the Free Edition quota; stratification is mandatory (F-01) |
| 7 | Time scope: which period and how is it split between batch and stream? | Study period 2012-07-01 to 2014-02-28 (D-08); historical `tstp < 2013-12-01`, stream `tstp >= 2013-12-01` (D-09) | Explicit, testable boundary; reconciliation test at the cutoff |
| 8 | Master data: how does household data arrive? | Static file in v0.1; Postgres with Debezium CDC in v0.2 (D-14) | No SCD in v0.1 |

---

## Sample Data Inventory

| Type | Location | Volume | Notes |
|---|---|---|---|
| Input data: readings | `data/raw/halfhourly_dataset/halfhourly_dataset/block_*.csv` (Kaggle, `jeanmidev` copy) | 112 blocks, about 50 households each; profiled 9 blocks: 13,059,525 rows, 450 households | `LCLid, tstp, energy(kWh/hh)`, all text; report `docs/profiling/halfhourly_readings.md` |
| Input data: households | `data/raw/informations_households.csv` | 5,566 rows | `LCLid, stdorToU, Acorn, Acorn_grouped, file`; report `docs/profiling/informations_households.md` |
| Input data: weather | `data/raw/weather_hourly_darksky.csv` | Hourly, 2011-11 to 2014-03 | Not yet profiled; timezone unconfirmed (A-07) |
| Input data: calendar | `data/raw/uk_bank_holidays.csv` | UK bank holidays 2012-2014 | Not yet profiled |
| Derived sample (seed 42) | Output of the sampling script (not yet in the repository) | Historical: 1,432,405 rows in 17 monthly files (about 63 MB), including 60 `Null` system rows. Stream: 247,569 rows (about 11 MB), no non-numeric values | 60 households, 6 blocks; 99.1% of household-days have all 48 readings |
| Expected output | N/A | N/A | Gold predictions table; schema set in `/define` |
| Ground truth | Derived from readings | N/A | Label computed from the readings themselves (section *Label analysis*); no external ground truth |

Not used in v0.1: `daily_dataset`, `hhblock_dataset`, `weather_daily_darksky.csv`,
`acorn_details.csv` (wide format or group-level indicators).

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
| F-05 | Dead or faulty meters | HH F-08: 2 households with >= 90% zeros, MAC004067 (100% zero) and MAC004672 (91% zero); 1 household with constant energy. EX: same pattern (one 100%, one 91%) | Per-household quality flag; exclude from training above a zero-share threshold |
| F-06 | Reading gaps and per-household coverage | HH F-06: 450 households, median coverage 99.8%, min 75.0%, 1 below 80%. **Refinement:** EX reported the worst household at about 19% missing; the 9-block profile shows up to 25% missing | Coverage feature and `warn` expectation on gaps; coverage threshold is a parameter |
| F-07 | Staggered start and end per household | HH F-07: starts 2011-11-23 to 2013-07-04, ends 2012-06-26 to 2014-02-28; readings span 2011-11-23 13:00 to 2014-02-28 00:00. **Refinement:** EX reported starts from 2011-12; the 9-block profile shows starts from 2011-11-23 | Fixed study window (D-08); "active household" defined per period; absence is not zero consumption |
| F-08 | Invalid ACORN labels | HI: `Acorn` has 49 `ACORN-U` and 2 `ACORN-`; `Acorn_grouped` the same | Excluded from sampling |
| F-09 | No duplicate keys | HH F-04: `(LCLid, tstp)` unique, 0 duplicates in 13,059,525 rows. HI F-09: `LCLid` unique, 0 duplicates in 5,566 rows | Idempotency can be asserted with row counts; Silver dedup key `(household, reading_ts)` |
| F-10 | Reading timestamps are UTC | EX: DST transition days have exactly 48 readings | Weather timezone must be confirmed before joining (A-07) |
| F-11 | Source header not Delta/SQL safe | HH F-01: column `energy(kWh/hh)` | Positional schema in Bronze; rename to `energy_kwh` in Silver |
| F-12 | Tariff mix varies by block | EX: ToU share per block ranges 0% to 64%; 21 blocks have none. HI: population 4,443 `Std`, 1,123 `ToU` (about 20% ToU) | Sample tariff mix depends on the blocks drawn; seed 42 yields 20% ToU, matching the population; the manifest reports the mix on every run |
| F-13 | Low coverage is the main exclusion reason | EX (sampling run): 26 of 27 excluded candidates fell below 80% coverage in the study period, none as dead meters in the planned blocks | Coverage threshold drives sample composition; keep it a parameter. Note: HH coverage (F-06) is measured over each household's own span, not the study period, so the two numbers are not directly comparable |

### Label analysis

Analysed on full days only (48 readings), over the whole study period, on the seed-42 sample.
Positive rate = share of household-days labelled 1.

| Baseline for "usual" consumption | Threshold | Positive rate |
|---|---|---|
| Median of previous 7 days | > 1.3x | 13.2% |
| Median of previous 28 days | > 1.2x / 1.3x / 1.5x | 21.3% / 14.3% / 7.3% |
| Mean of previous 28 days + k std | k = 1.0 / 1.5 | 17.6% / 9.4% |
| **Median of last 4 same-weekday days** | **> 1.2x / 1.3x / 1.5x** | **21.4% / 14.7% / 7.9%** |

| ID | Finding | Implication |
|---|---|---|
| L-01 | With calendar-day baselines, Sunday has about 22% positives vs about 12.5% on weekdays | A model would learn "tomorrow is Sunday"; metrics would look good without useful signal |
| L-02 | With the same-weekday baseline, positives are stable at 14-15% across all weekdays | Weekly cycle removed from the target |
| L-03 | Seasonality remains: October about 21.5%, February about 8.8% | The 4-week baseline lags the heating-season onset; temperature and month become strong features; the training range must span more than one season |
| L-04 | Positive rate differs by group: Affluent about 17%, Comfortable about 15%, Adversity about 11% (28-day baseline) | Report metrics per ACORN group, not only overall |

**Proposed label (to confirm in `/define`):** `label = 1` when a household's consumption on day
D+1 is greater than 1.3 times the median of its consumption on the last 4 full days with the same
weekday as D+1, all strictly before D+1. Days without 48 readings are neither labelled nor used in
the baseline.

---

## Approaches Explored

The main architectural choice is how streaming readings reach the lakehouse. The dataset and the
Kafka broker were compared separately and are summarised after the approaches.

### Approach A: Local producer replays readings into Kafka, Structured Streaming consumes (recommended)

A local Python producer (Docker) replays post-cutoff readings into an Aiven Kafka topic
`meter-readings`, keyed by household and preserving event time. A Databricks job consumes the topic
with Structured Streaming (`AvailableNow`) into a Bronze stream table. Historical files are ingested
by Auto Loader from a UC Volume into a Bronze historical table. Silver unions both.

- **Pros:** Producers live outside the lakehouse, as real meters do; no workspace quota spent on
  producing; exercises a real network path, authentication and offsets.
- **Cons:** Depends on a local machine running; external broker reachability and auth on serverless
  must be validated (A-01, A-03, A-06); free-tier service powers off after inactivity.
- **Why recommended:** Most realistic event path at zero cost, and it keeps the quota for ingestion,
  features and training.

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
| **Confirmed by** | Christian, 2026-10-07 |
| **Reasoning** | Realistic producer placement outside the lakehouse, zero cost, no quota spent on producing; the dataset offers real quality issues and absolute UTC timestamps |

**Architecture (v0.1):**

```text
                 Kaggle CSVs
                      |
           sampling script (local)
          /           |            \
  historical/     stream/       dimensions/
  monthly CSVs    one CSV       households, weather, holidays
       |              |              |
   UC Volume     producer (Docker)   UC Volume
       |              |              |
  Auto Loader    Aiven Kafka         |
       |         topic meter-readings|
       |              |              |
       |      Structured Streaming   |
       |       (Trigger.AvailableNow)|
       v              v              v
  Bronze readings  Bronze readings  Bronze dimensions
  (files)          (Kafka)
          \        /                 |
     Silver readings              Silver dimensions
     (union, dedup, expectations)    |
                \                   /
                 Gold features (daily grain) + label
                         |
          UC feature table + training set (point-in-time)
                         |
            MLflow run -> UC model @champion
                         |
                 batch scoring -> Gold predictions
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
- Silver readings: one row per `(household, reading_ts)`, deduplicated, with expectations from F-02
  to F-06 and F-09.

---

## Key Decisions

| # | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| D-01 | Dataset: Smart Meters in London (Kaggle, `jeanmidev` copy with `halfhourly_dataset`) | Real IoT data, multiple sources, real quality issues, absolute timestamps | Six other datasets (see *Dataset comparison*) |
| D-02 | New repository; reuses naming, spec structure and bundle conventions from the `sdd-kafka-databricks` project | Independent repository; no code coupling | Not recorded |
| D-03 | Platform: Databricks Free Edition, serverless only | Zero cost; constraints recorded as ADRs | Not recorded |
| D-04 | Reading format: `halfhourly_dataset` (long) | One row per reading is the natural event shape for Kafka | `hhblock_dataset` (wide, one row per day) |
| D-05 | ML framing: binary classification, household exceeds its usual daily consumption tomorrow | Simple to evaluate; keeps focus on data engineering | Forecasting (deferred to v0.3) |
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
| D-16 | Label baseline: median of the last 4 same-weekday full days, threshold 1.3x | Removes the weekly cycle from the target (L-01, L-02) | Calendar-day 7- or 28-day baselines |

---

## Out of Scope (YAGNI)

| Item | Reason | Revisit in |
|---|---|---|
| Household master data in Postgres with Debezium CDC and SCD Type 2 | Static file is enough for the thin slice | v0.2 |
| Point-in-time joins against a slowly changing dimension | Depends on SCD Type 2 | v0.2 |
| Richer features (weather sensitivity, profile deviation, calendar effects) | v0.1 needs a minimal feature set only | v0.2 |
| Forecasting formulation and backtesting by windows | Classification framing first (D-05) | v0.3 |
| Drift monitoring and retraining trigger | Needs a model in production first | v0.3 |
| Real-time model serving endpoint | Free Edition serving limits; batch scoring suffices | v0.4, or documented only |
| Larger sample for clustering and query optimisation benchmarks | Quota; not needed for correctness | Separate one-off scenario |
| `acorn_details.csv` enrichment | Group-level indicators add little at household level | Not planned |
| `daily_dataset`, `hhblock_dataset`, `weather_daily_darksky.csv` | Derivable from the selected sources | Not planned |

**Release roadmap:**

| Release | Scope |
|---|---|
| v0.1 | Thin slice end to end: sample, both ingestion paths, Silver with expectations, minimal features, one registered model, batch scoring |
| v0.2 | CDC for household master data, SCD Type 2, point-in-time features against the dimension, broader feature set |
| v0.3 | Forecasting and temporal backtesting, monitoring |
| v0.4 | Serving and scale-out scenario |

---

## Assumptions & Open Questions

| ID | Assumption or question | How it will be resolved | Status |
|---|---|---|---|
| A-01 | Serverless reaches the Aiven broker | TCP connectivity test from serverless | Validated (2026-10-06); not yet recorded in an ADR |
| A-02 | Auto Loader ingests CSVs from a UC Volume on serverless with `Trigger.AvailableNow` | Spike `spikes/databricks/01_spike_autoloader.py` | Pending |
| A-03 | Spark Kafka source authenticates with SASL_SSL and an inline PEM CA (`ssl.truststore.type=PEM`) | Spike `spikes/databricks/02_spike_kafka_consume.py` | Pending; fallback: CA file in a Volume |
| A-04 | MLflow registers models in UC and resolves aliases on Free Edition | Spike `spikes/databricks/03_spike_mlflow_uc.py` | Pending |
| A-05 | Serverless streaming supports only `AvailableNow`-style triggers, so ingestion is scheduled micro-batch | Spike 02 plus Databricks documentation | Pending |
| A-06 | The SASL mechanism offered by Aiven is SCRAM-SHA-256 | Aiven console | Pending |
| A-07 | Weather timestamps are UTC, like readings (F-10) | Profiling the weather file in Databricks | Pending |
| A-08 | Off-grid timestamps (F-03) are the same rows as the `Null` values (F-02) in all blocks, not only in blocks 0, 100, 110 | Join the two conditions on the 9 profiled blocks in Databricks or locally | Pending |

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
| Label threshold is a business choice (L-01 to L-03) | Positive rate swings from 7.9% to 21.4% between 1.5x and 1.2x | Record the choice and the label analysis table in an ADR |
| Seasonal shift in positive rate (L-03) | A temporal split could put one season only in test | Training range covers at least one full year; evaluate per month |
| Sample tariff mix skewed (F-12) | Model under-represents ToU households | Mix is balanced for seed 42; manifest reports it on every run; tariff-aware selection if the seed changes |
| Quality expectation tied to one timestamp (F-03) | Off-grid rows on other dates pass unnoticed | Grid-based expectation, not a hard-coded instant |
| Local producer depends on a running machine | Stream pauses when it is off | Accepted for v0.1; documented in limitations |
| Sampling script and plan not yet in the repository | Sample numbers in this document cannot be reproduced from the repository | Commit the script and `plan.json` before `/design` is finalised |

### Open questions for `/define`

| ID | Question | Notes |
|---|---|---|
| Q-01 | Confirm or adjust the label threshold (1.3x, same-weekday baseline) | Label analysis above; D-16 |
| Q-02 | Feature grain and minimum feature set for v0.1 | Daily grain proposed |
| Q-03 | Train, validation and test date ranges inside the study period | Must cover more than one season (L-03) |
| Q-04 | Expectation action per quality rule (`warn`, `drop`, `fail`) and the layer where each rule lives | F-02 to F-06, F-09 |
| Q-05 | Catalog and schema layout per environment (`dev` only on Free Edition, or simulated `dev`/`prod` schemas) | Free Edition limits |
| Q-06 | ~~Naming~~ **Answered 2026-10-15:** adopt `docs/conventions/naming.md` (`household_id`, `kafka_meter_readings`, `files_meter_readings`); `LCLid` is renamed to `household_id` from Bronze onwards, including the Kafka event contract. No ADR needed | Conflict found while writing this document |
| Q-07 | Pipeline type for Silver and Gold under the one-active-pipeline-per-type limit | Free Edition limits |
| Q-08 | ~~Business consumer~~ **Answered 2026-10-15:** a demand-response team (hypothetical) reads the next day's at-risk households once per day. Daily batch scoring writes a Gold table with `household_id`, `target_date`, `score`, `label`, `model_version`, `scored_at` | Not answered in discovery |
| Q-09 | ~~Exclusion thresholds~~ **Answered 2026-10-15:** exclude a household from training when coverage < 80% or zero share >= 90%; both are parameters | F-05, F-06, F-13; matches the seed-42 sample and catches MAC004067 and MAC004672 |
| Q-10 | ~~Profiled block set~~ **Answered 2026-10-15:** the 9-block profile covers blocks 0, 11, 17, 49, 69, 82, 100, 104, 110; list added to the report header | Confirmed by the author; consistent with 450 households (9 x 50) |

---

## Suggested Requirements for Define

- **Problem statement (draft):** Build a reproducible, governed data foundation on Databricks Free
  Edition that ingests smart meter readings from files and from Kafka into one quality-checked table,
  derives point-in-time correct daily features and a next-day consumption-spike label, and trains,
  registers and batch-scores a model with lineage from raw reading to model version.
- **Success criteria (draft):**
  - Running the sampling script twice with the same plan produces byte-identical outputs (checksums
    in a manifest).
  - Bronze historical row count equals the manifest count; re-running ingestion with no new files or
    messages ingests 0 rows.
  - Silver row count equals the manifest total minus rows dropped by expectations, every dropped row
    accounted for; no reading duplicated or lost at the cutoff.
  - No feature for a target day uses data from that day or later (leakage test); splits are temporal.
  - The registered model version links to its training run and feature table in UC lineage; alias
    `champion` resolves.
  - Evaluation reports PR-AUC and precision/recall, overall and per ACORN group; accuracy alone is
    not reported.
  - All jobs and pipelines deploy from a Databricks Asset Bundle.
- **Constraints:**
  - Free Edition serverless and Aiven free tier only.
  - No credentials in code, bundle files or git; Kafka secrets in a Databricks secret scope; local
    `.env` ignored.
  - Sample size, period, cutoff and replay speed are parameters, not code changes.
  - Time is UTC end to end; event time and ingestion time are separate columns.

---

## Self-Review

- **Weak points:**
  - Several findings (F-01, F-10, F-12, F-13) and all label numbers come from exploratory profiling
    and a sampling run whose script and `plan.json` are not yet in the repository, so they cannot be
    regenerated from the repository today.
  - The 9-block profiling report does not list which blocks were profiled (inferred from the local
    `data/raw` contents only), and it contradicts the
    earlier single-instant reading of the `Null` event (F-03 refinement). Whether the off-grid rows
    and the `Null` rows coincide is unconfirmed (A-08).
  - Coverage numbers in F-06 (household's own span) and F-13 (study period) use different
    denominators.
  - Weather and bank-holiday files are not profiled; A-07 is the only check planned.
  - The business consumer of the predictions is hypothetical (a demand-response team, Q-08); no real service-level expectations exist.
- **Risks:** Free Edition quota and the Aiven free tier are single points of failure for the stream
  path; label threshold choice moves the positive rate between 7.9% and 21.4%; seasonality (L-03)
  can make a temporal split unrepresentative.
- **What I would do differently:** Generate all profiling evidence through `scripts/profile_data.py`
  with the block list recorded in the report header, and profile the exact sample blocks plus
  weather and holidays before writing the label analysis.
- **Next improvement:** Commit the sampling script and plan, profile the six sample blocks, the
  weather and the holidays files with `scripts/profile_data.py` (using `--start-id 14`), and resolve
  A-08 by checking whether off-grid and `Null` rows coincide.

---

## Next Step

`/define .claude/sdd/features/BRAINSTORM_SMART_METER_ML_FOUNDATION.md`
