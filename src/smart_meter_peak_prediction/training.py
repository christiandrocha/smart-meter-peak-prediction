"""Training library: splits, guards, deterministic fit, threshold, evaluation and run logging.

Everything here is pandas, NumPy and scikit-learn. The tracking and registry side is a ``Tracker``
protocol (``registry.MlflowTracker`` on the platform, a fake in unit tests), so the order of
effects is testable: all guards (G-02, G-03, G-05, G-11, parameter cross-check) and the fit run
before the tracker is touched, and a failure leaves no run, no metric, no model version and no
alias move (AC-53).

Determinism (AC-49): the rows are sorted by ``(target_date, household_id)`` before fitting, the
classifier has a fixed seed and no random early stopping, and the threshold rule compares F1
exactly on integer counts (ADR 0009).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from smart_meter_peak_prediction.model import (
    CATEGORY_CODES,
    FEATURE_COLUMNS,
    INTEGER_CATEGORY_OFFSETS,
    LABEL_COLUMN,
    ConsumptionSpikeModel,
    build_classifier,
    encode,
)
from smart_meter_peak_prediction.peak_config import (
    PROPERTY_PREFIX,
    PeakParameters,
    calendar_months,
    label_parameters_from_properties,
)

KEYS = ["household_id", "target_date"]
SPLITS = ("train", "validation", "test")
SEGMENT_METRICS = (
    "precision_at_t",
    "recall_at_t",
    "flag_count_at_t",
    "row_count",
    "positive_count",
)
THRESHOLD_RULE = (
    "max F1 on validation; candidates are the distinct validation scores; F1 compared exactly "
    "on integer counts; the highest threshold wins a tie"
)
RATIO_ZERO_BASELINE = 1e-6
TRAINING_SET_FILE = "training_set.parquet"


class GuardError(Exception):
    """A design guard (G-02, G-03, G-05, G-11, parameter cross-check) stopped the run."""


# ----------------------------------------------------------------------------- tracker protocol
@dataclass(frozen=True)
class TableRef:
    name: str
    version: int


@dataclass(frozen=True)
class RegisteredModel:
    version: int
    reload_max_abs_diff: float


class Tracker(Protocol):
    """What ``run_training`` needs from MLflow and the registry."""

    def run(self) -> AbstractContextManager[str]: ...
    def log_params(self, params: Mapping[str, Any]) -> None: ...
    def log_metrics(self, metrics: Mapping[str, float]) -> None: ...
    def log_frame(self, name: str, frame: pd.DataFrame) -> None: ...
    def log_json(self, name: str, content: Mapping[str, Any]) -> None: ...
    def log_inputs(self, tables: Sequence[TableRef]) -> None: ...
    def register_model(
        self,
        model: ConsumptionSpikeModel,
        *,
        sample_input: pd.DataFrame,
        expected_scores: np.ndarray,
        threshold: float,
    ) -> RegisteredModel: ...


@dataclass
class TrainingInputs:
    """The materialised training set and everything the run records about its sources."""

    frame: pd.DataFrame  # household_id, target_date, FEATURE_COLUMNS, label_consumption_spike
    feature_keys: pd.DataFrame  # household_id, feature_date of the feature table at its version
    features_table: TableRef
    labels_table: TableRef
    label_properties: Mapping[str, str]
    feature_properties: Mapping[str, str]
    git_commit: str
    library_versions: Mapping[str, str] = field(default_factory=dict)


@dataclass
class ThresholdChoice:
    threshold: float
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def f1(self) -> float:
        tp = self.true_positives
        return 2 * tp / (2 * tp + self.false_positives + self.false_negatives)


@dataclass
class TrainingResult:
    run_id: str
    model_version: int
    threshold: ThresholdChoice
    metrics: dict[str, float]
    scores: dict[str, pd.DataFrame]


# ----------------------------------------------------------------------------- rows and splits
def _dates(series: pd.Series) -> pd.Series:
    """Calendar dates as ``datetime64`` (midnight), whatever the input type."""
    return pd.to_datetime(series).dt.tz_localize(None).dt.normalize()


def select_training_rows(labels: pd.DataFrame, params: PeakParameters) -> pd.DataFrame:
    """Eligible rows with a non-null label whose ``target_date`` lies in one of the ranges."""
    target = _dates(labels["target_date"])
    in_range = pd.Series(False, index=labels.index)
    for start, end in params.split_ranges().values():
        in_range |= (target >= pd.Timestamp(start)) & (target <= pd.Timestamp(end))
    keep = labels["is_eligible"].astype(bool) & labels[LABEL_COLUMN].notna() & in_range
    selected = labels.loc[keep, [*KEYS, "feature_date", LABEL_COLUMN]].reset_index(drop=True)
    selected[LABEL_COLUMN] = selected[LABEL_COLUMN].astype(int)  # nulls were filtered out above
    return selected


def assign_splits(frame: pd.DataFrame, params: PeakParameters) -> pd.DataFrame:
    """Sort by ``(target_date, household_id)`` and assign ``split`` by ``target_date`` only."""
    out = frame.copy()
    out["target_date"] = _dates(out["target_date"])
    out = out.sort_values(["target_date", "household_id"], kind="mergesort").reset_index(drop=True)
    out["split"] = None
    for name, (start, end) in params.split_ranges().items():
        inside = (out["target_date"] >= pd.Timestamp(start)) & (
            out["target_date"] <= pd.Timestamp(end)
        )
        out.loc[inside, "split"] = name
    outside = out[out["split"].isna()]
    if len(outside):
        raise GuardError(
            f"{len(outside)} training row(s) lie outside the three split ranges, "
            f"first target_date {outside['target_date'].min():%Y-%m-%d}"
        )
    return out


# ----------------------------------------------------------------------------- guards
def check_git_commit(git_commit: str) -> None:
    """G-05."""
    if not git_commit or not git_commit.strip():
        raise GuardError("G-05 git commit parameter is empty")


def check_feature_rows(frame: pd.DataFrame, feature_keys: pd.DataFrame) -> None:
    """G-02: every row has a feature row dated exactly ``target_date - 1`` with a share value."""
    lookup = _dates(frame["target_date"]) - pd.Timedelta(days=1)
    wanted = pd.MultiIndex.from_arrays([frame["household_id"], lookup])
    present = pd.MultiIndex.from_arrays(
        [feature_keys["household_id"], _dates(feature_keys["feature_date"])]
    )
    missing = ~wanted.isin(present)
    if missing.any():
        first = frame.loc[missing, KEYS].head(3).to_dict("records")
        raise GuardError(
            f"G-02 {int(missing.sum())} training row(s) have no feature row dated target_date - 1; "
            f"first: {first}"
        )
    null_share = frame["complete_day_share_28d"].isna()
    if null_share.any():
        raise GuardError(
            f"G-02 {int(null_share.sum())} training row(s) have a null complete_day_share_28d"
        )


def check_empty_months(assigned: pd.DataFrame, params: PeakParameters) -> None:
    """G-03: every calendar month of the validation and test ranges has an eligible labelled row."""
    empty: list[str] = []
    for split in ("validation", "test"):
        start, end = params.split_ranges()[split]
        rows = assigned[assigned["split"] == split]
        present = set(zip(rows["target_date"].dt.year, rows["target_date"].dt.month, strict=True))
        empty += [
            f"{year}-{month:02d} ({split})"
            for year, month in calendar_months(start, end)
            if (year, month) not in present
        ]
    if empty:
        raise GuardError("G-03 months without eligible labelled rows: " + ", ".join(empty))


def check_validation_positives(assigned: pd.DataFrame) -> None:
    """G-11."""
    validation = assigned[assigned["split"] == "validation"]
    if int(validation[LABEL_COLUMN].sum()) == 0:
        raise GuardError("G-11 the validation split has no positive row")


def check_parameter_properties(
    label_properties: Mapping[str, str], feature_properties: Mapping[str, str]
) -> dict[str, float | int]:
    """Read the label parameters of the labels table and cross-check the feature table's."""
    parsed = label_parameters_from_properties(label_properties)
    for name in ("baseline_day_count", "label_lookback_weeks"):
        key = PROPERTY_PREFIX + name
        theirs = feature_properties.get(key)
        if theirs is None or int(theirs) != parsed[name]:
            raise GuardError(
                f"{name} differs between the labels table ({parsed[name]}) and the feature "
                f"table ({theirs}); rebuild both with the same parameters"
            )
    return parsed


