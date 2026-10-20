# Runbook: meter ingestion

How to set up, deploy, run, verify and recover the meter ingestion pipeline (feature
METER_INGESTION). It targets the `dev` bundle target on Databricks Free Edition with an Aiven
Kafka service. Design: `.claude/sdd/features/DESIGN_METER_INGESTION.md`. Decisions: `docs/adr/`.
Contracts: `docs/contracts/`.

## What runs where

```text
local machine                      Aiven Kafka                Databricks (serverless, target dev)
-------------                      -----------                -----------------------------------
sample CSVs  --databricks fs cp--------------------------->   Volume landing/ ---+
producer (Docker) --> topic meter-readings (2 partitions) -->                     |
                                                              job smart_meter_ingestion (daily 06:00 UTC)
                                                               setup_catalog
                                                               ingest_files  (Auto Loader, availableNow)
                                                               ingest_kafka  (Kafka source, availableNow)
                                                               refresh_silver_gold (pipeline update)
                                                              -> bronze.* -> silver.* -> gold.*
```

- Bronze tables (`files_meter_readings`, `files_households`, `kafka_meter_readings`) are
  append-only and are the only replay source. The Kafka topic is not (ADR 0006).
- One triggered serverless pipeline, `smart_meter_silver_gold`, recomputes Silver and Gold from all
  of Bronze on every update (ADR 0004, ADR 0005).
- Rule, scope and duplicate counts are table totals over `silver.meter_readings_evaluated`,
  computed by `src/smart_meter_peak_prediction/metrics.py`. They are not read from the event log.
- Time is UTC end to end: job and pipeline sessions run with `spark.sql.session.timeZone = UTC`.

### Dependency on Aiven

The pipeline task `refresh_silver_gold` depends on both ingestion tasks. The Kafka task has no
retry and an 840 s timeout, so with the Aiven service off or unreachable it fails within
15 minutes and the pipeline task does not run. **An Aiven outage therefore stalls the refresh of
Silver and Gold, including the file-based history, until the next successful run.** Bronze and the
checkpoint of the Kafka stream stay unchanged on such a failure. To refresh Silver and Gold while
Aiven is off, run the pipeline directly (see "Broker outage").

## Prerequisites

| Item | Notes |
|---|---|
| Databricks CLI, authenticated | `databricks auth login --host <workspace-url> --profile dev` (OAuth). Commands below use `-p dev` |
| Python 3.11 and the project | `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev,sample,producer,integration]"` |
| Docker | For the replay producer |
| Kaggle raw files in `data/raw` | Needed only to regenerate the sample (git-ignored) |
| Aiven Kafka service | Free tier; powers off after inactivity |
| Java 17 | Only for the local Spark tests |

## 1. Secrets

Nothing secret goes into the repository, the bundle or a notebook. Two stores hold the same
values: the Databricks secret scope `smart_meter` (read by `ingest_kafka`) and the git-ignored
`.env` (read by the local producer).

Scope (once). Without a value flag, `put-secret` prompts for the value, so a password never
appears on the command line or in shell history. The multi-line CA is read from standard input:

```bash
databricks secrets create-scope smart_meter -p dev
databricks secrets put-secret smart_meter kafka-bootstrap-servers -p dev
databricks secrets put-secret smart_meter kafka-sasl-username -p dev
databricks secrets put-secret smart_meter kafka-sasl-password -p dev
databricks secrets put-secret smart_meter kafka-ca-pem -p dev < /absolute/path/outside/repo/ca.pem
```

The CA certificate is public data. Keep the file outside the repository (`*.pem` is git-ignored
anyway).

Local `.env`: copy `.env.example` to `.env` and fill it in (`KAFKA_BOOTSTRAP`, `KAFKA_USERNAME`,
`KAFKA_PASSWORD`, `KAFKA_SASL_MECHANISM`, `KAFKA_CA_PATH`, `KAFKA_TOPIC`, `REPLAY_SPEED`,
`SAMPLE_STREAM_FILE`, `DATABRICKS_WAREHOUSE_ID`). Write `KEY=value` without quotes: Docker's
`--env-file` keeps quotes literally.

