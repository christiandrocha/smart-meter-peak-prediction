"""Model wrapper: feature order, fixed categorical codes, classifier factory and pyfunc class.

This module imports no PySpark and no other module of the package, so the pyfunc class loads in any
environment that has scikit-learn and MLflow (DA-16: the model is logged with ``code_paths`` set to
the package folder).

OD-10: scikit-learn 1.3 needs integer-coded categories. The wrapper encodes with a fixed map, not a
fitted encoder, so nothing is fitted on data outside the classifier and ``fe.score_batch`` can
pass the raw feature table. Unknown categories become NaN; numeric nulls stay NaN and use the
native missing value support. Nothing is imputed or scaled.
"""

from __future__ import annotations

import mlflow.pyfunc
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

FEATURE_COLUMNS = [
    "total_energy_kwh_1d",
    "max_energy_kwh_1d",
    "avg_energy_kwh_7d",
    "avg_energy_kwh_28d",
    "median_energy_kwh_same_weekday_8w",
    "complete_day_share_28d",
    "target_weekday",
    "target_month",
    "acorn_group",
    "tariff",
    "mean_temperature_c_1d",
    "temperature_hour_count_1d",
]
LABEL_COLUMN = "label_consumption_spike"

CATEGORY_CODES: dict[str, dict[str, int]] = {
    "acorn_group": {"Affluent": 0, "Comfortable": 1, "Adversity": 2},
    "tariff": {"Std": 0, "ToU": 1},
}
# Integer categories: the code is the value minus the offset (Monday = 1 -> 0, January = 1 -> 0).
INTEGER_CATEGORY_OFFSETS = {"target_weekday": (1, 7), "target_month": (1, 12)}
CATEGORICAL_COLUMNS = ("target_weekday", "target_month", "acorn_group", "tariff")
CATEGORICAL_MASK = [column in CATEGORICAL_COLUMNS for column in FEATURE_COLUMNS]


def encode(frame: pd.DataFrame) -> np.ndarray:
    """Select ``FEATURE_COLUMNS``, apply the fixed codes and return a float64 matrix."""
    missing = [c for c in FEATURE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError("input lacks feature column(s): " + ", ".join(missing))
    encoded: dict[str, np.ndarray] = {}
    for column in FEATURE_COLUMNS:
        if column in CATEGORY_CODES:
            codes = CATEGORY_CODES[column]
            values = [codes.get(v, np.nan) if isinstance(v, str) else np.nan for v in frame[column]]
            encoded[column] = np.asarray(values, dtype="float64")
        elif column in INTEGER_CATEGORY_OFFSETS:
            low, high = INTEGER_CATEGORY_OFFSETS[column]
            numbers = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")
            valid = (numbers >= low) & (numbers <= high) & (numbers == np.floor(numbers))
            encoded[column] = np.where(valid, numbers - low, np.nan)
        else:
            encoded[column] = pd.to_numeric(frame[column], errors="coerce").to_numpy(
                dtype="float64"
            )
    return np.column_stack([encoded[c] for c in FEATURE_COLUMNS])


def build_classifier(random_seed: int) -> HistGradientBoostingClassifier:
    """The one classifier of v0.1 (D-30): fixed seed, no internal random early-stopping split."""
    return HistGradientBoostingClassifier(
        random_state=random_seed,
        early_stopping=False,
        categorical_features=CATEGORICAL_MASK,
    )


class ConsumptionSpikeModel(mlflow.pyfunc.PythonModel):
    """Returns the probability of the positive class for rows of raw feature values (FR-29)."""

    def __init__(self, classifier: HistGradientBoostingClassifier):
        self.classifier = classifier

    def predict(self, context, model_input, params=None):
        frame = model_input if isinstance(model_input, pd.DataFrame) else pd.DataFrame(model_input)
        return self.classifier.predict_proba(encode(frame))[:, 1]
