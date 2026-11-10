"""AC-154 to AC-158: the AC-66 verdict, precondition and leg procedure, proved on fixtures in CI.

AC66_ZERO_NEW_RUNS adds AC-165 to AC-170 (the run count, its order of side effects and the live
reader on a fake client); the AC-154 to AC-158 tests above are those of AC66_BOTH_LEGS.

The rules live in ``tests/support/ac66_rules.py`` (no SDK, no I/O, no clock). The leg procedure is
run with fakes for the runner, the table reads and the preflight, and with the real ``Evidence``
class of ``tests/integration/conftest.py`` on a temporary folder (DA-44), loaded by path under a
private name so the live conftest is not collected a second time. Fake secrets are built by
concatenation so the hygiene scans of tracked files stay clean.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import itertools
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from support import ac66_rules as rules

ROOT = Path(__file__).resolve().parents[1]
CONFTEST = ROOT / "tests" / "integration" / "conftest.py"
RULES_FILE = ROOT / "tests" / "support" / "ac66_rules.py"
SECRETS = ("htt" + "ps://host.example", "da" + "pi0123456789", "Bea" + "rer abcdef")
KEYS = [key for key, _ in rules.TABLES]
COUNTS = {"silver_weather": 21165, "features": 36480, "labels": 36480}
TASKS = rules.MERGE_TASKS


def _load_conftest() -> Any:
    spec = importlib.util.spec_from_file_location("_integration_conftest_under_test", CONFTEST)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves string annotations through it
    spec.loader.exec_module(module)
    return module


conftest = _load_conftest()


# ----------------------------------------------------------------------------- fixtures
def snapshot_dict(checksum_suffix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"saved_at_ms": 1000}
    for index, key in enumerate(KEYS):
        out[key] = {"row_count": COUNTS[key], "checksum": f"sum-{index}{checksum_suffix}"}
    return out


def leg_dict(leg: str, saved_at_ms: int, checksum_suffix: str = "") -> dict[str, Any]:
    snap = snapshot_dict(checksum_suffix)
    rebuild = leg == "rebuild"
    return {
        "saved_at_ms": saved_at_ms,
        "leg": leg,
        "outcome": "passed",
        "snapshot_saved_at_ms": 1000,
        "run_id": 11 if rebuild else 10,
        "started_ts": "2026-11-09T10:00:00Z",
        "ended_ts": "2026-11-09T10:04:00Z",
        "tables_present_at_start": {key: not rebuild for key in KEYS},
        "merges": {
            key: {"inserted": COUNTS[key] if rebuild else 0, "updated": 0, "deleted": 0}
            for key in KEYS
        },
        "after": {key: dict(snap[key]) for key in KEYS},
    }


def texts(**changes: Any) -> tuple[str | None, str | None, str | None]:
    """Snapshot, rerun and rebuild texts; a change is a dict (replaces), None, or a string."""
    parts = {
        "snapshot": snapshot_dict(),
        "rerun": leg_dict("rerun", 2000),
        "rebuild": leg_dict("rebuild", 3000),
    }
    parts.update(changes)
    return tuple(  # type: ignore[return-value]
        value if isinstance(value, str) or value is None else json.dumps(value)
        for value in (parts["snapshot"], parts["rerun"], parts["rebuild"])
    )


def pairs(verdict: rules.Verdict) -> list[tuple[str, str]]:
    return [(problem.subject, problem.kind) for problem in verdict.problems]


# ----------------------------------------------------------------------------- AC-154
def test_ac154_both_legs_on_the_current_snapshot_pass_deterministically() -> None:
    first = rules.evaluate(*texts())
    second = rules.evaluate(*texts())
    assert first.passed
    assert first.problems == ()
    assert set(first.record) == set(rules.VERDICT_FIELDS)
    assert first.record["verdict"] == "pass"
    assert first.record["problems"] == []
    assert first.record["snapshot_saved_at_ms"] == 1000
    assert first.record["rerun_saved_at_ms"] == 2000
    assert first.record["rebuild_saved_at_ms"] == 3000
    assert json.dumps(first.record, sort_keys=True) == json.dumps(second.record, sort_keys=True)
    assert rules.verdict_message(first) == rules.verdict_message(second)


def test_ac154_secret_like_strings_never_reach_the_record_or_the_message() -> None:
    snapshot = snapshot_dict(SECRETS[1])
    rerun = leg_dict("rerun", 2000, SECRETS[1])
    rerun["note"] = " ".join(SECRETS)  # an unknown field is ignored
    rebuild = leg_dict("rebuild", 3000, SECRETS[1])
    good = rules.evaluate(*texts(snapshot=snapshot, rerun=rerun, rebuild=rebuild))
    assert good.passed
    broken = leg_dict("rebuild", 3000, SECRETS[0])  # checksum differs and holds a secret-like text
    broken["leg"] = SECRETS[2]
    bad = rules.evaluate(*texts(snapshot=snapshot, rerun=rerun, rebuild=broken))
    for verdict in (good, bad):
        dumped = json.dumps(verdict.record) + rules.verdict_message(verdict)
        assert not any(secret in dumped for secret in SECRETS)
        for marker in ("https://", "dapi", "Bearer"):
            assert marker not in dumped
    inconsistent = leg_dict("rebuild", 3000, SECRETS[0])
    verdict = rules.evaluate(*texts(snapshot=snapshot_dict(), rebuild=inconsistent))
    assert "checksum differs" in rules.verdict_message(verdict)
    assert SECRETS[0] not in rules.verdict_message(verdict)


def test_ac154_rules_import_no_sdk_and_read_no_clock() -> None:
    tree = ast.parse(RULES_FILE.read_text(encoding="utf-8"))
    forbidden = {"databricks", "time", "os", "pathlib", "subprocess", "datetime"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & forbidden
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in forbidden, node.module
            if root == "smart_meter_peak_prediction":
                assert node.module == "smart_meter_peak_prediction.pipeline_guard"
    banned_calls = {"now", "utcnow", "time", "open", "sleep"}
    run_leg = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_leg")
    inside = {id(n) for n in ast.walk(run_leg)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        assert name not in banned_calls, name
        if name in {"read_text", "save", "remove"}:
            assert id(node) in inside
            assert isinstance(func, ast.Attribute)
            assert isinstance(func.value, ast.Name)
            assert func.value.id == "store"


# ----------------------------------------------------------------------------- AC-155
@pytest.mark.parametrize(
    ("case", "changes", "expected"),
    [
        ("a", {"rebuild": None}, [("rebuild leg", "missing")]),
        ("b", {"rerun": None}, [("rerun leg", "missing")]),
        (
            "c",
            {"rerun": None, "rebuild": None},
            [("rerun leg", "missing"), ("rebuild leg", "missing")],
        ),
        ("d", {"snapshot": None}, [("snapshot", "missing")]),
    ],
)
def test_ac155_missing_evidence_names_each_missing_leg_or_the_snapshot(
    case: str, changes: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    verdict = rules.evaluate(*texts(**changes))
    assert not verdict.passed
    assert verdict.record["verdict"] == "fail"
    assert pairs(verdict) == expected
    rendered = [problem.text() for problem in verdict.problems]
    if case == "a":
        assert "ac66_rebuild_leg.json" in rendered[0]
        assert rules.REBUILD_TEST in rendered[0]
        assert "rerun" not in rendered[0]
        assert verdict.record["rebuild_saved_at_ms"] is None
    if case == "b":
        assert "ac66_rerun_leg.json" in rendered[0]
        assert rules.RERUN_TEST in rendered[0]
        assert "rebuild" not in rendered[0]
    if case == "c":
        assert "ac66_rerun_leg.json" in rendered[0]
        assert "ac66_rebuild_leg.json" in rendered[1]
    if case == "d":
        assert rules.SNAPSHOT_TEST in rendered[0]
        assert verdict.record["snapshot_saved_at_ms"] is None


# ----------------------------------------------------------------------------- AC-156
def _edit(which: str, saved: int = 0, **fields: Any) -> dict[str, Any]:
    record = leg_dict(which, 2000 if which == "rerun" else 3000)
    if saved:
        record["saved_at_ms"] = saved
    record.update(fields)
    return record


def _case_g() -> dict[str, Any]:
    record = leg_dict("rebuild", 3000)
    record["after"]["labels"]["checksum"] = "other"
    return record


def _case_e() -> dict[str, Any]:
    record = leg_dict("rerun", 2000)
    record["merges"]["features"]["updated"] = 1
    return record


def _case_f() -> dict[str, Any]:
    record = leg_dict("rebuild", 3000)
    record["merges"]["silver_weather"]["inserted"] = 21164
    return record


def _case_i() -> dict[str, Any]:
    record = leg_dict("rebuild", 3000)
    del record["saved_at_ms"]
    return record


CASES = [
    ("a", {"rerun": _edit("rerun", snapshot_saved_at_ms=900)}, [("rerun leg", "stale")], ""),
    ("b", {"rebuild": _edit("rebuild", saved=900)}, [("rebuild leg", "stale")], ""),
    ("c", {"rerun": _edit("rerun", saved=4000)}, [("rerun leg", "out of order")], ""),
    ("d", {"rebuild": _edit("rebuild", outcome="failed")}, [("rebuild leg", "failed")], ""),
    ("e", {"rerun": _case_e()}, [("rerun leg", "inconsistent")], "features"),
    ("f", {"rebuild": _case_f()}, [("rebuild leg", "inconsistent")], "silver_weather"),
    ("g", {"rebuild": _case_g()}, [("rebuild leg", "inconsistent")], "checksum differs"),
    ("h", {"rerun": "{not json"}, [("rerun leg", "unreadable")], "ac66_rerun_leg.json"),
    ("i", {"rebuild": _case_i()}, [("rebuild leg", "malformed")], "ac66_rebuild_leg.json"),
    ("j", {"rerun": _edit("rerun", leg="rebuild")}, [("rerun leg", "malformed")], "ac66_rerun"),
]


@pytest.mark.parametrize(("case", "changes", "expected", "needle"), CASES)
def test_ac156_stale_out_of_order_failed_inconsistent_or_malformed_legs_fail(
    case: str, changes: dict[str, Any], expected: list[tuple[str, str]], needle: str
) -> None:
    verdict = rules.evaluate(*texts(**changes))
    assert not verdict.passed
    assert pairs(verdict) == expected, case
    text = verdict.problems[0].text()
    leg_file = "ac66_rerun_leg" if expected[0][0] == "rerun leg" else "ac66_rebuild_leg"
    assert leg_file in text
    assert needle in text
    assert all(kind != "internal error" for _, kind in pairs(verdict))
    if case == "i":
        assert verdict.record["rebuild_saved_at_ms"] is None
    if expected[0][0] == "rebuild leg":
        assert "rerun" not in text


def _odd_texts() -> list[str | None]:
    odd: list[str | None] = ["", "null", "[]", "1", "[" * 10000, "NaN", '{"saved_at_ms": NaN}']
    odd.append(json.dumps({**leg_dict("rerun", 2000), "leg": "sideways"}))
    odd.append(json.dumps({**leg_dict("rerun", 2000), "outcome": "maybe"}))
    odd.append(json.dumps({**leg_dict("rerun", 2000), "saved_at_ms": 10**400}))
    return odd


def _mutations() -> list[tuple[str, int, str]]:
    """(slot, index, text): each field of each record replaced by a wrong-typed value."""
    out: list[tuple[str, int, str]] = []
    wrong = [True, "x", [], None, float("nan"), 1.5]
    base = {"snapshot": snapshot_dict(), "rerun": leg_dict("rerun", 2000)}
    base["rebuild"] = leg_dict("rebuild", 3000)
    for slot, record in base.items():
        for field in record:
            for index, value in enumerate(wrong):
                changed = {**record, field: value}
                out.append((slot, index, json.dumps(changed)))
        if slot == "snapshot":
            for key in KEYS:
                for field in ("row_count", "checksum"):
                    for value in (True, "x", None, []):
                        changed = {**record, key: {**record[key], field: value}}
                        out.append((slot, 9, json.dumps(changed)))
            for key in KEYS:
                changed = {k: v for k, v in record.items() if k != key}
                out.append((slot, 8, json.dumps(changed)))
    return out


@pytest.mark.parametrize("slot", ["snapshot", "rerun", "rebuild"])
def test_ac156_odd_inputs_never_raise(slot: str) -> None:
    for text in _odd_texts():
        verdict = rules.evaluate(*texts(**{slot: text}))
        assert verdict.record["verdict"] == "fail"
        assert all(kind != "internal error" for _, kind in pairs(verdict))
    for mut_slot, _, text in _mutations():
        if mut_slot != slot:
            continue
        verdict = rules.evaluate(*texts(**{slot: text}))
        assert all(kind != "internal error" for _, kind in pairs(verdict)), text[:80]
        assert verdict.record["verdict"] == "fail", text[:80]
    for odd in ("", "null", "[]", "1", "[" * 10000):  # all three slots wrong at once
        verdict = rules.evaluate(odd, odd, odd)
        assert verdict.record["verdict"] == "fail"
        assert len(verdict.problems) == 3
    assert rules.precondition("sideways", snapshot_ok=True, present={}).allowed is False
    assert rules.precondition("rerun", snapshot_ok=True, present=None).allowed is False  # type: ignore[arg-type]
    for bad in ({"silver_weather": 1, "features": True, "labels": True}, {"labels": "yes"}):
        assert rules.precondition("rerun", snapshot_ok=True, present=bad).allowed is False


# ----------------------------------------------------------------------------- AC-157
STATES = list(itertools.product([True, False], repeat=3))


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
@pytest.mark.parametrize("snapshot_ok", [True, False])
@pytest.mark.parametrize("state", STATES)
def test_ac157_precondition_over_all_table_states(
    leg: str, snapshot_ok: bool, state: tuple[bool, bool, bool]
) -> None:
    present = dict(zip(KEYS, state, strict=True))
    result = rules.precondition(leg, snapshot_ok=snapshot_ok, present=present)
    wanted = all(state) if leg == "rerun" else not any(state)
    assert result.allowed is (wanted and snapshot_ok)
    if result.allowed:
        assert result.message == ""
        return
    message = result.message
    assert message.startswith(f"AC-66 {leg} leg refused before any job run:")
    for (_key, shown), is_there in zip(rules.TABLES, state, strict=True):
        in_wrong_state = (not is_there) if leg == "rerun" else is_there
        assert (shown in message) is in_wrong_state, (shown, message)
    if not snapshot_ok:
        assert "ac66_before_rebuild.json" in message
        assert rules.SNAPSHOT_TEST in message
    if not wanted:
        if 0 < sum(state) < 3:
            assert "smart_meter_peak_model" in message
        elif leg == "rerun":
            assert rules.REBUILD_TEST in message
        else:
            assert rules.RERUN_TEST in message
            assert "reset_peak_model_outputs.py --confirm" in message


# ----------------------------------------------------------------------------- AC-158
class Fakes:
    """Counters for the injected side effects of ``run_leg``."""

    def __init__(self, leg: str, present: dict[str, bool], merges: dict[str, Any] | None = None):
        self.leg = leg
        self.present = present
        self.calls: list[str] = []
        self.merges = merges
        self.after: dict[str, Any] = {k: dict(v) for k, v in _snapshot_tables().items()}
        self.raises: BaseException | None = None
        self.listed: list[Any] = [30, 20, 10]  # the fake run list, newest first
        self.started: list[int] = [42]  # ids the fake runner adds at the head of the list
        self.run_id = 42
        self.replies: dict[int, Any] = {}  # read number -> value to return or Exception to raise
        self.on_exists: Callable[[], None] | None = None
        self.reads = 0

    def runs(self) -> Any:
        self.calls.append("runs")
        self.reads += 1
        reply = self.replies.get(self.reads)
        if isinstance(reply, BaseException):
            raise reply
        if self.reads in self.replies:
            return reply
        return list(self.listed)

    def exists(self) -> dict[str, bool]:
        self.calls.append("exists")
        if self.on_exists is not None:
            self.on_exists()
        return dict(self.present)

    def preflight(self) -> None:
        self.calls.append("preflight")

    def run_tasks(self) -> rules.LegRun:
        self.calls.append("run")
        if self.raises is not None:
            raise self.raises
        for run_id in self.started:
            self.listed.insert(0, run_id)
        merges = self.merges or {
            key: {
                "inserted": COUNTS[key] if self.leg == "rebuild" else 0,
                "updated": 0,
                "deleted": 0,
            }
            for key in KEYS
        }
        outputs = {TASKS[key]: {"merge": merges[key]} for key in KEYS}
        return rules.LegRun(self.run_id, 1_700_000_000_000, 1_700_000_226_000, outputs)

    def state(self) -> dict[str, Any]:
        self.calls.append("state")
        return self.after

    def call(self, store: Any, report: Any = print) -> dict[str, Any]:
        return rules.run_leg(
            self.leg,
            store=store,
            exists=self.exists,
            run_tasks=self.run_tasks,
            state=self.state,
            runs=self.runs,
            preflight=self.preflight,
            report=report,
        )


def _snapshot_tables() -> dict[str, dict[str, Any]]:
    snap = snapshot_dict()
    return {key: dict(snap[key]) for key in KEYS}


def _store(tmp_path: Path, leg: str, *, with_snapshot: bool = True) -> Any:
    store = conftest.Evidence(folder=tmp_path)
    if with_snapshot:
        data = snapshot_dict()
        del data["saved_at_ms"]
        store.save(rules.SNAPSHOT_NAME, data)
    old = leg_dict(leg, 1)
    store.save(rules.LEG_NAMES[leg], {k: v for k, v in old.items() if k != "saved_at_ms"})
    return store


def _present(leg: str) -> dict[str, bool]:
    return {key: leg == "rerun" for key in KEYS}


def _files(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac158_leg_passes_and_writes_the_full_record(tmp_path: Path, leg: str) -> None:
    store = _store(tmp_path, leg)
    fakes = Fakes(leg, _present(leg))
    record = fakes.call(store)
    saved = json.loads((tmp_path / f"{rules.LEG_NAMES[leg]}.json").read_text(encoding="utf-8"))
    assert set(saved) == set(rules.RECORD_FIELDS) | {"saved_at_ms"}
    assert saved["outcome"] == "passed"
    assert saved["leg"] == leg
    assert (
        saved["snapshot_saved_at_ms"]
        == json.loads((tmp_path / "ac66_before_rebuild.json").read_text(encoding="utf-8"))[
            "saved_at_ms"
        ]
    )
    assert saved["run_id"] == 42
    for name in ("started_ts", "ended_ts"):
        assert re.fullmatch(rules.UTC_PATTERN, saved[name]), saved[name]
    assert saved["tables_present_at_start"] == _present(leg)
    assert record["outcome"] == "passed"
    assert fakes.calls.count("run") == 1
    assert fakes.calls.index("preflight") < fakes.calls.index("run")
    assert saved["started_ts"] == "2023-11-14T22:13:20Z"
    assert saved["ended_ts"] == "2023-11-14T22:17:06Z"
    assert saved["after"] == _snapshot_tables()
    assert saved["merges"]["features"]["inserted"] == (
        COUNTS["features"] if leg == "rebuild" else 0
    )


def _bad_merges(leg: str) -> dict[str, Any]:
    merges = {
        key: {"inserted": COUNTS[key] if leg == "rebuild" else 0, "updated": 0, "deleted": 0}
        for key in KEYS
    }
    if leg == "rerun":
        merges["labels"]["inserted"] = 1
    else:
        merges["labels"]["inserted"] = 0
    return merges


class Stop(BaseException):
    """Like ``pytest.fail``: a BaseException that is not an Exception."""


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
@pytest.mark.parametrize("failure", ["merges", "assertion", "baseexception"])
def test_ac158_leg_failure_leaves_no_passed_record(tmp_path: Path, leg: str, failure: str) -> None:
    store = _store(tmp_path, leg)
    fakes = Fakes(leg, _present(leg), merges=_bad_merges(leg) if failure == "merges" else None)
    expected: type[BaseException] = AssertionError
    if failure == "assertion":
        fakes.raises = AssertionError("run ended FAILED")
    if failure == "baseexception":
        fakes.raises = Stop("stop")
        expected = Stop
    with pytest.raises(expected):
        fakes.call(store)
    path = tmp_path / f"{rules.LEG_NAMES[leg]}.json"
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["outcome"] == "failed"
    if failure == "merges":
        assert saved["run_id"] == 42
        assert saved["merges"]["labels"]["inserted"] == _bad_merges(leg)["labels"]["inserted"]
    else:
        assert saved["run_id"] is None
        assert saved["merges"] == {key: None for key in KEYS}
        assert saved["after"] == {key: None for key in KEYS}
    for candidate in tmp_path.glob("*.json"):
        data = json.loads(candidate.read_text(encoding="utf-8"))
        assert not (data.get("leg") == leg and data.get("outcome") == "passed")


REFUSALS = [
    ("rerun", {key: False for key in KEYS}, True),
    ("rebuild", {key: True for key in KEYS}, True),
    ("rerun", {"silver_weather": True, "features": False, "labels": True}, True),
    ("rebuild", {"silver_weather": False, "features": True, "labels": False}, True),
    ("rerun", {key: True for key in KEYS}, False),
    ("rebuild", {key: False for key in KEYS}, False),
]


@pytest.mark.parametrize(("leg", "present", "with_snapshot"), REFUSALS)
def test_ac158_wrong_state_refuses_before_the_runner(
    tmp_path: Path, leg: str, present: dict[str, bool], with_snapshot: bool
) -> None:
    store = _store(tmp_path, leg, with_snapshot=with_snapshot)
    before = _files(tmp_path)
    fakes = Fakes(leg, present)
    with pytest.raises(AssertionError) as caught:
        fakes.call(store)
    assert str(caught.value).startswith(f"AC-66 {leg} leg refused before any job run")
    assert fakes.calls.count("run") == 0
    assert "state" not in fakes.calls
    assert "preflight" not in fakes.calls
    assert _files(tmp_path) == before


def test_ac158_unknown_leg_refuses(tmp_path: Path) -> None:
    fakes = Fakes("rerun", _present("rerun"))
    with pytest.raises(AssertionError, match="refused before any job run"):
        rules.run_leg(
            "sideways",
            store=_store(tmp_path, "rerun"),
            exists=fakes.exists,
            run_tasks=fakes.run_tasks,
            state=fakes.state,
            runs=fakes.runs,
        )
    assert fakes.calls == []


class SaveFails:
    """The real store, except that every save raises."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def read_text(self, name: str) -> str | None:
        return self.inner.read_text(name)

    def remove(self, name: str) -> None:
        self.inner.remove(name)

    def save(self, name: str, data: dict[str, Any]) -> None:
        raise OSError("disk says " + SECRETS[1])


