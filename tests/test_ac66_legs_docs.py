"""AC-159 to AC-161: names and shape of the AC-66 live tests, text order, nothing else changed.

AC-161 compares the working tree with tag ``v0.6.0`` (the release before AC66_BOTH_LEGS). The three
golden constants were computed from that tag with the functions of this file (``tree_digest``,
``reset_digest`` and ``kept_digest`` applied to ``git show v0.6.0:...``), not typed by hand. The
tag-based comparisons run only when the tag exists locally; the constants guard a clone without
tags (CI checks out one commit, DA-46).
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import check_specs
from support import ac66_rules as rules

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/peak_model.md"
LIVE_REL = "tests/integration/test_peak_data.py"
LIVE = ROOT / LIVE_REL
RULES_FILE = ROOT / "tests/support/ac66_rules.py"
RESET_REL = "scripts/reset_peak_model_outputs.py"
TAG = "v0.6.0"
ROOTS = ("src", "resources", "notebooks", "databricks.yml")
EXTRA = (
    "tests/test_peak_reset_script.py",
    ".claude/sdd/archive/PEAK_MODEL/DEFINE_PEAK_MODEL.md",
    ".claude/sdd/archive/PEAK_MODEL/DESIGN_PEAK_MODEL.md",
)
FOUR_NAMES = {rules.SNAPSHOT_TEST, rules.RERUN_TEST, rules.REBUILD_TEST, rules.VERDICT_TEST}
AC_NAME = re.compile(r"^test_ac(\d{2,3})_")

V060_TREE_SHA256 = "297fb0ca3b57415d59e433d92cfe6a6bd228da52baa881d3d6d16acff21617f2"
V060_RESET_SHA256 = "7fde3832bb4dbbbaca502b10272eecb90b317b357a32ed8db9001813b92323bd"
V060_KEPT_AST_SHA256 = "9c3671268db4680190432887012fa3c4327ac7ae966309fc24124f1f15ea08c7"


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
    out = _git("ls-tree", "-r", "--name-only", tag, "--", *ROOTS, *EXTRA)
    return sorted(out.decode().splitlines())


def tagged(tag: str, path: str) -> bytes:
    return _git("show", f"{tag}:{path}")


def tree_paths() -> list[str]:
    out = _git("ls-files", "--cached", "--others", "--exclude-standard", "--", *ROOTS, *EXTRA)
    return sorted({line for line in out.decode().splitlines() if (ROOT / line).is_file()})


def tree_digest(files: dict[str, bytes]) -> str:
    """SHA-256 over sorted ``path NUL sha256 LF`` lines."""
    lines = [f"{path}\0{hashlib.sha256(files[path]).hexdigest()}\n" for path in sorted(files)]
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ----------------------------------------------------------------------------- AST helpers
def _top(source: str, name: str) -> ast.AST:
    """A top-level function, class or simple assignment by name."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef | ast.ClassDef) and node.name == name:
            return node
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node
    raise AssertionError(f"{name} not found")


class _BlankStrings(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.Constant(""), node) if isinstance(node.value, str) else node


def reset_digest(source: str) -> str:
    """Guard code of the reset script; in ``main`` only the string constants are blanked."""
    parts = []
    for name in ("ROOT", "SNAPSHOT", "EXPECTED_ROWS", "ResetRefused", "Target", "targets", "plan"):
        parts.append(ast.unparse(_top(source, name)))
    parts.append(ast.unparse(_top(source, "Warehouse")))
    main = _BlankStrings().visit(_top(source, "main"))
    parts.append(ast.unparse(ast.fix_missing_locations(main)))
    return _sha("\n".join(parts))


KEPT = (
    "test_ac66_before_rebuild_snapshot",
    "_state",
    "_table_exists",
    "SNAPSHOT_TABLES",
    "DATA_TASKS",
)


def kept_digest(source: str) -> str:
    return _sha("\n".join(ast.unparse(_top(source, name)) for name in KEPT))


