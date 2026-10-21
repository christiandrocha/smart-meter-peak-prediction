"""AC-67: ADR 0007 records the PEAK_MODEL environment assumptions and the chosen variant."""

from __future__ import annotations

import re
from pathlib import Path

import check_specs

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/0007-peak-model-runtime-and-data-assumptions.md"
REQUIRED = ["A-04", "A-12", "A-16"]


def _results() -> dict[str, str]:
    """Assumption ID to its Result cell (the fifth column of the ADR table)."""
    rows: dict[str, str] = {}
    for line in ADR.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and re.fullmatch(r"A-\d+", cells[0]):
            rows[cells[0]] = cells[4]
    return rows


def test_ac67_adr_0007_accepted_with_spike_05_outcomes_and_variant() -> None:
    text = ADR.read_text(encoding="utf-8")
    status = re.search(r"\*\*Status\*\*\s*\|\s*([^|]+?)\s*\|", text)
    assert status is not None
    assert status.group(1) == "Accepted"
    results = _results()
    missing = [a for a in REQUIRED if a not in results]
    assert not missing, f"no row in ADR 0007 for: {missing}"
    for assumption in REQUIRED:
        result = results[assumption]
        assert result, assumption
        assert not result.lower().startswith("pending"), (assumption, result)
        assert re.match(r"(?i)(pass|fail)", result), (assumption, result)
    # The decision names variant 1A (Feature Engineering table, point-in-time set, log_model).
    decision = text.split("## Decision", 1)[1].split("## Consequences", 1)[0]
    assert "variant 1A" in decision


def test_ac67_check_specs_reports_no_errors() -> None:
    report = check_specs.run(ROOT)
    assert report.errors == []
