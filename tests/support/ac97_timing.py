"""Timing evidence of the live AC-97 test (AC97_TIMING_EVIDENCE, FR-55 to FR-59, G-28 to G-32).

Pure helpers: no SDK, no I/O, no clock (NFR-33). The live test fills ``Ac97Facts`` with primitives
it read from the platform; ``build_record`` turns them into the ``out/evidence/ac97_timing.json``
record. Every timestamp passes through ``pipeline_guard.utc_text`` (UTC with ``Z``, whole seconds;
a value without a zone is null, G-28). A value that is missing or unreadable is null and is never
estimated. The text of the busy message is the one rendered by ``PipelineReport.message`` at
v0.4.0 (A-34); the unit tests build it with the library itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from smart_meter_peak_prediction.pipeline_guard import TERMINAL_UPDATE_STATES, utc_text

EVIDENCE_NAME = "ac97_timing"
EVIDENCE_PATH_TEXT = "out/evidence/ac97_timing.json"
EVIDENCE_NOTE = (
    "AC-97 timing evidence: out/evidence/ac97_timing.json. Copy it into the release's "
    "BUILD_REPORT before the next attempt overwrites it (runbook: AC-97 timing evidence)."
)
RECORD_FIELDS = (
    "update_id",
    "update_created_ts",
    "update_ended_ts",
    "update_end_source",
    "update_final_state",
    "refused_run_id",
    "check_task_run_id",
    "check_started_ts",
    "check_ended_ts",
    "check_result",
    "check_read_ts",
    "check_read_update_state",
    "check_read_pipeline_state",
    "read_after_creation_seconds",
    "update_outlived_read_seconds",
    "rerun_run_id",
    "rerun_check_result",
    "rerun_refresh_result",
    "outcome",
)
OUTCOMES = ("refused", "update_ended_before_check", "incomplete")
END_SOURCES = ("platform", "observed_terminal")
FORBIDDEN_TEXT = ("https://", "dapi", "Bearer")  # G-31

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
_CHECKED_AT = re.compile(rf"\(checked at ({_UTC})\)")
_NOT_REPORTED = ("not reported", "creation time not reported")
_DIGITS = re.compile(r"^\d+$")


@dataclass(frozen=True)
class CheckRead:
    """What the check read: its own "checked at" time and the state of the update (FR-56)."""

    read_ts: str | None = None
    update_state: str | None = None
    pipeline_state: str | None = None
    update_created_ts: str | None = None


@dataclass(frozen=True)
class TaskFacts:
    run_id: int | None = None  # job run id
    task_run_id: int | None = None
    start: Any = None  # epoch ms as the platform reports it
    end: Any = None
    result: str | None = None


@dataclass
class UpdateWatch:
    """Filled by the live idle wait: what its polls of ``pipelines.get`` showed about the update."""

    update_id: str
    created: Any = None
    state: str | None = None
    observed_terminal_ts: str | None = None


@dataclass
class Ac97Facts:
    update_id: str
    watch: UpdateWatch
    update_created: Any = None  # from get_update
    update_state: str | None = None  # from get_update
    events: list[dict] | None = None  # PipelineEvent.as_dict() of one page
    end_read: bool = False
    refused: TaskFacts | None = None
    check_error: str | None = None
    check_exit: dict | None = None
    rerun_run_id: int | None = None
    rerun_check_result: str | None = None
    rerun_refresh_result: str | None = None


# ----------------------------------------------------------------------------- margins
def _seconds_between(earlier: str | None, later: str | None) -> int | None:
    if earlier is None or later is None:
        return None
    start = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
    end = datetime.fromisoformat(later.replace("Z", "+00:00"))
    return int((end - start).total_seconds())


def margins(created: Any, read: Any, ended: Any) -> dict[str, Any]:
    """The three timestamps (G-28) and the two signed margins in whole seconds (G-29)."""
    created_ts, read_ts, ended_ts = utc_text(created), utc_text(read), utc_text(ended)
    return {
        "update_created_ts": created_ts,
        "check_read_ts": read_ts,
        "update_ended_ts": ended_ts,
        "read_after_creation_seconds": _seconds_between(created_ts, read_ts),
        "update_outlived_read_seconds": _seconds_between(read_ts, ended_ts),
    }


# ----------------------------------------------------------------------------- reading the check
def parse_check_message(text: str | None, update_id: str) -> CheckRead:
    """Read the busy message of ``PipelineReport.message`` (G-30); anything else gives nulls."""
    if not isinstance(text, str) or not text:
        return CheckRead()
    clean = _ANSI.sub("", text)
    checked = _CHECKED_AT.search(clean)
    read_ts = checked.group(1) if checked else None
    line = re.search(
        rf"update {re.escape(str(update_id))}, state ([A-Z_]+), "
        rf"pipeline state ([A-Z_]+|not reported), "
        rf"created ({_UTC}|creation time not reported)",
        clean,
    )
    if not line:
        return CheckRead(read_ts=read_ts)
    state, pipeline_state, created = line.groups()
    return CheckRead(
        read_ts=read_ts,
        update_state=state,
        pipeline_state=None if pipeline_state in _NOT_REPORTED else pipeline_state,
        update_created_ts=None if created in _NOT_REPORTED else created,
    )


def _upper_text(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z_]+", value) else None


def read_from_exit_value(value: Mapping | None, update_id: str) -> CheckRead:
    """The exit value of a passing check: ``checked_at``, pipeline state, U's state if listed."""
    if not isinstance(value, Mapping):
        return CheckRead()
    pipeline = value.get("pipeline")
    pipeline = pipeline if isinstance(pipeline, Mapping) else {}
    latest = pipeline.get("latest_update")
    state = None
    if isinstance(latest, Mapping) and latest.get("update_id") == update_id:
        state = _upper_text(latest.get("state"))
    return CheckRead(
        read_ts=utc_text(value.get("checked_at")),
        update_state=state,
        pipeline_state=_upper_text(pipeline.get("state")),
    )


