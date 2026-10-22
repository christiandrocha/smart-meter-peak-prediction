"""Read-only pre-check before the shared pipeline task (FR-33 to FR-38, G-13 to G-20, ADR 0012).

The daily job ``smart_meter_peak_model`` and the ingestion job ``smart_meter_ingestion`` start
updates of one pipeline, which accepts one update at a time. ``check`` reads the active runs of the
ingestion job and the latest updates of the pipeline through a client-like object and returns a
``GuardReport``; ``enforce`` raises ``PipelineGuardError`` with the operator message unless the
report is clean. The module never imports the Databricks SDK (the notebook builds the client), so
CI needs no SDK. Enum members are compared by their ``.value`` string, otherwise ``str()``.

Read calls only (``READ_CALLS``); one read per object, no loop, no sleep. Anything unknown or
unreadable counts as busy or unreadable: the check fails closed (D-45). Time is UTC with ``Z``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import islice
from typing import Any

INGESTION_JOB = "smart_meter_ingestion"
PIPELINE = "smart_meter_silver_gold"
PEAK_JOB = "smart_meter_peak_model"

# Life-cycle states of a job run that are over (G-16); any other value, even a future one, is
# active.
TERMINAL_RUN_STATES = frozenset({"TERMINATED", "SKIPPED", "INTERNAL_ERROR"})
# States of a pipeline update that are over (G-17); a missing or unknown state is active.
TERMINAL_UPDATE_STATES = frozenset({"COMPLETED", "FAILED", "CANCELED"})
# Overall pipeline states (G-21): these pass; DELETED is unusable; any other value, including a
# missing or future one, is busy. FAILED means the last update failed, so a new one can start.
PASS_PIPELINE_STATES = frozenset({"IDLE", "FAILED"})
ACTIVE_PIPELINE_STATES = frozenset(
    {"DEPLOYING", "STARTING", "RUNNING", "STOPPING", "RECOVERING", "RESETTING"}
)
UNUSABLE_PIPELINE_STATE = "DELETED"
# The only client methods this module calls (G-19).
READ_CALLS = ("jobs.get", "jobs.list", "jobs.list_runs", "pipelines.get")
# Keywords of databricks.sdk.config.Config; WorkspaceClient 0.40.0 rejects them directly (DA-20).
CLIENT_LIMITS = {"retry_timeout_seconds": 60, "http_timeout_seconds": 30}

MAX_RUNS_READ = 25
MAX_JOBS_READ = 2
MAX_ERROR_CHARS = 200

_DEV_PREFIX = re.compile(r"^\[dev [^\]]+\] ")  # development-mode display prefix
_EPOCH_MS = re.compile(r"^\d{10,}$")
_POSITIVE_INT = re.compile(r"^[1-9]\d*$")
# Text that must never reach a task error or an email: bearer tokens, PATs and URLs (hosts).
_REDACT = re.compile(r"(?i)bearer\s+\S+|\bdapi\w+|https?://\S+")


class PipelineGuardError(RuntimeError):
    """The pipeline is busy or its state cannot be established; the message is for the operator."""


def strip_dev_prefix(name: str | None) -> str:
    return _DEV_PREFIX.sub("", name or "", count=1)


def utc_text(value: Any) -> str | None:
    """``YYYY-MM-DDTHH:MM:SSZ`` for an ISO 8601 string with a zone, epoch ms or an aware datetime.

    A naive, empty or unparseable value gives None, so no non-UTC time is ever printed.
    """
    moment: datetime | None = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, bool):
        return None
    elif isinstance(value, int | float):
        moment = _from_epoch_ms(value) if value > 0 else None
    elif isinstance(value, str):
        text = value.strip()
        if _EPOCH_MS.match(text):
            moment = _from_epoch_ms(int(text))
        elif text:
            try:
                moment = datetime.fromisoformat(text[:-1] + "+00:00" if text[-1] in "Zz" else text)
            except ValueError:
                moment = None
    if moment is None or moment.tzinfo is None:
        return None
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_epoch_ms(value: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _enum_text(value: Any) -> str | None:
    if value is None:
        return None
    inner = getattr(value, "value", None)
    return str(inner if inner is not None else value)


def _describe_error(exc: Exception) -> str:
    """Class, API error code and the first line of the message, cut to 200 characters."""
    code = getattr(exc, "error_code", None)
    label = type(exc).__name__ + (f" ({code})" if code else "")
    lines = str(exc).strip().splitlines()
    first = _REDACT.sub("<redacted>", lines[0].strip() if lines else "")
    return f"{label}: {first[:MAX_ERROR_CHARS]}" if first else label


# ----------------------------------------------------------------------------- report
@dataclass(frozen=True)
class ActiveRun:
    run_id: int | str
    state: str
    started: str | None  # UTC text or None (queued, no start time)


@dataclass(frozen=True)
class ActiveUpdate:
    update_id: str
    state: str
    created: str | None


@dataclass(frozen=True)
class Unreadable:
    subject: str  # "job smart_meter_ingestion (job id 1)"
    read: str  # what could not be read
    error: str


@dataclass(frozen=True)
class GuardReport:
    checked_at: str
    ingestion_job_id: str
    pipeline_id: str
    job_name: str | None = None
    pipeline_name: str | None = None
    pipeline_state: str | None = None
    latest_update: tuple[str, str] | None = None  # (update_id, state)
    pipeline_busy: bool = False  # G-21: the overall pipeline state is not a pass state
    runs: tuple[ActiveRun, ...] = ()
    updates: tuple[ActiveUpdate, ...] = ()
    unreadable: tuple[Unreadable, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not (self._blocked or self.unreadable)

    @property
    def _blocked(self) -> bool:
        return bool(self.runs or self.updates or self.pipeline_busy)

    def _pipeline_state_text(self) -> str:
        return self.pipeline_state or "not reported"

    def _job_subject(self) -> str:
        return f"job {INGESTION_JOB} (job id {_shown(self.ingestion_job_id)})"

    def _pipeline_subject(self) -> str:
        return f"pipeline {PIPELINE} (pipeline id {_shown(self.pipeline_id)})"

    def message(self) -> str:
        """FR-36 (busy) and FR-38 (unreadable) text; a short confirmation when idle."""
        if self.ok:
            return (
                f"check_pipeline_idle: the shared pipeline is idle (checked at {self.checked_at})."
            )
        lines: list[str] = []
        if self._blocked:
            lines.append(
                "check_pipeline_idle stopped the run before refresh_silver_gold: the shared "
                f"pipeline is busy (checked at {self.checked_at})."
            )
            lines.append("Blocking:")
            for run in self.runs:
                lines.append(
                    f"  - {self._job_subject()}: active run {run.run_id}, state {run.state}, "
                    f"started {run.started or 'not started'}"
                )
            for update in self.updates:
                lines.append(
                    f"  - {self._pipeline_subject()}: update {update.update_id}, "
                    f"state {update.state}, pipeline state {self._pipeline_state_text()}, "
                    f"created {update.created or 'creation time not reported'}"
                )
            if self.pipeline_busy and not self.updates:
                lines.append(
                    f"  - {self._pipeline_subject()}: pipeline state "
                    f"{self._pipeline_state_text()}, no active update listed in latest_updates"
                )
            if self.unreadable:
                lines.append("Could not read:")
        else:
            lines.append(
                "check_pipeline_idle could not establish the pipeline state and fails closed "
                f"(checked at {self.checked_at})."
            )
            lines.append("Could not read:")
        for item in self.unreadable:
            lines.append(f"  - {item.subject}: {item.read}: {item.error}")
        if self._blocked:
            action = "wait until the run or update named above ends"
            if self.unreadable:
                action += " and fix the cause named under 'Could not read'"
            lines.append(f"Action: {action}, then rerun {PEAK_JOB}.")
            lines.append(
                "Without action, the next scheduled run (08:00 UTC) is the retry. "
                "refresh_silver_gold and the tasks after it did not start; rerunning is safe."
            )
        else:
            lines.append(
                "Action: fix the cause named above (deployment, permission or API availability), "
                f"then rerun {PEAK_JOB}."
            )
            lines.append("Without action, the next scheduled run (08:00 UTC) checks again.")
        return "\n".join(lines)

    def exit_value(self) -> dict[str, Any]:
        """Notebook exit value of an idle check (keys fixed, DESIGN Data Model)."""
        latest = None
        if self.latest_update:
            latest = {"update_id": self.latest_update[0], "state": self.latest_update[1]}
        job_id: int | str = (
            int(self.ingestion_job_id)
            if _POSITIVE_INT.match(self.ingestion_job_id)
            else self.ingestion_job_id
        )
        return {
            "outcome": "idle" if self.ok else ("busy" if self._blocked else "unknown"),
            "checked_at": self.checked_at,
            "ingestion_job": {
                "job_id": job_id,
                "name": strip_dev_prefix(self.job_name) if self.job_name else None,
                "active_runs": [str(run.run_id) for run in self.runs],
            },
            "pipeline": {
                "pipeline_id": self.pipeline_id,
                "name": strip_dev_prefix(self.pipeline_name) if self.pipeline_name else None,
                "state": self.pipeline_state,
                "latest_update": latest,
            },
        }


def _shown(identifier: str) -> str:
    text = (identifier or "").strip()
    return text[:80] if text else "missing"


# ----------------------------------------------------------------------------- checks
def _checked_at(now: datetime | None) -> str:
    moment = now or datetime.now(UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_id(text: str) -> bool:
    return bool(text) and "${" not in text


def check(
    client: Any, ingestion_job_id: str | int, pipeline_id: str, *, now: datetime | None = None
) -> GuardReport:
    """Read the ingestion job's active runs and the pipeline's state and latest updates."""
    job_text = str(ingestion_job_id if ingestion_job_id is not None else "").strip()
    pipeline_text = str(pipeline_id if pipeline_id is not None else "").strip()
    unreadable: list[Unreadable] = []
    job_subject = f"job {INGESTION_JOB} (job id {_shown(job_text)})"
    pipeline_subject = f"pipeline {PIPELINE} (pipeline id {_shown(pipeline_text)})"

    job_name: str | None = None
    runs: list[ActiveRun] = []
    if not (_valid_id(job_text) and _POSITIVE_INT.match(job_text)):
        unreadable.append(Unreadable(job_subject, "ingestion_job_id", "id missing or not resolved"))
    else:
        job_name = _read_job(client, int(job_text), job_subject, runs, unreadable)

    pipeline_name: str | None = None
    pipeline_state: str | None = None
    pipeline_busy = False
    latest: tuple[str, str] | None = None
    updates: list[ActiveUpdate] = []
    if not _valid_id(pipeline_text):
        unreadable.append(Unreadable(pipeline_subject, "pipeline_id", "id missing or not resolved"))
    else:
        pipeline_name, pipeline_state, latest, pipeline_busy = _read_pipeline(
            client, pipeline_text, pipeline_subject, updates, unreadable
        )

    return GuardReport(
        checked_at=_checked_at(now),
        ingestion_job_id=job_text,
        pipeline_id=pipeline_text,
        job_name=job_name,
        pipeline_name=pipeline_name,
        pipeline_state=pipeline_state,
        latest_update=latest,
        pipeline_busy=pipeline_busy,
        runs=tuple(runs),
        updates=tuple(updates),
        unreadable=tuple(unreadable),
    )


def _read_job(
    client: Any, job_id: int, subject: str, runs: list[ActiveRun], unreadable: list[Unreadable]
) -> str | None:
    """G-14 identity and uniqueness, then G-16 active runs. Returns the deployed job name."""
    try:
        job = client.jobs.get(job_id=job_id)
        deployed = getattr(getattr(job, "settings", None), "name", None) or ""
    except Exception as exc:  # noqa: BLE001 - fail closed on any read error (G-18)
        unreadable.append(Unreadable(subject, "job", _describe_error(exc)))
        return None
    if strip_dev_prefix(deployed) != INGESTION_JOB:
        unreadable.append(
            Unreadable(subject, "job", f"the id names another job: {deployed or 'no name'!r}")
        )
        return deployed or None
    try:
        same_name = [j.job_id for j in islice(client.jobs.list(name=deployed), MAX_JOBS_READ)]
    except Exception as exc:  # noqa: BLE001
        unreadable.append(Unreadable(subject, "job name list", _describe_error(exc)))
        return deployed
    if len(same_name) != 1:
        found = ", ".join(str(i) for i in same_name) or "none"
        unreadable.append(
            Unreadable(subject, "job name list", f"{deployed!r} is not unique (job ids: {found})")
        )
        return deployed
    try:
        listed = list(islice(client.jobs.list_runs(job_id=job_id, active_only=True), MAX_RUNS_READ))
    except Exception as exc:  # noqa: BLE001
        unreadable.append(Unreadable(subject, "active runs", _describe_error(exc)))
        return deployed
    for run in listed:
        state = _enum_text(getattr(getattr(run, "state", None), "life_cycle_state", None))
        if state in TERMINAL_RUN_STATES:
            continue  # listed, but already over (list race)
        runs.append(
            ActiveRun(
                run_id=run.run_id,
                state=state or "UNKNOWN",
                started=utc_text(getattr(run, "start_time", None)),
            )
        )
    return deployed


def _read_pipeline(
    client: Any,
    pipeline_id: str,
    subject: str,
    updates: list[ActiveUpdate],
    unreadable: list[Unreadable],
) -> tuple[str | None, str | None, tuple[str, str] | None, bool]:
    """G-15 identity, G-21 overall state, then G-17 active updates (``latest_updates``, newest
    first). The last value is True when the overall state is busy."""
    try:
        pipeline = client.pipelines.get(pipeline_id=pipeline_id)
        name = getattr(pipeline, "name", None) or ""
        state = _enum_text(getattr(pipeline, "state", None))
        entries = list(getattr(pipeline, "latest_updates", None) or [])
    except Exception as exc:  # noqa: BLE001
        unreadable.append(Unreadable(subject, "pipeline", _describe_error(exc)))
        return None, None, None, False
    if strip_dev_prefix(name) != PIPELINE:
        unreadable.append(
            Unreadable(subject, "pipeline", f"the id names another pipeline: {name or 'no name'!r}")
        )
        return name or None, state, None, False
    busy = False
    if state == UNUSABLE_PIPELINE_STATE:
        unreadable.append(Unreadable(subject, "pipeline state", f"{state}, not usable"))
    elif state not in PASS_PIPELINE_STATES:
        busy = True  # an active, missing or unknown state (G-21)
    latest: tuple[str, str] | None = None
    for index, entry in enumerate(entries):
        entry_state = _enum_text(getattr(entry, "state", None))
        update_id = str(getattr(entry, "update_id", None) or "unknown")
        if index == 0:
            latest = (update_id, entry_state or "UNKNOWN")
        if entry_state in TERMINAL_UPDATE_STATES:
            continue
        updates.append(
            ActiveUpdate(
                update_id=update_id,
                state=entry_state or "UNKNOWN",
                created=utc_text(getattr(entry, "creation_time", None)),
            )
        )
    return name, state, latest, busy


def run(
    client_factory: Callable[[], Any],
    ingestion_job_id: str | int,
    pipeline_id: str,
    *,
    now: datetime | None = None,
) -> GuardReport:
    """Build the client and check; a failure to build it is unreadable for both objects (G-18)."""
    try:
        client = client_factory()
    except Exception as exc:  # noqa: BLE001
        error = _describe_error(exc)
        job_text = str(ingestion_job_id if ingestion_job_id is not None else "").strip()
        pipeline_text = str(pipeline_id if pipeline_id is not None else "").strip()
        return GuardReport(
            checked_at=_checked_at(now),
            ingestion_job_id=job_text,
            pipeline_id=pipeline_text,
            unreadable=(
                Unreadable(
                    f"job {INGESTION_JOB} (job id {_shown(job_text)})", "workspace client", error
                ),
                Unreadable(
                    f"pipeline {PIPELINE} (pipeline id {_shown(pipeline_text)})",
                    "workspace client",
                    error,
                ),
            ),
        )
    return check(client, ingestion_job_id, pipeline_id, now=now)


def enforce(report: GuardReport) -> dict[str, Any]:
    """Raise ``PipelineGuardError`` with the operator message unless idle; else the exit value."""
    if not report.ok:
        raise PipelineGuardError(report.message())
    return report.exit_value()
