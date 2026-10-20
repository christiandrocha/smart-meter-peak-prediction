# Databricks notebook source
# Spike 02 (A-03, A-05, DA-09; A-06 is read from the Aiven console). STATUS: written, NOT RUN.
# Throwaway code, never imported by src/.
#
# Questions
#   DA-09 Are Databricks secret scopes available and readable from serverless?
#   A-03  Does the Spark Kafka source authenticate with SASL_SSL, SCRAM and an inline PEM CA?
#   A-05  Does `availableNow` complete and stop, and is a `processingTime` trigger rejected?
#   A-06  Which SASL mechanism does Aiven list for the service user? (console; write it in ADR 0001)
#
# Pass criteria (ADR 0001)
#   - the four secrets are readable (values are never printed);
#   - an `availableNow` read of the topic returns the produced messages (count > 0) and stops;
#   - the Bronze-shaped projection has `_topic`, `_partition`, `_offset`, `_kafka_timestamp`
#     and `_ingested_at`, with no nulls.
#   - A-05 is informational: the notebook prints whether `processingTime` was rejected.
#
# Prerequisites (run by the user)
#   1. Secret scope and keys (values come from the Aiven console / local .env; never paste them
#      into a file or command history shared with others):
#        databricks secrets create-scope smart_meter
#        databricks secrets put-secret smart_meter kafka-bootstrap-servers
#        databricks secrets put-secret smart_meter kafka-sasl-username
#        databricks secrets put-secret smart_meter kafka-sasl-password
#        databricks secrets put-secret smart_meter kafka-ca-pem --string-value "$(cat /path/ca.pem)"
#   2. Aiven service powered on and some messages on the topic, for example:
#        python -m smart_meter_peak_prediction.producer --limit 1000 \
#            --input data/sample/seed42/stream/readings_stream.csv   # credentials from .env
#      or the Docker command in docker/producer/Dockerfile.
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

# COMMAND ----------

# DA-09: read the secrets (redacted by Databricks if displayed; we never display them).
try:
    bootstrap = dbutils.secrets.get(scope, "kafka-bootstrap-servers")
    username = dbutils.secrets.get(scope, "kafka-sasl-username")
    password = dbutils.secrets.get(scope, "kafka-sasl-password")
    ca_pem = dbutils.secrets.get(scope, "kafka-ca-pem")
    print("DA-09 PASS: four secrets readable")
except Exception as exc:  # noqa: BLE001
    raise AssertionError(f"DA-09 FAIL: {type(exc).__name__}") from None

SECRETS = [bootstrap, username, password, ca_pem]


def redact(text: str) -> str:
    for secret in SECRETS:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


JAAS = (
    "kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule required "
    f'username="{username}" password="{password}";'
)
OPTIONS = {
    "kafka.bootstrap.servers": bootstrap,
    "subscribe": topic,
    "startingOffsets": "earliest",
    "failOnDataLoss": "true",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": mechanism,
    "kafka.sasl.jaas.config": JAAS,
    "kafka.ssl.truststore.type": "PEM",
    "kafka.ssl.truststore.certificates": ca_pem,
    "kafka.request.timeout.ms": "30000",
    "kafka.default.api.timeout.ms": "60000",
    "fetchOffset.numRetries": "3",
}


def kafka_stream():
    reader = spark.readStream.format("kafka")
    for key, value in OPTIONS.items():
        reader = reader.option(key, value)
    return reader.load()


def bronze_projection(raw):
    return raw.select(
        F.col("key").cast("string").alias("kafka_key"),
        F.col("value").cast("string").alias("payload"),
        F.col("topic").alias("_topic"),
        F.col("partition").alias("_partition"),
        F.col("offset").alias("_offset"),
        F.col("timestamp").alias("_kafka_timestamp"),
        F.current_timestamp().alias("_ingested_at"),
    )


# COMMAND ----------

# A-03 and A-05: availableNow read into a scratch table.
started = time.time()
try:
    query = (
        bronze_projection(kafka_stream())
        .writeStream.option("checkpointLocation", CHECKPOINT)
        .trigger(availableNow=True)
        .toTable(TABLE)
    )
    query.awaitTermination()
except Exception as exc:  # noqa: BLE001
    print("A-03 FAIL:", type(exc).__name__, redact(str(exc))[:600])
    raise AssertionError("A-03 failed; see ADR 0001 fallback (CA file in a Volume)") from None
elapsed = time.time() - started

t = spark.table(TABLE)
rows = t.count()
null_cols = t.where(
    "_topic IS NULL OR _partition IS NULL OR _offset IS NULL OR _kafka_timestamp IS NULL "
    "OR _ingested_at IS NULL OR payload IS NULL OR kafka_key IS NULL"
).count()
dup_offsets = rows - t.select("_topic", "_partition", "_offset").distinct().count()
print(f"rows={rows} null_metadata={null_cols} duplicate_offsets={dup_offsets} seconds={elapsed:.0f}")
print("  sample payload shape:", [r.payload[:60] for r in t.limit(1).collect()])
ok = rows > 0 and null_cols == 0 and dup_offsets == 0 and not query.isActive
print("A-03 / A-05 availableNow:", "PASS" if ok else "FAIL")

# COMMAND ----------

# A-05 (informational): is a processingTime trigger rejected on serverless?
try:
    q = (
        kafka_stream()
        .writeStream.format("noop")
        .trigger(processingTime="10 seconds")
        .start()
    )
    time.sleep(20)
    q.stop()
    a05 = "accepted"
    print("A-05 processingTime: ACCEPTED (not used by the design; record it)")
except Exception as exc:  # noqa: BLE001
    a05 = "rejected: " + redact(str(exc)).splitlines()[0][:200]
    print("A-05 processingTime: REJECTED ->", type(exc).__name__, redact(str(exc)).splitlines()[0][:200])

# COMMAND ----------

# Keep the scratch table and checkpoint: spike 03 reuses them to show the checkpoint is unchanged.
# Remove both after spike 03:  DROP TABLE <TABLE>;  dbutils.fs.rm(CHECKPOINT, True)
result = {"rows": rows, "null_metadata": null_cols, "duplicate_offsets": dup_offsets,
          "seconds": round(elapsed), "a05_processing_time": a05}
assert ok, f"A-03 / A-05 failed: {result}; see ADR 0001"
dbutils.notebook.exit(str(result))  # prints are not returned by the Jobs API
