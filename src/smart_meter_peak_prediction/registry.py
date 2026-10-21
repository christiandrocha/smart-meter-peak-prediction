"""Registry adapter: Feature Engineering client, MLflow tracking and the Unity Catalog registry.

A thin layer over ``databricks-feature-engineering`` and MLflow. The Feature Engineering package is
imported inside the functions that need it, so the module loads (and the pure parts are tested)
where the client is not installed. Functions that talk to the platform take the clients as
arguments; the notebooks create them.

Guards raised here: G-04 (feature table unchanged while the training set is materialised), G-07
(alias ``champion`` resolves and carries a parseable threshold tag) and G-08 (the reloaded new
version reproduces the in-memory test scores exactly, checked before the alias moves).
"""

from __future__ import annotations

import importlib.metadata
import json
import platform
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from smart_meter_peak_prediction.model import FEATURE_COLUMNS, ConsumptionSpikeModel
from smart_meter_peak_prediction.peak_config import CHAMPION_ALIAS, THRESHOLD_TAG
from smart_meter_peak_prediction.training import GuardError, RegisteredModel, TableRef

PACKAGE_DIR = Path(__file__).resolve().parent


class ChampionError(Exception):
    """G-07: alias ``champion`` or its threshold tag is missing or unusable."""


class ReloadMismatchError(Exception):
    """G-08: the reloaded model version does not reproduce the in-memory scores."""


@dataclass(frozen=True)
class Champion:
    version: int
    threshold: float

    def uri(self, model_name: str) -> str:
        return f"models:/{model_name}/{self.version}"


# ----------------------------------------------------------------------------- tables
def ensure_feature_table(fe: Any, spark: Any, name: str, schema: Any) -> bool:
    """Create the feature table (time-series column ``feature_date``) when it is missing.

    Returns True when it was created. DA-15: later writes use a plain MERGE.
    """
    if spark.catalog.tableExists(name):
        return False
    fe.create_table(
        name=name,
        primary_keys=["household_id", "feature_date"],
        timeseries_columns="feature_date",
        schema=schema,
        description="Daily household features dated D, used to predict day D + 1 (PEAK_MODEL)",
    )
    return True


def table_version(spark: Any, table: str) -> int:
    """Latest Delta version of a table."""
    return int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"])


def table_properties(spark: Any, table: str) -> dict[str, str]:
    rows = spark.sql(f"SHOW TBLPROPERTIES {table}").collect()
    return {row["key"]: row["value"] for row in rows}


def build_training_set(
    fe: Any, spark: Any, rows: pd.DataFrame, features_table: str, feature_columns: Sequence[str]
) -> tuple[Any, pd.DataFrame, int]:
    """Point-in-time training set (spike 05 shape). Returns ``(training_set, frame, version)``.

    ``rows`` holds ``household_id``, ``target_date``, ``feature_date`` (= ``target_date`` - 1) and
    the label. G-04: the feature table version before and after materialising must be equal, so
    the version that is logged is the version that was read.
    """
    from databricks.feature_engineering import FeatureLookup
    from pyspark.sql import functions as F

    before = table_version(spark, features_table)
    # pandas date columns can arrive as timestamps; the lookup needs DATE keys, so cast both.
    labels_sdf = (
        spark.createDataFrame(
            rows.rename(columns={"feature_date": "lookup_date"})[
                ["household_id", "target_date", "lookup_date", "label_consumption_spike"]
            ]
        )
        .withColumn("target_date", F.col("target_date").cast("date"))
        .withColumn("lookup_date", F.col("lookup_date").cast("date"))
    )
    training_set = fe.create_training_set(
        df=labels_sdf,
        feature_lookups=[
            FeatureLookup(
                table_name=features_table,
                lookup_key="household_id",
                timestamp_lookup_key="lookup_date",
                feature_names=list(feature_columns),
            )
        ],
        label="label_consumption_spike",
        exclude_columns=["lookup_date"],
    )
    frame = training_set.load_df().toPandas()
    after = table_version(spark, features_table)
    if before != after:
        raise GuardError(
            f"G-04 {features_table} changed from version {before} to {after} while the "
            "training set was built; run training when no daily run is active"
        )
    return training_set, frame, before


