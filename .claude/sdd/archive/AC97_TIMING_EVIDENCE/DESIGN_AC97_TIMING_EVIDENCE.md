# DESIGN: AC-97 Timing Evidence

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC97_TIMING_EVIDENCE |
| **Date** | 2026-11-04 |
| **Author** | Christian |
| **Source** | DEFINE_AC97_TIMING_EVIDENCE.md (Ready for Design, commit 3cb057a; Q-25 and Q-26 answered); archived `DESIGN_INGESTION_GUARD.md` (OD-23, DA-31, layout of the live tests) and its BUILD_REPORT (I-04, AC-97 row); `tests/integration/test_ingestion_guard_live.py` (AC-97 at `v0.4.0`, `_wait_pipeline_idle`, `_updates_between`); `tests/integration/conftest.py` (`Evidence`, `PeakRunner`, `EVIDENCE_DIR`); `src/smart_meter_peak_prediction/pipeline_guard.py` (`PipelineReport.message`, `exit_value`, `_checked_at`, `utc_text`, `TERMINAL_UPDATE_STATES`); `tests/test_integration_layout.py`; `tests/test_ingestion_guard_docs.py`; `tests/test_ingestion_guard_bundle.py` (tag helpers); `tests/test_secrets_hygiene.py`; `scripts/check_specs.py`; `docs/runbooks/meter_ingestion.md`; installed `databricks-sdk` 0.153.0 in `.venv` (read-only inspection of `service/pipelines.py`) |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

**ID numbering.** Guards continue after INGESTION_GUARD (last G-27): G-28 to G-33. Design
assumptions continue after DA-33: DA-34 to DA-38. User items continue after U-05; U-06 is not used
(nothing needs the user). FR, NFR, AC, C, A, D and OD ids are those of the DEFINE.

---

## Overview

The live AC-97 test keeps its mechanics and every shipped assertion, and gains an in-memory record
of what it learns: the update U it starts, the refused run and its check task, the rerun, and U's
end. A single outer `finally` writes that record with the shipped `Evidence.save` as
`out/evidence/ac97_timing.json`, also when an assertion fails or the platform raises. The time the
check read the pipeline comes from the check's own output (the "checked at" time of the busy
message, or `checked_at` of the exit value), the end of U from the pipeline event log, with the
first terminal observation of the test's existing idle wait as the fallback. All computing is done
by pure, SDK-free helpers in a new test-support module with their own unit tests. A new live test
`test_ac106_*` reads the file back and cross-checks it against the platform without starting
anything. The runbook gets one subsection; the production code, the bundle and the notebooks do not
change (C-14). Release v0.4.1.

---

## Architecture

