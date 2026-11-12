# DESIGN: Reset Guard

> Phase 2. How the requirements will be met, file by file.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | RESET_GUARD |
| **Date** | 2026-11-12 |
| **Author** | Christian |
| **Source** | DEFINE_RESET_GUARD.md (Ready for Design, 14/15; Q-40 to Q-43 answered by the user on 2026-11-12 with the recommended answers); follow-up `.claude/sdd/follow-ups/F_PEAK_MODEL_03.md` (PEAK_MODEL F-03 with PEAK_MODEL_CONCURRENCY F-02, DC-01 to DC-03); precedents `.claude/sdd/archive/AC66_ZERO_NEW_RUNS/DESIGN_AC66_ZERO_NEW_RUNS.md` and `.claude/sdd/archive/PEAK_MODEL_CONCURRENCY/DESIGN_PEAK_MODEL_CONCURRENCY.md`; ADR 0012 and ADR 0013; code read on branch `spec/reset-guard` (`d30d377`, equal to main `de5535a` outside `.claude/sdd/`) on 2026-11-12: `scripts/reset_peak_model_outputs.py`, `src/smart_meter_peak_prediction/pipeline_guard.py`, `src/smart_meter_peak_prediction/__init__.py`, `src/smart_meter_peak_prediction/config.py`, `pyproject.toml`, `databricks.yml`, `tests/test_peak_reset_script.py`, `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py` (AC-92 additions-only diff against `v0.3.0`, peak-mode goldens), `tests/test_ac66_legs_docs.py` (AC66_BOTH_LEGS AC-161 and AC66_ZERO_NEW_RUNS AC-171 pins of `src/` and of the reset script), `tests/test_ac97_timing_docs.py` (AC97_TIMING_EVIDENCE AC-105 pin of `src/` and of version 0.4.1), `tests/test_peak_concurrency_docs.py`, `tests/test_ingestion_guard_docs.py`, `tests/test_secrets_hygiene.py`, `tests/integration/conftest.py` (`_job_named`, `peak_job`, `training_job`, `PeakRunner.assert_ingestion_idle`), `docs/runbooks/peak_model.md` ("Concurrency with the ingestion job", sections 8 and 9), `.claude/kb/databricks/bundles.md` and `free-edition.md`, `scripts/check_specs.py`; Jobs API reference "List jobs" (`limit` 1 to 100, default 20; `name` is an exact, case-insensitive match) |
| **Status** | Ready for Build |

Allowed status values: `Draft`, `Ready for Build`.

**ID numbering.** Design decisions continue after AC66_ZERO_NEW_RUNS DA-59: DA-60 to DA-72. Guards
continue after AC66_ZERO_NEW_RUNS G-58: G-59 to G-66. User items continue after AC66_ZERO_NEW_RUNS
U-08: U-09. Checked on 2026-11-12 with a search of `.claude/sdd/` (archive and follow-ups included)
for `DA-6`, `DA-7`, `G-59` to `G-69`, `U-09` and any three-digit `DA-`, `G-` or `U-` id: the only
hits are the range text "DA-49 to DA-69", "G-54 to G-69" and "U-07 to U-09" of the AC66_ZERO_NEW_RUNS
DESIGN, which defines none of them. The ADR is 0014 (highest existing: 0013). FR, NFR, AC, C, A, D, Q
and OD ids are those of the DEFINE; no new open design question remains. Every ID of another spec
carries that spec's name; unprefixed IDs are this feature's own.

---

## Overview

`pipeline_guard` gains a job-only mode, appended to the module without changing a shipped line:
`check_jobs(client, names)` finds each job by base name in one page of `jobs.list` (development
prefix stripped, exactly one match, page not full) and then applies the shipped identity, uniqueness
and active-run reads through `_read_named_job`, a copy of `_read_job` whose expected name is a
parameter and whose equivalence with `_read_job` is a unit test. `scripts/reset_peak_model_outputs.py`
builds one workspace client through an injectable factory (with `pipeline_guard.CLIENT_LIMITS`),
moves every set-up step inside the refusal handling, runs the checks in the order time zone, row
counts, idle check (last read before the first DROP, also in the dry run), and prints every refusal
as one line `refused, nothing dropped: ...` with exit code 2. A failed DROP stops the drops and exits
1 with one line naming what was dropped. The `main()` paths are unit-tested on fakes without the SDK;
the live evidence is one user-run dry run on `dev`. Three shipped pins that would block any change to
`src/` or to the reset script are narrowed to the parts this feature does not change (DA-68). Release
v0.8.0, package version 0.8.0 (Q-43).

---

## Architecture

```text
 LOCAL (user, C-31): python scripts/reset_peak_model_outputs.py [--confirm] [...]     DATABRICKS (dev)

 main(argv, *, client_factory=build_client, snapshot_exists=None)
   0 parse args (option set fixed, FR-110); settings from SMART_METER_<FIELD>
   1 client = client_factory()          -- WorkspaceClient(config=Config(profile, 60 s, 30 s))
       raises -> "refused, nothing dropped: workspace client: ..."            exit 2  [G-62]
   2 Warehouse(client)                  -- warehouses.list (unless DATABRICKS_WAREHOUSE_ID) --> SQL
       raises / none -> "refused, nothing dropped: warehouse lookup: ..."      exit 2
   3 SELECT current_timezone()          -- Statement Execution (wait 20 s) -----------------> SQL
       fails -> "... time-zone query: ..."; not UTC -> "... time zone is <z>, expected UTC"  exit 2
   4 plan(settings, warehouse.count)    -- 4 SELECT count(*) (shipped plan(), unchanged) ---> SQL
       ResetRefused / error -> problem kept, step 5 still runs
   5 pipeline_guard.check_jobs(client, (smart_meter_peak_model,                    [G-59..G-61]
                                        smart_meter_peak_model_training))
       per job: jobs.list(limit=100) -> one base-name match ------------------------> Jobs API
                jobs.get(job_id) -> the id names the job
                jobs.list(name=<deployed name>) -> unique
                jobs.list_runs(job_id, active_only=True), at most 25 -> no active run
       busy / unreadable -> problem kept
   6 any problem -> ONE line "refused, nothing dropped: <plan>; idle check: <items>; action: ..."
                    exit 2, no statement other than SELECT was sent                 [G-62, G-63]
   7 print idle lines (one per job, "0 active runs"), then "would DROP ..." or "DROP  ..." lines
   8 dry run -> "dry run: pass --confirm ..."                                       exit 0
   9 --confirm -> DROP TABLE x3 in plan order ---------------------------------------> SQL
       a DROP fails -> ONE line "drop phase failed: dropped: ...; failed: ...; ..."  exit 1 [G-64]
       all done -> shipped "done. Next (rebuild leg) ..." lines                      exit 0

 src/smart_meter_peak_prediction/pipeline_guard.py (no SDK import, additions only):
   TRAINING_JOB, JOB_READ_CALLS, MAX_JOBS_LISTED, redact, describe_error,
   JobStatus, JobsReport, check_jobs, _find_job_id, _read_named_job (= _read_job, name as parameter)

 CI (pytest, no marker, no SDK): tests/test_reset_guard.py (main on fakes),
   tests/test_reset_guard_library.py (job-only mode, parity, v0.7.3 compatibility),
   tests/test_reset_guard_docs.py (runbook and docstring), fakes in tests/support/reset_fakes.py
```

---

## Components

| Component | Responsibility | Technology | Requirements covered |
|---|---|---|---|
| Job-only mode (`pipeline_guard.py`, appended section) | `TRAINING_JOB`, `JOB_READ_CALLS`, `MAX_JOBS_LISTED`; `check_jobs` (lookup by base name, then the shipped identity, uniqueness and active-run rules); `JobStatus`, `JobsReport` with item and idle-line texts; public `redact` and `describe_error` (shipped `_describe_error` plus address redaction). No change to a shipped line, no new import, no SDK | Python 3.11 stdlib | FR-105, FR-106, FR-107 (item texts), FR-111, NFR-53 to NFR-55 |
| Reset script (`scripts/reset_peak_model_outputs.py`) | `build_client`, `build_parser`, `Warehouse(client)` without SDK imports, `StatementFailed`, `main(argv, *, client_factory, snapshot_exists)` with the stage order of G-62, the line shapes of DA-64 and the drop phase of G-64; module docstring (FR-114); `plan()`, `targets()`, `Target`, `EXPECTED_ROWS`, `SNAPSHOT`, `ResetRefused` unchanged | Python, `databricks-sdk` imported lazily in `build_client` only | FR-105 to FR-110, FR-112, FR-114, NFR-53, NFR-55, NFR-56 |
| Fakes (`tests/support/reset_fakes.py`) | Recording fake workspace client (`jobs`, `warehouses`, `statement_execution`), shared call log, forbidden-call recorder, state objects with and without `.value` | pytest support module | FR-113 |
| `main()` unit tests (`tests/test_reset_guard.py`) | AC-189 to AC-196, AC-198 to AC-200 on fakes | pytest, `capsys`, `monkeypatch` | FR-105 to FR-110, FR-112, FR-113, NFR-53 to NFR-56 |
| Library and compatibility tests (`tests/test_reset_guard_library.py`) | Job-only mode on fakes; parity of `_read_named_job` with `_read_job`; AC-197 against tag `v0.7.3` and golden constants; read budget of AC-200 at module level | pytest, `ast`, `git` when the tag exists | FR-111, FR-113, NFR-54, NFR-57 |
| Docs test (`tests/test_reset_guard_docs.py`) | AC-201 needles in runbook section 9, the "Training" bullet and the script docstring | pytest | FR-114 |
| Re-pinned shipped tests (`tests/test_ac97_timing_docs.py`, `tests/test_ac66_legs_docs.py`) | Narrow the AC97_TIMING_EVIDENCE AC-105, AC66_BOTH_LEGS AC-161 and AC66_ZERO_NEW_RUNS AC-171 pins to what RESET_GUARD does not change; same test names and `assert` counts (DA-68) | pytest | NFR-57 |
| Runbook (`docs/runbooks/peak_model.md`) | Section 9 paragraphs "Idle check" and "If the drop phase fails", dry-run comment, "Training" bullet | Markdown | FR-114 |
| ADR 0014 and the ADR 0012 note | Name lookup outside the bundle, failing closed; ADR 0012's rejection stands for the in-job check | Markdown | OD-51 |

---

## Data Model

No table, view, volume, contract file or evidence file is created or changed. The reset reads two
platform listings and drops the three tables as shipped.