# ----------------------------------------------------------------------------- threshold
def choose_threshold(labels: np.ndarray, scores: np.ndarray) -> ThresholdChoice:
    """ADR 0009: the distinct score that maximises F1; the highest one wins a tie.

    F1 at t is ``2 TP / (2 TP + FP + FN)`` over the rows with ``score >= t``. Values are
    compared as exact fractions of integer counts, never as floats.
    """
    y = np.asarray(labels).astype(int)
    s = np.asarray(scores, dtype="float64")
    if np.isnan(s).any():
        raise ValueError("validation scores contain NaN")
    positives = int(y.sum())
    if positives == 0:
        raise GuardError("G-11 the validation split has no positive row")
    order = np.argsort(-s, kind="stable")
    sorted_scores, sorted_labels = s[order], y[order]
    cumulative = np.cumsum(sorted_labels)
    last_of_value = np.flatnonzero(np.append(np.diff(sorted_scores) != 0, True))
    best: tuple[Fraction, ThresholdChoice] | None = None
    for index in last_of_value:  # highest score first
        tp = int(cumulative[index])
        flagged = int(index) + 1
        fp, fn = flagged - tp, positives - tp
        f1 = Fraction(2 * tp, 2 * tp + fp + fn)
        if best is None or f1 > best[0]:
            best = (f1, ThresholdChoice(float(sorted_scores[index]), tp, fp, fn))
    assert best is not None
    return best[1]