```text
 LOCAL MACHINE (pytest -m integration)                     DATABRICKS FREE EDITION (dev, unchanged v0.4.0)

 test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds
   assert_ingestion_idle, peak job idle (unchanged)
   pipelines.start_update(full_refresh=False) -> U  ------------------------>  pipeline smart_meter_silver_gold
   facts = Ac97Facts(update_id=U)              (support.ac97_timing, in memory)
   try:                                        outer try (NEW)
     try:                                      shipped inner try
       refused = peak_runner.run(job, only=[check, refresh], expect FAILED) -> job smart_meter_ingestion
         except AssertionError: facts <- run found by jobs.list_runs + get_run_output (2 reads, failure path only)
                               raise with failure_hint(U) (shipped ladder + evidence file)
       facts <- refused run id, check task run id, start/end ms, result, error text  (0 reads)
       shipped asserts (unchanged, 7)
     finally:
       _wait_pipeline_idle(..., watch=facts.watch)   same 10 s polls of pipelines.get;
                                                     records first poll that lists U terminal (0 extra reads)
     facts <- read_update_end(): pipelines.get_update(U) + list_pipeline_events (1 page of 50)  (2 reads)
     shipped "no other update" assert (1); rerun (unchanged); facts <- rerun ids and results; asserts (3)
   except BaseException as exc: exc.add_note(EVIDENCE_NOTE); print(EVIDENCE_NOTE); raise
   finally:
     if the end was not read yet: read_update_end() (guarded; a failure leaves nulls)
     evidence.save("ac97_timing", build_record(facts))  -> out/evidence/ac97_timing.json (git-ignored)

 test_ac106_ac97_timing_evidence_matches_the_platform  (run right after; 0 runs, 0 updates)
   evidence.load("ac97_timing") -> internal consistency (margins, order, outcome)
   jobs.get_run(refused_run_id), jobs.get_run(rerun_run_id), pipelines.get_update(U)  (3 reads)

 support/ac97_timing.py (pure: no SDK, no I/O, no clock; imports pipeline_guard for utc_text and states)
   margins() parse_check_message() read_from_exit_value() pick_update_end() resolve_update_end()
   decide_outcome() build_record() failure_hint() EVIDENCE_NAME EVIDENCE_PATH_TEXT EVIDENCE_NOTE
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Timing helpers (`tests/support/ac97_timing.py`) | Pure functions and dataclasses of the *Helper API* below: margins, message parse, exit-value read, end-event pick, end resolution, outcome rule, record builder, failure hint and the evidence name. Imports only the standard library and `smart_meter_peak_prediction.pipeline_guard` (itself SDK-free) | Python 3.11 stdlib | FR-55 to FR-59, NFR-30, NFR-32, NFR-33 |
| Live AC-97 test (`tests/integration/test_ingestion_guard_live.py`, AC-97 function) | Fills `Ac97Facts` at the points where each fact becomes known, writes the record in an outer `finally`, adds the evidence note to any failure; the shipped mechanics and 11 assertions stay | pytest, databricks-sdk | FR-54, FR-57, FR-58, FR-61, NFR-31 |
| Live AC-106 test (same file, new function) | Loads the file, checks its internal consistency and cross-checks ids and times with 3 platform reads | pytest, databricks-sdk | FR-54 to FR-57, FR-59 (AC-106) |
| Idle wait (`_wait_pipeline_idle`, same file) | Unchanged polling; an optional `watch` records the first poll time at which U is listed in a terminal state, U's listed creation time and state | pytest helper | FR-57 (fallback) |
| Unit tests (`tests/test_ac97_timing.py`, `tests/test_ac97_timing_docs.py`) | AC-100 to AC-103 against the helpers and the real `pipeline_guard` messages; AC-104 runbook and hint; AC-105 no-change, assert retention, version | pytest | AC-100 to AC-105 |
| Layout test (`tests/test_integration_layout.py`) | Accepts three-digit AC names, expects AC-106 among the live ACs, checks the new test is collected | pytest | NFR-34, C-15 |
| Runbook (`docs/runbooks/meter_ingestion.md`) | New subsection "AC-97 timing evidence"; pointer in Evidence order row H | Markdown | FR-60 |
| Version | `0.4.1` in `pyproject.toml` and `__init__.py`; CHANGELOG at `/ship` | - | FR-62 |

---

## Data Model

No table, view, volume, contract file or model is created or changed. The feature writes one local
JSON file per AC-97 execution, overwritten by the next one (D-61), and reads platform metadata.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| `out/evidence/ac97_timing.json` (written) | local evidence (git-ignored, C-16) | One AC-97 execution that started an update (the latest) | `update_id` with `refused_run_id` | - | Exactly the fields of the DEFINE *AC-97 timing record* contract, `saved_at_ms` added by `Evidence.save`; `json.dumps(indent=2, sort_keys=True)` as shipped |
| Pipeline update U (`pipelines.get_update`, read) | platform metadata | One update | `update_id` | - | Fields used: `update.creation_time` (epoch ms), `update.state` (DA-36) |
| Pipeline events (`pipelines.list_pipeline_events`, read) | platform metadata | One event | event `id` | - | Fields used from `as_dict()`: `event_type`, `origin.update_id`, `timestamp` (ISO text), `message`; newest first, one page of 50 (DA-35) |
| Pipeline state (`pipelines.get`, already polled by the idle wait) | platform metadata | One pipeline | `pipeline_id` | - | `latest_updates[].update_id`, `.state`, `.creation_time` (fallback source) |
| Job run and task runs (`jobs.get_run`, `jobs.list_runs`, `jobs.get_run_output`) | platform metadata | One task run | job `run_id`, task `run_id` | - | `start_time`, `end_time` (epoch ms), `state.result_state`; check error text (`error` and `error_trace`) or notebook exit value |

**Field sources** (first non-null wins, in the listed order):

| Field | Source |
|---|---|
| `update_id` | The `update_id` returned by `start_update` in the test (never parsed) |
| `update_created_ts` | `get_update(U).update.creation_time`; else U's `creation_time` seen by the idle wait; else the "created" value of the check's message |
| `update_ended_ts`, `update_end_source` | `pick_update_end(events, U, final_state)` with source `platform`; else the idle wait's first terminal observation with source `observed_terminal`; else both null (FR-57) |
| `update_final_state` | `get_update(U).update.state` when terminal; else the terminal state seen by the idle wait; else null |
| `refused_run_id`, `check_task_run_id`, `check_started_ts`, `check_ended_ts`, `check_result` | The refused `PeakRun` (`run.run_id`, the first `check_silver_gold_idle` entry of `run.tasks`); on the failure path the run found by `jobs.list_runs(job_id, start_time_from=<ms before start_update>, expand_tasks=True, limit=5)`, the oldest run started after that time |
| `check_read_ts`, `check_read_update_state`, `check_read_pipeline_state` | `parse_check_message(errors[check], U)` when the check failed; `read_from_exit_value(outputs[check], U)` when it passed (FR-56) |
| margins | `margins(update_created_ts, check_read_ts, update_ended_ts)` on the stored values (FR-55) |
| `rerun_run_id`, `rerun_check_result`, `rerun_refresh_result` | The rerun `PeakRun` |
| `outcome` | `decide_outcome(...)` (G-32) |

**Message parse (A-34, v0.4.0 text of `PipelineReport.message`).** Before matching, ANSI escape
sequences are removed (`\x1b\[[0-9;]*[A-Za-z]`), because the task error is
`output.error` plus `output.error_trace`. The first match wins (the text can hold the message twice).

```text
checked at :  \(checked at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\)
line of U  :  update <re.escape(U)>, state ([A-Z_]+), pipeline state ([A-Z_]+|not reported),
              created (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z|creation time not reported)
```

"not reported" and "creation time not reported" give null. A message without the line of U gives
null U fields and keeps the "checked at" time when present (AC-102).

**End event pick (DA-35).** Among the given events, those with `event_type` `update_progress`,
`origin.update_id` equal to U and a `message` that contains `final_state` as a whole word are the
candidates; the result is the earliest candidate timestamp normalised by `utc_text`. Nothing is
picked when `final_state` is not in `TERMINAL_UPDATE_STATES` or no event qualifies. The pick does
not depend on the order of the events.

### Data quality rules (guards)

There is no profiled data; the source column names the requirement. `drop` means the value is
stored as `null` and never estimated.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| G-28 every timestamp passes through `pipeline_guard.utc_text` (ISO with zone, epoch ms, aware datetime to `YYYY-MM-DDTHH:MM:SSZ`, cut to the second); naive, empty or unparseable values become null | every `_ts` field | `drop` | NFR-30, AC-100, AC-101 (d) |
| G-29 a margin is computed only from two non-null stored timestamps, as a signed integer of seconds (the difference of the stored texts, so AC-106 can recompute it exactly) | margins | `drop` (null when an input is null) | FR-55, AC-100, AC-101 |
| G-30 parsed values are constrained by the patterns above (states `[A-Z_]+`, times with `Z`), U is matched literally; anything else is null and no parse raises | read fields | `drop` | FR-56, A-34, AC-102 |
| G-31 the record never stores raw error text, URLs or ids from text; the builder replaces any string value that contains `https://`, `dapi` or `Bearer` by null, and AC-103 asserts that none is left | record | `drop` at run time; `fail` in AC-103 | NFR-32 |
| G-32 outcome precedence: `update_ended_before_check` when the check exit outcome is `idle` or `update_outlived_read_seconds` is 0 or less; else `refused` when `check_result` is `FAILED`, `check_read_ts` is not null and `check_read_update_state` is not null and not in `TERMINAL_UPDATE_STATES`; else `incomplete` | `outcome` | `warn` (recorded; AC-97 pass criteria unchanged, D-64) | FR-59, AC-101, AC-103 |
| G-33 the evidence never masks the AC-97 result: every platform read made for the evidence is wrapped, its failure leaves nulls and prints one line (exception class and error code only); `Evidence.save` runs in the outer `finally` | live test | `warn` | FR-58, NFR-32 |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-24 | **Widen the layout rule to two or three digits and give AC-106 its own live test.** `AC_NAME` becomes `^test_ac(\d{2,3})_`, `EXPECTED_ACS` gains 106, the collection assertion gains `test_ingestion_guard_live.py::test_ac106_`, the failure text reads "test_acNN_ or test_acNNN_". The AC-97 test keeps its shipped name. The new live test is `test_ac106_ac97_timing_evidence_matches_the_platform`. Unit tests are named `test_ac100_` to `test_ac105_`; no rule constrains unit test names, and `check_specs.py` reads `AC-\d+` (three digits included) in the DEFINE, DESIGN and BUILD_REPORT tables, so neither needs a change | Every shipped name still matches (`\d{2,3}` followed by `_`), so the change cannot break a shipped test, and it is needed by the next three-digit live AC anyway. Keeping the AC-97 name keeps the runbook row H (`::test_ac97_*`), the shipped collection check and the AC-105 comparison on the same function. A separate AC-106 test checks the file against the platform with 0 runs, so it can be repeated without quota, and AC-97's pass criteria are untouched (D-64). The `test_ac97_ac106_` alternative would have left AC-106 invisible to `EXPECTED_ACS`. Search result: no other file assumes two digits (`grep` over `tests/`, `scripts/`, `docs/`) |
| OD-25 | **`tests/support/ac97_timing.py`**, imported as `from support import ac97_timing` by the unit tests and the live test | `tests/support` is already a package (`__init__.py`) imported as `support` by 15 test modules, including `tests/local_data/` from a subdirectory; the module is not collected (no `test_` prefix), and its dotted name `support.ac97_timing` cannot clash with the test basenames `test_ac97_timing.py` and `test_ac97_timing_docs.py` (the D-01 clash concerned two collected test files of equal basename). Not under `src/` (C-14). DA-34 |
| OD-26 | **Platform end time from the pipeline event log; fallback the idle wait's first terminal observation.** `UpdateInfo` in SDK 0.153.0 has `creation_time` and `state` but no end time, so `get_update` alone cannot give it. One `list_pipeline_events(pipeline_id, max_results=50)` page, read right after the pipeline is `IDLE` and before the rerun (so U's last events are the newest), gives the `update_progress` event that names the terminal state (*End event pick*). `get_update(U)` supplies the creation time and the final state. Terminal states are `pipeline_guard.TERMINAL_UPDATE_STATES` (`COMPLETED`, `FAILED`, `CANCELED`), the same set the check uses. Fallback (`observed_terminal`): the shipped 10 s poll in `_wait_pipeline_idle` already reads `pipelines.get`; it now also records the local UTC time of the first poll whose `latest_updates` lists U in a terminal state (an upper bound, resolution about 10 s plus the poll latency) | Uses only read calls the test identity already makes (`pipelines.*` reads); 2 extra reads on the happy path. The event filter syntax is not needed (the newest page suffices), which removes an assumption. A wrong or missing event cannot give a false `platform` value: the pick requires U's id and the final state in the same event, otherwise the fallback applies and the file says so (`update_end_source`) |
| OD-27 | **One outer `try` / `except BaseException` / `finally` around everything after `start_update`, with an in-memory `Ac97Facts` filled at checkpoints.** The `except` adds `EVIDENCE_NOTE` to the exception (`add_note`, PEP 678) and prints it, then re-raises; the `finally` reads the end of U if not yet read (guarded, G-33) and calls `evidence.save(ac97_timing.EVIDENCE_NAME, ac97_timing.build_record(facts))`. The shipped `except AssertionError` hint text moves into `ac97_timing.failure_hint(update_id)` unchanged and gains one sentence naming `out/evidence/ac97_timing.json` and the BUILD_REPORT. No `assert` statement is edited, moved out of the function or given a message | One write point is simpler to prove than checkpoints and still covers every exit (pass, assertion, `pytest.fail` from `PeakRunner`, which is a `BaseException`, and SDK errors). Facts are captured before the shipped asserts that might fail, so a failing assert still leaves them in the file. A note is the only way to name the file on a plain `assert` without changing it (FR-61); the print is the fallback if the note is not shown (DA-38) |
| OD-28 | **New subsection `### AC-97 timing evidence` directly after "### Evidence order for the integration tests" in `docs/runbooks/meter_ingestion.md`, and in row H the AC-97 item gains "writes `out/evidence/ac97_timing.json`; then `::test_ac106_*`; see AC-97 timing evidence".** `docs/runbooks/peak_model.md` is not changed | Row H is a table cell and too narrow for the ladder; a subsection gives the docs test a stable heading. The peak runbook does not mention AC-97, and the peak side is unchanged (C-14); a cross-reference would only add text to keep in step |