| Object | Layer | Grain | Key | Partitioning / clustering | Notes |
|---|---|---|---|---|---|
| Jobs API job list (read, one page per job of the idle set) | platform metadata | One deployed job | `job_id`; `settings.name` with the development prefix stripped equals the base name | - | `jobs.list(limit=100)` read through `islice(..., 100)`, so no second page is requested (G-60). Only `job_id` and `settings.name` are used |
| Jobs API job (`jobs.get`) and same-name list (`jobs.list(name=...)`) | platform metadata | One job | `job_id` | - | Shipped G-14 reads (ADR 0012), here with the expected name as a parameter |
| Jobs API active runs (`jobs.list_runs(job_id=..., active_only=True)`) | platform metadata | One job run | `run_id`, scoped by `job_id` | - | At most `MAX_RUNS_READ` (25) runs; `state.life_cycle_state` by value text; `start_time` epoch ms shown by `utc_text` |
| `JobStatus`, `JobsReport` (in memory, `pipeline_guard`) | value | One job of the idle set; one check | base name | - | `JobStatus(name, job_id, runs, unreadable)`; `job_id` is `""` when no unique job was found. No time field, so two checks on the same inputs are equal (NFR-56) |
| The three tables (counted, dropped with `--confirm`) | silver, ml | As in the archived PEAK_MODEL DEFINE | As shipped | As shipped | Unchanged; DROP statements and their order come from the shipped `plan()` |
| Reset output and exit code | stdout | One reset run | - | - | Line shapes in DA-64; exit 0, 1 or 2 (D-108) |

### Data quality rules (guards)

There is no profiled data; the source column names the requirement or decision.

| Rule | Object | Action (`warn` / `drop` / `fail`) | Source finding |
|---|---|---|---|
| G-59 Idle rule: a job of the idle set is idle only when `_find_job_id` resolved exactly one id, `jobs.get` names the same base name, `jobs.list(name=<deployed name>)` lists exactly that one job, `jobs.list_runs` was read, and no listed run has a life-cycle state outside `pipeline_guard.TERMINAL_RUN_STATES`. A missing state is `UNKNOWN` and active, a future value is active, a listed terminal run is ignored (list race). Every run counts, whatever its trigger or task subset. Idleness never depends on a time | job reads | `fail` (refusal, exit 2) | FR-105, FR-106, NFR-55, D-107 |
| G-60 Lookup rule: one call `jobs.list(limit=MAX_JOBS_LISTED)` (100), at most 100 items taken with `islice`; a match is an item whose `settings.name`, development prefix stripped, equals the base name exactly. A raise, 100 items listed (page full), 0 matches, 2 or more matches, or a matching id that is not a positive integer is unreadable with read label `job list` | `_find_job_id` | `fail` | FR-106, A-57, DA-60 |
| G-61 Read budget: per job the calls are, in this order and at most once each, `jobs.list(limit=100)`, `jobs.get(job_id=...)`, `jobs.list(name=...)`, `jobs.list_runs(job_id=..., active_only=True)`; a failed step ends that job's reads. Only `JOB_READ_CALLS` are called, a subset of `READ_CALLS`; no sleep, no poll, no write call, no SQL | `check_jobs` | `fail` (AC-198, AC-200) | NFR-53, NFR-54 |
| G-62 Stage order of `main()`: settings, client, warehouse lookup, time-zone query, time-zone value, row counts (`plan`), idle check, report, then DROPs. The stages up to the time-zone value stop at their first failure with one refusal line; once the time zone passed, `plan` and the idle check both run once and their problems go into one line. No statement other than `SELECT` is sent before every check passed; the dry run never sends one | `main()` | `fail` | FR-108, FR-109, NFR-56, DA-62 |
| G-63 Output rule: every printed line goes through `_say`, which joins line breaks with a space and applies `pipeline_guard.redact` (tokens, `dapi...`, URLs, and any word holding `@` become `<redacted>`); error texts come from `pipeline_guard.describe_error` (class, API error code, first line, at most 200 characters) or the shipped `ResetRefused` text; times only as `utc_text` or `not started`; no clock time, host or URL is printed. A refusal is exactly one line that starts with `refused, nothing dropped: ` | output | `drop` (redacted text); `fail` in tests | FR-107, FR-108, NFR-53, NFR-55, NFR-56 |
| G-64 Drop phase: the DROP statements run in `plan()` order; the first failure stops the loop, prints one line naming the dropped tables (or `none`), the failed table with its error text and the tables not attempted, and returns 1. The line never contains `nothing dropped` | `main()` | `fail` | FR-112, D-108 |
| G-65 Additions only: against tag `v0.3.0` (shipped INGESTION_GUARD AC-92) and tag `v0.7.3` (AC-197), the diff of `pipeline_guard.py` holds only `equal` and `insert` blocks; the peak and pipeline-only modes give byte-equal `message()` and `exit_value()`; `READ_CALLS` and `PIPELINE_READ_CALLS` are unchanged | `pipeline_guard.py` | `fail` | FR-111, NFR-57 |
| G-66 Pin scope: the three re-pinned shipped tests exclude exactly `src/smart_meter_peak_prediction/pipeline_guard.py`, accept any release version line in `src/smart_meter_peak_prediction/__init__.py` (and in `pyproject.toml`, at least 0.4.1), and digest only the reset script parts RESET_GUARD keeps (`ROOT`, `SNAPSHOT`, `EXPECTED_ROWS`, `ResetRefused`, `Target`, `targets`, `plan`); everything else they pin is pinned as before. Their constants are recomputed from the tags with their own functions | shipped pins | `fail` | NFR-57, DA-68 |

### Resolution of the open design items

| ID | Decision | Rationale |
|---|---|---|
| OD-51 | **DA-60.** The ids come from a lookup by base name: per job one `jobs.list(limit=100)` page, development prefix stripped, exactly one match and fewer than 100 jobs listed (G-60); then the shipped identity and uniqueness reads. `databricks bundle summary`, environment variables, flags (excluded by FR-110) and `current_user.me` (outside NFR-53) are rejected. A new ADR, **0014** (Proposed), records the decision, and a dated note on ADR 0012 points to it; ADR 0012's decision is unchanged | ADR 0012 rejected name lookup for an unattended in-job check that has a bundle reference. The reset has no bundle reference, is run and read by a person, and every failure mode of the lookup (none, two, renamed, prefix changed, more than one page) refuses with a named cause; the dry run prints the resolved ids (AC-202). The lookup outlives the feature: it is how a local script identifies bundle jobs, and the job-only mode is reusable. A note on ADR 0012 alone would hide that the rejected option is now used in another context, so an ADR is needed (follow-up triage E3 `Unknown` resolves to "new ADR") |
| OD-52 | **DA-61.** The change to `pipeline_guard.py` is a section appended after the pipeline-only mode plus one paragraph inserted into the module docstring; no shipped line changes and no import is added. `_read_job` stays as shipped; `_read_named_job(client, job_id, name, subject, runs, unreadable)` is the same body with `INGESTION_JOB` replaced by `name`, and `test_ac197_job_reader_matches_the_shipped_reader` proves that both return the same value, the same runs, the same unreadable items and the same calls for `name=INGESTION_JOB` over every shipped case. New public names: `TRAINING_JOB`, `JOB_READ_CALLS`, `MAX_JOBS_LISTED`, `redact`, `describe_error`, `JobStatus`, `JobsReport`, `check_jobs`. `READ_CALLS`, `PIPELINE_READ_CALLS` and every shipped signature stay | The shipped INGESTION_GUARD test `test_ac92_guard_module_changes_are_additions_only` fails on any changed line against `v0.3.0` (the tag exists locally), and an import change would be a changed line plus an isort error. Replacing the body of `_read_job` by a call is therefore impossible without editing a shipped guard test. A parity test turns the copy into one tested rule: the state rule itself (`TERMINAL_RUN_STATES`, `_enum_text`, `utc_text`, `strip_dev_prefix`, `_describe_error`) is shared, not copied |
| OD-53 | **DA-62.** Order: settings, client, warehouse lookup, time-zone query and value, row counts, idle check, then the report and the DROPs. The idle check is the last read before the first DROP, so the window of D-109 is the time to print at most six lines; no second idle check. The set-up stages stop at the first failure; after the time zone passed, both state checks run and their problems are reported together in one line (G-62) | Placing the check last makes a second check unnecessary: any run that started during the count queries is seen. A re-check would double the reads beyond NFR-54. Running the idle check also when `plan()` refuses names the real cause when a running job is what changed the counts (a refusal "has N rows, expected M" alone would mislead). The set-up stages stop early because nothing after them can be read, and AC-192 requires one line and no count query |
| OD-54 | **DA-63.** `main(argv=None, *, client_factory=build_client, snapshot_exists=None)`: keyword-only injection, defaults for the user. `build_client()` imports `databricks.sdk` lazily and returns `WorkspaceClient(config=Config(**CLIENT_LIMITS, profile=<DATABRICKS_CONFIG_PROFILE>))` (profile only when set). One client serves the warehouse and the Jobs reads. `Warehouse(client)` takes it, compares statement states by value text (no SDK import), and waits at most 20 s per HTTP call (`wait_timeout="20s"`, below the 30 s HTTP limit), polling as shipped with the shipped 600 s deadline and cancel. `snapshot_exists` defaults to `SNAPSHOT.is_file`. Tests replace `time.sleep` through `monkeypatch` on the module | Parameters are explicit and need no module patching; `monkeypatch` of `SNAPSHOT` is not usable because `plan()` prints `SNAPSHOT.relative_to(ROOT)`. One client means one authentication and the shipped limits for every call (DEFINE Self-Review risk). The 50 s statement wait of v0.7.3 would exceed the 30 s HTTP limit; 20 s is within the Statement Execution range (0 or 5 to 50 s) and leaves the poll loop unchanged |
| OD-55 | **DA-64.** Every refusal is exactly one line (table *Line shapes*); the idle line is `idle check: job <name> (job id <id>): 0 active runs`, one per job, printed only when every check passed | One line satisfies FR-107 (prefix on the first line) and FR-108 (exactly one line) with one rule, keeps the shipped `plan()` refusal byte-equal after the prefix, and can be copied into the BUILD_REPORT whole. Items are separated by `; ` as the shipped `plan()` problems are |

### Further design decisions