Verify the repository is clean of credentials: `pre-commit run --all-files` and
`pytest tests/test_secrets_hygiene.py`.

## 2. Sample generation and upload

The seed-42 sample (60 households, 1,432,405 historical rows, 247,569 stream rows) is generated
locally and checked against `config/sample_manifest.json` and `config/sample_households.csv`.

```bash
python scripts/prepare_sample.py build --out data/sample/seed42
```

Upload the historical files and the household file to the landing Volume. The Volume exists after
the setup notebook has run (step 4):

```bash
databricks fs cp -r --overwrite -p dev data/sample/seed42/historical \
  dbfs:/Volumes/smart_meter_dev/bronze/landing/readings/historical
databricks fs cp --overwrite -p dev data/sample/seed42/dimensions/households_sample.csv \
  dbfs:/Volumes/smart_meter_dev/bronze/landing/households/households_sample.csv
```

New historical files go under a new name in the same folder; Auto Loader ingests only files it has
not seen. Re-uploading an unchanged file is not re-ingested.

## 3. Aiven: power on and create the topic

Aiven does **not** create topics automatically, and the free service powers off after inactivity.

1. Power the service on in the Aiven console and wait until it is running.
2. Create the topic `meter-readings` with 2 partitions (the contract in
   `docs/contracts/meter-readings.yaml`). The command reads the connection settings from your
   `.env` and prints no credential. It is idempotent: an existing topic is reported, not changed.

```bash
set -a; . ./.env; set +a
python - <<'PY'
import os
from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
from smart_meter_peak_prediction.producer import build_kafka_config

wanted = ("bootstrap.servers", "security.protocol", "sasl.mechanism",
          "sasl.username", "sasl.password", "ssl.ca.location")
config = {k: v for k, v in build_kafka_config(os.environ).items() if k in wanted}
topic = os.environ.get("KAFKA_TOPIC", "").strip() or "meter-readings"
future = AdminClient(config).create_topics(
    [NewTopic(topic, num_partitions=2, replication_factor=-1)]  # -1: broker default
)[topic]
try:
    future.result()
    print(f"created topic {topic}")
except KafkaException as error:
    if "TOPIC_ALREADY_EXISTS" in str(error):
        print(f"topic {topic} already exists")
    else:
        raise
PY
```

## 4. Deploy

Validate first. This is read-only:

```bash
databricks bundle validate -t dev -p dev
```

### First deploy on a fresh workspace (three steps)

Terraform creates the pipeline in the same apply as the job and the pipeline needs the catalog, so
a first deploy fails when the catalog does not exist yet (ADR 0001, DA-06; ADR 0003). The order is:

```bash
# 1. Sync the files. Expected to fail at pipeline creation with:
#    "Catalog 'smart_meter_dev' does not exist."   (the files are synced before the error)
databricks bundle deploy -t dev -p dev

# 2. Run the setup notebook once from the synced files. It is idempotent and needs no
#    parameters (the widgets default to the bundle defaults). In the workspace UI open
#    <bundle root>/files/notebooks/setup_catalog and run all cells on serverless compute.
#    The bundle root is printed by:
databricks bundle validate -t dev -p dev -o json   # field workspace.file_path

# 3. Deploy again. This time it creates the job and the pipeline.
databricks bundle deploy -t dev -p dev
```

Record the exit code of steps 1 and 3 (step 1 non-zero, step 3 zero) as evidence for AC-28.

Later deploys are a single `databricks bundle deploy -t dev -p dev`. The `setup_catalog` job task
keeps the catalog, schemas, Volumes and Bronze tables in place on every run, but it cannot help
on the first deploy.

Development mode shows the job and the pipeline as `[dev <user>] smart_meter_ingestion` and
`[dev <user>] smart_meter_silver_gold` and pauses the schedule. The base names (prefix stripped by
`^\[dev [^\]]+\] `) are the contract names. A `prod` target deployed in production mode has no
prefix. It is documented in `databricks.yml` and ADR 0003 but not deployed in this release.