### Helper API (`tests/support/ac97_timing.py`)

```python
EVIDENCE_NAME = "ac97_timing"
EVIDENCE_PATH_TEXT = "out/evidence/ac97_timing.json"
EVIDENCE_NOTE = (
    "AC-97 timing evidence: out/evidence/ac97_timing.json. Copy it into the release's "
    "BUILD_REPORT before the next attempt overwrites it (runbook: AC-97 timing evidence)."
)
RECORD_FIELDS = (...)  # the 19 contract fields of the DEFINE, saved_at_ms excluded


@dataclass(frozen=True)
class CheckRead:
    read_ts: str | None = None
    update_state: str | None = None
    pipeline_state: str | None = None
    update_created_ts: str | None = None


@dataclass(frozen=True)
class TaskFacts:
    run_id: int | None = None          # job run id
    task_run_id: int | None = None
    start: Any = None                  # epoch ms as reported
    end: Any = None
    result: str | None = None


@dataclass
class UpdateWatch:                     # filled by _wait_pipeline_idle in the live test
    update_id: str
    created: Any = None
    state: str | None = None
    observed_terminal_ts: str | None = None


@dataclass
class Ac97Facts:                       # mutable, filled by the live test
    update_id: str
    watch: UpdateWatch                 # same update_id
    update_created: Any = None         # from get_update
    update_state: str | None = None    # from get_update
    events: list[dict] | None = None   # PipelineEvent.as_dict() of one page
    end_read: bool = False
    refused: TaskFacts | None = None   # run_id of the refused run, its check task
    check_error: str | None = None
    check_exit: dict | None = None
    rerun_run_id: int | None = None
    rerun_check_result: str | None = None
    rerun_refresh_result: str | None = None


def margins(created: Any, read: Any, ended: Any) -> dict[str, Any]:
    """update_created_ts, check_read_ts, update_ended_ts (G-28) and the two margins (G-29)."""

def parse_check_message(text: str | None, update_id: str) -> CheckRead: ...          # G-30
def read_from_exit_value(value: Mapping | None, update_id: str) -> CheckRead: ...    # checked_at,
    # pipeline.state, and latest_update.state when latest_update.update_id == U
def pick_update_end(events: Iterable[Mapping], update_id: str, final_state: str | None) -> str | None
def resolve_update_end(platform_ts: Any, observed_ts: Any) -> tuple[str | None, str | None]
def decide_outcome(check_result: str | None, read: CheckRead, exit_outcome: str | None,
                   outlived: int | None) -> str: ...                                  # G-32
def build_record(facts: Ac97Facts) -> dict[str, Any]: ...  # exactly RECORD_FIELDS, G-31
def failure_hint(update_id: str) -> str: ...  # shipped DA-31 ladder text + EVIDENCE_NOTE
```

