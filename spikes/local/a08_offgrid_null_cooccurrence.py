"""
Spike A-08: are the off-grid `tstp` rows exactly the `Null` energy rows?

Question: DEFINE assumes that the rows rejected by QR-03 (timestamp off the 30-minute grid)
are the same rows rejected by QR-04 (non-numeric energy, literal 'Null'). This sets the
expected 60 quarantined rows in AC-11.

Pass criterion (per scope): the set of off-grid rows equals the set of non-numeric energy rows.
Scopes checked:
  - all rows of every block file found in the raw directory (the profiled blocks);
  - the seed-42 sample: households of config/sample_households.csv within the study period.

Throwaway code: never imported by src/. Usage:
  python spikes/local/a08_offgrid_null_cooccurrence.py [--raw-dir data/raw]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PERIOD_START = pd.Timestamp("2012-07-01 00:00:00")
PERIOD_END = pd.Timestamp("2014-02-28 00:00:00")


def blocks_dir(raw_dir: Path) -> Path:
    nested = raw_dir / "halfhourly_dataset" / "halfhourly_dataset"
    return nested if nested.exists() else raw_dir / "halfhourly_dataset"


def classify(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["tstp"].str.strip(), format="mixed")
    df = df.assign(ts=ts)
    df["off_grid"] = ~(ts.dt.minute.isin([0, 30]) & (ts.dt.second == 0) & (ts.dt.microsecond == 0))
    df["non_numeric"] = pd.to_numeric(df["energy"].str.strip(), errors="coerce").isna()
    return df


def report(name: str, df: pd.DataFrame) -> bool:
    off, null = df["off_grid"], df["non_numeric"]
    both, only_off, only_null = int((off & null).sum()), int((off & ~null).sum()), int((~off & null).sum())
    ok = only_off == 0 and only_null == 0
    print(f"[{name}] rows={len(df):,} off_grid={int(off.sum())} non_numeric={int(null.sum())} "
          f"both={both} only_off_grid={only_off} only_non_numeric={only_null} -> "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--sample", default="config/sample_households.csv")
    args = parser.parse_args()

    files = sorted(blocks_dir(Path(args.raw_dir)).glob("block_*.csv"))
    if not files:
        print("FAIL: no block files found")
        return 1
    print(f"blocks: {len(files)}")
    sample_ids = set(pd.read_csv(args.sample, dtype=str)["LCLid"])
    frames, in_sample, all_ok = [], [], True
    for path in files:
        df = pd.read_csv(path, dtype=str)
        df.columns = ["LCLid", "tstp", "energy"]
        df = classify(df)
        all_ok &= report(path.stem, df)
        frames.append(df[["LCLid", "ts", "off_grid", "non_numeric"]])
        sel = df[df["LCLid"].isin(sample_ids) & (df["ts"] >= PERIOD_START) & (df["ts"] <= PERIOD_END)]
        in_sample.append(sel)
    total = pd.concat(frames, ignore_index=True)
    all_ok &= report("ALL BLOCKS", total)
    sample = pd.concat(in_sample, ignore_index=True)
    sample_ok = report("SEED-42 SAMPLE (study period)", sample)
    print(f"sample rows failing QR-03 or QR-04: {int((sample['off_grid'] | sample['non_numeric']).sum())}")
    print("A-08:", "PASS" if all_ok and sample_ok else "FAIL")
    return 0 if all_ok and sample_ok else 1


if __name__ == "__main__":
    sys.exit(main())
