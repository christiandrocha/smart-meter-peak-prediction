# Databricks notebook source
# Spike 05 (A-04, A-12, A-16; informs OD-08). STATUS: written, NOT RUN.
# Throwaway code, never imported by src/. Run it through 05_spike_mlflow_uc_submit.py, which
# submits it as a one-time serverless job with two notebook tasks (mode=main, then mode=retrain),
# the same task type the PEAK_MODEL job will use.
#
# Questions (ADR 0007)
#   A-04  MLflow registers a model with a signature in UC, sets alias `champion`, and the model
#         loads by `models:/<name>@champion` and scores.
#   A-12  Feature Engineering in UC on serverless: the client installs in the task environment;
#         `create_table` with `timeseries_columns`; `create_training_set` with
#         `timestamp_lookup_key`; `fe.log_model`; `fe.score_batch`; feature lineage on the model.
#   A-16  HistGradientBoostingClassifier with a fixed seed and early_stopping=False gives bitwise
#         identical scores: twice in one process (mode=main) and in a second task (mode=retrain).
#   OD-08 (informational) a model version tag can hold the threshold t and is read back.
#
# Pass criteria
#   A-04: version registered, alias set, load by alias reproduces local scores (max diff <= 1e-12).
#   A-12: every listed call succeeds; the training set equals an explicit join on
#         feature_date = target_date - 1 (0 mismatches); score_batch through @champion
#         reproduces local scores; the logged model carries a feature spec naming the feature
#         table. UC lineage (model downstream of the table) is checked by the submit script.
#   A-16: identical scores in both comparisons.
#
# Data is synthetic and deterministic (20 households x 150 days); nothing reads the project
# tables. Objects are prefixed with `prefix` and removed by the submit script.

# COMMAND ----------

# MAGIC %pip install --quiet databricks-feature-engineering scikit-learn

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import inspect
import json
import os
import platform
import tempfile
import traceback
from datetime import timedelta
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import sklearn
from mlflow import MlflowClient
from mlflow.models import infer_signature
from pyspark.sql import functions as F
from sklearn.ensemble import HistGradientBoostingClassifier

dbutils.widgets.text("catalog", "smart_meter_dev")
dbutils.widgets.text("schema", "ml")
dbutils.widgets.text("prefix", "spike_05")
dbutils.widgets.dropdown("mode", "main", ["main", "retrain"])
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
prefix, mode = dbutils.widgets.get("prefix"), dbutils.widgets.get("mode")

FEATURES = f"{catalog}.{schema}.{prefix}_features"
LABELS = f"{catalog}.{schema}.{prefix}_labels"
SCORES = f"{catalog}.{schema}.{prefix}_scores"
MODEL_FE = f"{catalog}.{schema}.{prefix}_model_fe"
MODEL_PLAIN = f"{catalog}.{schema}.{prefix}_model_plain"
FEATURE_COLS = ["total_energy_kwh_1d", "avg_energy_kwh_7d", "mean_temperature_c_1d"]
KEYS = ["household_id", "target_date"]
SPLIT_DATE = pd.Timestamp("2013-04-15")
SEED = 42

mlflow.set_registry_uri("databricks-uc")
user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/spikes/{prefix}")
client = MlflowClient()

results: dict = {"mode": mode, "checks": {}, "info": {}, "errors": {}}


def record(key: str, ok: bool, detail) -> None:
    results["checks"][key] = {"pass": bool(ok), "detail": detail}
    print(f"{'PASS' if ok else 'FAIL'}  {key}: {detail}")


def error(key: str, exc: BaseException) -> None:
    results["errors"][key] = f"{type(exc).__name__}: {str(exc)[:500]}"
    print(f"ERROR {key}:", results["errors"][key])
    traceback.print_exc()


try:
    from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup
    from databricks.feature_engineering import __version__ as fe_version

    fe = FeatureEngineeringClient()
    fe_ok = True
except Exception as exc:  # noqa: BLE001
    fe_ok, fe_version = False, None
    error("A-12 import", exc)

results["info"]["versions"] = {
    "python": platform.python_version(),
    "mlflow": mlflow.__version__,
    "scikit_learn": sklearn.__version__,
    "databricks_feature_engineering": fe_version,
    "cpu_count": os.cpu_count(),
    "spark_session_time_zone": spark.conf.get("spark.sql.session.timeZone"),
}
print(results["info"]["versions"])
record("A-12 client installs in the task environment", fe_ok, f"version {fe_version}")

# COMMAND ----------

# Synthetic, deterministic data: dense features per (household, feature_date), labels per
# (household, target_date) with lookup_date = target_date - 1, as FR-20, FR-21 and FR-23 shape them.