`failure_hint` returns the shipped text "The update U may have ended before the check read it
(DA-31); the no-op update lasted about 125 s on dev. Run the test again; then start the update with
full_refresh=True; if it keeps passing vacuously record AC-97 as Partial with a direct
pipeline_guard.check_pipeline read during the update." followed by `EVIDENCE_NOTE`. Run ids are
integers when given as `int` or a digit string, else null. No function reads the clock, the
environment or a file.

### AC-97 test, new shape (outline)

```python
def test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds(
    workspace, job, peak_job, pipeline, peak_runner, evidence
) -> None:
    peak_runner.assert_ingestion_idle()
    _assert_peak_job_idle(workspace, peak_job)
    subset = [CHECK, REFRESH]
    before_ms = int(time.time() * 1000) - START_SLACK_SECONDS * 1000
    update_id = workspace.pipelines.start_update(
        pipeline_id=pipeline.pipeline_id, full_refresh=False
    ).update_id
    facts = ac97_timing.Ac97Facts(update_id, ac97_timing.UpdateWatch(update_id))
    try:
        try:
            try:
                refused = peak_runner.run(job, only=subset, expect="FAILED", require_idle=False)
            except AssertionError as exc:
                _capture_found_run(workspace, job, before_ms, facts)  # guarded, 2 reads
                raise AssertionError(f"{exc}. {ac97_timing.failure_hint(update_id)}") from exc
            _capture_refused(refused, facts)  # no read; before the shipped asserts
            check = _one(peak_runner, refused.run, CHECK)
            # ... the 7 shipped asserts, unchanged
        finally:
            _wait_pipeline_idle(workspace, pipeline.pipeline_id, watch=facts.watch)
        _read_update_end(workspace, pipeline.pipeline_id, facts)  # guarded, 2 reads
        during = [...]  # unchanged
        assert during == [], f"updates created during the refused run: {during}"
        rerun = peak_runner.run(job, only=subset, require_idle=True)  # expect SUCCESS
        _capture_rerun(rerun, facts)
        # ... the 3 shipped asserts, unchanged
    except BaseException as exc:
        exc.add_note(ac97_timing.EVIDENCE_NOTE)
        print(ac97_timing.EVIDENCE_NOTE)
        raise
    finally:
        if not facts.end_read:
            _read_update_end(workspace, pipeline.pipeline_id, facts)
        evidence.save(ac97_timing.EVIDENCE_NAME, ac97_timing.build_record(facts))
```

`_capture_found_run`, `_capture_refused`, `_capture_rerun` and `_read_update_end` are module
helpers in the live file that read SDK objects with `getattr` and store primitives only. Each
platform read in them sits in `try` / `except Exception`, prints one line with the exception class
and its `error_code` only (no message body, so no URL can be printed) and leaves the facts unset. `_wait_pipeline_idle` gains the keyword `watch: ac97_timing.UpdateWatch | None =
None`; its loop, its 10 s sleep, its 20 min deadline and its `IDLE` rule are unchanged.

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| - | None | - |

No decision outlives the feature in a way an ADR should record. The evidence file follows the
shipped `out/evidence/` pattern (D-61); the helpers are test code; the end-time source is a detail
of one live test with an automatic fallback recorded in each file; the three-digit layout rule is a
one-pattern test convention, visible in the test itself. ADR 0013 (the check) is unchanged and
needs no note: its behaviour and message are untouched (C-14).

---

## Delivery Plan

