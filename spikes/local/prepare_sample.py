"""
Prepare a stratified sample of the "Smart Meters in London" dataset.

Two steps, so you only download the blocks you actually need:

  1. plan  - reads informations_households.csv and picks which block files
             to use per ACORN group. Prints the list of blocks to download.
  2. build - reads the chosen blocks, selects households that pass basic
             quality checks, splits readings at the cutoff and writes:
               out/historical/   monthly CSVs  -> UC Volume -> Auto Loader
               out/stream/       one CSV       -> local replay producer -> Kafka
               out/dimensions/   households, weather, bank holidays
               out/manifest.json counts used later for reconciliation tests

Readings are written RAW (original header, original string values, including
the 'Null' system rows). Cleaning is the pipeline's job, not this script's.

Usage:
  python prepare_sample.py plan  --raw-dir ./data --out plan.json
  python prepare_sample.py build --raw-dir ./data --plan plan.json --out ./out
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import pandas as pd

VALID_GROUPS = ["Affluent", "Comfortable", "Adversity"]  # excludes ACORN-U / ACORN-
DEFAULTS = {
    "seed": 42,
    "households_per_group": 20,
    "blocks_per_group": 2,
    "period_start": "2012-07-01 00:00:00",
    "period_end": "2014-02-28 00:00:00",   # last reading in the dataset
    "cutoff": "2013-12-01 00:00:00",       # historical < cutoff <= stream
    "max_zero_ratio": 0.90,                # above this the meter is considered dead
    "min_coverage": 0.80,                  # share of expected half-hours present
}
HALF_HOUR = pd.Timedelta("30min")


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


# ----------------------------------------------------------------------------- plan
def plan(args: argparse.Namespace) -> None:
    raw_dir = Path(args.raw_dir)
    hh = load_households(raw_dir)
    all_hh = pd.read_csv(raw_dir / "informations_households.csv", dtype=str)
    rng = random.Random(args.seed)

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
            if len(chosen) == args.blocks_per_group:
                break
        for b in candidates:  # fill up if there are not enough distinct subgroups
            if len(chosen) == args.blocks_per_group:
                break
            if b not in chosen:
                chosen.append(b)
        groups[group] = sorted(chosen, key=lambda b: int(b.split("_")[1]))

    result = {"seed": args.seed, "blocks_per_group": args.blocks_per_group, "groups": groups}
    Path(args.out).write_text(json.dumps(result, indent=2))

    needed = sorted({b for bs in groups.values() for b in bs}, key=lambda b: int(b.split("_")[1]))
    present = {p.stem for p in blocks_dir(raw_dir).glob("block_*.csv")}
    print(f"Plan written to {args.out}")
    for g, bs in groups.items():
        print(f"  {g:<12} {', '.join(bs)}")
    missing = [b for b in needed if b not in present]
    print("\nBlocks to download:" if missing else "\nAll planned blocks are present.")
    for b in missing:
        print(f"  halfhourly_dataset/halfhourly_dataset/{b}.csv")


# ----------------------------------------------------------------------------- build
def household_quality(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Per-household zero ratio and coverage of the expected 30-minute grid."""
    on_grid = df[(df["ts"].dt.minute.isin([0, 30])) & (df["ts"].dt.second == 0)]
    expected = int((end - start) / HALF_HOUR) + 1
    q = on_grid.groupby("LCLid").agg(
        readings=("ts", "nunique"),
        zero_ratio=("energy_num", lambda s: float((s == 0).mean()) if len(s) else 1.0),
    )
    q["coverage"] = q["readings"] / expected
    return q