| ID | Decision | Rationale |
|---|---|---|
| DA-65 | Drop phase (G-64): before the loop the shipped `DROP  <statement>` lines are printed; a DROP that raises (`StatementFailed`, `ResetRefused` on time-out, any `Exception`) stops the loop and prints the drop-failure line; exit 1. `BaseException` (Ctrl-C) propagates | D-108 keeps exit 2 for "nothing dropped". The shipped lines announce the statements before they run, so the failure line names only the outcome |
| DA-66 | `StatementFailed(ResetRefused)` carries the raw server text in `detail` and shows `SQL failed: <redacted first line, at most 200 characters>`. `Warehouse.count` maps a `StatementFailed` whose `detail` holds `TABLE_OR_VIEW_NOT_FOUND` or `cannot be found` to `None` (missing table), as shipped; every other failure propagates | The missing-table rule of `plan()` keeps working on the raw text while the printed text is redacted (NFR-53) |
| DA-67 | New test files instead of extending shipped ones: `tests/test_pipeline_guard.py` is byte-pinned to `v0.3.0` (INGESTION_GUARD AC-92), and `tests/test_peak_reset_script.py` is part of the AC66_BOTH_LEGS AC-161 tree pin; both stay byte-equal. FR-113's "next to the three shipped `plan()` tests" is met by a sibling file in `tests/` | No shipped pin needs widening for the tests themselves; the three `plan()` tests keep every assertion |
| DA-68 | Three shipped pins are narrowed, each keeping its test name and `assert` count (G-66): (R1) `tests/test_ac97_timing_docs.py::test_ac105_production_files_equal_v040_except_the_version` excludes `pipeline_guard.py` from its tree and accepts the release version (pyproject version, at least 0.4.1, equal to the one `__version__` line); (R2) `tests/test_ac66_legs_docs.py::test_ac161_production_files_and_reset_guards_equal_v060` excludes `pipeline_guard.py` and `__init__.py` from its tree, and `reset_digest` digests only the reset parts RESET_GUARD keeps; (R3) `::test_ac171_rule_constants_and_reset_script_equal_v070` compares that `reset_digest` instead of the bytes. Constants `V040_TREE_SHA256`, `V060_TREE_SHA256`, `V060_RESET_SHA256` and `V070_RESET_SHA256` are recomputed at build from the tags with the files' own functions | These tests fence "this earlier feature changed no production file or reset guard". The DEFINE allows exactly the changes that break them (C-30: `pipeline_guard.py` and the version; FR-108: the reset `main()`), and NFR-57 requires 0 failures. Narrowing keeps every other pinned byte pinned; the parts RESET_GUARD changes are pinned anew by AC-197 (behaviour) and G-65 (additions only). Precedent: INGESTION_GUARD moved the ingestion-job pin out of `tests/test_peak_bundle.py` (INGESTION_GUARD D-53) |
| DA-69 | AC-197 goldens: `V073_ASSERT_COUNTS` (three files), `V073_MODES_SHA256` (SHA-256 of `json.dumps(outputs, sort_keys=True)` over the fixed inputs of both shipped modes, run on the module loaded from `git show v0.7.3:...`) and `V073_BUNDLE_SHA256` (tree digest of `resources/`, `notebooks/`, `pipelines/`, `databricks.yml`) are computed at build from tag `v0.7.3` with the test file's own functions, never typed by hand; the tag comparisons run when the tag exists | Same mechanism as AC66_ZERO_NEW_RUNS DA-57: CI checks out one commit without tags and keeps a real check |
| DA-70 | Version 0.8.0 (`pyproject.toml`, `__init__.py`) lands in the build PR, in the same commit as R1, so the build PR's CI already runs the version-agnostic pin on the final version. The ship PR adds the CHANGELOG entry and closes the follow-up | Q-43; R1 and the bump depend on each other. The tag `v0.8.0` is cut on the ship merge commit (precedent v0.7.x) |
| DA-71 | `pipeline_guard.redact` extends the shipped `_REDACT` with any word holding `@`, because an API error can name a user's address and NFR-53 forbids `@` in the output; the shipped `_describe_error` is unchanged, so the shipped messages stay byte-equal | Additions only (G-65); the reset is the only caller of the extended redaction |
| DA-72 | `IDLE_SET = (pipeline_guard.PEAK_JOB, pipeline_guard.TRAINING_JOB)` lives in the reset script; which jobs must be idle is the reset's rule (D-104), how a job is read is the guard's (D-107) | A later caller of `check_jobs` passes its own names |

### Line shapes (DA-64, DA-65)

`<name>` is a base name of the idle set; `<id>` is the resolved job id or `not resolved`; `<err>` is
`pipeline_guard.describe_error` of the exception, or the shipped `ResetRefused` text; `<plan>` is the
shipped `plan()` refusal text, unchanged. Every line passes `_say` (G-63).

| Case | Line (one line each) |
|---|---|
| Settings invalid | `refused, nothing dropped: settings: <err>` |
| Client factory raises (also a missing `databricks-sdk`) | `refused, nothing dropped: workspace client: <err>; not read: the SQL warehouse, job smart_meter_peak_model, job smart_meter_peak_model_training` |
| Warehouse lookup fails | `refused, nothing dropped: warehouse lookup: no SQL warehouse found; set DATABRICKS_WAREHOUSE_ID` or `refused, nothing dropped: warehouse lookup: <err>` |
| Time-zone query fails | `refused, nothing dropped: time-zone query: SQL failed: <message>` (or `SQL statement timed out`, or `<err>`) |
| Time zone not UTC | `refused, nothing dropped: the warehouse session time zone is <zone>, expected UTC` |
| `plan()` refuses, jobs idle | `refused, nothing dropped: <plan>` (byte-equal to v0.7.3) |
| Count query fails with another error | `refused, nothing dropped: row counts: <err>` |
| Idle check refuses | `refused, nothing dropped: idle check: <items>; action: <action>` |
| Both | `refused, nothing dropped: <plan>; idle check: <items>; action: <action>` |
| Busy item | `job <name> (job id <id>): active run <run_id>, state <STATE or UNKNOWN>, started <YYYY-MM-DDTHH:MM:SSZ or not started>` |
| Unreadable item | `job <name> (job id <id>): <read>: <cause>` with `<read>` one of `job list`, `job`, `job name list`, `active runs` (shipped labels) |
| Lookup causes (`job list`) | `no deployed job named '<name>' (development prefix stripped)`; `'<name>' is not unique (job ids: <ids>)`; `100 jobs listed, the page is full: '<name>' cannot be shown to be unique`; `the job id '<value>' is not a positive integer`; or `<err>` |
| Idle check itself raises | `refused, nothing dropped: idle check: internal error: <err>; action: <fix action>` |
| Actions | busy only: `wait until the named run ends, then run the reset again`; unreadable only: `fix the named cause (deployment, permission or API availability), then run the reset again`; both: `wait until the named run ends and fix the named cause, then run the reset again` |
| Idle line (each job, every check passed) | `idle check: job <name> (job id <id>): 0 active runs` |
| Drop phase failed (exit 1) | `drop phase failed: dropped: <tables or none>; failed: <table>: <err>; not attempted: <tables or none>; check the three tables before any other step (runbook section 9, "If the drop phase fails")` |

Example for AC-189 (peak job busy, training idle):
`refused, nothing dropped: idle check: job smart_meter_peak_model (job id 101): active run 7, state RUNNING, started 2025-11-12T10:00:00Z; action: wait until the named run ends, then run the reset again`.

### Job-only mode (`pipeline_guard.py`, appended after `enforce_pipeline`)

The module docstring gains one paragraph, inserted before its closing quotes:

```text
Job-only mode (RESET_GUARD, ADR 0014): ``check_jobs`` finds each named job by base name in one
page of ``jobs.list`` (development prefix stripped, exactly one match) and reads it with the same
identity, uniqueness and active-run rules as the peak mode (``_read_named_job``). It calls only
``JOB_READ_CALLS``; the peak and pipeline-only modes above are unchanged.
```

```python
# ----------------------------------------------------------------------------- job-only mode
# Job-only mode (RESET_GUARD, ADR 0014). Appended; the modes above are unchanged (additions
# only: INGESTION_GUARD AC-92, RESET_GUARD AC-197).
TRAINING_JOB = "smart_meter_peak_model_training"
# The only client methods this mode calls (RESET_GUARD G-61); a subset of READ_CALLS.
JOB_READ_CALLS = ("jobs.get", "jobs.list", "jobs.list_runs")
MAX_JOBS_LISTED = 100  # one page of jobs.list, the API maximum (RESET_GUARD DA-60)
_ADDRESS = re.compile(r"\S*@\S*")  # an address in an API error (RESET_GUARD DA-71)


def redact(text: str) -> str:
    """Tokens, PATs, URLs and any word holding ``@`` become ``<redacted>``; nothing else."""
    return _ADDRESS.sub("<redacted>", _REDACT.sub("<redacted>", text))


def describe_error(exc: Exception) -> str:
    """``_describe_error`` (class, API error code, first line, 200 characters), then ``redact``."""
    return redact(_describe_error(exc))


def _job_only_subject(name: str, job_id: str) -> str:
    return f"job {name} (job id {job_id or 'not resolved'})"


@dataclass(frozen=True)
class JobStatus:
    """One named job: its active runs, or what could not be read (G-59)."""

    name: str  # base name, development prefix stripped
    job_id: str  # "" when no unique deployed job was found
    runs: tuple[ActiveRun, ...] = ()
    unreadable: tuple[Unreadable, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not (self.runs or self.unreadable)

    def subject(self) -> str:
        return _job_only_subject(self.name, self.job_id)

    def idle_line(self) -> str:
        return f"idle check: {self.subject()}: 0 active runs"

    def problems(self) -> list[str]:
        busy = [
            f"{self.subject()}: active run {run.run_id}, state {run.state}, "
            f"started {run.started or 'not started'}"
            for run in self.runs
        ]
        return busy + [f"{item.subject}: {item.read}: {item.error}" for item in self.unreadable]


@dataclass(frozen=True)
class JobsReport:
    jobs: tuple[JobStatus, ...]

    @property
    def ok(self) -> bool:
        return all(job.ok for job in self.jobs)

    @property
    def blocked(self) -> bool:
        return any(job.runs for job in self.jobs)

    @property
    def has_unreadable(self) -> bool:
        return any(job.unreadable for job in self.jobs)

    def problems(self) -> list[str]:
        return [text for job in self.jobs for text in job.problems()]

    def idle_lines(self) -> list[str]:
        return [job.idle_line() for job in self.jobs]


def check_jobs(client: Any, names: tuple[str, ...]) -> JobsReport:
    """Per name: one base-name match (G-60), then the shipped G-14 and G-16 reads (G-59)."""
    jobs: list[JobStatus] = []
    for name in names:
        runs: list[ActiveRun] = []
        unreadable: list[Unreadable] = []
        job_id = _find_job_id(client, name, unreadable)
        if job_id is not None:
            subject = _job_only_subject(name, str(job_id))
            _read_named_job(client, job_id, name, subject, runs, unreadable)
        shown = "" if job_id is None else str(job_id)
        jobs.append(JobStatus(name, shown, tuple(runs), tuple(unreadable)))
    return JobsReport(tuple(jobs))


def _find_job_id(client: Any, name: str, unreadable: list[Unreadable]) -> int | None:
    subject = _job_only_subject(name, "")
    try:
        listed = list(islice(client.jobs.list(limit=MAX_JOBS_LISTED), MAX_JOBS_LISTED))
    except Exception as exc:  # noqa: BLE001 - fail closed on any read error (G-18)
        unreadable.append(Unreadable(subject, "job list", _describe_error(exc)))
        return None
    matches = [
        getattr(job, "job_id", None)
        for job in listed
        if strip_dev_prefix(getattr(getattr(job, "settings", None), "name", None)) == name
    ]
    if len(listed) >= MAX_JOBS_LISTED:
        problem = f"{len(listed)} jobs listed, the page is full: {name!r} cannot be shown to be unique"
    elif not matches:
        problem = f"no deployed job named {name!r} (development prefix stripped)"
    elif len(matches) > 1:
        problem = f"{name!r} is not unique (job ids: {', '.join(str(i) for i in matches)})"
    elif not _POSITIVE_INT.match(str(matches[0])):
        problem = f"the job id {str(matches[0])[:80]!r} is not a positive integer"
    else:
        return int(str(matches[0]))
    unreadable.append(Unreadable(subject, "job list", problem))
    return None


def _read_named_job(
    client: Any,
    job_id: int,
    name: str,
    subject: str,
    runs: list[ActiveRun],
    unreadable: list[Unreadable],
) -> str | None:
    """``_read_job`` with the expected base name as a parameter (G-14, G-16).

    The body equals ``_read_job`` with ``INGESTION_JOB`` replaced by ``name``; a unit test
    proves both give the same result (RESET_GUARD DA-61).
    """
    ...  # the 40 lines of _read_job from "try:" to "return deployed", with "!= name"
```