# ----------------------------------------------------------------------------- end of the update
def pick_update_end(
    events: Iterable[Mapping], update_id: str, final_state: str | None
) -> str | None:
    """Earliest ``update_progress`` event of U that names its terminal state (DA-35)."""
    if final_state not in TERMINAL_UPDATE_STATES:
        return None
    word = re.compile(rf"\b{re.escape(final_state)}\b")
    found: list[str] = []
    for event in events or []:
        if not isinstance(event, Mapping) or event.get("event_type") != "update_progress":
            continue
        origin = event.get("origin")
        if not isinstance(origin, Mapping) or origin.get("update_id") != update_id:
            continue
        message = event.get("message")
        stamp = utc_text(event.get("timestamp"))
        if isinstance(message, str) and word.search(message) and stamp is not None:
            found.append(stamp)
    return min(found) if found else None


def resolve_update_end(platform_ts: Any, observed_ts: Any) -> tuple[str | None, str | None]:
    """The end time and its source (FR-57): the platform's, else the observed upper bound."""
    platform, observed = utc_text(platform_ts), utc_text(observed_ts)
    if platform is not None:
        return platform, "platform"
    if observed is not None:
        return observed, "observed_terminal"
    return None, None


# ----------------------------------------------------------------------------- outcome
def decide_outcome(
    check_result: str | None, read: CheckRead, exit_outcome: str | None, outlived: int | None
) -> str:
    """G-32 precedence: an early end first, then a proven refusal, else incomplete."""
    if exit_outcome == "idle" or (outlived is not None and outlived <= 0):
        return "update_ended_before_check"
    if (
        check_result == "FAILED"
        and read.read_ts is not None
        and read.update_state is not None
        and read.update_state not in TERMINAL_UPDATE_STATES
    ):
        return "refused"
    return "incomplete"


# ----------------------------------------------------------------------------- record
def _run_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _DIGITS.match(value):
        return int(value)
    return None


def _safe(value: Any) -> Any:
    """G-31: no URL, token or bearer text in the record."""
    if isinstance(value, str) and any(token in value for token in FORBIDDEN_TEXT):
        return None
    return value


def _terminal(state: Any) -> str | None:
    return state if isinstance(state, str) and state in TERMINAL_UPDATE_STATES else None


def build_record(facts: Ac97Facts) -> dict[str, Any]:
    """Exactly ``RECORD_FIELDS``; ``Evidence.save`` adds ``saved_at_ms``."""
    update_id = facts.update_id
    refused = facts.refused or TaskFacts()
    if facts.check_error is not None:
        read = parse_check_message(facts.check_error, update_id)
    else:
        read = read_from_exit_value(facts.check_exit, update_id)

    watch = facts.watch
    created = next(
        (
            ts
            for ts in (
                utc_text(facts.update_created),
                utc_text(watch.created),
                read.update_created_ts,
            )
            if ts is not None
        ),
        None,
    )
    final_state = _terminal(facts.update_state) or _terminal(watch.state)
    platform_end = pick_update_end(facts.events or [], update_id, final_state)
    ended, source = resolve_update_end(platform_end, watch.observed_terminal_ts)
    figures = margins(created, read.read_ts, ended)

    exit_outcome = facts.check_exit.get("outcome") if isinstance(facts.check_exit, dict) else None
    record: dict[str, Any] = {
        "update_id": update_id,
        "update_created_ts": figures["update_created_ts"],
        "update_ended_ts": figures["update_ended_ts"],
        "update_end_source": source,
        "update_final_state": final_state,
        "refused_run_id": _run_id(refused.run_id),
        "check_task_run_id": _run_id(refused.task_run_id),
        "check_started_ts": utc_text(refused.start),
        "check_ended_ts": utc_text(refused.end),
        "check_result": refused.result,
        "check_read_ts": figures["check_read_ts"],
        "check_read_update_state": read.update_state,
        "check_read_pipeline_state": read.pipeline_state,
        "read_after_creation_seconds": figures["read_after_creation_seconds"],
        "update_outlived_read_seconds": figures["update_outlived_read_seconds"],
        "rerun_run_id": _run_id(facts.rerun_run_id),
        "rerun_check_result": facts.rerun_check_result,
        "rerun_refresh_result": facts.rerun_refresh_result,
        "outcome": decide_outcome(
            refused.result,
            read,
            exit_outcome if isinstance(exit_outcome, str) else None,
            figures["update_outlived_read_seconds"],
        ),
    }
    return {key: _safe(value) for key, value in record.items()}


# ----------------------------------------------------------------------------- failure hint
def failure_hint(update_id: str) -> str:
    """The shipped DA-31 advice (v0.4.0), then the evidence file (FR-58)."""
    return (
        f"The update {update_id} may have ended before the check read it "
        "(DA-31); the no-op update lasted about 125 s on dev. Run the test again; then "
        "start the update with full_refresh=True; if it keeps passing vacuously record "
        "AC-97 as Partial with a direct pipeline_guard.check_pipeline read during the "
        f"update. {EVIDENCE_NOTE}"
    )
