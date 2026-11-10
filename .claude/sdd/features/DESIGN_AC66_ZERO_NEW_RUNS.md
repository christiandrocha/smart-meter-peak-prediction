# DESIGN: AC-66 Zero New Runs

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_ZERO_NEW_RUNS |
| **Date** | 2026-11-10 |
| **Author** | Christian |
| **Source** | DEFINE_AC66_ZERO_NEW_RUNS.md (Ready for Design, 14/15; Q-35 to Q-39 answered by the user on 2026-11-10 with the recommended answers); follow-up `.claude/sdd/follow-ups/F_AC66_BOTH_LEGS_03.md` (AC66_BOTH_LEGS F-03, DC-01); precedent `.claude/sdd/archive/AC66_BOTH_LEGS/` (DESIGN, BUILD_REPORT, SHIPPED_2026-11-09.md Lessons Learned and Template Feedback); code read on 2026-11-10: `tests/support/ac66_rules.py` (`run_leg`, `precondition`, `leg_record`), `tests/test_ac66_rules.py` (`_load_conftest` with the `sys.modules` step, `Fakes`, the AC66_BOTH_LEGS AC-154 and AC-158 tests), `tests/integration/test_peak_data.py` (AC-66 section), `tests/integration/conftest.py` (`PeakRunner`, `peak_job`, `full_runs`), `tests/test_ac66_legs_docs.py`, `tests/test_integration_layout.py`, `docs/runbooks/peak_model.md` (sections 8 and 9), `resources/smart_meter_peak_model.job.yml`, `src/smart_meter_peak_prediction/pipeline_guard.py` (`islice(list_runs, 25)`), `scripts/check_specs.py`, `pyproject.toml` (ruff line length 100), `.claude/kb/databricks/bundles.md` (development mode pauses schedules); Jobs API reference "List job runs" (descending order by start time; `limit` 1 to 25, default 20; active runs are `QUEUED`, `PENDING`, `RUNNING`, `TERMINATING`) |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

**ID numbering.** Design decisions continue after AC66_BOTH_LEGS DA-48: DA-49 to DA-59. Guards
continue after AC66_BOTH_LEGS G-53: G-54 to G-58. User items continue after AC66_BOTH_LEGS U-06:
U-07 and U-08. Checked on 2026-11-10 with a repository-wide search for `DA-49` to `DA-69`,
`G-54` to `G-69`, `U-07` to `U-09` and any three-digit `DA-`, `G-` or `U-` id (none found). No
new open design question remains, so no OD id is added. FR, NFR, AC, C, A, D, Q and OD ids are
those of the DEFINE. Every ID of another spec carries that spec's name; unprefixed IDs are this
feature's own.

---

## Overview

`run_leg` gains one required, injected callable, `runs`, that returns the run ids of
`smart_meter_peak_model`. It is called twice per leg: first, before the snapshot and existence
reads; second, right after the refusal decision (refusal path) or right after the job run ended
(pass path). A new pure function, `count_runs`, compares the two reads by run id only and never
raises. A clean refusal keeps the AC66_BOTH_LEGS G-46 text and appends
`0 new runs of smart_meter_peak_model` with the newest run id of both reads. A refusal during
which a run appeared fails with a different first line that lists the new run ids. A pass needs
exactly one new run, equal to the leg's own run id, and prints one pass line. A read that raises
or returns anything but a list of integers is never reported as a clean refusal or a pass. The
live reader is a new method, `PeakRunner.run_ids(job)`: one Jobs API list request for the peak
job id, every life-cycle state, one page of 25. No production file, record field, evidence file,
test name or selector changes. Release v0.7.1, package version 0.4.1 (D-99).

---

## Architecture