def test_ac158_unsaved_failed_record_does_not_mask_the_failure(tmp_path: Path) -> None:
    store = _store(tmp_path, "rerun")
    fakes = Fakes("rerun", _present("rerun"))
    fakes.raises = AssertionError("run ended FAILED")
    lines: list[str] = []
    with pytest.raises(AssertionError, match="run ended FAILED"):
        fakes.call(SaveFails(store), report=lines.append)
    assert len(lines) == 1
    assert "OSError" in lines[0]
    assert SECRETS[1] not in lines[0]
    assert not (tmp_path / "ac66_rerun_leg.json").exists()  # removed before the run


def test_ac158_real_evidence_class_keeps_its_shipped_defaults(tmp_path: Path) -> None:
    default = conftest.Evidence()
    assert default.folder == conftest.EVIDENCE_DIR
    store = conftest.Evidence(folder=tmp_path / "nested")
    assert store.read_text("nothing") is None
    store.remove("nothing")  # a missing file is fine
    store.save("x", {"a": 1})
    assert json.loads(store.read_text("x") or "")["a"] == 1
    assert store.load("x", "before")["a"] == 1
    (tmp_path / "nested" / "bad.json").write_bytes(b"\xff\xfe{")
    assert isinstance(store.read_text("bad"), str)
    store.remove("x")
    assert store.read_text("x") is None


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac158_after_state_mismatch_fails_and_never_stores_a_secret(
    tmp_path: Path, leg: str
) -> None:
    store = _store(tmp_path, leg)
    fakes = Fakes(leg, _present(leg))
    fakes.after["features"]["checksum"] = SECRETS[0]
    fakes.after["labels"]["row_count"] += 1
    with pytest.raises(AssertionError) as caught:
        fakes.call(store)
    message = str(caught.value)
    assert "features: checksum differs" in message
    assert "labels: row_count differs" in message
    assert SECRETS[0] not in message
    path = tmp_path / f"{rules.LEG_NAMES[leg]}.json"
    saved = path.read_text(encoding="utf-8")
    assert json.loads(saved)["outcome"] == "failed"
    assert SECRETS[0] not in saved
    assert json.loads(saved)["after"]["features"]["checksum"] is None


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac158_failing_preflight_keeps_the_old_record(tmp_path: Path, leg: str) -> None:
    store = _store(tmp_path, leg)
    before = _files(tmp_path)
    fakes = Fakes(leg, _present(leg))

    def busy() -> None:
        raise AssertionError("the shared pipeline is not idle")

    with pytest.raises(AssertionError, match="not idle"):
        rules.run_leg(
            leg,
            store=store,
            exists=fakes.exists,
            run_tasks=fakes.run_tasks,
            state=fakes.state,
            runs=fakes.runs,
            preflight=busy,
        )
    assert "run" not in fakes.calls
    assert _files(tmp_path) == before


