"""Stratified sample of the "Smart Meters in London" dataset.

Port of ``spikes/local/prepare_sample.py`` (``plan`` and ``build``) without changing its
algorithm, so that the outputs stay byte-identical to the spike and the pinned seed-42
selection in ``config/sample_households.csv`` is reproduced. The spike is never imported.

Differences from the spike, none of which changes a data file:
  - the plan is a committed file (``config/sample_plan.json``) with every parameter, and any
    field can be overridden (``apply_overrides``);
  - ``\\n`` line endings are pinned explicitly;
  - the manifest is extended (FR-01) and written with sorted keys and no timestamp;
  - the weather and bank-holiday files are not written (they belong to PEAK_MODEL).

Readings are written RAW (original header, original string values, including the 'Null'
system rows). Cleaning is the pipeline's job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

VALID_GROUPS = ["Affluent", "Comfortable", "Adversity"]  # excludes ACORN-U / ACORN-
READING_HEADER = ["LCLid", "tstp", "energy(kWh/hh)"]  # original source header
HALF_HOUR = pd.Timedelta("30min")
SLOTS_PER_DAY = 48
PLAN_KEYS = {
    "seed": int,
    "blocks_per_group": int,
    "households_per_group": int,
    "period_start": str,
    "period_end": str,
    "cutoff": str,
    "max_zero_ratio": float,
    "min_coverage": float,
}


class PlanDriftError(RuntimeError):
    """The blocks recomputed from the raw data differ from the committed plan."""


class SampleError(RuntimeError):
    """The sample cannot be built with the given plan and raw files."""


# ----------------------------------------------------------------------------- helpers
def blocks_dir(raw_dir: Path) -> Path:
    """Kaggle nests the folder twice: halfhourly_dataset/halfhourly_dataset/."""
    nested = raw_dir / "halfhourly_dataset" / "halfhourly_dataset"
    return nested if nested.exists() else raw_dir / "halfhourly_dataset"


def load_households(raw_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(raw_dir / "informations_households.csv", dtype=str)
    return df[df["Acorn_grouped"].isin(VALID_GROUPS)].copy()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _block_number(block: str) -> int:
    return int(block.split("_")[1])


# ----------------------------------------------------------------------------- plan file
def load_plan(path: Path) -> dict[str, Any]:
    """Read a plan. ``groups`` (the spike's key) is accepted as an alias of ``blocks``."""
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if "blocks" not in plan and "groups" in plan:
        plan["blocks"] = plan.pop("groups")
    return plan


def apply_overrides(plan: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Return a copy of ``plan`` with ``key=value`` overrides applied (AC-04, FR-16)."""
    result = json.loads(json.dumps(plan))
    for item in overrides:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or key not in PLAN_KEYS:
            raise SampleError(f"invalid override '{item}'; keys: {', '.join(sorted(PLAN_KEYS))}")
        try:
            result[key] = PLAN_KEYS[key](value)
            if key.startswith("period_") or key == "cutoff":
                pd.Timestamp(result[key])
        except ValueError as exc:
            raise SampleError(f"invalid value for '{key}': {value!r}") from exc
    return result


# ----------------------------------------------------------------------------- plan
def plan_blocks(raw_dir: Path, seed: int, blocks_per_group: int) -> dict[str, list[str]]:
    """Choose the block files per ACORN group (the spike's ``plan`` step)."""
    hh = load_households(raw_dir)
    all_hh = pd.read_csv(raw_dir / "informations_households.csv", dtype=str)
    rng = random.Random(seed)  # noqa: S311  (reproducible sampling, not crypto)

    groups: dict[str, list[str]] = {}
    for group in VALID_GROUPS:
        # A block is a candidate when every valid household in it belongs to this group.
        # Blocks are sorted by ACORN in the source, so most blocks are homogeneous.
        by_block = all_hh.groupby("file")["Acorn_grouped"].agg(set)
        candidates = [b for b, gs in by_block.items() if gs - {"ACORN-U", "ACORN-"} == {group}]
        rng.shuffle(candidates)

        # Prefer blocks covering different ACORN subgroups (A, B, C...) for diversity.
        subgroup = hh.groupby("file")["Acorn"].agg(lambda s: s.mode().iat[0])
        chosen, seen = [], set()
        for b in candidates:
            if subgroup.get(b) not in seen:
                chosen.append(b)
                seen.add(subgroup.get(b))
            if len(chosen) == blocks_per_group:
                break
        for b in candidates:  # fill up if there are not enough distinct subgroups
            if len(chosen) == blocks_per_group:
                break
            if b not in chosen:
                chosen.append(b)
        groups[group] = sorted(chosen, key=_block_number)
    return groups


def missing_blocks(raw_dir: Path, blocks: dict[str, list[str]]) -> list[str]:
    present = {p.stem for p in blocks_dir(raw_dir).glob("block_*.csv")}
    needed = sorted({b for bs in blocks.values() for b in bs}, key=_block_number)
    return [b for b in needed if b not in present]


def check_plan(raw_dir: Path, plan: dict[str, Any]) -> dict[str, list[str]]:
    """Recompute the blocks; raise ``PlanDriftError`` if they differ from the committed plan."""
    computed = plan_blocks(raw_dir, plan["seed"], plan["blocks_per_group"])
    committed = plan.get("blocks")
    if committed is not None and computed != committed:
        raise PlanDriftError(
            f"recomputed blocks {computed} differ from the committed plan {committed}"
        )
    return computed


# ----------------------------------------------------------------------------- build
def household_quality(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Per-household zero ratio and coverage of the expected 30-minute grid (selection rule)."""
    on_grid = df[(df["ts"].dt.minute.isin([0, 30])) & (df["ts"].dt.second == 0)]
    expected = int((end - start) / HALF_HOUR) + 1
    q = on_grid.groupby("LCLid").agg(
        readings=("ts", "nunique"),
        zero_ratio=("energy_num", lambda s: float((s == 0).mean()) if len(s) else 1.0),
    )
    q["coverage"] = q["readings"] / expected
    return q


def study_days(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return int((end.normalize() - start.normalize()).days) + 1


def silver_quality(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Per-household coverage against the Silver denominator and zero share (AC-25).

    Observed readings are the distinct on-grid timestamps with a finite, non-negative energy,
    which is what Silver keeps. The denominator is 48 x the days of the study period.
    """
    grid = (df["ts"].dt.minute.isin([0, 30])) & (df["ts"].dt.second == 0)
    valid = df[grid & df["energy_num"].notna() & (df["energy_num"] >= 0)]
    valid = valid[valid["energy_num"] != float("inf")]
    expected = SLOTS_PER_DAY * study_days(start, end)
    q = valid.groupby("LCLid").agg(
        observed=("ts", "nunique"),
        zeros=("energy_num", lambda s: int((s == 0).sum())),
    )
    q["coverage_study_period"] = q["observed"] / expected
    q["zero_share"] = q["zeros"] / q["observed"]
    return q


def _round(value: float) -> float:
    return round(float(value), 6)


def build_sample(raw_dir: Path, plan: dict[str, Any], out: Path) -> dict[str, Any]:
    """Build the sample files and manifest in ``out`` (the spike's ``build`` step)."""
    raw_dir, out = Path(raw_dir), Path(out)
    rng = random.Random(plan["seed"])  # noqa: S311
    start, end = pd.Timestamp(plan["period_start"]), pd.Timestamp(plan["period_end"])
    cutoff = pd.Timestamp(plan["cutoff"])
    if not (start < cutoff <= end):
        raise SampleError("cutoff must fall inside the period")
    per_group = plan["households_per_group"]
    max_zero_ratio, min_coverage = plan["max_zero_ratio"], plan["min_coverage"]

    blocks_plan = plan.get("blocks") or plan_blocks(raw_dir, plan["seed"], plan["blocks_per_group"])
    # A re-run into an existing folder must not leave files of an earlier plan behind.
    for stale in (out / "historical").glob("readings_*.csv"):
        stale.unlink()
    for stale in (out / "stream").glob("*.csv"):
        stale.unlink()

    hh = load_households(raw_dir)
    tou_share = (hh["stdorToU"] == "ToU").mean()  # keep the population's tariff mix
    bdir = blocks_dir(raw_dir)

    selected_frames, selected_rows, excluded, per_household = [], [], [], {}
    for group, blocks in blocks_plan.items():
        missing = [b for b in blocks if not (bdir / f"{b}.csv").exists()]
        if missing:
            raise SampleError(f"Missing block files for {group}: {missing}.")

        readings = pd.concat(
            [pd.read_csv(bdir / f"{b}.csv", dtype=str) for b in blocks], ignore_index=True
        )
        readings.columns = ["LCLid", "tstp", "energy"]  # positional; raw header kept on write
        readings["ts"] = pd.to_datetime(readings["tstp"].str.strip(), format="mixed")
        readings = readings[(readings["ts"] >= start) & (readings["ts"] <= end)]
        readings["energy_num"] = pd.to_numeric(readings["energy"].str.strip(), errors="coerce")

        quality = household_quality(readings, start, end)
        candidates = hh[(hh["Acorn_grouped"] == group) & (hh["file"].isin(blocks))].copy()
        ids = candidates["LCLid"].tolist()
        rng.shuffle(ids)

        quota_tou = round(per_group * tou_share)
        quota = {"ToU": quota_tou, "Std": per_group - quota_tou}
        picked: list[str] = []
        leftovers: list[str] = []
        for lcl in ids:
            row = candidates[candidates["LCLid"] == lcl].iloc[0]
            if lcl not in quality.index:
                excluded.append({"LCLid": lcl, "group": group, "reason": "no readings in period"})
                continue
            q = quality.loc[lcl]
            if q["zero_ratio"] > max_zero_ratio:
                reason = f"dead meter (zero_ratio={q['zero_ratio']:.2f})"
                excluded.append({"LCLid": lcl, "group": group, "reason": reason})
                continue
            if q["coverage"] < min_coverage:
                reason = f"low coverage ({q['coverage']:.2f})"
                excluded.append({"LCLid": lcl, "group": group, "reason": reason})
                continue
            if quota[row["stdorToU"]] > 0:
                quota[row["stdorToU"]] -= 1
                picked.append(lcl)
            else:
                leftovers.append(lcl)
        # If one tariff ran out of qualified households, fill from the other one.
        shortfall = per_group - len(picked)
        picked += leftovers[:shortfall]
        if len(picked) < per_group:
            log.warning("%s has only %d qualified households", group, len(picked))

        silver_q = silver_quality(readings[readings["LCLid"].isin(picked)], start, end)
        no_valid = [lcl for lcl in picked if lcl not in silver_q.index]
        if no_valid:
            raise SampleError(f"selected households without valid readings: {no_valid}")
        for lcl in picked:
            sq = silver_q.loc[lcl]
            per_household[lcl] = {
                "selection_coverage": _round(quality.loc[lcl, "coverage"]),
                "zero_share": _round(sq["zero_share"]),
                "coverage_study_period": _round(sq["coverage_study_period"]),
            }
        selected_rows.append(candidates[candidates["LCLid"].isin(picked)])
        selected_frames.append(readings[readings["LCLid"].isin(picked)])

    readings = pd.concat(selected_frames, ignore_index=True).sort_values(["ts", "LCLid"])
    households = pd.concat(selected_rows, ignore_index=True).sort_values("LCLid")

    # Historical: one file per month, so Auto Loader sees many files arriving.
    hist_dir = out / "historical"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist = readings[readings["ts"] < cutoff]
    file_stats = {}
    for month, part in hist.groupby(hist["ts"].dt.strftime("%Y-%m")):
        p = hist_dir / f"readings_{month}.csv"
        part[["LCLid", "tstp", "energy"]].to_csv(
            p, index=False, header=READING_HEADER, lineterminator="\n"
        )
        file_stats[p.name] = {"rows": len(part), "sha256": sha256(p)}

    # Stream: single file ordered by event time, consumed by the replay producer.
    stream_dir = out / "stream"
    stream_dir.mkdir(parents=True, exist_ok=True)
    stream = readings[readings["ts"] >= cutoff]
    sp = stream_dir / "readings_stream.csv"
    stream[["LCLid", "tstp", "energy"]].to_csv(
        sp, index=False, header=READING_HEADER, lineterminator="\n"
    )

    # Dimension: the household file.
    dim_dir = out / "dimensions"
    dim_dir.mkdir(parents=True, exist_ok=True)
    hp = dim_dir / "households_sample.csv"
    households.to_csv(hp, index=False, lineterminator="\n")

    def null_rows(df: pd.DataFrame) -> int:
        return int(df["energy_num"].isna().sum())

    tariff_by_group = {
        group: {str(k): int(v) for k, v in part["stdorToU"].value_counts().items()}
        for group, part in households.groupby("Acorn_grouped")
    }
    manifest = {
        "seed": plan["seed"],
        "period": {"start": str(start), "end": str(end)},
        "cutoff": str(cutoff),
        "rules": {"historical": "tstp < cutoff", "stream": "tstp >= cutoff"},
        "quality_thresholds": {"max_zero_ratio": max_zero_ratio, "min_coverage": min_coverage},
        "households": {
            "selected": len(households),
            "by_group": households["Acorn_grouped"].value_counts().to_dict(),
            "by_tariff": households["stdorToU"].value_counts().to_dict(),
            "by_block": households["file"].value_counts().to_dict(),
            "tariff_by_group": tariff_by_group,
            "per_household": per_household,
            "excluded": excluded,
        },
        "counts": {
            "total_rows": len(readings),
            "historical_rows": len(hist),
            "historical_non_numeric_rows": null_rows(hist),
            "stream_rows": len(stream),
            "stream_non_numeric_rows": null_rows(stream),
        },
        "files": {
            "historical": file_stats,
            "stream": {sp.name: {"rows": len(stream), "sha256": sha256(sp)}},
            "households": {hp.name: {"rows": len(households), "sha256": sha256(hp)}},
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest
