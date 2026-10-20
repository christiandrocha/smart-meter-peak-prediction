"""Bundle, job, pipeline and notebook configuration (AC-10, AC-26, AC-28 to AC-30, I-14, DA-06).

The bundle YAML is parsed, not deployed. Values that the platform substitutes (``${var.x}``) are
resolved here from the variable defaults of ``databricks.yml``.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from smart_meter_peak_prediction import catalog_setup
from smart_meter_peak_prediction.config import PIPELINE_PREFIX, Settings, parse_utc

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = yaml.safe_load((ROOT / "databricks.yml").read_text(encoding="utf-8"))
JOB_FILE = ROOT / "resources" / "smart_meter_ingestion.job.yml"
PIPELINE_FILE = ROOT / "resources" / "smart_meter_silver_gold.pipeline.yml"
JOB = yaml.safe_load(JOB_FILE.read_text(encoding="utf-8"))["resources"]["jobs"]
PIPELINE = yaml.safe_load(PIPELINE_FILE.read_text(encoding="utf-8"))["resources"]["pipelines"]
NOTEBOOKS = ROOT / "notebooks"
DEV_PREFIX = re.compile(r"^\[dev [^\]]+\] ")


def job() -> dict:
    return JOB["smart_meter_ingestion"]


def tasks() -> dict[str, dict]:
    return {t["task_key"]: t for t in job()["tasks"]}


def default(variable: str) -> str:
    return str(BUNDLE["variables"][variable]["default"])


def resolve(value: str) -> str:
    return re.sub(r"\$\{var\.(\w+)\}", lambda m: default(m.group(1)), str(value))


def notebook_ast(name: str) -> ast.Module:
    return ast.parse((NOTEBOOKS / name).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- AC-26
def test_ac26_single_serverless_triggered_pipeline() -> None:
    assert list(PIPELINE) == ["smart_meter_silver_gold"]
    pipeline = PIPELINE["smart_meter_silver_gold"]
    assert pipeline["serverless"] is True
    assert pipeline["continuous"] is False
    assert pipeline["event_log"]["name"] == "pipeline_event_log"
    assert not (ROOT / "resources" / "jobs.yml").exists()  # template job removed


def test_ac26_pipeline_configuration_keys_are_known_settings_and_utc() -> None:
    configuration = PIPELINE["smart_meter_silver_gold"]["configuration"]
    assert configuration["spark.sql.session.timeZone"] == "UTC"  # DA-07
    known = {PIPELINE_PREFIX + f.name for f in fields(Settings)}
    smart = {k for k in configuration if k.startswith(PIPELINE_PREFIX)}
    assert smart - {PIPELINE_PREFIX + "src_path"} <= known
    resolved = {k: resolve(v) for k, v in configuration.items() if k != "smart_meter.src_path"}
    settings = Settings.from_pipeline_configuration(resolved)  # no unknown-key error
    assert settings == Settings()
    assert configuration["smart_meter.src_path"] == "${workspace.file_path}/src"


# ----------------------------------------------------------------------------- AC-28
def test_ac28_job_and_pipeline_names_and_schedule() -> None:
    assert job()["name"] == "smart_meter_ingestion"
    assert PIPELINE["smart_meter_silver_gold"]["name"] == "smart_meter_silver_gold"
    schedule = job()["schedule"]
    assert schedule["quartz_cron_expression"] == "0 0 6 * * ?"
    assert schedule["timezone_id"] == "UTC"
    assert job()["max_concurrent_runs"] == 1
    assert job()["email_notifications"]["on_failure"]
    # Development mode (target dev) prefixes display names and pauses the schedule; the test of the
    # deployed names strips the prefix with the anchored pattern of the DESIGN.
    assert BUNDLE["targets"]["dev"]["mode"] == "development"


def test_ac28_no_more_than_five_concurrent_tasks() -> None:
    graph = {key: set(_depends(task)) for key, task in tasks().items()}
    levels: dict[str, int] = {}

    def level(key: str) -> int:
        if key not in levels:
            levels[key] = 1 + max((level(d) for d in graph[key]), default=-1)
        return levels[key]

    widths: dict[int, int] = {}
    for key in graph:
        widths[level(key)] = widths.get(level(key), 0) + 1
    assert max(widths.values()) <= 5
    assert len(tasks()) == 4
    assert list(tasks()) == ["setup_catalog", "ingest_files", "ingest_kafka", "refresh_silver_gold"]


def _depends(task: dict) -> list[str]:
    return [d["task_key"] for d in task.get("depends_on", [])]


def test_ac28_task_dependencies_and_pipeline_task() -> None:
    t = tasks()
    assert _depends(t["setup_catalog"]) == []
    assert _depends(t["ingest_files"]) == ["setup_catalog"]
    assert _depends(t["ingest_kafka"]) == ["setup_catalog"]
    assert sorted(_depends(t["refresh_silver_gold"])) == ["ingest_files", "ingest_kafka"]
    assert t["refresh_silver_gold"]["pipeline_task"]["pipeline_id"] == (
        "${resources.pipelines.smart_meter_silver_gold.id}"
    )
    assert t["refresh_silver_gold"]["pipeline_task"]["full_refresh"] is False
    assert [t[k]["timeout_seconds"] for k in t] == [600, 1800, 840, 2700]
    assert [t[k]["max_retries"] for k in t] == [1, 1, 0, 0]


def test_ac28_layout_variables_match_sample_plan() -> None:
    defaults = Settings()
    for field in fields(Settings):
        if field.name in BUNDLE["variables"]:
            assert default(field.name) == getattr(defaults, field.name), field.name
    assert set(BUNDLE["variables"]) == {f.name for f in fields(Settings)}
    plan = json.loads((ROOT / "config" / "sample_plan.json").read_text(encoding="utf-8"))
    assert parse_utc(default("study_start")) == parse_utc(plan["period_start"])
    assert parse_utc(default("study_end")) == parse_utc(plan["period_end"])
    assert (default("catalog"), default("bronze_schema"), default("silver_schema")) == (
        "smart_meter_dev",
        "bronze",
        "silver",
    )
    assert (default("gold_schema"), default("ml_schema")) == ("gold", "ml")


def test_ac04_bundle_cutoff_default_equals_sample_plan() -> None:
    plan = json.loads((ROOT / "config" / "sample_plan.json").read_text(encoding="utf-8"))
    assert parse_utc(default("cutoff")) == parse_utc(plan["cutoff"])
    assert PIPELINE["smart_meter_silver_gold"]["configuration"]["smart_meter.cutoff"] == (
        "${var.cutoff}"
    )


def test_ac28_job_parameters_reach_declared_notebook_widgets() -> None:
    """Every base parameter of a notebook task is a widget the notebook reads (names equal)."""
    for key, task in tasks().items():
        if "notebook_task" not in task:
            continue
        path = (ROOT / "resources" / task["notebook_task"]["notebook_path"]).resolve()
        assert path.is_file(), key
        strings = {
            n.value
            for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        for parameter, value in task["notebook_task"]["base_parameters"].items():
            assert parameter in strings, (key, parameter)
            assert resolve(value) == resolve(value).strip()
        parameters = {
            p: resolve(v) for p, v in notebook_parameters(task).items() if p != "src_path"
        }
        assert Settings.from_mapping(parameters) == Settings()
        widgets = widget_names(path)
        assert widgets <= set(parameters), (key, widgets - set(parameters))


def notebook_parameters(task: dict) -> dict:
    return task["notebook_task"]["base_parameters"]


def widget_names(path: Path) -> set[str]:
    """Names in the notebook's ``_widget_names`` tuple (the widgets it creates from Settings)."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_widget_names" for t in node.targets
        ):
            return {e.value for e in node.value.elts}
    return set()


