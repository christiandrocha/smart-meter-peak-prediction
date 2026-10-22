"""PEAK_MODEL training on dev: run records, registry and lineage (AC-48 to AC-52, AC-54, AC-55).

AC-53 (an empty validation month stops the run) is covered by a unit test only; the DESIGN does not
give it a live test because it would need corrupt label rows in the shared tables.

Run order: run the training job twice on unchanged tables (``databricks bundle run -t dev
smart_meter_peak_model_training``), then these tests. AC-49 compares the two newest runs and fails
with that instruction when fewer than two runs share the same source table versions. Each training
run registers a version and moves ``champion`` (ADR 0009), so the tests read the newest run.
"""

from __future__ import annotations

import json
import re
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from smart_meter_peak_prediction import training
from smart_meter_peak_prediction.model import FEATURE_COLUMNS
from smart_meter_peak_prediction.peak_config import LABEL_PROPERTY_NAMES, PeakParameters

pytestmark = pytest.mark.integration

DEFAULTS = PeakParameters()
LABEL = "label_consumption_spike"
INT_FEATURES = ("target_weekday", "target_month", "temperature_hour_count_1d")
LINEAGE_WAIT_S = 300
ACORN_GROUPS = ("affluent", "comfortable", "adversity")
VALIDATION_MONTHS = ("2013_08", "2013_09", "2013_10", "2013_11")
TEST_MONTHS = ("2013_12", "2014_01", "2014_02")


