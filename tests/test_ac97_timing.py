"""AC-100 to AC-103: the AC-97 timing helpers (FR-54 to FR-59, G-28 to G-32).

The helpers in ``tests/support/ac97_timing.py`` are pure. The parser is tested against messages
rendered by the shipped ``pipeline_guard`` itself, through a minimal fake client that has
``pipelines.get`` only. Instants are the DEFINE reference values of 2026-10-23; epoch values are
computed from aware datetimes. Fake tokens are built by concatenation so that the repository scans
for secrets stay clean.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from support import ac97_timing as at

from smart_meter_peak_prediction import pipeline_guard as pg

HELPERS = Path(__file__).resolve().parent / "support" / "ac97_timing.py"
UTC_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

CREATED = datetime(2026, 10, 23, 18, 37, 7, tzinfo=UTC)
READ = datetime(2026, 10, 23, 18, 37, 34, tzinfo=UTC)
ENDED = datetime(2026, 10, 23, 18, 39, 12, tzinfo=UTC)
CREATED_TEXT, READ_TEXT, ENDED_TEXT = (
    "2026-10-23T18:37:07Z",
    "2026-10-23T18:37:34Z",
    "2026-10-23T18:39:12Z",
)
PLUS2 = timezone(timedelta(hours=2))
UPDATE = "856b017d-c522-45db-8129-35605f661cf3"
OTHER = "0f0f0f0f-aaaa-bbbb-cccc-111122223333"
PIPELINE_ID = "0a1b2c3d-pipeline"


# ----------------------------------------------------------------------------- fakes
def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _entry(update_id: str, state: str, created: datetime | None = CREATED) -> SimpleNamespace:
    return SimpleNamespace(
        update_id=update_id, state=state, creation_time=_ms(created) if created else None
    )


class _Pipelines:
    def __init__(self, pipeline: SimpleNamespace | Exception) -> None:
        self.pipeline = pipeline

    def get(self, pipeline_id: str) -> SimpleNamespace:
        if isinstance(self.pipeline, Exception):
            raise self.pipeline
        return self.pipeline


def _report(
    entries: list[SimpleNamespace], state: str = "RUNNING", name: str = pg.PIPELINE
) -> pg.PipelineReport:
    pipeline = SimpleNamespace(
        name=name, state=SimpleNamespace(value=state), latest_updates=entries
    )
    client = SimpleNamespace(pipelines=_Pipelines(pipeline))
    return pg.check_pipeline(client, PIPELINE_ID, caller=pg.INGESTION_CALLER, now=READ)


def _busy_message() -> str:
    return _report([_entry(UPDATE, "WAITING_FOR_RESOURCES")]).message()


def _tokens() -> list[str]:
    return ["https://host.example/x", "Bearer abc", "dapi" + "0123456789abcdef" * 2]


def _ansi_wrapped(message: str) -> str:
    trace = f"\x1b[0;31mPipelineGuardError\x1b[0m: {message}\n  at cell 3"
    return "PipelineGuardError: " + message + " " + trace


def _events() -> list[dict]:
    return [
        {
            "event_type": "update_progress",
            "origin": {"update_id": UPDATE},
            "timestamp": "2026-10-23T18:37:09.100Z",
            "message": f"Update {UPDATE[:6]} is WAITING_FOR_RESOURCES.",
        },
        {
            "event_type": "update_progress",
            "origin": {"update_id": UPDATE},
            "timestamp": "2026-10-23T18:39:12.500Z",
            "message": f"Update {UPDATE[:6]} is COMPLETED.",
        },
    ]


def _full_facts() -> at.Ac97Facts:
    watch = at.UpdateWatch(UPDATE, created=_ms(CREATED), state="COMPLETED")
    watch.observed_terminal_ts = "2026-10-23T18:39:20Z"
    return at.Ac97Facts(
        update_id=UPDATE,
        watch=watch,
        update_created=_ms(CREATED),
        update_state="COMPLETED",
        events=_events(),
        end_read=True,
        refused=at.TaskFacts(
            run_id=303996116036137,
            task_run_id=111,
            start=_ms(READ - timedelta(seconds=30)),
            end=_ms(READ + timedelta(seconds=4)),
            result="FAILED",
        ),
        check_error=_ansi_wrapped(_busy_message()),
        rerun_run_id=581887386545638,
        rerun_check_result="SUCCESS",
        rerun_refresh_result="SUCCESS",
    )


# ----------------------------------------------------------------------------- AC-100
def _forms() -> list[tuple[str, tuple[Any, Any, Any]]]:
    return [
        ("iso_z", (CREATED_TEXT, READ_TEXT, ENDED_TEXT)),
        (
            "iso_offset",
            tuple(m.astimezone(PLUS2).isoformat() for m in (CREATED, READ, ENDED)),
        ),
        ("epoch_ms", (_ms(CREATED), _ms(READ), _ms(ENDED))),
        ("aware_datetime", tuple(m.astimezone(PLUS2) for m in (CREATED, READ, ENDED))),
    ]


@pytest.mark.parametrize(("form", "instants"), _forms(), ids=[f for f, _ in _forms()])
def test_ac100_margins_are_whole_utc_seconds_for_every_input_form(form, instants) -> None:
    first = at.margins(*instants)
    second = at.margins(*instants)
    assert first["read_after_creation_seconds"] == 27, form
    assert first["update_outlived_read_seconds"] == 98, form
    assert first["update_created_ts"] == CREATED_TEXT
    assert first["check_read_ts"] == READ_TEXT
    assert first["update_ended_ts"] == ENDED_TEXT
    for key in ("update_created_ts", "check_read_ts", "update_ended_ts"):
        assert UTC_SHAPE.fullmatch(first[key]), key
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def _module_tree() -> ast.Module:
    return ast.parse(HELPERS.read_text(encoding="utf-8"))


def test_ac100_helpers_import_no_sdk_and_read_no_clock() -> None:
    tree = _module_tree()
    forbidden_modules = {"databricks", "time", "os", "pathlib", "subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
            assert not roots & forbidden_modules, roots
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden_modules, node.module
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            assert name not in {"now", "utcnow", "time", "open", "sleep"}, name


# ----------------------------------------------------------------------------- AC-101
def test_ac101_missing_naive_or_early_end_never_raises() -> None:
    # (a) the end is before the read: negative margin, outcome update_ended_before_check, also
    # with a busy message that names U (G-32 precedence)
    early = at.margins(CREATED_TEXT, READ_TEXT, "2026-10-23T18:37:29Z")
    assert early["update_outlived_read_seconds"] == -5
    read = at.parse_check_message(_busy_message(), UPDATE)
    assert read.update_state == "WAITING_FOR_RESOURCES"
    assert at.decide_outcome("FAILED", read, None, -5) == "update_ended_before_check"
    assert at.decide_outcome("FAILED", read, None, 0) == "update_ended_before_check"

    # (b) the read is missing: both margins null, never refused
    no_read = at.margins(CREATED_TEXT, None, ENDED_TEXT)
    assert no_read["read_after_creation_seconds"] is None
    assert no_read["update_outlived_read_seconds"] is None
    assert at.decide_outcome("FAILED", at.CheckRead(), None, None) != "refused"

    # (c) the end is missing: the creation margin is computed, the other one is null
    no_end = at.margins(CREATED_TEXT, READ_TEXT, None)
    assert no_end["read_after_creation_seconds"] == 27
    assert no_end["update_outlived_read_seconds"] is None
    assert no_end["update_ended_ts"] is None

    # (d) a naive creation time is not read as local time
    naive = at.margins(datetime(2026, 10, 23, 18, 37, 7), READ_TEXT, ENDED_TEXT)
    assert naive["update_created_ts"] is None
    assert naive["read_after_creation_seconds"] is None
    assert naive["update_outlived_read_seconds"] == 98
    assert at.margins("2026-10-23T18:37:07", READ_TEXT, None)["update_created_ts"] is None

    # (e) an idle check (exit outcome idle): the update had ended before the read
    exit_value = _report([_entry(UPDATE, "COMPLETED")], state="IDLE").exit_value()
    assert exit_value["outcome"] == "idle"
    idle_read = at.read_from_exit_value(exit_value, UPDATE)
    assert at.decide_outcome("SUCCESS", idle_read, "idle", None) == "update_ended_before_check"

    # the builder never raises on any of these inputs
    facts = at.Ac97Facts(UPDATE, at.UpdateWatch(UPDATE))
    facts.check_exit = exit_value
    facts.refused = at.TaskFacts(1, 2, "not a number", None, "SUCCESS")
    record = at.build_record(facts)
    assert record["outcome"] == "update_ended_before_check"
    assert record["check_started_ts"] is None


# ----------------------------------------------------------------------------- AC-102
def test_ac102_parser_reads_the_library_busy_message() -> None:
    expected = at.CheckRead(
        read_ts=READ_TEXT,
        update_state="WAITING_FOR_RESOURCES",
        pipeline_state="RUNNING",
        update_created_ts=CREATED_TEXT,
    )
    single = _busy_message()
    assert "update " + UPDATE + ", state WAITING_FOR_RESOURCES" in single  # the library's wording
    assert at.parse_check_message(single, UPDATE) == expected

    two = _report([_entry(OTHER, "RUNNING", None), _entry(UPDATE, "WAITING_FOR_RESOURCES")])
    assert at.parse_check_message(two.message(), UPDATE) == expected
    other = at.parse_check_message(two.message(), OTHER)
    assert other.update_state == "RUNNING"
    assert other.update_created_ts is None  # "creation time not reported"
    assert other.read_ts == READ_TEXT

    wrapped = _ansi_wrapped(single)
    assert at.parse_check_message(wrapped, UPDATE) == expected  # task error text, ANSI codes
    split = "\x1b[1m" + single.replace("state ", "state \x1b[0m", 1)
    assert at.parse_check_message(split, UPDATE).update_state == "WAITING_FOR_RESOURCES"


def test_ac102_parser_returns_nulls_for_other_messages() -> None:
    no_update = _report([], state="RUNNING").message()
    fail_closed = pg.check_pipeline(
        SimpleNamespace(pipelines=_Pipelines(RuntimeError("boom"))),
        PIPELINE_ID,
        caller=pg.INGESTION_CALLER,
        now=READ,
    ).message()
    idle = _report([_entry(UPDATE, "COMPLETED")], state="IDLE").message()
    for text in (no_update, fail_closed, idle):
        found = at.parse_check_message(text, UPDATE)
        assert found.update_state is None, text
        assert found.update_created_ts is None, text
        assert found.pipeline_state is None
        assert found.read_ts == READ_TEXT  # the library messages carry the time
    for text in ("", None, "an unrelated string", "update", "(checked at 2026-10-23T18:37)"):
        assert at.parse_check_message(text, UPDATE) == at.CheckRead()  # type: ignore[arg-type]

    exit_value = _report([_entry(UPDATE, "COMPLETED")], state="IDLE").exit_value()
    assert at.read_from_exit_value(exit_value, UPDATE) == at.CheckRead(
        read_ts=READ_TEXT, update_state="COMPLETED", pipeline_state="IDLE"
    )
    elsewhere = at.read_from_exit_value(exit_value, OTHER)
    assert elsewhere.update_state is None
    assert elsewhere.read_ts == READ_TEXT
    assert at.read_from_exit_value(None, UPDATE) == at.CheckRead()
    assert at.read_from_exit_value({"pipeline": 3, "checked_at": "x"}, UPDATE) == at.CheckRead()


def test_ac102_end_event_pick_requires_the_update_and_its_final_state() -> None:
    events = _events()
    assert at.pick_update_end(events, UPDATE, "COMPLETED") == ENDED_TEXT
    assert at.pick_update_end(list(reversed(events)), UPDATE, "COMPLETED") == ENDED_TEXT
    early = {**events[1], "timestamp": "2026-10-23T18:38:00Z"}
    assert at.pick_update_end([events[1], early], UPDATE, "COMPLETED") == "2026-10-23T18:38:00Z"
    assert at.pick_update_end(events, OTHER, "COMPLETED") is None  # other update
    assert at.pick_update_end(events, UPDATE, "FAILED") is None  # message names another state
    assert at.pick_update_end(events, UPDATE, "RUNNING") is None  # not terminal
    assert at.pick_update_end(events, UPDATE, None) is None
    assert (
        at.pick_update_end([{**events[1], "event_type": "flow_progress"}], UPDATE, "COMPLETED")
        is None
    )
    assert at.pick_update_end([{**events[1], "message": "done"}], UPDATE, "COMPLETED") is None
    assert (
        at.pick_update_end([{**events[1], "message": "UNCOMPLETED"}], UPDATE, "COMPLETED") is None
    )
    assert at.pick_update_end([{**events[1], "timestamp": "no time"}], UPDATE, "COMPLETED") is None
    assert at.pick_update_end([{"origin": None}, "text", {}], UPDATE, "COMPLETED") is None  # type: ignore[list-item]

    assert at.resolve_update_end(ENDED_TEXT, "2026-10-23T18:39:20Z") == (ENDED_TEXT, "platform")
    assert at.resolve_update_end(None, "2026-10-23T18:39:20Z") == (
        "2026-10-23T18:39:20Z",
        "observed_terminal",
    )
    assert at.resolve_update_end(None, None) == (None, None)
    assert at.resolve_update_end("naive 2026", datetime(2026, 1, 1)) == (None, None)


# ----------------------------------------------------------------------------- AC-103
def test_ac103_record_has_exactly_the_contract_fields() -> None:
    contract = {
        "update_id", "update_created_ts", "update_ended_ts", "update_end_source",
        "update_final_state", "refused_run_id", "check_task_run_id", "check_started_ts",
        "check_ended_ts", "check_result", "check_read_ts", "check_read_update_state",
        "check_read_pipeline_state", "read_after_creation_seconds",
        "update_outlived_read_seconds", "rerun_run_id", "rerun_check_result",
        "rerun_refresh_result", "outcome",
    }  # fmt: skip
    assert set(at.RECORD_FIELDS) == contract
    assert len(at.RECORD_FIELDS) == 19
    record = at.build_record(_full_facts())
    assert set(record) == contract
    assert record["update_id"] == UPDATE
    assert record["update_created_ts"] == CREATED_TEXT
    assert record["update_ended_ts"] == ENDED_TEXT
    assert record["update_end_source"] == "platform"
    assert record["update_final_state"] == "COMPLETED"
    assert record["refused_run_id"] == 303996116036137
    assert record["check_task_run_id"] == 111
    assert record["check_result"] == "FAILED"
    assert record["check_read_ts"] == READ_TEXT
    assert record["check_read_update_state"] == "WAITING_FOR_RESOURCES"
    assert record["check_read_pipeline_state"] == "RUNNING"
    assert record["rerun_run_id"] == 581887386545638
    assert (record["rerun_check_result"], record["rerun_refresh_result"]) == ("SUCCESS",) * 2
    assert record["outcome"] == "refused"
    for key in ("check_started_ts", "check_ended_ts", "update_created_ts", "update_ended_ts"):
        assert UTC_SHAPE.fullmatch(record[key]), key
    for key in ("refused_run_id", "check_task_run_id", "rerun_run_id"):
        assert type(record[key]) is int
    for key in ("read_after_creation_seconds", "update_outlived_read_seconds"):
        assert type(record[key]) is int
    assert record["update_end_source"] in at.END_SOURCES
    assert record["outcome"] in at.OUTCOMES

    figures = at.margins(
        record["update_created_ts"], record["check_read_ts"], record["update_ended_ts"]
    )
    assert record["read_after_creation_seconds"] == figures["read_after_creation_seconds"] == 27
    assert record["update_outlived_read_seconds"] == figures["update_outlived_read_seconds"] == 98
    text = json.dumps(record, sort_keys=True)
    assert text == json.dumps(at.build_record(_full_facts()), sort_keys=True)

    # fallbacks: no event and no get_update leave the idle wait's observation (FR-57)
    facts = _full_facts()
    facts.events, facts.update_created, facts.update_state = None, None, None
    fallback = at.build_record(facts)
    assert fallback["update_end_source"] == "observed_terminal"
    assert fallback["update_ended_ts"] == "2026-10-23T18:39:20Z"
    assert fallback["update_created_ts"] == CREATED_TEXT  # from the idle wait
    assert fallback["update_outlived_read_seconds"] == 106

    # a passing check: the read comes from its exit value
    passed = _full_facts()
    passed.check_error = None
    passed.refused = at.TaskFacts(1, 2, _ms(READ), _ms(READ), "SUCCESS")
    passed.check_exit = _report([_entry(UPDATE, "RUNNING")], state="IDLE").exit_value()
    passed.check_exit["outcome"] = "idle"
    got = at.build_record(passed)
    assert got["check_read_ts"] == READ_TEXT
    assert got["outcome"] == "update_ended_before_check"


def test_ac103_missing_inputs_give_nulls_and_incomplete_and_no_secret() -> None:
    record = at.build_record(at.Ac97Facts(UPDATE, at.UpdateWatch(UPDATE)))
    assert record["update_id"] == UPDATE
    assert {k: v for k, v in record.items() if k not in ("update_id", "outcome")} == {
        k: None for k in at.RECORD_FIELDS if k not in ("update_id", "outcome")
    }
    assert record["outcome"] == "incomplete"
    json.dumps(record)

    url, bearer, token = _tokens()
    facts = _full_facts()
    facts.check_error = f"{url} {bearer} {token} " + _busy_message()
    facts.events = [{**e, "message": f"{e['message']} {url} {bearer} {token}"} for e in _events()]
    facts.refused = at.TaskFacts(1, 2, _ms(READ), _ms(READ), url)
    facts.rerun_check_result = token
    facts.rerun_refresh_result = bearer
    scrubbed = at.build_record(facts)
    assert scrubbed["check_result"] is None
    assert scrubbed["rerun_check_result"] is None
    assert scrubbed["rerun_refresh_result"] is None
    text = json.dumps(scrubbed)
    for forbidden in at.FORBIDDEN_TEXT:
        assert forbidden not in text, forbidden
    assert scrubbed["check_read_update_state"] == "WAITING_FOR_RESOURCES"  # still parsed
    assert at.build_record(at.Ac97Facts(url, at.UpdateWatch(url)))["update_id"] is None