def synthetic() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range("2013-01-01", periods=150, freq="D")
    rows = []
    for n in range(1, 21):
        base = rng.uniform(5, 15)
        day = np.arange(len(dates))
        total = base * (1 + 0.3 * np.sin(2 * np.pi * day / 7)) * rng.gamma(8, 1 / 8, len(dates))
        temp = 6 + 6 * np.sin(2 * np.pi * (day - 60) / 365) + rng.normal(0, 2, len(dates))
        rows.append(
            pd.DataFrame(
                {"household_id": f"MAC{n:06d}", "feature_date": dates, "total": total, "temp": temp}
            )
        )
    df = pd.concat(rows, ignore_index=True)
    df["avg7"] = df.groupby("household_id")["total"].transform(lambda s: s.rolling(7).mean())
    feats = df.rename(
        columns={
            "total": "total_energy_kwh_1d",
            "avg7": "avg_energy_kwh_7d",
            "temp": "mean_temperature_c_1d",
        }
    )
    nxt = df.groupby("household_id")["total"].shift(-1)
    labels = df.assign(
        target_date=df["feature_date"] + pd.Timedelta(days=1),
        lookup_date=df["feature_date"],
        label=(nxt > 1.3 * df["avg7"]).astype(int),
    )
    labels = labels[df["avg7"].notna() & nxt.notna()][KEYS + ["lookup_date", "label"]]
    feats["feature_date"] = feats["feature_date"].dt.date
    labels["target_date"] = labels["target_date"].dt.date
    labels["lookup_date"] = labels["lookup_date"].dt.date
    return feats[["household_id", "feature_date"] + FEATURE_COLS], labels.reset_index(drop=True)


def fit_and_score(train: pd.DataFrame, test: pd.DataFrame):
    clf = HistGradientBoostingClassifier(random_state=SEED, early_stopping=False, max_iter=100)
    clf.fit(train[FEATURE_COLS], train["label"])
    return clf, clf.predict_proba(test[FEATURE_COLS])[:, 1]


class ProbaModel(mlflow.pyfunc.PythonModel):
    """Returns the positive-class probability, as `score` needs (FR-29)."""

    def __init__(self, clf):
        self.clf = clf

    def predict(self, context, model_input, params=None):
        return self.clf.predict_proba(model_input[FEATURE_COLS])[:, 1]


def training_frame(labels_sdf):
    """A-12: point-in-time training set through Feature Engineering."""
    ts = fe.create_training_set(
        df=labels_sdf,
        feature_lookups=[
            FeatureLookup(
                table_name=FEATURES,
                lookup_key="household_id",
                timestamp_lookup_key="lookup_date",
                feature_names=FEATURE_COLS,
            )
        ],
        label="label",
        exclude_columns=["lookup_date"],
    )
    pdf = ts.load_df().toPandas().sort_values(KEYS).reset_index(drop=True)
    pdf["target_date"] = pd.to_datetime(pdf["target_date"])
    return ts, pdf


# COMMAND ----------

if mode == "main":
    feats, labels = synthetic()
    results["info"]["data"] = {
        "feature_rows": len(feats),
        "label_rows": len(labels),
        "positive_share": round(float(labels["label"].mean()), 4),
    }
    print(results["info"]["data"])
    feats_sdf = spark.createDataFrame(feats)
    labels_sdf = spark.createDataFrame(labels)
    labels_sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(LABELS)

    # A-12: feature table with a time-series column.
    try:
        spark.sql(f"DROP TABLE IF EXISTS {FEATURES}")
        fe.create_table(
            name=FEATURES,
            primary_keys=["household_id", "feature_date"],
            timeseries_columns="feature_date",
            df=feats_sdf,
            description="Spike 05 synthetic features; dropped after the spike",
        )
        record("A-12 create_table with timeseries_columns", True, FEATURES)
    except Exception as exc:  # noqa: BLE001
        error("A-12 create_table", exc)
        record(
            "A-12 create_table with timeseries_columns",
            False,
            results["errors"]["A-12 create_table"],
        )

# COMMAND ----------

# A-12: training set and point-in-time semantics.
labels_sdf = spark.table(LABELS)
training_set, train_df = None, None
try:
    training_set, train_df = training_frame(labels_sdf)
    explicit = (
        spark.table(LABELS)
        .join(
            spark.table(FEATURES).withColumnRenamed("feature_date", "lookup_date"),
            ["household_id", "lookup_date"],
            "left",
        )
        .drop("lookup_date")
        .toPandas()
        .sort_values(KEYS)
        .reset_index(drop=True)
    )
    explicit["target_date"] = pd.to_datetime(explicit["target_date"])
    same_rows = len(explicit) == len(train_df)
    diff = (
        (explicit[FEATURE_COLS].to_numpy() != train_df[FEATURE_COLS].to_numpy()).any(axis=1).sum()
        if same_rows
        else -1
    )
    record(
        "A-12 create_training_set with timestamp_lookup_key",
        same_rows and diff == 0,
        f"{len(train_df)} rows; {diff} rows differ from the explicit join "
        "on feature_date = target_date - 1",
    )
except Exception as exc:  # noqa: BLE001
    error("A-12 create_training_set", exc)
    record(
        "A-12 create_training_set with timestamp_lookup_key",
        False,
        results["errors"]["A-12 create_training_set"],
    )

if mode == "main" and training_set is not None:
    # As-of semantics (informational, why FR-20 keeps the table dense): a lookup after the last
    # feature date returns the last row; a lookup before the first feature date returns nulls.
    try:
        bounds = spark.table(FEATURES).agg(F.min("feature_date"), F.max("feature_date")).first()
        probe = spark.createDataFrame(
            pd.DataFrame(
                {
                    "household_id": ["MAC000001", "MAC000001"],
                    "target_date": [bounds[1] + timedelta(days=6), bounds[0]],
                    "lookup_date": [bounds[1] + timedelta(days=5), bounds[0] - timedelta(days=1)],
                }
            )
        )
        got = (
            fe.create_training_set(
                df=probe,
                feature_lookups=[
                    FeatureLookup(
                        table_name=FEATURES,
                        lookup_key="household_id",
                        timestamp_lookup_key="lookup_date",
                        feature_names=FEATURE_COLS,
                    )
                ],
                label=None,
            )
            .load_df()
            .orderBy("lookup_date", ascending=False)
            .toPandas()
        )
        last = (
            spark.table(FEATURES)
            .where(f"household_id = 'MAC000001' AND feature_date = '{bounds[1]}'")
            .toPandas()
        )
        after_last = np.array_equal(
            got.loc[0, FEATURE_COLS].to_numpy(float), last.loc[0, FEATURE_COLS].to_numpy(float)
        )
        before_first = bool(got.loc[1, FEATURE_COLS].isna().all())
        results["info"]["as_of_semantics"] = {
            "lookup_after_last_returns_last_row": after_last,
            "lookup_before_first_returns_nulls": before_first,
        }
        print("as-of semantics:", results["info"]["as_of_semantics"])
    except Exception as exc:  # noqa: BLE001
        error("as-of probe", exc)

# COMMAND ----------

# A-16: fit, score, compare.
scores = None
if train_df is not None:
    train = train_df[train_df["target_date"] < SPLIT_DATE]
    test = train_df[train_df["target_date"] >= SPLIT_DATE].reset_index(drop=True)
    clf, scores = fit_and_score(train, test)
    if mode == "main":
        _, again = fit_and_score(train, test)
        record(
            "A-16 same process",
            np.array_equal(scores, again),
            f"{len(scores)} scores; max abs diff {float(np.max(np.abs(scores - again))):.3e}",
        )
        spark.createDataFrame(test[KEYS].assign(score=scores)).write.mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(SCORES)
    else:
        prev = spark.table(SCORES).toPandas().sort_values(KEYS).reset_index(drop=True)
        prev["target_date"] = pd.to_datetime(prev["target_date"])
        keys_equal = prev[KEYS].equals(test[KEYS])
        diff = float(np.max(np.abs(prev["score"].to_numpy() - scores))) if keys_equal else None
        record(
            "A-16 second task",
            keys_equal and np.array_equal(prev["score"].to_numpy(), scores),
            f"{len(scores)} scores; same keys {keys_equal}; max abs diff {diff}",
        )

# COMMAND ----------


def log_fe_model(model, flavor, signature):
    """fe.log_model with the keywords this client version accepts; returns (kwargs, error)."""
    params = inspect.signature(fe.log_model).parameters
    base = {
        "model": model,
        "flavor": flavor,
        "training_set": training_set,
        "registered_model_name": MODEL_FE,
    }
    base["name" if "name" in params and "artifact_path" not in params else "artifact_path"] = (
        "model"
    )
    attempts = [dict(base, signature=signature), dict(base, infer_input_example=True), base]
    last_exc = None
    for kwargs in attempts:
        try:
            fe.log_model(**kwargs)
            return [k for k in kwargs if k not in ("model", "flavor", "training_set")], None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    return None, last_exc


def latest_version(name: str) -> int:
    return max(int(v.version) for v in client.search_model_versions(f"name = '{name}'"))