def test_ac158_unreadable_snapshot_refuses(tmp_path: Path) -> None:
    store = _store(tmp_path, "rerun")
    (tmp_path / "ac66_before_rebuild.json").write_text("{broken", encoding="utf-8")
    before = _files(tmp_path)
    fakes = Fakes("rerun", _present("rerun"))
    with pytest.raises(AssertionError, match="refused before any job run"):
        fakes.call(store)
    assert "run" not in fakes.calls
    assert _files(tmp_path) == before


# ----------------------------------------------------------------------------- AC66_ZERO_NEW_RUNS
UTC_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\S*")
READER_ERROR = RuntimeError(" ".join(SECRETS) + " someone" + "@example.com")
JOB = "smart_meter_peak_model"


class Logged:
    """A store that appends its calls to a shared log, then delegates."""

    def __init__(self, inner: Any, log: list[str]) -> None:
        self.inner = inner
        self.log = log

    def read_text(self, name: str) -> str | None:
        self.log.append(f"read_text:{name}")
        return self.inner.read_text(name)

    def remove(self, name: str) -> None:
        self.log.append(f"remove:{name}")
        self.inner.remove(name)

    def save(self, name: str, data: dict[str, Any]) -> None:
        self.log.append(f"save:{name}")
        self.inner.save(name, data)


