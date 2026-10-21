# Databricks notebook source
# Training and registration (FR-23 to FR-27, AC-48 to AC-55; ADR 0007, ADR 0009).
#
# On demand only (D-36). Reads the labels table at version VL and the feature table at version VF,
# builds the point-in-time training set (`fe.create_training_set`), trains one deterministic
# HistGradientBoostingClassifier, picks t, evaluates, logs the run, registers the model with
# `fe.log_model`, tags the threshold, checks the reload (G-08) and then moves alias `champion`.
# Guards G-02 to G-05 and G-11 run in `training.run_training` before any run starts.
# No try/except (I-14): a failure stops the task and `champion` stays where it was.

# COMMAND ----------

# MAGIC %pip install --quiet databricks-feature-engineering==0.18.2 scikit-learn==1.3.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

import mlflow  # noqa: E402
from databricks.feature_engineering import FeatureEngineeringClient  # noqa: E402
from mlflow import MlflowClient  # noqa: E402

from smart_meter_peak_prediction import peak_config, registry, training  # noqa: E402
from smart_meter_peak_prediction.config import Settings  # noqa: E402
from smart_meter_peak_prediction.model import FEATURE_COLUMNS  # noqa: E402
from smart_meter_peak_prediction.peak_config import PeakParameters  # noqa: E402

# G-01: the pinned library versions are the ones installed.
peak_config.check_versions()

# COMMAND ----------

_defaults = Settings()
_settings_names = ("catalog", "ml_schema")
_parameter_names = (
    "train_start",
    "train_end",
    "validation_start",
    "validation_end",
    "test_start",
    "test_end",
    "random_seed",
)
_widget_names = (
    "catalog",
    "ml_schema",
    "experiment_path",
    "git_commit",
    "train_start",
    "train_end",
    "validation_start",
    "validation_end",
    "test_start",
    "test_end",
    "random_seed",
)
_parameter_defaults = PeakParameters()
for _name in _settings_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
for _name in _parameter_names:
    dbutils.widgets.text(_name, str(getattr(_parameter_defaults, _name)))
dbutils.widgets.text("experiment_path", "")
dbutils.widgets.text("git_commit", "")
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _settings_names})
params = PeakParameters.from_mapping({name: dbutils.widgets.get(name) for name in _parameter_names})
git_commit = dbutils.widgets.get("git_commit")
training.check_git_commit(git_commit)  # G-05 before any read (run_training checks it again)
print("training parameters:", params.training_parameters())

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(dbutils.widgets.get("experiment_path") or peak_config.experiment_path(user))
fe = FeatureEngineeringClient()

features_table = peak_config.features_table(settings)
labels_table = peak_config.labels_table(settings)
model_name = peak_config.model_name(settings)

# COMMAND ----------

# Labels at version VL: eligible, labelled, inside the three split ranges.
labels_version = registry.table_version(spark, labels_table)
# Table names come from validated Settings, versions from Delta history.
labels_sql = f"SELECT * FROM {labels_table} VERSION AS OF {labels_version}"  # noqa: S608
labels_pdf = spark.sql(labels_sql).toPandas()
rows = training.select_training_rows(labels_pdf, params)

# Point-in-time training set; G-04 stops the run when the feature table changes underneath it.
training_set, frame, features_version = registry.build_training_set(
    fe, spark, rows, features_table, FEATURE_COLUMNS
)
keys_sql = (
    "SELECT household_id, feature_date "  # noqa: S608
    f"FROM {features_table} VERSION AS OF {features_version}"
)
feature_keys = spark.sql(keys_sql).toPandas()

label_properties = registry.table_properties(spark, labels_table)
feature_properties = registry.table_properties(spark, features_table)
# The properties are read from the current tables: stop if a build changed them meanwhile.
if registry.table_version(spark, labels_table) != labels_version:
    raise training.GuardError(f"{labels_table} changed after version {labels_version} was read")
if registry.table_version(spark, features_table) != features_version:
    raise training.GuardError(f"{features_table} changed after version {features_version}")

inputs = training.TrainingInputs(
    frame=frame,
    feature_keys=feature_keys,
    features_table=training.TableRef(features_table, features_version),
    labels_table=training.TableRef(labels_table, labels_version),
    label_properties=label_properties,
    feature_properties=feature_properties,
    git_commit=git_commit,
    library_versions=registry.library_versions(),
)
tracker = registry.MlflowTracker(
    mlflow=mlflow,
    client=MlflowClient(),
    fe=fe,
    training_set=training_set,
    model_name=model_name,
)
result = training.run_training(inputs, params, tracker)

# COMMAND ----------

summary = {
    "run_id": result.run_id,
    "model": model_name,
    "model_version": result.model_version,
    "decision_threshold": result.threshold.threshold,
    "validation_f1_at_t": result.threshold.f1,
    "labels_table_version": labels_version,
    "features_table_version": features_version,
    "git_commit": git_commit,
    "training_rows": int(len(frame)),
}
print(summary)
dbutils.notebook.exit(json.dumps(summary))
