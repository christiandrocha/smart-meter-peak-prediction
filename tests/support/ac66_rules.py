"""AC-66 both legs (AC66_BOTH_LEGS): precondition, expectations, records and verdict.

No SDK, no I/O, no clock: every side effect of ``run_leg`` is an injected callable (FR-90, NFR-45).
The rules serve FR-84 to FR-90: a rerun leg and a rebuild leg for PEAK_MODEL AC-66 (each refuses in
the wrong table state, FR-86, and leaves no ``passed`` record after a failure, FR-87), and a verdict
that passes only when both legs passed against the current snapshot in order (FR-88, FR-89).
Guards G-46 to G-53 of DESIGN_AC66_BOTH_LEGS.md are marked where they apply. The only project import
is ``pipeline_guard.utc_text`` (SDK-free), the single place that renders UTC text (NFR-43).
AC66_ZERO_NEW_RUNS (FR-96 to FR-100, guards G-54 to G-58) adds the run count: ``run_leg``
reads the run ids of smart_meter_peak_model through the injected ``runs`` before anything
else and again after its refusal or its job run, and ``count_runs`` compares the two reads.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from smart_meter_peak_prediction.pipeline_guard import utc_text

SNAPSHOT_NAME = "ac66_before_rebuild"
LEG_NAMES = {"rerun": "ac66_rerun_leg", "rebuild": "ac66_rebuild_leg"}
VERDICT_NAME = "ac66_verdict"
SNAPSHOT_TEST = "test_ac66_before_rebuild_snapshot"
RERUN_TEST = "test_ac66_rerun_leg_ac163_ac164_merges_nothing_and_checksums_equal"
REBUILD_TEST = "test_ac66_rebuild_leg_ac162_ac164_inserts_the_snapshot_rows_and_checksums_equal"
VERDICT_TEST = "test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot"
RESET_COMMAND = "python scripts/reset_peak_model_outputs.py --confirm"
TABLES = (  # snapshot key, table shown in messages (SNAPSHOT_TABLES order)
    ("silver_weather", "silver.weather_hourly"),
    ("features", "ml.household_features_daily"),
    ("labels", "ml.household_labels_daily"),
)
MERGE_TASKS = {
    "silver_weather": "build_weather_silver",
    "features": "build_features",
    "labels": "build_labels",
}
RECORD_FIELDS = (
    "leg",
    "outcome",
    "snapshot_saved_at_ms",
    "run_id",
    "started_ts",
    "ended_ts",
    "tables_present_at_start",
    "merges",
    "after",
)
VERDICT_FIELDS = (
    "verdict",
    "problems",
    "snapshot_saved_at_ms",
    "rerun_saved_at_ms",
    "rebuild_saved_at_ms",
)
UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
_MERGE_FIELDS = ("inserted", "updated", "deleted")
_SECRET_MARKERS = ("https://", "dapi", "Bearer")


@dataclass(frozen=True)
class Snapshot:
    saved_at_ms: int
    tables: Mapping[str, Mapping[str, Any]]  # key -> {"row_count": int, "checksum": str}


@dataclass(frozen=True)
class Problem:
    subject: str  # "snapshot", "rerun leg", "rebuild leg", "verdict rule"
    kind: str  # missing, unreadable, malformed, failed, stale, out of order, inconsistent, ...
    detail: str  # names the file and ends with "next: ..."

    def text(self) -> str:
        return f"{self.subject}: {self.kind}: {self.detail}"


@dataclass(frozen=True)
class Precondition:
    allowed: bool
    message: str  # "" when allowed


@dataclass(frozen=True)
class LegRun:
    run_id: Any
    start_ms: Any
    end_ms: Any
    outputs: Mapping[str, Any]  # task key -> parsed exit value


@dataclass(frozen=True)
class Verdict:
    record: dict[str, Any]  # exactly VERDICT_FIELDS
    problems: tuple[Problem, ...]

    @property
    def passed(self) -> bool:
        return self.record.get("verdict") == "pass" and not self.problems


class EvidenceStore(Protocol):
    def read_text(self, name: str) -> str | None: ...

    def save(self, name: str, data: dict[str, Any]) -> None: ...

    def remove(self, name: str) -> None: ...


# ----------------------------------------------------------------------------- small helpers
def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _canon(value: Any) -> str:
    """Type-strict text of a JSON-like value (``True`` and ``1`` differ)."""
    return json.dumps(value, sort_keys=True, default=str)


def _file(name: str) -> str:
    return f"out/evidence/{name}.json"


def _safe_text(value: Any) -> str | None:
    """A task-output string, or None when it could carry a secret (G-52)."""
    if not isinstance(value, str) or any(marker in value for marker in _SECRET_MARKERS):
        return None
    return value


def _load(text: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """Parse one evidence file: (object, None) or (None, kind) (G-48)."""
    if text is None:
        return None, "missing"
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return None, "unreadable"
    if not isinstance(parsed, dict):
        return None, "unreadable"
    return parsed, None


def _valid_table(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and _is_int(entry.get("row_count"))
        and isinstance(entry.get("checksum"), str)
    )


# ----------------------------------------------------------------------------- snapshot (G-48)
def parse_snapshot(text: str | None) -> tuple[Snapshot | None, Problem | None]:
    file = _file(SNAPSHOT_NAME)
    next_step = (
        f"next: run {SNAPSHOT_TEST} with the three tables present, then the order of "
        "runbook section 8"
    )
    obj, kind = _load(text)
    if obj is None or kind is not None:
        detail = f"{file} is {kind}; {next_step}"
        return None, Problem("snapshot", kind or "unreadable", detail)
    if not _is_int(obj.get("saved_at_ms")) or not all(
        _valid_table(obj.get(key)) for key, _ in TABLES
    ):
        detail = f"{file} lacks saved_at_ms or a table with row_count and checksum; {next_step}"
        return None, Problem("snapshot", "malformed", detail)
    tables = {
        key: {"row_count": obj[key]["row_count"], "checksum": obj[key]["checksum"]}
        for key, _ in TABLES
    }
    return Snapshot(saved_at_ms=obj["saved_at_ms"], tables=tables), None


# ----------------------------------------------------------------------------- precondition (G-46)
def precondition(leg: str, *, snapshot_ok: bool, present: Mapping[str, Any]) -> Precondition:
    """Allowed only for the rerun leg with all tables present, the rebuild leg with none."""
    try:
        return _precondition(leg, snapshot_ok, present)
    except Exception as exc:  # totality (G-51)
        return Precondition(
            False, f"AC-66 {leg} leg refused before any job run: {type(exc).__name__}"
        )


def _precondition(leg: str, snapshot_ok: bool, present: Mapping[str, Any]) -> Precondition:
    head = f"AC-66 {leg} leg refused before any job run: "
    if leg not in LEG_NAMES:
        return Precondition(False, head + "unknown leg (expected rerun or rebuild)")
    reasons: list[str] = []
    nexts: list[str] = []
    if not snapshot_ok:
        reasons.append(f"the snapshot {_file(SNAPSHOT_NAME)} is missing, unreadable or malformed")
        nexts.append(f"run {SNAPSHOT_TEST} with the three tables present")
    states: dict[str, Any] = {}
    for key, shown in TABLES:
        value = present.get(key) if isinstance(present, Mapping) else None
        states[key] = value if isinstance(value, bool) else None
        if states[key] is None:
            reasons.append(f"{shown} existence is unknown")
    known = [value for value in states.values() if value is not None]
    wanted = leg == "rerun"  # rerun needs every table present, rebuild none
    wrong = [shown for key, shown in TABLES if states[key] is not None and states[key] != wanted]
    if wrong:
        state_word = "missing" if wanted else "present"
        reasons.extend(f"{shown} is {state_word}" for shown in wrong)
    if len(known) == len(TABLES) and 0 < sum(known) < len(TABLES):
        nexts.append(
            "partial state: a full run of smart_meter_peak_model restores the missing tables, "
            f"then start again with {SNAPSHOT_TEST}"
        )
    elif wrong and leg == "rerun":
        nexts.append(f"the tables are gone: run the rebuild leg ({REBUILD_TEST})")
    elif wrong:
        nexts.append(f"run the rerun leg ({RERUN_TEST}), then the user runs {RESET_COMMAND}")
    if not reasons:
        return Precondition(True, "")
    message = head + "; ".join(reasons)
    if nexts:
        message += "; next: " + "; ".join(nexts)
    return Precondition(False, message)


# ----------------------------------------------------------------------------- expectations
def merges_from_outputs(outputs: Mapping[str, Any]) -> dict[str, Any]:
    merges: dict[str, Any] = {}
    for key, task in MERGE_TASKS.items():
        output = outputs.get(task) if isinstance(outputs, Mapping) else None
        merge = output.get("merge") if isinstance(output, Mapping) else None
        merges[key] = dict(merge) if isinstance(merge, Mapping) else None
    return merges


def expected_merges(leg: str, snapshot: Snapshot) -> dict[str, dict[str, int]]:
    """Rerun: 0 / 0 / 0. Rebuild: inserted equals the snapshot row count, 0 updated, 0 deleted."""
    return {
        key: {
            "inserted": snapshot.tables[key]["row_count"] if leg == "rebuild" else 0,
            "updated": 0,
            "deleted": 0,
        }
        for key, _ in TABLES
    }


def _merge_text(merge: Any) -> str:
    if not isinstance(merge, Mapping):
        return "no merge object"
    return " ".join(
        f"{name}={merge[name] if _is_int(merge.get(name)) else '?'}" for name in _MERGE_FIELDS
    )


def check_leg(
    leg: str, snapshot: Snapshot, merges: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    """[] means pass. Texts hold keys, field names and integers only (G-52)."""
    problems: list[str] = []
    expected = expected_merges(leg, snapshot)
    for key, _ in TABLES:
        got = merges.get(key) if isinstance(merges, Mapping) else None
        if _canon(got) != _canon(expected[key]):
            problems.append(
                f"{key}: merge is {_merge_text(got)}, expected {_merge_text(expected[key])}"
            )
        state = after.get(key) if isinstance(after, Mapping) else None
        want = snapshot.tables[key]
        if not isinstance(state, Mapping):
            problems.append(f"{key}: no row count and checksum after the run")
            continue
        if _canon(state.get("row_count")) != _canon(want["row_count"]):
            problems.append(f"{key}: row_count differs from the snapshot")
        if _canon(state.get("checksum")) != _canon(want["checksum"]):
            problems.append(f"{key}: checksum differs from the snapshot")
    return problems


# ----------------------------------------------------------------------------- leg record
def leg_record(
    leg: str,
    outcome: str,
    snapshot_saved_at_ms: int,
    run: LegRun | None,
    present: Mapping[str, Any],
    merges: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The RECORD_FIELDS object; no value echoes a secret-like string (G-52, G-53)."""
    run_id = None
    started = ended = None
    if run is not None:
        raw = run.run_id
        if _is_int(raw):
            run_id = raw
        elif isinstance(raw, str) and raw.isascii() and raw.isdigit():
            run_id = int(raw)
        started, ended = utc_text(run.start_ms), utc_text(run.end_ms)
    merge_out: dict[str, Any] = {}
    after_out: dict[str, Any] = {}
    for key, _ in TABLES:
        merge = merges.get(key) if isinstance(merges, Mapping) else None
        if isinstance(merge, Mapping):
            merge_out[key] = {
                name: merge[name] if _is_int(merge.get(name)) else None for name in _MERGE_FIELDS
            }
        else:
            merge_out[key] = None
        state = after.get(key) if isinstance(after, Mapping) else None
        if isinstance(state, Mapping) and _is_int(state.get("row_count")):
            after_out[key] = {
                "row_count": state["row_count"],
                "checksum": _safe_text(state.get("checksum")),
            }
        else:
            after_out[key] = None
    return {
        "leg": leg,
        "outcome": outcome,
        "snapshot_saved_at_ms": snapshot_saved_at_ms,
        "run_id": run_id,
        "started_ts": started,
        "ended_ts": ended,
        "tables_present_at_start": {
            key: present.get(key) is True if isinstance(present, Mapping) else False
            for key, _ in TABLES
        },
        "merges": merge_out,
        "after": after_out,
    }


