"""Unit tests for the sampling port (AC-01 to AC-04) on a synthetic raw dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import prepare_sample
import pytest

from smart_meter_peak_prediction import sampling

PERIOD_START = "2013-01-01 00:00:00"
PERIOD_END = "2013-01-03 00:00:00"  # 97 half-hour slots
CUTOFF = "2013-01-02 00:00:00"
SLOTS = pd.date_range(PERIOD_START, PERIOD_END, freq="30min")
GROUPS = {"Affluent": "block_1", "Comfortable": "block_2", "Adversity": "block_3"}


def _fmt(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S") + ".0000000"


def _readings(lcl: str, slots, energy: str) -> list[str]:
    return [f"{lcl},{_fmt(ts)},{energy}" for ts in slots]


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    """Three blocks of eight households each (6 Std, 2 ToU => population ToU share 0.25).

    Per group: h1..h3 and h7, h8 valid, h4 a dead meter, h5 low coverage, h6 no readings in
    the period. One ACORN-U household sits outside the groups. Quotas: 3 Std and 1 ToU.
    """
    raw = tmp_path / "raw"
    bdir = raw / "halfhourly_dataset" / "halfhourly_dataset"
    bdir.mkdir(parents=True)
    info = ["LCLid,stdorToU,Acorn,Acorn_grouped,file"]
    for g, (group, block) in enumerate(GROUPS.items(), start=1):
        lines = ["LCLid,tstp,energy(kWh/hh)"]
        for n in range(1, 9):
            lcl = f"MAC{g}{n:05d}"
            tariff = "ToU" if n >= 7 else "Std"
            info.append(f"{lcl},{tariff},ACORN-{'ABC'[g - 1]},{group},{block}")
            if n == 4:
                lines += _readings(lcl, SLOTS, " 0 ")
            elif n == 5:
                lines += _readings(lcl, SLOTS[:20], " 0.3 ")
            elif n == 6:
                lines += _readings(lcl, [pd.Timestamp("2012-12-31 00:00:00")], " 0.3 ")
            else:
                lines += _readings(lcl, SLOTS, " 0.5 ")
                lines.append(f"{lcl},2012-12-31 23:30:00.0000000, 0.5 ")  # before the period
        lines.append(f"MAC{g}00001,2013-01-01 00:07:00.0000000,Null")  # off-grid and non-numeric
        (bdir / f"{block}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    info.append("MAC900001,Std,ACORN-U,ACORN-U,block_1")
    (raw / "informations_households.csv").write_text("\n".join(info) + "\n", encoding="utf-8")
    return raw


@pytest.fixture
def plan() -> dict:
    return {
        "seed": 42,
        "blocks_per_group": 1,
        "households_per_group": 4,
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "cutoff": CUTOFF,
        "max_zero_ratio": 0.9,
        "min_coverage": 0.8,
        "blocks": {group: [block] for group, block in GROUPS.items()},
    }


@pytest.fixture
def plan_file(tmp_path: Path, plan: dict) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _checksums(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_ac01_same_plan_produces_identical_checksums(raw_dir, plan, tmp_path):
    sampling.build_sample(raw_dir, plan, tmp_path / "run1")
    sampling.build_sample(raw_dir, plan, tmp_path / "run2")
    first, second = _checksums(tmp_path / "run1"), _checksums(tmp_path / "run2")
    assert first == second
    assert "manifest.json" in first
    assert "stream/readings_stream.csv" in first
    assert any(name.startswith("historical/readings_2013-01") for name in first)


def test_ac01_outputs_use_source_header_and_unix_line_endings(raw_dir, plan, tmp_path):
    sampling.build_sample(raw_dir, plan, tmp_path / "out")
    stream = (tmp_path / "out/stream/readings_stream.csv").read_bytes()
    assert stream.startswith(b"LCLid,tstp,energy(kWh/hh)\n")
    assert b"\r" not in stream
    households = (tmp_path / "out/dimensions/households_sample.csv").read_bytes()
    assert households.startswith(b"LCLid,stdorToU,Acorn,Acorn_grouped,file\n")
    manifest_text = (tmp_path / "out/manifest.json").read_text()
    assert json.loads(manifest_text)
    assert list(json.loads(manifest_text)) == sorted(json.loads(manifest_text))


def test_ac02_selection_respects_strata_and_exclusions(raw_dir, plan, tmp_path):
    manifest = sampling.build_sample(raw_dir, plan, tmp_path / "out")
    hh = manifest["households"]
    assert hh["selected"] == 12
    assert hh["by_group"] == {"Affluent": 4, "Comfortable": 4, "Adversity": 4}
    assert hh["by_tariff"] == {"Std": 9, "ToU": 3}
    assert all(mix == {"Std": 3, "ToU": 1} for mix in hh["tariff_by_group"].values())

    reasons = {e["LCLid"]: e["reason"] for e in hh["excluded"]}
    for g in (1, 2, 3):
        assert reasons[f"MAC{g}00004"].startswith("dead meter")
        assert reasons[f"MAC{g}00005"].startswith("low coverage")
        assert reasons[f"MAC{g}00006"] == "no readings in period"
    assert all(e["reason"] for e in hh["excluded"])

    selected = pd.read_csv(tmp_path / "out/dimensions/households_sample.csv", dtype=str)
    assert set(selected["LCLid"]) == set(hh["per_household"])
    assert len(selected) == 12
    assert selected["LCLid"].is_unique
    assert "MAC900001" not in set(selected["LCLid"])  # ACORN-U never selected
    assert not set(selected["LCLid"]) & set(reasons)
    for stats in hh["per_household"].values():
        assert stats["selection_coverage"] >= 0.8
        assert stats["zero_share"] < 0.9
        assert 0 < stats["coverage_study_period"] <= 1


def test_ac02_study_period_denominator_is_48_slots_per_day(raw_dir, plan, tmp_path):
    manifest = sampling.build_sample(raw_dir, plan, tmp_path / "out")
    # 3 study days -> 144 slots; 97 on-grid readings of the fixture -> 97 / 144
    stats = next(iter(manifest["households"]["per_household"].values()))
    assert stats["coverage_study_period"] == round(97 / 144, 6)
    assert stats["selection_coverage"] == 1.0  # spike denominator: 97 slots


def test_ac03_split_respects_cutoff_without_overlap(raw_dir, plan, tmp_path):
    manifest = sampling.build_sample(raw_dir, plan, tmp_path / "out")
    out = tmp_path / "out"
    hist = pd.concat(
        [pd.read_csv(p, dtype=str) for p in sorted((out / "historical").glob("*.csv"))]
    )
    stream = pd.read_csv(out / "stream/readings_stream.csv", dtype=str)
    cutoff = pd.Timestamp(CUTOFF)
    assert (pd.to_datetime(hist["tstp"], format="mixed") < cutoff).all()
    assert (pd.to_datetime(stream["tstp"], format="mixed") >= cutoff).all()
    keys_h = set(zip(hist["LCLid"], hist["tstp"], strict=True))
    keys_s = set(zip(stream["LCLid"], stream["tstp"], strict=True))
    assert not keys_h & keys_s
    counts = manifest["counts"]
    assert len(hist) == counts["historical_rows"]
    assert len(stream) == counts["stream_rows"]
    assert counts["historical_rows"] + counts["stream_rows"] == counts["total_rows"]
    assert counts["historical_non_numeric_rows"] == int((hist["energy(kWh/hh)"] == "Null").sum())
    assert counts["stream_non_numeric_rows"] == 0


def test_ac03_null_rows_are_kept_raw_in_the_output(raw_dir, plan, tmp_path):
    sampling.build_sample(raw_dir, plan, tmp_path / "out")
    text = (tmp_path / "out/historical/readings_2013-01.csv").read_text()
    assert ",Null\n" in text  # raw system rows survive (cleaning is the pipeline's job)
    assert ", 0.5 \n" in text  # raw padding preserved


def test_ac04_cutoff_override_moves_boundary_without_code_change(raw_dir, plan_file, tmp_path):
    base, moved = tmp_path / "base", tmp_path / "moved"
    common = ["--raw-dir", str(raw_dir), "--plan", str(plan_file)]
    assert prepare_sample.main(["build", *common, "--out", str(base)]) == 0
    code = prepare_sample.main(
        ["build", *common, "--out", str(moved), "--set", "cutoff=2013-01-01 12:00:00"]
    )
    assert code == 0
    m1 = json.loads((base / "manifest.json").read_text())
    m2 = json.loads((moved / "manifest.json").read_text())
    assert m1["counts"]["total_rows"] == m2["counts"]["total_rows"]
    assert m2["cutoff"] == "2013-01-01 12:00:00"
    assert m2["counts"]["historical_rows"] < m1["counts"]["historical_rows"]
    assert m2["counts"]["stream_rows"] > m1["counts"]["stream_rows"]


def test_ac04_invalid_override_and_cutoff_outside_period_fail(raw_dir, plan_file, tmp_path):
    common = ["--raw-dir", str(raw_dir), "--plan", str(plan_file), "--out", str(tmp_path / "o")]
    assert prepare_sample.main(["build", *common, "--set", "colour=red"]) == 1
    assert prepare_sample.main(["build", *common, "--set", "seed=abc"]) == 1
    assert prepare_sample.main(["build", *common, "--set", "cutoff=2015-01-01 00:00:00"]) == 1


def test_ac01_plan_drift_from_committed_blocks_fails(raw_dir, plan, plan_file, tmp_path):
    common = ["--raw-dir", str(raw_dir), "--plan", str(plan_file)]
    assert prepare_sample.main(["plan", *common]) == 0  # recomputed blocks equal the plan
    plan["blocks"]["Affluent"] = ["block_2"]
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    assert prepare_sample.main(["plan", *common]) == 1


def test_ac01_apply_overrides_coerces_types_and_does_not_mutate(plan):
    changed = sampling.apply_overrides(plan, ["seed=7", "min_coverage=0.5", "cutoff=2013-01-02"])
    assert changed["seed"] == 7
    assert changed["min_coverage"] == 0.5
    assert changed["cutoff"] == "2013-01-02"
    assert plan["seed"] == 42


def test_ac04_rebuild_into_same_folder_leaves_no_stale_files(raw_dir, plan, tmp_path):
    out = tmp_path / "out"
    sampling.build_sample(raw_dir, plan, out)
    moved = sampling.apply_overrides(plan, ["cutoff=2013-01-01 12:00:00"])
    manifest = sampling.build_sample(raw_dir, moved, out)
    on_disk = {p.name for p in (out / "historical").glob("*.csv")}
    assert on_disk == set(manifest["files"]["historical"])
