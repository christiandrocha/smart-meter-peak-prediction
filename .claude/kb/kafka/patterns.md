# Kafka patterns

## Delivery semantics

- Producer with `enable.idempotence=true` and `acks=all` avoids duplicates from retries.
- End to end, assume **at-least-once**: a consumer restart can reprocess a batch. Deduplicate
  downstream on a business key (`entity_id`, `event_ts`).
- Order is guaranteed only within a partition. The message key chooses the partition, so key
  by the entity whose events must stay ordered.

## Message design

```json
{"entity_id": "...", "event_ts": "2013-12-01T00:30:00Z", "value": 0.42,
 "source": "replay", "produced_at": "2026-10-08T12:00:00Z"}
```

- `event_ts` is when it happened (UTC, ISO-8601). `produced_at` is only the ingestion clock.
- Keep values nullable instead of dropping malformed records at the producer; the pipeline
  decides and counts.
- Schema evolution: additive fields only; breaking changes create a new topic or version.

## Python producer (confluent-kafka)

```python
from confluent_kafka import Producer

producer = Producer(
    {
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": os.environ.get("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256"),
        "sasl.username": os.environ["KAFKA_USERNAME"],
        "sasl.password": os.environ["KAFKA_PASSWORD"],
        "ssl.ca.location": os.environ["KAFKA_CA_PATH"],
        "enable.idempotence": True,
        "acks": "all",
    }
)
producer.produce(topic, key=entity_id, value=json.dumps(event), on_delivery=callback)
producer.poll(0)
...
producer.flush()
```

## Spark Structured Streaming consumer (Databricks)

Databricks ships a shaded Kafka client: login module classes take the `kafkashaded.` prefix.

```python
jaas = (
    "kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule required "
    f'username="{user}" password="{password}";'
)
raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", bootstrap)
    .option("kafka.security.protocol", "SASL_SSL")
    .option("kafka.sasl.mechanism", "SCRAM-SHA-256")
    .option("kafka.sasl.jaas.config", jaas)
    .option("kafka.ssl.truststore.type", "PEM")  # CA passed inline as PEM text
    .option("kafka.ssl.truststore.certificates", ca_pem)
    .option("subscribe", topic)
    .option("startingOffsets", "earliest")
    .load()
)

bronze = raw.select(
    F.col("key").cast("string").alias("kafka_key"),
    F.col("value").cast("string").alias("payload"),
    "topic",
    "partition",
    "offset",
    F.col("timestamp").alias("kafka_timestamp"),
    F.current_timestamp().alias("_ingested_at"),
)
```

- Inline PEM truststores need a recent Kafka client; if rejected, store the CA in a Volume and
  use `kafka.ssl.truststore.location`.
- `failOnDataLoss=false` only when Bronze, not Kafka, is the reprocessing source and the
  retention gap is accepted in an ADR.

## Watermarks and late data

Use `withWatermark("event_ts", "<delay>")` before stateful aggregations or stream
deduplication so state does not grow without bound. Choose the delay from observed lateness.

Sources: https://spark.apache.org/docs/latest/structured-streaming-kafka-integration.html ,
https://docs.databricks.com/aws/en/connect/streaming/kafka