def _days(series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d")


def _table_frame(sql, statement: str) -> pd.DataFrame:
    return pd.DataFrame(sql.rows(statement))


def _versions(run) -> tuple[int, int]:
    return (
        int(run.data.params["labels_table_version"]),
        int(run.data.params["features_table_version"]),
    )


# ----------------------------------------------------------------------------- AC-48
def test_ac48_logged_training_set_equals_labels_and_features_at_t_minus_1(
    sql, peak_names, mlflow_registry
) -> None:
    run = mlflow_registry.latest_run()
    params = run.data.params
    logged = mlflow_registry.parquet(run.info.run_id, "training_set.parquet")
    labels_version, features_version = _versions(run)
    logged = logged.assign(target_date=_days(logged["target_date"]))

    # split ranges: ordered, disjoint and every row inside its own range
    ranges = {
        name: (params[f"{name}_start"], params[f"{name}_end"])
        for name in ("train", "validation", "test")
    }
    order = list(ranges.values())
    assert order[0][1] < order[1][0]
    assert order[1][1] < order[2][0]
    for name, (start, end) in ranges.items():
        dates = logged.loc[logged["split"] == name, "target_date"]
        assert len(dates) > 0, name
        assert dates.min() >= start, name
        assert dates.max() <= end, name
    assert set(logged["split"]) == set(ranges)

    # the logged rows are exactly the eligible labelled rows of the labels table at its version
    in_ranges = " OR ".join(
        f"target_date BETWEEN DATE'{s}' AND DATE'{e}'" for s, e in ranges.values()
    )
    expected = _table_frame(
        sql,
        f"SELECT household_id, CAST(target_date AS STRING) AS target_date, {LABEL} "
        f"FROM {peak_names.labels} VERSION AS OF {labels_version} "
        f"WHERE is_eligible AND {LABEL} IS NOT NULL AND ({in_ranges})",
    )
    key = ["household_id", "target_date"]
    merged = logged[[*key, LABEL]].merge(
        expected, on=key, how="outer", suffixes=("", "_labels"), indicator=True
    )
    assert (merged["_merge"] == "both").all(), "logged rows differ from the labels table"
    assert (merged[LABEL] == merged[f"{LABEL}_labels"].astype(int)).all()

    # 100% of the feature values equal the feature table at its version, on target_date - 1
    columns = ", ".join(FEATURE_COLUMNS)
    features = _table_frame(
        sql,
        f"SELECT household_id, CAST(date_add(feature_date, 1) AS STRING) AS target_date, {columns} "
        f"FROM {peak_names.features} VERSION AS OF {features_version}",
    )
    joined = logged.merge(features, on=key, how="left", suffixes=("", "_table"), indicator=True)
    assert (joined["_merge"] == "both").all(), "a logged row has no feature row at T - 1"
    for column in FEATURE_COLUMNS:
        left, right = joined[column], joined[f"{column}_table"]
        if column in ("acorn_group", "tariff"):
            assert (left.fillna("") == right.fillna("")).all(), column
        else:
            left, right = left.astype(float), right.astype(float)
            same = np.isclose(left, right, rtol=1e-12, atol=0.0, equal_nan=True)
            assert same.all(), f"{column}: {int((~same).sum())} rows differ"


# ----------------------------------------------------------------------------- AC-49
def test_ac49_two_training_runs_are_identical(mlflow_registry) -> None:
    runs = mlflow_registry.training_runs()
    assert len(runs) >= 2, "run the training job twice on unchanged tables (runbook)"
    newest, previous = runs[0], runs[1]
    assert _versions(newest) == _versions(previous), (
        "the two newest runs used different table versions: rerun the training job twice with no "
        "build in between"
    )
    first = mlflow_registry.parquet(newest.info.run_id, "test_scores.parquet")
    second = mlflow_registry.parquet(previous.info.run_id, "test_scores.parquet")
    keys = ["household_id", "target_date"]
    both = first.merge(second, on=keys, suffixes=("_a", "_b"))
    assert len(both) == len(first) == len(second)
    assert float(np.max(np.abs(both["score_a"] - both["score_b"]))) == 0.0
    assert (
        newest.data.metrics["validation_threshold"] == previous.data.metrics["validation_threshold"]
    )
    assert newest.data.metrics == previous.data.metrics


# ----------------------------------------------------------------------------- AC-50
def test_ac50_logged_parameters(mlflow_registry) -> None:
    params = mlflow_registry.latest_run().data.params
    assert params["model_class"] == "HistGradientBoostingClassifier"
    assert params["random_state"] == str(DEFAULTS.random_seed)
    assert params["early_stopping"] == "False"
    fr31 = set(DEFAULTS.training_parameters()) | set(LABEL_PROPERTY_NAMES)
    missing = sorted(name for name in fr31 if name not in params)
    assert not missing, f"FR-31 parameters not logged: {missing}"
    assert "target_date" not in params  # scoring only (D-38)
    for name, value in DEFAULTS.training_parameters().items():
        assert params[name] == value, name


# ----------------------------------------------------------------------------- AC-51
def _best_threshold(labels: np.ndarray, scores: np.ndarray) -> tuple[float, Fraction]:
    """Brute force over every distinct score; exact F1; the highest threshold wins a tie."""
    best_f1, best_t = Fraction(-1), 0.0
    for t in sorted(set(scores.tolist())):
        flagged = scores >= t
        tp = int(np.sum(flagged & (labels == 1)))
        fp = int(np.sum(flagged & (labels == 0)))
        fn = int(np.sum(~flagged & (labels == 1)))
        f1 = Fraction(2 * tp, 2 * tp + fp + fn) if tp else Fraction(0)
        if f1 >= best_f1:
            best_f1, best_t = f1, t
    return best_t, best_f1


def test_ac51_version_tag_equals_recomputed_threshold(mlflow_registry) -> None:
    run = mlflow_registry.latest_run()
    scores = mlflow_registry.parquet(run.info.run_id, "validation_scores.parquet")
    threshold, f1 = _best_threshold(scores[LABEL].to_numpy(), scores["score"].to_numpy())
    version = mlflow_registry.version_of_run(run.info.run_id)
    assert mlflow_registry.threshold(version) == threshold
    assert run.data.metrics["validation_threshold"] == threshold
    assert abs(run.data.metrics["validation_f1_at_t"] - float(f1)) <= 1e-9


# ----------------------------------------------------------------------------- AC-52
def test_ac52_seed42_metrics_and_signal(mlflow_registry) -> None:
    metrics = mlflow_registry.latest_run().data.metrics
    assert not [name for name in metrics if "accuracy" in name.lower()]
    segments = ["validation", "test"]
    segments += [f"validation_acorn_{g}" for g in ACORN_GROUPS]
    segments += [f"test_acorn_{g}" for g in ACORN_GROUPS]
    segments += [f"validation_month_{m}" for m in VALIDATION_MONTHS]
    segments += [f"test_month_{m}" for m in TEST_MONTHS]
    for segment in segments:
        for suffix in ("row_count", "positive_count"):
            assert f"{segment}_{suffix}" in metrics, f"{segment}_{suffix}"
        assert f"{segment}_precision_at_t" in metrics, segment
        assert f"{segment}_recall_at_t" in metrics, segment
    assert "test_ratio_rule_pr_auc" in metrics
    positive_share = metrics["test_positive_count"] / metrics["test_row_count"]
    assert metrics["test_pr_auc"] > positive_share


# ----------------------------------------------------------------------------- AC-54
def test_ac54_registered_version_alias_reload_and_run_records(
    mlflow_registry, peak_names, training_job
) -> None:
    run = mlflow_registry.latest_run()
    version = mlflow_registry.version_of_run(run.info.run_id)
    all_versions = [
        int(v.version)
        for v in mlflow_registry.client.search_model_versions(f"name = '{peak_names.model}'")
    ]
    assert version == max(all_versions)
    assert mlflow_registry.champion_version() == version
    info = mlflow_registry.mlflow.models.get_model_info(f"models:/{peak_names.model}/{version}")
    assert info.signature is not None
    assert set(FEATURE_COLUMNS) <= {c.name for c in info.signature.inputs.inputs}
    assert run.data.metrics["champion_reload_max_abs_diff"] == 0.0

    params = run.data.params
    assert params["features_table"] == peak_names.features
    assert params["labels_table"] == peak_names.labels
    assert int(params["features_table_version"]) >= 0
    assert int(params["labels_table_version"]) >= 0
    assert re.fullmatch(r"[0-9a-f]{40}", params["git_commit"])
    deployed = training_job.settings.tasks[0].notebook_task.base_parameters["git_commit"]
    assert params["git_commit"] == deployed, "the run used a different commit than the deployed job"


# ----------------------------------------------------------------------------- AC-55
def test_ac55_uc_lineage_lists_feature_table_upstream_of_model(
    workspace, mlflow_registry, peak_names
) -> None:
    deadline = time.monotonic() + LINEAGE_WAIT_S
    last = ""
    short = peak_names.model.split(".")[-1]
    found = False
    while time.monotonic() < deadline and not found:
        try:
            response = workspace.api_client.do(
                "GET",
                "/api/2.0/lineage-tracking/table-lineage",
                query={"table_name": peak_names.features, "include_entity_lineage": "true"},
            )
            last = json.dumps(response)
            found = peak_names.model in last or short in last
        except Exception as exc:  # noqa: BLE001  (lineage appears with a delay; poll)
            last = f"{type(exc).__name__}: {str(exc)[:300]}"
        if not found:
            time.sleep(30)
    missing = f"model not downstream of the feature table after {LINEAGE_WAIT_S} s: {last[:600]}"
    assert found, missing

    version = mlflow_registry.version_of_run(mlflow_registry.latest_run().info.run_id)
    local = mlflow_registry.mlflow.artifacts.download_artifacts(
        artifact_uri=f"models:/{peak_names.model}/{version}", dst_path=mlflow_registry.scratch_dir
    )
    specs = list(Path(local).rglob("feature_spec.yaml"))
    assert specs, "the logged model has no feature_spec.yaml"
    assert peak_names.features in specs[0].read_text(encoding="utf-8")


def test_ac55_logged_versions_rebuild_the_same_training_set(
    sql, peak_names, mlflow_registry
) -> None:
    """The 1B check kept as extra evidence: an explicit join at the logged versions."""
    run = mlflow_registry.latest_run()
    manifest = json.loads(
        mlflow_registry.artifact(run.info.run_id, "training_set_manifest.json").read_text()
    )
    labels_version = manifest["labels_table_version"]
    features_version = manifest["features_table_version"]
    columns = manifest["checksum_columns"]
    params = run.data.params
    ranges = {
        n: (params[f"{n}_start"], params[f"{n}_end"]) for n in ("train", "validation", "test")
    }
    in_ranges = " OR ".join(
        f"l.target_date BETWEEN DATE'{s}' AND DATE'{e}'" for s, e in ranges.values()
    )
    names = ", ".join(f"f.{c}" for c in FEATURE_COLUMNS)
    frame = _table_frame(
        sql,
        f"SELECT l.household_id, CAST(l.target_date AS STRING) AS target_date, {names}, "
        f"l.{LABEL} FROM {peak_names.labels} VERSION AS OF {labels_version} l "
        f"JOIN {peak_names.features} VERSION AS OF {features_version} f "
        f"ON f.household_id = l.household_id AND f.feature_date = date_sub(l.target_date, 1) "
        f"WHERE l.is_eligible AND l.{LABEL} IS NOT NULL AND ({in_ranges})",
    )
    frame["target_date"] = pd.to_datetime(frame["target_date"])
    frame[LABEL] = frame[LABEL].astype("int64")
    for column in FEATURE_COLUMNS:
        if column in INT_FEATURES:
            frame[column] = frame[column].astype("int32")  # as the training frame (Spark int)
        elif column not in ("acorn_group", "tariff"):
            frame[column] = frame[column].astype("float64")
    frame["split"] = None
    for name, (start, end) in ranges.items():
        inside = (frame["target_date"] >= pd.Timestamp(start)) & (
            frame["target_date"] <= pd.Timestamp(end)
        )
        frame.loc[inside, "split"] = name
    for name, expected in manifest["splits"].items():
        rows = frame[frame["split"] == name]
        assert len(rows) == expected["rows"], name
        assert int(rows[LABEL].sum()) == expected["positives"], name
        assert training.frame_checksum(rows, columns) == expected["checksum"], name
