"""Scoring on local Spark with a fake scorer, registry and writer (AC-56 to AC-61)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from pyspark.sql import functions as F
from support import peak_builders as pb

from smart_meter_peak_prediction import registry, scoring
from smart_meter_peak_prediction.peak_config import PeakParameters
from smart_meter_peak_prediction.registry import Champion

MODEL = "smart_meter_dev.ml.consumption_spike_model"
LAST = date(2014, 2, 28)
THRESHOLD = 0.5
SCORES = {"A": 0.9, "B": 0.5, "C": 0.1, "D": 0.7}  # B sits exactly on the threshold


class Recorder:
    """Writer that records what it receives; ``calls`` stays empty when a run fails."""

    def __init__(self):
        self.calls: list[tuple[str, list[dict]]] = []

    def __call__(self, predictions, predicate: str) -> None:
        self.calls.append((predicate, [r.asDict() for r in predictions.collect()]))


def fake_scorer(overrides=None, duplicate=False):
    scores = SCORES | (overrides or {})
    seen: list[str] = []

    def score(model_uri: str, df):
        seen.append(model_uri)
        mapping = F.create_map(*[x for k, v in scores.items() for x in (F.lit(k), F.lit(v))])
        scored = df.withColumn("prediction", mapping[F.col("household_id")])
        return scored.union(scored.limit(1)) if duplicate else scored

    score.seen = seen
    return score


@pytest.fixture
def tables(spark):
    """Gold up to 2014-02-28 (incomplete), labels and features for four households."""
    ids = ["A", "B", "C", "D"]
    daily = [
        pb.daily_row(hid, d, 10.0, complete=d != LAST)
        for hid in ids
        for d in (LAST - timedelta(days=2), LAST - timedelta(days=1), LAST)
    ]
    label_dates = [LAST - timedelta(days=i) for i in range(-1, 6)]  # up to 2014-03-01
    eligible = {"A": True, "B": True, "C": False, "D": True}
    labels = [
        (hid, d, eligible[hid] and not (hid == "D" and d == LAST))
        for hid in ids
        for d in label_dates
    ]
    feature_dates = [LAST - timedelta(days=i) for i in range(0, 8)]  # up to 2014-02-28
    feats = [(hid, d) for hid in ids for d in feature_dates]
    return SimpleNamespace(
        daily=pb.daily_frame(spark, daily),
        labels=spark.createDataFrame(
            labels, "household_id string, target_date date, is_eligible boolean"
        ),
        features=spark.createDataFrame(feats, "household_id string, feature_date date"),
        households=pb.household_frame(spark, [pb.household_row(hid) for hid in ids]),
    )


def run(tables, params=None, *, champion=None, scorer=None, writer=None, scored_at=None):
    writer = writer if writer is not None else Recorder()
    result = scoring.run(
        daily=tables.daily,
        labels=tables.labels,
        features=tables.features,
        households=tables.households,
        params=params or PeakParameters(),
        champion=champion or (lambda: Champion(version=7, threshold=THRESHOLD)),
        model_name=MODEL,
        scorer=scorer or fake_scorer(),
        writer=writer,
        scored_at=scored_at or datetime(2026, 10, 21, 8, 0, tzinfo=UTC),
    )
    return result, writer


# ----------------------------------------------------------------------------- AC-56
def test_ac56_predictions_cover_exactly_eligible_households_with_label_rule(tables) -> None:
    scorer = fake_scorer()
    result, writer = run(tables, scorer=scorer)

    ((predicate, rows),) = writer.calls
    by_household = {r["household_id"]: r for r in rows}
    assert set(by_household) == {"A", "B"}  # C ineligible, D ineligible on this date
    assert all(r["target_date"] == LAST for r in rows)
    assert by_household["A"]["label"] == 1
    assert by_household["B"]["label"] == 1  # score == t flags
    assert by_household["B"]["score"] == THRESHOLD
    assert {r["model_version"] for r in rows} == {7}
    assert all(0 <= r["score"] <= 1 for r in rows)
    assert scorer.seen == [f"models:/{MODEL}/7"]
    assert result.rows == 2
    assert result.summary()["decision_threshold"] == THRESHOLD
    assert [(f, t) for f, t in scoring.PREDICTION_COLUMNS.items()] == [
        ("household_id", "string"), ("target_date", "date"), ("score", "double"),
        ("label", "int"), ("model_version", "int"), ("_scored_at", "timestamp"),
    ]  # fmt: skip


def test_ac56_label_is_zero_below_the_threshold(tables) -> None:
    _, writer = run(tables, scorer=fake_scorer({"A": 0.4999999999999999}))
    by_household = {r["household_id"]: r["label"] for r in writer.calls[0][1]}
    assert by_household == {"A": 0, "B": 1}


def test_ac56_qr20_fails_on_a_duplicate_and_on_a_score_of_1_2(tables) -> None:
    for scorer in (fake_scorer(duplicate=True), fake_scorer({"A": 1.2}), fake_scorer({"A": None})):
        writer = Recorder()
        with pytest.raises(scoring.ScoringError, match="QR-20"):
            run(tables, scorer=scorer, writer=writer)
        assert writer.calls == []


# ----------------------------------------------------------------------------- AC-57
def test_ac57_reassembly_is_identical_except_scored_at(tables) -> None:
    first = run(tables, scored_at=datetime(2026, 10, 21, 8, 0, tzinfo=UTC))[1].calls[0]
    second = run(tables, scored_at=datetime(2026, 10, 22, 8, 0, tzinfo=UTC))[1].calls[0]

    def strip(rows):
        return sorted(({k: v for k, v in r.items() if k != "_scored_at"} for r in rows),
                      key=lambda r: r["household_id"])  # fmt: skip

    assert strip(first[1]) == strip(second[1])
    assert {r["_scored_at"] for r in first[1]} != {r["_scored_at"] for r in second[1]}
    assert len({r["_scored_at"] for r in first[1]}) == 1  # one timestamp per run
    assert (
        first[0]
        == second[0]
        == ("`target_date` >= DATE'2014-02-28' AND `target_date` <= DATE'2014-02-28'")
    )


# ----------------------------------------------------------------------------- AC-58
def test_ac58_default_target_date_is_day_after_latest_complete_day(tables) -> None:
    assert scoring.latest_complete_day(tables.daily) == date(2014, 2, 27)
    assert scoring.resolve_target_dates(tables.daily, PeakParameters()) == [LAST]
    result, _ = run(tables)
    summary = result.summary()
    assert summary["target_dates"] == ["2014-02-28"]
    assert summary["feature_dates"] == ["2014-02-27"]


# ----------------------------------------------------------------------------- AC-59
def test_ac59_range_resolves_to_89_dates(tables) -> None:
    params = PeakParameters(target_date=date(2013, 12, 1), target_date_end=date(2014, 2, 27))
    dates = scoring.resolve_target_dates(tables.daily, params)
    assert len(dates) == 89
    assert dates[0] == date(2013, 12, 1)
    assert dates[-1] == date(2014, 2, 27)
    with pytest.raises(ValueError, match="target_date_end must not be before target_date"):
        PeakParameters(target_date=date(2014, 2, 27), target_date_end=date(2014, 2, 26))
    assert scoring.resolve_target_dates(
        tables.daily, PeakParameters(target_date=date(2014, 2, 20))
    ) == [date(2014, 2, 20)]


# ----------------------------------------------------------------------------- AC-60
def test_ac60_missing_feature_date_fails_before_write(tables) -> None:
    writer = Recorder()
    with pytest.raises(scoring.ScoringError, match="2014-03-04"):
        run(tables, PeakParameters(target_date=date(2014, 3, 5)), writer=writer)
    assert writer.calls == []


def test_ac60_a_household_missing_from_the_feature_date_fails_before_write(tables, spark) -> None:
    thin = tables.features.where("NOT (household_id = 'B' AND feature_date = DATE'2014-02-27')")
    writer = Recorder()
    with pytest.raises(scoring.ScoringError, match=r"G-06.*2014-02-27"):
        run(SimpleNamespace(**(vars(tables) | {"features": thin})), writer=writer)
    assert writer.calls == []


def test_ac60_missing_label_rows_fail_before_write(tables) -> None:
    sparse = tables.labels.where("target_date <> DATE'2014-02-28'")
    writer = Recorder()
    with pytest.raises(scoring.ScoringError, match=r"labels table.*2014-02-28"):
        run(SimpleNamespace(**(vars(tables) | {"labels": sparse})), writer=writer)
    assert writer.calls == []


# ----------------------------------------------------------------------------- AC-61
class FakeRegistryClient:
    def __init__(self, aliases: dict[str, dict]):
        self.aliases = aliases

    def get_model_version_by_alias(self, name, alias):
        if alias not in self.aliases:
            raise LookupError(f"alias {alias} not found")
        return SimpleNamespace(**self.aliases[alias])


def test_ac61_missing_champion_alias_fails_before_write(tables) -> None:
    client = FakeRegistryClient({"challenger": {"version": "3", "tags": {}}})
    writer = Recorder()
    with pytest.raises(registry.ChampionError, match="alias 'champion'"):
        run(tables, champion=lambda: registry.resolve_champion(client, MODEL), writer=writer)
    assert writer.calls == []


def test_ac61_champion_without_a_threshold_tag_fails_before_write(tables) -> None:
    for tags in ({}, {"decision_threshold": "not-a-number"}):
        client = FakeRegistryClient({"champion": {"version": "3", "tags": tags}})
        writer = Recorder()
        with pytest.raises(registry.ChampionError, match="decision_threshold"):
            run(
                tables, champion=lambda c=client: registry.resolve_champion(c, MODEL), writer=writer
            )
        assert writer.calls == []


def test_ac61_champion_resolves_version_and_exact_threshold(tables) -> None:
    client = FakeRegistryClient(
        {"champion": {"version": "3", "tags": {"decision_threshold": "0.5"}}}
    )
    resolved = registry.resolve_champion(client, MODEL)
    assert resolved == Champion(version=3, threshold=0.5)
    tag = repr(0.123456789012345678)
    exact = registry.resolve_champion(
        FakeRegistryClient({"champion": {"version": "4", "tags": {"decision_threshold": tag}}}),
        MODEL,
    )
    assert exact.threshold == 0.123456789012345678
