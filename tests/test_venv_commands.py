"""VENV_COMMANDS AC-207 and AC-208: copyable project commands name the tools in ``.venv/bin/``.

RESET_COMMAND_VENV I-01: the user's machine has no bare ``python`` and agents never activate the
virtual environment, so every project command a person or an agent copies names
``.venv/bin/<tool>``. Files the CHANGE track cannot touch (``scripts/check_specs.py``, the SDD
templates, ``src/``, ``tests/integration/``) are listed in VENV_COMMANDS I-01 instead.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BARE = re.compile(r"(?:^|[`\"' (:])(python|pytest|ruff|pre-commit|pip) ", flags=re.MULTILINE)


def _scope() -> list[Path]:
    files = [ROOT / "CLAUDE.md", ROOT / "README.md", ROOT / ".claude/sdd/README.md"]
    files += sorted((ROOT / "docs/runbooks").glob("*.md"))
    files += sorted((ROOT / ".claude/agents").rglob("*.md"))
    files += sorted((ROOT / ".claude/commands").rglob("*.md"))
    files += [p for p in sorted((ROOT / "scripts").glob("*.py")) if p.name != "check_specs.py"]
    files += sorted((ROOT / "tests/local_data").glob("*.py"))
    return files


def test_ac207_copyable_commands_name_the_venv_tools() -> None:
    files = _scope()
    assert len(files) >= 10, files
    found = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in BARE.finditer(line):
                found.append(f"{path.relative_to(ROOT)}:{number}: {match.group(1)}: {line.strip()}")
    assert found == []
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for command in (
        ".venv/bin/ruff check . && .venv/bin/ruff format --check .",
        ".venv/bin/pytest",
        ".venv/bin/python scripts/check_specs.py",
        ".venv/bin/pre-commit run --all-files",
    ):
        assert command in claude, command


def test_ac208_setup_creates_the_venv_with_python3() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/runbooks/meter_ingestion.md").read_text(encoding="utf-8")
    assert "\npython3 -m venv .venv\n.venv/bin/pip install -e " in readme
    assert '`python3 -m venv .venv && .venv/bin/pip install -e ".[' in runbook
    for text in (readme, runbook):
        assert "python -m venv" not in text
