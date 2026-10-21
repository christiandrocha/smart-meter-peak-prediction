"""Training library and model wrapper on fixtures with a fake tracker (AC-48 to AC-54)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from smart_meter_peak_prediction import model, registry, training
from smart_meter_peak_prediction.peak_config import PeakParameters

LABELS_PROPERTIES = PeakParameters().label_properties()
FEATURE_PROPERTIES = PeakParameters().feature_properties()
GROUPS = {"H1": "Affluent", "H2": "Comfortable", "H3": "Adversity"}


# ----------------------------------------------------------------------------- fixtures
def label_table(seed: int = 7) -> pd.DataFrame:
    """Labels for 3 households over the full study range, with signal in the features."""
    rng = np.random.default_rng(seed)
    rows = []
    start = date(2012, 7, 29)
    for hid, group in GROUPS.items():
        base = rng.uniform(5, 15)
        for i in range(580):  # 2012-07-29 to 2014-02-27
            target = start + timedelta(days=i)
            ratio = rng.lognormal(0.0, 0.35)
            total = base * ratio
            rows.append(
                {
                    "household_id": hid,
                    "target_date": target,
                    "feature_date": target - timedelta(days=1),
                    "is_eligible": target >= date(2012, 10, 1),
                    "label_consumption_spike": int(rng.random() < 0.15 + 0.5 * (ratio > 1.3)),
                    "total_energy_kwh_1d": total,
                    "max_energy_kwh_1d": total / 10,
                    "avg_energy_kwh_7d": base * 1.02,
                    "avg_energy_kwh_28d": base,
                    "median_energy_kwh_same_weekday_8w": base,
                    "complete_day_share_28d": 1.0 if i % 11 else 27 / 28,
                    "target_weekday": target.isoweekday(),
                    "target_month": target.month,
                    "acorn_group": group,
                    "tariff": "Std" if hid != "H3" else "ToU",
                    "mean_temperature_c_1d": 8 + 6 * np.sin(i / 58) + rng.normal(),
                    "temperature_hour_count_1d": 24,
                }
            )
    return pd.DataFrame(rows)


def make_inputs(labels: pd.DataFrame | None = None, **overrides) -> training.TrainingInputs:
    labels = label_table() if labels is None else labels
    params = PeakParameters()
    rows = training.select_training_rows(labels, params)
    frame = rows[["household_id", "target_date", training.LABEL_COLUMN]].merge(
        labels[["household_id", "target_date", *model.FEATURE_COLUMNS]],
        on=["household_id", "target_date"],
    )
    keys = labels[["household_id", "feature_date"]]
    inputs = dict(
        frame=frame,
        feature_keys=keys,
        features_table=training.TableRef("smart_meter_dev.ml.household_features_daily", 12),
        labels_table=training.TableRef("smart_meter_dev.ml.household_labels_daily", 34),
        label_properties=LABELS_PROPERTIES,
        feature_properties=FEATURE_PROPERTIES,
        git_commit="a" * 40,
        library_versions={"scikit_learn": "1.3.0", "mlflow": "3.17.2", "python": "3.12"},
    )
    return training.TrainingInputs(**(inputs | overrides))


class FakeTracker:
    """Records every effect; ``registry`` stands for the model registry with its alias."""

    def __init__(self, registry_state: dict | None = None):
        self.calls: list[str] = []
        self.params: dict = {}
        self.metrics: dict = {}
        self.frames: dict[str, pd.DataFrame] = {}
        self.json: dict = {}
        self.registry = registry_state if registry_state is not None else {"champion": 1}

    @contextmanager
    def run(self):
        self.calls.append("run")
        yield "run-1"

    def log_params(self, params):
        self.calls.append("params")
        self.params |= params

    def log_metrics(self, metrics):
        self.calls.append("metrics")
        self.metrics |= metrics

    def log_frame(self, name, frame):
        self.calls.append("frame")
        self.frames[name] = frame

    def log_json(self, name, content):
        self.calls.append("json")
        self.json[name] = content

    def log_inputs(self, tables):
        self.calls.append("inputs")

    def register_model(self, wrapped, *, sample_input, expected_scores, threshold):
        self.calls.append("register")
        again = wrapped.predict(None, sample_input)
        assert np.array_equal(again, expected_scores)
        self.registry["champion"] = 2
        self.registry["threshold"] = threshold
        return training.RegisteredModel(version=2, reload_max_abs_diff=0.0)


@pytest.fixture(scope="module")
def completed():
    tracker = FakeTracker()
    result = training.run_training(make_inputs(), PeakParameters(), tracker)
    return tracker, result


# ----------------------------------------------------------------------------- AC-48
def test_ac48_splits_are_ordered_disjoint_and_equal_the_eligible_labelled_rows() -> None:
    labels = label_table()
    labels.loc[labels.sample(60, random_state=1).index, training.LABEL_COLUMN] = np.nan
    params = PeakParameters()

    rows = training.select_training_rows(labels, params)
    assigned = training.assign_splits(rows, params)

    ranges = params.split_ranges()
    expected = {
        (r.household_id, r.target_date)
        for r in labels.itertuples()
        if r.is_eligible
        and not pd.isna(getattr(r, training.LABEL_COLUMN))
        and any(lo <= r.target_date <= hi for lo, hi in ranges.values())
    }
    got = {(r.household_id, r.target_date.date()) for r in assigned.itertuples()}
    assert got == expected  # 0 extra and 0 missing
    assert len(assigned) == len(expected)

    bounds = {
        name: (g["target_date"].min().date(), g["target_date"].max().date())
        for name, g in assigned.groupby("split")
    }
    assert bounds["train"][1] < bounds["validation"][0]
    assert bounds["validation"][1] < bounds["test"][0]
    for name, (lo, hi) in bounds.items():
        assert ranges[name][0] <= lo <= hi <= ranges[name][1]
    assert assigned["target_date"].is_monotonic_increasing


def test_ac48_missing_feature_row_at_t_minus_1_fails_guard_g02() -> None:
    inputs = make_inputs()
    target = date(2013, 9, 10)
    keys = inputs.feature_keys
    gap = keys[~((keys["household_id"] == "H2") & (keys["feature_date"] == target - timedelta(1)))]
    with pytest.raises(training.GuardError, match="G-02"):
        training.run_training(make_inputs(feature_keys=gap), PeakParameters(), FakeTracker())

    nulled = inputs.frame.copy()
    nulled.loc[nulled.index[5], "complete_day_share_28d"] = np.nan
    with pytest.raises(training.GuardError, match="G-02.*complete_day_share_28d"):
        training.run_training(make_inputs(frame=nulled), PeakParameters(), FakeTracker())


def test_ac48_overlapping_or_unordered_ranges_fail_guard_g09() -> None:
    with pytest.raises(ValueError, match="G-09.*ordered and disjoint"):
        PeakParameters(validation_start=date(2013, 7, 31))
    with pytest.raises(ValueError, match="G-09"):
        PeakParameters(test_start=date(2013, 12, 1), test_end=date(2013, 11, 1))
    with pytest.raises(ValueError, match="G-09"):
        PeakParameters(label_threshold=0)
    with pytest.raises(ValueError, match="G-09"):
        PeakParameters(coverage_min=1.5)


def test_ac48_a_row_outside_the_ranges_is_rejected() -> None:
    inputs = make_inputs()
    stray = inputs.frame.copy()
    stray.loc[stray.index[0], "target_date"] = date(2014, 3, 1)
    with pytest.raises(training.GuardError, match="outside the three split ranges"):
        training.run_training(make_inputs(frame=stray), PeakParameters(), FakeTracker())


# ----------------------------------------------------------------------------- AC-49
def test_ac49_two_fits_give_identical_scores_threshold_and_metrics() -> None:
    inputs = make_inputs()
    shuffled = make_inputs(
        frame=inputs.frame.sample(frac=1.0, random_state=3).reset_index(drop=True)
    )
    first, second = FakeTracker(), FakeTracker()

    a = training.run_training(inputs, PeakParameters(), first)
    b = training.run_training(shuffled, PeakParameters(), second)

    test_a, test_b = a.scores["test"]["score"].to_numpy(), b.scores["test"]["score"].to_numpy()
    assert np.array_equal(test_a, test_b)  # bitwise
    assert float(np.max(np.abs(test_a - test_b))) == 0.0
    assert a.threshold.threshold == b.threshold.threshold
    assert first.metrics == second.metrics


# ----------------------------------------------------------------------------- AC-50
def test_ac50_run_parameters_cover_model_seed_and_fr31(completed) -> None:
    tracker, _ = completed
    p = tracker.params
    assert p["model_class"] == "HistGradientBoostingClassifier"
    assert p["random_state"] == "42"
    assert p["early_stopping"] == "False"
    for name in (
        "train_start", "train_end", "validation_start", "validation_end", "test_start",
        "test_end", "random_seed", "label_threshold", "baseline_day_count",
        "label_lookback_weeks", "coverage_min", "zero_share_max", "eligibility_months",
    ):  # fmt: skip
        assert name in p
    assert "target_date" not in p
    assert p["label_threshold"] == "1.3"
    assert p["train_start"] == "2012-07-29"
    assert p["git_commit"] == "a" * 40
    assert p["features_table_version"] == "12"
    assert p["labels_table_version"] == "34"
    assert p["threshold_rule"] == training.THRESHOLD_RULE
    assert p["feature_columns"].split(",") == model.FEATURE_COLUMNS
    assert p["scikit_learn"] == "1.3.0"


# ----------------------------------------------------------------------------- AC-51
def brute_force_threshold(y: list[int], s: list[float]) -> tuple[Fraction, float]:
    best = None
    for t in sorted(set(s)):
        tp = sum(1 for a, b in zip(y, s, strict=True) if b >= t and a == 1)
        fp = sum(1 for a, b in zip(y, s, strict=True) if b >= t and a == 0)
        fn = sum(1 for a, b in zip(y, s, strict=True) if b < t and a == 1)
        candidate = (Fraction(2 * tp, 2 * tp + fp + fn), t)
        if best is None or candidate >= best:  # the highest t wins a tie
            best = candidate
    return best


def test_ac51_threshold_is_max_f1_with_highest_t_on_ties() -> None:
    tie_labels, tie_scores = [1, 0, 1, 0, 0], [1.0, 0.0, 0.2, 0.8, 0.6]
    choice = training.choose_threshold(np.array(tie_labels), np.array(tie_scores))
    assert choice.threshold == 1.0  # F1 2/3 at t = 0.2 and at t = 1.0
    assert brute_force_threshold(tie_labels, tie_scores)[1] == 1.0

    single = training.choose_threshold(np.array([0, 1, 0, 0]), np.array([0.4, 0.9, 0.2, 0.3]))
    assert (single.threshold, single.f1) == (0.9, 1.0)

    rng = np.random.default_rng(11)
    for _ in range(400):
        n = int(rng.integers(2, 41))
        digits = int(rng.choice([1, 2, 6]))
        scores = [round(float(x), digits) for x in rng.random(n)]
        labels = [int(x) for x in rng.integers(0, 2, n)]
        if not sum(labels):
            continue
        want_f1, want_t = brute_force_threshold(labels, scores)
        got = training.choose_threshold(np.array(labels), np.array(scores))
        assert got.threshold == want_t
        assert abs(got.f1 - float(want_f1)) <= 1e-9


def test_ac51_run_threshold_equals_recomputation_from_validation_scores(completed) -> None:
    tracker, result = completed
    validation = result.scores["validation"]
    want_f1, want_t = brute_force_threshold(
        validation[training.LABEL_COLUMN].tolist(), validation["score"].tolist()
    )
    assert result.threshold.threshold == want_t
    assert tracker.metrics["validation_threshold"] == want_t
    assert abs(tracker.metrics["validation_f1_at_t"] - float(want_f1)) <= 1e-9
    assert tracker.registry["threshold"] == want_t


def test_ac51_no_positive_validation_row_fails_before_any_effect() -> None:
    inputs = make_inputs()
    flat = inputs.frame.copy()
    in_validation = (flat["target_date"] >= pd.Timestamp("2013-08-01").date()) & (
        flat["target_date"] <= pd.Timestamp("2013-11-30").date()
    )
    flat.loc[in_validation, training.LABEL_COLUMN] = 0
    tracker = FakeTracker()
    with pytest.raises(training.GuardError, match="G-11"):
        training.run_training(make_inputs(frame=flat), PeakParameters(), tracker)
    assert tracker.calls == []


# ----------------------------------------------------------------------------- AC-52
def test_ac52_metric_names_cover_segments_with_counts_and_no_accuracy(completed) -> None:
    tracker, _ = completed
    metrics = tracker.metrics
    months = {
        "validation": ["2013_08", "2013_09", "2013_10", "2013_11"],
        "test": ["2013_12", "2014_01", "2014_02"],
    }
    for split, split_months in months.items():
        prefixes = [split]
        prefixes += [f"{split}_acorn_{g.lower()}" for g in GROUPS.values()]
        prefixes += [f"{split}_month_{m}" for m in split_months]
        for prefix in prefixes:
            for name in ("precision_at_t", "recall_at_t", "flag_count_at_t", "row_count"):
                assert f"{prefix}_{name}" in metrics, f"{prefix}_{name}"
            assert metrics[f"{prefix}_positive_count"] >= 0
            if metrics[f"{prefix}_positive_count"] > 0:
                assert f"{prefix}_pr_auc" in metrics
        assert f"{split}_ratio_rule_pr_auc" in metrics
    assert not [name for name in metrics if "accuracy" in name]
    assert "validation_threshold" in metrics
    assert "validation_f1_at_t" in metrics
    assert metrics["champion_reload_max_abs_diff"] == 0.0
    assert metrics["test_row_count"] == sum(
        metrics[f"test_acorn_{g.lower()}_row_count"] for g in GROUPS.values()
    )


def test_ac52_segment_without_positives_logs_no_pr_auc_and_precision_is_zero_without_flags() -> (
    None
):
    metrics = training.segment_metrics("s", np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3]), 0.9)
    assert "s_pr_auc" not in metrics
    assert metrics["s_precision_at_t"] == 0.0
    assert metrics["s_flag_count_at_t"] == 0.0
    assert metrics["s_row_count"] == 3.0


def test_ac52_ratio_rule_scores_null_total_as_zero_and_zero_baseline_as_1e_minus_6() -> None:
    frame = pd.DataFrame(
        {
            "total_energy_kwh_1d": [10.0, None, 3.0],
            "median_energy_kwh_same_weekday_8w": [5.0, 5.0, 0.0],
        }
    )
    assert training.ratio_rule_scores(frame).tolist() == [2.0, 0.0, 3.0 / 1e-6]


# ----------------------------------------------------------------------------- AC-53
def test_ac53_empty_validation_month_fails_before_any_metric_or_registration() -> None:
    labels = label_table()
    in_september = (labels["target_date"] >= date(2013, 9, 1)) & (
        labels["target_date"] <= date(2013, 9, 30)
    )
    labels.loc[in_september, "is_eligible"] = False
    tracker = FakeTracker({"champion": 1})

    with pytest.raises(training.GuardError, match="2013-09"):
        training.run_training(make_inputs(labels), PeakParameters(), tracker)

    assert tracker.calls == []  # no run, metric, logged model, tag or alias call
    assert tracker.registry == {"champion": 1}


def test_ac53_a_commit_less_run_or_mismatched_parameters_fail_before_any_effect() -> None:
    tracker = FakeTracker()
    with pytest.raises(training.GuardError, match="G-05"):
        training.run_training(make_inputs(git_commit=" "), PeakParameters(), tracker)
    other = dict(FEATURE_PROPERTIES, **{"smart_meter.baseline_day_count": "3"})
    with pytest.raises(training.GuardError, match="baseline_day_count"):
        training.run_training(make_inputs(feature_properties=other), PeakParameters(), tracker)
    assert tracker.calls == []


# ----------------------------------------------------------------------------- AC-54
def test_ac54_pyfunc_wrapper_round_trip_reproduces_scores(completed, tmp_path) -> None:
    import mlflow.pyfunc
    from mlflow.models import infer_signature

    _, result = completed
    labels = label_table()
    rows = make_inputs(labels).frame
    test_rows = rows[rows["target_date"] >= date(2013, 12, 1)][model.FEATURE_COLUMNS]
    classifier = model.build_classifier(42)
    train = rows[rows["target_date"] <= date(2013, 7, 31)]
    classifier.fit(model.encode(train), train[training.LABEL_COLUMN].astype(int))
    wrapped = model.ConsumptionSpikeModel(classifier)
    expected = wrapped.predict(None, test_rows)

    signature = infer_signature(test_rows, expected)
    path = tmp_path / "model"
    mlflow.pyfunc.save_model(
        str(path),
        python_model=wrapped,
        signature=signature,
        code_paths=[str(registry.PACKAGE_DIR)],
    )
    loaded = mlflow.pyfunc.load_model(str(path))

    again = np.asarray(loaded.predict(test_rows), dtype="float64")
    assert np.array_equal(again, expected)  # max abs difference 0
    assert [c.name for c in loaded.metadata.signature.inputs] == model.FEATURE_COLUMNS
    assert result.scores["test"]["score"].between(0, 1).all()


def test_ac54_encoding_uses_fixed_codes_and_unknown_values_become_nan() -> None:
    frame = pd.DataFrame(
        {
            **dict.fromkeys(model.FEATURE_COLUMNS, 1.0),
            "acorn_group": ["Affluent", "Adversity", "Other", None],
            "tariff": ["Std", "ToU", "ToU", "Std"],
            "target_weekday": [1, 7, 8, None],
            "target_month": [1, 12, 13, 0],
        }
    )
    encoded = model.encode(frame)
    column = model.FEATURE_COLUMNS.index
    assert encoded[:, column("acorn_group")].tolist()[:2] == [0.0, 2.0]
    assert np.isnan(encoded[2:, column("acorn_group")]).all()
    assert encoded[:2, column("target_weekday")].tolist() == [0.0, 6.0]
    assert np.isnan(encoded[2:, column("target_weekday")]).all()
    assert encoded[:2, column("target_month")].tolist() == [0.0, 11.0]
    assert np.isnan(encoded[2:, column("target_month")]).all()
    assert model.CATEGORICAL_MASK.count(True) == 4
    with pytest.raises(ValueError, match="lacks feature column"):
        model.encode(frame.drop(columns=["tariff"]))


class FakeFe:
    def __init__(self, log):
        self.log = log

    def log_model(self, **kwargs):
        self.log.append(("log_model", sorted(kwargs)))


class FakeClient:
    def __init__(self, log):
        self.log = log

    def search_model_versions(self, query):
        # Like the UC registry: only `name = '...'` is accepted (PR 2 gate, D-20).
        if query != "name = 'c.ml.m'":
            raise ValueError(f"INVALID_PARAMETER_VALUE: Unsupported filter query : `{query}`")
        return [
            SimpleNamespace(version="2", run_id="run-earlier"),
            SimpleNamespace(version="3", run_id="run-this"),
            SimpleNamespace(version="4", run_id="run-other"),
        ]

    def set_model_version_tag(self, name, version, key, value):
        self.log.append(("tag", version, key, value))

    def set_registered_model_alias(self, name, alias, version):
        self.log.append(("alias", alias, version))


def fake_tracker(log, reload_offset: float):
    class Loaded:
        def predict(self, frame):
            return np.full(len(frame), 0.25) + reload_offset

    pyfunc = SimpleNamespace(load_model=lambda uri: (log.append(("load", uri)), Loaded())[1])
    tracker = registry.MlflowTracker(
        mlflow=SimpleNamespace(pyfunc=pyfunc),
        client=FakeClient(log),
        fe=FakeFe(log),
        training_set=object(),
        model_name="c.ml.m",
    )
    tracker._run_id = "run-this"
    return tracker


def test_ac54_register_logs_reloads_then_tags_then_moves_the_alias() -> None:
    log: list = []
    frame = make_inputs().frame[model.FEATURE_COLUMNS].head(5)
    registered = fake_tracker(log, 0.0).register_model(
        None, sample_input=frame, expected_scores=np.full(5, 0.25), threshold=0.4321
    )
    assert registered.version == 3
    assert registered.reload_max_abs_diff == 0.0
    assert [entry[0] for entry in log] == ["log_model", "load", "tag", "alias"]
    assert log[1] == ("load", "models:/c.ml.m/3")
    assert log[2] == ("tag", "3", "decision_threshold", "0.4321")
    assert log[3] == ("alias", "champion", 3)
    assert {"code_paths", "signature", "training_set"} <= set(log[0][1])


def test_ac54_register_finds_the_version_of_this_run_with_a_name_only_filter() -> None:
    """The UC registry rejects `run_id` in the filter; a newer version of another run is skipped."""
    log: list = []
    frame = make_inputs().frame[model.FEATURE_COLUMNS].head(5)
    tracker = fake_tracker(log, 0.0)
    assert (
        tracker.register_model(
            None, sample_input=frame, expected_scores=np.full(5, 0.25), threshold=0.5
        ).version
        == 3
    )
    tracker._run_id = "run-without-version"
    with pytest.raises(RuntimeError, match="no version"):
        tracker.register_model(
            None, sample_input=frame, expected_scores=np.full(5, 0.25), threshold=0.5
        )


def test_ac54_reload_uses_the_registered_signature_with_the_fe_lookup_keys() -> None:
    """``fe.log_model`` adds household_id and target_date to the signature (PR 2 gate, D-22)."""
    seen: list = []
    names = ["household_id", "target_date", *model.FEATURE_COLUMNS]

    class Loaded:
        metadata = SimpleNamespace(
            get_input_schema=lambda: SimpleNamespace(input_names=lambda: names)
        )

        def predict(self, frame):
            seen.append(frame)
            return np.full(len(frame), 0.25)

    log: list = []
    tracker = fake_tracker(log, 0.0)
    tracker.mlflow = SimpleNamespace(pyfunc=SimpleNamespace(load_model=lambda uri: Loaded()))
    frame = make_inputs().frame[["household_id", "target_date", *model.FEATURE_COLUMNS]].head(5)
    tracker.register_model(
        None, sample_input=frame, expected_scores=np.full(5, 0.25), threshold=0.5
    )
    (passed,) = seen
    assert list(passed.columns) == names
    assert pd.api.types.is_datetime64_any_dtype(passed["target_date"])
    with pytest.raises(KeyError):
        registry.reload_input(Loaded(), frame[model.FEATURE_COLUMNS])


def test_ac54_reload_mismatch_stops_before_the_tag_and_the_alias() -> None:
    log: list = []
    frame = make_inputs().frame[model.FEATURE_COLUMNS].head(5)
    with pytest.raises(registry.ReloadMismatchError, match="G-08"):
        fake_tracker(log, 1e-12).register_model(
            None, sample_input=frame, expected_scores=np.full(5, 0.25), threshold=0.5
        )
    assert [entry[0] for entry in log] == ["log_model", "load"]


# ----------------------------------------------------------------------------- AC-48 wiring
class _FakeHistory:
    def __init__(self, versions: list[int]):
        self._versions = versions

    def first(self) -> dict:
        return {"version": self._versions.pop(0)}


class _SparkWithVersions:
    """Real local Spark for ``createDataFrame``; ``DESCRIBE HISTORY`` answers from a list."""

    def __init__(self, spark, versions: list[int]):
        self._spark = spark
        self._versions = versions

    def sql(self, statement: str) -> _FakeHistory:
        assert statement.startswith("DESCRIBE HISTORY c.ml.features")
        return _FakeHistory(self._versions)

    def createDataFrame(self, data):  # noqa: N802  (Spark API name)
        return self._spark.createDataFrame(data)


def _fake_feature_engineering(monkeypatch: pytest.MonkeyPatch, seen: dict):
    """Stand-in for ``databricks.feature_engineering`` (installed on the platform only)."""
    import sys
    import types

    class FeatureLookup:
        def __init__(self, **kwargs):
            seen["lookup"] = kwargs

    package = types.ModuleType("databricks")
    module = types.ModuleType("databricks.feature_engineering")
    module.FeatureLookup = FeatureLookup
    package.feature_engineering = module
    monkeypatch.setitem(sys.modules, "databricks", package)
    monkeypatch.setitem(sys.modules, "databricks.feature_engineering", module)

    class TrainingSet:
        def load_df(self):
            return seen["df"]

    class Fe:
        def create_training_set(self, **kwargs):
            seen["call"] = kwargs
            seen["df"] = kwargs["df"]
            return TrainingSet()

    return Fe()


def test_ac48_training_set_lookup_uses_date_keys_the_spike_shape_and_guard_g04(
    spark, monkeypatch
) -> None:
    """The lookup keys are DATE (not timestamp), the shape is spike 05's, and G-04 is enforced."""
    seen: dict = {}
    fe = _fake_feature_engineering(monkeypatch, seen)
    rows = pd.DataFrame(
        {
            "household_id": ["H1", "H2"],
            "target_date": pd.to_datetime(["2013-08-02", "2013-08-03"]),  # pandas timestamps
            "feature_date": pd.to_datetime(["2013-08-01", "2013-08-02"]),
            "label_consumption_spike": [0, 1],
        }
    )
    training_set, frame, version = registry.build_training_set(
        fe, _SparkWithVersions(spark, [7, 7]), rows, "c.ml.features", model.FEATURE_COLUMNS
    )
    assert version == 7
    assert dict(seen["df"].dtypes) == {
        "household_id": "string",
        "target_date": "date",
        "lookup_date": "date",
        "label_consumption_spike": "bigint",
    }
    assert seen["lookup"] == {
        "table_name": "c.ml.features",
        "lookup_key": "household_id",
        "timestamp_lookup_key": "lookup_date",
        "feature_names": list(model.FEATURE_COLUMNS),
    }
    assert seen["call"]["label"] == "label_consumption_spike"
    assert seen["call"]["exclude_columns"] == ["lookup_date"]
    assert len(frame) == 2
    assert training_set is not None
    with pytest.raises(training.GuardError, match=r"G-04.*version 7 to 8"):
        registry.build_training_set(
            fe, _SparkWithVersions(spark, [7, 8]), rows, "c.ml.features", model.FEATURE_COLUMNS
        )