def _function(source: str, name: str) -> ast.FunctionDef:
    node = _top(source, name)
    assert isinstance(node, ast.FunctionDef)
    return node


def _calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _section(text: str, heading: str) -> str:
    rest = text[text.index(heading) + len(heading) :]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _collect(*args: str, allowed: tuple[int, ...] = (0,)) -> list[str]:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode in allowed, result.stdout + result.stderr
    return [line.strip() for line in result.stdout.splitlines() if "::test_" in line]


# ----------------------------------------------------------------------------- AC-159
def test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state() -> None:
    source = LIVE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = [
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_ac66_")
    ]
    assert sorted(names) == sorted(FOUR_NAMES)
    assert all(AC_NAME.match(name) for name in names)
    assert "test_ac66_after_rerun_and_rebuild_checksums_equal" not in source

    present = _function(source, "_tables_present")
    body = [
        n
        for n in present.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
    ]
    assert len(body) == 1
    assert isinstance(body[0], ast.Return)
    assert isinstance(body[0].value, ast.DictComp)
    for func in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        if func.name == "_tables_present":
            continue
        for call in _calls(func):
            assert not (isinstance(call.func, ast.Name) and call.func.id == "_table_exists")

    run_legs = [c for c in _calls(tree) if ast.unparse(c.func) == "ac66_rules.run_leg"]
    assert len(run_legs) == 2
    exists_ids: set[int] = set()
    legs = {}
    for func in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        for call in _calls(func):
            if ast.unparse(call.func) != "ac66_rules.run_leg":
                continue
            keywords = {k.arg: k.value for k in call.keywords}
            leg = keywords["leg"]
            assert isinstance(leg, ast.Constant)
            legs[func.name] = leg.value
            lam = keywords["exists"]
            assert isinstance(lam, ast.Lambda)
            exists_ids |= {id(n) for n in ast.walk(lam)}
    assert legs == {rules.RERUN_TEST: "rerun", rules.REBUILD_TEST: "rebuild"}
    uses = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id == "_tables_present" and isinstance(n.ctx, ast.Load)
    ]
    assert uses
    assert all(id(n) in exists_ids for n in uses)

    verdict = _function(source, rules.VERDICT_TEST)
    assert [a.arg for a in verdict.args.args] == ["evidence"]
    called = {ast.unparse(c.func) for c in _calls(verdict)}
    assert not any("run_leg" in name or "peak_runner" in name for name in called)

    rule_tree = ast.parse(RULES_FILE.read_text(encoding="utf-8"))
    for name in ("check_leg", "expected_merges"):
        func = next(n for n in rule_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        used = {a.arg for a in func.args.args + func.args.kwonlyargs}
        used |= {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
        assert not used & {"present", "exists"}, name

    listed = _collect("-m", "integration", "-o", "addopts=", LIVE_REL, "-k", "ac66")
    assert {line.split("::")[-1] for line in listed} == FOUR_NAMES


# ----------------------------------------------------------------------------- AC-160
def _first_positions(text: str, needles: list[str]) -> list[int]:
    positions = []
    for needle in needles:
        assert needle in text, needle
        positions.append(text.index(needle))
    return positions


ORDER = [
    "ac66_before",
    "ac66_rerun_leg",
    "reset_peak_model_outputs.py --confirm",
    "ac66_rebuild_leg",
    "ac66_verdict",
]


def _main_strings() -> list[str]:
    main = _function((ROOT / RESET_REL).read_text(encoding="utf-8"), "main")
    return [
        n.value for n in ast.walk(main) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_ac160_runbook_docstring_and_script_state_the_order() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    eight = _section(text, "## 8. Evidence order (integration tests)")
    nine = _section(text, "## 9. Reset (user-run, AC-66)")
    docstring = ast.get_docstring(ast.parse(LIVE.read_text(encoding="utf-8"))) or ""
    for where in (eight, docstring):
        positions = _first_positions(where, ORDER)
        assert positions == sorted(positions), positions
    for where in (eight, nine):
        assert "then the daily job" not in where.casefold()
        assert "run the daily job" not in where.casefold()
    assert "optional" not in nine.casefold()
    for line in eight.splitlines():
        if "ac66" in line or "reset" in line:
            assert "optional" not in line.casefold(), line
    for needle in (
        "ac66_rebuild_leg",
        "ac66_verdict",
        *(f"`{t}`" for t in rules.MERGE_TASKS.values()),
    ):
        assert needle in nine, needle
    for task in ("ingest_weather", "build_weather_silver", "build_features", "build_labels"):
        assert task in nine, task

    script = (ROOT / RESET_REL).read_text(encoding="utf-8")
    usage = ast.get_docstring(ast.parse(script)) or ""
    confirm_lines = [
        ln for ln in usage.splitlines() if ln.strip().startswith("python") and "--confirm" in ln
    ]
    assert len(confirm_lines) == 1
    assert "daily job" not in confirm_lines[0]
    selectors = [m for s in _main_strings() for m in re.findall(r"-k\s+(\S+)", s)]
    assert selectors == ["ac66_rebuild_leg"]


def _selectors() -> set[str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    found: set[str] = set()
    for section in (
        _section(text, "## 8. Evidence order (integration tests)"),
        _section(text, "## 9. Reset (user-run, AC-66)"),
        ast.get_docstring(ast.parse(LIVE.read_text(encoding="utf-8"))) or "",
    ):
        found |= {m for m in re.findall(r'-k "([^"]+)"', section) if "ac66" in m}
    found |= {m for s in _main_strings() for m in re.findall(r"-k\s+(\S+)", s) if "ac66" in m}
    return found


def test_ac160_every_ac66_selector_selects_exactly_one_test() -> None:
    selectors = _selectors()
    assert selectors == {"ac66_before", "ac66_rerun_leg", "ac66_rebuild_leg", "ac66_verdict"}
    union: set[str] = set()
    for selector in sorted(selectors):
        found = _collect("-m", "integration", "-o", "addopts=", LIVE_REL, "-k", selector)
        assert len(found) == 1, (selector, found)
        union.add(found[0].split("::")[-1])
    assert union == FOUR_NAMES
    stale = _collect(
        "-m", "integration", "-o", "addopts=", LIVE_REL, "-k", "ac66_after", allowed=(0, 5)
    )
    assert stale == []


# ----------------------------------------------------------------------------- AC-161
def _tree_files(paths: list[str]) -> dict[str, bytes]:
    return {path: (ROOT / path).read_bytes() for path in paths}


def test_ac161_production_files_and_reset_guards_equal_v060() -> None:
    paths = tree_paths()
    assert tree_digest(_tree_files(paths)) == V060_TREE_SHA256
    reset_source = (ROOT / RESET_REL).read_text(encoding="utf-8")
    assert reset_digest(reset_source) == V060_RESET_SHA256
    if tag_exists(TAG):
        assert paths == tagged_paths(TAG)
        for path in paths:
            assert (ROOT / path).read_bytes() == tagged(TAG, path), path
        assert reset_digest(tagged(TAG, RESET_REL).decode()) == V060_RESET_SHA256
        assert tree_digest({p: tagged(TAG, p) for p in tagged_paths(TAG)}) == V060_TREE_SHA256


def test_ac161_snapshot_test_and_its_helpers_are_kept() -> None:
    source = LIVE.read_text(encoding="utf-8")
    assert kept_digest(source) == V060_KEPT_AST_SHA256
    if tag_exists(TAG):
        assert kept_digest(tagged(TAG, LIVE_REL).decode()) == V060_KEPT_AST_SHA256
    snapshot = _top((ROOT / RESET_REL).read_text(encoding="utf-8"), "SNAPSHOT")
    assert isinstance(snapshot, ast.Assign)
    assert f'"{rules.SNAPSHOT_NAME}.json"' in ast.unparse(snapshot).replace("'", '"')


def test_ac161_specs_are_clean() -> None:
    assert check_specs.run(ROOT).errors == []
