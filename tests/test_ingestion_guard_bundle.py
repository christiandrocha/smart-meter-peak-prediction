"""Ingestion job with the reverse pre-check (AC-81 to AC-85; G-26, G-27, ADR 0013).

The YAML is parsed, not deployed. The live counterpart is
``tests/integration/test_ingestion_guard_live.py`` (AC-94). The v0.1.0 job file is kept as a
byte copy in ``tests/support`` so the structural comparison also runs in a clone without tags.
"""

from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
JOB_REL = "resources/smart_meter_ingestion.job.yml"
JOB_FILE = ROOT / JOB_REL
FIXTURE = ROOT / "tests" / "support" / "ingestion_job_v0.1.0.yml"
PIPELINE_REF = "${resources.pipelines.smart_meter_silver_gold.id}"
CLUSTER_KEYS = {"job_cluster_key", "new_cluster", "existing_cluster_id", "job_clusters"}
CHECK = "check_silver_gold_idle"
ORDER = ["setup_catalog", "ingest_files", "ingest_kafka", CHECK, "refresh_silver_gold"]

# SHA-256 of the ingestion job file at the INGESTION_GUARD feature commit. It replaces the v0.1.0
# pin of AC-62 and AC-78 in tests/test_peak_bundle.py (FR-51, D-53); once tag v0.4.0 exists the file
# must also equal its content there.
INGESTION_SHA256 = "dac24eafa4b152a37cb0d33bd59f875b2e29f4f3a2f67cd5954c98b564b2d4b9"
V010_INGESTION_SHA256 = "a2e8f0dc13e9b4e522eca68a4d445546badec85aca4f83c745245acc143dc817"
# (tag, path, SHA-256 at the tag): everything INGESTION_GUARD must leave unchanged.
PINS = [
    (
        "v0.1.0",
        "resources/smart_meter_silver_gold.pipeline.yml",
        "37f24bc0b54ab6174a2726de86c401300b62a64d1286d02bc8d33032a4d9cd1e",
    ),
    (
        "v0.1.0",
        "databricks.yml",
        "ea54b04cdec74c544404831f8652969fa5eaa780253fa22d22483f412a1cf4ab",
    ),
    (
        "v0.2.0",
        "resources/smart_meter_peak_model_training.job.yml",
        "ccc7c66d8324299c54567c67ce8005bce1e5c63a4a163fc62db62c950524040a",
    ),
    (
        "v0.3.0",
        "resources/smart_meter_peak_model.job.yml",
        "2cdfb63ed07d12962cec08eeb93d4babc29505fd7188bc5702a562fc1fc5ff98",
    ),
    (
        "v0.3.0",
        "notebooks/check_pipeline_idle.py",
        "3947e535e1b5340667094c3a35ac358df4ba4c3997529f34b43aa700b47e1620",
    ),
]


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["resources"]


JOB = load(JOB_FILE)["jobs"]["smart_meter_ingestion"]
OLD = load(FIXTURE)["jobs"]["smart_meter_ingestion"]


def tasks(job: dict = JOB) -> dict[str, dict]:
    return {t["task_key"]: t for t in job["tasks"]}


def depends(task: dict) -> list[str]:
    return [d["task_key"] for d in task.get("depends_on", [])]


def ancestors(key: str) -> set[str]:
    seen: set[str] = set()
    todo = depends(tasks()[key])
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            todo.extend(depends(tasks()[current]))
    return seen


def widest_level() -> int:
    found: dict[str, int] = {}

    def level(key: str) -> int:
        if key not in found:
            found[key] = 1 + max((level(d) for d in depends(tasks()[key])), default=-1)
        return found[key]

    counts: dict[int, int] = {}
    for key in tasks():
        counts[level(key)] = counts.get(level(key), 0) + 1
    return max(counts.values())


