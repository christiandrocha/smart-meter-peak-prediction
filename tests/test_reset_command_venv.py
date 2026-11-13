"""RESET_COMMAND_VENV AC-203 to AC-205: the reset commands name the project interpreter.

RESET_GUARD F-01: the user's machine has no bare ``python``, so every reset command a person
copies names ``.venv/bin/python``, and each dry run shows its exit code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from support import ac66_rules

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/peak_model.md"
SCRIPT = ROOT / "scripts/reset_peak_model_outputs.py"

SCRIPT_REL = "scripts/reset_peak_model_outputs.py"
PREFIX = f".venv/bin/python {SCRIPT_REL}"
BARE = re.compile(rf"(?<![/\w])python {re.escape(SCRIPT_REL)}")
EXIT_CODE = '; echo "exit $?"'


def _section(text: str, heading: str) -> str:
    rest = text[text.index(heading) + len(heading) :]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _texts() -> dict[str, str]:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(SCRIPT.read_text(encoding="utf-8"))) or ""
    return {
        "runbook section 8": _section(runbook, "## 8. Evidence order (integration tests)"),
        "runbook section 9": _section(runbook, "## 9. Reset (user-run, AC-66)"),
        "script docstring": docstring,
    }


def _command_lines(text: str) -> list[str]:
    """Lines that run the reset script (start with an interpreter, not prose)."""
    return [
        ln.strip()
        for ln in text.splitlines()
        if SCRIPT_REL in ln and ln.strip().split(" ", 1)[0].endswith("python")
    ]


def _command(line: str) -> str:
    return line.split(" #", 1)[0].rstrip()


def test_ac203_reset_commands_name_the_project_interpreter() -> None:
    for where, text in _texts().items():
        lines = _command_lines(text)
        assert len(lines) == 2, (where, lines)
        for line in lines:
            assert line.startswith(PREFIX), (where, line)
        assert not BARE.search(text), where
    assert ac66_rules.RESET_COMMAND == f"{PREFIX} --confirm"
    assert not BARE.search(ac66_rules.RESET_COMMAND)


def test_ac204_dry_run_lines_show_the_exit_code() -> None:
    for where, text in _texts().items():
        lines = _command_lines(text)
        dry = [ln for ln in lines if "--confirm" not in _command(ln)]
        confirm = [ln for ln in lines if "--confirm" in _command(ln)]
        assert len(dry) == 1, (where, lines)
        assert len(confirm) == 1, (where, lines)
        assert _command(dry[0]) == PREFIX + EXIT_CODE, (where, dry[0])
        assert "echo" not in _command(confirm[0]), (where, confirm[0])


def test_ac205_rebuild_refusal_names_the_project_interpreter() -> None:
    present = {key: True for key, _shown in ac66_rules.TABLES}
    result = ac66_rules.precondition("rebuild", snapshot_ok=True, present=present)
    assert result.allowed is False
    assert f"{PREFIX} --confirm" in result.message
    assert not BARE.search(result.message)