| Step | Scope | Manifest entries | Files |
|---|---|---|---|
| Precondition | Spec PR #32 (DEFINE and this DESIGN) merged or stable; tag `v0.4.0` present locally (it is, D-60) | - | - |
| PR 1 (branch `build/ac97-timing-evidence`) | Helpers, tests, runbook, version | 1 to 8 | 8 |
| Ship | CHANGELOG `[0.4.1]`, tag `v0.4.1` | 9 | 1 |

One build PR: 8 files, no deployable change. The live gate (AC-97 then AC-106) runs on the branch
after a deploy of the branch's tree.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Agents: `pipeline-builder`
(Databricks module) for the helpers and tests, `build-agent` for the runbook and the version,
`ship-agent` for the CHANGELOG. No Kafka or MLflow agent applies.

Existing inputs, read and not modified: `tests/integration/conftest.py`,
`src/smart_meter_peak_prediction/pipeline_guard.py`, `tests/test_ingestion_guard_docs.py`,
`tests/test_ingestion_guard.py`, `tests/test_ingestion_guard_bundle.py`, `scripts/check_specs.py`,
`docs/runbooks/peak_model.md`, everything under `resources/`, `notebooks/` and `databricks.yml`.

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | `tests/support/ac97_timing.py` | Create | Helper API above (G-28 to G-32); module docstring names FR-55 to FR-59 and states "no SDK, no I/O, no clock" | pipeline-builder | - |
| 2 | `tests/test_ac97_timing.py` | Create | AC-100 to AC-103 (Test Strategy). Own minimal fake client with `pipelines.get` only, fixed `now`; fake tokens built by concatenation (`"dapi" + ...`) so the AC-29 and AC-65 scans of tracked files stay clean | pipeline-builder | 1 |
| 3 | `tests/integration/test_ingestion_guard_live.py` | Update | AC-97 new shape (OD-27); `_wait_pipeline_idle` `watch`; capture and read helpers; new `test_ac106_ac97_timing_evidence_matches_the_platform`; module docstring: AC-106 and the order "AC-97, then AC-106". AC-94, AC-96, AC-98 unchanged | pipeline-builder | 1 |
| 4 | `tests/test_integration_layout.py` | Update | `AC_NAME` `^test_ac(\d{2,3})_`; failure text; `EXPECTED_ACS` gains 106 under a comment "AC97_TIMING_EVIDENCE"; collection assertion gains `test_ingestion_guard_live.py::test_ac106_` (the `test_ac97_` assertion stays) | pipeline-builder | 3 |
| 5 | `docs/runbooks/meter_ingestion.md` | Update | Subsection "### AC-97 timing evidence" (content below) and the row H pointer (OD-28) | build-agent | 1, 3 |
| 6 | `pyproject.toml` | Update | `version = "0.4.1"` (FR-62) | build-agent | - |
| 7 | `src/smart_meter_peak_prediction/__init__.py` | Update | Only the line `__version__ = "0.4.1"` (FR-62, AC-105) | build-agent | - |
| 8 | `tests/test_ac97_timing_docs.py` | Create | AC-104 and AC-105 (Test Strategy). Constants `V040_TREE_SHA256` and `V040_AC97_ASSERTS` computed at build from tag `v0.4.0` with the test's own functions, never typed by hand | pipeline-builder | 3, 5, 6, 7 |
| 9 | `CHANGELOG.md` | Update at `/ship` | `[0.4.1]` entry: Added (AC-97 timing evidence file, AC-106 live check, runbook subsection), Changed (layout rule accepts three-digit AC names; version 0.4.1) | ship-agent | 1 to 8 |

The build report (`.claude/sdd/archive/AC97_TIMING_EVIDENCE/BUILD_REPORT_AC97_TIMING_EVIDENCE.md`) is the output of
`/build` and is not a manifest entry.

**Runbook subsection content (entry 5).** Where the file is (`out/evidence/ac97_timing.json`,
git-ignored, overwritten by each AC-97 execution); the fields in one short table; the margins
`read_after_creation_seconds` (read minus creation; reference 27 s on 2026-10-23, update
`WAITING_FOR_RESOURCES`) and `update_outlived_read_seconds` (end minus read; positive means the
check read U while it was active), their sign, and that the "checked at" time is taken just after
the read and cut to the second, so `update_outlived_read_seconds` errs low; `update_end_source`
(`platform` or `observed_terminal`, an upper bound within about 10 s); the outcomes; then run
`::test_ac106_*`. "When AC-97 fails because the update ended early" (`outcome`
`update_ended_before_check`): copy the file into the release's BUILD_REPORT AC-97/AC-106 row; rerun
once; then start the update with `full_refresh=True`; then record AC-97 `Partial` with a direct
`check_pipeline` read during the update; copy each attempt's file before the next attempt. If a
refresh-only rerun is shown, it is
`--only check_silver_gold_idle,refresh_silver_gold` (AC-99 rule). No dated log of runs (D-65).

---

## Test Strategy

Levels as in INGESTION_GUARD: **Unit** (pytest, no workspace, runs in CI), **Integration**
(marker `integration`, deployed `dev` target, user-run). Every test name contains its AC id.
Timestamps in the unit tests use the DEFINE reference instants (creation 18:37:07Z, read 18:37:34Z,
end 18:39:12Z on 2026-10-23); epoch values are computed in the test from aware datetimes, not typed.