If `CREATE CATALOG` is not allowed in a workspace, use the fallback layout (catalog `workspace`,
schemas `smart_meter_dev_<layer>`) by overriding the layout variables in the `dev` target; see the
comment in `databricks.yml` and ADR 0003. Integration tests then need `SMART_METER_CATALOG` and the
schema overrides.

## 5. Produce, run and verify

### Produce

Build the image once, then replay. `REPLAY_SPEED=0` publishes without pacing. The producer is
idempotent (`acks=all`); delivery is at-least-once and Silver deduplicates.

```bash
docker build -f docker/producer/Dockerfile -t smart-meter-producer .
mkdir -p out && grep '^\(KAFKA_\|REPLAY_\)' .env > "$PWD/out/producer.env"   # keep Databricks keys out of the container
docker run --rm --user "$(id -u):$(id -g)" --env-file "$PWD/out/producer.env" \
  -e KAFKA_CA_PATH=/certs/ca.pem -e SAMPLE_STREAM_FILE=/data/readings_stream.csv \
  -v "$PWD/data/sample/seed42/stream/readings_stream.csv:/data/readings_stream.csv:ro" \
  -v /absolute/path/outside/repo/ca.pem:/certs/ca.pem:ro \
  smart-meter-producer
```

`--dry-run` writes the events as JSON lines to stdout without contacting the broker, and
`--limit N` publishes only the first N events.

### Run the job

```bash
databricks bundle run -t dev -p dev smart_meter_ingestion
```

It runs the four tasks in order: `setup_catalog`, then `ingest_files` and `ingest_kafka` in
parallel, then `refresh_silver_gold`. Run a subset with `--only`, for example
`--only setup_catalog,ingest_files`. Run the pipeline alone (no Kafka needed):

```bash
databricks bundle run -t dev -p dev smart_meter_silver_gold
```

The daily schedule (06:00 UTC) is paused in development mode. Failures send an e-mail to the
deploying user. One run takes minutes on serverless; the Free Edition daily quota applies.

### Check the counts

Counts are table totals, queryable at any time after an update. Print the SQL and run it in the SQL
editor:

```bash
python -c "from smart_meter_peak_prediction import config, metrics; \
print(metrics.rule_counts_sql(config.Settings().table('silver', 'meter_readings_evaluated')))"
```

Result columns: `evaluated_rows` (must equal the rows of both Bronze reading tables), one column
per drop rule (`qr_02` to `qr_07`, not counting quarantine duplicates), `sf_01` (outside the study
period), `qr_09` (all duplicates: valid duplicates plus quarantine duplicates),
`quarantine_duplicates` (the repeats of a dropped record), `quarantine_rows` and `silver_rows`.
`metrics.reconciliation_sql` classifies every Bronze row exactly once, in one of five classes
(seed 42: 60 quarantined, 0 out of period, 0 duplicates, 0 quarantine duplicates, 1,679,914 in
Silver).
Rejected rows are in `silver.meter_readings_quarantine`.

### Evidence order for the integration tests

The integration tests (`tests/integration`, marker `integration`) target the deployed `dev`
environment. They are excluded from the default `pytest` run and from CI. Credentials come from the
CLI profile; no secret is read from a file.

```bash
export DATABRICKS_CONFIG_PROFILE=dev       # and DATABRICKS_WAREHOUSE_ID if not the first warehouse
pytest -m integration tests/integration/<file>::<test>
```

AC-25 reads the per-household facts from the local `data/sample/seed42/manifest.json` (or
`SAMPLE_MANIFEST`), so build the sample locally first. AC-30 and AC-31 use the latest successful
run of all four tasks, so run the full job right after producing (step C); partial `--only` reruns do not count. Some tests are before/after pairs: the `before` test stores a snapshot in `out/evidence/`
(git-ignored) and the `after` test compares against it, so run them in this order.

