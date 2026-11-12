"""AC-159 to AC-161: names and shape of the AC-66 live tests, text order, nothing else changed.

AC-161 compares the working tree with tag ``v0.6.0`` (the release before AC66_BOTH_LEGS). The three
golden constants were computed from that tag with the functions of this file (``tree_digest``,
``reset_digest`` and ``kept_digest`` applied to ``git show v0.6.0:...``), not typed by hand. The
tag-based comparisons run only when the tag exists locally; the constants guard a clone without
tags (CI checks out one commit, DA-46).

AC66_ZERO_NEW_RUNS adds AC-170 to AC-172: the two live legs pass a reader bound to the peak job
(AST, AC-170), the v0.7.0 tests, rule constants and reset script are kept (AC-171; constants
computed from tag ``v0.7.0`` with the functions of this file) and the runbook and the live
docstring name the run list reads (AC-172).

RESET_GUARD (DA-68, AC-197) narrows AC-161 and AC-171: ``pipeline_guard.py`` and ``__init__.py``
(the release version) leave the AC-161 tree pin, and ``reset_digest`` covers only the reset parts
that RESET_GUARD keeps (``ROOT``, ``SNAPSHOT``, ``EXPECTED_ROWS``, ``ResetRefused``, ``Target``,
``targets``, ``plan``), not ``Warehouse`` or ``main``. ``V060_TREE_SHA256``, ``V060_RESET_SHA256``
and ``V070_RESET_SHA256`` were recomputed from tags ``v0.6.0`` and ``v0.7.0`` with these functions.
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
# RESET_GUARD DA-68: the module that feature extends and the release version, excluded from AC-161.
SUPERSEDED = (
    "src/smart_meter_peak_prediction/__init__.py",
    "src/smart_meter_peak_prediction/pipeline_guard.py",
)
EXTRA = (
    "tests/test_peak_reset_script.py",
    ".claude/sdd/archive/PEAK_MODEL/DEFINE_PEAK_MODEL.md",
    ".claude/sdd/archive/PEAK_MODEL/DESIGN_PEAK_MODEL.md",
)
FOUR_NAMES = {rules.SNAPSHOT_TEST, rules.RERUN_TEST, rules.REBUILD_TEST, rules.VERDICT_TEST}
AC_NAME = re.compile(r"^test_ac(\d{2,3})_")

V060_TREE_SHA256 = "b3c8db31e37882a91bb86177c75282b41e79541c025b7424a925d12026eca6bd"
V060_RESET_SHA256 = "05488e6db0df9a6b449c42d90b7b0e8e0d79b25b2636f6ebe08d18a35a39d304"
V060_KEPT_AST_SHA256 = "9c3671268db4680190432887012fa3c4327ac7ae966309fc24124f1f15ea08c7"

V070_TAG = "v0.7.0"
CONFTEST_REL = "tests/integration/conftest.py"
RULES_REL = "tests/support/ac66_rules.py"
V070_ASSERT_COUNTS = {
    "tests/test_ac66_rules.py": {
        "test_ac154_both_legs_on_the_current_snapshot_pass_deterministically": 10,
        "test_ac154_secret_like_strings_never_reach_the_record_or_the_message": 5,
        "test_ac154_rules_import_no_sdk_and_read_no_clock": 8,
        "test_ac155_missing_evidence_names_each_missing_leg_or_the_snapshot": 14,
        "test_ac156_stale_out_of_order_failed_inconsistent_or_malformed_legs_fail": 7,
        "test_ac156_odd_inputs_never_raise": 9,
        "test_ac157_precondition_over_all_table_states": 10,
        "test_ac158_leg_passes_and_writes_the_full_record": 14,
        "test_ac158_leg_failure_leaves_no_passed_record": 8,
        "test_ac158_wrong_state_refuses_before_the_runner": 5,
        "test_ac158_unknown_leg_refuses": 1,
        "test_ac158_unsaved_failed_record_does_not_mask_the_failure": 4,
        "test_ac158_real_evidence_class_keeps_its_shipped_defaults": 6,
        "test_ac158_after_state_mismatch_fails_and_never_stores_a_secret": 6,
        "test_ac158_failing_preflight_keeps_the_old_record": 2,
        "test_ac158_unreadable_snapshot_refuses": 2,
    },
    "tests/test_ac66_legs_docs.py": {
        "test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state": 17,
        "test_ac160_runbook_docstring_and_script_state_the_order": 10,
        "test_ac160_every_ac66_selector_selects_exactly_one_test": 4,
        "test_ac161_production_files_and_reset_guards_equal_v060": 6,
        "test_ac161_snapshot_test_and_its_helpers_are_kept": 4,
        "test_ac161_specs_are_clean": 1,
    },
}
V070_RULE_CONSTANTS_SHA256 = "6adb18da228fe3831b6c2cee8facea54a942ecad56de6092d5107391051d2946"
V070_RESET_SHA256 = "05488e6db0df9a6b449c42d90b7b0e8e0d79b25b2636f6ebe08d18a35a39d304"
RULE_CONSTANTS = (
    "SNAPSHOT_NAME",
    "LEG_NAMES",
    "VERDICT_NAME",
    "SNAPSHOT_TEST",
    "RERUN_TEST",
    "REBUILD_TEST",
    "VERDICT_TEST",
    "RECORD_FIELDS",
    "VERDICT_FIELDS",
)


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


def reset_digest(source: str) -> str:
    """Reset script parts that RESET_GUARD keeps (DA-68); not ``Warehouse`` or ``main``."""
    parts = []
    for name in ("ROOT", "SNAPSHOT", "EXPECTED_ROWS", "ResetRefused", "Target", "targets", "plan"):
        parts.append(ast.unparse(_top(source, name)))
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


def assert_counts(source: str) -> dict[str, int]:
    """Top-level test functions and their ``assert`` statements (AC-171)."""
    return {
        node.name: sum(isinstance(n, ast.Assert) for n in ast.walk(node))
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def rule_constants_digest(source: str) -> str:
    return _sha("\n".join(ast.unparse(_top(source, name)) for name in RULE_CONSTANTS))


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
    paths = [path for path in tree_paths() if path not in SUPERSEDED]
    assert tree_digest(_tree_files(paths)) == V060_TREE_SHA256
    reset_source = (ROOT / RESET_REL).read_text(encoding="utf-8")
    assert reset_digest(reset_source) == V060_RESET_SHA256
    if tag_exists(TAG):
        kept_paths = [path for path in tagged_paths(TAG) if path not in SUPERSEDED]
        assert paths == kept_paths
        for path in paths:
            assert (ROOT / path).read_bytes() == tagged(TAG, path), path
        assert reset_digest(tagged(TAG, RESET_REL).decode()) == V060_RESET_SHA256
        assert tree_digest({p: tagged(TAG, p) for p in kept_paths}) == V060_TREE_SHA256


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


# ----------------------------------------------------------------------------- AC66_ZERO_NEW_RUNS
def _method(source: str, cls: str, name: str) -> ast.FunctionDef:
    klass = _top(source, cls)
    assert isinstance(klass, ast.ClassDef)
    for node in klass.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{cls}.{name} not found")


def test_ac170_both_live_legs_pass_a_reader_bound_to_the_peak_job() -> None:
    tree = ast.parse(LIVE.read_text(encoding="utf-8"))
    seen = 0
    for func in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        for call in _calls(func):
            if ast.unparse(call.func) != "ac66_rules.run_leg":
                continue
            seen += 1
            keywords = {k.arg: k.value for k in call.keywords}
            lam = keywords["runs"]
            assert isinstance(lam, ast.Lambda)
            assert not lam.args.args
            assert not lam.args.kwonlyargs
            assert lam.args.vararg is None
            body = lam.body
            assert isinstance(body, ast.Call)
            assert ast.unparse(body.func) == "peak_runner.run_ids"
            assert [ast.unparse(a) for a in body.args] == ["peak_job"]
            assert body.keywords == []
            params = {a.arg for a in func.args.args + func.args.kwonlyargs}
            assert not params & {"job", "training_job"}, func.name
    assert seen == 2

    reader = _method((ROOT / CONFTEST_REL).read_text(encoding="utf-8"), "PeakRunner", "run_ids")
    listed = [c for c in _calls(reader) if getattr(c.func, "attr", "") == "list_runs"]
    assert len(listed) == 1
    keywords = {k.arg: ast.unparse(k.value) for k in listed[0].keywords}
    assert set(keywords) == {"job_id", "limit"}
    assert keywords["job_id"] == "job.job_id"
    for banned in (
        "active_only",
        "completed_only",
        "start_time_from",
        "start_time_to",
        "run_type",
        "page_token",
    ):
        assert banned not in keywords


def test_ac171_v070_unit_tests_are_kept_with_their_asserts() -> None:
    for path, golden in V070_ASSERT_COUNTS.items():
        found = assert_counts((ROOT / path).read_text(encoding="utf-8"))
        for name, count in golden.items():
            assert name in found, (path, name)
            assert found[name] >= count, (path, name)
        if tag_exists(V070_TAG):
            assert assert_counts(tagged(V070_TAG, path).decode()) == golden, path


def test_ac171_rule_constants_and_reset_script_equal_v070() -> None:
    rules_source = RULES_FILE.read_text(encoding="utf-8")
    reset_source = (ROOT / RESET_REL).read_text(encoding="utf-8")
    assert rule_constants_digest(rules_source) == V070_RULE_CONSTANTS_SHA256
    # guard parts of the reset script, RESET_GUARD DA-68
    assert reset_digest(reset_source) == V070_RESET_SHA256
    if tag_exists(V070_TAG):
        assert rule_constants_digest(tagged(V070_TAG, RULES_REL).decode()) == (
            V070_RULE_CONSTANTS_SHA256
        )
        assert reset_digest(tagged(V070_TAG, RESET_REL).decode()) == V070_RESET_SHA256


def _flat(text: str) -> str:
    return " ".join(text.replace("`", "").split()).casefold()


def test_ac172_runbook_and_docstring_name_the_run_list_reads() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    eight = _section(text, "## 8. Evidence order (integration tests)")
    nine = _section(text, "## 9. Reset (user-run, AC-66)")
    leg_note = nine[nine.index("**If a leg refuses or fails.**") :]
    docstring = ast.get_docstring(ast.parse(LIVE.read_text(encoding="utf-8"))) or ""
    for where in (leg_note, docstring):
        flat = _flat(where)
        for needle in (
            "run list of smart_meter_peak_model",
            "again after its refusal or its job run",
            "0 new runs of smart_meter_peak_model",
            "names the new run ids",
            "1 new run of smart_meter_peak_model",
        ):
            assert needle in flat, needle
    for section in (eight, nine):
        for paragraph in re.split(r"\n\s*\n", section):
            if re.search(r"ac66|AC-66|\bleg\b", paragraph, flags=re.IGNORECASE):
                assert "list-runs" not in paragraph, paragraph


def test_ac172_leg_command_lines_carry_rp() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    seen = 0
    for heading in ("## 8. Evidence order (integration tests)", "## 9. Reset (user-run, AC-66)"):
        for line in _section(text, heading).splitlines():
            if line.startswith("pytest ") and re.search(r"ac66_(rerun|rebuild)_leg", line):
                seen += 1
                assert "-rP" in line, line
    assert seen == 3
