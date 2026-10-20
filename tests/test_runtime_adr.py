"""AC-32: ADR 0001 records an outcome for every environment assumption, and specs are clean."""

from __future__ import annotations

import re
from pathlib import Path

import check_specs

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/0001-runtime-environment-constraints.md"
REQUIRED = ["A-01", "A-02", "A-03", "A-05", "A-06", "A-09", "A-10"]


def _results() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in ADR.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and re.fullmatch(r"(A|DA)-\d+", cells[0]):
            rows[cells[0]] = cells[
                4
            ]  # ID | Assumption | Spike | Pass criterion | Result | Fallback
    return rows


def test_ac32_runtime_adr_records_every_spike_outcome():
    results = _results()
    missing = [a for a in REQUIRED if a not in results]
    assert not missing, f"no row in ADR 0001 for: {missing}"
    pending = [a for a in REQUIRED if not results[a] or results[a].lower().startswith("pending")]
    assert not pending, f"ADR 0001 still has Pending results for: {pending}"
    for assumption in REQUIRED:
        assert re.match(r"(?i)(pass|fail)", results[assumption]), (assumption, results[assumption])


def test_ac32_check_specs_reports_no_errors():
    report = check_specs.run(ROOT)
    assert report.errors == []
