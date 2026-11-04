"""Pipeline-only pre-check of the ingestion job (AC-86 to AC-93; G-22 to G-27, ADR 0013).

The check runs against a recording fake that exposes ``pipeline_guard.PIPELINE_READ_CALLS`` only;
every other attribute, including all of ``jobs``, is recorded as forbidden and raises. The shipped
fake of ``tests/test_pipeline_guard.py`` is not imported, so that file stays byte-identical (AC-92).
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import importlib.util
import inspect
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml

from smart_meter_peak_prediction import pipeline_guard as pg

ROOT = Path(__file__).resolve().parents[1]
GUARD_FILE = ROOT / "src" / "smart_meter_peak_prediction" / "pipeline_guard.py"
GUARD_REL = "src/smart_meter_peak_prediction/pipeline_guard.py"
SHIPPED_TEST_REL = "tests/test_pipeline_guard.py"
# SHA-256 of tests/test_pipeline_guard.py at tag v0.3.0 (AC-92: the 28 shipped tests stay as is).
SHIPPED_TEST_SHA256 = "73bc3a02694f794d2762bc5d8aa57285f8dfbb12608c81d1f0c210c9cf2f94f2"

NOW = datetime(2026, 10, 24, 6, 7, 12, tzinfo=UTC)
NOW_TEXT = "2026-10-24T06:07:12Z"
PIPELINE_ID = "0a1b2c3d-pipeline"
UPDATE_ID = "3c4d5e6f-update"
DEV_PIPELINE = "[dev someone] smart_meter_silver_gold"
UTC_SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}[\w:.+\-]*")
UTC_OK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
CALLER = pg.INGESTION_CALLER

NON_TERMINAL_UPDATE_STATES = [
    "CREATED",
    "QUEUED",
    "INITIALIZING",
    "RESETTING",
    "SETTING_UP_TABLES",
    "RUNNING",
    "STOPPING",
    "WAITING_FOR_RESOURCES",
]


class ApiError(Exception):
    """Carries ``error_code`` as the SDK errors do."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PermissionDenied(ApiError):
    def __init__(self, message: str = "no access to the pipeline") -> None:
        super().__init__(message, "PERMISSION_DENIED")


class NotFound(ApiError):
    def __init__(self, message: str = "does not exist") -> None:
        super().__init__(message, "RESOURCE_DOES_NOT_EXIST")


def update_obj(
    state: Any = "RUNNING",
    update_id: str = UPDATE_ID,
    creation_time: Any = "2026-10-24T06:05:58.206Z",
) -> SimpleNamespace:
    return SimpleNamespace(update_id=update_id, state=state, creation_time=creation_time)


class _Api:
    def __init__(self, fake: PipelineFake, name: str) -> None:
        self._fake = fake
        self._name = name

    def __getattr__(self, method: str) -> Any:
        key = f"{self._name}.{method}"
        if key not in pg.PIPELINE_READ_CALLS:
            self._fake.forbidden.append(key)
            raise AssertionError(f"forbidden call {key}")

        def call(**kwargs: Any) -> Any:
            self._fake.calls.append(key)
            handler = self._fake.handlers[key]
            if isinstance(handler, Exception):
                raise handler
            return handler(**kwargs) if callable(handler) else handler

        return call


@dataclass
class PipelineFake:
    """Recording fake: ``handlers`` map ``api.method`` to a value, a callable or an exception."""

    handlers: dict[str, Any]

    def __post_init__(self) -> None:
        self.calls: list[str] = []
        self.forbidden: list[str] = []
        self.jobs = _Api(self, "jobs")
        self.pipelines = _Api(self, "pipelines")


def fake_pipeline(
    *,
    updates: list[Any] | None = None,
    name: str = DEV_PIPELINE,
    state: str | None = "IDLE",
    override: Any = None,
) -> PipelineFake:
    pipeline = SimpleNamespace(
        name=name,
        state=SimpleNamespace(value=state) if state else None,
        latest_updates=updates,
    )
    return PipelineFake({"pipelines.get": override if override is not None else pipeline})


def check(fake: PipelineFake, pipeline_id: Any = PIPELINE_ID, now: datetime = NOW) -> Any:
    return pg.check_pipeline(fake, pipeline_id, caller=CALLER, now=now)


