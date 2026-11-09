# DESIGN: AC-66 Both Legs

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | AC66_BOTH_LEGS |
| **Date** | 2026-11-09 |
| **Author** | Christian |
| **Source** | DEFINE_AC66_BOTH_LEGS.md (Ready for Design, commit d723bb7; Q-32 to Q-34 answered by the user on 2026-11-09); follow-up `.claude/sdd/follow-ups/F_PEAK_MODEL_15.md` (PEAK_MODEL F-15, DC-01); precedent `.claude/sdd/archive/AC97_TIMING_EVIDENCE/DESIGN_AC97_TIMING_EVIDENCE.md` (pure helper module under `tests/support/`, golden constants from a tag, layout rule); code read on 2026-11-09: `tests/integration/test_peak_data.py` (module docstring, `DATA_TASKS`, `SNAPSHOT_TABLES`, AC-66 section lines 379 to 422), `tests/integration/conftest.py` (`Evidence`, `checksum`, `PeakRunner.run`, `PeakRun.outputs`), `scripts/reset_peak_model_outputs.py`, `tests/test_peak_reset_script.py`, `tests/test_integration_layout.py`, `tests/test_ac97_timing_docs.py` (tag helpers), `tests/test_ingestion_guard_live_helpers.py` (load by path), `tests/conftest.py`, `pyproject.toml` (pytest `pythonpath`), `.github/workflows/ci.yml` (shallow checkout, no tags), `src/smart_meter_peak_prediction/pipeline_guard.py` (`utc_text`), `docs/runbooks/peak_model.md` (sections 8 and 9), `scripts/check_specs.py` |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

**ID numbering.** Design decisions continue after DA-38 (AC97_TIMING_EVIDENCE): DA-39 to DA-48.
Guards continue after G-45 (SMALL_CHANGE_TRACK): G-46 to G-53. User items continue after U-05
(U-06 was never used): U-06. No open design question remains, so OD-46 is not used. FR, NFR, AC,
C, A, D, Q and OD ids are those of the DEFINE. PEAK_MODEL AC-66 keeps its ID; every ID of another
spec carries that spec's name.

---

## Overview

The combined AC-66 test is replaced by three live tests and one pure rule module. A rerun-leg test
and a rebuild-leg test call the same leg procedure, `ac66_rules.run_leg`, with a constant leg name;
the procedure reads the snapshot and the table existence, refuses before any job run when the
state does not fit the leg, removes the leg's old record, starts the four data tasks once, checks
the MERGE metrics, counts and checksums against the snapshot, and saves a leg record with
`outcome` `passed` only when every check held (`failed` otherwise). A verdict test reads the
snapshot and both leg records, applies the pure verdict rule, saves the verdict record and passes
only when both legs passed against the current snapshot in the PEAK_MODEL AC-66 order. The
precondition, the expectations, the record builder and the verdict live in
`tests/support/ac66_rules.py`, with no SDK, no I/O and no clock, so CI proves them on fixtures; the
leg procedure gets every side effect as an injected callable, so CI also runs it with fakes. The
reset script changes only in its docstring and its two printed lines, the runbook gets the new
order, and nothing under `src/`, `resources/`, `notebooks/` or `databricks.yml` changes. Release
v0.7.0, package version 0.4.1 (D-92).

---

## Architecture