# ----------------------------------------------------------------------------- evaluation
def segment_metrics(
    prefix: str, labels: np.ndarray, scores: np.ndarray, threshold: float
) -> dict[str, float]:
    """Metrics of one segment; ``pr_auc`` is omitted when the segment has no positive row."""
    y = np.asarray(labels).astype(int)
    flagged = np.asarray(scores) >= threshold
    positives = int(y.sum())
    flags = int(flagged.sum())
    hits = int((flagged & (y == 1)).sum())
    metrics = {
        f"{prefix}_row_count": float(len(y)),
        f"{prefix}_positive_count": float(positives),
        f"{prefix}_flag_count_at_t": float(flags),
        f"{prefix}_precision_at_t": hits / flags if flags else 0.0,
        f"{prefix}_recall_at_t": hits / positives if positives else 0.0,
    }
    if positives:
        metrics[f"{prefix}_pr_auc"] = float(average_precision_score(y, scores))
    return metrics


def ratio_rule_scores(frame: pd.DataFrame) -> np.ndarray:
    """Reference score (D-30): total of D over the same-weekday baseline for D + 1."""
    baseline = frame["median_energy_kwh_same_weekday_8w"]
    if baseline.isna().any():
        raise ValueError("a labelled row has no baseline; the ratio rule is undefined")
    total = frame["total_energy_kwh_1d"].fillna(0.0)
    return (total / baseline.where(baseline != 0, RATIO_ZERO_BASELINE)).to_numpy(dtype="float64")


def evaluate_split(
    split: str, rows: pd.DataFrame, scores: np.ndarray, threshold: float, params: PeakParameters
) -> dict[str, float]:
    """Overall, per ACORN group and per calendar month metrics of one split, plus the ratio rule."""
    y = rows[LABEL_COLUMN].to_numpy()
    metrics = segment_metrics(split, y, scores, threshold)
    for group in sorted(rows["acorn_group"].dropna().unique()):
        picked = (rows["acorn_group"] == group).to_numpy()
        metrics |= segment_metrics(
            f"{split}_acorn_{group.lower()}", y[picked], scores[picked], threshold
        )
    start, end = params.split_ranges()[split]
    target = rows["target_date"]
    for year, month in calendar_months(start, end):
        picked = ((target.dt.year == year) & (target.dt.month == month)).to_numpy()
        if picked.any():
            metrics |= segment_metrics(
                f"{split}_month_{year}_{month:02d}", y[picked], scores[picked], threshold
            )
    if int(y.sum()):
        metrics[f"{split}_ratio_rule_pr_auc"] = float(
            average_precision_score(y, ratio_rule_scores(rows))
        )
    return metrics


# ----------------------------------------------------------------------------- run record
def frame_checksum(frame: pd.DataFrame, columns: Sequence[str]) -> int:
    """Order-independent checksum: the sum of per-row hashes modulo 2**64."""
    shown = frame[list(columns)].copy()
    for column in shown.columns:
        if pd.api.types.is_datetime64_any_dtype(shown[column]):
            shown[column] = shown[column].dt.strftime("%Y-%m-%d")
    hashes = pd.util.hash_pandas_object(shown, index=False)
    return sum(int(h) for h in hashes) % 2**64


def split_manifest(assigned: pd.DataFrame, inputs: TrainingInputs) -> dict[str, Any]:
    columns = [*KEYS, "split", *FEATURE_COLUMNS, LABEL_COLUMN]
    splits = {}
    for name in SPLITS:
        rows = assigned[assigned["split"] == name]
        splits[name] = {
            "rows": len(rows),
            "positives": int(rows[LABEL_COLUMN].sum()),
            "checksum": frame_checksum(rows, columns),
        }
    return {
        "splits": splits,
        "checksum_columns": columns,
        "features_table": inputs.features_table.name,
        "features_table_version": inputs.features_table.version,
        "labels_table": inputs.labels_table.name,
        "labels_table_version": inputs.labels_table.version,
    }