The line of the page-full message is wrapped by `ruff format` at build; the text stays.

### Reset script (`scripts/reset_peak_model_outputs.py`)

Module docstring, new text (first paragraph, the table list, the Bronze paragraph, the credentials
paragraph and the usage block as shipped; exactly one line starts with `python` and holds
`--confirm`, as the shipped AC66_BOTH_LEGS AC-160 test requires):

```text
Guarded reset of the PEAK_MODEL rebuildable tables (AC-66). Run by the user, never by an agent.

(table list and Bronze paragraph as shipped)

Safety checks, all before the first DROP:
  1. Without ``--confirm`` the script only prints what it would do (dry run). The dry run runs
     every check below as well, so it predicts the outcome of ``--confirm``.
  2. The warehouse session time zone is UTC.
  3. Row counts: every table exists and has the expected row count (default: seed 42, 21,165
     weather rows and 36,480 rows in each ML table); other counts need ``--allow-other-counts``.
  4. ``bronze.files_weather_hourly`` has rows, because the weather Silver table is rebuilt from it.
  5. The AC-66 snapshot ``out/evidence/ac66_before_rebuild.json`` exists, so the evidence pair is
     not lost (``--skip-snapshot-check`` to override).
  6. Idle check, the last read before the first DROP: the jobs ``smart_meter_peak_model`` and
     ``smart_meter_peak_model_training`` (found by name, development prefix stripped) have no
     active run. A run in any state other than TERMINATED, SKIPPED or INTERNAL_ERROR, or a job
     that is not found exactly once or cannot be read, refuses (ADR 0014). The dry run runs the
     idle check too. No flag skips the idle check. A run started in the window between the idle
     check and the first DROP is not seen: start no job run until the reset has ended.

Every refusal is one line that starts with ``refused, nothing dropped: `` and exits 2; nothing was
dropped. Wait until the named run ends (or fix the named cause), then run the reset again. A failed
DROP stops the drops and exits 1 with one line that names the tables already dropped (runbook
"Reset"). Exit 0: dry run, or the three tables dropped.

(credentials paragraph, usage block and the Optional line as shipped)
```

Code (unchanged: `ROOT`, `SNAPSHOT`, `EXPECTED_ROWS`, `ResetRefused`, `Target`, `targets`, `plan`;
new import `from typing import Any` and `from smart_meter_peak_prediction import pipeline_guard`):

```python
IDLE_SET = (pipeline_guard.PEAK_JOB, pipeline_guard.TRAINING_JOB)  # D-104, DA-72
REFUSED = "refused, nothing dropped: "
UTC_ZONES = ("UTC", "Etc/UTC", "GMT")
STATEMENT_WAIT = "20s"  # below the 30 s HTTP limit of CLIENT_LIMITS (DA-63)
STATEMENT_DEADLINE_S = 600
ACTIVE_STATEMENT_STATES = ("PENDING", "RUNNING")  # Statement Execution states, not run states
ACTION_WAIT = "wait until the named run ends, then run the reset again"
ACTION_FIX = (
    "fix the named cause (deployment, permission or API availability), then run the reset again"
)
ACTION_BOTH = "wait until the named run ends and fix the named cause, then run the reset again"


class StatementFailed(ResetRefused):
    """A statement ended other than SUCCEEDED; ``detail`` keeps the raw text (DA-66)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        lines = detail.strip().splitlines()
        first = pipeline_guard.redact(lines[0].strip() if lines else "")
        super().__init__(f"SQL failed: {first[: pipeline_guard.MAX_ERROR_CHARS] or 'no message'}")


def build_client() -> Any:
    """The one workspace client: CLI profile or DATABRICKS_* variables, shipped limits (DA-63)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config

    options: dict[str, Any] = dict(pipeline_guard.CLIENT_LIMITS)
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if profile:
        options["profile"] = profile
    return WorkspaceClient(config=Config(**options))


class Warehouse:
    """Minimal SQL runner on the Statement Execution API (one value per statement)."""

    def __init__(self, client: Any) -> None:
        self.client = client
        warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
        if not warehouse:
            found = list(client.warehouses.list())
            if not found:
                raise ResetRefused("no SQL warehouse found; set DATABRICKS_WAREHOUSE_ID")
            warehouse = found[0].id
        self.warehouse_id = warehouse

    def run(self, statement: str) -> list[list[str]]:
        api = self.client.statement_execution
        response = api.execute_statement(
            statement=statement, warehouse_id=self.warehouse_id, wait_timeout=STATEMENT_WAIT
        )
        deadline = time.monotonic() + STATEMENT_DEADLINE_S
        while _state(response) in ACTIVE_STATEMENT_STATES:
            if time.monotonic() > deadline:
                api.cancel_execution(response.statement_id)
                raise ResetRefused("SQL statement timed out")
            time.sleep(3)
            response = api.get_statement(response.statement_id)
        if _state(response) != "SUCCEEDED":
            error = getattr(response.status, "error", None)
            raise StatementFailed(getattr(error, "message", None) or "no message")
        return list(response.result.data_array or []) if response.result else []

    def count(self, table: str) -> int | None:
        try:
            return int(self.run(f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608
        except StatementFailed as exc:
            if "TABLE_OR_VIEW_NOT_FOUND" in exc.detail or "cannot be found" in exc.detail:
                return None
            raise


def _state(response: Any) -> str:
    state = getattr(getattr(response, "status", None), "state", None)
    return str(getattr(state, "value", state))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--confirm", action="store_true", help="drop the tables (default: dry run)")
    parser.add_argument("--allow-other-counts", action="store_true")
    parser.add_argument("--skip-snapshot-check", action="store_true")
    return parser


def _settings() -> Settings:
    overrides = {
        f.name: os.environ[f"SMART_METER_{f.name.upper()}"]
        for f in fields(Settings)
        if os.environ.get(f"SMART_METER_{f.name.upper()}")
    }
    return Settings.from_mapping(overrides)


def _say(line: str) -> None:
    print(pipeline_guard.redact(" ".join(line.splitlines())))  # G-63


def _refuse(text: str) -> int:
    _say(REFUSED + text)
    return 2


def _reason(exc: Exception) -> str:
    return str(exc) if isinstance(exc, ResetRefused) else pipeline_guard.describe_error(exc)


def _idle_check(client: Any) -> tuple[list[str], str | None]:
    """Idle lines, or the idle-check problem (G-59 to G-61); never raises."""
    try:
        report = pipeline_guard.check_jobs(client, IDLE_SET)
    except Exception as exc:  # fail closed
        error = pipeline_guard.describe_error(exc)
        return [], f"idle check: internal error: {error}; action: {ACTION_FIX}"
    if report.ok:
        return report.idle_lines(), None
    if report.blocked and report.has_unreadable:
        action = ACTION_BOTH
    else:
        action = ACTION_WAIT if report.blocked else ACTION_FIX
    return [], f"idle check: {'; '.join(report.problems())}; action: {action}"


def _drop_failure(statements: list[str], done: int, exc: Exception) -> str:
    tables = [statement.removeprefix("DROP TABLE ") for statement in statements]
    return (
        f"drop phase failed: dropped: {', '.join(tables[:done]) or 'none'}; "
        f"failed: {tables[done]}: {_reason(exc)}; "
        f"not attempted: {', '.join(tables[done + 1 :]) or 'none'}; check the three tables "
        'before any other step (runbook section 9, "If the drop phase fails")'
    )


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[], Any] = build_client,
    snapshot_exists: Callable[[], bool] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = _settings()
    except Exception as exc:
        return _refuse(f"settings: {pipeline_guard.describe_error(exc)}")
    try:
        client = client_factory()
    except Exception as exc:
        jobs = ", ".join(f"job {name}" for name in IDLE_SET)
        error = pipeline_guard.describe_error(exc)
        return _refuse(f"workspace client: {error}; not read: the SQL warehouse, {jobs}")
    try:
        warehouse = Warehouse(client)
    except Exception as exc:
        return _refuse(f"warehouse lookup: {_reason(exc)}")
    try:
        zone = str(warehouse.run("SELECT current_timezone()")[0][0])
    except Exception as exc:
        return _refuse(f"time-zone query: {_reason(exc)}")
    if zone not in UTC_ZONES:
        return _refuse(f"the warehouse session time zone is {zone}, expected UTC")

    problems: list[str] = []
    statements: list[str] = []
    exists = snapshot_exists or SNAPSHOT.is_file
    try:
        statements = plan(
            settings,
            warehouse.count,
            allow_other_counts=args.allow_other_counts,
            snapshot_exists=args.skip_snapshot_check or exists(),
        )
    except ResetRefused as exc:
        problems.append(str(exc))
    except Exception as exc:
        problems.append(f"row counts: {pipeline_guard.describe_error(exc)}")
    idle_lines, idle_problem = _idle_check(client)  # the last read before the first DROP
    if idle_problem:
        problems.append(idle_problem)
    if problems:
        return _refuse("; ".join(problems))

    for line in idle_lines:
        _say(line)
    for statement in statements:
        _say(("DROP  " if args.confirm else "would ") + statement)
    if not args.confirm:
        _say("dry run: pass --confirm to drop these tables")
        return 0
    for done, statement in enumerate(statements):
        try:
            warehouse.run(statement)
        except Exception as exc:
            _say(_drop_failure(statements, done, exc))
            return 1
    _say(
        "done. Next (rebuild leg): pytest -m integration "
        "tests/integration/test_peak_data.py -k ac66_rebuild_leg"
    )
    _say(
        "(it starts ingest_weather, build_weather_silver, build_features and build_labels itself "
        "and compares; then the AC-66 verdict; runbook, Reset)"
    )
    return 0
```

The two `done.` strings stay inside `main` as literals: the shipped AC66_BOTH_LEGS AC-160 tests
read the string constants of `main` and expect exactly one `-k` selector, `ac66_rebuild_leg`. The
`if __name__ == "__main__": sys.exit(main())` block stays. `ruff check` and `ruff format` decide the
final wrapping; no text changes.