def test_ac28_first_deploy_three_steps_are_supported_by_setup_notebook() -> None:
    """DA-06: setup runs by hand with its defaults, and is the first job task afterwards."""
    tree = notebook_ast("setup_catalog.py")
    source = (NOTEBOOKS / "setup_catalog.py").read_text(encoding="utf-8")
    assert "DA-06" in source
    assert "setup_statements(settings)" in source
    # Widgets default to the Settings defaults and src_path may stay empty (manual run).
    assert 'dbutils.widgets.text("src_path", "")' in source
    assert "dbutils.widgets.text(_name, getattr(_defaults, _name))" in source
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
    statements = catalog_setup.setup_statements(Settings())
    assert statements[0] == "CREATE CATALOG IF NOT EXISTS smart_meter_dev"
    # Terraform needs the catalog before the pipeline: the first deploy leaves the pipeline
    # configured with the catalog variable only, so step 3 succeeds after step 2.
    assert PIPELINE["smart_meter_silver_gold"]["catalog"] == "${var.catalog}"


def test_ac28_prod_target_is_documented_only() -> None:
    assert list(BUNDLE["targets"]) == ["dev"]
    text = (ROOT / "databricks.yml").read_text(encoding="utf-8")
    assert any(line.lstrip().startswith("# prod:") for line in text.splitlines())
    assert BUNDLE["targets"]["dev"]["default"] is True