def _no_secret(text: str) -> None:
    for marker in ("https://", "dapi", "Bearer", "@"):
        assert marker not in text, marker
    assert not any(secret in text for secret in SECRETS)


def _utc_only(text: str) -> None:
    for match in UTC_TIME.findall(text):
        assert re.fullmatch(rules.UTC_PATTERN, match.strip("),.;")), match


def _logged(tmp_path: Path, leg: str, fakes: Fakes, **kwargs: Any) -> Logged:
    return Logged(_store(tmp_path, leg, **kwargs), fakes.calls)


REFUSAL_LOG = ["runs", "read_text:ac66_before_rebuild", "exists", "runs"]


# AC-165
PAIRS = [
    ("a", [3, 2, 1], [3, 2, 1], (), None, 3, 3),
    ("b", [3, 2, 1], [4, 3, 2, 1], (4,), None, 3, 4),
    ("c", [], [7], (7,), None, None, 7),
    ("d", [3, 2, 1], [5, 4, 3, 2], (4, 5), None, 3, 5),
]


@pytest.mark.parametrize("leg_id", [None, 4])
@pytest.mark.parametrize(("case", "first", "second", "new", "_unused", "nb", "na"), PAIRS)
def test_ac165_run_count_rule_over_pairs_of_reads(
    case: str, first: Any, second: Any, new: Any, _unused: Any, nb: Any, na: Any, leg_id: Any
) -> None:
    one = rules.count_runs(list(first), list(second), leg_id)
    two = rules.count_runs(list(first), list(second), leg_id)
    assert one.unreadable == ""
    assert one.new == new
    assert (one.newest_before, one.newest_after) == (nb, na)
    assert one.own is (case == "b" and leg_id == 4)
    dumped = json.dumps(dataclasses.asdict(one), sort_keys=True)
    assert dumped == json.dumps(dataclasses.asdict(two), sort_keys=True)


