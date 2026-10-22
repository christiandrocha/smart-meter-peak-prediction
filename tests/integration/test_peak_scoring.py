"""PEAK_MODEL scoring on dev (AC-56 to AC-60).

Run order (runbook "Evidence order"): AC-58 (default target date), AC-59 (backfill of the test
range, run twice), then AC-56 (it compares the backfilled predictions with the logged test scores),
then the AC-57 pair back to back, then AC-60. The tests start only ``score_predictions`` (the
pipeline task is not part of them), so they do not collide with the ingestion job (DA-13). They
need a trained ``champion`` (training job) and built feature and label tables.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.integration

DEFAULT_DATE = "2014-02-28"
FEATURE_DATE = "2014-02-27"
BEYOND_DATE = "2014-03-05"
BEYOND_FEATURE_DATE = "2014-03-04"
TEST_START, TEST_END = "2013-12-01", "2014-02-27"
PREDICTION_COLUMNS = ["household_id", "target_date", "score", "label", "model_version"]
ALL_COLUMNS = [*PREDICTION_COLUMNS, "_scored_at"]


def _hash_columns(columns: list[str]) -> str:
    return ", ".join(f"`{c}`" for c in columns)


def _per_date(sql, table: str, columns: list[str]) -> dict[str, tuple[int, str]]:
    """Row count and order-independent checksum per target date."""
    rows = sql.rows(
        f"SELECT CAST(target_date AS STRING) AS d, count(*) AS n, "
        f"CAST(sum(CAST(xxhash64({_hash_columns(columns)}) AS DECIMAL(38,0))) AS STRING) AS cs "
        f"FROM {table} GROUP BY target_date"
    )
    return {row["d"]: (row["n"], row["cs"]) for row in rows}


def _scored_at(sql, table: str, day: str) -> int:
    return sql.scalar(
        f"SELECT unix_micros(max(_scored_at)) FROM {table} WHERE target_date = DATE'{day}'"
    )


# ----------------------------------------------------------------------------- AC-58
def test_ac58_run_without_target_date_scores_2014_02_28(
    sql, peak_names, peak_job, peak_runner
) -> None:
    run = peak_runner.run(peak_job, only=["score_predictions"])
    summary = run.outputs["score_predictions"]
    assert summary["target_dates"] == [DEFAULT_DATE]
    assert summary["feature_dates"] == [FEATURE_DATE]
    rows = sql.scalar(
        f"SELECT count(*) FROM {peak_names.predictions} WHERE target_date = DATE'{DEFAULT_DATE}'"
    )
    assert rows > 0
    assert rows == summary["rows"]


# ----------------------------------------------------------------------------- AC-59
def _backfill(peak_runner, peak_job) -> dict:
    params = {"target_date": TEST_START, "target_date_end": TEST_END}
    return peak_runner.run(peak_job, params=params, only=["score_predictions"]).outputs[
        "score_predictions"
    ]


def test_ac59_backfill_covers_test_range_and_rerun_changes_only_scored_at(
    sql, peak_names, peak_job, peak_runner
) -> None:
    summary = _backfill(peak_runner, peak_job)
    assert len(summary["target_dates"]) == 89
    in_range = f"target_date BETWEEN DATE'{TEST_START}' AND DATE'{TEST_END}'"
    eligible = {
        row["d"]: row["n"]
        for row in sql.rows(
            f"SELECT CAST(target_date AS STRING) AS d, count(*) AS n "
            f"FROM {peak_names.labels} WHERE is_eligible AND {in_range} GROUP BY target_date"
        )
    }
    predicted = {
        row["d"]: row["n"]
        for row in sql.rows(
            f"SELECT CAST(target_date AS STRING) AS d, count(*) AS n "
            f"FROM {peak_names.predictions} WHERE {in_range} GROUP BY target_date"
        )
    }
    assert len(predicted) == 89
    assert predicted == eligible
    missing = sql.one(
        f"SELECT count(*) AS n, count_if(p.household_id IS NULL) AS missing "
        f"FROM {peak_names.labels} l LEFT JOIN {peak_names.predictions} p "
        f"ON p.household_id = l.household_id AND p.target_date = l.target_date "
        f"WHERE l.is_eligible AND l.label_consumption_spike IS NOT NULL "
        f"AND l.target_date BETWEEN DATE'{TEST_START}' AND DATE'{TEST_END}'"
    )
    assert missing["n"] == 5116
    assert missing["missing"] == 0

    before = _per_date(sql, peak_names.predictions, PREDICTION_COLUMNS)
    before_scored = _scored_at(sql, peak_names.predictions, TEST_END)
    _backfill(peak_runner, peak_job)
    after = _per_date(sql, peak_names.predictions, PREDICTION_COLUMNS)
    assert after == before  # no column except _scored_at changed, on any date
    assert _scored_at(sql, peak_names.predictions, TEST_END) > before_scored


# ----------------------------------------------------------------------------- AC-56
def test_ac56_predictions_for_t_match_eligibility_threshold_and_model(
    sql, peak_names, mlflow_registry
) -> None:
    champion = mlflow_registry.champion_version()
    threshold = mlflow_registry.threshold(champion)
    table = peak_names.predictions
    for day in (DEFAULT_DATE,):  # one scored date; the backfill is compared below
        predicted = sql.rows(
            f"SELECT household_id FROM {table} WHERE target_date = DATE'{day}' ORDER BY 1"
        )
        eligible = sql.rows(
            f"SELECT household_id FROM {peak_names.labels} "
            f"WHERE target_date = DATE'{day}' AND is_eligible ORDER BY 1"
        )
        assert predicted == eligible
    bad = sql.one(
        f"SELECT count_if(score < 0 OR score > 1) AS out_of_range, "
        f"count_if(model_version <> {champion}) AS other_version, "
        f"count_if(label <> CAST(score >= CAST('{threshold!r}' AS DOUBLE) AS INT)) AS bad_label "
        f"FROM {table} WHERE target_date = DATE'{DEFAULT_DATE}'"
    )
    assert bad == {"out_of_range": 0, "other_version": 0, "bad_label": 0}

    # after the backfill: the predictions of the test range equal the logged test scores
    run_id = mlflow_registry.client.get_model_version(peak_names.model, str(champion)).run_id
    logged = mlflow_registry.parquet(run_id, "test_scores.parquet")
    logged = logged.assign(
        target_date=pd.to_datetime(logged["target_date"]).dt.strftime("%Y-%m-%d")
    )
    stored = pd.DataFrame(
        sql.rows(
            f"SELECT household_id, CAST(target_date AS STRING) AS target_date, score "
            f"FROM {table} WHERE model_version = {champion} "
            f"AND target_date BETWEEN DATE'{TEST_START}' AND DATE'{TEST_END}'"
        )
    )
    assert len(stored) > 0, "run the backfill first (test_ac59, runbook order)"
    both = logged.merge(stored, on=["household_id", "target_date"], suffixes=("_logged", "_stored"))
    assert len(both) == len(logged)  # every logged test row has a prediction
    assert float(np.max(np.abs(both["score_logged"] - both["score_stored"]))) == 0.0


# ----------------------------------------------------------------------------- AC-57
def test_ac57_before_rescore_snapshot(sql, peak_names, evidence) -> None:
    table = peak_names.predictions
    evidence.save(
        "ac57_before_rescore",
        {
            "without_scored_at": _per_date(sql, table, PREDICTION_COLUMNS),
            "with_scored_at": _per_date(sql, table, ALL_COLUMNS),
            "scored_at": _scored_at(sql, table, DEFAULT_DATE),
        },
    )


def test_ac57_after_rescore_only_scored_at_changes(
    sql, peak_names, peak_job, peak_runner, evidence
) -> None:
    before = evidence.load("ac57_before_rescore", "test_ac57_before_rescore_snapshot")
    peak_runner.run(peak_job, params={"target_date": DEFAULT_DATE}, only=["score_predictions"])
    table = peak_names.predictions
    without = _per_date(sql, table, PREDICTION_COLUMNS)
    assert without == {k: tuple(v) for k, v in before["without_scored_at"].items()}
    assert _scored_at(sql, table, DEFAULT_DATE) > before["scored_at"]
    with_scored = _per_date(sql, table, ALL_COLUMNS)
    others = {d for d in with_scored if d != DEFAULT_DATE}
    saved = {k: tuple(v) for k, v in before["with_scored_at"].items()}
    assert others == {d for d in saved if d != DEFAULT_DATE}
    assert all(with_scored[d] == saved[d] for d in others)  # every other date is untouched
    assert with_scored[DEFAULT_DATE] != saved[DEFAULT_DATE]  # only _scored_at differs


# ----------------------------------------------------------------------------- AC-60
def test_ac60_target_beyond_features_fails_and_writes_nothing(
    settings, contracts, checksum, peak_job, peak_runner
) -> None:
    stem = "gold_consumption_spike_predictions"
    columns = [name for name, _ in contracts.columns(stem)]
    table = contracts.table(stem, settings)
    before = checksum(table, columns)
    run = peak_runner.run(
        peak_job,
        params={"target_date": BEYOND_DATE},
        only=["score_predictions"],
        expect="FAILED",
    )
    assert BEYOND_FEATURE_DATE in run.errors["score_predictions"]
    assert checksum(table, columns) == before
