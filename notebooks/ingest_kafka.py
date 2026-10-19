# Databricks notebook source
# Kafka `availableNow` into the append-only Bronze table (FR-05, AC-07, AC-08, AC-10, AC-29).
#
# Credentials are read from the secret scope with dbutils.secrets.get and passed to the library.
# The options are never printed or logged (ADR 0002). There is deliberately no try/except around the
# stream (I-14, spike 03): a broker outage fails the task; the bounded Kafka timeouts, the task
# timeout (840 s) and `max_retries: 0` of the job make it fail within 15 minutes, and the next daily
# run is the retry. The checkpoint and the Bronze table stay unchanged on failure.

# COMMAND ----------

import os
import sys

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import bronze  # noqa: E402
from smart_meter_peak_prediction.config import BRONZE_KAFKA_READINGS, Settings  # noqa: E402

# COMMAND ----------

_defaults = Settings()
_widget_names = (
    "catalog",
    "bronze_schema",
    "kafka_topic",
    "kafka_sasl_mechanism",
    "secret_scope",
)
for _name in _widget_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _widget_names})

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

kafka_options = bronze.kafka_options(
    settings,
    bootstrap_servers=dbutils.secrets.get(settings.secret_scope, "kafka-bootstrap-servers"),
    sasl_username=dbutils.secrets.get(settings.secret_scope, "kafka-sasl-username"),
    sasl_password=dbutils.secrets.get(settings.secret_scope, "kafka-sasl-password"),
    ca_pem=dbutils.secrets.get(settings.secret_scope, "kafka-ca-pem"),
)

# COMMAND ----------

bronze.run_available_now(
    bronze.project_kafka(bronze.kafka_reader(spark, kafka_options)),
    settings.bronze_kafka_readings,
    settings.checkpoint(BRONZE_KAFKA_READINGS),
)

# COMMAND ----------

_table = settings.bronze_kafka_readings
print(f"{_table}: {spark.table(_table).count()} rows")