class _BadList(list):  # type: ignore[type-arg]
    def __iter__(self) -> Any:
        raise RuntimeError("no iteration")


@pytest.mark.parametrize("leg_id", [None, 4, "4"])
def test_ac165_run_count_rule_never_raises_on_odd_reads(leg_id: Any) -> None:
    cases: list[tuple[Any, Any, str]] = []
    for odd in (True, "4", None, 4.0, [4]):
        cases.append(([3, 2, 1], [odd, 3, 2, 1], "second read"))
    for whole in (None, (4, 3), "4,3"):
        cases.append(([3, 2, 1], whole, "second read"))
    for first in (None, (3, 2, 1), "3,2,1", {3: 1}, 3):
        cases.append((first, [4, 3, 2, 1], "first read"))
    cases.append((_BadList([3]), [3], "comparison rule"))
    for first, second, unreadable in cases:
        one = rules.count_runs(first, second, leg_id)
        two = rules.count_runs(first, second, leg_id)
        assert one.unreadable == unreadable, (first, second)
        assert one.new == ()
        assert one.own is False
        assert json.dumps(dataclasses.asdict(one), sort_keys=True) == json.dumps(
            dataclasses.asdict(two), sort_keys=True
        )
    assert rules.count_runs([1], [1, 2], object()).own is False  # an odd leg run id never raises


