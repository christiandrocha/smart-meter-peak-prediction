"""Unit tests for the AC-97 capture helpers of the live ingestion guard tests.

Closes AC97_TIMING_EVIDENCE I-11. The helpers live in
``tests/integration/test_ingestion_guard_live.py``, which carries the ``integration`` marker. This
module loads that file by path, under a private module name, so the live module is not collected
a second time, and runs in the default CI pass. AC-105 does not cover these helpers: it hashes
only ``src/``, ``resources/``, ``notebooks/`` and ``databricks.yml`` and checks the asserts inside
the AC-97 test function. In scope: the five helpers named in I-11 (``_observe``,
``_capture_found_run``, ``_capture_refused``, ``_capture_rerun``, ``_read_update_end``) and the
private helpers they call directly (``_skipped``, ``_enum``, ``_task_facts``, ``_check_output``,
``_first_result``). The other live helpers are INGESTION_GUARD I-11.

No network, no credentials, no ``databricks-sdk``: SDK objects are ``SimpleNamespace`` values and
the workspace is a small fake whose methods return canned data or raise ``FakeSdkError``.

A known bug that is not yet fixed has a test of the current behavior and a strict ``xfail`` test of
the correct one, so a fix turns the ``xfail`` into a failure and forces these tests to be updated
(INGESTION_GUARD I-12). The ``_update_creation_ms`` tests cover the fix of INGESTION_GUARD I-13.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from support import ac97_timing as at

LIVE = Path(__file__).resolve().parent / "integration" / "test_ingestion_guard_live.py"
CHECK = "check_silver_gold_idle"
REFRESH = "refresh_silver_gold"
UPDATE_ID = "u-0001"
SECRET = "sentinel-" + "message-body"  # must never be printed (G-33)


def _load_live() -> Any:
    spec = importlib.util.spec_from_file_location("_ingestion_guard_live_under_test", LIVE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = _load_live()


# ----------------------------------------------------------------------------- fakes
class FakeSdkError(Exception):
    """Shaped like ``databricks.sdk.errors.DatabricksError``: a message and an ``error_code``."""

    def __init__(self, message: str = SECRET, error_code: str | None = "RESOURCE_DOES_NOT_EXIST"):
        super().__init__(message)
        self.error_code = error_code


Reply = Any  # a value, an Exception to raise, or a callable taking the call's kwargs


def _reply(reply: Reply, **kwargs: Any) -> Any:
    if isinstance(reply, BaseException):
        raise reply
    if callable(reply):
        return reply(**kwargs)
    return reply


class FakeJobs:
    def __init__(self, runs: Reply = (), output: Reply = None) -> None:
        self._runs, self._output = runs, output
        self.calls: list[tuple[str, dict]] = []

    def list_runs(self, **kwargs: Any) -> Any:
        self.calls.append(("list_runs", kwargs))
        return iter(_reply(self._runs, **kwargs))

    def get_run_output(self, run_id: int) -> Any:
        self.calls.append(("get_run_output", {"run_id": run_id}))
        return _reply(self._output, run_id=run_id)


class FakePipelines:
    def __init__(self, update: Reply = None, events: Reply = (), updates: Reply = None) -> None:
        self._update, self._events, self._updates = update, events, updates
        self.calls: list[tuple[str, tuple]] = []

    def get_update(self, pipeline_id: str, update_id: str) -> Any:
        self.calls.append(("get_update", (pipeline_id, update_id)))
        return _reply(self._update, pipeline_id=pipeline_id, update_id=update_id)

    def list_pipeline_events(self, pipeline_id: str, max_results: int) -> Any:
        self.calls.append(("list_pipeline_events", (pipeline_id, max_results)))
        return iter(_reply(self._events, pipeline_id=pipeline_id))

    def list_updates(self, pipeline_id: str, max_results: int) -> Any:
        self.calls.append(("list_updates", (pipeline_id, max_results)))
        return _reply(self._updates, pipeline_id=pipeline_id)


def _workspace(jobs: FakeJobs | None = None, pipelines: FakePipelines | None = None) -> Any:
    return SimpleNamespace(jobs=jobs or FakeJobs(), pipelines=pipelines or FakePipelines())


def _facts() -> at.Ac97Facts:
    return at.Ac97Facts(UPDATE_ID, at.UpdateWatch(UPDATE_ID))


def _state(value: str | None) -> Any:
    return SimpleNamespace(result_state=None if value is None else SimpleNamespace(value=value))


def _task(key: str, run_id: int, start: int = 1_000, end: int = 2_000, result: str | None = None):
    return SimpleNamespace(
        task_key=key, run_id=run_id, start_time=start, end_time=end, state=_state(result)
    )


def _run(run_id: int, start: int, tasks: list[Any] | None = None, end: int | None = None) -> Any:
    return SimpleNamespace(run_id=run_id, start_time=start, end_time=end, tasks=tasks)


def _event(n: int) -> Any:
    return SimpleNamespace(as_dict=lambda n=n: {"id": f"e{n}", "event_type": "update_progress"})


def _entry(update_id: str, state: Any, created: Any = None) -> Any:
    return SimpleNamespace(update_id=update_id, state=state, creation_time=created)


def _enum_of(value: str) -> Any:
    return SimpleNamespace(value=value)


def _assert_one_skip_line(out: str, what: str, exc: Exception) -> None:
    lines = [line for line in out.splitlines() if line]
    code = getattr(exc, "error_code", None) or "-"
    assert lines == [f"AC-97 timing evidence: {what} not read ({type(exc).__name__} {code})"]
    assert SECRET not in out


# ----------------------------------------------------------------------------- _skipped
def test_skipped_prints_class_and_error_code_only(capsys: pytest.CaptureFixture[str]) -> None:
    exc = FakeSdkError(error_code="PERMISSION_DENIED")
    live._skipped("the update", exc)
    _assert_one_skip_line(capsys.readouterr().out, "the update", exc)


def test_skipped_without_error_code_prints_a_dash_and_no_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exc = ValueError(SECRET)
    live._skipped("the rerun", exc)
    out = capsys.readouterr().out
    assert out == "AC-97 timing evidence: the rerun not read (ValueError -)\n"
    assert SECRET not in out


# ----------------------------------------------------------------------------- _enum
@pytest.mark.parametrize(
    ("value", "expected"),
    [(_enum_of("RUNNING"), "RUNNING"), ("COMPLETED", "COMPLETED"), (_enum_of(7), "7")],
)
def test_enum_unwraps_value_and_returns_text(value: Any, expected: str) -> None:
    assert live._enum(value) == expected


@pytest.mark.parametrize("value", [None, _enum_of(None)])
def test_enum_of_none_is_none(value: Any) -> None:
    assert live._enum(value) is None


# ----------------------------------------------------------------------------- _observe
def test_observe_records_creation_state_and_first_terminal_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watch = at.UpdateWatch(UPDATE_ID)
    live._observe(SimpleNamespace(latest_updates=[_entry(UPDATE_ID, "WAITING", 111)]), watch)
    assert (watch.created, watch.state, watch.observed_terminal_ts) == (111, "WAITING", None)

    times = iter(["2026-11-05T12:00:00Z", "2026-11-05T12:00:10Z"])
    monkeypatch.setattr(live.pipeline_guard, "utc_text", lambda _value: next(times))
    completed = SimpleNamespace(latest_updates=[_entry(UPDATE_ID, _enum_of("COMPLETED"), 999)])
    live._observe(completed, watch)
    live._observe(completed, watch)  # a later terminal poll keeps the first time

    assert watch.created == 111  # creation time is recorded once
    assert watch.state == "COMPLETED"
    assert watch.observed_terminal_ts == "2026-11-05T12:00:00Z"


def test_observe_ignores_other_updates_and_missing_lists() -> None:
    watch = at.UpdateWatch(UPDATE_ID)
    live._observe(SimpleNamespace(latest_updates=[_entry("other", "FAILED", 5)]), watch)
    live._observe(SimpleNamespace(latest_updates=None), watch)
    live._observe(SimpleNamespace(), watch)  # no attribute at all
    assert watch == at.UpdateWatch(UPDATE_ID)


def test_observe_entry_without_state_records_none() -> None:
    watch = at.UpdateWatch(UPDATE_ID)
    live._observe(SimpleNamespace(latest_updates=[SimpleNamespace(update_id=UPDATE_ID)]), watch)
    assert (watch.created, watch.state, watch.observed_terminal_ts) == (None, None, None)


# ----------------------------------------------------------------------------- _first_result
def test_first_result_returns_the_first_matching_task_result() -> None:
    run = _run(1, 0, [_task(CHECK, 10, result="SUCCESS"), _task(CHECK, 11, result="FAILED")])
    assert live._first_result(run, CHECK) == "SUCCESS"


@pytest.mark.parametrize(
    "run",
    [
        _run(1, 0, None),
        _run(1, 0, [_task(REFRESH, 10, result="SUCCESS")]),
        _run(1, 0, [_task(CHECK, 10, result=None)]),
        _run(1, 0, [SimpleNamespace(task_key=CHECK, state=None)]),
    ],
    ids=["no-tasks", "task-missing", "no-result-state", "no-state"],
)
def test_first_result_is_none_without_a_result(run: Any) -> None:
    assert live._first_result(run, CHECK) is None


# ----------------------------------------------------------------------------- _task_facts
def test_task_facts_reads_the_check_task() -> None:
    run = _run(7, 0, [_task(REFRESH, 70), _task(CHECK, 71, 1_500, 2_500, "FAILED")])
    assert live._task_facts(run) == at.TaskFacts(
        run_id=7, task_run_id=71, start=1_500, end=2_500, result="FAILED"
    )


@pytest.mark.parametrize(
    "tasks", [None, [], [_task(REFRESH, 70, result="UPSTREAM_FAILED")]], ids=["none", "empty", "x"]
)
def test_task_facts_without_the_check_task_keeps_only_the_run_id(tasks: Any) -> None:
    assert live._task_facts(_run(7, 0, tasks)) == at.TaskFacts(run_id=7)


def test_task_facts_check_task_without_result_state_has_result_none() -> None:
    facts = live._task_facts(_run(7, 0, [_task(CHECK, 71, result=None)]))
    assert (facts.task_run_id, facts.result) == (71, None)


# ----------------------------------------------------------------------------- _check_output
def test_check_output_records_error_and_exit_value() -> None:
    output = SimpleNamespace(
        error="refused",
        error_trace="trace",
        notebook_output=SimpleNamespace(result=json.dumps({"outcome": "busy"})),
    )
    jobs = FakeJobs(output=output)
    facts = _facts()
    live._check_output(_workspace(jobs), _task(CHECK, 71), facts)
    assert jobs.calls == [("get_run_output", {"run_id": 71})]
    assert facts.check_error == "refused trace"
    assert facts.check_exit == {"outcome": "busy"}


def test_check_output_without_error_or_output_leaves_facts_unchanged() -> None:
    output = SimpleNamespace(error=None, error_trace=None, notebook_output=None)
    facts = _facts()
    live._check_output(_workspace(FakeJobs(output=output)), _task(CHECK, 71), facts)
    assert facts == _facts()


def test_check_output_error_without_trace_keeps_a_trailing_space() -> None:
    output = SimpleNamespace(error="refused", error_trace=None, notebook_output=None)
    facts = _facts()
    live._check_output(_workspace(FakeJobs(output=output)), _task(CHECK, 71), facts)
    assert facts.check_error == "refused "


def test_check_output_raises_on_a_platform_error() -> None:
    """Unguarded on its own; ``_capture_found_run`` is the guard (see below)."""
    with pytest.raises(FakeSdkError):
        live._check_output(_workspace(FakeJobs(output=FakeSdkError())), _task(CHECK, 71), _facts())


def test_check_output_raises_on_an_exit_value_that_is_not_json() -> None:
    output = SimpleNamespace(error=None, notebook_output=SimpleNamespace(result="not json"))
    with pytest.raises(json.JSONDecodeError):
        live._check_output(_workspace(FakeJobs(output=output)), _task(CHECK, 71), _facts())


# ----------------------------------------------------------------------------- _capture_found_run
BEFORE_MS = 1_000_000


def test_capture_found_run_takes_the_oldest_run_and_reads_its_check() -> None:
    newer = _run(2, BEFORE_MS + 60_000, [_task(CHECK, 21, result="SUCCESS")])
    oldest = _run(1, BEFORE_MS + 40_000, [_task(CHECK, 11, 5, 6, "FAILED")])
    output = SimpleNamespace(error="refused", error_trace="t", notebook_output=None)
    jobs = FakeJobs(runs=[newer, oldest], output=output)
    facts = _facts()

    live._capture_found_run(_workspace(jobs), SimpleNamespace(job_id=42), BEFORE_MS, facts)

    assert jobs.calls[0] == (
        "list_runs",
        {"job_id": 42, "start_time_from": BEFORE_MS, "expand_tasks": True, "limit": 5},
    )
    assert facts.refused == at.TaskFacts(run_id=1, task_run_id=11, start=5, end=6, result="FAILED")
    assert jobs.calls[1] == ("get_run_output", {"run_id": 11})
    assert facts.check_error == "refused t"


def test_capture_found_run_reads_at_most_five_runs() -> None:
    drawn: list[int] = []

    def runs(**_kwargs: Any) -> Any:
        for n in range(100, 0, -1):  # newest first, oldest last
            drawn.append(n)
            yield _run(n, BEFORE_MS + n)

    facts = _facts()
    live._capture_found_run(_workspace(FakeJobs(runs=runs)), SimpleNamespace(job_id=1), 0, facts)
    assert drawn == [100, 99, 98, 97, 96]
    assert facts.refused == at.TaskFacts(run_id=96)


def test_capture_found_run_without_runs_leaves_facts_unchanged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs = FakeJobs(runs=[])
    facts = _facts()
    live._capture_found_run(_workspace(jobs), SimpleNamespace(job_id=1), BEFORE_MS, facts)
    assert facts == _facts()
    assert [name for name, _ in jobs.calls] == ["list_runs"]
    assert capsys.readouterr().out == ""


def test_capture_found_run_without_check_task_reads_no_output() -> None:
    jobs = FakeJobs(runs=[_run(1, BEFORE_MS + 1, [_task(REFRESH, 11)])])
    facts = _facts()
    live._capture_found_run(_workspace(jobs), SimpleNamespace(job_id=1), BEFORE_MS, facts)
    assert facts.refused == at.TaskFacts(run_id=1)
    assert [name for name, _ in jobs.calls] == ["list_runs"]


def test_capture_found_run_list_error_is_one_skip_line(capsys: pytest.CaptureFixture[str]) -> None:
    exc = FakeSdkError(error_code="TEMPORARILY_UNAVAILABLE")
    facts = _facts()
    live._capture_found_run(_workspace(FakeJobs(runs=exc)), SimpleNamespace(job_id=1), 0, facts)
    assert facts == _facts()
    _assert_one_skip_line(capsys.readouterr().out, "the refused run", exc)


def test_capture_found_run_output_error_keeps_the_run_facts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exc = FakeSdkError(error_code="INTERNAL_ERROR")
    jobs = FakeJobs(runs=[_run(1, BEFORE_MS + 1, [_task(CHECK, 11)])], output=exc)
    facts = _facts()
    live._capture_found_run(_workspace(jobs), SimpleNamespace(job_id=1), BEFORE_MS, facts)
    assert facts.refused is not None
    assert facts.refused.task_run_id == 11
    assert facts.check_error is None
    _assert_one_skip_line(capsys.readouterr().out, "the refused run", exc)


# INGESTION_GUARD I-12: the lookup starts START_SLACK_SECONDS before start_update and keeps the
# oldest run, so a run that ended before the update was requested can be taken as the refused run.
SLACK_MS = live.START_SLACK_SECONDS * 1000


def _slack_case() -> tuple[FakeJobs, at.Ac97Facts]:
    requested = BEFORE_MS + SLACK_MS  # when start_update was called
    stale = _run(1, BEFORE_MS + 5_000, [_task(CHECK, 11, result="SUCCESS")], end=requested - 1_000)
    refused = _run(
        2, requested + 5_000, [_task(CHECK, 21, result="FAILED")], end=requested + 60_000
    )
    output = SimpleNamespace(error=None, notebook_output=None)
    return FakeJobs(runs=[refused, stale], output=output), _facts()


def test_capture_found_run_takes_a_run_that_ended_before_the_update_was_requested() -> None:
    """Documenta comportamento atual com bug — ver INGESTION_GUARD I-12."""
    jobs, facts = _slack_case()
    live._capture_found_run(_workspace(jobs), SimpleNamespace(job_id=1), BEFORE_MS, facts)
    assert facts.refused is not None
    assert facts.refused.run_id == 1


@pytest.mark.xfail(strict=True, reason="INGESTION_GUARD I-12")
def test_capture_found_run_skips_a_run_that_ended_before_the_update_was_requested() -> None:
    jobs, facts = _slack_case()
    live._capture_found_run(_workspace(jobs), SimpleNamespace(job_id=1), BEFORE_MS, facts)
    assert facts.refused is not None
    assert facts.refused.run_id == 2


# ----------------------------------------------------------------------------- _capture_refused
def test_capture_refused_copies_facts_without_a_platform_call() -> None:
    run = _run(3, 0, [_task(CHECK, 31, 10, 20, "FAILED"), _task(REFRESH, 32)])
    refused = SimpleNamespace(run=run, errors={CHECK: "busy U"}, outputs={CHECK: {"outcome": "x"}})
    facts = _facts()
    live._capture_refused(refused, facts)
    assert facts.refused == at.TaskFacts(
        run_id=3, task_run_id=31, start=10, end=20, result="FAILED"
    )
    assert (facts.check_error, facts.check_exit) == ("busy U", {"outcome": "x"})


def test_capture_refused_without_check_entries_records_none() -> None:
    refused = SimpleNamespace(run=_run(3, 0, []), errors={}, outputs={})
    facts = _facts()
    live._capture_refused(refused, facts)
    assert facts.refused == at.TaskFacts(run_id=3)
    assert (facts.check_error, facts.check_exit) == (None, None)


def test_capture_refused_broken_run_is_one_skip_line(capsys: pytest.CaptureFixture[str]) -> None:
    facts = _facts()
    live._capture_refused(SimpleNamespace(errors={}, outputs={}), facts)  # no ``run``
    assert facts == _facts()
    out = capsys.readouterr().out
    assert out == "AC-97 timing evidence: the refused run not read (AttributeError -)\n"


def test_capture_refused_error_after_the_run_keeps_the_run_facts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    refused = SimpleNamespace(run=_run(3, 0, [_task(CHECK, 31)]), errors=None, outputs={})
    facts = _facts()
    live._capture_refused(refused, facts)
    assert facts.refused is not None
    assert facts.refused.run_id == 3
    assert facts.check_error is None
    assert "(AttributeError -)" in capsys.readouterr().out


# ----------------------------------------------------------------------------- _capture_rerun
def test_capture_rerun_records_run_id_and_both_results() -> None:
    run = _run(4, 0, [_task(CHECK, 41, result="SUCCESS"), _task(REFRESH, 42, result="SUCCESS")])
    facts = _facts()
    live._capture_rerun(SimpleNamespace(run=run), facts)
    assert (facts.rerun_run_id, facts.rerun_check_result, facts.rerun_refresh_result) == (
        4,
        "SUCCESS",
        "SUCCESS",
    )


def test_capture_rerun_missing_tasks_give_none() -> None:
    facts = _facts()
    live._capture_rerun(SimpleNamespace(run=_run(4, 0, None)), facts)
    assert (facts.rerun_run_id, facts.rerun_check_result, facts.rerun_refresh_result) == (
        4,
        None,
        None,
    )


def test_capture_rerun_broken_run_is_one_skip_line(capsys: pytest.CaptureFixture[str]) -> None:
    facts = _facts()
    live._capture_rerun(SimpleNamespace(), facts)
    assert facts == _facts()
    assert (
        capsys.readouterr().out == "AC-97 timing evidence: the rerun not read (AttributeError -)\n"
    )


def test_capture_rerun_error_after_the_run_id_keeps_it(capsys: pytest.CaptureFixture[str]) -> None:
    broken = SimpleNamespace(run_id=4, tasks=[SimpleNamespace()])  # a task without ``task_key``
    facts = _facts()
    live._capture_rerun(SimpleNamespace(run=broken), facts)
    assert facts.rerun_run_id == 4
    assert facts.rerun_check_result is None
    assert "(AttributeError -)" in capsys.readouterr().out


# ----------------------------------------------------------------------------- _read_update_end
def _update(created: Any = 1_700, state: Any = None) -> Any:
    return SimpleNamespace(update=SimpleNamespace(creation_time=created, state=state))


def test_read_update_end_reads_update_and_one_event_page() -> None:
    pipelines = FakePipelines(
        update=_update(1_700, _enum_of("COMPLETED")), events=[_event(1), _event(2)]
    )
    facts = _facts()
    live._read_update_end(_workspace(pipelines=pipelines), "p-1", facts)
    assert facts.end_read is True
    assert (facts.update_created, facts.update_state) == (1_700, "COMPLETED")
    assert facts.events == [
        {"id": "e1", "event_type": "update_progress"},
        {"id": "e2", "event_type": "update_progress"},
    ]
    assert pipelines.calls == [
        ("get_update", ("p-1", UPDATE_ID)),
        ("list_pipeline_events", ("p-1", 50)),
    ]


def test_read_update_end_takes_at_most_fifty_events() -> None:
    facts = _facts()
    pipelines = FakePipelines(update=_update(), events=(_event(n) for n in range(80)))
    live._read_update_end(_workspace(pipelines=pipelines), "p-1", facts)
    assert facts.events is not None
    assert len(facts.events) == 50


def test_read_update_end_update_error_still_reads_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exc = FakeSdkError(error_code="RESOURCE_DOES_NOT_EXIST")
    facts = _facts()
    live._read_update_end(_workspace(pipelines=FakePipelines(exc, [_event(1)])), "p-1", facts)
    assert facts.end_read is True
    assert (facts.update_created, facts.update_state) == (None, None)
    assert facts.events == [{"id": "e1", "event_type": "update_progress"}]
    _assert_one_skip_line(capsys.readouterr().out, "the update", exc)


def test_read_update_end_events_error_keeps_the_update(capsys: pytest.CaptureFixture[str]) -> None:
    exc = FakeSdkError(error_code="PERMISSION_DENIED")
    pipelines = FakePipelines(update=_update(1_700, "FAILED"), events=exc)
    facts = _facts()
    live._read_update_end(_workspace(pipelines=pipelines), "p-1", facts)
    assert facts.end_read is True
    assert (facts.update_created, facts.update_state, facts.events) == (1_700, "FAILED", None)
    _assert_one_skip_line(capsys.readouterr().out, "the pipeline events", exc)


def test_read_update_end_both_errors_give_two_skip_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    facts = _facts()
    live._read_update_end(_workspace(pipelines=FakePipelines(ValueError(), KeyError())), "p", facts)
    assert facts.end_read is True
    assert capsys.readouterr().out.splitlines() == [
        "AC-97 timing evidence: the update not read (ValueError -)",
        "AC-97 timing evidence: the pipeline events not read (KeyError -)",
    ]


# ----------------------------------------------------------------------------- _update_creation_ms
# Fixed for INGESTION_GUARD I-13 (DA-36 fallback, DESIGN Change Log 2026-11-05). The helper's other
# live-only aspects stay in INGESTION_GUARD I-11.
LISTED = SimpleNamespace(updates=[SimpleNamespace(update_id=UPDATE_ID, creation_time=1_234)])
NO_CREATION = "AC-97 timing evidence: the update (AC-106) has no creation time; using the list\n"


def _creation(update: Reply, updates: Reply = LISTED) -> tuple[Any, FakePipelines]:
    pipelines = FakePipelines(update=update, updates=updates)
    return live._update_creation_ms(_workspace(pipelines=pipelines), "p-1", UPDATE_ID), pipelines


def _called(pipelines: FakePipelines) -> list[str]:
    return [name for name, _ in pipelines.calls]


def test_update_creation_ms_reads_get_update_alone(capsys: pytest.CaptureFixture[str]) -> None:
    found, pipelines = _creation(_update(created=5_678))
    assert found == 5_678
    assert _called(pipelines) == ["get_update"]
    assert capsys.readouterr().out == ""


def test_update_creation_ms_falls_back_to_the_list_when_creation_time_is_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    found, pipelines = _creation(_update(created=None))
    assert found == 1_234
    assert _called(pipelines) == ["get_update", "list_updates"]
    assert capsys.readouterr().out == NO_CREATION


def test_update_creation_ms_falls_back_to_the_list_when_get_update_raises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exc = FakeSdkError(error_code="RESOURCE_DOES_NOT_EXIST")
    found, pipelines = _creation(exc)
    assert found == 1_234
    assert _called(pipelines) == ["get_update", "list_updates"]
    _assert_one_skip_line(capsys.readouterr().out, "the update (AC-106)", exc)


def test_update_creation_ms_skips_list_entries_without_creation_time() -> None:
    updates = SimpleNamespace(
        updates=[
            SimpleNamespace(update_id="other", creation_time=1),
            SimpleNamespace(update_id=UPDATE_ID, creation_time=None),
            SimpleNamespace(update_id=UPDATE_ID, creation_time=9_999),
        ]
    )
    found, _ = _creation(_update(created=None), updates)
    assert found == 9_999


@pytest.mark.parametrize(
    "updates",
    [
        SimpleNamespace(updates=None),
        SimpleNamespace(updates=[SimpleNamespace(update_id="other", creation_time=1)]),
        SimpleNamespace(updates=[SimpleNamespace(update_id=UPDATE_ID, creation_time=None)]),
    ],
    ids=["empty-list", "not-listed", "listed-without-creation-time"],
)
@pytest.mark.parametrize("update", [None, FakeSdkError()], ids=["no-creation-time", "raises"])
def test_update_creation_ms_without_any_source_is_a_clear_assertion(
    update: Any, updates: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    reply = _update(created=None) if update is None else update
    with pytest.raises(AssertionError) as raised:
        _creation(reply, updates)
    message = str(raised.value)
    assert UPDATE_ID in message
    assert "get_update" in message
    assert "update list" in message
    assert SECRET not in capsys.readouterr().out
