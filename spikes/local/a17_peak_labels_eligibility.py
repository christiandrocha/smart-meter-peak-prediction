"""
Spike A-17: do the PEAK_MODEL label and eligibility definitions reproduce the seed-42 figures?

Question: DEFINE_PEAK_MODEL sets AC-41, AC-44, AC-47 and AC-63 from figures of a scratch script
outside the repository (F-28, F-30, F-31). This spike recomputes them from the seed-42 sample,
following the written definitions (FR-21, FR-22, *Eligibility definitions*, D-19, D-27, D-29,
D-34) and the METER_INGESTION Silver and Gold rules they build on (QR-02 to QR-05, QR-09, FR-10,
FR-11).

Pass criterion: every figure of AC-41, AC-44 and AC-47 matches; with --label-ratio 1.5 and
--coverage-min 0.90 the AC-63 checks hold instead of AC-44 and AC-47.

Throwaway code: never imported by src/. Usage:
  python spikes/local/a17_peak_labels_eligibility.py [--sample-dir data/sample/seed42]
  python spikes/local/a17_peak_labels_eligibility.py --label-ratio 1.5 --coverage-min 0.90
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PERIOD_START = pd.Timestamp("2012-07-01 00:00:00")
PERIOD_END = pd.Timestamp("2014-02-28 00:00:00")
SPLITS = {
    "train": ("2012-07-29", "2013-07-31"),
    "validation": ("2013-08-01", "2013-11-30"),
    "test": ("2013-12-01", "2014-02-27"),
}
DEFAULTS = {"label_ratio": 1.3, "coverage_min": 0.80, "zero_share_max": 0.90}


def load_silver(sample_dir: Path) -> pd.DataFrame:
    """Silver readings: parse, grid, numeric, non-negative, study period, first ingested wins."""
    files = sorted((sample_dir / "historical").glob("readings_*.csv"))
    files.append(sample_dir / "stream" / "readings_stream.csv")
    df = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    df.columns = ["household_id", "tstp", "energy"]
    df["reading_ts"] = pd.to_datetime(df["tstp"].str.strip(), format="mixed", errors="coerce")
    df["energy_kwh"] = pd.to_numeric(df["energy"].str.strip(), errors="coerce")
    ts = df["reading_ts"]
    on_grid = ts.dt.minute.isin([0, 30]) & (ts.dt.second == 0) & (ts.dt.microsecond == 0)
    valid = ts.notna() & on_grid & df["energy_kwh"].notna() & (df["energy_kwh"] >= 0)
    in_period = (ts >= PERIOD_START) & (ts <= PERIOD_END)
    df = df[valid & in_period]
    return df.drop_duplicates(["household_id", "reading_ts"], keep="first")


def daily_matrices(silver: pd.DataFrame, households: list[str], dates: pd.DatetimeIndex):
    """Gold daily totals and completeness (48 readings) as household x date matrices."""
    daily = (
        silver.assign(reading_date=silver["reading_ts"].dt.normalize())
        .groupby(["household_id", "reading_date"])["energy_kwh"]
        .agg(["sum", "size"])
    )
    total = daily["sum"].unstack().reindex(index=households, columns=dates)
    count = daily["size"].unstack().reindex(index=households, columns=dates).fillna(0)
    return total.to_numpy(), (count == 48).to_numpy()


def labels(total: np.ndarray, complete: np.ndarray, ratio: float):
    """D-19 label per household and T: T complete, 4 complete same-weekday days in 8 weeks."""
    n_hh, n_days = total.shape
    # Column j of the output is T = dates[j]; candidate k weeks back is column j - 7k.
    found = np.zeros((n_hh, n_days), dtype=int)
    picked = np.full((n_hh, n_days, 4), np.nan)
    for k in range(1, 9):
        src = np.arange(n_days) - 7 * k
        ok = src >= 0
        cand_complete = np.zeros((n_hh, n_days), dtype=bool)
        cand_total = np.full((n_hh, n_days), np.nan)
        cand_complete[:, ok] = complete[:, src[ok]]
        cand_total[:, ok] = total[:, src[ok]]
        take = cand_complete & (found < 4)
        rows, cols = np.nonzero(take)
        picked[rows, cols, found[rows, cols]] = cand_total[rows, cols]
        found += take
    baseline = np.where(found == 4, np.median(picked, axis=2), np.nan)
    has_label = complete & (found == 4)
    label = np.where(has_label, (total > ratio * baseline).astype(float), np.nan)
    return label, found


def eligibility(silver: pd.DataFrame, households: list[str], targets: pd.DatetimeIndex, args):
    """D-27 / D-34: the 3 latest study months whose last day is before T, from monthly facts."""
    months = pd.period_range(PERIOD_START, PERIOD_END, freq="M")
    period_days = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    expected = pd.Series(period_days.to_period("M")).value_counts().reindex(months) * 48
    monthly = (
        silver.assign(month=silver["reading_ts"].dt.to_period("M"), zero=silver["energy_kwh"] == 0)
        .groupby(["household_id", "month"])
        .agg(observed=("energy_kwh", "size"), zero=("zero", "sum"))
        .reindex(pd.MultiIndex.from_product([households, months]), fill_value=0)
    )
    assert len(monthly) == len(households) * len(months)  # dense, as METER_INGESTION AC-22
    rows = []
    for t in targets:
        window = [m for m in months if m.end_time.normalize() < t][-3:]
        exp = int(expected[window].sum())
        for hh in households:
            obs = int(monthly.loc[[(hh, m) for m in window], "observed"].sum()) if window else 0
            zer = int(monthly.loc[[(hh, m) for m in window], "zero"].sum()) if window else 0
            reasons = []
            cov = zs = None
            if len(window) < 3:
                reasons.append("insufficient_history")
            else:
                cov = obs / exp
                zs = zer / obs if obs else None
                if cov < args.coverage_min:
                    reasons.append("low_coverage")
                if zs is None or zs >= args.zero_share_max:
                    reasons.append("high_zero_share")
            rows.append((hh, t, len(window), cov, zs, not reasons, reasons))
    return pd.DataFrame(
        rows,
        columns=[
            "household_id",
            "target_date",
            "eligibility_month_count",
            "coverage_ratio_3m",
            "zero_share_3m",
            "is_eligible",
            "ineligibility_reasons",
        ],
    )


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--sample-dir", default="data/sample/seed42")
    parser.add_argument("--households", default="config/sample_households.csv")
    parser.add_argument("--label-ratio", type=float, default=DEFAULTS["label_ratio"])
    parser.add_argument("--coverage-min", type=float, default=DEFAULTS["coverage_min"])
    parser.add_argument("--zero-share-max", type=float, default=DEFAULTS["zero_share_max"])
    args = parser.parse_args()
    is_default = all(getattr(args, k) == v for k, v in DEFAULTS.items())

    households = sorted(pd.read_csv(args.households, dtype=str)["LCLid"])
    silver = load_silver(Path(args.sample_dir))
    print(f"silver rows: {len(silver):,}  households: {len(households)}")
    print(
        f"parameters: label_ratio={args.label_ratio} coverage_min={args.coverage_min} "
        f"zero_share_max={args.zero_share_max}"
    )

    # Gold days 2012-07-01..2014-02-28; label targets T = D + 1, 2012-07-02..2014-03-01.
    gold_dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    targets = gold_dates + pd.Timedelta(days=1)
    span = pd.date_range(gold_dates[0], targets[-1], freq="D")
    total, complete = daily_matrices(silver, households, span)
    label, found = labels(total, complete, args.label_ratio)
    t_slice = slice(1, None)  # drop column 2012-07-01, which is a feature date only
    lab = pd.DataFrame(
        {
            "household_id": np.repeat(households, len(targets)),
            "target_date": np.tile(targets, len(households)),
            "label_consumption_spike": label[:, t_slice].ravel(),
            "baseline_day_count": found[:, t_slice].ravel(),
            "t_complete": complete[:, t_slice].ravel(),
        }
    )
    elig = eligibility(silver, households, targets, args)
    lab = lab.merge(elig, on=["household_id", "target_date"], validate="one_to_one")

    labelled = lab[lab["label_consumption_spike"].notna()]
    eligible = labelled[labelled["is_eligible"]]
    ok = True
    print("\nAC-41 / QR-19")
    ok &= check(
        "dense label table",
        len(lab) == 36_480 and not lab.duplicated(["household_id", "target_date"]).any(),
        f"{len(lab):,} rows (expected 60 x 608 = 36,480), unique keys",
    )
    qr19 = (
        lab["label_consumption_spike"].notna()
        != (lab["t_complete"] & (lab["baseline_day_count"] == 4))
    ).sum()
    qr19 += (lab["is_eligible"] != lab["ineligibility_reasons"].map(len).eq(0)).sum()
    ok &= check("QR-19", qr19 == 0, f"{qr19} violations")

    pos = 100 * labelled["label_consumption_spike"].mean()
    if is_default:
        print("\nAC-44")
        ok &= check(
            "labelled rows", len(labelled) == 33_093, f"{len(labelled):,} (expected 33,093)"
        )
        ok &= check("positive share", 14.5 <= pos <= 14.7, f"{pos:.2f}% (expected 14.5% to 14.7%)")
        first, last = labelled["target_date"].min().date(), labelled["target_date"].max().date()
        ok &= check(
            "labelled T range",
            str(first) == "2012-07-29" and str(last) == "2014-02-27",
            f"{first} to {last} (expected 2012-07-29 to 2014-02-27)",
        )

    print("\nPer split (eligible labelled rows)")
    expected_split = {"train": (16_969, 14.0), "validation": (7_170, 15.8), "test": (5_116, 13.6)}
    for split, (lo, hi) in SPLITS.items():
        in_split = labelled[labelled["target_date"].between(lo, hi)]
        kept = in_split[in_split["is_eligible"]]
        rate = 100 * kept["label_consumption_spike"].mean()
        print(
            f"  {split:<10} labelled {len(in_split):>6,}  eligible {len(kept):>6,}  "
            f"positive {rate:5.2f}%"
        )
        if is_default:
            n, r = expected_split[split]
            ok &= check(
                f"AC-47 {split}",
                len(kept) == n and abs(rate - r) <= 0.1 + 1e-9,
                f"{len(kept):,} at {rate:.2f}% (expected {n:,} at {r}% +/- 0.1 pp)",
            )

    reasons = (
        labelled.loc[~labelled["is_eligible"], "ineligibility_reasons"].explode().value_counts()
    )
    print(f"  ineligible labelled rows by reason: {reasons.to_dict()}")
    if is_default:
        first_eligible = eligible["target_date"].min().date()
        last_ineligible = labelled.loc[~labelled["is_eligible"], "target_date"].max().date()
        ok &= check(
            "AC-47 first eligible T",
            str(first_eligible) >= "2012-10-01",
            f"{first_eligible} (expected on or after 2012-10-01)",
        )
        ok &= check(
            "AC-47 last ineligible T",
            str(last_ineligible) == "2013-10-31",
            f"{last_ineligible} (expected 2013-10-31)",
        )
    else:
        print("\nAC-63 (compare with the default run)")
        print(
            f"  positive share of labelled rows: {pos:.2f}% "
            "(AC-63: below default, within 1 pp of 7.9%)"
        )
        print(f"  eligible labelled rows: {len(eligible):,} (AC-63: no higher than the default)")
        if args.label_ratio == 1.5:
            ok &= check(
                "AC-63 positive share", abs(pos - 7.9) <= 1.0, f"{pos:.2f}% vs 7.9% +/- 1 pp"
            )

    print("\nA-17:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
