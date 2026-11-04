"""AC-104 and AC-105: runbook and hint text, production files unchanged, shipped AC-97 asserts kept.

AC-105 compares the working tree with tag ``v0.4.0`` (the release before AC97_TIMING_EVIDENCE). The
two golden constants were computed from that tag with the functions of this file (``tree_digest``
and ``assert_texts`` applied to ``git show v0.4.0:...``), not typed by hand. The tag-based
comparisons also run when the tag exists only; the constants guard a clone without tags.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path

from support import ac97_timing

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/meter_ingestion.md"
LIVE_REL = "tests/integration/test_ingestion_guard_live.py"
AC97 = "test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds"
TAG = "v0.4.0"
INIT_REL = "src/smart_meter_peak_prediction/__init__.py"
ROOTS = ("src/smart_meter_peak_prediction/", "resources/", "notebooks/", "databricks.yml")
VERSION_LINE_NEW = '__version__ = "0.4.1"'
VERSION_LINE_OLD = '__version__ = "0.4.0"'

V040_TREE_SHA256 = "258a24c28e3cf0babd75cd3b19c2eea635985f5ac24cd2a8fe73816e2a771f8c"
V040_AC97_ASSERTS = [
    "assert _result(check) == 'FAILED'",
    "assert _seconds(check) <= CHECK_BUDGET_SECONDS",
    "assert update_id in error",
    "assert 'smart_meter_silver_gold' in error",
    "assert 'rerun smart_meter_ingestion' in error",
    "assert re.search('\\\\d{4}-\\\\d{2}-\\\\d{2}T\\\\d{2}:\\\\d{2}:\\\\d{2}Z', error)",
    "assert _result(_one(peak_runner, refused.run, REFRESH)) == 'UPSTREAM_FAILED'",
    "assert during == [], f'updates created during the refused run: {during}'",
    "assert _result(_one(peak_runner, rerun.run, CHECK)) == 'SUCCESS'",
    "assert _result(_one(peak_runner, rerun.run, REFRESH)) == 'SUCCESS'",
    "assert rerun.outputs[CHECK]['outcome'] == 'idle'",
]


# ----------------------------------------------------------------------------- git helpers
def _git(*args: str) -> bytes:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def tag_exists(tag: str) -> bool:
    done = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def tagged_paths(tag: str) -> list[str]:
    out = _git("ls-tree", "-r", "--name-only", tag, "--", *ROOTS)
    return sorted(out.decode().splitlines())


def tagged(tag: str, path: str) -> bytes:
    return _git("show", f"{tag}:{path}")


def tree_paths() -> list[str]:
    out = _git("ls-files", "--cached", "--others", "--exclude-standard", "--", *ROOTS)
    return sorted({line for line in out.decode().splitlines() if (ROOT / line).is_file()})


def tree_digest(files: dict[str, bytes]) -> str:
    """SHA-256 over sorted ``path NUL sha256 LF`` lines; the version line reads 0.4.0."""
    lines = []
    for path in sorted(files):
        data = files[path]
        if path == INIT_REL:
            data = data.replace(VERSION_LINE_NEW.encode(), VERSION_LINE_OLD.encode())
        lines.append(f"{path}\0{hashlib.sha256(data).hexdigest()}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def assert_texts(source: str, function: str) -> list[str]:
    """``ast.unparse`` of every ``assert`` statement of the named function, in source order."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            found = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            return [ast.unparse(n) for n in sorted(found, key=lambda n: (n.lineno, n.col_offset))]
    raise AssertionError(f"{function} not found")