### Re-pinned shipped tests (DA-68)

| Test | Change | Kept |
|---|---|---|
| `tests/test_ac97_timing_docs.py::test_ac105_production_files_equal_v040_except_the_version` | New `SUPERSEDED = ("src/smart_meter_peak_prediction/pipeline_guard.py",)` with a comment naming RESET_GUARD DA-68 and AC-197; `tree_paths()` results and `tagged_paths(TAG)` results are filtered by it in this test. `VERSION_LINE_NEW` is replaced by `VERSION_LINE = re.compile(r'^__version__ = "\d+\.\d+\.\d+"$')`; `tree_digest` maps any matching line of `INIT_REL` to `VERSION_LINE_OLD`. The version asserts read `version = config["project"]["version"]` first, then check `init.count(f'__version__ = "<version>"') == 1`, no other `__version__` line, and the version as an int tuple at least `(0, 4, 1)`; the tag block replaces `VERSION_LINE_OLD` by the current line. `V040_TREE_SHA256` is recomputed from `v0.4.0` with the changed `tree_digest` over the filtered paths. Module docstring: one sentence on the narrowing | Test name, 6 `assert` statements, every other pinned path under `src/`, `resources/`, `notebooks/`, `databricks.yml` |
| `tests/test_ac66_legs_docs.py::test_ac161_production_files_and_reset_guards_equal_v060` | New `SUPERSEDED = ("src/smart_meter_peak_prediction/__init__.py", "src/smart_meter_peak_prediction/pipeline_guard.py")`, applied to `tree_paths()` and `tagged_paths(TAG)` in this test; `reset_digest` keeps only `ROOT`, `SNAPSHOT`, `EXPECTED_ROWS`, `ResetRefused`, `Target`, `targets`, `plan` (no `Warehouse`, no `main`); `_BlankStrings` is removed (no other user). `V060_TREE_SHA256` and `V060_RESET_SHA256` are recomputed from `v0.6.0` with the changed functions | Test name, 6 `assert` statements; `tests/test_peak_reset_script.py` and the archived PEAK_MODEL DEFINE and DESIGN stay pinned |
| `tests/test_ac66_legs_docs.py::test_ac171_rule_constants_and_reset_script_equal_v070` | The two reset asserts compare `reset_digest(...)` of the working file and of `git show v0.7.0:...` with `V070_RESET_SHA256`, recomputed from `v0.7.0` with the changed `reset_digest` (comment: "guard parts of the reset script, RESET_GUARD DA-68") | Test name, 4 `assert` statements, the rule-constant digest of `ac66_rules.py` |
| Module docstring of `tests/test_ac66_legs_docs.py` | One paragraph: RESET_GUARD narrows the AC-161 and AC-171 pins (paths and reset parts above), recomputed from the same tags | `V070_ASSERT_COUNTS` (its `test_ac161_...` count 6 stays true) |

No other shipped test changes. `tests/test_ingestion_guard.py` (AC-92 additions only against
`v0.3.0`, peak goldens) and `tests/test_pipeline_guard.py` (byte pin) pass unchanged by G-65 and
DA-67.

### Runbook (`docs/runbooks/peak_model.md`)

- "Concurrency with the ingestion job", bullet **Training.** becomes: `Run training only when no
  daily run is active. The training job fails with a guard error (G-04) if the feature table changes
  underneath it. It has no pre-check. The user-run reset (scripts/reset_peak_model_outputs.py,
  section 9) refuses while a run of the training job or of the daily job is active.` (with the
  script path in backticks).
- Section 9, the code block comment of the dry-run line becomes `# dry run: runs every check and
  prints the plan` (the v0.7.3 comment "prints the plan and the counts" was inaccurate: the counts
  appear only in a refusal).
- Section 9, after the paragraph that starts `The script prints table names and row counts only.`
  and before `**If a leg refuses or fails.**`, two paragraphs:

```text
**Idle check.** Before the first DROP, and in the dry run as well, the reset reads the jobs
`smart_meter_peak_model` and `smart_meter_peak_model_training` (found by name with the development
prefix stripped, ADR 0014) and refuses while either has an active run, in any state other than
`TERMINATED`, `SKIPPED` or `INTERNAL_ERROR`, including a queued run and a run started with `--only`.
The dry run runs the idle check too, so it predicts `--confirm`; when both jobs are idle it prints
one line per job with its job id and `0 active runs`. A refusal is one line that starts with
`refused, nothing dropped: `, names the job, its job id, the run id, the state and the start time
in UTC, and exits 2: wait until the named run ends, then run the reset again. A job that is not
found exactly once or cannot be read (permission, API error, a second deployment with the same
name) refuses the same way and names the cause: fix it, then run the reset again. No flag skips the
idle check. The idle check is the last read before the first DROP, but a run started in the window
between the idle check and the first DROP is not seen: start no job run until the reset has ended.

**If the drop phase fails.** A DROP that fails stops the reset with exit code 1 and one line that
names the tables already dropped, the table whose DROP failed with its error, and the tables not
attempted. Some tables may be gone: run the rebuild leg only if all three are gone; otherwise a
full run of `smart_meter_peak_model` restores the missing tables, then start again with the
snapshot (as for a partial state below).
```

Neither paragraph contains `optional`, `list-runs`, `then the daily job` or `run the daily job`,
nor a `-k` selector, so the shipped AC66_BOTH_LEGS AC-160 and AC66_ZERO_NEW_RUNS AC-172 checks of
section 9 stay green; the `**If a leg refuses or fails.**` marker and the text after it are unchanged.

### ADR 0012 note (build) and index

Appended to the Consequences of ADR 0012, after the INGESTION_GUARD note:

```text
- **Note (2026-11-12, RESET_GUARD):** the option "identify the job by name, with the
  development-mode prefix stripped", rejected above for the in-job pre-check, is used by the
  user-run reset script, which has no bundle reference; there any missing, duplicate or mismatched
  match refuses (ADR 0014). The reset reads the jobs through a job-only mode added to
  `pipeline_guard`; this decision and the peak pre-check are unchanged.
```

`docs/adr/README.md` gains the row `| 0014 | [The user-run reset finds the two peak jobs by base name
and refuses unless both are idle, failing closed](0014-user-run-reset-checks-the-peak-jobs-by-base-name-and-fails-closed.md)
| Proposed | 2026-11-12 |`; at `/ship` both the ADR and the row become `Accepted`.

### Unit-test fakes (`tests/support/reset_fakes.py`)

