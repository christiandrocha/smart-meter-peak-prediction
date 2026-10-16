# Databricks notebook source
# Spike 01 (A-02). STATUS: written, NOT RUN. Throwaway code, never imported by src/.
#
# Question: does Auto Loader ingest the sample CSVs from a Unity Catalog Volume on serverless
# with `availableNow`, using a read schema named after the source header
# (`LCLid`, `tstp`, `energy(kWh/hh)`), and does a second run ingest 0 rows?
#
# Pass criteria (ADR 0001, A-02)
#   1. Run 1 ingests every data row of the uploaded files (count equals a plain batch read).
#   2. `_rescued_data` is null for every row (the header names match the read schema).
#   3. Run 2, with no new files, adds 0 rows.
#   4. `_source_file` (from `_metadata.file_path`) and `_ingested_at` are non-null.
#
# Prerequisite (run by the user, after spike 00):
#   databricks fs cp data/sample/seed42/historical/readings_2012-07.csv \
#       dbfs:/Volumes/smart_meter_dev/bronze/landing/_spike/readings/
#   databricks fs cp data/sample/seed42/historical/readings_2012-08.csv \
#       dbfs:/Volumes/smart_meter_dev/bronze/landing/_spike/readings/
# (use the fallback catalog/schema in the widgets if spike 00 selected it)
#
# Cleans up after itself (scratch table and checkpoint).

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

dbutils.widgets.text("catalog", "smart_meter_dev")
dbutils.widgets.text("schema", "bronze")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")

LANDING = f"/Volumes/{catalog}/{schema}/landing/_spike/readings"
CHECKPOINT = f"/Volumes/{catalog}/{schema}/checkpoints/_spike/autoloader"
TABLE = f"{catalog}.{schema}.spike_files_meter_readings"

READ_SCHEMA = StructType(
    [
        StructField("LCLid", StringType()),
        StructField("tstp", StringType()),
        StructField("energy(kWh/hh)", StringType()),
    ]
)

# COMMAND ----------

spark.sql(f"DROP TABLE IF EXISTS {TABLE}")  # stale state from a crashed run
dbutils.fs.rm(CHECKPOINT, True)
expected = (
    spark.read.option("header", True).schema(READ_SCHEMA).csv(LANDING).count()
)
print("data rows in the uploaded files:", expected)


def ingest() -> None:
    stream = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", True)
        .option("rescuedDataColumn", "_rescued_data")
        .schema(READ_SCHEMA)
        .load(LANDING)
    )
    renamed = stream.select(
        F.col("LCLid").alias("household_id"),
        F.col("tstp").alias("reading_ts_raw"),
        F.col("`energy(kWh/hh)`").alias("energy_kwh_raw"),
        F.col("_rescued_data"),
        F.col("_metadata.file_path").alias("_source_file"),
        F.current_timestamp().alias("_ingested_at"),
    )
    (
        renamed.writeStream.option("checkpointLocation", CHECKPOINT)
        .trigger(availableNow=True)
        .toTable(TABLE)
        .awaitTermination()
    )


# COMMAND ----------

ingest()
after_first = spark.table(TABLE).count()
ingest()
after_second = spark.table(TABLE).count()
t = spark.table(TABLE)
rescued = t.where("_rescued_data IS NOT NULL").count()
null_meta = t.where("_source_file IS NULL OR _ingested_at IS NULL").count()
print(f"run 1: {after_first}  run 2: {after_second}  rescued: {rescued}  null metadata: {null_meta}")

checks = {
    "run 1 ingests every row": after_first == expected,
    "_rescued_data null": rescued == 0,
    "run 2 adds 0 rows": after_second == after_first,
    "metadata non-null": null_meta == 0,
}
for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
print("A-02:", "PASS" if all(checks.values()) else "FAIL")

# COMMAND ----------

spark.sql(f"DROP TABLE IF EXISTS {TABLE}")
dbutils.fs.rm(CHECKPOINT, True)
result = {"expected": expected, "run1": after_first, "run2": after_second, "rescued": rescued,
          "null_metadata": null_meta, "checks": checks}
assert all(checks.values()), f"A-02 failed: {result}; use the ADR 0001 fallback"
dbutils.notebook.exit(str(result))  # prints are not returned by the Jobs API