**Live plan.** One session, no Kafka, Aiven state irrelevant. 1. `databricks bundle validate -t dev
-p dev`, then `databricks bundle deploy -t dev -p dev` from a clean tree of the build branch (the
bundle content equals `v0.4.0` except the version string). 2. Pipeline, ingestion job and peak job
idle. 3. `.venv/bin/pytest -o addopts= -m integration
tests/integration/test_ingestion_guard_live.py::test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds`
(one no-op update, two subset runs, as shipped). 4. Right after:
`...::test_ac106_ac97_timing_evidence_matches_the_platform` (0 runs, 3 reads). 5. Copy the file into
the BUILD_REPORT AC-106 row with the wall time of step 3. If AC-97 fails on timing, follow the
runbook ladder; each attempt's file goes into the BUILD_REPORT before the next.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-100 | Unit | `tests/test_ac97_timing.py::test_ac100_margins_are_whole_utc_seconds_for_every_input_form` | Parametrized over ISO with `Z`, ISO with `+02:00`, epoch ms (int) and aware datetimes in a non-UTC zone for the three instants: `read_after_creation_seconds == 27`, `update_outlived_read_seconds == 98`; the three returned timestamps fully match the NFR-30 pattern and equal the UTC texts of the instants; two calls give equal results, also byte-equal after `json.dumps(..., sort_keys=True)` |
| AC-100 | Unit | `tests/test_ac97_timing.py::test_ac100_helpers_import_no_sdk_and_read_no_clock` | AST of `tests/support/ac97_timing.py`: no import of a `databricks` module, of `time`, `os`, `pathlib` or `subprocess`; no call named `now`, `utcnow`, `time`, `open`, `sleep` (NFR-33) |
| AC-101 | Unit | `tests/test_ac97_timing.py::test_ac101_missing_naive_or_early_end_never_raises` | Parametrized cases (a) to (e) of the DEFINE through `margins`, `decide_outcome` and `build_record`: (a) `update_outlived_read_seconds == -5`, outcome `update_ended_before_check` (also with a busy message naming U, G-32 precedence); (b) both margins null, outcome not `refused`; (c) creation margin 27, end margin null; (d) naive creation gives null `update_created_ts` and null `read_after_creation_seconds`; (e) exit value `outcome` `idle` gives `update_ended_before_check`. No case raises |
| AC-102 | Unit | `tests/test_ac97_timing.py::test_ac102_parser_reads_the_library_busy_message` | Messages from `pipeline_guard.check_pipeline(fake, id, caller=INGESTION_CALLER, now=fixed)`: busy with U `WAITING_FOR_RESOURCES` created at a known time; busy with two active updates, U second. The parser returns U's state, `pipeline state` and creation time and the "checked at" time exactly as rendered; same result when the message is wrapped as task error text (`"PipelineGuardError: " + msg + " " + ANSI-coloured trace containing msg`) |
| AC-102 | Unit | `tests/test_ac97_timing.py::test_ac102_parser_returns_nulls_for_other_messages` | Busy with no update listed (overall state `RUNNING`), fail-closed (`pipelines.get` raises), idle, `""`, `None` and an unrelated string: U state and creation null, no exception; "checked at" returned for the library messages and null for the others. `read_from_exit_value` on the idle exit value returns its `checked_at`, the pipeline state, and U's state only when `latest_update.update_id` is U |
| AC-102 | Unit | `tests/test_ac97_timing.py::test_ac102_end_event_pick_requires_the_update_and_its_final_state` | `pick_update_end` on `as_dict`-shaped events: picks the earliest `update_progress` event of U naming `COMPLETED` regardless of list order; ignores other updates, other event types, non-terminal final states and messages without the state; `resolve_update_end` gives `platform`, then `observed_terminal`, then nulls (FR-57) |
| AC-103 | Unit | `tests/test_ac97_timing.py::test_ac103_record_has_exactly_the_contract_fields` | Full facts (ids, task times in epoch ms, the busy message, U's times, events): keys equal `RECORD_FIELDS`, which equal the 19 DEFINE contract fields other than `saved_at_ms`; types per contract (ints, UTC texts, the enumerated `update_end_source` and `outcome`); `json.dumps` succeeds and is byte-stable; margins equal `margins()` on the stored timestamps; outcome `refused` |
| AC-103 | Unit | `tests/test_ac97_timing.py::test_ac103_missing_inputs_give_nulls_and_incomplete_and_no_secret` | Facts with only `update_id`: every other field null, outcome `incomplete`. Facts whose error text and event messages contain `https://host.example/x`, `Bearer abc` and a fake `dapi` token (built by concatenation): no record value contains `https://`, `dapi` or `Bearer` (G-31) |
| AC-104 | Unit | `tests/test_ac97_timing_docs.py::test_ac104_runbook_explains_the_timing_evidence` | Section "### AC-97 timing evidence" of `docs/runbooks/meter_ingestion.md` names `out/evidence/ac97_timing.json`, `read_after_creation_seconds`, `update_outlived_read_seconds`, `27 s`, `full_refresh=True`, `Partial`, `check_pipeline`, `BUILD_REPORT` and `test_ac106_`; row H names `ac97_timing.json`; every `--only` list in the file with `refresh_silver_gold` contains `check_silver_gold_idle` (own 3-line parser, same rule as AC-99). The shipped `tests/test_ingestion_guard_docs.py` runs unmodified in the same session |
| AC-104 | Unit | `tests/test_ac97_timing_docs.py::test_ac104_failure_hint_and_note_name_the_evidence_file` | `failure_hint("U")` contains the shipped ladder sentences and `out/evidence/ac97_timing.json`; `EVIDENCE_NOTE` contains it; `EVIDENCE_PATH_TEXT` equals `out/evidence/` plus `EVIDENCE_NAME` plus `.json`. AST of the AC-97 function: its `except AssertionError` handler raises with a call to `failure_hint`; an `except BaseException` handler calls `add_note`; the outermost `try` has a `finalbody` that calls `evidence.save` with `ac97_timing.EVIDENCE_NAME` (FR-58 wiring) |
| AC-105 | Unit | `tests/test_ac97_timing_docs.py::test_ac105_production_files_equal_v040_except_the_version` | Files from `git ls-files --cached --others --exclude-standard` under `src/smart_meter_peak_prediction/`, `resources/`, `notebooks/` and `databricks.yml`: aggregate SHA-256 over sorted `path NUL sha256 LF` lines, with the `__version__` line of `__init__.py` normalised to `0.4.0`, equals `V040_TREE_SHA256`; with tag `v0.4.0` present, the path set equals `git ls-tree -r --name-only v0.4.0` for those roots and each file equals `git show v0.4.0:<path>` byte for byte except that one line; `__init__.py` has exactly `__version__ = "0.4.1"`; `pyproject.toml` version is `0.4.1` |
| AC-105 | Unit | `tests/test_ac97_timing_docs.py::test_ac105_shipped_ac97_asserts_and_mechanics_are_kept` | `ast.unparse` of every `Assert` in the shipped function equals `V040_AC97_ASSERTS` (11 entries; checked against `git show v0.4.0:tests/integration/test_ingestion_guard_live.py` when the tag exists); each occurs in the new function at least as often (Counter). The new function has exactly one `start_update` call with `full_refresh=False` and exactly two `peak_runner.run` calls with `only=subset`, where `subset` is `[CHECK, REFRESH]` (FR-61) |
| AC-105 | Unit | `pytest` (no marker) and `scripts/check_specs.py`; also `tests/test_ingestion_guard_docs.py::test_ac99_adrs_record_the_reverse_check_and_specs_are_clean` (unchanged) | 0 failures and 0 errors, recorded in the build report; the shipped AC-99 test already asserts `check_specs.run(ROOT).errors == []` |
| AC-106 | Integration | `tests/integration/test_ingestion_guard_live.py::test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds` | Writes the file (FR-54, FR-58); passes with the shipped assertions |
| AC-106 | Integration | `tests/integration/test_ingestion_guard_live.py::test_ac106_ac97_timing_evidence_matches_the_platform` | `evidence.load("ac97_timing", <AC-97 test name>)`: keys equal the contract plus `saved_at_ms`; `outcome == "refused"`; `check_read_update_state` not terminal; `update_created_ts <= check_read_ts`; `check_started_ts - 1 s <= check_read_ts <= check_ended_ts + 1 s`; `update_outlived_read_seconds > 0`, `read_after_creation_seconds >= 0`, each equal to the difference of the stored texts; `update_end_source` not null; `refused_run_id != rerun_run_id`. Platform (3 reads): both runs belong to the ingestion job; refused run started at or after `update_created_ts` - 5 s and the rerun started after the refused run ended; `get_update(U)` creation equals `update_created_ts` to the second; `saved_at_ms` is later than U's creation. Values copied into the BUILD_REPORT AC-106 row, with the AC-97 wall time and run count (NFR-31) |
| AC-106 | Unit | `tests/test_integration_layout.py::test_integration_tests_cover_every_in_scope_ac` (updated) | `EXPECTED_ACS` includes 106 and the widened `AC_NAME` finds it; `test_integration_tests_are_collected_but_deselected_by_default` finds `::test_ac97_` and `::test_ac106_` (NFR-34) |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | Nothing deployable changes. For AC-106's precondition, `databricks bundle validate -t dev -p dev` and `databricks bundle deploy -t dev -p dev` from a clean tree (exit codes in the build report). AC-94 may be rerun as a free sanity check |
| Scheduling and retries | Schedules, retries and timeouts of both jobs unchanged. The live tests are user-run; AC-97 is retried by the runbook ladder only |
| Monitoring and alerting | Unchanged for the jobs. For the test: the evidence file, the note on any AC-97 failure, and the BUILD_REPORT row |
| Secrets | None added. The file and helpers store ids, states and UTC times only (G-31); raw error text is never stored; printed read failures show class and error code only. Credentials stay with the CLI profile; the file stays under git-ignored `out/` |
| Cost | AC-97: 0 extra runs and updates; 2 extra reads on the happy path (`get_update`, one events page), 4 on the failure path (plus `list_runs`, `get_run_output`), within NFR-31's 5; well under 30 s. AC-106: 0 runs, 3 reads. The live plan costs what the shipped AC-97 costs (one no-op update, two subset runs) |
| Backfill / reprocessing | Not applicable. A lost or overwritten file cannot be rebuilt from the repository; the BUILD_REPORT row is the durable record (C-16, D-65) |

---

## Assumption dependencies

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| DA-34 **Validated by prior art.** `tests/conftest.py` puts `tests/` on `sys.path` (pytest prepend import mode, no `__init__.py` in `tests/`), so `from support import ac97_timing` works for unit and integration modules; `tests/local_data/` already imports `support.harness` from a subdirectory | OD-25 | The shipped `test_integration_tests_are_collected_but_deselected_by_default` collects the live module with `-m integration` in CI, which imports it | Import through `importlib` from the file path in the live module |
| DA-35 (A-33) **Validated (live AC-106, dev, 2026-11-04).** `list_pipeline_events(pipeline_id, max_results=50)` returns, newest first by default, events whose `as_dict()` has `event_type`, `origin.update_id`, `timestamp` and `message`, and the transition of U to its terminal state is an `update_progress` event whose message names that state; the test identity can read it. Source: SDK 0.153.0 code (`PipelineEvent`, `Origin.update_id`, docstring "descending order by timestamp"); the message wording is not a documented contract. Evidence: first AC-106 run on dev, 2026-11-04, `update_end_source` = `platform`; update 1bb3c498-6f34-4303-98ad-ebd8c40f2ade ended `COMPLETED` at 18:52:28Z, read from the pipeline events. Single observation, dev only | OD-26 | First AC-106 run: `update_end_source` = `platform` | Automatic: `observed_terminal` from the idle wait; the build report records which source was used. If it is `observed_terminal`, a follow-up may drop the event read |
| DA-36 **Validated (live AC-106, dev, 2026-11-04).** `pipelines.get_update(pipeline_id, update_id)` returns `update.creation_time` (epoch ms) and `update.state` for an update that has ended (SDK docstring says "from an active pipeline"; the pipeline is active, the update finished). Evidence: same run, `get_update` on the finished update returned the creation time (18:51:29Z) and final state `COMPLETED`; AC-106's cross-check passed. Single observation, dev only | OD-26, AC-106 | First AC-106 run | Creation time and final state from the idle wait's `latest_updates` entry, then from the busy message; AC-106's platform cross-check of the creation time then uses `list_updates` (1 read) |
| DA-37 **Validated (shipped AC-97, 2026-10-23, in part; live AC-106, dev, 2026-11-04, in full).** The check task's `error` plus `error_trace` holds the busy line of U unbroken somewhere after ANSI sequences are removed. The shipped asserts found U, "rerun smart_meter_ingestion" and a `Z` time in that text. Evidence: AC-106 run, `check_read_update_state` = `INITIALIZING` (pipeline `RUNNING`), read at 18:51:56Z, parsed from the check task's error text; outcome `refused`. Single observation, dev only | FR-56, G-30 | First AC-106 run: `check_read_update_state` not null | `outcome` is `incomplete` and AC-106 fails without touching AC-97; `/iterate` to read the message from `output.error` alone or with a looser line pattern |
| DA-38 **Validated (build, 2026-11-04).** pytest (>= 8 in `dev`) shows PEP 678 notes added with `add_note` in the failure report. Evidence: a throwaway failing test (not committed) with pytest 9.1.1 showed both the `add_note` text and the printed line | OD-27, FR-58 | At build, one throwaway failing test in the scratch directory (not committed) | The same text is printed, and pytest shows captured stdout for a failed test |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| Local clock vs platform clock | `observed_terminal` uses the local clock while the read time uses the platform's; a skewed local clock shifts `update_outlived_read_seconds` | `platform` is preferred; the source is in the file; AC-106 compares only platform values with each other except `saved_at_ms`, which it compares with a minutes-wide gap |
| The parse depends on the v0.4.0 message text (A-34) | A later change of the message silently gives null read fields | AC-102 builds the message with the library itself, so a change breaks a unit test first |
| The outer `finally` grows the AC-97 function | Harder to read; risk of masking an exception | Facts are captured by small helpers; every evidence read is guarded (G-33); AC-104 checks the wiring and AC-105 the shipped asserts |
| Changing a shipped test (`test_integration_layout.py`) | Could weaken the layout guard | The change only widens the digit count and adds an expected AC; every shipped expectation stays |
| Trade-off: separate AC-106 test | One more test to run in order after AC-97 | It costs no run, can be repeated, and keeps AC-97's pass criteria as shipped (D-64) |
| Trade-off: G-32 precedence | A busy refusal whose end second equals the read second is recorded `update_ended_before_check` | Conservative: the file never claims `refused` when the timestamps disagree; AC-97's own asserts still decide pass or fail |
| Trade-off: one file per name (D-61) | A second attempt overwrites the first | Runbook: copy each attempt into the BUILD_REPORT first (D-65) |

---

## Open Items for the User

None. U-06 is not used: OD-24 to OD-28 are resolved above within D-60 to D-65, and the user's
answers to Q-25 (BUILD_REPORT) and Q-26 (no threshold) are applied. The platform items DA-35 and
DA-36 were validated by the first live AC-106 run (2026-11-04); no decision is open.

---

## Self-Review

- **Weak points:**
  - The failure path (FR-58) is proven by unit tests of the builder and by an AST check of the
    wiring, not by a live failure, which cannot be forced on dev.
  - The platform end time depends on the wording of an event message (DA-35). The pick refuses
    rather than guesses. The first live run recorded `platform`, but this is a single observation
    on dev; a later wording change would fall back to `observed_terminal`.
  - The live evidence is one run: the update lasted 59 s (not the 125 s of spike 06), so the
    margin after the read was 32 s (build I-13).
  - `observed_terminal` mixes the local clock with the platform's read time.
  - The AC-97 function gets a third level of `try`. It is correct but denser than the shipped one.
- **Risks:**
  - DA-37 held on the first live run. If a later message change leaves the task error text
    without the busy line in one piece, the record is `incomplete` and AC-106 fails, costing a
    live session after an `/iterate`.
  - The AC-105 golden constants must be computed from the tag at build; a hand-typed value would
    make the test meaningless.
- **Trade-offs:** Helpers under `tests/` keep production byte-identical (C-14) but cannot be reused
  by production code. A separate AC-106 test costs one more step in the runbook but keeps AC-97's
  meaning. Reading the check's own "checked at" time measures the state at the read, at the price of
  parsing text.
- **What I would do differently (with more budget or time):** Make the check itself emit a
  structured record (read time, U, state) in its task output for busy results too, for example a
  JSON line printed before `enforce_pipeline` raises, and read it with `get_run_output`. That
  removes the message parse (A-34, DA-37) for every live test of both guards, but it changes the
  notebook and the guard library, which this patch release excludes (C-14). A spike would first
  check that printed output is retrievable through the Jobs API for a failed serverless notebook
  task.
- **Next improvement:** Build entries 1 and 2 first and make AC-100 to AC-103 green, then entry 3,
  and run the shipped layout and collection tests before entry 4 to see the regex change is the
  only one needed.

---

## Next Step

`/build .claude/sdd/archive/AC97_TIMING_EVIDENCE/DESIGN_AC97_TIMING_EVIDENCE.md`

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-11-04 | Created from DEFINE_AC97_TIMING_EVIDENCE.md (Ready for Design): OD-24 to OD-28 resolved, guards G-28 to G-33, DA-34 to DA-38, helper API, AC-97 outline, 9-entry manifest (8 in one build PR, CHANGELOG at ship), test strategy for AC-100 to AC-106, live plan; no ADR. Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts at entry 1 |
| 2026-11-04 | DA-35, DA-36, DA-37 and DA-38 set to Validated with evidence (first live AC-106 run on dev: `update_end_source` = `platform`, `get_update` creation and state, `check_read_update_state` = `INITIALIZING`; throwaway pytest 9.1.1 test for `add_note`); prose in Open Items and Self-Review updated, genuine risks kept (single observation, dev only; 59 s update, 32 s margin, I-13) | Live AC-97 and AC-106 evidence recorded in BUILD_REPORT_AC97_TIMING_EVIDENCE.md (I-02 closed) | None for the build report, which already records the evidence; status stays `Ready for Build`; no manifest file to rebuild; DEFINE A-33 updated the same way and logged in the DEFINE |