def run_parameters(
    params: PeakParameters,
    classifier: Any,
    inputs: TrainingInputs,
    label_parameters: Mapping[str, float | int],
) -> dict[str, str]:
    """Parameters of the run (AC-50): model, seed, every classifier argument, every FR-31 value.

    The training-side FR-31 parameters come from the job; the label and eligibility parameters come
    from the labels table properties. ``target_date`` is scoring only (D-38).
    """
    logged = {
        "model_class": type(classifier).__name__,
        **{name: str(value) for name, value in classifier.get_params().items()},
        **params.training_parameters(),
        **{name: repr(value) for name, value in label_parameters.items()},
        "features_table": inputs.features_table.name,
        "features_table_version": str(inputs.features_table.version),
        "labels_table": inputs.labels_table.name,
        "labels_table_version": str(inputs.labels_table.version),
        "git_commit": inputs.git_commit,
        "threshold_rule": THRESHOLD_RULE,
        "feature_columns": ",".join(FEATURE_COLUMNS),
        "categorical_codes": json.dumps(
            {**CATEGORY_CODES, "integer_offsets_value_minus": INTEGER_CATEGORY_OFFSETS},
            sort_keys=True,
        ),
    }
    versions = {
        "scikit_learn": inputs.library_versions.get("scikit_learn"),
        "mlflow": inputs.library_versions.get("mlflow"),
        "databricks_feature_engineering": inputs.library_versions.get(
            "databricks_feature_engineering"
        ),
        "python": inputs.library_versions.get("python"),
    }
    logged.update({k: str(v) for k, v in versions.items() if v is not None})
    return logged


# ----------------------------------------------------------------------------- orchestration
def run_training(
    inputs: TrainingInputs, params: PeakParameters, tracker: Tracker
) -> TrainingResult:
    """Guards, fit, threshold, evaluation, then log and register through ``tracker``."""
    check_git_commit(inputs.git_commit)
    assigned = assign_splits(inputs.frame, params)
    check_feature_rows(assigned, inputs.feature_keys)
    check_empty_months(assigned, params)
    check_validation_positives(assigned)
    label_parameters = check_parameter_properties(
        inputs.label_properties, inputs.feature_properties
    )

    train = assigned[assigned["split"] == "train"]
    classifier = build_classifier(params.random_seed)
    classifier.fit(encode(train), train[LABEL_COLUMN].to_numpy().astype(int))

    scored: dict[str, pd.DataFrame] = {}
    rows_by_split: dict[str, pd.DataFrame] = {}
    for split in ("validation", "test"):
        rows = assigned[assigned["split"] == split].reset_index(drop=True)
        rows_by_split[split] = rows
        scores = classifier.predict_proba(encode(rows))[:, 1]
        scored[split] = rows[[*KEYS, LABEL_COLUMN]].assign(score=scores)
    choice = choose_threshold(
        scored["validation"][LABEL_COLUMN].to_numpy(), scored["validation"]["score"].to_numpy()
    )
    metrics: dict[str, float] = {
        "validation_threshold": choice.threshold,
        "validation_f1_at_t": choice.f1,
    }
    for split, rows in rows_by_split.items():
        metrics |= evaluate_split(
            split, rows, scored[split]["score"].to_numpy(), choice.threshold, params
        )

    artifact = assigned[[*KEYS, "split", *FEATURE_COLUMNS, LABEL_COLUMN]].copy()
    artifact["target_date"] = artifact["target_date"].dt.date
    scores_out = {
        split: frame.assign(target_date=frame["target_date"].dt.date)
        for split, frame in scored.items()
    }

    with tracker.run() as run_id:
        tracker.log_params(run_parameters(params, classifier, inputs, label_parameters))
        tracker.log_inputs([inputs.labels_table, inputs.features_table])
        tracker.log_frame(TRAINING_SET_FILE, artifact)
        tracker.log_frame("validation_scores.parquet", scores_out["validation"])
        tracker.log_frame("test_scores.parquet", scores_out["test"])
        tracker.log_json("training_set_manifest.json", split_manifest(assigned, inputs))
        tracker.log_metrics(metrics)
        registered = tracker.register_model(
            ConsumptionSpikeModel(classifier),
            sample_input=rows_by_split["test"][[*KEYS, *FEATURE_COLUMNS]],
            expected_scores=scored["test"]["score"].to_numpy(),
            threshold=choice.threshold,
        )
        tracker.log_metrics({"champion_reload_max_abs_diff": registered.reload_max_abs_diff})
    return TrainingResult(
        run_id=run_id,
        model_version=registered.version,
        threshold=choice,
        metrics=metrics | {"champion_reload_max_abs_diff": registered.reload_max_abs_diff},
        scores=scored,
    )
