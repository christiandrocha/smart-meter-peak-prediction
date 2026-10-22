"""PEAK_MODEL bundle resources and notebooks (AC-62, AC-63, G-01, I-14, DA-14, DA-17).

The YAML is parsed, not deployed. ``${var.x}`` is resolved from the variable defaults of
``databricks.yml``. The live counterpart of AC-62 is ``tests/integration/test_peak_deployment.py``
(PR 3).
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from smart_meter_peak_prediction import peak_config
from smart_meter_peak_prediction.config import Settings
from smart_meter_peak_prediction.peak_config import PeakParameters

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
NOTEBOOKS = ROOT / "notebooks"
BUNDLE = yaml.safe_load((ROOT / "databricks.yml").read_text(encoding="utf-8"))
DAILY_FILE = RESOURCES / "smart_meter_peak_model.job.yml"
TRAINING_FILE = RESOURCES / "smart_meter_peak_model_training.job.yml"
DAILY = yaml.safe_load(DAILY_FILE.read_text(encoding="utf-8"))["resources"]["jobs"][
    "smart_meter_peak_model"
]
TRAINING = yaml.safe_load(TRAINING_FILE.read_text(encoding="utf-8"))["resources"]["jobs"][
    "smart_meter_peak_model_training"
]

PEAK_NOTEBOOKS = (
    "check_pipeline_idle.py",
    "ingest_weather.py",
    "build_weather_silver.py",
    "build_features.py",
    "build_labels.py",
    "score_predictions.py",
    "train_model.py",
)
ML_NOTEBOOKS = ("build_features.py", "score_predictions.py", "train_model.py")

# SHA-256 of the training job file at tag v0.2.0 (AC-78: PEAK_MODEL_CONCURRENCY must not change it).
TRAINING_SHA256 = "ccc7c66d8324299c54567c67ce8005bce1e5c63a4a163fc62db62c950524040a"

# SHA-256 of the METER_INGESTION files at tag v0.1.0 (AC-62: they must not change).
PINNED_SHA256 = {
    "resources/smart_meter_ingestion.job.yml": (
        "a2e8f0dc13e9b4e522eca68a4d445546badec85aca4f83c745245acc143dc817"
    ),
    "resources/smart_meter_silver_gold.pipeline.yml": (
        "37f24bc0b54ab6174a2726de86c401300b62a64d1286d02bc8d33032a4d9cd1e"
    ),
    "databricks.yml": "ea54b04cdec74c544404831f8652969fa5eaa780253fa22d22483f412a1cf4ab",
}
CLUSTER_KEYS = {"job_cluster_key", "new_cluster", "existing_cluster_id", "job_clusters"}


def tasks(job: dict) -> dict[str, dict]:
    return {t["task_key"]: t for t in job["tasks"]}


def depends(task: dict) -> list[str]:
    return [d["task_key"] for d in task.get("depends_on", [])]


def default(variable: str) -> str:
    return str(BUNDLE["variables"][variable]["default"])


def resolve(value: str) -> str:
    return re.sub(r"\$\{var\.(\w+)\}", lambda m: default(m.group(1)), str(value))


def levels(job: dict) -> dict[str, int]:
    graph = {key: depends(task) for key, task in tasks(job).items()}
    found: dict[str, int] = {}

    def level(key: str) -> int:
        if key not in found:
            found[key] = 1 + max((level(d) for d in graph[key]), default=-1)
        return found[key]

    for key in graph:
        level(key)
    return found


def ancestors(job: dict, key: str) -> set[str]:
    seen: set[str] = set()
    todo = list(depends(tasks(job)[key]))
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            todo.extend(depends(tasks(job)[current]))
    return seen


def source(name: str) -> str:
    return (NOTEBOOKS / name).read_text(encoding="utf-8")


def _literal_tuple(tree: ast.AST, variable: str) -> tuple[str, ...] | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == variable for t in node.targets
        ):
            return tuple(e.value for e in node.value.elts)
    return None


def widget_names(name: str) -> tuple[str, ...]:
    """Widgets a notebook really declares: the loop tuples plus literal ``widgets.text`` names.

    The ``_widget_names`` tuple must equal that set, so it cannot drift from the code.
    """
    tree = ast.parse(source(name))
    declared: set[str] = set()
    for variable in ("_settings_names", "_parameter_names"):
        declared |= set(_literal_tuple(tree, variable) or ())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value != "src_path"
        ):
            declared.add(node.args[0].value)
    listed = _literal_tuple(tree, "_widget_names")
    if listed is None:  # the two Settings-only notebooks declare the tuple only
        raise AssertionError(f"{name} declares no _widget_names tuple")
    if _literal_tuple(tree, "_settings_names") is not None:
        assert set(listed) == declared, (name, set(listed) ^ declared)
    return tuple(listed)


def task_for(notebook: str) -> tuple[dict, dict]:
    for job in (DAILY, TRAINING):
        for task in job["tasks"]:
            if task.get("notebook_task", {}).get("notebook_path") == f"../notebooks/{notebook}":
                return job, task
    raise AssertionError(f"no task runs {notebook}")


def job_parameters(job: dict) -> dict[str, str]:
    return {p["name"]: p["default"] for p in job.get("parameters", [])}


# ----------------------------------------------------------------------------- AC-62
def test_ac62_daily_job_graph_schedule_and_pipeline_dependency() -> None:
    assert DAILY["name"] == "smart_meter_peak_model"
    t = tasks(DAILY)
    assert list(t) == [
        "check_pipeline_idle",
        "refresh_silver_gold",
        "ingest_weather",
        "build_weather_silver",
        "build_features",
        "build_labels",
        "score_predictions",
    ]
    assert depends(t["check_pipeline_idle"]) == []
    assert depends(t["refresh_silver_gold"]) == ["check_pipeline_idle"]
    assert depends(t["ingest_weather"]) == []
    assert depends(t["build_weather_silver"]) == ["ingest_weather"]
    assert sorted(depends(t["build_features"])) == ["build_weather_silver", "refresh_silver_gold"]
    assert depends(t["build_labels"]) == ["refresh_silver_gold"]
    assert sorted(depends(t["score_predictions"])) == ["build_features", "build_labels"]
    widths: dict[int, int] = {}
    for level in levels(DAILY).values():
        widths[level] = widths.get(level, 0) + 1
    assert max(widths.values()) <= 5
    assert max(widths.values()) == 2  # DESIGN, Concurrency
    assert "refresh_silver_gold" in ancestors(DAILY, "score_predictions")
    assert "check_pipeline_idle" in ancestors(DAILY, "score_predictions")
    pipeline_task = t["refresh_silver_gold"]["pipeline_task"]
    assert pipeline_task["pipeline_id"] == "${resources.pipelines.smart_meter_silver_gold.id}"
    assert pipeline_task["full_refresh"] is False
    assert t["refresh_silver_gold"]["max_retries"] == 1
    assert t["refresh_silver_gold"]["min_retry_interval_millis"] == 600000  # FAILED only (DA-13)
    schedule = DAILY["schedule"]
    assert schedule["quartz_cron_expression"] == "0 0 8 * * ?"
    assert schedule["timezone_id"] == "UTC"
    assert DAILY["max_concurrent_runs"] == 1
    assert DAILY["email_notifications"]["on_failure"]
    assert DAILY["timeout_seconds"] == 7200
    assert [t[k]["timeout_seconds"] for k in t] == [300, 2700, 900, 900, 1800, 1800, 1800]
    assert all(t[k]["timeout_seconds"] < DAILY["timeout_seconds"] for k in t)
    # Serverless: no cluster of any kind on the job or its tasks.
    assert not CLUSTER_KEYS & set(DAILY)
    for task in DAILY["tasks"]:
        assert not CLUSTER_KEYS & set(task), task["task_key"]


def test_ac62_training_is_on_demand_only() -> None:
    assert TRAINING["name"] == "smart_meter_peak_model_training"
    assert "schedule" not in TRAINING
    assert "trigger" not in TRAINING
    assert "continuous" not in TRAINING
    assert TRAINING["max_concurrent_runs"] == 1
    assert list(tasks(TRAINING)) == ["train_model"]
    train = tasks(TRAINING)["train_model"]
    assert train["max_retries"] == 0  # a retry would register a second identical version
    assert train["timeout_seconds"] == 3000
    assert train["timeout_seconds"] < TRAINING["timeout_seconds"] == 3600
    assert (
        max(
            sum(1 for v in levels(TRAINING).values() if v == level)
            for level in levels(TRAINING).values()
        )
        <= 5
    )
    assert not CLUSTER_KEYS & set(TRAINING)
    assert not CLUSTER_KEYS & set(train)
    for task in DAILY["tasks"]:  # no training in the scheduled job
        path = task.get("notebook_task", {}).get("notebook_path", "")
        assert not path.endswith("train_model.py"), task["task_key"]
    assert not [k for k in tasks(DAILY) if "train" in k]


def test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged() -> None:
    pipelines: list[str] = []
    for path in sorted(RESOURCES.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        pipelines += list(data["resources"].get("pipelines", {}))
    assert pipelines == ["smart_meter_silver_gold"]
    for relative, expected in PINNED_SHA256.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    # When the tag is present the files also equal their content at v0.1.0 (a clone without tags
    # still has the pinned digests above).
    tag = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", "v0.1.0^{commit}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if tag.returncode == 0:
        for relative in PINNED_SHA256:
            shown = subprocess.run(  # noqa: S603
                ["git", "show", f"v0.1.0:{relative}"],  # noqa: S607
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            assert shown == (ROOT / relative).read_bytes(), relative


def test_ac62_peak_model_adds_no_bundle_variable_and_uses_the_layout_variables() -> None:
    """PEAK_MODEL parameters are job parameters; the variable set stays equal to ``Settings``."""
    assert set(BUNDLE["variables"]) == {f.name for f in fields(Settings)}
    for job in (DAILY, TRAINING):
        text = yaml.safe_dump(job)
        used = set(re.findall(r"\$\{var\.(\w+)\}", text))
        assert used <= set(BUNDLE["variables"])
        assert "secret" not in text.lower()  # workspace identity only


# ----------------------------------------------------------------------------- AC-63 / DA-14
def test_ac63_label_and_eligibility_parameters_are_job_parameters() -> None:
    parameters = job_parameters(DAILY)
    for name in ("label_threshold", "coverage_min"):
        assert name in parameters
    assert set(parameters) == {
        "label_threshold",
        "baseline_day_count",
        "label_lookback_weeks",
        "coverage_min",
        "zero_share_max",
        "eligibility_months",
        "target_date",
        "target_date_end",
    }
    assert set(job_parameters(TRAINING)) == {
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
        "random_seed",
    }
    # Every job parameter is a PeakParameters field, and the defaults are the library defaults.
    known = {f.name for f in fields(PeakParameters)}
    for job in (DAILY, TRAINING):
        assert set(job_parameters(job)) <= known
        assert PeakParameters.from_mapping(job_parameters(job)) == PeakParameters()
    # The scoring-only parameters stay out of the training job (D-38) and default to "empty".
    assert not {"target_date", "target_date_end"} & set(job_parameters(TRAINING))
    assert job_parameters(DAILY)["target_date"] == job_parameters(DAILY)["target_date_end"] == ""
    # build_labels reads them as widgets, with no hard-coded value.
    labels_widgets = set(widget_names("build_labels.py"))
    assert {
        "label_threshold",
        "baseline_day_count",
        "label_lookback_weeks",
        "coverage_min",
        "zero_share_max",
        "eligibility_months",
    } <= labels_widgets
    text = source("build_labels.py")
    assert "PeakParameters.from_mapping(" in text
    assert "from_widgets" not in text  # the library reads every field; only declared names here
    assert "1.3" not in text
    assert "label_properties()" in text  # printed and returned


@pytest.mark.parametrize("name", PEAK_NOTEBOOKS)
def test_ac63_job_parameters_reach_declared_notebook_widgets(name: str) -> None:
    """Each widget a notebook reads is a task base parameter or a job parameter (DA-14)."""
    job, task = task_for(name)
    base = task["notebook_task"]["base_parameters"]
    provided = set(base) | set(job_parameters(job))
    widgets = set(widget_names(name))
    assert widgets <= provided, (name, widgets - provided)
    # Every base parameter is read: a widget of that name exists (or is the src_path widget).
    for parameter, value in base.items():
        assert parameter == "src_path" or parameter in widgets, (name, parameter)
        assert resolve(value) == resolve(value).strip()
    # Settings widgets resolve to the Settings defaults (A-09 fallback changes variables only).
    settings = {k: resolve(v) for k, v in base.items() if k in {f.name for f in fields(Settings)}}
    assert Settings.from_mapping(settings) == Settings()

    # Notebooks only declare widgets they parse, with Settings fields or PeakParameters fields.
    known = {f.name for f in fields(Settings)} | {f.name for f in fields(PeakParameters)}
    assert widgets - {"experiment_path", "git_commit", "ingestion_job_id", "pipeline_id"} <= known


def test_ac63_training_task_receives_git_commit_and_experiment_path() -> None:
    base = tasks(TRAINING)["train_model"]["notebook_task"]["base_parameters"]
    assert base["git_commit"] == "${bundle.git.commit}"  # DA-17, G-05
    assert base["experiment_path"] == "/Users/${workspace.current_user.userName}/" + (
        peak_config.EXPERIMENT
    )
    assert peak_config.experiment_path("u@x") == "/Users/u@x/smart_meter_peak_model"


def test_ac63_every_peak_notebook_task_exists_and_points_at_a_notebook() -> None:
    paths = [
        t["notebook_task"]["notebook_path"]
        for job in (DAILY, TRAINING)
        for t in job["tasks"]
        if "notebook_task" in t
    ]
    assert sorted(Path(p).name for p in paths) == sorted(PEAK_NOTEBOOKS)
    for path in paths:
        assert (RESOURCES / path).resolve().is_file(), path


# ----------------------------------------------------------------------------- G-01 pins
@pytest.mark.parametrize("name", PEAK_NOTEBOOKS)
def test_g01_pip_pins_equal_pinned_requirements_and_restart_precedes_path_setup(name: str) -> None:
    """ADR 0007: the ML notebooks pin the platform libraries, restart, and check them (G-01)."""
    text = source(name)
    pips = re.findall(r"^# MAGIC %pip install --quiet (.+)$", text, flags=re.MULTILINE)
    if name not in ML_NOTEBOOKS:
        assert pips == []
        assert "restartPython" not in text
        return
    assert len(pips) == 1
    assert tuple(pips[0].split()) == peak_config.PINNED_REQUIREMENTS
    assert pips[0].split() == [
        "databricks-feature-engineering==0.18.2",
        "scikit-learn==1.3.0",
    ]
    assert text.index("%pip install") < text.index("dbutils.library.restartPython()")
    assert text.index("dbutils.library.restartPython()") < text.index("sys.path.insert(")
    assert text.index("dbutils.library.restartPython()") < text.index("import json")
    assert "peak_config.check_versions()" in text


@pytest.mark.parametrize("job", [DAILY, TRAINING], ids=["daily", "training"])
def test_g01_every_notebook_task_runs_on_serverless_environment_version_2(job: dict) -> None:
    """ADR 0007, D-19: the pins only install on the environment spike 05 validated (Python 3.11).

    Without an explicit environment the jobs get a Python 3.12 environment, where
    scikit-learn==1.3.0 has no wheel and the %pip cell fails.
    """
    environments = {e["environment_key"]: e["spec"] for e in job["environments"]}
    assert environments == {"peak_model_env": {"environment_version": "2"}}
    notebook_tasks = [t for t in job["tasks"] if "notebook_task" in t]
    assert notebook_tasks
    assert {t["task_key"]: t.get("environment_key") for t in notebook_tasks} == {
        t["task_key"]: "peak_model_env" for t in notebook_tasks
    }


def test_ac53_training_task_is_never_retried_by_the_platform() -> None:
    """ADR 0008, D-21: a retry would register a second version; serverless auto-optimization
    retries failed tasks unless it is disabled, even with ``max_retries: 0``."""
    (train,) = TRAINING["tasks"]
    assert train["max_retries"] == 0
    assert train["disable_auto_optimization"] is True


# ----------------------------------------------------------------------------- UTC, I-14, wiring
@pytest.mark.parametrize("name", PEAK_NOTEBOOKS)
def test_ac37_notebooks_set_and_assert_utc_and_have_no_try_except(name: str) -> None:
    text = source(name)
    assert 'spark.conf.set("spark.sql.session.timeZone", "UTC")' in text
    assert 'assert spark.conf.get("spark.sql.session.timeZone") == "UTC"' in text
    assert not [n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Try)]
    assert "dbutils.notebook.exit(" in text  # counts and parameters reach the Jobs API
    assert "dbutils.secrets" not in text


def test_ac62_notebooks_and_sources_never_import_spike_code() -> None:
    files = [*(NOTEBOOKS / n for n in PEAK_NOTEBOOKS), *(ROOT / "src").rglob("*.py")]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not [n for n in names if n.split(".")[0] == "spikes"], path.name


def test_ac62_library_calls_used_by_the_notebooks_exist() -> None:
    """Wiring: each ``module.function`` a notebook calls exists in the package (PR 1 hand-off)."""
    import importlib

    package = "smart_meter_peak_prediction"
    modules = {
        "bronze",
        "delta_sync",
        "features",
        "labels",
        "peak_config",
        "peak_setup",
        "pipeline_guard",
        "registry",
        "scoring",
        "training",
        "weather",
    }
    for name in PEAK_NOTEBOOKS:
        for node in ast.walk(ast.parse(source(name))):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in modules
            ):
                module = importlib.import_module(f"{package}.{node.value.id}")
                assert hasattr(module, node.attr), f"{name}: {node.value.id}.{node.attr}"


# ----------------------------------------------------------------------------- AC-68, AC-78
def test_ac68_pre_check_task_precedes_the_pipeline_and_is_never_retried() -> None:
    """ADR 0012: first task, one attempt, ids from the bundle."""
    t = tasks(DAILY)
    pre = t["check_pipeline_idle"]
    assert "notebook_task" in pre
    assert "pipeline_task" not in pre
    assert pre["notebook_task"]["notebook_path"] == "../notebooks/check_pipeline_idle.py"
    assert pre["max_retries"] == 0
    assert pre["disable_auto_optimization"] is True  # max_retries 0 alone did not stop it (D-21)
    assert pre["environment_key"] == "peak_model_env"
    assert pre["timeout_seconds"] == 300
    assert depends(pre) == []
    assert depends(t["refresh_silver_gold"]) == ["check_pipeline_idle"]
    for key in ("build_features", "build_labels", "score_predictions"):
        assert "check_pipeline_idle" in ancestors(DAILY, key), key
    assert depends(t["ingest_weather"]) == []  # unchanged since v0.2.0
    assert depends(t["build_weather_silver"]) == ["ingest_weather"]
    widths: dict[int, int] = {}
    for level in levels(DAILY).values():
        widths[level] = widths.get(level, 0) + 1
    assert max(widths.values()) == 2
    assert DAILY["schedule"]["quartz_cron_expression"] == "0 0 8 * * ?"
    assert DAILY["schedule"]["timezone_id"] == "UTC"
    assert DAILY["max_concurrent_runs"] == 1
    assert pre["notebook_task"]["base_parameters"] == {
        "src_path": "${workspace.file_path}/src",
        "ingestion_job_id": "${resources.jobs.smart_meter_ingestion.id}",
        "pipeline_id": "${resources.pipelines.smart_meter_silver_gold.id}",
    }


def test_ac78_ingestion_pipeline_and_training_definitions_unchanged_and_retry_kept() -> None:
    for relative, expected in PINNED_SHA256.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    training = TRAINING_FILE.relative_to(ROOT).as_posix()
    assert hashlib.sha256(TRAINING_FILE.read_bytes()).hexdigest() == TRAINING_SHA256, training
    tag = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", "v0.2.0^{commit}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if tag.returncode == 0:
        shown = subprocess.run(  # noqa: S603
            ["git", "show", f"v0.2.0:{training}"],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert shown == TRAINING_FILE.read_bytes()
    refresh = tasks(DAILY)["refresh_silver_gold"]
    assert refresh["max_retries"] == 1
    assert refresh["min_retry_interval_millis"] == 600000
    text = " ".join(DAILY_FILE.read_text(encoding="utf-8").split())
    assert "is not retried" in text  # the refused update, D-41
