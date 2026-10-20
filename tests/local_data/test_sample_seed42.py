"""Local-data tests (marker ``local_data``): the src port reproduces the pinned seed-42 sample.

Run with the Kaggle files in ``data/raw``:  pytest -m local_data
Expected values come from ``config/sample_households.csv`` and ``config/sample_manifest.json``,
never from the spike code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from smart_meter_peak_prediction import sampling

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PINNED_HOUSEHOLDS = ROOT / "config" / "sample_households.csv"
PINNED_MANIFEST = ROOT / "config" / "sample_manifest.json"


@pytest.fixture(scope="module")
def plan() -> dict:
    return sampling.load_plan(ROOT / "config" / "sample_plan.json")


@pytest.fixture(scope="module")
def pinned() -> dict:
    return json.loads(PINNED_MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run1(tmp_path_factory, plan) -> tuple[Path, dict]:
    assert RAW.is_dir(), "data/raw is required for local_data tests"
    out = tmp_path_factory.mktemp("seed42_run1")
    return out, sampling.build_sample(RAW, plan, out)


def test_ac01_seed42_reruns_are_byte_identical(tmp_path_factory, plan, run1, pinned):
    out1, _ = run1
    out2 = tmp_path_factory.mktemp("seed42_run2")
    sampling.build_sample(RAW, plan, out2)
    names = sorted(p.relative_to(out1).as_posix() for p in out1.rglob("*") if p.is_file())
    assert names == sorted(p.relative_to(out2).as_posix() for p in out2.rglob("*") if p.is_file())
    for name in names:
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name
    for kind in ("historical", "stream"):
        for fname, stats in pinned["files"][kind].items():
            assert sampling.sha256(out1 / kind / fname) == stats["sha256"], fname


def test_ac01_plan_recomputed_from_raw_equals_committed_plan(plan):
    assert sampling.check_plan(RAW, plan) == plan["blocks"]
    spike_plan = json.loads((ROOT / "spikes/local/plan.json").read_text(encoding="utf-8"))
    assert spike_plan["groups"] == plan["blocks"]  # drift guard against the frozen copy


def test_ac02_src_sampling_selects_exactly_the_pinned_households(run1, pinned):
    out, manifest = run1
    pinned_hh = (
        pd.read_csv(PINNED_HOUSEHOLDS, dtype=str).sort_values("LCLid").reset_index(drop=True)
    )
    built = (
        pd.read_csv(out / "dimensions" / "households_sample.csv", dtype=str)
        .sort_values("LCLid")
        .reset_index(drop=True)
    )
    assert built.equals(pinned_hh)  # same ids and attributes
    assert len(built) == 60
    assert built["Acorn_grouped"].value_counts().to_dict() == {
        "Affluent": 20,
        "Comfortable": 20,
        "Adversity": 20,
    }
    assert built["stdorToU"].value_counts().to_dict() == {"Std": 48, "ToU": 12}
    for _, part in built.groupby("Acorn_grouped"):
        assert part["stdorToU"].value_counts().to_dict() == {"Std": 16, "ToU": 4}
    assert not built["Acorn"].isin(["ACORN-U", "ACORN-"]).any()
    assert not built["Acorn_grouped"].isin(["ACORN-U", "ACORN-"]).any()
    excluded = manifest["households"]["excluded"]
    assert excluded == pinned["households"]["excluded"]
    assert all(e["reason"] for e in excluded)
    assert not {e["LCLid"] for e in excluded} & set(built["LCLid"])


def test_ac02_src_sampling_counts_match_pinned_manifest(run1, pinned):
    _, manifest = run1
    assert manifest["counts"] == pinned["counts"]
    for key in ("seed", "period", "cutoff", "rules", "quality_thresholds"):
        assert manifest[key] == pinned[key]
    for key in ("selected", "by_group", "by_tariff", "by_block"):
        assert manifest["households"][key] == pinned["households"][key]
    for kind in ("historical", "stream"):
        assert manifest["files"][kind] == pinned["files"][kind]
    per_household = manifest["households"]["per_household"]
    assert len(per_household) == 60
    for stats in per_household.values():
        assert stats["selection_coverage"] >= pinned["quality_thresholds"]["min_coverage"]
        assert stats["zero_share"] < pinned["quality_thresholds"]["max_zero_ratio"]
        assert 0 < stats["coverage_study_period"] <= 1


def test_ac03_seed42_split_counts_match_pinned_manifest(run1, pinned):
    out, manifest = run1
    assert manifest["counts"]["historical_rows"] == 1_432_405
    assert manifest["counts"]["stream_rows"] == 247_569
    for kind in ("historical", "stream"):
        for fname, stats in pinned["files"][kind].items():
            assert manifest["files"][kind][fname] == stats
            assert sampling.sha256(out / kind / fname) == stats["sha256"]
    assert sum(s["rows"] for s in pinned["files"]["historical"].values()) == 1_432_405


def test_ac04_seed42_cutoff_2013_11_01_preserves_total(tmp_path, plan, pinned):
    moved = sampling.apply_overrides(plan, ["cutoff=2013-11-01 00:00:00"])
    manifest = sampling.build_sample(RAW, moved, tmp_path)
    counts = manifest["counts"]
    assert counts["total_rows"] == pinned["counts"]["total_rows"]
    assert counts["historical_rows"] + counts["stream_rows"] == counts["total_rows"]
    expected_hist = sum(
        s["rows"] for name, s in pinned["files"]["historical"].items() if name < "readings_2013-11"
    )
    assert counts["historical_rows"] == expected_hist
    assert counts["stream_rows"] == pinned["counts"]["stream_rows"] + sum(
        s["rows"] for name, s in pinned["files"]["historical"].items() if name >= "readings_2013-11"
    )