```text
 LOCAL (pytest -m integration -rP, tests/integration/test_peak_data.py)       DATABRICKS (dev)

 test_ac66_rerun_leg_ac163_ac164_...    \  ac66_rules.run_leg(leg=..., runs=lambda:
 test_ac66_rebuild_leg_ac162_ac164_...  /      peak_runner.run_ids(peak_job), ...)
   0 leg not in LEG_NAMES -> AssertionError (no read at all; shipped behaviour)
   1 before = runs()                     -- jobs.list_runs(job_id=<peak>, limit=25) --> Jobs API
       raises or not list[int] -> AssertionError "run list ... could not be read"   [G-54]
   2 snapshot = parse_snapshot(store.read_text(SNAPSHOT_NAME))
   3 present = exists()                  -- information_schema.tables (3 reads) ---> warehouse
   4 precondition(...) refused:
       listed = runs()                   -- second list request ----------------> Jobs API
       count = count_runs(before, listed)                                            [G-55]
       0 new  -> AssertionError "<G-46 text>; 0 new runs of ... (newest ...)"
       >0 new -> AssertionError "AC-66 <leg> leg found N new run(s) ... while refusing"
       unreadable -> AssertionError "... could not be confirmed ..."                [G-57]
   5 preflight()                         -- peak_runner.assert_ingestion_idle
   6 store.remove(<leg file>)
   7 try: run = run_tasks()              -- jobs.run_now(only=DATA_TASKS), 1 run
          listed = runs()                -- second list request, run already ended
          count = count_runs(before, listed, run.run_id)
          merges, after = ..., state()   -- 3 checksum queries
          problems = [count problem unless own] + check_leg(...)
          problems -> AssertionError "AC-66 <leg> leg failed: ..."
          store.save(<leg file>, passed); report(pass line)
      except BaseException: save failed (guarded); raise          (shipped, unchanged)

 tests/support/ac66_rules.py (pure): RUN_JOB_NAME, RunCount, run_ids, count_runs + messages
 tests/integration/conftest.py: PeakRunner.RUN_LIST_LIMIT, PeakRunner.run_ids(job)

 CI (pytest, no marker): tests/test_ac66_rules.py (AC-165 to AC-170 on fakes, shipped
   AC66_BOTH_LEGS AC-154 to AC-158 kept), tests/test_ac66_legs_docs.py (AC-170 to AC-172,
   shipped AC66_BOTH_LEGS AC-159 to AC-161 kept)
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Run-count rule (`tests/support/ac66_rules.py`) | `RUN_JOB_NAME`, `RunCount`, `run_ids` (validates one read), `count_runs` (compares two reads, total), private message builders. No new import; still passes the shipped AC66_BOTH_LEGS AC-154 import and call check | Python 3.11 stdlib | FR-96, FR-99, FR-100, NFR-49, NFR-50, NFR-51 |
| Leg procedure (`run_leg`, same module) | New required keyword `runs`; the two reads in the order of G-56; refusal, read-failure and pass-path messages (G-57); pass line through `report` | Python | FR-96 to FR-99, FR-101, NFR-48 |
| Live reader (`PeakRunner.run_ids` in `tests/integration/conftest.py`) | `list(islice(client.jobs.list_runs(job_id=job.job_id, limit=25), 25))` of `run.run_id`; no state or time filter (G-58) | databricks-sdk (lazy, through the fixture's client) | FR-96, NFR-48 |
| Live leg tests (`tests/integration/test_peak_data.py`) | Both `run_leg` calls pass `runs=lambda: peak_runner.run_ids(peak_job)`; docstrings name AC-173 to AC-175; module docstring text (FR-103) | pytest | FR-96, FR-100, FR-103, FR-104 |
| Unit tests (`tests/test_ac66_rules.py`) | AC-165 to AC-169, AC-170 (reader on a fake client); the shipped `Fakes` gains a fake run list and the shipped calls pass `runs=` | pytest | FR-96 to FR-101, NFR-48 to NFR-51 |
| Docs and compatibility tests (`tests/test_ac66_legs_docs.py`) | AC-170 (AST of both call sites and of `run_ids`), AC-171 (v0.7.0 tests, constants and reset script kept), AC-172 (runbook and docstring texts) | pytest, `ast`, `git` when the tag exists | FR-101 to FR-103, NFR-52 |
| Runbook (`docs/runbooks/peak_model.md`) | Section 8 paragraph and the leg command lines (`-rP`); section 9 leg command lines and one new paragraph after "If a leg refuses or fails" | Markdown | FR-103 |

---

## Data Model

No table, view, volume, contract file, evidence file or record field is created or changed
(D-103, DA-51). The feature reads one platform listing twice per leg.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| Jobs API run list of `smart_meter_peak_model` (read) | platform metadata | One job run | `run_id`, scoped by the peak `job_id` | - | One request per read, `limit=25`, no `active_only`, `completed_only`, `start_time_from`, `run_type` (G-58). Only `run_id` is used. Newest first by start time (Jobs API reference, A-55) |
| `RunCount` (in memory, `ac66_rules`) | test value | One comparison of two reads | - | - | Fields `unreadable`, `new`, `newest_before`, `newest_after`, `own`; JSON-serializable through `dataclasses.asdict` (NFR-50) |
| `out/evidence/ac66_*.json` (read and written as shipped) | local evidence | As in AC66_BOTH_LEGS | As shipped | - | Unchanged: `RECORD_FIELDS`, `VERDICT_FIELDS`, file names; a refused leg still writes nothing (AC66_BOTH_LEGS FR-86) |
| Refusal message, failure message and pass line | test output, copied into the BUILD_REPORT | One leg execution | Leg name and run ids | - | Shapes in DA-52; ints, counts, class names and constants only (G-57) |

### Data quality rules (guards)

There is no profiled data; the source column names the requirement or assumption.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| G-54 Read validity: a read is usable only when it is a `list` whose every item is an `int` that is not a `bool`. A raised `Exception`, `None`, a tuple, a dict, a string, or a list holding `True`, `"4"`, `None`, a float or a nested list is unreadable. `BaseException` subclasses that are not `Exception` (`pytest.fail`, `KeyboardInterrupt`) are not caught and propagate | run-list reads | `fail` (first read: the leg stops before any other side effect; second read: never a clean refusal or a pass) | FR-99, AC-165 (e, f), AC-169 |
| G-55 New-run rule: `new` is the ascending tuple of run ids in the second read and not in the first; `own` is true only when `new` equals the one-element tuple of the leg's run id (an `int`, or an ASCII digit string turned into an `int`). Decided by run id only, never by a start time or the local clock. `count_runs` never raises: any defect gives `unreadable` `comparison rule` | `count_runs` | `fail` (refusal needs `new == ()`, pass needs `own`) | FR-96, FR-98, FR-100, D-102, NFR-50, NFR-51 |
| G-56 Side-effect order of `run_leg`. Refusal path: unknown-leg check (no read), first `runs()`, `store.read_text(SNAPSHOT_NAME)`, `exists()`, second `runs()`, raise; nothing else. Pass path: first `runs()`, snapshot read, `exists()`, `preflight()`, `store.remove`, `run_tasks()`, second `runs()`, `state()`, `store.save` (passed), `report` (pass line). First read unusable: raise after the first `runs()` and nothing else. No second read when `exists()`, `preflight()` or `run_tasks()` raises (DA-54) | `run_leg` | `fail` | FR-96, FR-99, NFR-48, AC-166 to AC-169 |
| G-57 Messages: every message and the pass line hold the leg name, counts, run ids, `RUN_JOB_NAME`, file names, the AC66_BOTH_LEGS G-46 texts and exception class names only; the text of a reader exception is never echoed (it can hold a host or a token) and is kept as `__cause__`. No message contains `https://`, `dapi`, `Bearer` or `@`, and none contains a time | messages | `drop` at run time (exception text); `fail` in AC-166 to AC-169 | NFR-49, NFR-51, OD-49 |
| G-58 Live reader scope: `PeakRunner.run_ids(job)` calls `jobs.list_runs` once with exactly the keywords `job_id=job.job_id` and `limit=RUN_LIST_LIMIT` (25) and takes at most 25 items with `islice`, so no second page is requested; it returns the raw `run_id` values and leaves validation to G-54. Both live calls pass the `peak_job` fixture, never `job` or `training_job` | live reader | `fail` (AC-170) | FR-96, FR-100, NFR-48, A-55 |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-46 | **DA-49.** `runs: Callable[[], Any]` is a required keyword-only parameter of `run_leg` with no default, placed after `state` and before `preflight`. A caller that omits it gets a `TypeError` at the call, so a live test cannot skip the count silently. The live tests pass `runs=lambda: peak_runner.run_ids(peak_job)` (a method on `PeakRunner`, which already holds the client and takes the job object in `run`). The shipped AC66_BOTH_LEGS AC-158 tests keep every assertion: `Fakes.call` passes `runs=self.runs`, the two direct calls (`test_ac158_unknown_leg_refuses`, `test_ac158_failing_preflight_keeps_the_old_record`) gain `runs=fakes.runs`, the fake run list starts as `[30, 20, 10]`, and the fake runner puts its run id 42 at the head of the list before it returns, so the shipped pass test still passes and the shipped failure tests still fail for their own reason | An optional parameter with a default (`lambda: []` or `None`) would let a live call that forgets it pass with a fake "0 new runs"; a required keyword cannot be forgotten. A method on `PeakRunner` gives AC-170 one AST shape to check (`peak_runner.run_ids(peak_job)`) and one unit test with a fake client, instead of a helper that takes `workspace` and a job id in the live module |
| OD-47 | **DA-50.** `jobs.list_runs(job_id=job.job_id, limit=25)` with no `active_only`, `completed_only`, `start_time_from` or `run_type`, read through `islice(..., 25)`: one request, one page of the maximum size. One page is enough: a run that starts after the first read is newer than every run in it, so it is among the first entries of the second read; more than 25 new runs still show 25 new ids (never 0, never exactly the leg's run). An older run that was not in the first read can only appear in the second read if the order changes (for example a queued run whose start time moves); it is then counted as new and fails the leg, which is the safe direction. With `max_concurrent_runs: 1`, a foreign run that starts while the leg's run is active is queued (`QUEUED`) or skipped (`SKIPPED`); both get a run id and are listed, so it counts as new and fails the leg (Q-36); a foreign run already active at the first read is in both reads, is not new, and makes the leg's own run wait or fail in `PeakRunner.run` | The rule needs no order and no page token; the only order-dependent value is the "newest run" shown in messages (the first entry of a read). `pipeline_guard` already reads `islice(list_runs(...), 25)` (`MAX_RUNS_READ`), and the shipped `full_runs` fixture uses `limit=25` live, so the page size is validated by prior art. `completed_only=True` (as in `full_runs`) would hide a pending or running run, the exact case FR-96 counts |
| OD-48 | **DA-51.** No record change: the counts and run ids live in the messages and the pass line only (D-103); `RECORD_FIELDS`, the AC66_BOTH_LEGS AC-158 field-set assertion and the verdict stay as at `v0.7.0` | A record field would need the user's OK, a change to AC66_BOTH_LEGS D-94 and to the verdict parser, for evidence that the BUILD_REPORT already copies from the test output |
| OD-49 | **DA-52.** Message shapes, all raised as `AssertionError` (as shipped) with `from <reader exception>` when a read raised (`from None` otherwise), so the original exception is visible as `__cause__` and its text never enters the message (G-57). The exact texts are in the table *Message shapes* below. A clean refusal keeps the AC66_BOTH_LEGS G-46 message unchanged and appends `; 0 new runs of smart_meter_peak_model (newest run before: <id>, after: <id>)`, so the shipped AC66_BOTH_LEGS AC-157 and AC-158 prefix checks stay green | One exception type keeps the shipped `pytest.raises(AssertionError)` checks; appending keeps the G-46 start that the shipped tests and the runbook rely on; distinct first lines make a "started a run and refused" regression impossible to read as a clean refusal |
| OD-50 | **DA-53.** On the pass path the second read comes right after `run_tasks()` returns, before `merges_from_outputs` and `state()`, so the window for a foreign run is the job run plus one list request, not the three checksum queries. A count problem does not stop the leg early: `state()` and `check_leg` still run, and the count problem is the first entry of the same `AC-66 <leg> leg failed: ...` message, followed by the `check_leg` problems; the `failed` record then holds the known merges and after state | One failure lists everything that is wrong, and the `failed` record keeps the most evidence. Reading right after the run keeps the shipped order "run, then state" and reads the list while the leg's own run is the newest |

### Further design decisions

| ID | Decision | Rationale |
|---|---|---|
| DA-54 | No second read on the other exits: an unknown leg raises before the first read (shipped AC66_BOTH_LEGS `test_ac158_unknown_leg_refuses` keeps `fakes.calls == []`); an exception from `exists()`, `preflight()` or `run_tasks()` propagates unchanged without a second read. None of these exits claims a run count | FR-96 fixes the second read only after the refusal decision and after the job run ended; a second read on an error path could raise and mask the first error (the AC66_BOTH_LEGS F-01 concern, out of scope by Q-39) |
| DA-55 | The pass line goes through the injected `report` (default `print`) after the `passed` save and inside the shipped `try`, so a pass line that cannot be written turns the leg into a `failed` record. The live leg commands in runbook sections 8 and 9 and in the live plan carry `-rP`, which prints the captured output of passing tests | FR-98 requires the line to be visible in the test output; pytest captures `print` by default and shows it for a passed test only with `-rP` (or `-s`). The selectors and their order are unchanged, so the shipped AC66_BOTH_LEGS AC-160 tests stay green |
| DA-56 | A-54 (a run from `run_now` listed at once) is in the unsafe direction and is mitigated three ways. (1) CI proves the order: no runner call on the refusal path (AC-166, AC-167, shipped AC66_BOTH_LEGS AC-158 (d)); the only realistic regression that starts a run before refusing would call `run_tasks`, which blocks until the run ended, long before the second read. (2) A build-time check before the evidence sequence (live plan step 3, U-08): start `smart_meter_peak_model` with `--only check_pipeline_idle --no-wait` (a read-only task, ADR 0012), then at once list the newest run of the job; Pass when it is the started run. This is not AC evidence and is the only `list-runs` read near the sequence. (3) Fallback when the check fails: `PeakRunner` gets `RUN_LIST_SETTLE_S` equal to the measured delay rounded up plus 5 seconds, `run_ids` sleeps that long before listing, with a unit test that patches `time.sleep`; recorded in the BUILD_REPORT Deviations table | A spike would need an ADR for one number; one read-only run and two CLI commands answer the question with the same evidence as AC66_BOTH_LEGS DA-47 (checked once at build, recorded in the BUILD_REPORT). Keeping the settle out of the default path avoids a fixed wait that the check may show is not needed |
| DA-57 | AC-171 compares with tag `v0.7.0` when it exists locally (it does: `.git/refs/tags/v0.7.0`) and always with golden constants computed at build from that tag with the test's own functions, never typed by hand: `V070_ASSERT_COUNTS` (per file, test function name to `assert` count), `V070_RULE_CONSTANTS_SHA256` (`ast.unparse` of the nine constants) and `V070_RESET_SHA256` (bytes of `scripts/reset_peak_model_outputs.py`) | Same mechanism as AC66_BOTH_LEGS DA-46: CI checks out one commit without tags and keeps a real check |
| DA-58 | Names and pins stay: the four live AC-66 names, the selectors, `EXPECTED_ACS` and `tests/test_integration_layout.py` are unchanged (FR-101, NFR-52); the AC66_BOTH_LEGS AC-161 pin stays on `v0.6.0` (D-100). Golden rule 3 is met by the two leg test docstrings, which name AC-173 to AC-175, and by the new unit test names (`test_ac165_` to `test_ac172_`) | FR-101 forbids renaming the live tests, so `test_ac173_` names are impossible; AC66_BOTH_LEGS DA-39 already put the live AC ids after `test_ac66_` and in docstrings |
| DA-59 | The reader is unit-tested on the `conftest` module that `tests/test_ac66_rules.py` already loads by path under `_integration_conftest_under_test`. That loader keeps its `sys.modules[spec.name] = module` step before `exec_module` (the module defines dataclasses, which resolve string annotations through `sys.modules`; AC66_BOTH_LEGS SHIPPED lesson "Design (module loading)"). No other file loads `conftest` by path; `tests/test_ac66_legs_docs.py` reads it with `ast` only | One loader, already proven in CI; the lesson is named so a second loader cannot drop the step |

### Message shapes (DA-52)

`<leg>` is `rerun` or `rebuild`; `<id>` is an integer or `none`; `<ids>` is a comma-separated
ascending list or `none`; `<cls>` is the class name of the reader exception, or
`not a list of integer run ids` when the read returned a wrong value, or `internal error`.

| Case | Message (one line) |
|---|---|
| First read unusable (FR-99) | `AC-66 <leg> leg: the run list of smart_meter_peak_model could not be read (first read: <cls>); no table was read, no job run was started and no evidence file was changed; next: check the CLI profile, then run the leg again` |
| Refused, 0 new runs (FR-97) | `<AC66_BOTH_LEGS G-46 refusal message>; 0 new runs of smart_meter_peak_model (newest run before: <id>, after: <id>)` |
| Refused, new runs found (FR-97) | `AC-66 <leg> leg found <n> new run(s) of smart_meter_peak_model while refusing (new run ids: <ids>; newest run before: <id>, after: <id>); find what started them before the next attempt; precondition: <G-46 message without its head>` |
| Refused, second read unusable (FR-99) | `AC-66 <leg> leg refused, but the count of new runs of smart_meter_peak_model could not be confirmed (second read: <cls>; newest run before: <id>); precondition: <G-46 message without its head>` |
| Pass path, count wrong (FR-98) | Problem entry `<n> new run(s) of smart_meter_peak_model (new run ids: <ids>), expected exactly the leg's run <id>` in the shipped `AC-66 <leg> leg failed: <problems>; record outcome failed in out/evidence/ac66_<leg>_leg.json` |
| Pass path, second read unusable (FR-99) | Problem entry `the count of new runs of smart_meter_peak_model could not be confirmed (second read: <cls>), the leg's run <id>` in the same failed message |
| Pass line (FR-98) | `AC-66 <leg> leg passed: 1 new run of smart_meter_peak_model, run <id> (newest run before: <id>)` |

"The G-46 head" is `AC-66 <leg> leg refused before any job run: `; only the clean refusal keeps
it. `run(s)` is `run` for 1 and `runs` otherwise.

### Rule API additions (`tests/support/ac66_rules.py`)

The module docstring gains one paragraph; nothing else above `run_leg` changes except the new
names below (placed after `verdict_message`). `leg_record` is not touched.

```python
"""...
AC66_ZERO_NEW_RUNS (FR-96 to FR-100, guards G-54 to G-58) adds the run count: ``run_leg``
reads the run ids of smart_meter_peak_model through the injected ``runs`` before anything
else and again after its refusal or its job run, and ``count_runs`` compares the two reads.
"""

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
```

### `run_leg`, new shape

Changed lines only are new; the `except BaseException` handler and everything from
`preflight()` to `store.remove(name)` are as shipped.

```python
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
    if run_ids(before) is None:
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
        ...  # unchanged: save the failed record (guarded), report a save error, re-raise
```

### Live reader (`tests/integration/conftest.py`)

`from itertools import islice` joins the standard-library imports. In `PeakRunner`, after
`NEVER_RAN`:

```python
    RUN_LIST_LIMIT = 25  # one list page, the API maximum (AC66_ZERO_NEW_RUNS DA-50)

    def run_ids(self, job: Any) -> list[Any]:
        """Run ids of ``job``, newest first, in every life-cycle state, from one request.

        No ``active_only``, ``completed_only`` or time filter, so a queued, pending, running
        or finished run all count; ``islice`` stops before a second page (AC66_ZERO_NEW_RUNS
        G-58). The values are returned raw; ``ac66_rules.run_ids`` validates them.
        """
        listed = self.client.jobs.list_runs(job_id=job.job_id, limit=self.RUN_LIST_LIMIT)
        return [run.run_id for run in islice(listed, self.RUN_LIST_LIMIT)]
```

The class docstring of `PeakRunner` and every other line of the file stay as they are.

### Live leg tests (`tests/integration/test_peak_data.py`)

Each of the two `run_leg` calls gains one keyword line after `state=...`:

```python
        runs=lambda: peak_runner.run_ids(peak_job),
```

New docstrings of the two leg tests (the first line of the rebuild docstring is the shipped one):

```python
    """PEAK_MODEL AC-66 rerun leg; AC66_BOTH_LEGS AC-163 (passes) and AC-164 (refuses after the
    reset); AC66_ZERO_NEW_RUNS AC-174 (1 new run, its own) and AC-175 (0 new runs). Needs the
    snapshot and the three tables; starts the four data tasks once."""
```

```python
    """PEAK_MODEL AC-66 rebuild leg (PEAK_MODEL NFR-17); AC66_BOTH_LEGS AC-162 (refuses before the
    reset) and AC-164 (passes after it); AC66_ZERO_NEW_RUNS AC-173 (0 new runs) and AC-175 (1 new
    run, its own). Needs the snapshot and none of the three tables; starts the four data tasks
    once and expects inserts equal to the snapshot counts."""
```

Module docstring: after line 3 (`AC66_BOTH_LEGS adds the live criteria ...`) one line, and after
the bullet sentence `A leg in the wrong table state refuses before any job run and changes no
evidence file.` five lines, indented as the bullet:

```text
AC66_ZERO_NEW_RUNS adds AC-173 to AC-175: each leg counts the new runs of the peak job itself.
```

```text
  Each leg reads the run list of ``smart_meter_peak_model`` (its job id only, runs in every
  state) before anything else and again after its refusal or its job run (AC66_ZERO_NEW_RUNS
  AC-173 to AC-175). A clean refusal ends with ``0 new runs of smart_meter_peak_model``; a
  refusal during which a run started fails with a message that names the new run ids; a
  passing leg prints ``1 new run of smart_meter_peak_model`` and its run id (``-rP``).
```

`_state`, `_table_exists`, `_tables_present`, `_leg_run`, `SNAPSHOT_TABLES`, `DATA_TASKS`, the
snapshot test, the verdict test and every other test stay byte-equal.

### Runbook (`docs/runbooks/peak_model.md`)

- Sections 8 and 9 code blocks: in each line that holds `-k "ac66_rerun_leg"` or
  `-k "ac66_rebuild_leg"`, insert `-rP ` after `pytest -m integration ` (three lines; the
  comments keep their text). No other command changes.
- Section 8, the paragraph that starts `Each AC-66 leg refuses before any job run` becomes:

```text
Each AC-66 leg refuses before any job run when the table state does not fit it (rerun leg: all
three tables present; rebuild leg: none present), and counts the new runs of
`smart_meter_peak_model` itself (section 9, "If a leg refuses or fails"); `-rP` prints the line
of a passing leg. The verdict starts no run and reads `out/evidence/ac66_before_rebuild.json`,
`ac66_rerun_leg.json` and `ac66_rebuild_leg.json`, and writes `ac66_verdict.json`; copy the four
files into the build report.
```

- Section 9, a new paragraph after the paragraph that starts `**If a leg refuses or fails.**`:

```text
Each leg reads the run list of `smart_meter_peak_model` (by its job id, runs in every state)
before anything else and again after its refusal or its job run, and compares the run ids. A
clean refusal ends with `0 new runs of smart_meter_peak_model` and the newest run id of both
reads. A refusal during which a run of the job started fails with a message that names the new
run ids instead of "refused before any job run": find what started the run, then run the leg
again. A passing leg prints `1 new run of smart_meter_peak_model` and its run id (`-rP`); any
other count fails the leg with `outcome` `failed`, and a run list that cannot be read is never
reported as a clean refusal or a pass.
```

Neither text contains `list-runs`, `optional`, "then the daily job" or "run the daily job", and
neither moves a first occurrence of the AC66_BOTH_LEGS AC-160 order needles.

### Unit-test fakes (`tests/test_ac66_rules.py`)

| Change | Detail |
|---|---|
| `Fakes.__init__` | Adds `self.listed = [30, 20, 10]` (newest first), `self.started = [42]` (ids the fake runner adds), `self.run_id = 42`, `self.replies: dict[int, Any] = {}` (read number 1 or 2 to a value to return, or an `Exception` to raise), `self.on_exists: Callable[[], None] or None` (called inside `exists`, for AC-167) and `self.reads = 0` |
| `Fakes.runs` | Appends `"runs"` to `calls`, increments `reads`, raises or returns `replies[reads]` when set, else returns `list(self.listed)` (a copy) |
| `Fakes.run_tasks` | After the shipped `raises` check, inserts each id of `started` at index 0 of `listed` in order (so `[42, 43]` gives `[43, 42, 30, 20, 10]`), then returns `LegRun(self.run_id, ...)` as shipped |
| `Fakes.exists` | Calls `on_exists` when set, after the shipped `calls.append("exists")` |
| `Fakes.call` | Passes `runs=self.runs` |
| `Logged` (new) | Wraps a store and appends `read_text:<name>`, `remove:<name>`, `save:<name>` to a shared call log, then delegates |
| `_no_secret(text)` and `_utc_only(text)` (new) | NFR-49: none of `https://`, `dapi`, `Bearer`, `@` in the text; NFR-51: every `\d{4}-\d{2}-\d{2}T\S*` match, stripped of `),.;`, fully matches `UTC_PATTERN` |
| Fake reader errors | `RuntimeError(" ".join(SECRETS) + " someone" + "@example.com")`, built by concatenation so the hygiene scans stay clean |

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| - | None | - |

No ADR is drafted. Every decision is a test mechanism of the AC-66 leg tests: an injected reader,
a pure comparison rule, message texts and one method on a test helper. None changes a platform,
data, deployment or contract choice, and none binds another feature. The A-54 question is
answered by a recorded build check (DA-56), as AC66_BOTH_LEGS DA-47 was, not by a spike, so the
spike rule's ADR does not apply. ADR 0012 (read-only pre-check) is cited only because the A-54
check runs its task. The pattern "a live test that claims it started nothing reads the run list
itself" is a lesson for `/ship`, not an architecture decision.

---

## Delivery Plan

| Step | Scope | Manifest entries | Files |
|---|---|---|---|
| Precondition | Spec PR (DEFINE and this DESIGN) open and stable; tag `v0.7.0` present locally (it is) | - | - |
| PR 1 (branch `build/ac66-zero-new-runs`) | Rules, live reader, unit tests, live tests, runbook, docs tests | 1 to 6 | 6 |
| Live gate (on the build branch, before `/ship`, Q-38) | A-53 and A-54 checks, then AC-173 to AC-175 on `dev`; the user runs the reset (U-07) | - | 0 |
| Ship | CHANGELOG `[0.7.1]`, tag `v0.7.1`; follow-up file closed; SHIPPED row AC66_BOTH_LEGS F-03 updated | 7 to 9 | 3 |

Entries 1, 3 and 4 land in one commit: the required `runs` makes every caller fail until it
passes the reader. `ruff check .` and `ruff format --check .` run before each commit.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Agents: `pipeline-builder`
(Databricks module) for test code, `build-agent` for the runbook, `ship-agent` for the release
entries. No Kafka or MLflow agent applies.

Existing inputs, read and not modified: `src/`, `resources/`, `notebooks/`, `databricks.yml`,
`scripts/reset_peak_model_outputs.py`, `scripts/check_specs.py`, `tests/test_integration_layout.py`
(DA-58), `tests/support/__init__.py`, `pyproject.toml`, the archived AC66_BOTH_LEGS DEFINE and
DESIGN (E4).

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | `tests/support/ac66_rules.py` | Update | Module docstring paragraph; `RUN_JOB_NAME`, `RunCount`, `run_ids`, `count_runs` and the private helpers (Rule API additions); `run_leg` new shape (G-54 to G-57). No new import; `leg_record`, `precondition`, `check_leg`, the verdict and every constant unchanged | pipeline-builder | - |
| 2 | `tests/integration/conftest.py` | Update | `from itertools import islice`; `PeakRunner.RUN_LIST_LIMIT` and `PeakRunner.run_ids` (G-58); nothing else changes | pipeline-builder | - |
| 3 | `tests/test_ac66_rules.py` | Update | Module docstring names AC66_ZERO_NEW_RUNS AC-165 to AC-170; fakes as in *Unit-test fakes*; the shipped `Fakes.call` and the two direct `run_leg` calls pass the reader; new tests of the Test Strategy for AC-165 to AC-170 (unit). The `_load_conftest` `sys.modules` step stays (DA-59). No shipped test loses an assertion | pipeline-builder | 1, 2 |
| 4 | `tests/integration/test_peak_data.py` | Update | `runs=` in both `run_leg` calls; the two leg docstrings; the module docstring lines (FR-103). Nothing else | pipeline-builder | 1, 2 |
| 5 | `docs/runbooks/peak_model.md` | Update | `-rP` in the three leg lines; section 8 paragraph; section 9 new paragraph | build-agent | 4 |
| 6 | `tests/test_ac66_legs_docs.py` | Update | Module docstring names AC66_ZERO_NEW_RUNS AC-170 to AC-172; new tests for AC-170 (AST), AC-171 and AC-172; constants `V070_TAG`, `V070_ASSERT_COUNTS`, `V070_RULE_CONSTANTS_SHA256`, `V070_RESET_SHA256` computed at build from tag `v0.7.0` with the file's own functions (`assert_counts`, `rule_constants_digest`, `hashlib.sha256` of the bytes) (DA-57). The shipped `V060_*` constants, `TAG` and the AC66_BOTH_LEGS AC-159 to AC-161 tests unchanged | pipeline-builder | 3, 4, 5 |
| 7 | `CHANGELOG.md` | Update at `/ship` | `[0.7.1]`: Changed (each AC-66 leg reads the run list of `smart_meter_peak_model` before and after and asserts 0 new runs on a refusal and exactly its own run on a pass; `run_leg` takes a required `runs` reader), Added (`count_runs`, `PeakRunner.run_ids`, unit and docs tests), Docs (runbook sections 8 and 9, `-rP`). Package version stays 0.4.1 (D-99) | ship-agent | 1 to 6 |
| 8 | `.claude/sdd/follow-ups/F_AC66_BOTH_LEGS_03.md` | Update at `/ship` | Closure filled, status `Closed` | ship-agent | 7 |
| 9 | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` | Update at `/ship` | Follow-ups row AC66_BOTH_LEGS F-03: target cell points to AC66_ZERO_NEW_RUNS and v0.7.1 (C-26); if `check_specs.py` rule (c) counts change, update `.claude/sdd/citation_allowlist.json` in the same commit | ship-agent | 8 |

The build report (`BUILD_REPORT_AC66_ZERO_NEW_RUNS.md`) is the output of `/build` and is not a
manifest entry. Six files in the build PR, nine in total.

---

## Test Strategy

Levels: **Unit** (pytest, no workspace, runs in CI) and **Integration** (marker `integration`, the
deployed `dev` target, user-run). Every new unit test name starts with its AC id; the two live leg
tests name their ACs in their docstrings (DA-58). Fixture values: fake run list `[30, 20, 10]`,
leg run id 42, a started foreign id 40 (AC-167) or 43 (AC-168 (b)); snapshot and records as in
the shipped AC66_BOTH_LEGS AC-158 fixtures. Rows with a "(order)" or "(after-state)" test type
are the side-effect order and after-state checks of the procedure, listed separately (AC66_BOTH_LEGS
SHIPPED lesson "Build review (side-effect order)").

**Live plan** (one session, one checkout of the build branch; Kafka not needed).

1. `databricks bundle validate -t dev -p dev`, then `databricks bundle deploy -t dev -p dev` from a
   clean tree (bundle content equals `v0.6.0`); exit codes in the BUILD_REPORT.
2. A-53: `databricks jobs get <peak job id> -p dev`; record `settings.schedule.pause_status`
   (expected `PAUSED`) and that `settings` holds no `trigger` or `continuous` block. If it is
   `UNPAUSED`, run steps 5 to 9 outside 07:45 to 08:30 UTC and record that.
3. A-54 (DA-56, U-08), not AC evidence: `databricks bundle run -t dev -p dev
   smart_meter_peak_model --only check_pipeline_idle --no-wait`, then at once `databricks jobs list-runs --job-id <peak job id> --limit 1 -p dev`. Pass when the
   listed run id is the started run's id (from the command output or the Jobs UI); record both ids
   and the seconds between the commands; wait until the run has ended. On Fail apply the DA-56
   fallback and record it in Deviations.
4. `smart_meter_ingestion` and `smart_meter_peak_model` idle; the three tables present.
5. `pytest -m integration tests/integration/test_peak_data.py -k "ac66_before"` (snapshot).
6. AC-173: `pytest -m integration -rP tests/integration/test_peak_data.py -k "ac66_rebuild_leg"`
   (expected to fail, refused); copy the message.
7. AC-174: `pytest -m integration -rP tests/integration/test_peak_data.py -k "ac66_rerun_leg"`
   (1 run, passes); copy the pass line and `run_id` of `out/evidence/ac66_rerun_leg.json`.
8. U-07: the user runs `python scripts/reset_peak_model_outputs.py`, then with `--confirm`; the
   output goes into the BUILD_REPORT. If the user authorizes the agent for this one run instead,
   the authorization (the user's words and the date, with the condition that `--confirm` runs only
   when the dry run lists exactly the three `dev` tables) goes into the BUILD_REPORT Deviations
   table (C-27).
9. AC-175: `-rP -k "ac66_rerun_leg"` (expected to fail, refused naming the three missing tables),
   `-rP -k "ac66_rebuild_leg"` (1 run, passes), `-k "ac66_verdict"` (passes); copy the messages,
   the pass line, `run_id` of `ac66_rebuild_leg.json` and the verdict record. Steps 5 to 9 start
   2 job runs (NFR-48); step 3 starts 1 read-only run outside the sequence. No `list-runs` read is
   used for AC-173 to AC-175.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-165 | Unit | `tests/test_ac66_rules.py::test_ac165_run_count_rule_over_pairs_of_reads` | Parametrized over (a) `[3, 2, 1]`/`[3, 2, 1]`, (b) `[3, 2, 1]`/`[4, 3, 2, 1]`, (c) `[]`/`[7]`, (d) `[3, 2, 1]`/`[5, 4, 3, 2]`, each with leg run id `None` and `4`, each evaluated twice. `count_runs(...).new` is (a) `()`, (b) `(4,)`, (c) `(7,)`, (d) `(4, 5)`; `own` true only for (b) with 4; `unreadable` `""`; `newest_before`/`newest_after` (a) 3/3, (b) 3/4, (c) `None`/7, (d) 3/5; the two results of each (pair, leg id) are byte-equal after `json.dumps(dataclasses.asdict(r), sort_keys=True)` (NFR-50) |
| AC-165 | Unit | `tests/test_ac66_rules.py::test_ac165_run_count_rule_never_raises_on_odd_reads` | (e) second read `[x, 3, 2, 1]` for x in `True`, `"4"`, `None`, `4.0`, `[4]`, and the whole read `None`, `(4, 3)`, `"4,3"`; (f) first read `None`, `(3, 2, 1)`, `"3,2,1"`, `{3: 1}`, `3`; plus a `list` subclass whose `__iter__` raises. No call raises; `unreadable` is `second read`, `first read` and `comparison rule` respectively, `new == ()`, `own` false; with leg id 4 and with `None`; repeated results byte-equal. The shipped `test_ac154_rules_import_no_sdk_and_read_no_clock` still passes on the changed module (NFR-50, NFR-51: ids only) |
| AC-166 | Unit (order) | `tests/test_ac66_rules.py::test_ac166_refusal_reads_the_run_list_twice_and_reports_0_new_runs` | Parametrized over the six shipped `REFUSALS` (both legs: wrong full state, one partial state, no snapshot), `Logged` store on the real `Evidence(folder=tmp_path)` with an earlier `passed` record, `run_leg` called twice. The shared call log of each execution is exactly `["runs", "read_text:ac66_before_rebuild", "exists", "runs"]`: 2 run-list reads, the first before every other call, the second last; `run`, `state`, `preflight`, `remove:`, `save:` 0 times |
| AC-166 | Unit (after-state) | same test | After both executions `_files(tmp_path)` equals the bytes and listing taken before; the two messages are byte-equal |
| AC-166 | Unit (message) | same test | Each message starts `AC-66 <leg> leg refused before any job run:` and ends `; 0 new runs of smart_meter_peak_model (newest run before: 30, after: 30)`; `_no_secret` and `_utc_only` hold (NFR-49, NFR-51) |
| AC-167 | Unit (order) | `tests/test_ac66_rules.py::test_ac167_a_run_started_during_a_refusal_fails_differently` | The six `REFUSALS`, `fakes.on_exists` inserts 40 at the head of the fake list. Call log exactly `["runs", "read_text:ac66_before_rebuild", "exists", "runs"]`; `run` and `preflight` 0 times |
| AC-167 | Unit (after-state) | same test | Earlier record bytes and folder listing equal to before |
| AC-167 | Unit (message) | same test | `AssertionError` whose first line starts `AC-66 <leg> leg found 1 new run of smart_meter_peak_model while refusing`, contains `new run ids: 40` and `after: 40`, and the whole message does not contain `refused before any job run`; `_no_secret`, `_utc_only` |
| AC-168 | Unit (order) | `tests/test_ac66_rules.py::test_ac168_pass_checks_exactly_its_own_run` | Both legs, case (a) (runner adds 42): the call log is exactly `["runs", "read_text:ac66_before_rebuild", "exists", "preflight", "remove:<name>", "run", "runs", "state", "save:<name>"]` with `<name>` equal to `LEG_NAMES[leg]`, so the first read precedes the snapshot read and the second follows the runner and precedes the `passed` save |
| AC-168 | Unit (after-state) | same test, case (a) | The leg file has the full AC66_BOTH_LEGS AC-158 (a) record with `outcome` `passed` and `run_id` 42; `report` received exactly one line, `AC-66 <leg> leg passed: 1 new run of smart_meter_peak_model, run 42 (newest run before: 30)` |
| AC-168 | Unit (failure) | same test, cases (b) runner adds 42 and 43, (c) runner adds nothing | `AssertionError` starting `AC-66 <leg> leg failed:`; (b) contains `2 new runs of smart_meter_peak_model (new run ids: 42, 43), expected exactly the leg's run 42`; (c) contains `(new run ids: none), expected exactly the leg's run 42`; the `state` call still happened (DA-53) |
| AC-168 | Unit (after-state) | same test, cases (b), (c) | The leg file exists with `outcome` `failed` and `run_id` 42; no `*.json` in the folder has `leg` equal to the leg and `outcome` `passed`; `report` received no line; `_no_secret`, `_utc_only` on every message and line |
| AC-169 | Unit (order) | `tests/test_ac66_rules.py::test_ac169_unreadable_run_list_never_reports_a_pass` | Both legs, case (a) first read raises the fake `RuntimeError`, or returns `"x"`, `None` or `[True]`: call log exactly `["runs"]` (no snapshot read, `exists`, `preflight`, `run`, `state`) |
| AC-169 | Unit (message) | same test, case (a) | Message contains `the run list of smart_meter_peak_model could not be read` and `first read: RuntimeError` (or `first read: not a list of integer run ids`); for the raise case `__cause__` is the fake error and no part of its text (`SECRETS`, `@example.com`) is in the message |
| AC-169 | Unit (after-state) | same test, cases (a), (b) | Evidence bytes and folder listing equal to before |
| AC-169 | Unit (message) | same test, case (b): a refusal state (`REFUSALS[0]` and `REFUSALS[1]`) with read 2 raising | Message contains `could not be confirmed (second read: RuntimeError; newest run before: 30)` and does not contain `0 new runs` or `refused before any job run`; call log `["runs", "read_text:ac66_before_rebuild", "exists", "runs"]`; `run`, `preflight` 0 times |
| AC-169 | Unit (after-state) | same test, case (c): right state, read 2 raises after the runner returned 42 | `AssertionError` containing `the count of new runs of smart_meter_peak_model could not be confirmed (second read: RuntimeError), the leg's run 42`, not `0 new runs`; `__cause__` is the fake error; the leg file has `outcome` `failed`, `run_id` 42; no `passed` record for the leg; `report` received no line |
| AC-170 | Unit | `tests/test_ac66_legs_docs.py::test_ac170_both_live_legs_pass_a_reader_bound_to_the_peak_job` | AST of `tests/integration/test_peak_data.py`: in each of the two `ac66_rules.run_leg` calls the keyword `runs` is a `Lambda` without arguments whose body is a `Call` with `ast.unparse(func) == "peak_runner.run_ids"`, positional arguments exactly `["peak_job"]` and no keywords; neither test function has a parameter `job` or `training_job`. AST of `tests/integration/conftest.py`: `PeakRunner.run_ids` holds exactly one call whose attribute is `list_runs`, with keywords exactly `{"job_id", "limit"}`, `job_id` unparsing to `job.job_id`, and no `active_only`, `completed_only`, `start_time_from`, `start_time_to`, `run_type`, `page_token`. The shipped `test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state` passes unchanged |
| AC-170 | Unit | `tests/test_ac66_rules.py::test_ac170_run_ids_reads_one_page_of_every_state_for_the_given_job` | `conftest.PeakRunner(fake_client, 1, "p").run_ids(SimpleNamespace(job_id=7))` with a fake `jobs.list_runs` that records its keywords and yields 30 runs with ids 130 down to 101 in mixed life-cycle states (`QUEUED`, `PENDING`, `RUNNING`, `TERMINATED`, `SKIPPED`): one call with keywords exactly `{"job_id": 7, "limit": 25}`; the result is the first 25 ids in listing order; the generator was advanced exactly 25 times (no second page) |
| AC-171 | Unit | `tests/test_ac66_legs_docs.py::test_ac171_v070_unit_tests_are_kept_with_their_asserts` | For `tests/test_ac66_rules.py` and `tests/test_ac66_legs_docs.py`: every name in `V070_ASSERT_COUNTS` exists as a top-level test function and its `assert` count (`ast.Assert` nodes inside it) is at least the golden count; with tag `v0.7.0` present, `assert_counts(git show v0.7.0:<file>)` equals the golden dict |
| AC-171 | Unit | `tests/test_ac66_legs_docs.py::test_ac171_rule_constants_and_reset_script_equal_v070` | `ast.unparse` of `SNAPSHOT_NAME`, `LEG_NAMES`, `VERDICT_NAME`, `SNAPSHOT_TEST`, `RERUN_TEST`, `REBUILD_TEST`, `VERDICT_TEST`, `RECORD_FIELDS`, `VERDICT_FIELDS` in `ac66_rules.py` hashes to `V070_RULE_CONSTANTS_SHA256`; the reset script's bytes hash to `V070_RESET_SHA256`; with the tag present both equal the tag's versions |
| AC-171 | Unit (shipped) | `tests/test_ac66_legs_docs.py::test_ac161_production_files_and_reset_guards_equal_v060`, `::test_ac161_snapshot_test_and_its_helpers_are_kept`, `::test_ac161_specs_are_clean`; `tests/test_ac66_rules.py::test_ac154_rules_import_no_sdk_and_read_no_clock` and every AC66_BOTH_LEGS AC-158 test with the reader argument | Unchanged and green: production files equal `v0.6.0` (D-100), the snapshot helpers keep their digest, `check_specs.run(ROOT).errors == []`, the rules module keeps its import and call bans (NFR-50), and the shipped leg tests pass with `runs=` added (FR-101) |
| AC-171 | Unit (gates) | Full `pytest` run (no marker) and `python scripts/check_specs.py`, BUILD_REPORT Verification Log | 0 failures and 0 errors (NFR-52); `pytest -m integration -o addopts= --collect-only -k ac66 tests/integration/test_peak_data.py` lists the four `v0.7.0` names (also asserted by the shipped AC66_BOTH_LEGS AC-159 test) |
| AC-172 | Unit | `tests/test_ac66_legs_docs.py::test_ac172_runbook_and_docstring_name_the_run_list_reads` | From the `**If a leg refuses or fails.**` marker to the end of runbook section 9, and in the module docstring of `test_peak_data.py`, with backticks removed, whitespace collapsed and casefolded, each needle is present: `run list of smart_meter_peak_model`, `again after its refusal or its job run`, `0 new runs of smart_meter_peak_model`, `names the new run ids`, `1 new run of smart_meter_peak_model`. Every paragraph (split on blank lines) of sections 8 and 9 that matches `ac66`, `AC-66` or the word `leg` contains no `list-runs`. The shipped AC66_BOTH_LEGS AC-160 tests pass unchanged |
| AC-173 | Integration | `tests/integration/test_peak_data.py::test_ac66_rebuild_leg_ac162_ac164_inserts_the_snapshot_rows_and_checksums_equal`, live plan step 6 | With the three tables present right after the snapshot, the test fails with the AC66_BOTH_LEGS G-46 refusal naming the three present tables and ending `0 new runs of smart_meter_peak_model (newest run before: X, after: X)` with equal ids; the message is copied into the BUILD_REPORT; no `list-runs` read is used (AC66_BOTH_LEGS F-03 DC-01, rebuild leg) |
| AC-174 | Integration | `tests/integration/test_peak_data.py::test_ac66_rerun_leg_ac163_ac164_merges_nothing_and_checksums_equal`, live plan step 7 | The test passes as AC66_BOTH_LEGS AC-163 requires (MERGE 0 / 0 / 0, counts and checksums equal to the snapshot); the `-rP` output holds `AC-66 rerun leg passed: 1 new run of smart_meter_peak_model, run R` and R equals `run_id` in `out/evidence/ac66_rerun_leg.json`; both copied into the BUILD_REPORT |
| AC-175 | Manual (user, U-07) | Live plan step 8 | The reset dry run lists exactly the three `dev` tables, `--confirm` drops them; the output goes into the BUILD_REPORT; a per-run authorization of the agent goes into the Deviations table (C-27) |
| AC-175 | Integration | `::test_ac66_rerun_leg_...`, then `::test_ac66_rebuild_leg_...`, then `::test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot`, live plan step 9 | The rerun leg fails with the refusal naming the three missing tables and `0 new runs of smart_meter_peak_model` with equal newest ids (AC66_BOTH_LEGS F-03 DC-01, rerun leg); the rebuild leg passes as AC66_BOTH_LEGS AC-164 requires and prints `1 new run of smart_meter_peak_model, run B` with B equal to `run_id` in `ac66_rebuild_leg.json`; the verdict passes with empty `problems`; the rebuild record's `after` holds the snapshot counts, so the tables are present again. Messages, lines, records and the reset output copied into the BUILD_REPORT |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | Nothing deployable changes. For the live gate, `databricks bundle validate -t dev -p dev` and `databricks bundle deploy -t dev -p dev` from a clean tree of the build branch; exit codes in the BUILD_REPORT |
| Scheduling and retries | Schedules, retries and timeouts of the three jobs are unchanged. A-53 is read once at build (live plan step 2). A-56 holds by code reading: the data tasks have `max_retries: 1`, and a task retry is a second task run inside the same job run (`PeakRunner.task_runs_by_key`, runbook "Serverless auto-optimization and retries"), so it keeps the job run id; AC-174 and AC-175 confirm one new run per passing leg. A leg that fails on a foreign run is rerun once its cause is known (Q-36) |
| Monitoring and alerting | Unchanged for the jobs. For the evidence: the refusal and failure messages and the `-rP` pass lines, copied into the BUILD_REPORT |
| Secrets | None added. The reader uses the fixture's client (CLI profile or `DATABRICKS_*` variables). Messages hold ids, counts, constants and exception class names only (G-57); reader exception texts are never echoed. Fake secrets and the fake address are built by concatenation |
| Cost | Each leg adds 2 Jobs API list requests and 0 job runs and 0 SQL statements (NFR-48); the sequence of AC-173 to AC-175 starts 2 job runs (as AC66_BOTH_LEGS NFR-44). The A-54 check starts 1 read-only `check_pipeline_idle` run outside the sequence (about a minute of serverless). CI gains about 25 unit cases and no subprocess |
| Backfill / reprocessing | Not applicable to the run count. A failed rebuild leg can leave a partial state that both legs refuse; recovery is the shipped runbook section 9 path (full run of `smart_meter_peak_model`, new snapshot, full sequence) |

---

## Assumption dependencies

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| A-53 Nothing but a person starts `smart_meter_peak_model` on `dev` | Q-36 acceptance, AC-173 to AC-175 | Live plan step 2 (`pause_status`, no trigger); KB `bundles.md`: development mode pauses schedules | Run the sequence outside 07:45 to 08:30 UTC; a foreign run fails the leg (safe direction) |
| A-54 A run from `run_now` is listed at once | DA-56; the live strength of AC-173 and AC-175 | Live plan step 3 | DA-56 fallback (`RUN_LIST_SETTLE_S`), recorded in Deviations; CI order proof stands either way |
| A-55 Newest first; fewer new runs per leg than one page | DA-50 (only the "newest" shown in messages depends on order) | Jobs API reference: "descending order by start time"; AC66_BOTH_LEGS I-02 (CLI newest first); AC-173 to AC-175 messages show plausible newest ids | None needed for correctness: more than 25 new runs still fail the leg |
| A-56 A task retry keeps the job run id | DA-53, FR-98 | Code reading above; AC-174, AC-175 | A retry that created a second job run would fail the pass (safe direction); record and rerun |
| DA-50 `limit=25` is accepted and the SDK iterator pages lazily | G-58 | Prior art: `pipeline_guard` `islice(list_runs, 25)` and the `full_runs` fixture with `limit=25`, both live; AC-170 fake proves 25 pulls | `limit=20` (the API default) with `islice(..., 20)` |
| DA-56 `bundle run ... --only ... --no-wait` prints or exposes the run id | Live plan step 3 | Step 3 itself | Read the run id from the Jobs UI run list of the job |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| A-54 lag would hide a fire-and-forget `run_now` regression on the refusal path | A "0 new runs" that is not true | DA-56: CI order proof, build check, pre-designed fallback |
| A foreign run in the window fails a leg (Q-36) | On the rebuild leg's pass path: a new snapshot, rerun leg, reset and rebuild leg | A-53 check; the message lists the run ids so the cause can be found; accepted by the user |
| The required `runs` breaks every caller at once | A partial commit fails CI | Entries 1, 3 and 4 in one commit (Delivery Plan) |
| AC-171 counts `assert` statements | A weakened condition with the same count passes | Review reads the diff of the two shipped test files (DEFINE Self-Review) |
| Trade-off: messages only, no record field (DA-51) | Evidence of a refusal lives in the copied test output | BUILD_REPORT rows hold the copied messages; FR-104 |
| Trade-off: one page of 25 | An order change can make an old run look new | Safe direction (false failure); the message lists ids |
| Trade-off: the pass path still reads the state after a count problem | One more set of checksum queries on a failing leg | The `failed` record and the message carry every problem at once (DA-53) |

---

## Open Items for the User

| ID | Item | When |
|---|---|---|
| U-07 | Run `python scripts/reset_peak_model_outputs.py` (dry run), then with `--confirm`, between live plan steps 7 and 9, and paste the output; or authorize the agent for that one run with the dry-run condition, recorded in the BUILD_REPORT Deviations table with your words and the date (C-27) | Live gate of PR 1, before `/ship` (Q-38) |
| U-08 | OK for one read-only run of `smart_meter_peak_model` with `--only check_pipeline_idle` for the A-54 check (live plan step 3). Recommended: yes. If you decline, step 3 is skipped and A-54 stays `Pending` in the BUILD_REPORT, with the CI order proof as the only guard. **Answered 2026-11-10 by the user: yes** | Before the live gate |

No design question is open: OD-46 to OD-50 are resolved by DA-49 to DA-53.

---

## Self-Review

- **Weak points:**
  - The live check proves "no new run of the peak job appeared between two list requests", not
    "this code did not call `run_now`"; A-54 is checked once, on one day, and the CI order proof
    carries the rest.
  - The new unit tests check exact call logs and message texts, so a harmless refactor of
    `run_leg` (another read helper, a reordered keyword) needs the tests to change too, as the
    AC66_BOTH_LEGS AC-159 AST rules already do (AC66_BOTH_LEGS F-05).
  - AC-171 detects removed assertions, not weakened ones.
  - The pass line is visible only with `-rP`; an operator who drops the flag sees a pass without
    the line and must read the evidence file for the run id.
- **Risks:**
  - The live gate leaves `dev` without the feature and label tables between the reset and a
    passing rebuild leg (C-27); a failing rebuild leg leaves a partial state.
  - A foreign run during the rebuild leg's pass path costs a full new sequence with a reset.
  - The golden constants of AC-171 must be computed from tag `v0.7.0` at build; a typed value would
    make the CI check meaningless.
- **Trade-offs:** A required keyword breaks every caller once, in exchange for a check no caller
  can skip. Messages instead of record fields keep AC66_BOTH_LEGS D-94 and the verdict untouched,
  at the price of evidence that lives in copied test output. One page and run-id comparison need
  no clock and no ordering, and err only toward false failures.
- **What I would do differently (with more budget or time):** Give `PeakRunner` a ledger of the
  run ids it started itself (from `run_now`) and compare the listing with that ledger as well, so
  that a run started by the test process is told apart from a foreign run without filtering by
  creator; and replace the one-day A-54 check with a small spike that measures the listing delay
  over a few runs, recorded in an ADR, before relying on it for other live tests that refuse
  (for example PEAK_MODEL_CONCURRENCY).
- **Next improvement:** Build entries 1, 3 and 4 in one commit and make AC-165 to AC-170 and the
  shipped AC66_BOTH_LEGS AC-154 to AC-158 tests green, then compute the `V070_*` constants from the
  tag for entry 6; U-08 answered yes by the user on 2026-11-10.

---

## Next Step

`/build .claude/sdd/features/DESIGN_AC66_ZERO_NEW_RUNS.md`

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-11-10 | Created from DEFINE_AC66_ZERO_NEW_RUNS.md (Ready for Design, Q-35 to Q-39 answered): OD-46 to OD-50 resolved (DA-49 to DA-53), DA-54 to DA-59, guards G-54 to G-58, rule API additions, `run_leg` and live reader shapes, message shapes, text changes, 9-entry manifest (6 in one build PR, 3 at ship), test strategy for AC-165 to AC-175 with order and after-state rows, live plan with U-07 and U-08; no ADR. Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts at entry 1 |
| 2026-11-10 | U-08 answered yes by the user: one read-only `--only check_pipeline_idle` run for the A-54 check is allowed | User answer in the design session | Live plan step 3 runs at build |