| Step | Do | Then run |
|---|---|---|
| A. Files only | Deploy (section 4), upload the sample (section 2), then `databricks bundle run -t dev -p dev smart_meter_ingestion --only setup_catalog,ingest_files` | `test_gold_tables.py::test_ac26_i18_before_first_update_gold_schema_is_empty` |
| B. First pipeline update | `databricks bundle run -t dev -p dev smart_meter_silver_gold` (from an empty Gold schema) | `test_gold_tables.py::test_ac26_i18_after_first_update_summary_view_exists_and_update_completed`, `test_reprocessing.py::test_ac24_before_kafka_snapshot`, `test_bronze_ingestion.py::test_ac05_*`, `test_ac06_*` |
| C. Kafka load | Aiven on, topic created, one full replay (produce), then `databricks bundle run -t dev -p dev smart_meter_ingestion` | `test_bronze_ingestion.py::test_ac07_*`, `test_ac08_*`; `test_silver_tables.py` (all); `test_gold_tables.py` (all except the `i18` pair); `test_reprocessing.py::test_ac24_after_*`; `test_deployment.py::test_ac28_*`, `test_ac30_*` |
| D. Broker outage (AC-10) | `test_bronze_ingestion.py::test_ac10_before_outage_snapshot`; power Aiven off; run the job (it fails); see "Broker outage" | `test_bronze_ingestion.py::test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged` |
| E. Recovery | Aiven on; run the job again; it passes | `test_bronze_ingestion.py::test_ac07_*`, `test_deployment.py::test_ac30_*` (the latest successful run) |
| F. Replay (AC-09) | `test_reprocessing.py::test_ac09_before_replay_snapshot`; produce the full stream again; run the job | `test_reprocessing.py::test_ac09_after_replay_silver_unchanged` |
| G. Full refresh (AC-27) | `test_reprocessing.py::test_ac27_before_full_refresh_snapshot`; Aiven may be off; `databricks bundle run -t dev -p dev smart_meter_silver_gold --full-refresh-all` | `test_reprocessing.py::test_ac27_after_*`, `test_ac12_totals_consistent_after_full_refresh` |

Steps A and B also give the AC-28 deploy evidence (exit codes of section 4). The exact seed-42
counts in step C hold for a state with no replay; run step F last among the data tests.

## 6. Operations

### Broker outage

With the service off or unreachable, `ingest_kafka` fails; it does not retry. Bounded Kafka
timeouts and the task timeout (840 s) make it fail within 15 minutes, and the stream checkpoint and
`bronze.kafka_meter_readings` stay unchanged (`failOnDataLoss` is on). The pipeline task is skipped.

1. Power Aiven on.
2. Run the job again. The Kafka stream resumes at the checkpoint offsets.
3. To refresh Silver and Gold in the meantime, using only what Bronze already holds, run the
   pipeline directly: `databricks bundle run -t dev -p dev smart_meter_silver_gold`.

The free tier keeps messages only briefly. If a consumer outage outlasts the retention, the messages
are lost to the lakehouse and `failOnDataLoss` fails the task; re-produce them from the stream
sample file (duplicates are removed by Silver).

### Full refresh

Every update already recomputes Silver and Gold from all of Bronze, so a full refresh gives the
same tables:

```bash
databricks bundle run -t dev -p dev smart_meter_silver_gold --full-refresh-all
```

No Kafka access is needed. Changing the study period or the cutoff needs only a redeploy with new
variable values (`--var study_end=...`) and a pipeline update.

### Update from an empty Gold schema

The summary check dataset (`household_data_quality_check`, Python) reads the summary view that the
SQL file `pipelines/household_data_quality.sql` creates in the same pipeline. That dependency is
proved only by a local fake, so the first update must start from an empty Gold schema. A fresh
workspace does this naturally (evidence steps A and B). If the update fails because the check
dataset cannot read the view, report the failing update and its error text. The decided fallback
(2026-10-19) is to derive the check from the monthly table (`gold.household_data_quality_monthly`),
a DESIGN change applied through `/iterate`.

