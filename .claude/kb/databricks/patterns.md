# Databricks patterns

## Unity Catalog layout

```text
<catalog>                     one per environment when the platform allows, else one shared
├── bronze | silver | gold    schemas per layer (or per domain, decided by ADR)
├── ml                        feature tables, prediction tables, registered models
└── landing (Volume)          raw files; checkpoints in a separate Volume
```

Files live in Volumes: `/Volumes/<catalog>/<schema>/<volume>/<path>`.

## Auto Loader (incremental files to Bronze)

```python
(
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "csv")
    .option("header", "true")
    .option("rescuedDataColumn", "_rescued_data")
    .schema(explicit_schema)  # explicit for Bronze; or cloudFiles.schemaLocation
    .load("/Volumes/cat/sch/landing/source")
    .withColumn("_source_file", F.col("_metadata.file_path"))
    .withColumn("_ingested_at", F.current_timestamp())
    .writeStream.option("checkpointLocation", "/Volumes/cat/sch/checkpoints/source")
    .trigger(availableNow=True)
    .toTable("cat.bronze.files_source")
)
```

- Column names with spaces or parentheses are invalid in Delta by default: read with
  positional names or rename before writing.
- Re-running with no new files ingests nothing: the checkpoint tracks processed files.

## Lakeflow Declarative Pipelines (Python)

```python
import dlt  # newer runtimes also expose `from pyspark import pipelines as dp`


@dlt.table(comment="Typed, deduplicated readings")
@dlt.expect_or_drop("valid_ts", "reading_ts IS NOT NULL")
@dlt.expect("non_negative", "energy_kwh >= 0")  # warn: keep row, record metric
@dlt.expect_or_fail("known_household", "household_id IS NOT NULL")
def meter_readings():
    return dlt.read_stream("bronze_readings").select(...)
```

Actions: `expect` (warn), `expect_or_drop` (drop), `expect_or_fail` (fail the update).
Use `dlt.create_auto_cdc_flow` (formerly `apply_changes`) for CDC and SCD Type 1/2.

## MERGE for idempotent upserts

```python
from delta.tables import DeltaTable


def upsert(batch_df, batch_id):
    (
        DeltaTable.forName(spark, "cat.silver.meter_readings")
        .alias("t")
        .merge(
            batch_df.dropDuplicates(["household_id", "reading_ts"]).alias("s"),
            "t.household_id = s.household_id AND t.reading_ts = s.reading_ts",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


stream.writeStream.foreachBatch(upsert).option("checkpointLocation", cp).trigger(
    availableNow=True
).start()
```

Deduplicate inside the batch before MERGE; duplicate source keys make MERGE fail.

## Table design

- Liquid Clustering: `CLUSTER BY (household_id, reading_date)` on columns used in filters and
  joins. Change keys later with `ALTER TABLE ... CLUSTER BY`.
- Partition only very large tables with a low-cardinality column and a reason in an ADR.
- Keep event time (`*_ts`) and ingestion time (`_ingested_at`) as separate columns.
- Time travel (`VERSION AS OF`) lets a training run be reproduced; record the version used.

## Testing

- Unit tests: transformation functions over small in-memory DataFrames.
- Reconciliation tests: row counts per layer against a manifest or source count.
- Integration tests (marked): run the job in a dev target and assert on table contents.

Sources: https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/ ,
https://docs.databricks.com/aws/en/dlt/ , https://docs.databricks.com/aws/en/delta/clustering