def assert_read_only(fake: PipelineFake, *, at_most: int = 1) -> None:
    assert fake.forbidden == []
    assert len(fake.calls) <= at_most
    assert set(fake.calls) <= set(pg.PIPELINE_READ_CALLS)


def assert_times_are_utc(text: str) -> None:
    for found in UTC_SHAPE.findall(text):
        assert UTC_OK.fullmatch(found), found


# ----------------------------------------------------------------------------- AC-86
@pytest.mark.parametrize("state", ["IDLE", "FAILED"])
@pytest.mark.parametrize(
    "updates",
    [
        None,
        [],
        [update_obj("COMPLETED")],
        [update_obj("FAILED"), update_obj("COMPLETED", update_id="older")],
        [update_obj("CANCELED")],
    ],
    ids=["absent", "empty", "completed", "failed-completed", "canceled"],
)
def test_ac86_idle_or_failed_pipeline_passes_twice_with_one_read(
    state: str, updates: list[Any] | None
) -> None:
    fake = fake_pipeline(state=state, updates=updates)
    first = check(fake)
    second = check(fake)
    assert first.ok
    assert second.ok
    assert first == second
    assert first.exit_value() == second.exit_value()
    assert fake.calls == ["pipelines.get", "pipelines.get"]  # exactly 1 per run
    assert fake.forbidden == []
    later = check(fake, now=NOW + timedelta(hours=1))
    assert later.checked_at == "2026-10-24T07:07:12Z"
    assert {**later.exit_value(), "checked_at": NOW_TEXT} == first.exit_value()
    value = json.loads(json.dumps(first.exit_value()))
    assert value["outcome"] == "idle"
    assert value["checked_at"] == NOW_TEXT
    assert value["caller"] == {"job": "smart_meter_ingestion", "task": "check_silver_gold_idle"}
    pipeline = value["pipeline"]
    assert pipeline["pipeline_id"] == PIPELINE_ID
    assert pipeline["name"] == "smart_meter_silver_gold"  # prefix stripped
    assert pipeline["state"] == state
    expected = (
        None if not updates else {"update_id": updates[0].update_id, "state": updates[0].state}
    )
    assert pipeline["latest_update"] == expected
    assert pg.enforce_pipeline(first) == first.exit_value()
    assert "idle" in first.message()


# ----------------------------------------------------------------------------- AC-87
@pytest.mark.parametrize("state", [*NON_TERMINAL_UPDATE_STATES, "A_FUTURE_STATE", None])
def test_ac87_active_update_fails_with_update_caller_and_action(state: str | None) -> None:
    fake = fake_pipeline(state="RUNNING", updates=[update_obj(state)])
    report = check(fake)
    assert not report.ok
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce_pipeline(report)
    message = str(raised.value)
    assert message == report.message()
    expected = [
        "check_silver_gold_idle",
        "smart_meter_silver_gold",
        PIPELINE_ID,
        UPDATE_ID,
        state or "UNKNOWN",
        "created 2026-10-24T06:05:58Z",
        "pipeline state RUNNING",
        "smart_meter_ingestion",
        "06:00 UTC",
        "rerun smart_meter_ingestion",
        "smart_meter_peak_model",
        "08:00 UTC",
        "refresh_silver_gold did not start",
        "Bronze",
    ]
    for fragment in expected:
        assert fragment in message, fragment
    assert "check_pipeline_idle" not in message
    assert "rerun smart_meter_peak_model" not in message
    assert "job id" not in message
    assert_times_are_utc(message)
    assert_read_only(fake)
    assert report.exit_value()["outcome"] == "busy"


def test_ac87_every_non_terminal_sdk_update_state_blocks() -> None:
    pipelines = pytest.importorskip("databricks.sdk.service.pipelines")
    update_enum = getattr(pipelines, "UpdateInfoState", None) or pipelines.UpdateStateInfoState
    states = {member.value for member in update_enum}
    assert pg.TERMINAL_UPDATE_STATES <= states
    for member in sorted(states - pg.TERMINAL_UPDATE_STATES):
        report = check(fake_pipeline(state="RUNNING", updates=[update_obj(member)]))
        assert not report.ok, member
        assert f"state {member}," in report.message(), member
    # the real enum members are read through .value
    assert not check(fake_pipeline(state="RUNNING", updates=[update_obj(update_enum.RUNNING)])).ok
    assert check(fake_pipeline(updates=[update_obj(update_enum.COMPLETED)])).ok