# AC-166
@pytest.mark.parametrize(("leg", "present", "with_snapshot"), REFUSALS)
def test_ac166_refusal_reads_the_run_list_twice_and_reports_0_new_runs(
    tmp_path: Path, leg: str, present: dict[str, bool], with_snapshot: bool
) -> None:
    messages = []
    for _ in range(2):
        fakes = Fakes(leg, present)
        store = _logged(tmp_path, leg, fakes, with_snapshot=with_snapshot)
        before = _files(tmp_path)
        with pytest.raises(AssertionError) as caught:
            fakes.call(store)
        assert fakes.calls == REFUSAL_LOG
        assert _files(tmp_path) == before
        messages.append(str(caught.value))
    assert messages[0] == messages[1]
    message = messages[0]
    assert message.startswith(f"AC-66 {leg} leg refused before any job run:")
    assert message.endswith(f"; 0 new runs of {JOB} (newest run before: 30, after: 30)")
    _no_secret(message)
    _utc_only(message)


# AC-167
@pytest.mark.parametrize(("leg", "present", "with_snapshot"), REFUSALS)
def test_ac167_a_run_started_during_a_refusal_fails_differently(
    tmp_path: Path, leg: str, present: dict[str, bool], with_snapshot: bool
) -> None:
    fakes = Fakes(leg, present)
    fakes.on_exists = lambda: fakes.listed.insert(0, 40)
    store = _logged(tmp_path, leg, fakes, with_snapshot=with_snapshot)
    before = _files(tmp_path)
    with pytest.raises(AssertionError) as caught:
        fakes.call(store)
    message = str(caught.value)
    assert fakes.calls == REFUSAL_LOG
    assert _files(tmp_path) == before
    assert message.startswith(f"AC-66 {leg} leg found 1 new run of {JOB} while refusing")
    assert "new run ids: 40" in message
    assert "after: 40" in message
    assert "refused before any job run" not in message
    _no_secret(message)
    _utc_only(message)


