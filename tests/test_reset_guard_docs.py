"""RESET_GUARD AC-201: the runbook and the script docstring state the idle check."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/peak_model.md"
SCRIPT = ROOT / "scripts/reset_peak_model_outputs.py"

NEEDLES = (
    "smart_meter_peak_model and smart_meter_peak_model_training",
    "the dry run runs the idle check too",
    "refused, nothing dropped:",
    "no flag skips the idle check",
    "the window between the idle check and the first drop",
)


def _flat(text: str) -> str:
    return " ".join(text.replace("`", "").split()).casefold()


def _section(text: str, heading: str) -> str:
    rest = text[text.index(heading) + len(heading) :]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _training_bullet(text: str) -> str:
    section = _section(text, "## Concurrency with the ingestion job")
    rest = section[section.index("- **Training.**") :]
    end = re.search(r"\n(?:- |\n)", rest[2:])
    return rest[: end.start() + 2] if end else rest


def test_ac201_runbook_and_docstring_state_the_idle_check() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    nine = _section(text, "## 9. Reset (user-run, AC-66)")
    docstring = ast.get_docstring(ast.parse(SCRIPT.read_text(encoding="utf-8"))) or ""
    for where in (nine, docstring):
        flat = _flat(where)
        for needle in NEEDLES:
            assert needle in flat, needle
    bullet = _flat(_training_bullet(text))
    assert "reset_peak_model_outputs.py" in bullet
    assert "refuses while a run of the training job" in bullet
