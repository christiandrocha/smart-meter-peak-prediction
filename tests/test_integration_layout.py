"""The integration tests are marked, deselected by default and name every in-scope AC (PR 3).

The integration tests themselves need a live workspace and are never run here. This file checks,
without a workspace, that they are collectable, carry the ``integration`` marker, are excluded from
the default run and from CI, and cover the acceptance criteria that the DESIGN assigns to them.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "tests" / "integration"
# Acceptance criteria with an integration test in the DESIGN Test Strategy (manifest 54 to 58).
EXPECTED_ACS = {5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22, 24, 25, 26, 27, 28, 30}
EXPECTED_ACS |= {31, 34, 35}
# PEAK_MODEL (manifest 37 to 40); AC-53 has a unit test only (DESIGN Test Strategy).
EXPECTED_ACS |= {36, 37, 39, 40, 41, 44, 47, 48, 49, 50, 51, 52, 54, 55, 56, 57, 58, 59, 60}
EXPECTED_ACS |= {62, 63, 64, 66}
TEST_FILES = sorted(INTEGRATION.glob("test_*.py"))
AC_NAME = re.compile(r"^test_ac(\d{2})_")


def _test_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def test_integration_files_exist_for_every_manifest_entry() -> None:
    names = {path.name for path in TEST_FILES}
    assert names == {
        "test_bronze_ingestion.py",
        "test_silver_tables.py",
        "test_gold_tables.py",
        "test_reprocessing.py",
        "test_deployment.py",
        "test_peak_data.py",
        "test_peak_training.py",
        "test_peak_scoring.py",
        "test_peak_deployment.py",
    }
    assert (INTEGRATION / "conftest.py").is_file()


def test_integration_every_test_is_marked_and_names_its_ac() -> None:
    for path in TEST_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        marked = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
            and ast.unparse(node.value) == "pytest.mark.integration"
            for node in tree.body
        )
        assert marked, f"{path.name} lacks pytestmark = pytest.mark.integration"
        for name in _test_functions(path):
            assert AC_NAME.match(name), f"{path.name}::{name} does not start with test_acNN_"


def test_integration_tests_cover_every_in_scope_ac() -> None:
    covered = {
        int(match.group(1))
        for path in TEST_FILES
        for name in _test_functions(path)
        if (match := AC_NAME.match(name))
    }
    assert EXPECTED_ACS <= covered, sorted(EXPECTED_ACS - covered)


def test_ac29_integration_modules_import_no_sdk_and_read_no_secret_files() -> None:
    """Collection needs no databricks-sdk; credentials come from the profile or environment."""
    for path in [*TEST_FILES, INTEGRATION / "conftest.py"]:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:  # top-level imports only; the SDK is imported inside fixtures
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith("databricks") for a in node.names), path.name
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("databricks"), path.name
        assert "load_dotenv" not in source
        assert not re.search(r"""["']\.env["']|/\.env\b""", source)  # no .env file access
        assert "DATABRICKS_TOKEN" not in source


def test_integration_default_run_and_ci_exclude_integration_marker() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]
    assert "not integration" in pytest_config["addopts"]
    assert any(marker.startswith("integration:") for marker in pytest_config["markers"])
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "-m integration" not in ci
    assert "tests/integration" not in ci


def _collect(*args: str, allowed: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(  # noqa: S603  (fixed arguments, the current interpreter)
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode in allowed, result.stdout + result.stderr
    return result.stdout


def test_integration_tests_are_collected_but_deselected_by_default() -> None:
    default = _collect("tests/integration", allowed=(0, 5))  # 5: nothing selected
    assert "tests/integration/test_" not in default
    assert "deselected" in default
    selected = _collect("-m", "integration", "-o", "addopts=", "tests/integration")
    assert "tests/integration/test_silver_tables.py::test_ac11_" in selected
    assert "tests/integration/test_reprocessing.py::test_ac27_after_" in selected
    assert "tests/integration/test_peak_data.py::test_ac66_after_" in selected
    assert "tests/integration/test_peak_training.py::test_ac55_uc_lineage" in selected
    assert "tests/integration/test_peak_scoring.py::test_ac57_after_" in selected
    assert "tests/integration/test_peak_deployment.py::test_ac62_" in selected
