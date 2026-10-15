"""Profile sample data and write findings in the F-NN format used by BRAINSTORM documents.

Reads CSV (as text, so formatting problems stay visible) or Parquet files and reports:
  - column names that are not safe for Delta / SQL
  - null-like values, including literal tokens such as 'Null', 'NaN', 'None' and empty strings
  - values padded with whitespace
  - mostly-numeric columns that contain non-numeric tokens
  - duplicate keys                                  (--key)
  - unparsable and off-grid timestamps, time range  (--time, --grid)
  - per-entity time coverage and staggered start/end (--time, --entity, --grid)
  - entities whose measure is constant or mostly zero (--entity, --value)

The output is a Markdown file with an overview, a column table and a findings table whose rows
can be pasted into the "Profiling findings" table of a BRAINSTORM document. Every finding
carries numbers; the implication column is a starting suggestion to review, not a decision.

Examples:
  python scripts/profile_data.py data/readings/*.csv --key household_id,reading_ts \\
      --time reading_ts --entity household_id --value energy_kwh --grid 30min \\
      --out docs/profiling/readings.md
  python scripts/profile_data.py data/households.csv --key LCLid --start-id 10
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - exercised only without the optional dependency
    sys.exit("profile_data.py needs pandas: pip install -e '.[profile]'")

NULL_TOKENS = {"", "null", "none", "nan", "na", "n/a", "nil", "-"}
UNSAFE_NAME = re.compile(r"[ ,;{}()\n\t=]")
NUMERIC_SHARE = 0.95  # a column is "mostly numeric" above this share of parseable values
COVERAGE_WARN = 0.80
DEAD_ZERO_SHARE = 0.90
CATEGORICAL_MAX = 20
STAGGER_WARN = pd.Timedelta(days=30)  # spread of first/last timestamps across entities


def pct(ratio: float) -> str:
    return "<0.01%" if 0 < ratio < 0.0001 else f"{ratio:.2%}"


def is_text(series: pd.Series) -> bool:
    """True for object and string dtypes (pandas 3 reads text as the 'str' dtype)."""
    return series.dtype == object or pd.api.types.is_string_dtype(series.dtype)


@dataclass
class Finding:
    id: str
    finding: str
    evidence: str
    implication: str


class Profiler:
    def __init__(self, df: pd.DataFrame, start_id: int = 1) -> None:
        self.df = df
        self.findings: list[Finding] = []
        self._next = start_id

    def add(self, finding: str, evidence: str, implication: str) -> None:
        self.findings.append(Finding(f"F-{self._next:02d}", finding, evidence, implication))
        self._next += 1

    # ------------------------------------------------------------------ column level
    def column_names(self) -> None:
        bad = [c for c in self.df.columns if UNSAFE_NAME.search(str(c))]
        if bad:
            self.add(
                "Column names not safe for Delta/SQL",
                ", ".join(f"`{c}`" for c in bad),
                "Rename or read with a positional schema in Bronze",
            )

    def text_columns(self) -> list[str]:
        return [c for c in self.df.columns if is_text(self.df[c])]

    def nulls(self) -> None:
        n = len(self.df)
        for col in self.df.columns:
            series = self.df[col]
            real_null = int(series.isna().sum())
            token_counts: dict[str, int] = {}
            if is_text(series):
                stripped = series.dropna().astype(str).str.strip()
                tokens = stripped[stripped.str.lower().isin(NULL_TOKENS)]
                token_counts = tokens.value_counts().head(3).to_dict()
            total = real_null + sum(token_counts.values())
            if total:
                detail = [f"{real_null:,} missing"] if real_null else []
                detail += [f"{v:,} literal '{k}'" for k, v in token_counts.items()]
                self.add(
                    f"Null-like values in `{col}`",
                    f"{total:,} of {n:,} rows ({pct(total / n)}): " + ", ".join(detail),
                    "Decide drop / default / keep-as-null; add an expectation and count it",
                )

    def padding(self) -> None:
        for col in self.text_columns():
            values = self.df[col].dropna().astype(str)
            padded = int((values != values.str.strip()).sum())
            if padded:
                example = values[values != values.str.strip()].iloc[0]
                self.add(
                    f"Whitespace-padded values in `{col}`",
                    f"{padded:,} values, e.g. {example!r}",
                    "Trim before casting",
                )

    def mostly_numeric(self) -> None:
        for col in self.text_columns():
            values = self.df[col].dropna().astype(str).str.strip()
            values = values[~values.str.lower().isin(NULL_TOKENS)]
            if values.empty:
                continue
            parsed = pd.to_numeric(values, errors="coerce")
            share = parsed.notna().mean()
            if NUMERIC_SHARE <= share < 1:
                bad = values[parsed.isna()].value_counts().head(3).to_dict()
                self.add(
                    f"Non-numeric tokens in numeric column `{col}`",
                    f"{int(parsed.isna().sum()):,} values: {bad}",
                    "Cast with explicit handling; quarantine or drop with an expectation",
                )

    # ------------------------------------------------------------------ keys and time
    def duplicate_keys(self, key: list[str]) -> None:
        missing = [k for k in key if k not in self.df.columns]
        if missing:
            raise SystemExit(f"--key columns not found: {missing}")
        dupes = int(self.df.duplicated(key).sum())
        if dupes:
            self.add(
                f"Duplicate keys on ({', '.join(key)})",
                f"{dupes:,} duplicated rows",
                "Deduplicate before MERGE; define which duplicate wins",
            )
        else:
            self.add(
                f"Key ({', '.join(key)}) is unique",
                f"0 duplicates in {len(self.df):,} rows",
                "Idempotency can be asserted by row counts",
            )

    def parse_time(self, col: str) -> pd.Series:
        if col not in self.df.columns:
            raise SystemExit(f"--time column not found: {col}")
        raw = self.df[col]
        ts = pd.to_datetime(
            raw.astype(str).str.strip() if is_text(raw) else raw,
            errors="coerce",
            format="mixed",
        )
        bad = int(ts.isna().sum() - raw.isna().sum())
        if bad > 0:
            self.add(
                f"Unparsable timestamps in `{col}`",
                f"{bad:,} values",
                "Quarantine or drop with an expectation",
            )
        return ts

    def time_grid(
        self, ts: pd.Series, col: str, grid: pd.Timedelta | None, label: str = ""
    ) -> None:
        valid = ts.dropna()
        if valid.empty:
            return
        evidence = f"{valid.min()} to {valid.max()}"
        if grid is not None:
            off = valid[valid != valid.dt.floor(grid)]
            if len(off):
                evidence += f"; {len(off):,} off the {label} grid, e.g. {off.iloc[0]}"
                self.add(
                    f"Timestamps off the {label} grid in `{col}`",
                    evidence,
                    "Expectation on the grid; check if off-grid rows share a cause",
                )
                return
        self.add(f"Time range of `{col}`", evidence, "Fix the study window and the timezone")

    def entity_coverage(self, ts: pd.Series, entity: str, grid: pd.Timedelta) -> None:
        frame = pd.DataFrame({"e": self.df[entity], "t": ts}).dropna()
        frame = frame[frame["t"] == frame["t"].dt.floor(grid)].drop_duplicates()
        stats = frame.groupby("e")["t"].agg(["min", "max", "count"])
        if stats.empty:
            return
        expected = (stats["max"] - stats["min"]) / grid + 1
        coverage = stats["count"] / expected
        low = coverage[coverage < COVERAGE_WARN]
        self.add(
            f"Per-`{entity}` time coverage",
            f"{len(stats):,} entities; median {coverage.median():.1%}, "
            f"min {coverage.min():.1%}; {len(low):,} below {COVERAGE_WARN:.0%}",
            "Coverage feature or exclusion threshold; warn expectation on gaps",
        )
        start_spread = stats["min"].max() - stats["min"].min()
        end_spread = stats["max"].max() - stats["max"].min()
        if max(start_spread, end_spread) > STAGGER_WARN:
            self.add(
                f"Staggered start/end per `{entity}`",
                f"starts {stats['min'].min().date()} to {stats['min'].max().date()}, "
                f"ends {stats['max'].min().date()} to {stats['max'].max().date()}",
                "Define an 'active entity' window; avoid treating absence as zero",
            )

    def dead_entities(self, entity: str, value: str) -> None:
        if value not in self.df.columns:
            raise SystemExit(f"--value column not found: {value}")
        raw = self.df[value]
        numbers = pd.to_numeric(
            raw.astype(str).str.strip() if is_text(raw) else raw, errors="coerce"
        )
        frame = pd.DataFrame({"e": self.df[entity], "v": numbers}).dropna()
        by_entity = frame.groupby("e")["v"]
        zero_share = by_entity.apply(lambda s: float((s == 0).mean()))
        constant = by_entity.nunique() <= 1
        dead = zero_share[zero_share >= DEAD_ZERO_SHARE]
        if len(dead) or constant.any():
            examples = ", ".join(f"{e} ({z:.0%} zero)" for e, z in dead.head(3).items())
            self.add(
                f"`{entity}` with constant or mostly-zero `{value}`",
                f"{len(dead):,} with >= {DEAD_ZERO_SHARE:.0%} zeros, "
                f"{int(constant.sum()):,} constant. {examples}",
                "Flag as faulty source; exclude from training above a threshold",
            )

    # ------------------------------------------------------------------ summaries
    def column_table(self) -> list[dict]:
        rows = []
        n = len(self.df)
        for col in self.df.columns:
            s = self.df[col]
            sample = s.dropna().astype(str).str.strip().unique()[:3]
            rows.append(
                {
                    "column": str(col),
                    "dtype": str(s.dtype),
                    "null_pct": f"{s.isna().mean():.1%}" if n else "-",
                    "distinct": int(s.nunique(dropna=True)),
                    "sample": ", ".join(sample),
                }
            )
        return rows

    def categoricals(self) -> dict[str, dict[str, int]]:
        out = {}
        for col in self.text_columns():
            if 1 < self.df[col].nunique() <= CATEGORICAL_MAX:
                out[str(col)] = (
                    self.df[col].value_counts(dropna=False).head(CATEGORICAL_MAX).to_dict()
                )
        return out


def load(paths: list[Path], sample_rows: int | None) -> pd.DataFrame:
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"file(s) not found: {', '.join(missing)}")
    frames = []
    for path in paths:
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
            frames.append(df.head(sample_rows) if sample_rows else df)
        else:
            frames.append(
                pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[], nrows=sample_rows)
            )
    if not frames:
        raise SystemExit("no input files")
    return pd.concat(frames, ignore_index=True)


def to_markdown(name: str, paths: list[Path], prof: Profiler) -> str:
    def esc(text: str) -> str:
        return str(text).replace("|", "\\|")

    lines = [
        f"# Data profile: {name}",
        "",
        f"Generated by `scripts/profile_data.py` on {date.today().isoformat()}.",
        "",
        "## Overview",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Files | {len(paths)} |",
        f"| Rows | {len(prof.df):,} |",
        f"| Columns | {len(prof.df.columns)} |",
        "",
        "## Columns",
        "",
        "| Column | Type | Null % | Distinct | Sample |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| `{esc(r['column'])}` | {r['dtype']} | {r['null_pct']} | {r['distinct']:,} | "
        f"{esc(r['sample'])} |"
        for r in prof.column_table()
    ]
    cats = prof.categoricals()
    if cats:
        lines += ["", "## Categorical distributions", ""]
        for col, counts in cats.items():
            dist = ", ".join(f"{esc(k)}: {v:,}" for k, v in counts.items())
            lines.append(f"- `{esc(col)}`: {dist}")
    lines += [
        "",
        "## Findings",
        "",
        "| ID | Finding | Evidence | Implication |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {f.id} | {esc(f.finding)} | {esc(f.evidence)} | {esc(f.implication)} |"
        for f in prof.findings
    ]
    if not prof.findings:
        lines.append("| - | No findings | - | - |")
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> Profiler:
    paths = [Path(p) for p in args.paths]
    prof = Profiler(load(paths, args.sample_rows), start_id=args.start_id)
    grid = pd.Timedelta(args.grid) if args.grid else None

    prof.column_names()
    prof.nulls()
    prof.padding()
    prof.mostly_numeric()
    if args.key:
        prof.duplicate_keys([k.strip() for k in args.key.split(",")])
    if args.time:
        ts = prof.parse_time(args.time)
        prof.time_grid(ts, args.time, grid, args.grid or "")
        if args.entity and grid is not None:
            prof.entity_coverage(ts, args.entity, grid)
    if args.entity and args.value:
        prof.dead_entities(args.entity, args.value)
    return prof


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("paths", nargs="+", help="CSV or Parquet files")
    p.add_argument("--key", help="comma-separated key columns")
    p.add_argument("--time", help="event timestamp column")
    p.add_argument("--entity", help="entity id column (household, device, customer...)")
    p.add_argument("--value", help="numeric measure column, for constant / zero checks")
    p.add_argument("--grid", help="expected time step, e.g. 30min, 1h, 1D")
    p.add_argument("--sample-rows", type=int, help="read at most N rows per file")
    p.add_argument("--start-id", type=int, default=1, help="first finding number (F-NN)")
    p.add_argument("--name", help="dataset name in the report title")
    p.add_argument("--out", type=Path, help="write Markdown here (default: stdout)")
    p.add_argument("--json", type=Path, help="also write findings as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prof = run(args)
    name = args.name or Path(args.paths[0]).stem
    markdown = to_markdown(name, [Path(p) for p in args.paths], prof)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"{len(prof.findings)} finding(s) written to {args.out}")
    else:
        print(markdown)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps([asdict(f) for f in prof.findings], indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