def build(args: argparse.Namespace) -> None:
    raw_dir, out = Path(args.raw_dir), Path(args.out)
    cfg = json.loads(Path(args.plan).read_text())
    rng = random.Random(cfg["seed"])
    start, end = pd.Timestamp(args.period_start), pd.Timestamp(args.period_end)
    cutoff = pd.Timestamp(args.cutoff)
    if not (start < cutoff <= end):
        sys.exit("cutoff must fall inside the period")

    hh = load_households(raw_dir)
    tou_share = (hh["stdorToU"] == "ToU").mean()  # keep the population's tariff mix
    bdir = blocks_dir(raw_dir)

    selected_frames, selected_rows, excluded = [], [], []
    for group, blocks in cfg["groups"].items():
        missing = [b for b in blocks if not (bdir / f"{b}.csv").exists()]
        if missing:
            sys.exit(f"Missing block files for {group}: {missing}. Run 'plan' and download them.")

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

        quota_tou = round(args.households_per_group * tou_share)
        quota = {"ToU": quota_tou, "Std": args.households_per_group - quota_tou}
        picked: list[str] = []
        leftovers: list[str] = []
        for lcl in ids:
            row = candidates[candidates["LCLid"] == lcl].iloc[0]
            if lcl not in quality.index:
                excluded.append({"LCLid": lcl, "group": group, "reason": "no readings in period"})
                continue
            q = quality.loc[lcl]
            if q["zero_ratio"] > args.max_zero_ratio:
                excluded.append({"LCLid": lcl, "group": group, "reason": f"dead meter (zero_ratio={q['zero_ratio']:.2f})"})
                continue
            if q["coverage"] < args.min_coverage:
                excluded.append({"LCLid": lcl, "group": group, "reason": f"low coverage ({q['coverage']:.2f})"})
                continue
            if quota[row["stdorToU"]] > 0:
                quota[row["stdorToU"]] -= 1
                picked.append(lcl)
            else:
                leftovers.append(lcl)
        # If one tariff ran out of qualified households, fill from the other one.
        shortfall = args.households_per_group - len(picked)
        picked += leftovers[:shortfall]
        if len(picked) < args.households_per_group:
            print(f"WARNING: {group} has only {len(picked)} qualified households", file=sys.stderr)

        selected_rows.append(candidates[candidates["LCLid"].isin(picked)])
        selected_frames.append(readings[readings["LCLid"].isin(picked)])

    readings = pd.concat(selected_frames, ignore_index=True).sort_values(["ts", "LCLid"])
    households = pd.concat(selected_rows, ignore_index=True).sort_values("LCLid")
    header = ["LCLid", "tstp", "energy(kWh/hh)"]  # original source header

    # Historical: one file per month, so Auto Loader sees many files arriving.
    hist_dir = out / "historical"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist = readings[readings["ts"] < cutoff]
    file_stats = {}
    for month, part in hist.groupby(hist["ts"].dt.strftime("%Y-%m")):
        p = hist_dir / f"readings_{month}.csv"
        part[["LCLid", "tstp", "energy"]].to_csv(p, index=False, header=header)
        file_stats[p.name] = {"rows": len(part), "sha256": sha256(p)}

    # Stream: single file ordered by event time, consumed by the replay producer.
    stream_dir = out / "stream"
    stream_dir.mkdir(parents=True, exist_ok=True)
    stream = readings[readings["ts"] >= cutoff]
    sp = stream_dir / "readings_stream.csv"
    stream[["LCLid", "tstp", "energy"]].to_csv(sp, index=False, header=header)

    # Dimensions.
    dim_dir = out / "dimensions"
    dim_dir.mkdir(parents=True, exist_ok=True)
    households.to_csv(dim_dir / "households_sample.csv", index=False)
    weather = raw_dir / "weather_hourly_darksky.csv"
    if weather.exists():
        w = pd.read_csv(weather, dtype=str)
        wt = pd.to_datetime(w["time"])
        w[(wt >= start.floor("D")) & (wt <= end.ceil("D"))].to_csv(dim_dir / "weather_hourly_darksky.csv", index=False)
    holidays = raw_dir / "uk_bank_holidays.csv"
    if holidays.exists():
        pd.read_csv(holidays, dtype=str).to_csv(dim_dir / "uk_bank_holidays.csv", index=False)

    def null_rows(df: pd.DataFrame) -> int:
        return int(df["energy_num"].isna().sum())

    manifest = {
        "seed": cfg["seed"],
        "period": {"start": str(start), "end": str(end)},
        "cutoff": str(cutoff),
        "rules": {"historical": "tstp < cutoff", "stream": "tstp >= cutoff"},
        "quality_thresholds": {"max_zero_ratio": args.max_zero_ratio, "min_coverage": args.min_coverage},
        "households": {
            "selected": len(households),
            "by_group": households["Acorn_grouped"].value_counts().to_dict(),
            "by_tariff": households["stdorToU"].value_counts().to_dict(),
            "by_block": households["file"].value_counts().to_dict(),
            "excluded": excluded,
        },
        "counts": {
            "total_rows": len(readings),
            "historical_rows": len(hist),
            "historical_non_numeric_rows": null_rows(hist),
            "stream_rows": len(stream),
            "stream_non_numeric_rows": null_rows(stream),
        },
        "files": {"historical": file_stats, "stream": {sp.name: {"rows": len(stream), "sha256": sha256(sp)}}},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    c = manifest["counts"]
    print(f"Households: {len(households)}  {manifest['households']['by_group']}")
    print(f"Historical: {c['historical_rows']:,} rows in {len(file_stats)} files  |  Stream: {c['stream_rows']:,} rows")
    print(f"Excluded during selection: {len(excluded)}  |  Output: {out.resolve()}")


# ----------------------------------------------------------------------------- cli
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="choose which block files to use")
    p.add_argument("--raw-dir", required=True)
    p.add_argument("--out", default="plan.json")
    p.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    p.add_argument("--blocks-per-group", type=int, default=DEFAULTS["blocks_per_group"])
    p.set_defaults(func=plan)

    b = sub.add_parser("build", help="build the sample from the planned blocks")
    b.add_argument("--raw-dir", required=True)
    b.add_argument("--plan", default="plan.json")
    b.add_argument("--out", default="out")
    b.add_argument("--households-per-group", type=int, default=DEFAULTS["households_per_group"])
    for key in ("period_start", "period_end", "cutoff"):
        b.add_argument(f"--{key.replace('_', '-')}", default=DEFAULTS[key])
    b.add_argument("--max-zero-ratio", type=float, default=DEFAULTS["max_zero_ratio"])
    b.add_argument("--min-coverage", type=float, default=DEFAULTS["min_coverage"])
    b.set_defaults(func=build)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