# ----------------------------------------------------------------------------- champion
def resolve_champion(client: Any, model_name: str) -> Champion:
    """G-07: version behind alias ``champion`` and its ``decision_threshold`` tag."""
    try:
        version = client.get_model_version_by_alias(model_name, CHAMPION_ALIAS)
    except Exception as exc:
        raise ChampionError(
            f"alias '{CHAMPION_ALIAS}' of model {model_name} does not resolve: {exc}"
        ) from exc
    tag = (getattr(version, "tags", None) or {}).get(THRESHOLD_TAG)
    try:
        threshold = float(tag)
        if not 0 < threshold <= 1:
            raise ValueError("threshold outside (0, 1]")
    except (TypeError, ValueError) as exc:
        raise ChampionError(
            f"version {version.version} of {model_name} has no usable tag '{THRESHOLD_TAG}' "
            f"(found {tag!r})"
        ) from exc
    return Champion(version=int(version.version), threshold=threshold)


def fe_scorer(fe: Any) -> Callable[[str, Any], Any]:
    """Scorer for ``scoring.run``: ``fe.score_batch`` returns the input rows plus ``prediction``."""

    def score(model_uri: str, df: Any) -> Any:
        return fe.score_batch(model_uri=model_uri, df=df, result_type="double")

    return score


def library_versions() -> dict[str, str]:
    """Versions a training run records (G-01 pins the first two)."""
    found = {"python": platform.python_version()}
    for key, package in (
        ("scikit_learn", "scikit-learn"),
        ("mlflow", "mlflow"),
        ("databricks_feature_engineering", "databricks-feature-engineering"),
    ):
        try:
            found[key] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            try:
                found[key] = importlib.metadata.version("mlflow-skinny") if key == "mlflow" else ""
            except importlib.metadata.PackageNotFoundError:
                found[key] = ""
    return {k: v for k, v in found.items() if v}


# ----------------------------------------------------------------------------- tracker
class MlflowTracker:
    """``training.Tracker`` over MLflow, the Feature Engineering client and the UC registry."""

    def __init__(
        self,
        *,
        mlflow: Any,
        client: Any,
        fe: Any,
        training_set: Any,
        model_name: str,
        run_name: str = "train",
        code_paths: Sequence[str | Path] | None = None,
    ):
        self.mlflow = mlflow
        self.client = client
        self.fe = fe
        self.training_set = training_set
        self.model_name = model_name
        self.run_name = run_name
        self.code_paths = [str(p) for p in (code_paths or [PACKAGE_DIR])]
        self._run_id: str | None = None

    @contextmanager
    def run(self) -> Iterator[str]:
        with self.mlflow.start_run(run_name=self.run_name) as active:
            self._run_id = active.info.run_id
            yield active.info.run_id

    def log_params(self, params: Mapping[str, Any]) -> None:
        self.mlflow.log_params({k: str(v) for k, v in params.items()})

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self.mlflow.log_metrics({k: float(v) for k, v in metrics.items()})

    def log_frame(self, name: str, frame: pd.DataFrame) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            frame.to_parquet(path, index=False)
            self.mlflow.log_artifact(str(path))

    def log_json(self, name: str, content: Mapping[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
            self.mlflow.log_artifact(str(path))

    def log_inputs(self, tables: Sequence[TableRef]) -> None:
        for table in tables:
            dataset = self.mlflow.data.load_delta(table_name=table.name, version=str(table.version))
            self.mlflow.log_input(dataset, context="training")

    def register_model(
        self,
        model: ConsumptionSpikeModel,
        *,
        sample_input: pd.DataFrame,
        expected_scores: np.ndarray,
        threshold: float,
    ) -> RegisteredModel:
        """Log with the training set, reload and compare (G-08), then tag, then move the alias."""
        from mlflow.models import infer_signature

        signature = infer_signature(sample_input[FEATURE_COLUMNS], expected_scores)
        self.fe.log_model(
            model=model,
            artifact_path="model",
            flavor=self.mlflow.pyfunc,
            training_set=self.training_set,
            registered_model_name=self.model_name,
            signature=signature,
            code_paths=self.code_paths,
        )
        version = max(
            int(v.version)
            for v in self.client.search_model_versions(
                f"name = '{self.model_name}' and run_id = '{self._run_id}'"
            )
        )
        reloaded = self.mlflow.pyfunc.load_model(f"models:/{self.model_name}/{version}")
        again = np.asarray(reloaded.predict(sample_input[FEATURE_COLUMNS]), dtype="float64")
        diff = float(np.max(np.abs(again - np.asarray(expected_scores, dtype="float64"))))
        if diff != 0.0:
            raise ReloadMismatchError(
                f"G-08 version {version} of {self.model_name} reloads with max abs difference "
                f"{diff}; champion is unchanged"
            )
        self.client.set_model_version_tag(
            self.model_name, str(version), THRESHOLD_TAG, repr(float(threshold))
        )
        self.client.set_registered_model_alias(self.model_name, CHAMPION_ALIAS, version)
        return RegisteredModel(version=version, reload_max_abs_diff=diff)