def tag_exists(tag: str) -> bool:
    done = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def tagged(tag: str, path: str) -> bytes:
    return subprocess.run(  # noqa: S603
        ["git", "show", f"{tag}:{path}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------------- AC-81
def test_ac81_ingestion_graph_places_the_check_before_the_pipeline_task() -> None:
    t = tasks()
    assert list(t) == ORDER
    assert depends(t["setup_catalog"]) == []
    assert depends(t["ingest_files"]) == ["setup_catalog"]
    assert depends(t["ingest_kafka"]) == ["setup_catalog"]
    assert sorted(depends(t[CHECK])) == ["ingest_files", "ingest_kafka"]
    assert depends(t["refresh_silver_gold"]) == [CHECK]
    assert "ingest_kafka" in ancestors("refresh_silver_gold")
    assert not any("run_if" in task for task in t.values())
    assert "notebook_task" in t[CHECK]
    assert "pipeline_task" not in t[CHECK]
    assert widest_level() == 2
    for key in ("schedule", "max_concurrent_runs", "timeout_seconds", "email_notifications"):
        assert JOB[key] == OLD[key], key
    assert JOB["schedule"]["quartz_cron_expression"] == "0 0 6 * * ?"
    assert JOB["schedule"]["timezone_id"] == "UTC"
    assert JOB["max_concurrent_runs"] == 1
    assert JOB["timeout_seconds"] == 3600
    assert t[CHECK]["notebook_task"]["notebook_path"] == "../notebooks/check_silver_gold_idle.py"
    assert (ROOT / "notebooks" / "check_silver_gold_idle.py").is_file()
    assert t[CHECK]["notebook_task"]["base_parameters"] == {
        "src_path": "${workspace.file_path}/src",
        "pipeline_id": PIPELINE_REF,
    }
    # G-27: a job reference would form a bundle cycle with the peak job (A-30)
    assert "resources.jobs." not in JOB_FILE.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- AC-82
def test_ac82_retry_timeout_and_auto_optimization_settings() -> None:
    t = tasks()
    expected = {
        "setup_catalog": (600, 1),
        "ingest_files": (1800, 1),
        "ingest_kafka": (840, 0),
        CHECK: (300, 0),
        "refresh_silver_gold": (2700, 0),
    }
    for key, (timeout, retries) in expected.items():
        assert t[key]["timeout_seconds"] == timeout, key
        assert t[key]["max_retries"] == retries, key
        assert t[key]["timeout_seconds"] < JOB["timeout_seconds"], key
    assert t["ingest_kafka"]["disable_auto_optimization"] is True
    assert t[CHECK]["disable_auto_optimization"] is True
    for key in ("setup_catalog", "ingest_files", "refresh_silver_gold"):
        assert "disable_auto_optimization" not in t[key], key
        if key != "refresh_silver_gold":  # its depends_on changes by design
            assert t[key] == tasks(OLD)[key], key
    refresh = t["refresh_silver_gold"]
    assert refresh["pipeline_task"] == {"pipeline_id": PIPELINE_REF, "full_refresh": False}
    assert refresh["pipeline_task"] == tasks(OLD)["refresh_silver_gold"]["pipeline_task"]
    old_kafka = dict(tasks(OLD)["ingest_kafka"])
    new_kafka = dict(t["ingest_kafka"])
    assert new_kafka.pop("disable_auto_optimization") is True
    assert new_kafka == old_kafka


# ----------------------------------------------------------------------------- AC-83
def test_ac83_only_the_check_runs_on_environment_version_2() -> None:
    assert JOB["environments"] == [
        {"environment_key": "ingestion_check_env", "spec": {"environment_version": "2"}}
    ]
    t = tasks()
    assert t[CHECK]["environment_key"] == "ingestion_check_env"
    for key, task in t.items():
        if key != CHECK:
            assert "environment_key" not in task, key
        assert not CLUSTER_KEYS & set(task), key
    assert not CLUSTER_KEYS & set(JOB)


# ----------------------------------------------------------------------------- AC-84
def test_ac84_pinned_definitions_equal_their_tags() -> None:
    """Supersedes the ingestion-file clause of AC-62 and AC-78 (tests/test_peak_bundle.py)."""
    assert sha(JOB_FILE.read_bytes()) == INGESTION_SHA256
    if tag_exists("v0.4.0"):
        assert tagged("v0.4.0", JOB_REL) == JOB_FILE.read_bytes()
    for tag, path, digest in PINS:
        assert sha((ROOT / path).read_bytes()) == digest, path
        if tag_exists(tag):
            assert sha(tagged(tag, path)) == digest, path
            assert tagged(tag, path) == (ROOT / path).read_bytes(), path
    pipelines = [
        name
        for file in sorted((ROOT / "resources").glob("*.yml"))
        for name in load(file).get("pipelines", {})
    ]
    assert pipelines == ["smart_meter_silver_gold"]


# ----------------------------------------------------------------------------- AC-85
def test_ac85_v010_fixture_is_the_shipped_file() -> None:
    assert sha(FIXTURE.read_bytes()) == V010_INGESTION_SHA256
    if tag_exists("v0.1.0"):
        assert tagged("v0.1.0", JOB_REL) == FIXTURE.read_bytes()


def test_ac85_ingestion_job_differs_from_v010_only_by_the_listed_changes() -> None:
    resources = copy.deepcopy(load(JOB_FILE))
    job = resources["jobs"]["smart_meter_ingestion"]
    del job["environments"]
    job["tasks"] = [t for t in job["tasks"] if t["task_key"] != CHECK]
    for task in job["tasks"]:
        if task["task_key"] == "ingest_kafka":
            del task["disable_auto_optimization"]
        if task["task_key"] == "refresh_silver_gold":
            task["depends_on"] = [{"task_key": "ingest_files"}, {"task_key": "ingest_kafka"}]
    assert resources == load(FIXTURE)