### Bronze reset and Bronze schema changes

`CREATE TABLE IF NOT EXISTS` in the setup notebook creates a missing Bronze table but does **not**
migrate an existing one. If the Bronze schema in `src/smart_meter_peak_prediction/bronze.py`
changes, or a Bronze table must be rebuilt, reset it:

1. Run in the SQL editor: `DROP TABLE <catalog>.bronze.<table>;`
2. Remove its checkpoint:
   `databricks fs rm -r -p dev dbfs:/Volumes/smart_meter_dev/bronze/checkpoints/<stream>`
   (`files_meter_readings`, `files_households` or `kafka_meter_readings`).
3. Run the job (`setup_catalog` recreates the table; the stream re-ingests: files from the Volume,
   Kafka from the earliest message still on the topic; re-produce from the sample if needed).
4. The pipeline update that follows recomputes Silver and Gold.

Because Bronze is append-only, there is no in-place correction.

### Stream error redaction check

The Kafka notebook never prints its options, and a failing stream must not print the credentials
either. To verify, run `ingest_kafka` against a scratch secret scope that holds a real broker host
and CA but sentinel credentials (Aiven on), so that authentication fails:

```bash
databricks secrets create-scope smart_meter_redaction_test -p dev
databricks secrets put-secret smart_meter_redaction_test kafka-bootstrap-servers -p dev   # real host
databricks secrets put-secret smart_meter_redaction_test kafka-ca-pem -p dev < /absolute/path/outside/repo/ca.pem
databricks secrets put-secret smart_meter_redaction_test kafka-sasl-username -p dev --string-value redaction-sentinel-user
databricks secrets put-secret smart_meter_redaction_test kafka-sasl-password -p dev --string-value redaction-sentinel-password
```

Submit the notebook once with that scope (take `FILES` from `workspace.file_path` of
`databricks bundle validate -t dev -p dev -o json`; the notebook path has no `.py` extension):

```bash
databricks jobs submit -p dev --json '{
  "run_name": "kafka-redaction-check",
  "tasks": [{"task_key": "redaction", "notebook_task": {
    "notebook_path": "FILES/notebooks/ingest_kafka",
    "base_parameters": {"src_path": "FILES/src", "secret_scope": "smart_meter_redaction_test"}}}]}'
databricks jobs get-run <run_id> -p dev -o json     # take tasks[0].run_id
REDACTION_RUN_ID=<task run id> REDACTION_SENTINELS=redaction-sentinel-user,redaction-sentinel-password \
  pytest -m integration tests/integration/test_bronze_ingestion.py::test_ac29_failed_stream_error_does_not_leak_credentials
databricks secrets delete-scope smart_meter_redaction_test -p dev
```

### Rotating credentials

Update the secret with `put-secret` (and `.env` for the producer). No deploy is needed.

## 7. Known limits

- Silver and Gold are recomputed in full on every update (about 1.7 M rows; one update over
  1.68 M synthetic rows took 63 s in the feasibility spike). Revisit when an update exceeds
  15 minutes or Bronze exceeds 50 M rows (ADR 0005).
- A replayed message that is invalid is not quarantined again: dropped rows are deduplicated on
  `_dedup_key` (the raw business key when the payload has a readable `household_id` and `reading_ts`, also if it
  fails QR-07, otherwise a hash of the payload), the
  earliest-ingested row stays in the quarantine, and each repeat is counted in `qr_09` and in
  `quarantine_duplicates`, and in no per-rule total. The seed-42 stream has no invalid message, so
  its figures show no quarantine duplicate.
- Free Edition: one active pipeline per type, at most five concurrent tasks, a daily compute quota,
  and a Kafka service that powers off when idle (`.claude/kb/databricks/free-edition.md`).
- The unit tests prove the pipeline logic on local Spark with a fake `dlt`; Lakeflow behaviour is
  proved on the platform by the integration tests above and by the feasibility spikes
  (`docs/spikes/README.md`).
