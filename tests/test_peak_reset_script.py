"""The user-run reset script guards the AC-66 rebuild (manifest 41). No workspace is touched."""

from __future__ import annotations

import pytest
import reset_peak_model_outputs as reset

from smart_meter_peak_prediction import peak_config
from smart_meter_peak_prediction.config import Settings

SETTINGS = Settings()


def counts(**overrides):
    base = {
        peak_config.silver_weather_table(SETTINGS): 21165,
        peak_config.features_table(SETTINGS): 36480,
        peak_config.labels_table(SETTINGS): 36480,
        peak_config.bronze_weather_table(SETTINGS): 21165,
    }
    base.update(overrides)
    return base.get


def test_ac66_reset_drops_exactly_the_three_rebuildable_tables() -> None:
    statements = reset.plan(SETTINGS, counts())
    assert statements == [
        "DROP TABLE smart_meter_dev.silver.weather_hourly",
        "DROP TABLE smart_meter_dev.ml.household_features_daily",
        "DROP TABLE smart_meter_dev.ml.household_labels_daily",
    ]
    joined = " ".join(statements)
    for protected in ("bronze", "predictions", "model"):
        assert protected not in joined


def test_ac66_reset_refuses_unexpected_row_counts_missing_tables_and_empty_bronze() -> None:
    labels = peak_config.labels_table(SETTINGS)
    with pytest.raises(reset.ResetRefused, match="36480"):
        reset.plan(SETTINGS, counts(**{labels: 5}))
    reset.plan(SETTINGS, counts(**{labels: 5}), allow_other_counts=True)
    with pytest.raises(reset.ResetRefused, match="does not exist"):
        reset.plan(SETTINGS, counts(**{labels: None}))
    bronze = peak_config.bronze_weather_table(SETTINGS)
    with pytest.raises(reset.ResetRefused, match="empty or missing"):
        reset.plan(SETTINGS, counts(**{bronze: 0}))


def test_ac66_reset_refuses_without_the_before_snapshot() -> None:
    with pytest.raises(reset.ResetRefused, match="snapshot"):
        reset.plan(SETTINGS, counts(), snapshot_exists=False)