```text
 LOCAL MACHINE (pytest -m integration, tests/integration/test_peak_data.py)       DATABRICKS FREE EDITION (dev, unchanged v0.6.0)

 test_ac66_before_rebuild_snapshot (unchanged)  -- 3 checksum queries ------------------------->  SQL warehouse
   evidence.save("ac66_before_rebuild")  -> out/evidence/ac66_before_rebuild.json

 test_ac66_rerun_leg_ac163_ac164_...    \   ac66_rules.run_leg(leg="rerun" | "rebuild", ...)
 test_ac66_rebuild_leg_ac162_ac164_...  /     1 snapshot = parse_snapshot(store.read_text(SNAPSHOT_NAME))
                                              2 present  = exists()            -- information_schema.tables (3 reads)
                                              3 precondition(leg, snapshot_ok, present)
                                                  refused -> AssertionError (no job run, no file touched)  [G-46]
                                              4 preflight()                    -- peak_runner.assert_ingestion_idle
                                              5 store.remove(<leg file>)                                     [G-47]
                                              6 try: run = run_tasks()         -- jobs.run_now(only=DATA_TASKS), 1 run
                                                     merges = merges_from_outputs(run.outputs)
                                                     after  = state()          -- 3 checksum queries
                                                     problems = check_leg(leg, snapshot, merges, after)
                                                     problems -> AssertionError
                                                     store.save(<leg file>, leg_record(..., "passed"))
                                                except BaseException:
                                                     store.save(<leg file>, leg_record(..., "failed")) (guarded); raise
                                              -> out/evidence/ac66_rerun_leg.json | ac66_rebuild_leg.json

 (user only, U-06) python scripts/reset_peak_model_outputs.py [--confirm]  -- DROP 3 tables ---->  dev catalog

 test_ac66_verdict_ac163_ac164_...  (fixture: evidence only; 0 runs, 0 SQL)
   verdict = ac66_rules.evaluate(snapshot text, rerun text, rebuild text)                     [G-48 to G-51]
   evidence.save("ac66_verdict", verdict.record)   -> out/evidence/ac66_verdict.json (pass or fail)
   assert verdict.passed, ac66_rules.verdict_message(verdict)

 tests/support/ac66_rules.py  (pure: no SDK, no I/O, no clock; imports pipeline_guard.utc_text)
   constants, parse_snapshot, precondition, merges_from_outputs, expected_merges, check_leg,
   leg_record, evaluate, verdict_message, run_leg (side effects injected)

 CI (pytest, no marker): tests/test_ac66_rules.py (AC-154 to AC-158, real Evidence on tmp_path, fakes)
                         tests/test_ac66_legs_docs.py (AC-159 to AC-161), tests/test_integration_layout.py
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Rule module (`tests/support/ac66_rules.py`) | The *Rule API* below: file and test name constants, snapshot parse, precondition rule, expected MERGE metrics per leg, leg check, record builder, verdict rule and message, and the leg procedure `run_leg` with injected store, existence read, runner, state read, preflight and reporter. Imports only the standard library and `smart_meter_peak_prediction.pipeline_guard.utc_text` (SDK-free) | Python 3.11 stdlib | FR-84 to FR-90, NFR-43, NFR-45, NFR-46 |
| Evidence store (`Evidence` in `tests/integration/conftest.py`) | Gains a `folder` argument (default `EVIDENCE_DIR`, so the fixture and every shipped caller behave as before), `read_text(name)` (text or None, decode errors replaced) and `remove(name)` (missing is fine). `save` and `load` keep their format and messages and use `self.folder` | pytest helper | FR-84, FR-85, FR-87, FR-89 |
| Rerun-leg live test (`test_peak_data.py`) | Calls `run_leg(leg="rerun", ...)` with the live callables; PEAK_MODEL AC-66 first half | pytest, databricks-sdk (through fixtures) | FR-84, FR-86, FR-87 |
| Rebuild-leg live test (`test_peak_data.py`) | Calls `run_leg(leg="rebuild", ...)`; PEAK_MODEL AC-66 second half, PEAK_MODEL NFR-17 | pytest, databricks-sdk (through fixtures) | FR-85, FR-86, FR-87 |
| Verdict live test (`test_peak_data.py`) | Reads the three files, evaluates, saves the verdict record, asserts `pass`; takes only the `evidence` fixture | pytest | FR-88, FR-89, NFR-44 |
| Live helpers (`test_peak_data.py`) | `_tables_present` (the three `_table_exists` reads as one mapping, no branching) and `_leg_run` (a `PeakRun` to a `LegRun` of primitives). `_state`, `_table_exists`, `SNAPSHOT_TABLES`, `DATA_TASKS` and the snapshot test stay as at `v0.6.0`; the combined test is removed | pytest | FR-91, FR-92 |
| Unit tests (`tests/test_ac66_rules.py`, `tests/test_ac66_legs_docs.py`) | AC-154 to AC-161 | pytest | FR-90, FR-92 to FR-94, NFR-45 to NFR-47 |
| Layout test (`tests/test_integration_layout.py`) | The collection assertion for `test_ac66_after_` becomes three assertions for the new names; nothing else changes | pytest | FR-92, NFR-47, C-24 |
| Reset script text (`scripts/reset_peak_model_outputs.py`) | Module docstring (lines 3 and 26) and the two printed lines at the end of `main`; guard code unchanged (OD-44) | Python | FR-93, FR-94 |
| Runbook (`docs/runbooks/peak_model.md`) | Section 8 AC-66 lines and section 9 rewritten for the new order | Markdown | FR-93 |

---

## Data Model

No table, view, volume, contract file or model is created or changed. The feature writes three
local JSON files (one per name, overwritten by the next execution, D-94) and reads the unchanged
snapshot file, the job run outputs and `information_schema.tables`.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| `out/evidence/ac66_before_rebuild.json` (read) | local evidence (git-ignored, C-25) | One snapshot (the latest) | `saved_at_ms` | - | Unchanged writer and format (FR-91): `saved_at_ms`, then `silver_weather`, `features`, `labels`, each `row_count` (int) and `checksum` (text) |
| `out/evidence/ac66_rerun_leg.json`, `out/evidence/ac66_rebuild_leg.json` (written) | local evidence | One leg execution that passed its precondition and preflight (the latest) | `leg`, `snapshot_saved_at_ms` | - | Exactly `RECORD_FIELDS` (the 9 DEFINE *AC-66 leg record* fields other than `saved_at_ms`) plus `saved_at_ms` from `Evidence.save`; `json.dumps(indent=2, sort_keys=True)` as shipped |
| `out/evidence/ac66_verdict.json` (written) | local evidence | One verdict execution (the latest) | `snapshot_saved_at_ms` with `saved_at_ms` | - | Exactly `VERDICT_FIELDS` (the DEFINE *AC-66 verdict record* fields other than `saved_at_ms`) plus `saved_at_ms` |
| `out/evidence/ac66_after_rebuild.json` | local evidence | - | - | - | No longer written or read; left in place if present |
| Task exit values of `build_weather_silver`, `build_features`, `build_labels` (read) | job run output | One task run | job `run_id`, task key | - | `PeakRun.outputs[task]["merge"]`, a mapping with integer `inserted`, `updated`, `deleted` (A-50) |
| `information_schema.tables` of the dev catalog (read) | platform metadata | One table | `table_schema`, `table_name` | - | Through the shipped `_table_exists` (A-51) |

**Leg record fields** (in `leg_record`, G-52 applies to every value):

| Field | Source |
|---|---|
| `leg` | The constant leg argument of `run_leg` |
| `outcome` | `passed` only on the success path after `check_leg` returned no problem; `failed` on every exception after step 5 |
| `snapshot_saved_at_ms` | `saved_at_ms` of the parsed snapshot |
| `run_id` | `LegRun.run_id` when an `int` or a digit string, else null (null when the runner raised) |
| `started_ts`, `ended_ts` | `pipeline_guard.utc_text(LegRun.start_ms)` and `utc_text(LegRun.end_ms)` (the SDK run's `start_time` and `end_time`, epoch ms); null when unknown |
| `tables_present_at_start` | The existence mapping read in step 2, keys `silver_weather`, `features`, `labels`, booleans |
| `merges` | Per key: `inserted`, `updated`, `deleted` taken from the task's `merge` when each is an `int` (not `bool`), else null; the key is null when the task gave no `merge` mapping |
| `after` | Per key: `row_count` (int) and `checksum` (text) from `state()`; every key null when the state was not read (the field stays an object, as the contract says) |

**Verdict problem texts.** `evaluate` builds `Problem(subject, kind, detail)` values and renders
each as `"<subject>: <kind>: <detail>"`; the record's `problems` holds the rendered texts in a fixed
order (snapshot, rerun leg, rebuild leg, order). Subjects: `snapshot`, `rerun leg`, `rebuild leg`,
`verdict rule`. Each detail names the file (`out/evidence/<name>.json`) and ends with `next: ...`:

| Subject | Next step in the detail |
|---|---|
| `snapshot` | `run test_ac66_before_rebuild_snapshot with the three tables present, then the order of runbook section 8` |
| `rerun leg` | `run <RERUN_TEST> while the three tables exist (runbook section 8)`; for `out of order`: `start again with test_ac66_before_rebuild_snapshot (runbook section 8)` |
| `rebuild leg` | `the user runs python scripts/reset_peak_model_outputs.py --confirm, then <REBUILD_TEST>` |
| `verdict rule` | `report this as a defect of tests/support/ac66_rules.py` |

The rebuild-leg texts never contain `rerun`, and the rerun-leg texts other than `out of order`
never contain `rebuild`, so a message read by eye also names only its own leg (AC-155, AC-163).

### Data quality rules (guards)

There is no profiled data; the source column names the requirement.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| G-46 Precondition: the rerun leg needs a valid snapshot and all three tables present; the rebuild leg needs a valid snapshot and none present; any other state (including the six partial states, an unknown leg, a missing key or a non-boolean existence value) is refused before preflight, removal and job run. The message starts `AC-66 <leg> leg refused before any job run:` and names every table in the wrong state (`silver.weather_hourly`, `ml.household_features_daily`, `ml.household_labels_daily`), the missing or unreadable snapshot, and the next step (rerun leg with tables absent: run the rebuild leg; rebuild leg with tables present: run the rerun leg, then the user-run reset script; partial state: a full run of `smart_meter_peak_model` restores the missing tables, then start again with the snapshot test; snapshot: run the snapshot test) | leg tests | `fail` | FR-86, D-97, AC-157, AC-158 (d) |
| G-47 Record lifecycle: the leg file is removed after the precondition and the preflight held and before the runner is called; `passed` is written only as the last step of the success path; any `BaseException` after the removal writes a `failed` record with the facts known so far and is re-raised unchanged; a failure to write the `failed` record is reported in one line (`AC-66 <leg> leg: the failed record was not saved (<exception class>)`) and never replaces the original exception | leg files | `fail` | FR-87, AC-158 (b, c) |
| G-48 Parse: a file that is absent is `missing`; text that `json.loads` rejects (`ValueError`, `RecursionError`) or that is not a JSON object is `unreadable`; an object that lacks a required field or holds a wrong type is `malformed` (snapshot: `saved_at_ms` int, each of the three keys an object with int `row_count` and text `checksum`; leg: `leg` equal to the file's leg, `outcome` `passed` or `failed`, `saved_at_ms` and `snapshot_saved_at_ms` int, `run_id` int or null, `started_ts` and `ended_ts` null or NFR-43 text, `tables_present_at_start`, `merges`, `after` objects; a `passed` record also needs an int `run_id` and both timestamps). `bool` is never accepted as an int | snapshot, leg files | `fail` (verdict `fail`, the file named) | FR-90, AC-156 (h to j) |
| G-49 Per-leg precedence, at most one problem per leg: `missing`, `unreadable`, `malformed`, `failed` (`outcome` not `passed`), then, only with a valid snapshot, `stale` (`snapshot_saved_at_ms` differs from the snapshot's `saved_at_ms`, or `saved_at_ms` not greater than it), then `inconsistent` (one problem listing every table whose recorded `merges` differ from `expected_merges(leg, snapshot)`, whose `after` differs from the snapshot's `row_count` and `checksum`, or whose `tables_present_at_start` is not all true for the rerun leg or all false for the rebuild leg). Leg checks that need the snapshot are skipped when it is missing or invalid | leg files | `fail` | FR-88, FR-89, D-96, AC-155, AC-156 (a, b, d to g) |
| G-50 Order: only when both legs have no problem, the rerun record's `saved_at_ms` must be strictly less than the rebuild record's, else one `rerun leg: out of order` problem (D-95) | leg files | `fail` | FR-88, AC-156 (c), A-49 |
| G-51 Totality: `evaluate` and `precondition` never raise; a defect inside `evaluate` is caught at its top level and gives a failing verdict with one `verdict rule: internal error` problem naming the exception class only. Unit tests assert this problem never appears for any fixture | verdict | `fail` | FR-90 |
| G-52 No secret: no problem text, message or record value echoes a string read from an input file or a task output; details use integers, field names and constants only (a checksum mismatch says `checksum differs`); record strings from task outputs (`checksum`) that contain `https://`, `dapi` or `Bearer` are stored as null | records, messages | `drop` at run time; `fail` in AC-154 | NFR-46 |
| G-53 Timestamps: every `_ts` value passes through `pipeline_guard.utc_text`; naive, empty or unparseable values become null; order checks use `saved_at_ms` only | leg records | `drop` | NFR-43 |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-41 | **DA-39.** Live names (constants in `ac66_rules`): `test_ac66_before_rebuild_snapshot` (kept), `test_ac66_rerun_leg_ac163_ac164_merges_nothing_and_checksums_equal`, `test_ac66_rebuild_leg_ac162_ac164_inserts_the_snapshot_rows_and_checksums_equal`, `test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot`. Runbook selectors: `-k "ac66_before"`, `-k "ac66_rerun_leg"`, `-k "ac66_rebuild_leg"`, `-k "ac66_verdict"`; each is a substring of exactly one of the four names, and the stale `-k "ac66_after"` now selects nothing. `EXPECTED_ACS` is unchanged (66 is still covered; adding 162 to 164 would force names starting `test_ac162_`, which contradicts AC-159's `test_ac66_` prefix). Line 130 of `tests/test_integration_layout.py` is replaced by three assertions for `::test_ac66_rerun_leg_`, `::test_ac66_rebuild_leg_` and `::test_ac66_verdict_`, in the same commit as the rename. Unit tests: `test_ac154_` to `test_ac161_` | The leading `test_ac66_` keeps the layout rule, the PEAK_MODEL AC-66 coverage and the operator's mental map; the second AC id names this feature's live criteria (golden rule 3; the AC97_TIMING_EVIDENCE precedent `test_ac106_ac97_`). The word `leg` and the leg name follow `ac66_` directly, so the selectors are short and cannot overlap (the snapshot name holds `rebuild_snapshot`, not `rebuild_leg`) |
| OD-42 | **DA-40.** `tests/support/ac66_rules.py`, imported as `from support import ac66_rules` by `tests/test_ac66_rules.py`, `tests/test_ac66_legs_docs.py` and `tests/integration/test_peak_data.py` | `tests/support` is a package already imported this way from `tests/` and from `tests/integration/` (`support.ac97_timing` in `test_ingestion_guard_live.py`, AC97_TIMING_EVIDENCE DA-34); the module is not collected (no `test_` prefix); the basename `ac66_rules.py` is unique under `tests/` (INGESTION_GUARD D-01); not under `src/` (FR-94). The leg procedure lives in the same module because every side effect is injected, so it stays free of I/O imports and AC-158 runs it with fakes |
| OD-43 | **DA-41.** Remove, then run, then write `passed` last; on any exception after the removal write `failed` and re-raise (G-47). Refusal and preflight come before the removal | Removing first means no exit path, not even a killed process, can leave an old `passed` record of the leg; writing `failed` in the handler leaves evidence of the failed execution (matching the DEFINE grain "one execution that started its job run" and AC-156 (d)), and its guarded write cannot mask the error. The refusal reads only the snapshot and the table existence, so AC-158 (d), AC-162 and AC-164 find the old file byte-equal. The preflight (ingestion idle) before the removal keeps a busy ingestion job from destroying a valid record when no run starts |
| OD-44 | **DA-42.** No change to the reset script's guards; the D-95 order is enforced by the verdict only. The script changes in its module docstring (line 3 "the next daily run rebuilds them" becomes "the AC-66 rebuild leg rebuilds them"; line 26 usage comment becomes `drop; then the rebuild leg (-k ac66_rebuild_leg)`) and in the two printed lines at the end of `main` | DEFINE fences the guard code (FR-94, AC-161); a reset without a passing rerun record costs only one more sequence, and the verdict already refuses it (`rerun leg: missing` or `stale`), so a new guard would buy little and would need the user's OK and changes to `tests/test_peak_reset_script.py` |
| OD-45 | **DA-43.** The verdict reads the three files only (0 job runs, 0 SQL statements, fixture `evidence` only); the snapshot test is not changed and deletes nothing; older leg records become stale by `saved_at_ms` (D-96) | NFR-44; FR-91 requires the snapshot test unchanged; the leg records already carry the counts and checksums read right after each leg, and AC-156 (e to g) catches records that contradict the snapshot. A live re-read would catch a change after the rebuild leg, which is outside PEAK_MODEL AC-66 |

### Further design decisions

| ID | Decision | Rationale |
|---|---|---|
| DA-44 | `Evidence` gets `folder: Path = EVIDENCE_DIR`, `read_text(name)` and `remove(name)`; `tests/test_ac66_rules.py` loads `tests/integration/conftest.py` by path under the private name `_integration_conftest_under_test` (as `tests/test_ingestion_guard_live_helpers.py` loads the live module) and uses the real `Evidence(folder=tmp_path)` as the store | AC-158 then proves the file format, the `saved_at_ms` added by the shipped `save` and the removal on the class the live tests use, not on a copy. The conftest imports only `pytest`, `yaml` and the SDK-free library at module level, all present in the dev environment |
| DA-45 | `evaluate` returns `Verdict(record, problems)`; unit tests assert on `Problem.subject` and `Problem.kind`, and on the rendered texts for the file and test names | "Names exactly the leg concerned" (AC-155, AC-156) is then a precise, structural check, while the record keeps the contract's list of strings |
| DA-46 | AC-161 and the FR-91 checks compare with tag `v0.6.0` when it exists locally, and always with golden SHA-256 constants computed at build from that tag with the test's own functions (never typed by hand). CI checks out one commit without tags (`actions/checkout` default) | Same mechanism as AC97_TIMING_EVIDENCE AC-105: CI keeps a real check without the tag |
| DA-47 | AC-162 and AC-164 "0 new runs" and "byte-equal" are read by the operator around each refused leg: the newest run id of `smart_meter_peak_model` from `databricks jobs list-runs --job-id <peak job id> -p dev` (the command form of runbook section 2) and `sha256sum` of the leg file (or "absent"), before and after; both go into the BUILD_REPORT row | Keeps the leg tests free of extra platform reads; AC-158 (d) proves 0 runner calls in CI. Assumption: the CLI lists runs newest first; check once at build, fallback the Jobs UI run list of the job |
| DA-48 | The archived PEAK_MODEL DESIGN Test Strategy rows for PEAK_MODEL AC-66 keep naming the removed test (E4); this DESIGN supersedes that mechanism, and the SHIPPED row PEAK_MODEL F-15 is updated at `/ship` to point here | Archived documents are frozen; the trail lives in this spec and the follow-up file |

### Rule API (`tests/support/ac66_rules.py`)

```python
"""AC-66 both legs (AC66_BOTH_LEGS): precondition, expectations, records and verdict.

No SDK, no I/O, no clock: every side effect of run_leg is an injected callable (FR-90).
"""

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
MERGE_TASKS = {"silver_weather": "build_weather_silver", "features": "build_features",
               "labels": "build_labels"}
RECORD_FIELDS = ("leg", "outcome", "snapshot_saved_at_ms", "run_id", "started_ts", "ended_ts",
                 "tables_present_at_start", "merges", "after")
VERDICT_FIELDS = ("verdict", "problems", "snapshot_saved_at_ms", "rerun_saved_at_ms",
                  "rebuild_saved_at_ms")
UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


@dataclass(frozen=True)
class Snapshot:
    saved_at_ms: int
    tables: Mapping[str, Mapping[str, Any]]  # key -> {"row_count": int, "checksum": str}

@dataclass(frozen=True)
class Problem:
    subject: str   # "snapshot", "rerun leg", "rebuild leg", "verdict rule"
    kind: str      # "missing", "unreadable", "malformed", "failed", "stale", "out of order",
                   # "inconsistent", "internal error"
    detail: str    # names the file and ends with "next: ..."
    def text(self) -> str: ...  # "<subject>: <kind>: <detail>"

@dataclass(frozen=True)
class Precondition:
    allowed: bool
    message: str   # "" when allowed

@dataclass(frozen=True)
class LegRun:
    run_id: Any
    start_ms: Any
    end_ms: Any
    outputs: Mapping[str, Any]   # task key -> parsed exit value

@dataclass(frozen=True)
class Verdict:
    record: dict[str, Any]       # exactly VERDICT_FIELDS
    problems: tuple[Problem, ...]
    @property
    def passed(self) -> bool: ...


class EvidenceStore(Protocol):
    def read_text(self, name: str) -> str | None: ...
    def save(self, name: str, data: dict[str, Any]) -> None: ...
    def remove(self, name: str) -> None: ...


def parse_snapshot(text: str | None) -> tuple[Snapshot | None, Problem | None]: ...      # G-48
def precondition(leg: str, *, snapshot_ok: bool, present: Mapping[str, Any]) -> Precondition  # G-46
def merges_from_outputs(outputs: Mapping[str, Any]) -> dict[str, Any]: ...  # key -> merge or None
def expected_merges(leg: str, snapshot: Snapshot) -> dict[str, dict[str, int]]: ...
    # rerun: 0 / 0 / 0; rebuild: inserted = snapshot row_count, 0, 0
def check_leg(leg: str, snapshot: Snapshot, merges: Mapping[str, Any],
              after: Mapping[str, Any]) -> list[str]: ...
    # [] = pass; merge == expected (exact mapping equality, as the v0.6.0 assert) and
    # after[key] == {"row_count", "checksum"} of the snapshot, per table, ints and names only
def leg_record(leg: str, outcome: str, snapshot_saved_at_ms: int, run: LegRun | None,
               present: Mapping[str, Any], merges: Mapping[str, Any] | None,
               after: Mapping[str, Any] | None) -> dict[str, Any]: ...  # RECORD_FIELDS, G-52, G-53
def evaluate(snapshot_text: str | None, rerun_text: str | None,
             rebuild_text: str | None) -> Verdict: ...                   # G-48 to G-52
def verdict_message(verdict: Verdict) -> str: ...
    # "AC-66 verdict <pass|fail> (record out/evidence/ac66_verdict.json)" + one line per problem
def run_leg(leg: str, *, store: EvidenceStore, exists: Callable[[], Mapping[str, Any]],
            run_tasks: Callable[[], LegRun], state: Callable[[], Mapping[str, Any]],
            preflight: Callable[[], None] = lambda: None,
            report: Callable[[str], None] = print) -> dict[str, Any]: ...
    # steps 1 to 6 of the Architecture; returns the passed record; raises AssertionError on a
    # refusal ("AC-66 <leg> leg refused before any job run: ...") or a failed check
    # ("AC-66 <leg> leg failed: <check_leg problems>; record outcome failed in out/evidence/...")
```

`check_leg` and `expected_merges` take no table-existence argument, so the expectations depend on
the leg name only (FR-92). No function reads the clock, the environment or a file.

### Live tests, new shape (outline)

```python
from support import ac66_rules

def _tables_present(sql, settings, contracts) -> dict[str, bool]:
    return {key: _table_exists(sql, settings, contracts, stem) for stem, key in SNAPSHOT_TABLES}

def _leg_run(peak_run) -> ac66_rules.LegRun:
    run = peak_run.run
    return ac66_rules.LegRun(run_id=run.run_id, start_ms=run.start_time, end_ms=run.end_time,
                             outputs=peak_run.outputs)

def test_ac66_rerun_leg_ac163_ac164_merges_nothing_and_checksums_equal(
    sql, settings, contracts, checksum, evidence, peak_job, peak_runner
) -> None:
    """PEAK_MODEL AC-66 rerun leg; AC66_BOTH_LEGS AC-163 (passes) and AC-164 (refuses after the
    reset). Needs the snapshot and the three tables; starts the four data tasks once."""
    ac66_rules.run_leg(
        leg="rerun",
        store=evidence,
        exists=lambda: _tables_present(sql, settings, contracts),
        run_tasks=lambda: _leg_run(peak_runner.run(peak_job, only=DATA_TASKS)),
        state=lambda: _state(settings, contracts, checksum),
        preflight=peak_runner.assert_ingestion_idle,
    )

# test_ac66_rebuild_leg_ac162_ac164_...: the same call with leg="rebuild"; docstring names
# PEAK_MODEL AC-66 and PEAK_MODEL NFR-17, AC-162 (refuses before the reset) and AC-164 (passes).

def test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot(evidence) -> None:
    verdict = ac66_rules.evaluate(
        evidence.read_text(ac66_rules.SNAPSHOT_NAME),
        evidence.read_text(ac66_rules.LEG_NAMES["rerun"]),
        evidence.read_text(ac66_rules.LEG_NAMES["rebuild"]),
    )
    evidence.save(ac66_rules.VERDICT_NAME, verdict.record)
    assert verdict.passed, ac66_rules.verdict_message(verdict)
```

The removed combined test also removes the last writer of `ac66_after_rebuild.json`.

### Text changes

**Module docstring of `test_peak_data.py`** (the AC-66 bullet; the AC list in the first line gains
"AC66_BOTH_LEGS AC-162 to AC-164"):

```text
- AC-66 (AC66_BOTH_LEGS), in this order: ``ac66_before`` (snapshot, the three tables present);
  ``ac66_rerun_leg`` (rerun leg: MERGE 0 / 0 / 0, counts and checksums equal); the user runs
  ``scripts/reset_peak_model_outputs.py`` as a dry run, then
  ``reset_peak_model_outputs.py --confirm``; ``ac66_rebuild_leg`` (rebuild leg: starts the four
  data tasks itself, inserts the snapshot rows, counts and checksums equal); ``ac66_verdict``
  (reads out/evidence only; passes only when both legs passed against the current snapshot).
  A leg in the wrong table state refuses before any job run and changes no evidence file.
```

**Runbook section 8**, replacing lines 203 to 205:

```bash
pytest -m integration tests/integration/test_peak_data.py -k "ac66_before"       # snapshot, tables present
pytest -m integration tests/integration/test_peak_data.py -k "ac66_rerun_leg"    # rerun leg: MERGE 0 / 0 / 0
python scripts/reset_peak_model_outputs.py                                        # user only: dry run
python scripts/reset_peak_model_outputs.py --confirm                              # user only: drops the three tables
pytest -m integration tests/integration/test_peak_data.py -k "ac66_rebuild_leg"  # rebuild leg: starts the four data tasks
pytest -m integration tests/integration/test_peak_data.py -k "ac66_verdict"      # green only with both legs
```

plus one paragraph after the block: each leg refuses before any job run when the table state does
not fit it (rerun leg: all three tables present; rebuild leg: none present); the verdict starts no
run and reads `out/evidence/ac66_before_rebuild.json`, `ac66_rerun_leg.json` and
`ac66_rebuild_leg.json`, and writes `ac66_verdict.json`; copy the four files into the build report.

**Runbook section 9**: the code block ends with the rebuild leg and the verdict instead of
`-k "ac66_after"`; the paragraph says the rebuild leg (`-k "ac66_rebuild_leg"`) starts
`ingest_weather`, `build_weather_silver`, `build_features` and `build_labels` itself and compares
counts and checksums with the snapshot, so no job run is needed between the reset and the rebuild
leg; then the verdict (`-k "ac66_verdict"`). New sub-paragraph "If a leg refuses or fails":
refusal texts and their next step (G-46); a failed rebuild leg can leave a partial state, which
both legs refuse: a full run of `smart_meter_peak_model` restores the missing tables, then start
again with the snapshot. Sections 8 and 9 never use the phrases "then the daily job" or "run the
daily job", and "optional" does not occur next to the rebuild leg. Section 7 (Backfill) keeps its
sentence about a full rebuild by the reset and a daily run, which is the operational path, not the
AC-66 evidence.

**Reset script.** Module docstring line 3: "Drops exactly three tables so that the AC-66 rebuild
leg (or a later daily run) rebuilds them from Gold and Bronze weather:". Line 26:
`python scripts/reset_peak_model_outputs.py --confirm       # drop; then the rebuild leg (-k ac66_rebuild_leg)`.
The two `print` calls at the end of `main` (split into adjacent literals where a line would pass 100
characters, which keeps one string constant per call):

```text
done. Next (rebuild leg): pytest -m integration tests/integration/test_peak_data.py -k ac66_rebuild_leg
(it starts ingest_weather, build_weather_silver, build_features and build_labels itself and compares; then the AC-66 verdict; runbook, Reset)
```

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| - | None | - |

No ADR is drafted. Every decision here is a test mechanism of one acceptance criterion: the leg
split, the record lifecycle and the verdict rule live in test code and in this spec, change no
platform, data or deployment choice, and do not bind other features. The evidence files follow the
shipped `out/evidence/` pattern (D-94, AC97_TIMING_EVIDENCE D-61). The rule "one test per leg, no
mode chosen from the state" is a lesson for future specs, recorded at `/ship` in the SHIPPED
lessons, not a project-wide architecture decision. ADR 0006 (Bronze as the replay source) is
unchanged and still the reason the rebuild leg is possible.

---

## Delivery Plan

| Step | Scope | Manifest entries | Files |
|---|---|---|---|
| Precondition | Spec PR (DEFINE and this DESIGN) open and stable; tag `v0.6.0` present locally | - | - |
| PR 1 (branch `build/ac66-both-legs`) | Rules, Evidence store, unit tests, live tests, layout test, reset script text, runbook, docs tests | 1 to 8 | 8 |
| Live gate (on the build branch, before `/ship`, Q-33) | AC-162 to AC-164 on `dev`; the user runs the reset (U-06) | - | 0 |
| Ship | CHANGELOG `[0.7.0]`, tag `v0.7.0`; follow-up file closed; PEAK_MODEL SHIPPED row PEAK_MODEL F-15 updated | 9 to 11 | 3 |

One build PR with 8 files and no deployable change. The agent never runs
`scripts/reset_peak_model_outputs.py --confirm`; it may run the dry run only when the user asks.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Agents: `pipeline-builder`
(Databricks module) for test code and the reset script text, `build-agent` for the runbook,
`ship-agent` for the release entries. No Kafka or MLflow agent applies.

Existing inputs, read and not modified: `src/` (including `pipeline_guard.py`), `resources/`,
`notebooks/`, `databricks.yml`, `tests/test_peak_reset_script.py`, `tests/support/__init__.py`,
`scripts/check_specs.py`, `pyproject.toml`, the archived PEAK_MODEL DEFINE and DESIGN.

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | `tests/support/ac66_rules.py` | Create | Rule API above (G-46 to G-53); module docstring names FR-84 to FR-90 and states "no SDK, no I/O, no clock" | pipeline-builder | - |
| 2 | `tests/integration/conftest.py` | Update | `Evidence`: `folder` argument (default `EVIDENCE_DIR`), `read_text`, `remove`; `save` and `load` use `self.folder` with unchanged format and messages (DA-44); nothing else in the file changes | pipeline-builder | - |
| 3 | `tests/test_ac66_rules.py` | Create | AC-154 to AC-158 (Test Strategy). Fixtures built in code from the AC-154 values; real `Evidence(folder=tmp_path)` loaded by path (DA-44); fake runner, existence read, state read and preflight with call counters; fake secrets built by concatenation (`"da" + "pi"`, `"htt" + "ps://"`) so the hygiene scans of tracked files stay clean | pipeline-builder | 1, 2 |
| 4 | `tests/integration/test_peak_data.py` | Update | Module docstring (Text changes); `from support import ac66_rules`; `_tables_present`, `_leg_run`; the rerun-leg, rebuild-leg and verdict tests (outline); remove `test_ac66_after_rerun_and_rebuild_checksums_equal`. `_state`, `_table_exists`, `SNAPSHOT_TABLES`, `DATA_TASKS`, `test_ac66_before_rebuild_snapshot` and every other test unchanged | pipeline-builder | 1, 2 |
| 5 | `tests/test_integration_layout.py` | Update | Line 130 replaced by three assertions (`::test_ac66_rerun_leg_`, `::test_ac66_rebuild_leg_`, `::test_ac66_verdict_`); `EXPECTED_ACS`, `AC_NAME` and all other lines unchanged (DA-39, C-24). Same commit as entry 4 | pipeline-builder | 4 |
| 6 | `scripts/reset_peak_model_outputs.py` | Update | Docstring lines 3 and 26 and the two printed lines of `main` (Text changes); no other byte changes (DA-42) | pipeline-builder | 4 |
| 7 | `docs/runbooks/peak_model.md` | Update | Section 8 AC-66 lines and paragraph; section 9 block and text (Text changes) | build-agent | 4, 6 |
| 8 | `tests/test_ac66_legs_docs.py` | Create | AC-159, AC-160, AC-161 (Test Strategy). Constants `V060_TREE_SHA256`, `V060_RESET_SHA256` and `V060_KEPT_AST_SHA256` computed at build from tag `v0.6.0` with the test's own functions (DA-46); tag helpers as in `tests/test_ac97_timing_docs.py` | pipeline-builder | 3 to 7 |
| 9 | `CHANGELOG.md` | Update at `/ship` | `[0.7.0]`: Changed (PEAK_MODEL AC-66 evidence split into rerun leg, rebuild leg and verdict; the combined test and `-k "ac66_after"` removed; a one-leg sequence now fails), Added (`tests/support/ac66_rules.py`, unit tests, `Evidence.read_text` and `remove`), Docs (runbook sections 8 and 9, reset script hint). Package version stays 0.4.1 (D-92) | ship-agent | 1 to 8 |
| 10 | `.claude/sdd/follow-ups/F_PEAK_MODEL_15.md` | Update at `/ship` | Closure filled, status `Closed` | ship-agent | 9 |
| 11 | `.claude/sdd/archive/PEAK_MODEL/SHIPPED_2026-10-22.md` | Update at `/ship` | Follow-ups row PEAK_MODEL F-15: Follow-up cell no longer starts with `Open`, points to AC66_BOTH_LEGS and v0.7.0 (DA-48); if `check_specs.py` rule (c) counts change, update `.claude/sdd/citation_allowlist.json` in the same commit | ship-agent | 10 |

The build report (`BUILD_REPORT_AC66_BOTH_LEGS.md`) is the output of `/build` and is not a
manifest entry.

---

## Test Strategy

Levels: **Unit** (pytest, no workspace, runs in CI), **Integration** (marker `integration`, the
deployed `dev` target, user-run). Every test name contains its AC id. Fixture values are those of
AC-154: snapshot `saved_at_ms` 1000, counts 21,165 / 36,480 / 36,480 and three checksum texts;
rerun record `saved_at_ms` 2000; rebuild record `saved_at_ms` 3000; run ids, UTC timestamps and
`tables_present_at_start` filled consistently.

**Live plan** (one session; Kafka not needed; the agent never runs the reset).
1. `databricks bundle validate -t dev -p dev`, then `databricks bundle deploy -t dev -p dev` from a
   clean tree of the build branch (bundle content equals `v0.6.0`); exit codes in the build report.
2. `smart_meter_ingestion` and `smart_meter_peak_model` idle (`databricks jobs list-runs --job-id
   <id> --active-only -p dev` lists nothing); the three tables present.
3. `-k "ac66_before"` (snapshot).
4. AC-162: record the newest peak run id and `sha256sum out/evidence/ac66_rebuild_leg.json` (or
   "absent"); `-k "ac66_rebuild_leg"` (expected to fail, refused); record both again.
5. AC-163: `-k "ac66_rerun_leg"` (1 run, passes); `-k "ac66_verdict"` (expected to fail, names the
   rebuild leg only); copy both records.
6. U-06 (user): `python scripts/reset_peak_model_outputs.py`, then `--confirm`; the output (three
   DROP lines) goes into the build report.
7. AC-164: record the newest peak run id and the rerun file's `sha256sum`; `-k "ac66_rerun_leg"`
   (expected to fail, refused naming the three missing tables); record both again;
   `-k "ac66_rebuild_leg"` (1 run, passes); `-k "ac66_verdict"` (passes). Copy the three records
   and both run ids. The full sequence starts 2 job runs (NFR-44).

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-154 | Unit | `tests/test_ac66_rules.py::test_ac154_both_legs_on_the_current_snapshot_pass_deterministically` | `evaluate` twice on the AC-154 texts: `passed`, `problems == ()`, record keys equal `VERDICT_FIELDS`, `snapshot_saved_at_ms` 1000, `rerun_saved_at_ms` 2000, `rebuild_saved_at_ms` 3000, `verdict` `pass`; the two records byte-equal after `json.dumps(..., sort_keys=True)`; no value of the record or of `verdict_message` contains `https://`, `dapi` or `Bearer`, also when the fixtures' checksum texts and an extra unknown field hold such strings (G-52) |
| AC-154 | Unit | `tests/test_ac66_rules.py::test_ac154_rules_import_no_sdk_and_read_no_clock` | AST of `tests/support/ac66_rules.py`: no import of `databricks`, `time`, `os`, `pathlib`, `subprocess`, `datetime`; no call named `now`, `utcnow`, `time`, `open`, `sleep`; every call of `read_text`, `save` or `remove` is an attribute call on the injected `store` parameter of `run_leg`; the only project import is `smart_meter_peak_prediction.pipeline_guard` (NFR-45, FR-90) |
| AC-155 | Unit | `tests/test_ac66_rules.py::test_ac155_missing_evidence_names_each_missing_leg_or_the_snapshot` | Parametrized (a) to (d): (a) rebuild text None gives exactly one problem, subject `rebuild leg`, kind `missing`, text with `ac66_rebuild_leg.json` and `REBUILD_TEST`, no `rerun` in it and no `rerun leg` subject; (b) the mirror for the rerun leg with `RERUN_TEST` and no `rebuild` in it; (c) both subjects, both `missing`; (d) snapshot None gives exactly one problem, subject `snapshot`, text with `test_ac66_before_rebuild_snapshot`, record `snapshot_saved_at_ms` null. Every result `fail` |
| AC-156 | Unit | `tests/test_ac66_rules.py::test_ac156_stale_out_of_order_failed_inconsistent_or_malformed_legs_fail` | Parametrized (a) to (j) of the DEFINE, each one change to the AC-154 texts; expected `(subject, kind)` lists: (a) rerun stale; (b) rebuild stale (and no order problem, G-50); (c) rerun out of order; (d) rebuild failed; (e) rerun inconsistent, text names `features`; (f) rebuild inconsistent, names `silver_weather`; (g) rebuild inconsistent, `checksum differs`; (h) rerun unreadable; (i) rebuild malformed, `rebuild_saved_at_ms` null; (j) rerun malformed. The problems equal the expected list exactly, each text names its file, no call raises, no `internal error` |
| AC-156 | Unit | `tests/test_ac66_rules.py::test_ac156_odd_inputs_never_raise` | Parametrized odd inputs for each of the three texts: `""`, `"null"`, `"[]"`, `"1"`, deep nesting (10,000 `[`), `true` for each int field, strings for ints, lists for objects, a missing table key, NaN, a 400-digit int, unknown `leg` and `outcome` values. `evaluate` and `precondition` return without raising, verdict `fail` where the input is wrong, never `internal error` (G-51) |
| AC-157 | Unit | `tests/test_ac66_rules.py::test_ac157_precondition_over_all_table_states` | All 8 existence states x snapshot present or absent x both legs (32 cases): allowed only for rerun with all present and the snapshot, and rebuild with none present and the snapshot; every refusal message names the leg, every table in the wrong state by its shown name, the snapshot when absent, and its next step (G-46: the rebuild-leg selector, the reset command, the snapshot test or a full run of `smart_meter_peak_model`); the six partial states refuse both legs; an unknown leg and a non-boolean value refuse without raising |
| AC-158 | Unit | `tests/test_ac66_rules.py::test_ac158_leg_passes_and_writes_the_full_record` | Both legs, (a): real `Evidence(folder=tmp_path)` with the snapshot and an earlier `passed` record of the leg; fake runner returning the expected merges, `run_id` 42 and epoch-ms times; fake state equal to the snapshot. `run_leg` returns; the file's keys equal `RECORD_FIELDS` plus `saved_at_ms`; `outcome` `passed`, `snapshot_saved_at_ms` 1000, `run_id` 42, `started_ts` and `ended_ts` fully match the NFR-43 pattern; runner called once; preflight called once before the runner |
| AC-158 | Unit | `tests/test_ac66_rules.py::test_ac158_leg_failure_leaves_no_passed_record` | Both legs, an earlier `passed` record present: (b) rerun `inserted` 1, rebuild `inserted` 0 on one table; (c) the runner raises `AssertionError` (as `PeakRunner.run` on a failed run) and, separately, a `BaseException` subclass (as `pytest.fail`). Each raises the original exception; afterwards the leg file exists with `outcome` `failed` (merges and after as known, `run_id` null in (c)) and no file with `outcome` `passed` exists for that leg |
| AC-158 | Unit | `tests/test_ac66_rules.py::test_ac158_wrong_state_refuses_before_the_runner` | Both legs, (d): rerun with no table present, rebuild with all present, each leg in one partial state, and each leg without the snapshot. `AssertionError` starting `AC-66 <leg> leg refused before any job run`; runner, state and preflight called 0 times; the earlier record's bytes and the folder listing equal to before |
| AC-158 | Unit | `tests/test_ac66_rules.py::test_ac158_unsaved_failed_record_does_not_mask_the_failure` | A store whose `save` raises `OSError`: the leg's original exception propagates, `report` received exactly one line naming `OSError` and no message text (G-47); the old record was removed before the run |
| AC-159 | Unit | `tests/test_ac66_legs_docs.py::test_ac159_four_ac66_tests_are_collected_and_none_chooses_by_state` | AST of `tests/integration/test_peak_data.py`: the `test_ac66_` functions are exactly `SNAPSHOT_TEST`, `RERUN_TEST`, `REBUILD_TEST`, `VERDICT_TEST`, each matching `^test_ac(\d{2,3})_`; `test_ac66_after_rerun_and_rebuild_checksums_equal` absent; `_table_exists` is called only in `_tables_present`, whose body is one `return` of a dict comprehension; `_tables_present` occurs only inside a `lambda` passed as `exists=` to `ac66_rules.run_leg`; each `run_leg` call has a constant `leg=` (`"rerun"` in `RERUN_TEST`, `"rebuild"` in `REBUILD_TEST`, one call each); the verdict test's only parameter is `evidence` and it calls neither `run_leg` nor a runner; in `ac66_rules`, `check_leg` and `expected_merges` have no parameter or name `present` or `exists`. Collection with `-m integration -o addopts= tests/integration/test_peak_data.py` lists the four names |
| AC-159 | Unit | `tests/test_integration_layout.py` (updated, all five tests) | The shipped layout tests pass with the new names: marker, `AC_NAME`, `EXPECTED_ACS` (66 covered), and the collection assertions for `::test_ac66_rerun_leg_`, `::test_ac66_rebuild_leg_`, `::test_ac66_verdict_` (NFR-47) |
| AC-160 | Unit | `tests/test_ac66_legs_docs.py::test_ac160_runbook_docstring_and_script_state_the_order` | In runbook section 8 and in the module docstring of `test_peak_data.py`, the first occurrences of `ac66_before`, `ac66_rerun_leg`, `reset_peak_model_outputs.py --confirm`, `ac66_rebuild_leg`, `ac66_verdict` are in this order; sections 8 and 9 contain neither "then the daily job" nor "run the daily job" (case-insensitive), section 9 contains no "optional" and no section-8 line with `ac66` or `reset` contains it; section 9 contains `ac66_rebuild_leg`, `ac66_verdict` and the four task names; in the reset script, the usage line with `--confirm` does not contain "daily job" and the string constants of `main` hold exactly one `-k` selector, `ac66_rebuild_leg` |
| AC-160 | Unit | `tests/test_ac66_legs_docs.py::test_ac160_every_ac66_selector_selects_exactly_one_test` | Every distinct `-k` selector containing `ac66` in sections 8 and 9, the module docstring and the script's `main` strings is collected with `-m integration -o addopts= tests/integration/test_peak_data.py -k <selector>`: exactly one node id, and the four selectors together select the four AC-66 names; `-k ac66_after` selects none |
| AC-161 | Unit | `tests/test_ac66_legs_docs.py::test_ac161_production_files_and_reset_guards_equal_v060` | Aggregate SHA-256 over sorted `path NUL sha256 LF` lines of the files under `src/`, `resources/`, `notebooks/`, `databricks.yml`, plus `tests/test_peak_reset_script.py`, `.claude/sdd/archive/PEAK_MODEL/DEFINE_PEAK_MODEL.md` and `DESIGN_PEAK_MODEL.md`, equals `V060_TREE_SHA256`; with the tag present, the path set equals `git ls-tree` of `v0.6.0` and each file equals `git show v0.6.0:<path>`. In the reset script, `ast.unparse` of `ROOT`, `SNAPSHOT`, `EXPECTED_ROWS`, `ResetRefused`, `Target`, `targets`, `plan`, `Warehouse`, and of `main` with every string constant replaced by `""`, hashes to `V060_RESET_SHA256` and equals the tag's version when present |
| AC-161 | Unit | `tests/test_ac66_legs_docs.py::test_ac161_snapshot_test_and_its_helpers_are_kept` | `ast.unparse` of `test_ac66_before_rebuild_snapshot`, `_state`, `_table_exists`, `SNAPSHOT_TABLES` and `DATA_TASKS` in `test_peak_data.py` hashes to `V060_KEPT_AST_SHA256` and equals the tag's version when present (FR-91); `ac66_rules.SNAPSHOT_NAME` equals the stem of the reset script's `SNAPSHOT` path |
| AC-161 | Unit | `tests/test_ac66_legs_docs.py::test_ac161_specs_are_clean` and the full `pytest` run | `check_specs.run(ROOT).errors == []`; the build report records `pytest` (no marker) with 0 failures and `python scripts/check_specs.py` with 0 errors (NFR-47) |
| AC-162 | Integration | `tests/integration/test_peak_data.py::test_ac66_rebuild_leg_ac162_ac164_inserts_the_snapshot_rows_and_checksums_equal`, live plan step 4 | With the three tables present right after the snapshot, the test fails with `AC-66 rebuild leg refused before any job run`, naming the three present tables and `reset_peak_model_outputs.py`; the newest peak run id and the leg file's `sha256sum` (or "absent") are equal before and after (DA-47), recorded in the BUILD_REPORT |
| AC-162 | Manual (operator) | Live plan step 4, BUILD_REPORT AC-162 row | The two reads of `databricks jobs list-runs --job-id <peak job id> -p dev` and `sha256sum`, before and after |
| AC-163 | Integration | `tests/integration/test_peak_data.py::test_ac66_rerun_leg_ac163_ac164_merges_nothing_and_checksums_equal`, then `::test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot`, live plan step 5 | The rerun leg passes (MERGE 0 / 0 / 0 for the three keys, counts and checksums equal) and its record has `outcome` `passed` and `snapshot_saved_at_ms` equal to the snapshot's; the verdict fails, its message and `ac66_verdict.json` `problems` hold one `rebuild leg: missing` (or `stale`) entry and no `rerun leg` entry (PEAK_MODEL F-15 DC-01, first half). Both records copied into the BUILD_REPORT |
| AC-164 | Manual (user, U-06) | Live plan step 6 | The user runs the reset dry run, then `--confirm`; its three DROP lines go into the BUILD_REPORT. The agent never runs `--confirm` (C-23) |
| AC-164 | Integration | `tests/integration/test_peak_data.py::test_ac66_rerun_leg_ac163_ac164_merges_nothing_and_checksums_equal`, then `::test_ac66_rebuild_leg_ac162_ac164_inserts_the_snapshot_rows_and_checksums_equal`, then `::test_ac66_verdict_ac163_ac164_both_legs_passed_against_the_current_snapshot`, live plan step 7 | The rerun leg refuses naming the three missing tables, with the newest peak run id and `ac66_rerun_leg.json` bytes unchanged; the rebuild leg passes (inserted 21,165 / 36,480 / 36,480, 0 updated, 0 deleted, counts and checksums equal); the verdict passes with empty `problems` and `snapshot_saved_at_ms` < `rerun_saved_at_ms` < `rebuild_saved_at_ms` (PEAK_MODEL F-15 DC-01, second half). The three records and both run ids copied into the BUILD_REPORT |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | Nothing deployable changes. For the live gate, `databricks bundle validate -t dev -p dev` and `databricks bundle deploy -t dev -p dev` from a clean tree of the build branch, exit codes in the build report |
| Scheduling and retries | Schedules, retries and timeouts of `smart_meter_peak_model` and `smart_meter_ingestion` unchanged. The live tests are user-run; a refused leg is rerun only after the state is fixed (G-46 next steps) |
| Monitoring and alerting | Unchanged for the jobs. For the evidence: the four files under `out/evidence/`, the refusal and failure messages, and the BUILD_REPORT rows |
| Secrets | None added. Records and messages hold ids, counts, checksums, field names and UTC times only (G-52); credentials stay with the CLI profile; `out/` stays git-ignored. Unit tests build fake secret strings by concatenation |
| Cost | Each leg that passes its precondition starts 1 job run of the four data tasks (as the shipped test per mode); a refused leg starts 0 runs and reads `information_schema.tables` 3 times; the verdict starts 0 runs and 0 SQL statements. Full sequence: 2 job runs (NFR-44). Unit tests add a few `pytest --collect-only` subprocesses (about 5) to CI |
| Backfill / reprocessing | The rebuild leg is the reprocessing proof (PEAK_MODEL NFR-17). A partial state after a failed rebuild leg is restored by a full run of `smart_meter_peak_model`, then a new snapshot and the full sequence (runbook section 9). Lost evidence files cannot be rebuilt; the BUILD_REPORT is the durable record (C-25) |

---

## Assumption dependencies

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| DA-40 **Validated by prior art.** `from support import ...` works from `tests/` and `tests/integration/` (rootdir `tests/conftest.py`, prepend import mode; `test_ingestion_guard_live.py` imports `support.ac97_timing`) | OD-42 | The shipped collection test collects `test_peak_data.py` in CI | Load the module by path with `importlib` |
| DA-44 Loading `tests/integration/conftest.py` by path in a unit test needs only `pytest`, `yaml` and the SDK-free library | AC-158 | First run of `tests/test_ac66_rules.py` in CI | A fake store with the same `save` format in the unit test, and one AST check that `Evidence.save` is unchanged apart from `self.folder` |
| A-51 (DEFINE) `information_schema.tables` reflects the drop and the rebuild without lag | G-46, AC-162, AC-164 | Live plan steps 4 and 7 | A wrong refusal is safe (no run); wait and rerun the leg |
| DA-47 `databricks jobs list-runs --job-id <id> -p dev` lists the newest run first | AC-162, AC-164 | Once at build, against the Jobs UI | The run list of the job in the Jobs UI |
| A-49 (DEFINE) The local clock does not step back between the four steps | G-50 | The verdict record shows the three `saved_at_ms` | A step back fails the verdict (safe direction); rerun the sequence |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| A failed rebuild leg leaves `dev` without some tables (partial state), which both legs refuse | Scoring on `dev` blocked; AC-164 needs another snapshot, rerun leg, reset and rebuild leg | Runbook section 9 recovery (full run of `smart_meter_peak_model`); the failed record and the message show which tables exist; A-52 validated once live |
| Changing `tests/integration/conftest.py` (`Evidence`) | A mistake would break every snapshot pair | Default folder keeps the shipped path; `save` and `load` keep format and messages; AC-158 runs the real class in CI |
| The verdict trusts local files | A forged record passes | Out of scope (DEFINE Self-Review); cross-checks catch inconsistent records (G-49) |
| Trade-off: `failed` record plus removal | Two writes per failing leg, one more code path | One handler, unit-tested for both runner failures and for a failing save (AC-158) |
| Trade-off: the order problem is attributed to the rerun leg | A rebuild-then-rerun sequence is reported on the rerun leg | Its next step says to restart from the snapshot, which is the only fix (D-95) |
| Trade-off: `EXPECTED_ACS` not extended to 162 to 164 | The layout test does not prove the live ACs by number | The AC ids are in the test names after `test_ac66_`; AC-159 checks the four exact names |
| Subprocess collections in CI | A few seconds more per CI run | Bounded to the distinct AC-66 selectors (4) plus `ac66_after` |

---

## Open Items for the User

| ID | Item | When |
|---|---|---|
| U-06 | Run `python scripts/reset_peak_model_outputs.py` (dry run), then with `--confirm`, between live plan steps 5 and 7, and paste its output for the BUILD_REPORT. Agents never run `--confirm` (C-23) | Live gate of PR 1, before `/ship` (Q-33) |

No design question is open: OD-41 to OD-45 are resolved by DA-39 to DA-43; OD-44 keeps the reset
guards unchanged, so no user OK on a guard change is needed.

---

## Self-Review

- **Weak points:**
  - The failure paths of the legs (FR-87) are proven with fakes, not live; a live failure cannot be
    forced on `dev` without damaging the tables.
  - "0 new job runs" in AC-162 and AC-164 is read by the operator from the CLI, not asserted by the
    test; AC-158 (d) carries the proof that no runner call is made.
  - The verdict reads local files and can be fooled by a hand-made record that agrees with the
    snapshot; this is accepted in the DEFINE.
  - The AC-159 AST rules check the shape of today's code (lambda passed as `exists=`); a
    legitimate refactor of the live tests will need the test to change too.
- **Risks:**
  - The live gate leaves `dev` without the feature and label tables between the reset and a
    passing rebuild leg (C-23); a failing rebuild leg also leaves a partial state that blocks both
    legs until a full job run.
  - The golden constants of AC-161 must be computed from tag `v0.6.0` at build; a hand-typed value
    would make the test meaningless in CI.
  - Editing the shared `Evidence` class touches every before/after pair; a regression would show
    only in live runs if AC-158 did not use the real class.
- **Trade-offs:** Three tests and a user step instead of one test cost the operator four more
  commands, in exchange for an AC that cannot be green on one leg and refusals that cost no run.
  Rules under `tests/` keep production byte-equal but cannot be reused by production code. A
  `failed` record adds a code path but leaves evidence of every started leg.
- **What I would do differently (with more budget or time):** Make the leg tests also read the job
  run list before and after a refusal and record the newest run id in the refusal message, so that
  AC-162 and AC-164 assert "0 new runs" themselves instead of relying on the operator's CLI reads.
  It costs two Jobs API reads per leg and a fake in AC-158; I left it out to keep the leg's
  side effects to the ones the DEFINE names.
- **Next improvement:** Build entries 1 to 3 first and make AC-154 to AC-158 green in CI, then
  entries 4 and 5 in one commit and run `tests/test_integration_layout.py` before touching the
  script, runbook and docs tests.

---

## Next Step

`/build .claude/sdd/features/DESIGN_AC66_BOTH_LEGS.md`

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-11-09 | Created from DEFINE_AC66_BOTH_LEGS.md (Ready for Design, Q-32 to Q-34 answered): OD-41 to OD-45 resolved (DA-39 to DA-43), DA-44 to DA-48, guards G-46 to G-53, rule API, live test outline, text changes, 11-entry manifest (8 in one build PR, 3 at ship), test strategy for AC-154 to AC-164, live plan with U-06; no ADR. Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts at entry 1 |