| Item | Detail |
|---|---|
| Constants | `PEAK_ID = 101`, `TRAINING_ID = 102`, `INGESTION_ID = 103`, `DEV = "[dev someone] "`, `RUN_ID = 7`, `START_MS = 1762941600000` (`2025-11-12T10:00:00Z`), `WAREHOUSE_ID = "wh-1"`, `TABLES` (the three `smart_meter_dev` tables and `smart_meter_dev.bronze.files_weather_hourly` with 21165, 36480, 36480, 21165 rows) |
| `FakeClient(jobs=..., runs=..., sql=..., warehouses=...)` | `jobs`: list of `(job_id, deployed name)` (default the three dev jobs); `runs`: job id to a list of runs, or an `Exception`; `overrides`: `api.method` to an `Exception` or a callable; `sql`: statement to a result row, a `"FAILED:<text>"` marker or an `Exception`; `log`: shared list of call records such as `jobs.list(limit=100)`, `jobs.get(101)`, `jobs.list(name=[dev someone] smart_meter_peak_model)`, `jobs.list_runs(101)`, `warehouses.list`, `sql:<statement>`; `forbidden`: every other attribute, recorded and raising `AssertionError` |
| Iterators | `jobs.list` and `jobs.list_runs` return generators that count `next()` calls (`pulled[...]`), so tests prove at most 100 jobs and 25 runs were read |
| States | `run(state, run_id=RUN_ID, start_time=START_MS)`; `state` may be a string, an `Enum` member with `.value`, or `None` (missing); statement responses carry `status.state` as a string or an object with `.value` |
| `factory(client)` / `raising_factory(exc)` | Client factories for `main(client_factory=...)` |
| `secret_error()` | `RuntimeError` whose text is built by concatenation from `"Bea" + "rer abc"`, `"da" + "pi123"`, `"https" + "://example.invalid/x"` and `"someone" + "@" + "example.invalid"`, so the hygiene scans stay clean |
| `no_secret(text)`, `utc_only(text)` | NFR-53: none of `https://`, `http://`, `dapi`, `Bearer`, `@`; NFR-55: every `\d{4}-\d{2}-\d{2}T\S*` match, stripped of `),.;`, fully matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` |

---

## Key Decisions (ADRs)

| ADR | Title | Status |
|---|---|---|
| 0014 | [The user-run reset finds the two peak jobs by base name and refuses unless both are idle, failing closed](../../../docs/adr/0014-user-run-reset-checks-the-peak-jobs-by-base-name-and-fails-closed.md) | Proposed |
| 0012 | Read-only pre-check in the daily peak job: unchanged; a dated note at build points to ADR 0014 | Accepted |

ADR 0014 is the lasting decision: how a local script identifies bundle jobs without a bundle
reference, and that it fails closed on any ambiguity. The other decisions are code shape (DA-61 to
DA-67), test mechanics (DA-68, DA-69) and release mechanics (DA-70); none binds another feature, so
none is an ADR. The additions-only rule for `pipeline_guard` is already practice from INGESTION_GUARD
(ADR 0013 Decision, "added next to the peak mode without changing it").

---

## Delivery Plan

| Step | Scope | Manifest entries | Files |
|---|---|---|---|
| Precondition | Spec PR #78 (DEFINE and this DESIGN, ADR 0014 Proposed) stable; tags `v0.3.0`, `v0.4.0`, `v0.6.0`, `v0.7.0`, `v0.7.3` present locally (they are) | - | - |
| PR 1 (branch `build/reset-guard`) | Guard mode, reset script, fakes, tests, re-pins, version, runbook, ADR note and index | 1 to 13 | 13 |
| Live gate (on the build branch, before `/ship`, Q-42) | Deploy, then the user-run dry run of AC-202 (U-09) | - | 0 |
| Ship | CHANGELOG `[0.8.0]`, ADR 0014 and its index row `Accepted`, follow-up file closed, the two SHIPPED rows updated; tag `v0.8.0` on the merge commit | 14 to 19 | 6 |

Entries 1, 2, 6 and 7 land in one commit with 3 to 5 and 12, 13: entry 1 breaks R1 and R2, entry 2
breaks R2 and R3, and the bump depends on R1, so no intermediate commit is green otherwise.
`ruff check .`, `ruff format --check .` and `pytest` run before each commit, with the tags present.

---

## File Manifest

Ordered by dependency. `/build` executes this list top to bottom. Agents: `pipeline-builder`
(Databricks module) for library, script and test code, `build-agent` for the runbook and ADR text,
`ship-agent` for the release entries. No Kafka or MLflow agent applies.

Existing inputs, read and not modified: `resources/`, `notebooks/`, `pipelines/`, `databricks.yml`
(C-30), `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py`,
`tests/test_peak_reset_script.py`, `tests/integration/` (no live test changes), `scripts/check_specs.py`,
the archived PEAK_MODEL and PEAK_MODEL_CONCURRENCY DEFINE and DESIGN (E4).

| # | File | Action | Purpose | Agent | Depends on |
|---|---|---|---|---|---|
| 1 | `src/smart_meter_peak_prediction/pipeline_guard.py` | Update (additions only) | Docstring paragraph; job-only mode section (*Job-only mode*): `TRAINING_JOB`, `JOB_READ_CALLS`, `MAX_JOBS_LISTED`, `_ADDRESS`, `redact`, `describe_error`, `_job_only_subject`, `JobStatus`, `JobsReport`, `check_jobs`, `_find_job_id`, `_read_named_job` (body copied from `_read_job`, `INGESTION_JOB` replaced by `name`). No shipped line changes, no import added (G-65) | pipeline-builder | - |
| 2 | `scripts/reset_peak_model_outputs.py` | Update | Docstring (FR-114); `IDLE_SET` and the constants, `StatementFailed`, `build_client`, `Warehouse(client)`, `_state`, `build_parser`, `_settings`, `_say`, `_refuse`, `_reason`, `_idle_check`, `_drop_failure`, `main` (*Reset script*); `plan()` and the parts G-66 names unchanged | pipeline-builder | 1 |
| 3 | `tests/support/reset_fakes.py` | Create | Fakes and helpers (*Unit-test fakes*) | pipeline-builder | - |
| 4 | `tests/test_reset_guard_library.py` | Create | Module docstring naming RESET_GUARD AC-189, AC-190, AC-197, AC-200; job-only mode tests, parity test, AC-197 tests with `V073_*` constants computed at build from tag `v0.7.3` (DA-69) | pipeline-builder | 1, 3 |
| 5 | `tests/test_reset_guard.py` | Create | Module docstring naming RESET_GUARD AC-189 to AC-196 and AC-198 to AC-200; the `main()` tests of the Test Strategy | pipeline-builder | 2, 3 |
| 6 | `tests/test_ac97_timing_docs.py` | Update | R1 (*Re-pinned shipped tests*); `V040_TREE_SHA256` recomputed from `v0.4.0` | pipeline-builder | 1, 12, 13 |
| 7 | `tests/test_ac66_legs_docs.py` | Update | R2 and R3; `V060_TREE_SHA256`, `V060_RESET_SHA256`, `V070_RESET_SHA256` recomputed from `v0.6.0` and `v0.7.0` | pipeline-builder | 1, 2, 13 |
| 8 | `docs/runbooks/peak_model.md` | Update | "Training" bullet, dry-run comment, section 9 paragraphs (*Runbook*) | build-agent | 2 |
| 9 | `tests/test_reset_guard_docs.py` | Create | AC-201 test | pipeline-builder | 2, 8 |
| 10 | `docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md` | Update | Dated note pointing to ADR 0014 (*ADR 0012 note*); status stays `Accepted` (shipped PEAK_MODEL_CONCURRENCY AC-79 test) | build-agent | - |
| 11 | `docs/adr/README.md` | Update | Index row 0014, `Proposed` | build-agent | 10 |
| 12 | `pyproject.toml` | Update | `version = "0.8.0"`; runtime `dependencies` unchanged (E7, NFR-57) | pipeline-builder | - |
| 13 | `src/smart_meter_peak_prediction/__init__.py` | Update | `__version__ = "0.8.0"` | pipeline-builder | 12 |
| 14 | `CHANGELOG.md` | Update at `/ship` | `[0.8.0]`: Added (reset idle check over `smart_meter_peak_model` and `smart_meter_peak_model_training`, also in the dry run; job-only mode of `pipeline_guard`; `main()` unit tests), Changed (every failure before the first DROP is one `refused, nothing dropped: ...` line with exit 2, the time-zone refusal takes that prefix; a failed DROP exits 1; statement wait 20 s; four shipped pins narrowed, DA-68), Unchanged (peak and pipeline-only modes byte-equal, no bundle file changed); package version 0.8.0 | ship-agent | 1 to 13 |
| 15 | `docs/adr/0014-user-run-reset-checks-the-peak-jobs-by-base-name-and-fails-closed.md` | Update at `/ship` | Status `Accepted` after AC-202 passed; a "Live check" line with the AC-202 date and the two job ids seen | ship-agent | 14 |
| 16 | `docs/adr/README.md` | Update at `/ship` | Row 0014 `Accepted` | ship-agent | 15 |
| 17 | `.claude/sdd/follow-ups/F_PEAK_MODEL_03.md` | Update at `/ship` | Closure filled, status `Closed`; the Problem's table names corrected in the Closure note (`ml.household_*_daily`, not `gold.*_daily`) | ship-agent | 16 |
| 18 | `.claude/sdd/archive/PEAK_MODEL/SHIPPED_2026-10-22.md` | Update at `/ship` | Follow-ups row PEAK_MODEL F-03: item cell appended with a bold "Closed <date>" sentence naming RESET_GUARD, v0.8.0 and the follow-up file; target cell `Closed (v0.8.0)`. If `check_specs.py` rule (c) counts change, update `.claude/sdd/citation_allowlist.json` in the same commit | ship-agent | 17 |
| 19 | `.claude/sdd/archive/PEAK_MODEL_CONCURRENCY/SHIPPED_2026-10-22.md` | Update at `/ship` | Follow-ups row PEAK_MODEL_CONCURRENCY F-02 the same way (`Closed (v0.8.0)`); allowlist rule as entry 18 | ship-agent | 17 |

The build report (`BUILD_REPORT_RESET_GUARD.md`) is the output of `/build` and is not a manifest
entry. ADR 0014 itself was drafted in this phase. Thirteen files in the build PR, six at ship, 19 in
total (below the split threshold of about 25).

---

## Test Strategy

Levels: **Unit** (pytest, no workspace, no `databricks-sdk`, runs in CI) and **Manual (live)** (the
user, on `dev`, C-31). Every new test name starts with its AC id. Fixture values are those of
*Unit-test fakes*; "every table check passes" means time zone `UTC`, the expected counts, Bronze
weather 21165 rows and `snapshot_exists=lambda: True`. "0 DROP statements" means no `sql:DROP` entry
in the log. Rows marked "(order)" check the shared call log, rows marked "(after-state)" check what
did not change.

**Live plan** (one session, a clean checkout of the build branch; Kafka not needed; no job run is
started).

1. `databricks bundle validate -t dev -p dev`, then `databricks bundle deploy -t dev -p dev`; exit
   codes in the BUILD_REPORT (only the synced `src/` changes; C-30).
2. Both jobs idle (Jobs UI, or the hand check of "Concurrency with the ingestion job"); the three
   tables present with the expected counts; `out/evidence/ac66_before_rebuild.json` present (if
   not, run `-k "ac66_before"`, which reads tables only).
3. U-09: the user runs `DATABRICKS_CONFIG_PROFILE=dev python scripts/reset_peak_model_outputs.py`
   (no `--confirm`), then `echo $?`, and pastes both into the BUILD_REPORT. An authorization of the
   agent for that one dry run goes into the Deviations table with the user's words and the date (C-31).

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-189 | Unit | `tests/test_reset_guard.py::test_ac189_an_active_run_of_either_peak_job_refuses_both_modes` | Parametrized over the busy job (101 or 102) and the state (`QUEUED`, `PENDING`, `RUNNING`, `TERMINATING`, `BLOCKED`, `WAITING_FOR_RETRY`, `NEW_STATE`, an `Enum` member `RUNNING`, `None`); the other job has no run. For `main(["--confirm"])` and then `main([])`: exit 2; output exactly one line starting `refused, nothing dropped: ` that contains `job <base name> (job id <id>): active run 7, state <state or UNKNOWN>, started 2025-11-12T10:00:00Z` and `action: wait until the named run ends`; 0 DROP statements; `no_secret` and `utc_only` hold |
| AC-189 | Unit | `tests/test_reset_guard.py::test_ac189_a_run_without_start_time_is_shown_not_started` | A `QUEUED` run of 102 with `start_time` `None`, `0`, `""` and a naive ISO string: the line contains `started not started`; exit 2 |
| AC-189 | Unit | `tests/test_reset_guard_library.py::test_ac189_check_jobs_reports_every_active_run` | `check_jobs` on the fake: `JobsReport.ok` false, `blocked` true, one `JobStatus` per name in order, `problems()` texts as in *Line shapes*; a run listed `TERMINATED`, `SKIPPED` or `INTERNAL_ERROR` next to an active one is not reported |
| AC-190 | Unit | `tests/test_reset_guard.py::test_ac190_an_unreadable_peak_job_fails_closed` | Every table check passes; parametrized: the client factory raises; `jobs.get` raises `RuntimeError`; `jobs.get` raises an error with `error_code` `PERMISSION_DENIED`; no deployed job matches `smart_meter_peak_model_training`; two jobs match it (another user's `[dev other] ` copy); `jobs.get(101)` names `[dev someone] other_job`; `jobs.list_runs` raises; plus `jobs.list` raises and 100 listed jobs (page full). `main(["--confirm"])`: exit 2; exactly one line, starting `refused, nothing dropped: `, naming the base name and the read label (`workspace client`, `job`, `PERMISSION_DENIED`, `job list`, `not unique`, `another job`, `active runs`, `page is full`); no `Traceback` in the captured stdout and stderr; 0 DROP statements |
| AC-190 | Unit | `tests/test_reset_guard_library.py::test_ac190_lookup_fails_closed_on_every_ambiguity` | `check_jobs` directly on the G-60 cases (none, two, page full, id `"abc"`, id `0`, listing raises, item without `settings`): each `JobStatus.job_id == ""`, one unreadable item `job list`, and no `jobs.get` or `jobs.list_runs` call for that job |
| AC-191 | Unit (order) | `tests/test_reset_guard.py::test_ac191_confirm_with_both_jobs_idle_drops_the_three_tables_in_order` | Runs listed only in `TERMINATED`, `SKIPPED`, `INTERNAL_ERROR`; `main(["--confirm"])` exit 0; output lines in order: `idle check: job smart_meter_peak_model (job id 101): 0 active runs`, the same for `smart_meter_peak_model_training (job id 102)`, the three `DROP  DROP TABLE ...` lines, the two `done.` lines; the `sql:DROP` entries of the log are exactly the three statements of the AC, in that order, and come after every Jobs read |
| AC-192 | Unit | `tests/test_reset_guard.py::test_ac192_connection_failures_print_one_refusal_line` | Parametrized over the cases (client factory raises; `warehouses.list` returns `[]`; it raises `RuntimeError`; `SELECT current_timezone()` ends `FAILED`; it raises `RuntimeError`; it returns `Europe/Berlin`) and over `[]` and `["--confirm"]`, with `DATABRICKS_WAREHOUSE_ID` unset: exactly one stdout line, starting `refused, nothing dropped: ` (the last case ends `time zone is Europe/Berlin, expected UTC`); no `Traceback` in stdout or stderr; exit 2; 0 DROP and 0 `count(*)` statements; 0 Jobs calls |
| AC-192 | Unit | `tests/test_reset_guard.py::test_ac192_missing_sdk_refuses_through_the_default_factory` | `sys.modules` entries `databricks`, `databricks.sdk`, `databricks.sdk.config` set to `None` through `monkeypatch`; `main([])` with the default factory prints exactly one line starting `refused, nothing dropped: workspace client: ModuleNotFoundError`; exit 2 |
| AC-193 | Unit (order) | `tests/test_reset_guard.py::test_ac193_every_check_completes_before_the_first_drop` | (a) Every check passes: in the log, the index of the first `sql:DROP` is greater than the index of every `jobs.*` entry, of `sql:SELECT current_timezone()` and of the four `sql:SELECT count(*) FROM ...` entries; the last Jobs read precedes the first DROP with no SQL statement in between (DA-62) |
| AC-193 | Unit | `tests/test_reset_guard.py::test_ac193_each_failing_check_refuses_without_a_drop` | (b) to (f) one failing check in turn (time zone `Europe/Berlin`; `smart_meter_peak_model` `RUNNING`; features count 5; Bronze weather count 0; `snapshot_exists=lambda: False`) with `["--confirm"]`: no `sql:DROP` in the log; exit 2; exactly one line starting `refused, nothing dropped: `; for (d) to (f) the line after the prefix equals the shipped `plan()` text (`... has 5 rows, expected 36480`, `... is empty or missing: ...`, `snapshot out/evidence/ac66_before_rebuild.json is missing: ...`) and the Jobs reads were made |
| AC-193 | Unit | `tests/test_reset_guard.py::test_ac193_count_and_idle_problems_share_one_line` | Features count 5 and the training job `RUNNING`: one line `refused, nothing dropped: <plan text>; idle check: job smart_meter_peak_model_training (job id 102): active run 7, ...; action: ...`; exit 2 (G-62) |
| AC-194 | Unit | `tests/test_reset_guard.py::test_ac194_dry_run_checks_the_jobs_and_sends_only_select` | Both jobs idle; `main([])` exit 0; the log holds the 8 Jobs reads of G-61; output lines exactly: the two idle lines, `would DROP TABLE smart_meter_dev.silver.weather_hourly` and the two other `would` lines, `dry run: pass --confirm to drop these tables`; every `sql:` entry starts with `SELECT` |
| AC-195 | Unit | `tests/test_reset_guard.py::test_ac195_no_option_or_variable_skips_the_idle_check` | `smart_meter_peak_model_training` `RUNNING`; `DATABRICKS_CONFIG_PROFILE=dev`, `DATABRICKS_WAREHOUSE_ID=wh-1` and every `SMART_METER_<FIELD>` of `Settings` set to its default through `monkeypatch`; `main(["--confirm", "--allow-other-counts", "--skip-snapshot-check"])`: exit 2, 0 DROP statements, the line names job 102 and run 7. `sorted(s for a in build_parser()._actions for s in a.option_strings)` equals `["--allow-other-counts", "--confirm", "--help", "--skip-snapshot-check", "-h"]`. `inspect.signature(main)` has exactly the parameters `argv`, `client_factory`, `snapshot_exists` |
| AC-196 | Unit | `tests/test_reset_guard.py::test_ac196_a_failed_drop_stops_and_exits_1` | Both jobs idle, every check passing; `DROP TABLE smart_meter_dev.ml.household_features_daily` ends `FAILED:[TABLE_LOCKED] busy`; `main(["--confirm"])` exit 1; the log holds the first two DROP statements and not the third; the last line is `drop phase failed: dropped: smart_meter_dev.silver.weather_hourly; failed: smart_meter_dev.ml.household_features_daily: SQL failed: [TABLE_LOCKED] busy; not attempted: smart_meter_dev.ml.household_labels_daily; ...`; no output contains `Traceback` or `nothing dropped`; with the first DROP failing the line holds `dropped: none` |
| AC-197 | Unit | `tests/test_reset_guard_library.py::test_ac197_shipped_guard_and_reset_tests_are_kept_with_their_asserts` | For `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py`, `tests/test_peak_reset_script.py`: every name in `V073_ASSERT_COUNTS` is a top-level test function with at least its golden `assert` count; with tag `v0.7.3` present the counts of `git show v0.7.3:<file>` equal the goldens; the three files pass in the same `pytest` run |
| AC-197 | Unit | `tests/test_reset_guard_library.py::test_ac197_shipped_modes_equal_v073_byte_for_byte` | Fixed inputs: peak mode idle, busy run, unreadable job (`PermissionDenied`), client factory failure; pipeline-only mode idle, busy update, unreadable pipeline, client factory failure; `now` fixed. The SHA-256 of `json.dumps` of every `message()` and `exit_value()` equals `V073_MODES_SHA256`; with the tag present the module loaded from `git show v0.7.3:src/smart_meter_peak_prediction/pipeline_guard.py` (with the `sys.modules` step of `_load_tagged_guard`) gives equal outputs, and `enforce`/`enforce_pipeline` raise the same messages |
| AC-197 | Unit | `tests/test_reset_guard_library.py::test_ac197_read_call_sets_and_no_sdk_import` | `READ_CALLS == ("jobs.get", "jobs.list", "jobs.list_runs", "pipelines.get")`, `PIPELINE_READ_CALLS == ("pipelines.get",)`, both equal to the tag's values when present; `set(JOB_READ_CALLS) <= set(READ_CALLS)`; the AST of `pipeline_guard.py` imports no `databricks` module and calls no `sleep` |
| AC-197 | Unit | `tests/test_reset_guard_library.py::test_ac197_job_reader_matches_the_shipped_reader` | For every shipped job case (idle; each non-terminal state; terminal list race; `jobs.get` raises `NotFound` and `PermissionDenied`; another name; same-name list of 0 and 2; `jobs.list` raises; `jobs.list_runs` raises; 30 runs): `_read_job(c1, id, s, r1, u1)` and `_read_named_job(c2, id, INGESTION_JOB, s, r2, u2)` on twin fakes return the same value, and `r1 == r2`, `u1 == u2`, and the two call logs are equal (DA-61) |
| AC-197 | Unit | `tests/test_reset_guard_library.py::test_ac197_reset_imports_the_guard_and_defines_no_run_state_set` | AST of the reset script: an `ImportFrom` of `smart_meter_peak_prediction` with the name `pipeline_guard`; no `Set`, `Tuple`, `List` literal and no `set(...)`/`frozenset(...)` call whose string elements include any of `TERMINATED`, `SKIPPED`, `INTERNAL_ERROR`, `QUEUED`, `TERMINATING`, `BLOCKED`, `WAITING_FOR_RETRY`; the module imports no `databricks` module at top level |
| AC-197 | Unit | `tests/test_reset_guard_library.py::test_ac197_bundle_files_equal_v073` | Tree digest of `resources/`, `notebooks/`, `pipelines/` and `databricks.yml` equals `V073_BUNDLE_SHA256`; with the tag present the path lists and every file's bytes equal `v0.7.3` |
| AC-197 | Unit (shipped, unchanged) | `tests/test_ingestion_guard.py::test_ac92_guard_module_changes_are_additions_only`, `::test_ac92_peak_mode_signatures_and_output_are_unchanged`, `::test_ac92_shipped_guard_tests_are_byte_identical_to_v030`, `::test_ac93_library_imports_no_sdk_and_never_sleeps`; `tests/test_pipeline_guard.py` (all 28); `tests/test_peak_reset_script.py` (all 3) | Green with no edit: additions only against `v0.3.0` (G-65), peak goldens, byte pin of the shipped guard tests, the three `plan()` tests (FR-113) |
| AC-197 | Unit (shipped, re-pinned) | `tests/test_ac97_timing_docs.py::test_ac105_production_files_equal_v040_except_the_version`; `tests/test_ac66_legs_docs.py::test_ac161_production_files_and_reset_guards_equal_v060`, `::test_ac171_rule_constants_and_reset_script_equal_v070`, `::test_ac171_v070_unit_tests_are_kept_with_their_asserts` | Green after DA-68 with the same names and `assert` counts; every path and reset part outside G-66 still equals its tag |
| AC-197 | Unit (gates) | Full `pytest` run (no marker), `ruff check .`, `ruff format --check .`, `python scripts/check_specs.py`; BUILD_REPORT Verification Log | 0 failures, 0 errors (NFR-57); `databricks-sdk` not in `[project] dependencies` |
| AC-198 | Unit | `tests/test_reset_guard.py::test_ac198_only_read_calls_before_the_first_drop_and_no_secret_in_output` | The paths of AC-189 to AC-196 (one case each) on the recording fake: before the first `sql:DROP` the called methods are a subset of `READ_CALLS` minus `pipelines.get`, `warehouses.list`, `statement_execution.execute_statement` with a statement starting `SELECT`, `statement_execution.get_statement` and `statement_execution.cancel_execution`; `forbidden == []`. `jobs.get` raising `secret_error()`: the line contains `<redacted>` and none of `https://`, `http://`, `dapi`, `Bearer`, `@`; `no_secret` holds on every output line of every path |
| AC-199 | Unit (after-state) | `tests/test_reset_guard.py::test_ac199_two_runs_give_equal_output_and_change_nothing` | Cases: AC-189 busy (`RUNNING`, job 101), AC-190 `PERMISSION_DENIED`, AC-192 empty warehouse list, AC-194 idle dry run; each run twice on fresh twin fakes: captured outputs byte-equal, exit codes equal; on the refused cases every `sql:` entry starts with `SELECT`; `git status --porcelain --untracked-files=all` before and after the four cases is equal |
| AC-200 | Unit | `tests/test_reset_guard.py::test_ac200_idle_check_reads_at_most_4_calls_per_job_and_never_sleeps` | `reset.time.sleep` replaced by a counter; the cases of AC-189 (one per job), each AC-190 case and AC-194: the Jobs entries of the log are at most 8, and for the idle case exactly `jobs.list(limit=100)`, `jobs.get(101)`, `jobs.list(name=...smart_meter_peak_model)`, `jobs.list_runs(101)`, then the same four for 102; the sleep counter is 0; with 30 active runs listed per job the run generator was advanced 25 times |
| AC-200 | Unit | `tests/test_reset_guard.py::test_ac200_client_is_built_with_the_shipped_limits` | Fake modules `databricks.sdk` and `databricks.sdk.config` injected through `monkeypatch.setitem(sys.modules, ...)`: `build_client()` passes `Config(retry_timeout_seconds=60, http_timeout_seconds=30)`, plus `profile="dev"` only when `DATABRICKS_CONFIG_PROFILE` is set; every `execute_statement` call of a `main` run carries `wait_timeout="20s"` (DA-63) |
| AC-200 | Unit | `tests/test_reset_guard_library.py::test_ac200_job_only_mode_reads_one_page_and_25_runs` | `check_jobs` with 150 listed jobs: the job generator advanced 100 times and the job is unreadable (`page is full`); with 30 active runs: 25 advanced, 25 reported; the fake's only methods called are in `JOB_READ_CALLS` |
| AC-201 | Unit | `tests/test_reset_guard_docs.py::test_ac201_runbook_and_docstring_state_the_idle_check` | Section 9 of `docs/runbooks/peak_model.md` (from `## 9. Reset (user-run, AC-66)` to the next `## `) and the module docstring of the reset script, backticks removed, whitespace collapsed, casefolded, each hold `smart_meter_peak_model and smart_meter_peak_model_training`, `the dry run runs the idle check too`, `refused, nothing dropped:`, `no flag skips the idle check`, `the window between the idle check and the first drop`; the `**Training.**` bullet of "Concurrency with the ingestion job" holds `reset_peak_model_outputs.py` and `refuses while a run of the training job`. The shipped AC66_BOTH_LEGS AC-160 and AC66_ZERO_NEW_RUNS AC-172 tests and PEAK_MODEL_CONCURRENCY AC-79 pass unchanged |
| AC-202 | Manual (live, user, U-09) | Live plan steps 1 to 3; BUILD_REPORT Acceptance Criteria Evidence | Exit 0; the output holds `idle check: job smart_meter_peak_model (job id <id>): 0 active runs` and the same for `smart_meter_peak_model_training`, with the deployed ids (A-57, A-60), the three `would DROP TABLE smart_meter_dev...` lines and the `dry run:` line; because the dry run passed `plan()` without `--allow-other-counts`, the three tables had the expected counts and nothing was dropped; full output and exit code copied into the BUILD_REPORT |