def test_ac87_caller_constants_match_the_bundle() -> None:
    ingestion = yaml.safe_load(
        (ROOT / "resources" / "smart_meter_ingestion.job.yml").read_text(encoding="utf-8")
    )["resources"]["jobs"]["smart_meter_ingestion"]
    peak = yaml.safe_load(
        (ROOT / "resources" / "smart_meter_peak_model.job.yml").read_text(encoding="utf-8")
    )["resources"]["jobs"]["smart_meter_peak_model"]
    assert CALLER.task in [t["task_key"] for t in ingestion["tasks"]]
    assert CALLER.job == ingestion["name"]
    assert ingestion["schedule"]["timezone_id"] == peak["schedule"]["timezone_id"] == "UTC"
    assert ingestion["schedule"]["quartz_cron_expression"] == "0 0 6 * * ?"
    assert CALLER.schedule == "06:00 UTC"
    assert peak["schedule"]["quartz_cron_expression"] == "0 0 8 * * ?"
    assert peak["name"] in CALLER.next_refresh
    assert "08:00 UTC" in CALLER.next_refresh


# ----------------------------------------------------------------------------- AC-88
@pytest.mark.parametrize(
    "state",
    ["DEPLOYING", "STARTING", "RUNNING", "STOPPING", "RECOVERING", "RESETTING", None, "NEW_STATE"],
)
@pytest.mark.parametrize("updates", [[], [update_obj("COMPLETED")]], ids=["empty", "terminal"])
def test_ac88_busy_overall_state_without_active_update_fails_as_busy(
    state: str | None, updates: list[Any]
) -> None:
    fake = fake_pipeline(state=state, updates=updates)
    report = check(fake)
    assert report.pipeline_busy
    assert not report.ok
    assert report.exit_value()["outcome"] == "busy"
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce_pipeline(report)
    message = str(raised.value)
    assert "smart_meter_silver_gold" in message
    assert f"pipeline state {state or 'not reported'}," in message
    assert "no active update is listed in latest_updates" in message
    for fragment in ("check_silver_gold_idle", "rerun smart_meter_ingestion", "08:00 UTC"):
        assert fragment in message
    assert "update named above" not in message
    assert_times_are_utc(message)
    assert_read_only(fake)


def test_ac88_deleted_pipeline_with_an_active_update_reports_both_blocks() -> None:
    report = check(fake_pipeline(state="DELETED", updates=[update_obj("RUNNING")]))
    message = report.message()
    assert "Blocking:" in message
    assert "Could not read:" in message
    assert "DELETED, not usable" in message
    assert "wait until the update named above ends and fix the cause named under" in message
    assert "then rerun smart_meter_ingestion" in message
    assert "check_pipeline_idle" not in message


# ----------------------------------------------------------------------------- AC-89
def _factory_raises() -> Any:
    raise RuntimeError("client build failed")