# AC-168
@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac168_pass_checks_exactly_its_own_run(tmp_path: Path, leg: str) -> None:
    name = rules.LEG_NAMES[leg]
    lines: list[str] = []
    # (a) the runner adds its own run only
    fakes = Fakes(leg, _present(leg))
    fakes.call(_logged(tmp_path, leg, fakes), report=lines.append)
    assert fakes.calls == [
        "runs",
        "read_text:ac66_before_rebuild",
        "exists",
        "preflight",
        f"remove:{name}",
        "run",
        "runs",
        "state",
        f"save:{name}",
    ]
    saved = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
    assert set(saved) == set(rules.RECORD_FIELDS) | {"saved_at_ms"}
    assert saved["outcome"] == "passed"
    assert saved["run_id"] == 42
    assert lines == [f"AC-66 {leg} leg passed: 1 new run of {JOB}, run 42 (newest run before: 30)"]
    for line in lines:
        _no_secret(line)
        _utc_only(line)
    # (b) a foreign run too, (c) no run at all
    for started, ids in (([42, 43], "2 new runs of " + JOB + " (new run ids: 42, 43)"), ([], None)):
        fakes = Fakes(leg, _present(leg))
        fakes.started = started
        lines = []
        with pytest.raises(AssertionError) as caught:
            fakes.call(_logged(tmp_path, leg, fakes), report=lines.append)
        message = str(caught.value)
        assert message.startswith(f"AC-66 {leg} leg failed:")
        if ids is None:
            assert f"0 new runs of {JOB} (new run ids: none)" in message
        else:
            assert ids in message
        assert "expected exactly the leg's run 42" in message
        assert "state" in fakes.calls
        saved = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
        assert saved["outcome"] == "failed"
        assert saved["run_id"] == 42
        for candidate in tmp_path.glob("*.json"):
            data = json.loads(candidate.read_text(encoding="utf-8"))
            assert not (data.get("leg") == leg and data.get("outcome") == "passed")
        assert lines == []
        _no_secret(message)
        _utc_only(message)


# AC-169
@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
@pytest.mark.parametrize("reply", [READER_ERROR, "x", None, [True]], ids=type)
def test_ac169_unreadable_run_list_never_reports_a_pass(
    tmp_path: Path, leg: str, reply: Any
) -> None:
    # (a) the first read is unusable: nothing else is called
    fakes = Fakes(leg, _present(leg))
    fakes.replies = {1: reply}
    store = _logged(tmp_path, leg, fakes)
    before = _files(tmp_path)
    with pytest.raises(AssertionError) as caught:
        fakes.call(store)
    message = str(caught.value)
    assert fakes.calls == ["runs"]
    assert _files(tmp_path) == before
    assert f"the run list of {JOB} could not be read" in message
    if isinstance(reply, Exception):
        assert "first read: RuntimeError" in message
        assert caught.value.__cause__ is reply
    else:
        assert "first read: not a list of integer run ids" in message
    _no_secret(message)
    # (c) the right state, the second read raises after the runner returned 42
    fakes = Fakes(leg, _present(leg))
    fakes.replies = {2: READER_ERROR}
    lines: list[str] = []
    with pytest.raises(AssertionError) as caught:
        fakes.call(_store(tmp_path, leg), report=lines.append)
    message = str(caught.value)
    assert (
        f"the count of new runs of {JOB} could not be confirmed (second read: RuntimeError), "
        "the leg's run 42"
    ) in message
    assert "0 new runs" not in message
    assert caught.value.__cause__ is READER_ERROR
    saved = json.loads((tmp_path / f"{rules.LEG_NAMES[leg]}.json").read_text(encoding="utf-8"))
    assert saved["outcome"] == "failed"
    assert saved["run_id"] == 42
    assert lines == []
    _no_secret(message)