# ----------------------------------------------------------------------------- verdict
def _parse_leg(leg: str, text: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """A structurally valid leg record, or (None, kind) with kind missing/unreadable/malformed."""
    obj, kind = _load(text)
    if obj is None:
        return None, kind
    ts_ok = all(
        obj.get(name) is None
        or (isinstance(obj.get(name), str) and re.fullmatch(UTC_PATTERN, obj[name]))
        for name in ("started_ts", "ended_ts")
    )
    valid = (
        obj.get("leg") == leg
        and obj.get("outcome") in ("passed", "failed")
        and _is_int(obj.get("saved_at_ms"))
        and _is_int(obj.get("snapshot_saved_at_ms"))
        and (obj.get("run_id") is None or _is_int(obj.get("run_id")))
        and ts_ok
        and all(isinstance(obj.get(name), dict) for name in ("tables_present_at_start", "merges"))
        and isinstance(obj.get("after"), dict)
    )
    if valid and obj["outcome"] == "passed":
        valid = (
            _is_int(obj.get("run_id"))
            and obj.get("started_ts") is not None
            and obj.get("ended_ts") is not None
        )
    if not valid:
        return None, "malformed"
    return obj, None


def _leg_next(leg: str, kind: str) -> str:
    if kind == "out of order":
        return f"next: start again with {SNAPSHOT_TEST} (runbook section 8)"
    if leg == "rerun":
        return f"next: run {RERUN_TEST} while the three tables exist (runbook section 8)"
    return f"next: the user runs {RESET_COMMAND}, then {REBUILD_TEST}"


def _inconsistencies(leg: str, record: dict[str, Any], snapshot: Snapshot) -> list[str]:
    found: list[str] = []
    expected = expected_merges(leg, snapshot)
    want_present = leg == "rerun"
    for key, _ in TABLES:
        if _canon(record["merges"].get(key)) != _canon(expected[key]):
            found.append(f"{key} merge differs from the expected metrics")
        state = record["after"].get(key)
        want = snapshot.tables[key]
        if not isinstance(state, dict):
            found.append(f"{key} has no row count and checksum")
            continue
        if _canon(state.get("row_count")) != _canon(want["row_count"]):
            found.append(f"{key} row_count differs from the snapshot")
        if _canon(state.get("checksum")) != _canon(want["checksum"]):
            found.append(f"{key} checksum differs from the snapshot")
        if record["tables_present_at_start"].get(key) is not want_present:
            found.append(f"{key} existence at the start does not fit the {leg} leg")
    return found


def _judge_leg(
    leg: str, text: str | None, snapshot: Snapshot | None
) -> tuple[dict[str, Any] | None, Problem | None]:
    """The valid record (or None) and the single problem of one leg (G-49)."""
    subject = f"{leg} leg"
    file = _file(LEG_NAMES[leg])
    record, kind = _parse_leg(leg, text)
    if record is None:
        what = {
            "missing": "is missing",
            "unreadable": "is not a JSON object",
            "malformed": "lacks a required field or holds a wrong type",
        }[kind or "malformed"]
        return None, Problem(subject, kind or "malformed", f"{file} {what}; {_leg_next(leg, '')}")
    if record["outcome"] != "passed":
        return record, Problem(
            subject, "failed", f"{file} has outcome failed; {_leg_next(leg, '')}"
        )
    if snapshot is None:
        return record, None
    if (
        record["snapshot_saved_at_ms"] != snapshot.saved_at_ms
        or record["saved_at_ms"] <= snapshot.saved_at_ms
    ):
        detail = f"{file} is not from the current snapshot; {_leg_next(leg, '')}"
        return record, Problem(subject, "stale", detail)
    found = _inconsistencies(leg, record, snapshot)
    if found:
        detail = f"{file} disagrees with the snapshot: {'; '.join(found)}; {_leg_next(leg, '')}"
        return record, Problem(subject, "inconsistent", detail)
    return record, None


def evaluate(
    snapshot_text: str | None, rerun_text: str | None, rebuild_text: str | None
) -> Verdict:
    """The pure verdict rule (FR-88, FR-89). Never raises (G-51)."""
    try:
        return _evaluate(snapshot_text, rerun_text, rebuild_text)
    except Exception as exc:
        problem = Problem(
            "verdict rule",
            "internal error",
            f"{type(exc).__name__}; next: report this as a defect of tests/support/ac66_rules.py",
        )
        return _verdict(None, None, None, [problem])


def _verdict(
    snapshot: Snapshot | None,
    rerun: dict[str, Any] | None,
    rebuild: dict[str, Any] | None,
    problems: list[Problem],
) -> Verdict:
    record = {
        "verdict": "fail" if problems else "pass",
        "problems": [problem.text() for problem in problems],
        "snapshot_saved_at_ms": snapshot.saved_at_ms if snapshot else None,
        "rerun_saved_at_ms": rerun["saved_at_ms"] if rerun else None,
        "rebuild_saved_at_ms": rebuild["saved_at_ms"] if rebuild else None,
    }
    return Verdict(record=record, problems=tuple(problems))


def _evaluate(
    snapshot_text: str | None, rerun_text: str | None, rebuild_text: str | None
) -> Verdict:
    snapshot, snapshot_problem = parse_snapshot(snapshot_text)
    problems: list[Problem] = [snapshot_problem] if snapshot_problem else []
    rerun, rerun_problem = _judge_leg("rerun", rerun_text, snapshot)
    rebuild, rebuild_problem = _judge_leg("rebuild", rebuild_text, snapshot)
    problems.extend(p for p in (rerun_problem, rebuild_problem) if p)
    if rerun_problem is None and rebuild_problem is None and rerun and rebuild:
        if rerun["saved_at_ms"] >= rebuild["saved_at_ms"]:
            detail = (
                f"{_file(LEG_NAMES['rerun'])} was saved at or after "
                f"{_file(LEG_NAMES['rebuild'])}; {_leg_next('rerun', 'out of order')}"
            )
            problems.append(Problem("rerun leg", "out of order", detail))
    return _verdict(snapshot, rerun, rebuild, problems)


def verdict_message(verdict: Verdict) -> str:
    lines = [f"AC-66 verdict {verdict.record['verdict']} (record {_file(VERDICT_NAME)})"]
    lines.extend(f"  - {text}" for text in verdict.record["problems"])
    return "\n".join(lines)


# ----------------------------------------------------------------------------- leg procedure
RUN_JOB_NAME = "smart_meter_peak_model"  # the only job whose runs a leg counts (D-102)
_UNREAD = "not a list of integer run ids"


@dataclass(frozen=True)
class RunCount:
    """Two run-list reads compared by run id only (G-55)."""

    unreadable: str  # "", "first read", "second read" or "comparison rule"
    new: tuple[int, ...]  # in the second read and not in the first, ascending
    newest_before: int | None  # first entry of the first read (newest first, A-55)
    newest_after: int | None  # first entry of the second read
    own: bool  # exactly one new run, equal to the leg's run id


def run_ids(value: Any) -> tuple[int, ...] | None:
    """A read as int run ids, or None unless it is a list of int (not bool) items (G-54)."""
    if not isinstance(value, list) or not all(_is_int(item) for item in value):
        return None
    return tuple(value)


def count_runs(before: Any, after: Any, leg_run_id: Any = None) -> RunCount:
    """The pure comparison rule (FR-100, NFR-50); never raises."""
    try:
        return _count_runs(before, after, _as_run_id(leg_run_id))
    except Exception:  # totality, as AC66_BOTH_LEGS G-51
        return RunCount("comparison rule", (), None, None, False)


def _count_runs(before: Any, after: Any, leg_run_id: int | None) -> RunCount:
    first = run_ids(before)
    if first is None:
        return RunCount("first read", (), None, None, False)
    newest_before = first[0] if first else None
    second = run_ids(after)
    if second is None:
        return RunCount("second read", (), newest_before, None, False)
    new = tuple(sorted(set(second) - set(first)))
    own = leg_run_id is not None and new == (leg_run_id,)
    return RunCount("", new, newest_before, second[0] if second else None, own)


def _as_run_id(raw: Any) -> int | None:
    if _is_int(raw):
        return raw
    if isinstance(raw, str) and raw.isascii() and raw.isdigit():
        return int(raw)
    return None


def _usable(value: Any) -> bool:
    """G-54 for the first-read gate: a read whose check raises an Exception is unusable.

    A list subclass whose ``__iter__`` raises would otherwise escape the gate with its own text
    (AC66_FIRST_READ_GATE, AC66_ZERO_NEW_RUNS I-07). A BaseException still propagates.
    """
    try:
        return run_ids(value) is not None
    except Exception:
        return False


def _read(runs: Callable[[], Any]) -> tuple[Any, Exception | None]:
    """One run-list read; an exception is kept for its class name and as the cause (G-57)."""
    try:
        return runs(), None
    except Exception as exc:  # a BaseException such as pytest.fail propagates
        return None, exc


def _id_text(value: int | None) -> str:
    return "none" if value is None else str(value)


def _ids_text(ids: tuple[int, ...]) -> str:
    return ", ".join(str(run_id) for run_id in ids) or "none"


def _count_text(count: int) -> str:
    return f"{count} new run{'' if count == 1 else 's'} of {RUN_JOB_NAME}"


def _why(count: RunCount, error: Exception | None) -> str:
    """Class name only: a reader message can hold a host name or a token (G-57)."""
    if error is not None:
        return type(error).__name__
    return "internal error" if count.unreadable == "comparison rule" else _UNREAD


def _first_read_message(leg: str, error: Exception | None) -> str:
    why = type(error).__name__ if error is not None else _UNREAD
    return (
        f"AC-66 {leg} leg: the run list of {RUN_JOB_NAME} could not be read "
        f"(first read: {why}); no table was read, no job run was started and no "
        "evidence file was changed; next: check the CLI profile, then run the leg again"
    )


def _refusal_message(leg: str, refusal: str, count: RunCount, error: Exception | None) -> str:
    reasons = refusal.removeprefix(f"AC-66 {leg} leg refused before any job run: ")
    before = _id_text(count.newest_before)
    if count.unreadable:
        return (
            f"AC-66 {leg} leg refused, but the count of new runs of {RUN_JOB_NAME} "
            f"could not be confirmed ({count.unreadable}: {_why(count, error)}; "
            f"newest run before: {before}); precondition: {reasons}"
        )
    reads = f"newest run before: {before}, after: {_id_text(count.newest_after)}"
    if not count.new:
        return f"{refusal}; {_count_text(0)} ({reads})"
    return (
        f"AC-66 {leg} leg found {_count_text(len(count.new))} while refusing "
        f"(new run ids: {_ids_text(count.new)}; {reads}); find what started them "
        f"before the next attempt; precondition: {reasons}"
    )


def _count_problem(count: RunCount, leg_run_id: Any, error: Exception | None) -> str:
    own = _id_text(_as_run_id(leg_run_id))
    if count.unreadable:
        return (
            f"the count of new runs of {RUN_JOB_NAME} could not be confirmed "
            f"({count.unreadable}: {_why(count, error)}), the leg's run {own}"
        )
    return (
        f"{_count_text(len(count.new))} (new run ids: {_ids_text(count.new)}), "
        f"expected exactly the leg's run {own}"
    )


def _pass_line(leg: str, count: RunCount) -> str:
    return (
        f"AC-66 {leg} leg passed: {_count_text(1)}, run {count.new[0]} "
        f"(newest run before: {_id_text(count.newest_before)})"
    )


def run_leg(
    leg: str,
    *,
    store: EvidenceStore,
    exists: Callable[[], Mapping[str, Any]],
    run_tasks: Callable[[], LegRun],
    state: Callable[[], Mapping[str, Any]],
    runs: Callable[[], Any],
    preflight: Callable[[], None] = lambda: None,
    report: Callable[[str], None] = print,
) -> dict[str, Any]:
    """One leg: refuse in the wrong state, run once, check, save the record (G-46, G-47).

    ``runs`` returns the run ids of smart_meter_peak_model and has no default, so no caller
    can skip the run count (AC66_ZERO_NEW_RUNS DA-49, order G-56).
    """
    if leg not in LEG_NAMES:
        raise AssertionError(precondition(leg, snapshot_ok=False, present={}).message)
    name = LEG_NAMES[leg]
    before, error = _read(runs)  # first read, before any other side effect
    if not _usable(before):
        raise AssertionError(_first_read_message(leg, error)) from error
    snapshot, _ = parse_snapshot(store.read_text(SNAPSHOT_NAME))
    present = dict(exists())
    decision = precondition(leg, snapshot_ok=snapshot is not None, present=present)
    if not decision.allowed or snapshot is None:
        listed, error = _read(runs)  # second read, after the refusal decision
        count = count_runs(before, listed)
        raise AssertionError(_refusal_message(leg, decision.message, count, error)) from error
    preflight()
    store.remove(name)  # no exit path can keep an old record from here on (OD-43)
    run: LegRun | None = None
    merges: dict[str, Any] | None = None
    after: Mapping[str, Any] | None = None
    try:
        run = run_tasks()
        listed, error = _read(runs)  # second read, right after the job run ended (DA-53)
        count = count_runs(before, listed, run.run_id)
        merges = merges_from_outputs(run.outputs)
        after = state()
        problems = [] if count.own else [_count_problem(count, run.run_id, error)]
        problems += check_leg(leg, snapshot, merges, after)
        if problems:
            raise AssertionError(
                f"AC-66 {leg} leg failed: {'; '.join(problems)}; "
                f"record outcome failed in {_file(name)}"
            ) from error
        record = leg_record(leg, "passed", snapshot.saved_at_ms, run, present, merges, after)
        store.save(name, record)
        report(_pass_line(leg, count))
        return record
    except BaseException:
        try:
            failed = leg_record(leg, "failed", snapshot.saved_at_ms, run, present, merges, after)
            store.save(name, failed)
        except Exception as exc:
            report(f"AC-66 {leg} leg: the failed record was not saved ({type(exc).__name__})")
        raise