---

## Operational Concerns

| Concern | Approach |
|---|---|
| Deployment | No bundle resource changes (C-30). `databricks bundle validate -t dev -p dev` and `databricks bundle deploy -t dev -p dev` from a clean tree of the build branch sync the new `pipeline_guard.py`; the two shipped pre-checks import it and behave as at `v0.7.3` (AC-197) |
| Scheduling and retries | Schedules, retries and timeouts of the jobs are unchanged. The reset never waits or retries: a refusal is the outcome, and the user runs it again (G-61). The SDK's own retry is bounded by `CLIENT_LIMITS` (60 s retry, 30 s per HTTP call); a statement waits 20 s per call and 600 s in total, as shipped |
| Monitoring and alerting | None added: the reset is interactive. The refusal or drop-failure line is the signal; the BUILD_REPORT keeps the AC-202 output |
| Secrets | None added. The client authenticates through the CLI profile or `DATABRICKS_*` variables, read by the SDK; the script reads no secret and prints no host, URL, token or address (G-63). Fake secrets in tests are built by concatenation |
| Cost | Per run at most 8 Jobs API reads (G-61), 0 job runs, and the shipped 5 `SELECT` statements (time zone, 4 counts) on the serverless warehouse; the dry run costs the same. CI gains about 60 unit cases and two `git` subprocess calls per tag comparison |
| Backfill / reprocessing | Not applicable. A refused run changes nothing and can be repeated (NFR-56). After a failed drop phase the recovery is the runbook section 9 path for a partial state (a full run of `smart_meter_peak_model`, a new snapshot, the full AC-66 sequence) |