@pytest.mark.parametrize(("leg", "present", "with_snapshot"), REFUSALS[:2])
def test_ac169_unreadable_second_read_never_reports_a_clean_refusal(
    tmp_path: Path, leg: str, present: dict[str, bool], with_snapshot: bool
) -> None:
    fakes = Fakes(leg, present)
    fakes.replies = {2: READER_ERROR}
    store = _logged(tmp_path, leg, fakes)
    before = _files(tmp_path)
    with pytest.raises(AssertionError) as caught:
        fakes.call(store)
    message = str(caught.value)
    assert "could not be confirmed (second read: RuntimeError; newest run before: 30)" in message
    assert "0 new runs" not in message
    assert "refused before any job run" not in message
    assert fakes.calls == REFUSAL_LOG
    assert _files(tmp_path) == before
    assert caught.value.__cause__ is READER_ERROR
    _no_secret(message)


# AC-170 (reader on a fake client)
def test_ac170_run_ids_reads_one_page_of_every_state_for_the_given_job() -> None:
    seen: list[dict[str, Any]] = []
    pulled: list[int] = []
    states = ("QUEUED", "PENDING", "RUNNING", "TERMINATED", "SKIPPED")

    def list_runs(**kwargs: Any) -> Any:
        seen.append(kwargs)
        for index, run_id in enumerate(range(130, 100, -1)):
            pulled.append(run_id)
            yield SimpleNamespace(run_id=run_id, state=states[index % len(states)])

    client = SimpleNamespace(jobs=SimpleNamespace(list_runs=list_runs))
    got = conftest.PeakRunner(client, 1, "p").run_ids(SimpleNamespace(job_id=7))
    assert seen == [{"job_id": 7, "limit": 25}]
    assert got == list(range(130, 105, -1))
    assert len(pulled) == 25


# Review additions (AC-165, AC-168, AC-169, DA-54, DA-55)
def test_ac165_one_new_run_that_is_not_the_legs_own_is_not_own() -> None:
    count = rules.count_runs([3, 2, 1], [4, 3, 2, 1], 5)
    assert count.new == (4,)
    assert count.own is False


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac168_one_foreign_run_instead_of_its_own_fails(tmp_path: Path, leg: str) -> None:
    fakes = Fakes(leg, _present(leg))
    fakes.started = [43]  # the runner reports run 42 but only a foreign 43 is listed
    with pytest.raises(AssertionError) as caught:
        fakes.call(_store(tmp_path, leg))
    message = str(caught.value)
    assert f"1 new run of {JOB} (new run ids: 43), expected exactly the leg's run 42" in message


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
@pytest.mark.parametrize("read", [1, 2])
def test_ac169_a_base_exception_from_the_reader_propagates(
    tmp_path: Path, leg: str, read: int
) -> None:
    fakes = Fakes(leg, _present(leg))
    fakes.replies = {read: Stop("stop")}  # a BaseException: the reader maps only Exception
    with pytest.raises(Stop):
        fakes.call(_store(tmp_path, leg))


def test_ac169_a_base_exception_from_the_second_refusal_read_propagates(tmp_path: Path) -> None:
    fakes = Fakes("rerun", {key: False for key in KEYS})
    fakes.replies = {2: Stop("stop")}
    with pytest.raises(Stop):
        fakes.call(_store(tmp_path, "rerun"))


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac168_error_exits_make_no_second_read(tmp_path: Path, leg: str) -> None:
    def boom() -> dict[str, bool]:
        raise OSError("exists failed")

    fakes = Fakes(leg, _present(leg))
    with pytest.raises(OSError, match="exists failed"):
        rules.run_leg(
            leg,
            store=_store(tmp_path, leg),
            exists=boom,
            run_tasks=fakes.run_tasks,
            state=fakes.state,
            runs=fakes.runs,
        )
    assert fakes.reads == 1
    for raises in (AssertionError("run ended FAILED"), Stop("stop")):
        fakes = Fakes(leg, _present(leg))
        fakes.raises = raises
        with pytest.raises(type(raises)):
            fakes.call(_store(tmp_path, leg))
        assert fakes.reads == 1
    fakes = Fakes(leg, _present(leg))

    def busy() -> None:
        raise AssertionError("not idle")

    with pytest.raises(AssertionError, match="not idle"):
        rules.run_leg(
            leg,
            store=_store(tmp_path, leg),
            exists=fakes.exists,
            run_tasks=fakes.run_tasks,
            state=fakes.state,
            runs=fakes.runs,
            preflight=busy,
        )
    assert fakes.reads == 1


@pytest.mark.parametrize("leg", ["rerun", "rebuild"])
def test_ac168_a_pass_line_that_cannot_be_written_leaves_a_failed_record(
    tmp_path: Path, leg: str
) -> None:
    def report(line: str) -> None:
        if "passed" in line:
            raise OSError("closed")

    fakes = Fakes(leg, _present(leg))
    with pytest.raises(OSError, match="closed"):
        fakes.call(_store(tmp_path, leg), report=report)
    saved = json.loads((tmp_path / f"{rules.LEG_NAMES[leg]}.json").read_text(encoding="utf-8"))
    assert saved["outcome"] == "failed"
