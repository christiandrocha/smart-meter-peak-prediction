# Databricks notebook source
# Spike 03 (DA-05). STATUS: written, NOT RUN. Throwaway code, never imported by src/.
#
# Question: with the broker unreachable, does the Kafka source fail within the configured client
# timeouts, and is the checkpoint left unchanged?
#
# Pass criteria (ADR 0001, DA-05)
#   - the availableNow query FAILS (does not hang), in under 600 seconds;
#   - the checkpoint folder listing (paths and sizes) is identical before and after;
#   - the scratch table row count is unchanged.
#
# Prerequisites (run by the user)
#   1. Spike 02 completed (its table and checkpoint are reused).
#   2. Power OFF the Aiven Kafka service in the Aiven console and wait until it is off.
#   3. Run this notebook. Power the service back on afterwards.
#
# The notebook never prints the Kafka options; error text is redacted before printing.

# COMMAND ----------

import time

from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "smart_meter_dev")
dbutils.widgets.text("schema", "bronze")
dbutils.widgets.text("scope", "smart_meter")
dbutils.widgets.text("topic", "meter-readings")
dbutils.widgets.text("sasl_mechanism", "SCRAM-SHA-256")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
scope, topic = dbutils.widgets.get("scope"), dbutils.widgets.get("topic")
mechanism = dbutils.widgets.get("sasl_mechanism")

TABLE = f"{catalog}.{schema}.spike_kafka_meter_readings"
CHECKPOINT = f"/Volumes/{catalog}/{schema}/checkpoints/_spike/kafka_consume"

bootstrap = dbutils.secrets.get(scope, "kafka-bootstrap-servers")
username = dbutils.secrets.get(scope, "kafka-sasl-username")
password = dbutils.secrets.get(scope, "kafka-sasl-password")
ca_pem = dbutils.secrets.get(scope, "kafka-ca-pem")
SECRETS = [bootstrap, username, password, ca_pem]


def redact(text: str) -> str:
    for secret in SECRETS:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


OPTIONS = {
    "kafka.bootstrap.servers": bootstrap,
    "subscribe": topic,
    "startingOffsets": "earliest",
    "failOnDataLoss": "true",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": mechanism,
    "kafka.sasl.jaas.config": (
        "kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule required "
        f'username="{username}" password="{password}";'
    ),
    "kafka.ssl.truststore.type": "PEM",
    "kafka.ssl.truststore.certificates": ca_pem,
    "kafka.request.timeout.ms": "30000",
    "kafka.default.api.timeout.ms": "60000",
    "fetchOffset.numRetries": "3",
}


def listing(path: str) -> list[tuple[str, int]]:
    result = []
    for f in dbutils.fs.ls(path):
        if f.isDir():
            result += listing(f.path)
        else:
            result.append((f.path, f.size))
    return sorted(result)


# COMMAND ----------

before_files, before_rows = listing(CHECKPOINT), spark.table(TABLE).count()
print(f"before: {len(before_files)} checkpoint files, {before_rows} rows")

reader = spark.readStream.format("kafka")
for key, value in OPTIONS.items():
    reader = reader.option(key, value)

started = time.time()
failed, error = False, ""
try:
    (
        reader.load()
        .select(
            F.col("key").cast("string").alias("kafka_key"),
            F.col("value").cast("string").alias("payload"),
            F.col("topic").alias("_topic"),
            F.col("partition").alias("_partition"),
            F.col("offset").alias("_offset"),
            F.col("timestamp").alias("_kafka_timestamp"),
            F.current_timestamp().alias("_ingested_at"),
        )
        .writeStream.option("checkpointLocation", CHECKPOINT)
        .trigger(availableNow=True)
        .toTable(TABLE)
        .awaitTermination()
    )
except Exception as exc:  # noqa: BLE001  (the failure is the expected outcome)
    failed, error = True, f"{type(exc).__name__}: {redact(str(exc)).splitlines()[0][:300]}"
elapsed = time.time() - started

after_files, after_rows = listing(CHECKPOINT), spark.table(TABLE).count()
print(f"query failed: {failed} after {elapsed:.0f} s; error: {error}")
checks = {
    "query failed (did not hang)": failed,
    "failed in under 600 s": elapsed < 600,
    "checkpoint unchanged": before_files == after_files,
    "row count unchanged": before_rows == after_rows,
}
for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
print("DA-05:", "PASS" if all(checks.values()) else "FAIL", f"(time to failure {elapsed:.0f} s)")

# COMMAND ----------

# Cleanup of the scratch objects of spikes 02 and 03 (run after power-on).
# spark.sql(f"DROP TABLE IF EXISTS {TABLE}"); dbutils.fs.rm(CHECKPOINT, True)
result = {"seconds": round(elapsed), "error": error, "checks": checks}
assert all(checks.values()), f"DA-05 failed: {result}; rely on the task timeout_seconds"
dbutils.notebook.exit(str(result))  # prints are not returned by the Jobs API