def _function(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


# ----------------------------------------------------------------------------- AC-104
def _section(text: str, heading: str) -> str:
    rest = text[text.index(heading) + len(heading) :]
    nxt = re.search(r"^#{2,3} ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_ac104_runbook_explains_the_timing_evidence() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    section = _section(text, "### AC-97 timing evidence")
    for needle in (
        "out/evidence/ac97_timing.json",
        "read_after_creation_seconds",
        "update_outlived_read_seconds",
        "27 s",
        "full_refresh=True",
        "Partial",
        "check_pipeline",
        "BUILD_REPORT",
        "test_ac106_",
    ):
        assert needle in section, needle
    row_h = next(line for line in text.splitlines() if line.startswith("| H. Reverse check"))
    assert "ac97_timing.json" in row_h

    joined = re.sub(r"\\\n\s*", " ", text)  # same rule as AC-99, own parser
    lists = [found.split(",") for found in re.findall(r"--only[ =]+([A-Za-z_,]+)", joined)]
    with_refresh = [tasks for tasks in lists if "refresh_silver_gold" in tasks]
    assert with_refresh
    for tasks in with_refresh:
        assert "check_silver_gold_idle" in tasks, tasks
    new_lists = re.findall(r"--only[ =]+([A-Za-z_,]+)", section)
    assert new_lists
    for tasks in new_lists:
        assert "check_silver_gold_idle" in tasks.split(",")


def test_ac104_failure_hint_and_note_name_the_evidence_file() -> None:
    hint = ac97_timing.failure_hint("U")
    for sentence in (
        "The update U may have ended before the check read it (DA-31)",
        "the no-op update lasted about 125 s on dev",
        "Run the test again; then start the update with full_refresh=True",
        "record AC-97 as Partial with a direct pipeline_guard.check_pipeline read during the "
        "update",
        "out/evidence/ac97_timing.json",
    ):
        assert sentence in hint, sentence
    assert ac97_timing.EVIDENCE_PATH_TEXT in ac97_timing.EVIDENCE_NOTE
    assert ac97_timing.EVIDENCE_PATH_TEXT == f"out/evidence/{ac97_timing.EVIDENCE_NAME}.json"

    function = _function((ROOT / LIVE_REL).read_text(encoding="utf-8"), AC97)
    tries = [n for n in function.body if isinstance(n, ast.Try)]
    assert len(tries) == 1, "the outermost try of the AC-97 test"
    outer = tries[0]
    base = [h for h in outer.handlers if ast.unparse(h.type) == "BaseException"]
    assert base
    assert any(
        isinstance(c.func, ast.Attribute) and c.func.attr == "add_note"
        for h in base
        for c in _calls(h)
    )
    saves = [
        c
        for stmt in outer.finalbody
        for c in _calls(stmt)
        if ast.unparse(c.func) == "evidence.save"
    ]
    assert saves
    assert ast.unparse(saves[0].args[0]) == "ac97_timing.EVIDENCE_NAME"
    inner = [n for n in ast.walk(outer) if isinstance(n, ast.ExceptHandler)]
    handlers = [h for h in inner if h.type is not None and ast.unparse(h.type) == "AssertionError"]
    assert handlers
    for handler in handlers:
        assert any(ast.unparse(c.func) == "ac97_timing.failure_hint" for c in _calls(handler))
        assert any(isinstance(n, ast.Raise) for n in ast.walk(handler))


# ----------------------------------------------------------------------------- AC-105
def test_ac105_production_files_equal_v040_except_the_version() -> None:
    paths = tree_paths()
    files = {path: (ROOT / path).read_bytes() for path in paths}
    assert tree_digest(files) == V040_TREE_SHA256
    init = files[INIT_REL].decode().splitlines()
    assert init.count(VERSION_LINE_NEW) == 1
    assert not [
        line for line in init if line.startswith("__version__") and line != VERSION_LINE_NEW
    ]
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["version"] == "0.4.1"

    if tag_exists(TAG):
        assert paths == tagged_paths(TAG)
        for path in paths:
            expected = tagged(TAG, path)
            if path == INIT_REL:
                expected = expected.replace(VERSION_LINE_OLD.encode(), VERSION_LINE_NEW.encode())
            assert files[path] == expected, path


def test_ac105_shipped_ac97_asserts_and_mechanics_are_kept() -> None:
    source = (ROOT / LIVE_REL).read_text(encoding="utf-8")
    if tag_exists(TAG):
        old = tagged(TAG, LIVE_REL).decode()
        assert assert_texts(old, AC97) == V040_AC97_ASSERTS
    assert len(V040_AC97_ASSERTS) == 11
    kept = Counter(assert_texts(source, AC97))
    for text, count in Counter(V040_AC97_ASSERTS).items():
        assert kept[text] >= count, text

    function = _function(source, AC97)
    starts = [c for c in _calls(function) if ast.unparse(c.func).endswith("pipelines.start_update")]
    assert len(starts) == 1
    assert {k.arg: ast.unparse(k.value) for k in starts[0].keywords}["full_refresh"] == "False"
    runs = [c for c in _calls(function) if ast.unparse(c.func) == "peak_runner.run"]
    assert len(runs) == 2
    for call in runs:
        assert {k.arg: ast.unparse(k.value) for k in call.keywords}["only"] == "subset"
    ordered = sorted(runs, key=lambda c: c.lineno)
    first, second = ({k.arg: ast.unparse(k.value) for k in c.keywords} for c in ordered)
    assert (first["expect"], first["require_idle"]) == ("'FAILED'", "False")
    assert second["require_idle"] == "True"
    waits = [
        c
        for n in ast.walk(function)
        if isinstance(n, ast.Try)
        for stmt in n.finalbody
        for c in _calls(stmt)
        if ast.unparse(c.func) == "_wait_pipeline_idle"
    ]
    assert waits
    subset = [
        n
        for n in ast.walk(function)
        if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "subset"
    ]
    assert [ast.unparse(n.value) for n in subset] == ["[CHECK, REFRESH]"]