if mode == "main" and scores is not None:
    X_test = test[FEATURE_COLS]
    signature = infer_signature(X_test, scores)

    # A-04: plain MLflow model in UC (also the D-32 fallback path, variant 1B).
    try:
        with mlflow.start_run(run_name=f"{prefix}_plain"):
            mlflow.log_params(
                {
                    "model": "HistGradientBoostingClassifier",
                    "random_state": SEED,
                    "early_stopping": False,
                }
            )
            mlflow.pyfunc.log_model(
                "model",
                python_model=ProbaModel(clf),
                signature=signature,
                registered_model_name=MODEL_PLAIN,
            )
        v_plain = latest_version(MODEL_PLAIN)
        client.set_registered_model_alias(MODEL_PLAIN, "champion", v_plain)
        alias_v = int(client.get_model_version_by_alias(MODEL_PLAIN, "champion").version)
        loaded = mlflow.pyfunc.load_model(f"models:/{MODEL_PLAIN}@champion")
        pred = np.asarray(loaded.predict(X_test), dtype=float)
        diff = float(np.max(np.abs(pred - scores)))
        has_sig = loaded.metadata.signature is not None
        record(
            "A-04 register, alias, load by alias",
            alias_v == v_plain and has_sig and diff <= 1e-12,
            f"version {v_plain}; alias -> {alias_v}; signature {has_sig}; max abs diff {diff:.3e}",
        )
        # OD-08 (informational): threshold as a version tag.
        client.set_model_version_tag(MODEL_PLAIN, str(v_plain), "decision_threshold", "0.4321")
        tag = client.get_model_version(MODEL_PLAIN, str(v_plain)).tags.get("decision_threshold")
        results["info"]["od08_version_tag_round_trip"] = tag == "0.4321"
    except Exception as exc:  # noqa: BLE001
        error("A-04", exc)
        record("A-04 register, alias, load by alias", False, results["errors"]["A-04"])

    # A-12: fe.log_model with a probability pyfunc, alias, score_batch, feature spec.
    if training_set is not None:
        with mlflow.start_run(run_name=f"{prefix}_fe"):
            used, exc = log_fe_model(ProbaModel(clf), mlflow.pyfunc, signature)
        results["info"]["fe_log_model_pyfunc_kwargs"] = used
        if exc is not None:
            error("A-12 fe.log_model pyfunc", exc)
            with mlflow.start_run(run_name=f"{prefix}_fe_sklearn"):
                used, exc2 = log_fe_model(
                    clf, mlflow.sklearn, infer_signature(X_test, clf.predict(X_test))
                )
            results["info"]["fe_log_model_sklearn_kwargs"] = used
            if exc2 is not None:
                error("A-12 fe.log_model sklearn", exc2)
        record(
            "A-12 fe.log_model (probability pyfunc)",
            exc is None,
            f"kwargs {used}" if exc is None else results["errors"].get("A-12 fe.log_model pyfunc"),
        )
        try:
            v_fe = latest_version(MODEL_FE)
            client.set_registered_model_alias(MODEL_FE, "champion", v_fe)
            batch = spark.createDataFrame(
                test[KEYS].assign(
                    lookup_date=(test["target_date"] - pd.Timedelta(days=1)).dt.date,
                    target_date=test["target_date"].dt.date,
                )
            )
            out = (
                fe.score_batch(
                    model_uri=f"models:/{MODEL_FE}@champion", df=batch, result_type="double"
                )
                .toPandas()
                .sort_values(KEYS)
                .reset_index(drop=True)
            )
            diff = float(np.max(np.abs(out["prediction"].to_numpy(float) - scores)))
            record(
                "A-12 fe.score_batch by alias",
                exc is None and len(out) == len(scores) and diff <= 1e-12,
                f"version {v_fe}; {len(out)} rows; max abs diff to local probabilities {diff:.3e}",
            )
        except Exception as exc3:  # noqa: BLE001
            error("A-12 fe.score_batch", exc3)
            record("A-12 fe.score_batch by alias", False, results["errors"]["A-12 fe.score_batch"])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                local = mlflow.artifacts.download_artifacts(
                    f"models:/{MODEL_FE}/{v_fe}", dst_path=tmp
                )
                specs = list(Path(local).rglob("feature_spec.yaml"))
                text = specs[0].read_text() if specs else ""
            record(
                "A-12 feature spec on the model",
                FEATURES in text,
                f"feature_spec.yaml found {bool(specs)}; names {FEATURES}: {FEATURES in text}",
            )
        except Exception as exc4:  # noqa: BLE001
            error("A-12 feature spec", exc4)
            record("A-12 feature spec on the model", False, results["errors"]["A-12 feature spec"])

# COMMAND ----------

results["pass"] = all(c["pass"] for c in results["checks"].values())
print(json.dumps(results, indent=2, default=str))
dbutils.notebook.exit(json.dumps(results, default=str))  # prints are not returned by the Jobs API
