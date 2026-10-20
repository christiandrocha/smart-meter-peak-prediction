"""Prepare the stratified seed-42 sample of the London smart meter dataset.

Thin CLI over ``smart_meter_peak_prediction.sampling`` (install with ``pip install -e .[sample]``).

  plan   recompute the block choice and fail if it differs from the committed plan
  build  write historical/, stream/, dimensions/ and manifest.json from the planned blocks

Examples:
  python scripts/prepare_sample.py plan  --raw-dir data/raw --plan config/sample_plan.json
  python scripts/prepare_sample.py build --raw-dir data/raw --plan config/sample_plan.json \\
      --out data/sample/seed42 --set cutoff="2013-11-01 00:00:00"

Any plan field can be overridden with ``--set key=value`` (seed, blocks_per_group,
households_per_group, period_start, period_end, cutoff, max_zero_ratio, min_coverage).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from smart_meter_peak_prediction import sampling


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--plan", type=Path, default=Path("config/sample_plan.json"))
    p.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override a plan field; repeatable",
    )


def cmd_plan(args: argparse.Namespace) -> int:
    plan = sampling.apply_overrides(sampling.load_plan(args.plan), args.overrides)
    blocks = sampling.check_plan(args.raw_dir, plan)  # raises PlanDriftError on drift
    if args.out:
        args.out.write_text(
            json.dumps({**plan, "blocks": blocks}, indent=2) + "\n", encoding="utf-8"
        )
    for group, group_blocks in blocks.items():
        print(f"  {group:<12} {', '.join(group_blocks)}")
    missing = sampling.missing_blocks(args.raw_dir, blocks)
    print("Blocks to download:" if missing else "All planned blocks are present.")
    for block in missing:
        print(f"  halfhourly_dataset/halfhourly_dataset/{block}.csv")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    plan = sampling.apply_overrides(sampling.load_plan(args.plan), args.overrides)
    manifest = sampling.build_sample(args.raw_dir, plan, args.out)
    c = manifest["counts"]
    print(f"Households: {manifest['households']['selected']}  {manifest['households']['by_group']}")
    print(
        f"Historical: {c['historical_rows']:,} rows in {len(manifest['files']['historical'])} "
        f"files  |  Stream: {c['stream_rows']:,} rows"
    )
    print(
        f"Excluded during selection: {len(manifest['households']['excluded'])}"
        f"  |  Output: {args.out.resolve()}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="check the committed block plan against the raw data")
    _add_common(p)
    p.add_argument("--out", type=Path, default=None, help="also write the recomputed plan here")
    p.set_defaults(func=cmd_plan)

    b = sub.add_parser("build", help="build the sample from the planned blocks")
    _add_common(b)
    b.add_argument("--out", type=Path, default=Path("data/sample/seed42"))
    b.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (sampling.SampleError, sampling.PlanDriftError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