---

## Assumption dependencies

| Assumption | Decisions depending on it | Check | Fallback |
|---|---|---|---|
| A-57 Each peak job deployed once under `[dev <user>] <base name>`, no other visible copy | DA-60, AC-202 | AC-202 prints both resolved ids; prior art: the integration fixtures `peak_job` and `training_job` | The check refuses with `not unique` or `no deployed job named ...` (safe direction); the user removes the extra deployment |
| A-58 An active run is listed by `list_runs(active_only=True)` at once | G-59 | Shipped behaviour (PEAK_MODEL_CONCURRENCY spike 06 and live tests) | None in code; the window is that of C-32 and is named in the runbook |
| A-60 The user's profile may read both jobs and their runs | AC-202 | AC-202 | A denied read refuses with `PERMISSION_DENIED` (FR-106) |
| DA-60 `jobs.list(limit=100)` is accepted and the SDK iterator fetches a second page only when a 101st item is pulled | G-60 | Jobs API reference (`limit` 1 to 100); `islice` stops after 100 pulls (AC-200 fake); same reasoning as AC66_ZERO_NEW_RUNS DA-50 for `list_runs` | `limit=25` with `MAX_JOBS_LISTED = 25` (a page-full refusal then needs 25 jobs) |
| DA-63 `Config(profile=..., retry_timeout_seconds=60, http_timeout_seconds=30)` works with the local SDK and `wait_timeout="20s"` is accepted | `build_client`, `Warehouse.run` | `Config` form proven by spike 06 (ADR 0012, Platform probe) for 0.40.0; the local SDK (`databricks-sdk>=0.30`, integration extra) is exercised by AC-202; `wait_timeout` range 0 or 5 to 50 s (Statement Execution reference) | If `Config` rejects `profile`, pass `profile` to `WorkspaceClient` and the limits to `Config` (a Deviations row) |

---

## Risks & Trade-offs

| Risk or trade-off | Impact | Mitigation |
|---|---|---|
| A run starts between the idle read and the first DROP (C-32) | The drop that the feature prevents, in a window of a few lines of output | The check is the last read (DA-62); development mode pauses schedules on `dev`; the runbook and docstring name the window |
| `_read_named_job` is a copy of `_read_job` | The two could drift | The parity test (AC-197) compares results and calls over every shipped case; the state rule itself is shared |
| Narrowing three shipped pins (DA-68) | A later accidental change to `pipeline_guard.py` or to the reset `main()` is no longer caught by those pins | AC-197 pins behaviour and additions only; the plan-side reset parts stay pinned; the narrowing is listed in the CHANGELOG |
| A second deployment or a full page blocks every reset (no override, Q-41) | A legitimate reset waits until the workspace is cleaned up | The line names the cause and the job ids; ADR 0014 names the revisit trigger |
| Statement wait lowered from 50 s to 20 s | A few more `get_statement` polls on a cold warehouse | Same 600 s deadline and 3 s poll; no HTTP time-out on a long wait |
| Trade-off: idle check after the counts | On a busy job the 5 `SELECT` statements ran for nothing | They are cheap, and a count refusal caused by a running job is shown with its cause |
| Trade-off: one refusal line for every case | Long lines when several items block | Items are separated by `; ` and appear in idle-set order; the line can be copied whole |
| Trade-off: exit code 1 for a drop-phase failure (D-108) | A third exit code | Code 2 keeps meaning "nothing dropped" |

---

## Open Items for the User

| ID | Item | When |
|---|---|---|
| U-09 | Run `DATABRICKS_CONFIG_PROFILE=dev python scripts/reset_peak_model_outputs.py` (dry run, no `--confirm`) on `dev` with both peak jobs idle after the deploy of the build branch, and paste the output and the exit code; or authorize the agent for that one dry run, recorded in the BUILD_REPORT Deviations table with your words and the date (C-31) | Live gate of PR 1, before `/ship` (Q-42) |

No design question is open: OD-51 to OD-55 are resolved by DA-60 to DA-64.

---

## Self-Review

- **Weak points:**
  - The idle check proves "no active run at the moment of the last read", not "no run during the
    drop" (C-32); the window is now a few printed lines, but it is not closed.
  - `_read_named_job` duplicates the 40-line flow of `_read_job` because the shipped
    additions-only test forbids editing it; the parity test makes the copy safe but not elegant.
  - Name lookup depends on the development prefix format and on the user's view of the workspace;
    every failure is a refusal, so a wrong lookup costs a blocked reset, not a wrong drop.
  - AC-197 counts `assert` statements and compares digests of outputs; a weakened condition with the
    same count still passes, so review reads the diffs of the re-pinned tests.
  - The live evidence is one idle dry run; the busy and unreadable paths are proven on fakes only
    (Q-42), relying on the shipped `pipeline_guard` rules proven live by PEAK_MODEL_CONCURRENCY.
- **Risks:**
  - DA-68 narrows guards of three archived features. The user chose on 2026-11-12 to record it in
    the DEFINE: `/iterate` named the three tests and the allowed narrowing in NFR-57 and AC-197.
  - The `V0x0_*` and `V073_*` constants must be computed from the tags at build; a typed value
    would make the CI checks meaningless.
  - `ruff format` could rewrap an existing line of `pipeline_guard.py` if the appended code changes
    its context; the AC-92 additions-only test catches it locally with the tags present.
- **Trade-offs:** One shared client with the shipped limits and a shorter statement wait, in return
  for bounded calls everywhere. One refusal line for every case, in return for a single rule that
  meets FR-107 and FR-108 and keeps the `plan()` text byte-equal. The idle check last, without a
  re-check, in return for the smallest window within the NFR-54 budget.
- **What I would do differently (with more budget or time):** Spike `databricks bundle summary -t dev
  -o json` and use its exact job ids as the primary source with the base-name match as a cross-check,
  which removes the prefix-format dependency and the full-page refusal; and give `pipeline_guard` a
  one-time, user-approved refactor in which `_read_job` delegates to `_read_named_job`, with the
  INGESTION_GUARD AC-92 diff test moved to "behaviour equal" goldens, so the copy disappears.
- **Next improvement:** Build entries 1 to 7, 12 and 13 in one commit with the tags present, compute
  the `V040`, `V060`, `V070` and `V073` constants from the tags with each file's own functions, and
  run `pytest` and `check_specs.py` before the live gate (U-09).

---

## Next Step

`/build .claude/sdd/features/DESIGN_RESET_GUARD.md`

---

## Change Log

| Date | Change | Why | Downstream impact |
|---|---|---|---|
| 2026-11-12 | Created from DEFINE_RESET_GUARD.md (Ready for Design, Q-40 to Q-43 answered): OD-51 to OD-55 resolved (DA-60 to DA-64), DA-65 to DA-72, guards G-59 to G-66, job-only mode and reset script shapes, line shapes, re-pins of four shipped tests (DA-68), runbook and ADR texts, 19-entry manifest (13 in the build PR, 6 at ship), test strategy for AC-189 to AC-202 with order and after-state rows, live plan with U-09; ADR 0014 drafted (Proposed). Status `Ready for Build` | Phase 2 of the SDD workflow | `/build` starts at entry 1 |
| 2026-11-12 | DA-68 wording aligned to the three pins it names (R1 to R3); Risks bullet updated after the user's `/iterate` of the DEFINE (NFR-57, AC-197 name the three tests) | User decision on DA-68 | None: manifest, tests and status unchanged |