# ----------------------------------------------------------------------------- AC-10
def test_ac10_kafka_task_fails_within_15_minutes() -> None:
    kafka = tasks()["ingest_kafka"]
    assert kafka["timeout_seconds"] <= 900
    assert kafka["max_retries"] == 0
    assert "ingest_kafka" in _depends(tasks()["refresh_silver_gold"])


def test_ac10_notebooks_and_pipeline_have_no_try_except() -> None:
    """I-14: a stream failure escapes a Python try, so the task fails and the job handles it."""
    sources = sorted(NOTEBOOKS.glob("*.py")) + [ROOT / "pipelines" / "meter_pipeline.py"]
    assert {p.name for p in sources} >= {
        "setup_catalog.py",
        "ingest_files.py",
        "ingest_kafka.py",
        "meter_pipeline.py",
    }
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Try)]
        assert not offenders, f"{path.name}: try at line(s) {offenders}"


def test_ac10_stream_notebooks_use_the_available_now_writer() -> None:
    for name, tables in (
        ("ingest_files.py", ("bronze_files_readings", "bronze_files_households")),
        ("ingest_kafka.py", ("bronze_kafka_readings",)),
    ):
        source = (NOTEBOOKS / name).read_text(encoding="utf-8")
        assert source.count("bronze.run_available_now(") == len(tables)
        for table in tables:
            assert f"settings.{table}" in source
        assert "writeStream" not in source  # only the library writer starts streams
        assert "awaitTermination" not in source
        assert "processingTime" not in source


# ----------------------------------------------------------------------------- AC-29
def test_ac29_bundle_reads_kafka_credentials_from_secret_scope() -> None:
    """The bundle holds the scope name only; the notebook reads each credential from the scope."""
    texts = [
        p.read_text(encoding="utf-8") for p in (ROOT / "databricks.yml", JOB_FILE, PIPELINE_FILE)
    ]
    for text in texts:
        assert "secrets/" not in text
        assert "{{secrets" not in text
        for key in ("kafka-bootstrap-servers", "kafka-sasl-username", "kafka-sasl-password"):
            assert key not in text  # the bundle names the scope only, not its keys
        assert "kafka-ca-pem" not in text
    assert default("secret_scope") == "smart_meter"
    kafka_parameters = tasks()["ingest_kafka"]["notebook_task"]["base_parameters"]
    assert kafka_parameters["secret_scope"] == "${var.secret_scope}"  # noqa: S105
    # No other task receives the scope.
    for key, task in tasks().items():
        if key != "ingest_kafka":
            assert "secret_scope" not in task.get("notebook_task", {}).get("base_parameters", {})

    source = (NOTEBOOKS / "ingest_kafka.py").read_text(encoding="utf-8")
    calls = [
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "get"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "secrets"
    ]
    keys = sorted(c.args[1].value for c in calls)
    assert keys == [
        "kafka-bootstrap-servers",
        "kafka-ca-pem",
        "kafka-sasl-password",
        "kafka-sasl-username",
    ]
    assert all(
        isinstance(c.args[0], ast.Attribute) and c.args[0].attr == "secret_scope" for c in calls
    )


def _is_secret_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "secrets"
    )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def test_ac29_kafka_notebook_never_prints_options_or_secrets() -> None:
    tree = notebook_ast("ingest_kafka.py")
    tainted = {"kafka_options"}
    for node in ast.walk(tree):  # names assigned from a secret read or from the options
        if isinstance(node, ast.Assign) and any(_is_secret_call(n) for n in ast.walk(node.value)):
            tainted |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    sinks = {"print", "display", "repr", "str", "show", "info", "warning", "error", "debug"}
    for node in ast.walk(tree):
        if _call_name(node) in sinks:
            inner = list(ast.walk(node))
            used = {n.id for n in inner if isinstance(n, ast.Name)}
            assert not used & tainted, f"line {node.lineno} may print a secret"
            assert not any(_is_secret_call(n) for n in inner), f"line {node.lineno} prints a secret"
    assert "logging" not in (NOTEBOOKS / "ingest_kafka.py").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- AC-30
def test_ac30_job_timeout_within_60_minutes() -> None:
    assert job()["timeout_seconds"] <= 3600
    assert all(t["timeout_seconds"] < job()["timeout_seconds"] for t in tasks().values())


@pytest.mark.parametrize("name", ["setup_catalog.py", "ingest_files.py", "ingest_kafka.py"])
def test_notebooks_set_and_assert_utc_session_time_zone(name: str) -> None:
    """DESIGN: the session time zone is UTC in every task (DA-07)."""
    source = (NOTEBOOKS / name).read_text(encoding="utf-8")
    assert 'spark.conf.set("spark.sql.session.timeZone", "UTC")' in source
    assert 'assert spark.conf.get("spark.sql.session.timeZone") == "UTC"' in source
