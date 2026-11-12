"""Job-only mode of ``pipeline_guard`` and the compatibility pins (RESET_GUARD AC-189/190/197/200).

The job-only mode is tested on the recording fake of ``support.reset_fakes``. AC-197 proves that the
shipped modes did not change: goldens computed from tag ``v0.7.3`` with the functions of this file
(``assert_counts``, ``modes_outputs`` and ``tree_digest`` applied to ``git show v0.7.3:...``), never
typed by hand (DA-69). The tag-based comparisons run when the tag exists locally; the constants
guard a clone without tags (CI checks out one commit).
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from support import reset_fakes as fakes

from smart_meter_peak_prediction import pipeline_guard as pg

ROOT = Path(__file__).resolve().parents[1]
GUARD_REL = "src/smart_meter_peak_prediction/pipeline_guard.py"
RESET_REL = "scripts/reset_peak_model_outputs.py"
TAG = "v0.7.3"
SHIPPED_TESTS = (
    "tests/test_pipeline_guard.py",
    "tests/test_ingestion_guard.py",
    "tests/test_peak_reset_script.py",
)
BUNDLE_ROOTS = ("resources", "notebooks", "pipelines", "databricks.yml")
NOW = datetime(2026, 10, 23, 8, 0, 41, tzinfo=UTC)

V073_ASSERT_COUNTS: dict[str, dict[str, int]] = {
    "tests/test_pipeline_guard.py": {
        "test_ac69_active_ingestion_run_fails_with_job_run_id_and_action": 7,
        "test_ac69_queued_run_without_start_time_reads_not_started": 1,
        "test_ac69_listed_run_in_a_terminal_state_does_not_block": 2,
        "test_ac69_at_most_25_runs_are_read": 1,
        "test_ac69_state_constants_match_the_sdk_enums": 10,
        "test_ac70_update_state_decides_the_outcome_when_active": 6,
        "test_ac70_update_state_decides_the_outcome_when_terminal": 3,
        "test_ac70_creation_time_is_printed_in_utc_or_not_at_all": 9,
        "test_ac70_pipeline_state_decides_the_outcome": 5,
        "test_ac70_pipeline_pass_states_succeed": 2,
        "test_ac70_missing_pipeline_state_fails_closed": 2,
        "test_ac70_active_update_names_the_update_and_the_pipeline_state": 5,
        "test_ac71_both_blockers_are_named": 4,
        "test_ac71_active_run_and_busy_pipeline_state_are_both_named": 2,
        "test_ac72_idle_state_succeeds_twice_with_read_calls_only": 11,
        "test_ac72_one_read_per_object_without_waiting": 2,
        "test_ac72_client_limits_are_config_keywords_and_module_is_sdk_free": 3,
        "test_ac73_unreadable_state_fails_closed": 7,
        "test_ac73_deleted_pipeline_fails_closed_as_unusable": 5,
        "test_ac73_client_factory_failure_is_unreadable_for_both_objects": 5,
        "test_ac73_run_with_a_working_factory_checks_the_workspace": 1,
        "test_ac73_error_text_is_one_short_line_without_secrets": 4,
        "test_ac73_blockers_and_unreadable_items_are_both_reported": 4,
        "test_ac73_unreadable_job_does_not_hide_a_busy_pipeline": 3,
        "test_ac73_forbidden_calls_are_recorded_and_raise": 1,
        "test_ac73_secret_like_text_on_the_first_line_is_redacted": 2,
        "test_ac73_client_limits_are_accepted_by_the_sdk_config": 2,
        "test_ac73_edge_inputs_fail_closed_or_are_active": 4,
    },
    "tests/test_ingestion_guard.py": {
        "test_ac86_idle_or_failed_pipeline_passes_twice_with_one_read": 17,
        "test_ac87_active_update_fails_with_update_caller_and_action": 7,
        "test_ac87_every_non_terminal_sdk_update_state_blocks": 5,
        "test_ac87_caller_constants_match_the_bundle": 8,
        "test_ac88_busy_overall_state_without_active_update_fails_as_busy": 8,
        "test_ac88_deleted_pipeline_with_an_active_update_reports_both_blocks": 6,
        "test_ac89_unreadable_pipeline_fails_closed_with_the_ingestion_action": 6,
        "test_ac89_client_factory_failure_is_unreadable_through_run_pipeline_check": 5,
        "test_ac89_run_pipeline_check_with_a_working_factory_reads_once": 2,
        "test_ac89_forbidden_calls_are_recorded_and_raise": 1,
        "test_ac89_missing_state_with_no_updates_fails_as_busy_not_as_success": 3,
        "test_ac90_error_text_is_redacted_and_cut_to_one_short_line": 4,
        "test_ac91_times_are_utc_with_z_or_not_reported": 1,
        "test_ac91_naive_or_unparseable_creation_time_is_not_reported": 1,
        "test_ac91_now_in_another_zone_is_written_as_utc": 2,
        "test_ac92_shipped_guard_tests_are_byte_identical_to_v030": 3,
        "test_ac92_guard_module_changes_are_additions_only": 2,
        "test_ac92_peak_mode_signatures_and_output_are_unchanged": 8,
        "test_ac93_library_imports_no_sdk_and_never_sleeps": 2,
        "test_g23_pipeline_mode_reads_only_pipelines_get": 2,
    },
    "tests/test_peak_reset_script.py": {
        "test_ac66_reset_drops_exactly_the_three_rebuildable_tables": 2,
        "test_ac66_reset_refuses_unexpected_row_counts_missing_tables_and_empty_bronze": 0,
        "test_ac66_reset_refuses_without_the_before_snapshot": 0,
    },
}
V073_MODES_SHA256 = "c158948a5569907bdd3fd742d01e43b04a97cb0063490cfe5e5fa7006529e9a1"
V073_BUNDLE_SHA256 = "3f58b79e87aaa1f8894bbaa0de150e852caaa2e659ed383e415faaaffeee57a2"

IDS = (PEAK_ID, TRAINING_ID) = (fakes.PEAK_ID, fakes.TRAINING_ID)
NAMES = (fakes.PEAK, fakes.TRAINING)


# ----------------------------------------------------------------------------- git helpers
def _git(*args: str) -> bytes:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def tag_exists(tag: str = TAG) -> bool:
    done = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def tagged(path: str, tag: str = TAG) -> str:
    return _git("show", f"{tag}:{path}").decode()


def tagged_paths(tag: str = TAG) -> list[str]:
    out = _git("ls-tree", "-r", "--name-only", tag, "--", *BUNDLE_ROOTS)
    return sorted(out.decode().splitlines())


def tree_paths() -> list[str]:
    out = _git("ls-files", "--cached", "--others", "--exclude-standard", "--", *BUNDLE_ROOTS)
    return sorted({line for line in out.decode().splitlines() if (ROOT / line).is_file()})


def tree_digest(files: dict[str, bytes]) -> str:
    """SHA-256 over sorted ``path NUL sha256 LF`` lines."""
    lines = [f"{path}\0{hashlib.sha256(files[path]).hexdigest()}\n" for path in sorted(files)]
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def assert_counts(source: str) -> dict[str, int]:
    """Top-level test functions and their ``assert`` statements."""
    return {
        node.name: sum(isinstance(n, ast.Assert) for n in ast.walk(node))
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def load_tagged_guard() -> ModuleType:
    name = "pipeline_guard_v073"
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # the dataclass decorator looks the module up here
    try:
        exec(compile(tagged(GUARD_REL), f"{name}.py", "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(name, None)
    return module


# ----------------------------------------------------------------------------- fixed inputs
def _api_error(message: str, code: str) -> Exception:
    error = RuntimeError(message)
    error.error_code = code  # type: ignore[attr-defined]
    return error


def _shipped_client(
    *,
    runs: list[Any] | None = None,
    updates: list[Any] | None = None,
    job_error: Exception | None = None,
    pipeline_error: Exception | None = None,
    pipeline_state: str = "IDLE",
) -> SimpleNamespace:
    def get_job(**_: Any) -> Any:
        if job_error is not None:
            raise job_error
        return SimpleNamespace(settings=SimpleNamespace(name="[dev someone] smart_meter_ingestion"))

    def get_pipeline(**_: Any) -> Any:
        if pipeline_error is not None:
            raise pipeline_error
        return SimpleNamespace(
            name="[dev someone] smart_meter_silver_gold",
            state=SimpleNamespace(value=pipeline_state),
            latest_updates=updates,
        )

    jobs = SimpleNamespace(
        get=get_job,
        list=lambda **_: [SimpleNamespace(job_id=123456789)],
        list_runs=lambda **_: runs or [],
    )
    return SimpleNamespace(jobs=jobs, pipelines=SimpleNamespace(get=get_pipeline))


def _update(state: str) -> SimpleNamespace:
    return SimpleNamespace(update_id="3c4d5e6f", state=state, creation_time="2026-10-23T07:59:10Z")


def _text(call: Any) -> Any:
    try:
        report = call()
    except Exception as exc:  # noqa: BLE001 - the raised message is part of the output
        return {"raised": type(exc).__name__, "message": str(exc)}
    return {"message": report.message(), "exit": report.exit_value(), "ok": report.ok}


def _enforced(module: ModuleType, report: Any, enforce: Any) -> Any:
    try:
        return {"value": enforce(report)}
    except module.PipelineGuardError as exc:
        return {"raised": str(exc)}


def modes_outputs(module: ModuleType) -> dict[str, Any]:
    """Messages, exit values and enforce results of both shipped modes on fixed inputs."""
    denied = _api_error("no access", "PERMISSION_DENIED")
    peak_args = (123456789, "0a1b2c3d-pipeline")
    caller = module.INGESTION_CALLER
    busy_run = SimpleNamespace(
        run_id=1002990004411119,
        state=SimpleNamespace(life_cycle_state="RUNNING"),
        start_time=1792742282000,
    )
    peak = {
        "idle": module.check(_shipped_client(), *peak_args, now=NOW),
        "busy": module.check(_shipped_client(runs=[busy_run]), *peak_args, now=NOW),
        "unreadable": module.check(_shipped_client(job_error=denied), *peak_args, now=NOW),
        "factory": module.run(_raising, *peak_args, now=NOW),
    }
    pipeline = {
        "idle": module.check_pipeline(_shipped_client(), "p-1", caller=caller, now=NOW),
        "busy": module.check_pipeline(
            _shipped_client(updates=[_update("RUNNING")], pipeline_state="RUNNING"),
            "p-1",
            caller=caller,
            now=NOW,
        ),
        "unreadable": module.check_pipeline(
            _shipped_client(pipeline_error=denied), "p-1", caller=caller, now=NOW
        ),
        "factory": module.run_pipeline_check(_raising, "p-1", caller=caller, now=NOW),
    }
    return {
        "peak": {k: _text(lambda r=r: r) for k, r in peak.items()}
        | {f"enforce_{k}": _enforced(module, r, module.enforce) for k, r in peak.items()},
        "pipeline": {k: _text(lambda r=r: r) for k, r in pipeline.items()}
        | {
            f"enforce_{k}": _enforced(module, r, module.enforce_pipeline)
            for k, r in pipeline.items()
        },
    }


def _raising() -> Any:
    raise RuntimeError("no workspace")


def digest(outputs: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(outputs, sort_keys=True).encode()).hexdigest()


# ----------------------------------------------------------------------------- AC-189
def test_ac189_check_jobs_reports_every_active_run() -> None:
    runs = {
        PEAK_ID: [
            fakes.run("RUNNING"),
            fakes.run("TERMINATED", run_id=8),
            fakes.run("SKIPPED", run_id=9),
            fakes.run("INTERNAL_ERROR", run_id=10),
        ],
        TRAINING_ID: [],
    }
    client = fakes.FakeClient(runs=runs)
    report = pg.check_jobs(client, NAMES)
    assert not report.ok
    assert report.blocked
    assert not report.has_unreadable
    assert [job.name for job in report.jobs] == list(NAMES)
    assert [job.job_id for job in report.jobs] == ["101", "102"]
    assert report.problems() == [
        f"job {fakes.PEAK} (job id 101): active run 7, state RUNNING, started {fakes.START_TEXT}"
    ]
    assert report.jobs[1].ok
    assert (
        report.jobs[1].idle_line()
        == f"idle check: job {fakes.TRAINING} (job id 102): 0 active runs"
    )

    idle = pg.check_jobs(fakes.FakeClient(), NAMES)
    assert idle.ok
    assert idle.idle_lines() == [
        f"idle check: job {fakes.PEAK} (job id 101): 0 active runs",
        f"idle check: job {fakes.TRAINING} (job id 102): 0 active runs",
    ]


# ----------------------------------------------------------------------------- AC-190
def _page(count: int) -> list[tuple[Any, str]]:
    others = [(1000 + i, f"{fakes.DEV}other_{i}") for i in range(count - 1)]
    return [*others, (PEAK_ID, fakes.DEV + fakes.PEAK)]


LOOKUP_CASES = {
    "none": ({"jobs": [(103, fakes.DEV + fakes.INGESTION)]}, "no deployed job named"),
    "two": (
        {"jobs": [(PEAK_ID, fakes.DEV + fakes.PEAK), (104, "[dev other] " + fakes.PEAK)]},
        "is not unique (job ids: 101, 104)",
    ),
    "page full": ({"jobs": _page(100)}, "100 jobs listed, the page is full"),
    "page over full": ({"jobs": _page(150)}, "100 jobs listed, the page is full"),
    "id not a number": ({"jobs": [("abc", fakes.DEV + fakes.PEAK)]}, "not a positive integer"),
    "id zero": ({"jobs": [(0, fakes.DEV + fakes.PEAK)]}, "not a positive integer"),
    "listing raises": ({"overrides": {"jobs.list": RuntimeError("boom")}}, "RuntimeError: boom"),
    "item without settings": (
        {"overrides": {"jobs.list": lambda **_: [SimpleNamespace(job_id=5)]}},
        "no deployed job named",
    ),
}


@pytest.mark.parametrize("case", LOOKUP_CASES)
def test_ac190_lookup_fails_closed_on_every_ambiguity(case: str) -> None:
    options, cause = LOOKUP_CASES[case]
    client = fakes.FakeClient(**options)
    report = pg.check_jobs(client, (fakes.PEAK,))
    job = report.jobs[0]
    assert job.job_id == ""
    assert len(job.unreadable) == 1
    assert job.unreadable[0].read == "job list"
    assert cause in job.unreadable[0].error
    assert not report.ok
    assert report.has_unreadable
    assert not [e for e in client.log if e.startswith(("jobs.get", "jobs.list_runs"))]
    assert job.problems()[0].startswith(f"job {fakes.PEAK} (job id not resolved): job list: ")


# ----------------------------------------------------------------------------- AC-197
def test_ac197_shipped_guard_and_reset_tests_are_kept_with_their_asserts() -> None:
    for path in SHIPPED_TESTS:
        golden = V073_ASSERT_COUNTS[path]
        found = assert_counts((ROOT / path).read_text(encoding="utf-8"))
        for name, count in golden.items():
            assert name in found, (path, name)
            assert found[name] >= count, (path, name)
        if tag_exists():
            assert assert_counts(tagged(path)) == golden, path


def test_ac197_shipped_modes_equal_v073_byte_for_byte() -> None:
    outputs = modes_outputs(pg)
    assert digest(outputs) == V073_MODES_SHA256
    kinds = {key.removeprefix("enforce_") for part in outputs.values() for key in part}
    assert kinds == {"idle", "busy", "unreadable", "factory"}
    assert outputs["peak"]["enforce_busy"]["raised"].startswith("check_pipeline_idle stopped")
    assert outputs["peak"]["enforce_idle"]["value"]["outcome"] == "idle"
    if tag_exists():
        assert modes_outputs(load_tagged_guard()) == outputs


def test_ac197_read_call_sets_and_no_sdk_import() -> None:
    assert pg.READ_CALLS == ("jobs.get", "jobs.list", "jobs.list_runs", "pipelines.get")
    assert pg.PIPELINE_READ_CALLS == ("pipelines.get",)
    assert set(pg.JOB_READ_CALLS) <= set(pg.READ_CALLS)
    if tag_exists():
        old = load_tagged_guard()
        assert pg.READ_CALLS == old.READ_CALLS
        assert pg.PIPELINE_READ_CALLS == old.PIPELINE_READ_CALLS
    tree = ast.parse((ROOT / GUARD_REL).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not [a for a in node.names if a.name.split(".")[0] == "databricks"]
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "databricks"
        if isinstance(node, ast.Call):
            assert ast.unparse(node.func).split(".")[-1] != "sleep"


def _job_case(**options: Any) -> dict[str, Any]:
    return options


_NAME = fakes.DEV + fakes.INGESTION
_ID = 55
READER_CASES = {
    "idle": _job_case(),
    "terminal list race": _job_case(
        runs={
            _ID: [fakes.run("TERMINATED"), fakes.run("SKIPPED", 8), fakes.run("INTERNAL_ERROR", 9)]
        }
    ),
    "queued": _job_case(runs={_ID: [fakes.run("QUEUED")]}),
    "pending": _job_case(runs={_ID: [fakes.run("PENDING")]}),
    "running": _job_case(runs={_ID: [fakes.run("RUNNING")]}),
    "terminating": _job_case(runs={_ID: [fakes.run("TERMINATING")]}),
    "blocked": _job_case(runs={_ID: [fakes.run("BLOCKED")]}),
    "waiting for retry": _job_case(runs={_ID: [fakes.run("WAITING_FOR_RETRY")]}),
    "future state": _job_case(runs={_ID: [fakes.run("NEW_STATE")]}),
    "missing state": _job_case(runs={_ID: [fakes.run(None, start_time=None)]}),
    "get not found": _job_case(overrides={"jobs.get": fakes.NotFound()}),
    "get denied": _job_case(overrides={"jobs.get": fakes.PermissionDenied()}),
    "another name": _job_case(jobs=[(_ID, fakes.DEV + "other_job")]),
    "no name": _job_case(jobs=[(_ID, "")]),
    "same name 0": _job_case(overrides={"jobs.list": lambda **_: []}),
    "same name 2": _job_case(jobs=[(_ID, _NAME), (56, _NAME)]),
    "list raises": _job_case(overrides={"jobs.list": RuntimeError("list down")}),
    "runs raise": _job_case(runs={_ID: RuntimeError("runs down")}),
    "30 runs": _job_case(runs={_ID: [fakes.run("RUNNING", run_id=i) for i in range(1, 31)]}),
}


@pytest.mark.parametrize("case", READER_CASES)
def test_ac197_job_reader_matches_the_shipped_reader(case: str) -> None:
    options = READER_CASES[case]
    options = {"jobs": [(_ID, _NAME)], **options}
    first, second = fakes.FakeClient(**options), fakes.FakeClient(**options)
    runs1: list[pg.ActiveRun] = []
    runs2: list[pg.ActiveRun] = []
    bad1: list[pg.Unreadable] = []
    bad2: list[pg.Unreadable] = []
    value1 = pg._read_job(first, _ID, "subject", runs1, bad1)
    value2 = pg._read_named_job(second, _ID, pg.INGESTION_JOB, "subject", runs2, bad2)
    assert value1 == value2
    assert runs1 == runs2
    assert bad1 == bad2
    assert first.log == second.log
    assert first.called == second.called


def test_ac197_reset_imports_the_guard_and_defines_no_run_state_set() -> None:
    tree = ast.parse((ROOT / RESET_REL).read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "smart_meter_peak_prediction"
        for alias in node.names
    ]
    assert "pipeline_guard" in imports
    states = {
        "TERMINATED",
        "SKIPPED",
        "INTERNAL_ERROR",
        "QUEUED",
        "TERMINATING",
        "BLOCKED",
        "WAITING_FOR_RETRY",
    }
    for node in ast.walk(tree):
        elements: list[ast.expr] = []
        if isinstance(node, ast.Set | ast.Tuple | ast.List):
            elements = list(node.elts)
        elif isinstance(node, ast.Call) and ast.unparse(node.func) in ("set", "frozenset"):
            elements = [e for arg in node.args for e in ast.walk(arg)]
        strings = {e.value for e in elements if isinstance(e, ast.Constant)}
        assert not strings & states, ast.unparse(node)
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert not [a for a in node.names if a.name.split(".")[0] == "databricks"]
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "databricks"


def test_ac197_bundle_files_equal_v073() -> None:
    paths = tree_paths()
    files = {path: (ROOT / path).read_bytes() for path in paths}
    assert tree_digest(files) == V073_BUNDLE_SHA256
    if tag_exists():
        assert paths == tagged_paths()
        for path in paths:
            assert files[path] == _git("show", f"{TAG}:{path}"), path


# ----------------------------------------------------------------------------- AC-200
def test_ac200_job_only_mode_reads_one_page_and_25_runs() -> None:
    client = fakes.FakeClient(jobs=_page(150))
    job = pg.check_jobs(client, (fakes.PEAK,)).jobs[0]
    assert client.pulled["jobs.list"] == pg.MAX_JOBS_LISTED == 100
    assert "page is full" in job.unreadable[0].error

    many = {PEAK_ID: [fakes.run("RUNNING", run_id=i) for i in range(1, 31)]}
    client = fakes.FakeClient(runs=many)
    job = pg.check_jobs(client, (fakes.PEAK,)).jobs[0]
    assert client.pulled["runs:101"] == pg.MAX_RUNS_READ == 25
    assert len(job.runs) == 25
    assert set(client.called) <= set(pg.JOB_READ_CALLS)
    assert client.forbidden == []