CASES: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {
    "empty id": ({}, {"pipeline_id": ""}, "id missing or not resolved"),
    "blank id": ({}, {"pipeline_id": "   "}, "id missing or not resolved"),
    "none id": ({}, {"pipeline_id": None}, "id missing or not resolved"),
    "unresolved reference": (
        {},
        {"pipeline_id": "${resources.pipelines.smart_meter_silver_gold.id}"},
        "id missing or not resolved",
    ),
    "generic error": ({"override": RuntimeError("boom")}, {}, "pipeline: RuntimeError: boom"),
    "permission denied": ({"override": PermissionDenied()}, {}, "PERMISSION_DENIED"),
    "not found": ({"override": NotFound()}, {}, "RESOURCE_DOES_NOT_EXIST"),
    "another pipeline": ({"name": "other_pipeline"}, {}, "another pipeline"),
    "deleted": ({"state": "DELETED"}, {}, "DELETED, not usable"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_ac89_unreadable_pipeline_fails_closed_with_the_ingestion_action(case: str) -> None:
    build, ids, expected = CASES[case]
    fake = fake_pipeline(**build)
    report = check(fake, **ids)
    assert not report.ok
    assert report.exit_value()["outcome"] == "unknown"
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce_pipeline(report)
    message = str(raised.value)
    for fragment in (
        "check_silver_gold_idle",
        "smart_meter_silver_gold",
        expected,
        "fails closed",
        "fix the cause, then rerun smart_meter_ingestion",
        "refresh_silver_gold did not start",
        "Bronze",
    ):
        assert fragment in message, fragment
    assert "job id" not in message
    assert "check_pipeline_idle" not in message
    assert_times_are_utc(message)
    assert_read_only(fake)
    if "pipeline_id" in ids:
        assert fake.calls == []  # G-22: no API call for a bad id


def test_ac89_client_factory_failure_is_unreadable_through_run_pipeline_check() -> None:
    report = pg.run_pipeline_check(_factory_raises, PIPELINE_ID, caller=CALLER, now=NOW)
    assert not report.ok
    message = report.message()
    assert "workspace client" in message
    assert "client build failed" in message
    assert "fails closed" in message
    assert "fix the cause, then rerun smart_meter_ingestion" in message
    with pytest.raises(pg.PipelineGuardError):
        pg.enforce_pipeline(report)


def test_ac89_run_pipeline_check_with_a_working_factory_reads_once() -> None:
    fake = fake_pipeline()
    report = pg.run_pipeline_check(lambda: fake, PIPELINE_ID, caller=CALLER, now=NOW)
    assert report.ok
    assert fake.calls == ["pipelines.get"]


def test_ac89_forbidden_calls_are_recorded_and_raise() -> None:
    fake = fake_pipeline()
    with pytest.raises(AssertionError):
        fake.jobs.list_runs(job_id=1)
    with pytest.raises(AssertionError):
        fake.pipelines.start_update(pipeline_id="x")
    assert fake.forbidden == ["jobs.list_runs", "pipelines.start_update"]


def test_ac89_missing_state_with_no_updates_fails_as_busy_not_as_success() -> None:
    report = check(fake_pipeline(state=None, updates=None))
    assert not report.ok
    assert report.pipeline_busy
    assert "pipeline state not reported" in report.message()


# ----------------------------------------------------------------------------- AC-90
def test_ac90_error_text_is_redacted_and_cut_to_one_short_line() -> None:
    token = "dapi" + "0123456789abcdef0123456789abcdef"
    first = f"call https://host.example/api failed: Bearer abc123 {token}"
    error = RuntimeError(first + "\nsecond line with a_hidden_detail")
    report = check(fake_pipeline(override=error))
    message = report.message()
    assert "<redacted>" in message
    for leaked in ("host.example", "abc123", token, "a_hidden_detail", "second line"):
        assert leaked not in message
    long_error = PermissionDenied("x" * 500)
    item = check(fake_pipeline(override=long_error)).unreadable[0]
    prefix = "PermissionDenied (PERMISSION_DENIED): "
    assert item.error.startswith(prefix)
    assert len(item.error) - len(prefix) <= pg.MAX_ERROR_CHARS == 200


# ----------------------------------------------------------------------------- AC-91
@pytest.mark.parametrize(
    "created",
    [
        "2026-10-24T08:05:58+02:00",
        "2026-10-24T06:05:58Z",
        "2026-10-24T06:05:58.999Z",
        1792821958000,
        "1792821958000",
        datetime(2026, 10, 24, 8, 5, 58, tzinfo=timezone(timedelta(hours=2))),
    ],
)
def test_ac91_times_are_utc_with_z_or_not_reported(created: Any) -> None:
    report = check(fake_pipeline(state="RUNNING", updates=[update_obj(creation_time=created)]))
    message = report.message()
    assert "created 2026-10-24T06:05:58Z" in message
    assert_times_are_utc(message)


def test_ac91_naive_or_unparseable_creation_time_is_not_reported() -> None:
    for created in (datetime(2026, 10, 24, 6, 5, 58), "not a time", None):
        report = check(fake_pipeline(state="RUNNING", updates=[update_obj(creation_time=created)]))
        assert "creation time not reported" in report.message()
        assert_times_are_utc(report.message())


def test_ac91_now_in_another_zone_is_written_as_utc() -> None:
    local = datetime(2026, 10, 24, 8, 7, 12, tzinfo=timezone(timedelta(hours=2)))
    report = check(fake_pipeline(state="RUNNING", updates=[update_obj()]), now=local)
    assert report.checked_at == NOW_TEXT
    assert f"(checked at {NOW_TEXT})" in report.message()
    assert_times_are_utc(report.message())
    assert_times_are_utc(json.dumps(check(fake_pipeline(), now=local).exit_value()))


# ----------------------------------------------------------------------------- AC-92
def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return done.stdout


def _tagged(path: str, tag: str = "v0.3.0") -> str | None:
    return _git("show", f"{tag}:{path}")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_tagged_guard() -> ModuleType | None:
    text = _tagged(GUARD_REL)
    if text is None:
        return None
    name = "pipeline_guard_v030"
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # the dataclass decorator looks the module up here
    try:
        exec(compile(text, f"{name}.py", "exec"), module.__dict__)  # noqa: S102
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def test_ac92_shipped_guard_tests_are_byte_identical_to_v030() -> None:
    path = ROOT / SHIPPED_TEST_REL
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHIPPED_TEST_SHA256
    tagged = _tagged(SHIPPED_TEST_REL)
    if tagged is not None:
        assert _sha(tagged) == SHIPPED_TEST_SHA256
    tree = ast.parse(data.decode("utf-8"))
    tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    assert len(tests) == 28


def test_ac92_guard_module_changes_are_additions_only() -> None:
    tagged = _tagged(GUARD_REL)
    if tagged is None:
        return  # no tag in this clone (CI); the golden peak output test still guards the path
    old = tagged.splitlines()
    new = GUARD_FILE.read_text(encoding="utf-8").splitlines()
    opcodes = difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
    kinds = {tag for tag, *_ in opcodes}
    assert kinds <= {"equal", "insert"}, [op for op in opcodes if op[0] not in ("equal", "insert")]
    assert "insert" in kinds


# Peak-mode golden values captured from the v0.3.0 module (used when the tag is not available).
PEAK_JOB_ID = 123456789
PEAK_NOW = datetime(2026, 10, 23, 8, 0, 41, tzinfo=UTC)


def _peak_workspace(
    *,
    runs: list[Any] | None = None,
    updates: list[Any] | None = None,
    state: str | None = "IDLE",
    job_error: Exception | None = None,
) -> _FullFake:
    job = SimpleNamespace(
        job_id=PEAK_JOB_ID, settings=SimpleNamespace(name="[dev someone] smart_meter_ingestion")
    )
    pipeline = SimpleNamespace(
        name=DEV_PIPELINE,
        state=SimpleNamespace(value=state) if state else None,
        latest_updates=updates,
    )
    return _FullFake(
        {
            "jobs.get": job_error or job,
            "jobs.list": [SimpleNamespace(job_id=PEAK_JOB_ID)],
            "jobs.list_runs": runs or [],
            "pipelines.get": pipeline,
        }
    )


class _FullApi:
    def __init__(self, fake: _FullFake, name: str) -> None:
        self._fake = fake
        self._name = name

    def __getattr__(self, method: str) -> Any:
        key = f"{self._name}.{method}"
        assert key in pg.READ_CALLS, key

        def call(**kwargs: Any) -> Any:
            handler = self._fake.handlers[key]
            if isinstance(handler, Exception):
                raise handler
            return handler

        return call


class _FullFake:
    def __init__(self, handlers: dict[str, Any]) -> None:
        self.handlers = handlers
        self.jobs = _FullApi(self, "jobs")
        self.pipelines = _FullApi(self, "pipelines")


def _run_obj() -> SimpleNamespace:
    return SimpleNamespace(
        run_id=1002990004411119,
        state=SimpleNamespace(life_cycle_state="RUNNING"),
        start_time=1792742282000,
    )


PEAK_CASES = {
    "idle": lambda: _peak_workspace(),
    "busy run": lambda: _peak_workspace(runs=[_run_obj()]),
    "busy update": lambda: _peak_workspace(state="RUNNING", updates=[update_obj("RUNNING")]),
    "busy state only": lambda: _peak_workspace(state="STOPPING", updates=[]),
    "unreadable job": lambda: _peak_workspace(job_error=PermissionDenied("no access to the job")),
    "deleted": lambda: _peak_workspace(state="DELETED"),
}


def _peak_output(module: ModuleType, case: str) -> dict[str, Any]:
    if case == "factory failure":
        report = module.run(_factory_raises, PEAK_JOB_ID, PIPELINE_ID, now=PEAK_NOW)
    else:
        report = module.check(PEAK_CASES[case](), PEAK_JOB_ID, PIPELINE_ID, now=PEAK_NOW)
    return {"message": report.message(), "exit_value": report.exit_value()}


def _signature(function: Any) -> list[tuple[str, Any, Any]]:
    return [
        (p.name, p.kind.name, repr(p.default))
        for p in inspect.signature(function).parameters.values()
    ]


def test_ac92_peak_mode_signatures_and_output_are_unchanged() -> None:
    assert [p[0] for p in _signature(pg.check)] == [
        "client",
        "ingestion_job_id",
        "pipeline_id",
        "now",
    ]
    assert _signature(pg.check)[-1] == ("now", "KEYWORD_ONLY", "None")
    assert [p[0] for p in _signature(pg.run)] == [
        "client_factory",
        "ingestion_job_id",
        "pipeline_id",
        "now",
    ]
    assert _signature(pg.run)[-1] == ("now", "KEYWORD_ONLY", "None")
    assert [p[0] for p in _signature(pg.enforce)] == ["report"]
    module = _load_tagged_guard()
    try:
        for name in ("check", "run", "enforce"):
            if module is not None:
                assert _signature(getattr(pg, name)) == _signature(getattr(module, name)), name
        cases = [*PEAK_CASES, "factory failure"]
        for case in cases:
            current = _peak_output(pg, case)
            if module is not None:
                assert current == _peak_output(module, case), case
            assert current == PEAK_GOLDEN[case], case
    finally:
        sys.modules.pop("pipeline_guard_v030", None)


PEAK_GOLDEN: dict[str, dict[str, Any]] = {
    "idle": {
        "message": "check_pipeline_idle: the shared pipeline is idle (checked at "
        "2026-10-23T08:00:41Z).",
        "exit_value": {
            "outcome": "idle",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {
                "job_id": 123456789,
                "name": "smart_meter_ingestion",
                "active_runs": [],
            },
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": "smart_meter_silver_gold",
                "state": "IDLE",
                "latest_update": None,
            },
        },
    },
    "busy run": {
        "message": "check_pipeline_idle stopped the run before refresh_silver_gold: the "
        "shared pipeline is busy (checked at 2026-10-23T08:00:41Z).\n"
        "Blocking:\n"
        "  - job smart_meter_ingestion (job id 123456789): active run "
        "1002990004411119, state RUNNING, started 2026-10-23T07:58:02Z\n"
        "Action: wait until the run or update named above ends, then rerun "
        "smart_meter_peak_model.\n"
        "Without action, the next scheduled run (08:00 UTC) is the retry. "
        "refresh_silver_gold and the tasks after it did not start; rerunning "
        "is safe.",
        "exit_value": {
            "outcome": "busy",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {
                "job_id": 123456789,
                "name": "smart_meter_ingestion",
                "active_runs": ["1002990004411119"],
            },
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": "smart_meter_silver_gold",
                "state": "IDLE",
                "latest_update": None,
            },
        },
    },
    "busy update": {
        "message": "check_pipeline_idle stopped the run before refresh_silver_gold: "
        "the shared pipeline is busy (checked at 2026-10-23T08:00:41Z).\n"
        "Blocking:\n"
        "  - pipeline smart_meter_silver_gold (pipeline id "
        "0a1b2c3d-pipeline): update 3c4d5e6f-update, state RUNNING, "
        "pipeline state RUNNING, created 2026-10-24T06:05:58Z\n"
        "Action: wait until the run or update named above ends, then rerun "
        "smart_meter_peak_model.\n"
        "Without action, the next scheduled run (08:00 UTC) is the retry. "
        "refresh_silver_gold and the tasks after it did not start; "
        "rerunning is safe.",
        "exit_value": {
            "outcome": "busy",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {
                "job_id": 123456789,
                "name": "smart_meter_ingestion",
                "active_runs": [],
            },
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": "smart_meter_silver_gold",
                "state": "RUNNING",
                "latest_update": {"update_id": "3c4d5e6f-update", "state": "RUNNING"},
            },
        },
    },
    "busy state only": {
        "message": "check_pipeline_idle stopped the run before "
        "refresh_silver_gold: the shared pipeline is busy (checked at "
        "2026-10-23T08:00:41Z).\n"
        "Blocking:\n"
        "  - pipeline smart_meter_silver_gold (pipeline id "
        "0a1b2c3d-pipeline): pipeline state STOPPING, no active update "
        "listed in latest_updates\n"
        "Action: wait until the run or update named above ends, then "
        "rerun smart_meter_peak_model.\n"
        "Without action, the next scheduled run (08:00 UTC) is the "
        "retry. refresh_silver_gold and the tasks after it did not "
        "start; rerunning is safe.",
        "exit_value": {
            "outcome": "busy",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {
                "job_id": 123456789,
                "name": "smart_meter_ingestion",
                "active_runs": [],
            },
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": "smart_meter_silver_gold",
                "state": "STOPPING",
                "latest_update": None,
            },
        },
    },
    "unreadable job": {
        "message": "check_pipeline_idle could not establish the pipeline state and "
        "fails closed (checked at 2026-10-23T08:00:41Z).\n"
        "Could not read:\n"
        "  - job smart_meter_ingestion (job id 123456789): job: "
        "PermissionDenied (PERMISSION_DENIED): no access to the job\n"
        "Action: fix the cause named above (deployment, permission or "
        "API availability), then rerun smart_meter_peak_model.\n"
        "Without action, the next scheduled run (08:00 UTC) checks "
        "again.",
        "exit_value": {
            "outcome": "unknown",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {"job_id": 123456789, "name": None, "active_runs": []},
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": "smart_meter_silver_gold",
                "state": "IDLE",
                "latest_update": None,
            },
        },
    },
    "deleted": {
        "message": "check_pipeline_idle could not establish the pipeline state and fails "
        "closed (checked at 2026-10-23T08:00:41Z).\n"
        "Could not read:\n"
        "  - pipeline smart_meter_silver_gold (pipeline id 0a1b2c3d-pipeline): "
        "pipeline state: DELETED, not usable\n"
        "Action: fix the cause named above (deployment, permission or API "
        "availability), then rerun smart_meter_peak_model.\n"
        "Without action, the next scheduled run (08:00 UTC) checks again.",
        "exit_value": {
            "outcome": "unknown",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {
                "job_id": 123456789,
                "name": "smart_meter_ingestion",
                "active_runs": [],
            },
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": "smart_meter_silver_gold",
                "state": "DELETED",
                "latest_update": None,
            },
        },
    },
    "factory failure": {
        "message": "check_pipeline_idle could not establish the pipeline state "
        "and fails closed (checked at 2026-10-23T08:00:41Z).\n"
        "Could not read:\n"
        "  - job smart_meter_ingestion (job id 123456789): workspace "
        "client: RuntimeError: client build failed\n"
        "  - pipeline smart_meter_silver_gold (pipeline id "
        "0a1b2c3d-pipeline): workspace client: RuntimeError: client "
        "build failed\n"
        "Action: fix the cause named above (deployment, permission or "
        "API availability), then rerun smart_meter_peak_model.\n"
        "Without action, the next scheduled run (08:00 UTC) checks "
        "again.",
        "exit_value": {
            "outcome": "unknown",
            "checked_at": "2026-10-23T08:00:41Z",
            "ingestion_job": {"job_id": 123456789, "name": None, "active_runs": []},
            "pipeline": {
                "pipeline_id": "0a1b2c3d-pipeline",
                "name": None,
                "state": None,
                "latest_update": None,
            },
        },
    },
}


# ----------------------------------------------------------------------------- AC-93
def test_ac93_library_imports_no_sdk_and_never_sleeps() -> None:
    tree = ast.parse(GUARD_FILE.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [name for name in imported if name.split(".")[0] in ("databricks", "time")]
    called = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
    }
    assert "sleep" not in called


def test_g23_pipeline_mode_reads_only_pipelines_get() -> None:
    assert pg.PIPELINE_READ_CALLS == ("pipelines.get",)
    assert set(pg.PIPELINE_READ_CALLS) <= set(pg.READ_CALLS)
