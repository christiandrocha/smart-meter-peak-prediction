# DEFINE: Reset Guard

> Phase 1. Requirements that can be tested. No implementation choices here.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | RESET_GUARD |
| **Date** | 2026-11-12 |
| **Author** | Christian |
| **Source** | Follow-up PEAK_MODEL F-03 together with PEAK_MODEL_CONCURRENCY F-02 (`.claude/sdd/follow-ups/F_PEAK_MODEL_03.md`: triage full cycle because E1 is `No`, done criteria DC-01 to DC-03; no BRAINSTORM: small feature cycle, as AC66_BOTH_LEGS); PEAK_MODEL BUILD_REPORT Issues row (line 269) and SHIPPED_2026-10-22 Follow-ups row PEAK_MODEL F-03 (line 193); PEAK_MODEL_CONCURRENCY SHIPPED_2026-10-22 Follow-ups row PEAK_MODEL_CONCURRENCY F-02 (line 160); ADR 0012 and ADR 0013; code read on main `de5535a` on 2026-11-12: `scripts/reset_peak_model_outputs.py`, `tests/test_peak_reset_script.py`, `src/smart_meter_peak_prediction/pipeline_guard.py`, `src/smart_meter_peak_prediction/peak_config.py`, `src/smart_meter_peak_prediction/peak_setup.py`, `resources/*.yml`, `pipelines/meter_pipeline.py`, `pipelines/household_data_quality.sql`, the notebooks under `notebooks/`, `tests/integration/conftest.py` (`job`, `pipeline`, `_job_named`, `PeakRunner.assert_ingestion_idle`), `docs/runbooks/peak_model.md` (sections "Concurrency with the ingestion job" and "9. Reset") |
| **Status** | Ready for Design |

Allowed status values: `Draft`, `Ready for Design`.

The user answered Q-40 to Q-43 on 2026-11-12 with the recommended defaults; the requirements were
written for those answers, so only the status and the pending notes changed.

Target release: v0.8.0 (minor, follow-up target "Next minor release after v0.7.3"; Q-43). This
feature closes PEAK_MODEL F-03 and PEAK_MODEL_CONCURRENCY F-02.

**ID numbering.** IDs continue the project-wide series: FR-105, NFR-53, AC-189, C-30, A-57, D-104,
Q-40 and OD-51 (last used: FR-104, NFR-52, C-29, A-56, D-103, Q-39 and OD-50 in AC66_ZERO_NEW_RUNS;
AC-188 in AC66_FIRST_READ_GATE). Checked on 2026-11-12 with a search of `.claude/sdd/` (archive and
follow-ups included) for higher numbers of each series (none found). Every ID of another spec is
written with that spec's name in front; unprefixed IDs are this feature's own.

**Table names.** The three tables the reset drops are, by `peak_config` and the shipped `plan()`
test: `<catalog>.silver.weather_hourly`, `<catalog>.ml.household_features_daily` and
`<catalog>.ml.household_labels_daily` (catalog `smart_meter_dev` by default). This document calls
them *the three tables*.

---

## Problem Statement

`scripts/reset_peak_model_outputs.py --confirm` drops the three tables so that the AC-66 rebuild leg
can rebuild them. Three gaps were measured on main `de5535a`: (1) `main()` builds the warehouse
client and runs `SELECT current_timezone()` before its `try`, so a missing SQL warehouse, a failed
query or an SDK error ends in a raw traceback instead of `refused, nothing dropped: ...` and exit
code 2; (2) nothing reads the job runs, so a `--confirm` while `smart_meter_peak_model` or
`smart_meter_peak_model_training` runs drops tables that a running task is writing or reading, which
fails that run (the training job's G-04 guard, a half-written MERGE in `build_features` or
`build_labels`) and leaves `dev` in a partial state that both AC-66 legs refuse; (3) `main()` has no
test, so the exit codes, the dry-run default and the order "every check, then the first DROP" are
unproven. The cost of (2) is a failed job run plus a full AC-66 sequence (snapshot, rerun leg,
reset, rebuild leg) to recover; the cost of (1) is an operator reading a traceback without knowing
whether anything was dropped.

---

## Users & Stakeholders

| User or consumer | Need | How they consume the output |
|---|---|---|
| User who runs the reset (the only person allowed to run the script, C-31) | Know before anything is dropped whether a peak job is running, which run blocks, and that a refusal dropped nothing; never read a traceback | Script output and exit code; `docs/runbooks/peak_model.md` section 9 |
| AC-66 evidence operator (rebuild leg after the reset) | A reset that cannot leave the three tables half rebuilt by a concurrent run | The reset's refusal line; the shipped AC-66 leg refusals (AC66_BOTH_LEGS FR-86) |
| Runs of `smart_meter_peak_model` and `smart_meter_peak_model_training` | Their tables are not dropped while they run | Unchanged job definitions (C-30) |
| Shipped callers of `pipeline_guard`: notebooks `check_pipeline_idle` (ADR 0012) and `check_silver_gold_idle` (ADR 0013), `PeakRunner.assert_ingestion_idle` in the integration tests | No change in behaviour, message or exit value when the module is generalised | Unchanged messages and exit values (FR-111, AC-197) |
| CI (`pytest` without the integration marker) | Prove every exit path of `main()` without a workspace or the Databricks SDK | Unit tests on fakes (AC-189 to AC-201) |
| Release reviewer | Copy the live dry-run output into the BUILD_REPORT | AC-202 |

---

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| No drop while a dependent job runs | DROP statements sent by `main()` when a job of the idle set has an active run or cannot be read (CI fakes) | 0 (AC-189, AC-190, AC-195) |
| No traceback before the first DROP | Paths of `main()` before the first DROP (client build, warehouse lookup, time-zone query, idle check, counts) that print a `Traceback` or exit with a code other than 2 on failure | 0 (AC-192) |
| `main()` tested | Exit paths of `main()` named in FR-105 to FR-112 without a unit test that names its AC | 0 (AC-189 to AC-196) |
| One definition of "active run" | Life-cycle state sets defined outside `pipeline_guard` in the reset script | 0 (AC-197) |
| Shipped guard unchanged | Shipped tests of `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py` and `tests/test_peak_reset_script.py` that fail or lose an assertion | 0 (AC-197) |
| Bounded, read-only check | Jobs API calls of the idle check per job; sleep calls; write calls on jobs or pipelines | at most 4; 0; 0 (AC-198, AC-200) |

---

## Scope

**In scope:**
- An idle check in `scripts/reset_peak_model_outputs.py` over the jobs `smart_meter_peak_model` and
  `smart_meter_peak_model_training` (the *idle set*, D-104, Q-40), run before the first DROP and in
  the dry run as well (D-105), failing closed (FR-105 to FR-107, FR-110).
- Moving the client and warehouse set-up and the time-zone query inside the refusal handling, so
  every failure before the first DROP ends in one `refused, nothing dropped: ...` line and exit code
  2 (FR-108); the time-zone mismatch line takes the same prefix.
- A defined outcome for a failure during the drop phase (FR-112).
- Generalising `src/smart_meter_peak_prediction/pipeline_guard.py` so its job identity and
  active-run rules can read a job other than `smart_meter_ingestion`, with the shipped peak mode and
  pipeline-only mode unchanged (FR-111; PEAK_MODEL_CONCURRENCY F-02).
- Unit tests on fakes that call `main()` (FR-113; DC-03), next to the three shipped `plan()` tests.
- Text: runbook section 9 and the script's module docstring (FR-114); the ADR question of OD-51.
- One user-run live dry run on `dev` with the jobs idle (FR-115, AC-202; Q-42).
- At `/ship`: CHANGELOG entry for the release of Q-43; the follow-up file `F_PEAK_MODEL_03.md`
  closed; the Follow-ups rows PEAK_MODEL F-03 and PEAK_MODEL_CONCURRENCY F-02 updated to point to
  this feature.

**Out of scope:**
- Checking `smart_meter_ingestion` or the pipeline `smart_meter_silver_gold`: neither reads nor
  writes the three tables (A-59, D-104). Picked up only if the user answers Q-40 otherwise.
- An override flag or variable for the idle check (FR-110; Q-41).
- Closing the race window between the check and the first DROP with a lock: none exists across jobs
  (C-32). Not scheduled.
- Any change under `resources/`, `notebooks/`, `pipelines/` or to `databricks.yml` (C-30).
- A live refusal on `dev` while a peak run is active (costs one job run; Q-42 recommends against it).
  Not scheduled.
- Changing the three tables, the expected row counts, `--allow-other-counts`,
  `--skip-snapshot-check` or the snapshot rule of `plan()`.
- Pausing, cancelling or waiting for a run: the script never waits and never writes to a job.

---

## Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-105 | Before the first DROP, and in a dry run as well (D-105), the reset shall read the active runs of each job of the idle set, `smart_meter_peak_model` and `smart_meter_peak_model_training` (D-104), and refuse when either job has a run whose life-cycle state is not `TERMINATED`, `SKIPPED` or `INTERNAL_ERROR`; an unknown, future or missing state counts as active (the shipped rule of `pipeline_guard.TERMINAL_RUN_STATES`, PEAK_MODEL_CONCURRENCY G-16). Every run of the job counts, whatever its trigger or task subset (`--only` runs included) | Must |
| FR-106 | The idle check shall fail closed (PEAK_MODEL_CONCURRENCY D-45): when the state of a job of the idle set cannot be established, the reset refuses. Cases: the workspace client cannot be built, no deployed job or more than one deployed job matches the job's base name, the resolved id names another job, a Jobs API read raises (including a denied permission), or the run list cannot be read. No case is treated as idle | Must |
| FR-107 | A refusal of the idle check shall print a first line that starts with `refused, nothing dropped: ` and name, for each blocking run, the job base name, the job id, the run id, the life-cycle state and the start time as UTC text ending in `Z` (or `not started`), and, for each unreadable job, the job base name and what could not be read; the exit code is 2 and no DROP statement is sent. When both jobs are idle, the output holds one line per job of the idle set with its base name, its job id and `0 active runs` | Must |
| FR-108 | Every failure before the first DROP shall end in exactly one output line that starts with `refused, nothing dropped: `, without a traceback, and exit code 2, with or without `--confirm`. This covers building the workspace client (including a missing `databricks-sdk` or failed authentication), the warehouse lookup (`no SQL warehouse found`), any SDK exception during the lookup or a query, a failed or timed-out `SELECT current_timezone()`, a failed count query, and a session time zone other than `UTC`, `Etc/UTC` or `GMT` (whose shipped line `refused: the warehouse session time zone is ...` takes the common prefix). The refusals of `plan()` keep their shipped text after the prefix | Must |
| FR-109 | Every check (time zone, idle set, row counts, Bronze weather rows, snapshot) shall complete before the first DROP. Without `--confirm` no DROP is ever sent: when every check passes, the dry run prints the three shipped `would DROP TABLE ...` lines and the dry-run line and exits 0. With `--confirm` and every check passing, the reset sends exactly the three shipped DROP statements, in the shipped order, and exits 0 | Must |
| FR-110 | No command-line option, environment variable or argument shall skip or weaken the idle check. `--allow-other-counts` and `--skip-snapshot-check` keep their shipped meaning and have no effect on it; the option set of the script stays `--confirm`, `--allow-other-counts`, `--skip-snapshot-check` (and `-h`). Q-41 | Must |
| FR-111 | The identity and active-run rules of the idle check shall come from `smart_meter_peak_prediction.pipeline_guard` (PEAK_MODEL_CONCURRENCY F-02), generalised so the expected job name is no longer fixed to `INGESTION_JOB`. For the same inputs, the shipped peak mode (`check`, `run`, `enforce`, `GuardReport.message`, `GuardReport.exit_value`) and pipeline-only mode (`check_pipeline`, `run_pipeline_check`, `enforce_pipeline`, `PipelineReport.message`, `PipelineReport.exit_value`) return byte-equal results to tag `v0.7.3`; `READ_CALLS` and `PIPELINE_READ_CALLS` keep their values; the module still imports no Databricks SDK | Must |
| FR-112 | When a DROP statement fails, the reset shall send no further DROP and print one line that names the tables already dropped (or `none`) and the table whose DROP failed with the error text, without a traceback and without the words `nothing dropped`, and exit with code 1 (D-108) | Should |
| FR-113 | Unit tests on fakes for the warehouse and the workspace client shall call `main()` and cover the dry run, `--confirm` with the idle set idle, each refusal path of FR-105 to FR-108, the drop-phase failure of FR-112 and the order of FR-109; each test names its AC. The three shipped `plan()` tests stay by name with no assertion removed. The tests run without `databricks-sdk` installed (DC-03) | Must |
| FR-114 | `docs/runbooks/peak_model.md` section 9 and the script's module docstring shall state the idle check: the two jobs it reads, that it also runs in the dry run, the refusal prefix, the action (wait until the named run ends, then run the reset again; for an unreadable job, fix the named cause), that no flag skips it, and the remaining race window (C-32). The runbook bullet "Training" of "Concurrency with the ingestion job" names the reset as refusing while a training run is active | Should |
| FR-115 | The user shall run the reset once as a dry run on `dev` from the build branch with both jobs idle, and the BUILD_REPORT shall hold its full output and exit code. No `--confirm` run is part of this feature's evidence. Q-42 | Should |

---

## Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-53 | Security | Before the first DROP the reset calls on the workspace client only the Jobs API reads of `pipeline_guard.READ_CALLS` (`jobs.get`, `jobs.list`, `jobs.list_runs`), the shipped `warehouses.list` and the Statement Execution calls for `SELECT` statements (plus the shipped `cancel_execution` of a timed-out statement); no call starts, cancels, repairs or edits a job run or a pipeline update. No output line holds a token, a workspace host or a URL: no line contains `https://`, `http://`, `dapi`, `Bearer` or `@`; error text is redacted as `pipeline_guard._describe_error` does (first line, at most 200 characters) |
| NFR-54 | Cost and latency | The idle check makes at most 4 Jobs API calls per job of the idle set (at most 8 in total), lists at most `pipeline_guard.MAX_RUNS_READ` (25) runs per job, makes 0 `time.sleep` calls and never polls or waits; it starts 0 job runs and sends 0 SQL statements |
| NFR-55 | Time handling | Idleness is decided by life-cycle state only, never by comparing a time with the local clock (golden rule 5); every time in the output matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` or is the text `not started`; a naive, empty or unparseable start time is shown as `not started` (`pipeline_guard.utc_text`) |
| NFR-56 | Idempotency | Two calls of `main()` with the same fakes and arguments give byte-equal output and the same exit code. A refused run sends 0 statements other than `SELECT`, writes no file and changes no table; a dry run sends 0 statements other than `SELECT` |
| NFR-57 | Compatibility | `pytest` without the integration marker reports 0 failures, including every shipped test; every test function of `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py` and `tests/test_peak_reset_script.py` at tag `v0.7.3` exists with the same name and at least as many `assert` statements; `scripts/check_specs.py` reports 0 errors; `databricks-sdk` stays out of the runtime `dependencies` of `pyproject.toml` (E7) |

---

## Data Contracts

This feature writes no table and no shared contract under `docs/contracts/`. It reads two platform
listings, drops the three tables as shipped, and prints its outcome. Contracts are inline because no
other feature shares them.

| Dataset / topic | Owner | Grain | Key | Freshness | Contract file |
|---|---|---|---|---|---|
| Job definitions of `smart_meter_peak_model` and `smart_meter_peak_model_training` (read, Jobs API) | Platform (jobs owned by PEAK_MODEL) | One deployed job | `job_id`; the deployed name with the development prefix `[dev <user>] ` stripped equals the base name and is unique (PEAK_MODEL_CONCURRENCY G-14) | Read once per reset run, before the first DROP and in the dry run | Inline: `job_id` (positive integer), `settings.name`. How the id is found is OD-51 |
| Active runs of each job of the idle set (read, Jobs API) | Platform | One job run | `run_id`, scoped by `job_id` | Read once per job per reset run, after the job definition | Inline: `run_id`, `state.life_cycle_state` (enum, compared by its value text), `start_time` (epoch milliseconds, optional); at most 25 runs read (NFR-54) |
| The three tables (dropped with `--confirm`, counted in every run) | PEAK_MODEL | As in the PEAK_MODEL DEFINE Data Contracts (one weather hour; one household per feature date; one household per target date) | As shipped (`weather_ts`; `household_id`, `feature_date`; `household_id`, `target_date`) | Rebuilt by the AC-66 rebuild leg or the next daily run | Inline in the archived PEAK_MODEL DEFINE; unchanged |
| Reset output and exit code (stdout, copied into the BUILD_REPORT for AC-202) | RESET_GUARD | One reset run | None: not stored | Written when the script ends | Inline: exit 0 (dry run or drop done), 2 (refused, nothing dropped), 1 (drop phase failed, FR-112); refusal lines start `refused, nothing dropped: `; idle lines name each job, its job id and `0 active runs` (FR-107) |

---

## Acceptance Criteria

**CI** criteria run in `pytest` without the Databricks SDK or a workspace, on fakes for the warehouse
and the workspace client injected into `main()` (how: OD-54). **Live** criteria run on `dev`, by the
user (C-31). DC-01 of the follow-up is AC-189 and AC-190; DC-02 is AC-192; DC-03 is AC-189 to AC-196
together, with AC-191, AC-193 and AC-194 for the dry run, the idle `--confirm` and the order.

| ID | Level | Given | When | Then |
|---|---|---|---|---|
| AC-189 | CI | Fakes in which every table check passes; for each job of the idle set in turn, one active run (run id 7, start time epoch ms `1762941600000`) in each of the states `QUEUED`, `PENDING`, `RUNNING`, `TERMINATING`, `BLOCKED`, `WAITING_FOR_RETRY`, a future value `NEW_STATE` and a missing state, while the other job has none; plus one case with a run whose start time is missing | `main(["--confirm"])` runs, then `main([])` | Each call exits 2; the first output line starts with `refused, nothing dropped: `; the output names the busy job's base name, its job id, run id `7`, the state (or `UNKNOWN` for a missing one) and `2025-11-12T10:00:00Z` (or `not started` for the missing start time); 0 DROP statements are sent |
| AC-190 | CI | Fakes in which every table check passes and, in turn: the client factory raises; `jobs.get` raises a generic error; `jobs.get` raises an error with `error_code` `PERMISSION_DENIED`; no deployed job matches a base name; two deployed jobs match it; the resolved id names another job; `jobs.list_runs` raises | `main(["--confirm"])` runs | Each call exits 2; the first line starts with `refused, nothing dropped: ` and names the job base name and what could not be read; 0 DROP statements are sent; no output contains `Traceback` |
| AC-191 | CI | Both jobs with runs listed only in `TERMINATED`, `SKIPPED` or `INTERNAL_ERROR` (a list race), every table check passing, a call log shared by the fakes | `main(["--confirm"])` runs | Exit 0; the output holds one line per job with its base name, job id and `0 active runs`; the warehouse received exactly `DROP TABLE smart_meter_dev.silver.weather_hourly`, `DROP TABLE smart_meter_dev.ml.household_features_daily`, `DROP TABLE smart_meter_dev.ml.household_labels_daily`, in that order; the `done.` line is printed |
| AC-192 | CI | In turn: the client factory raises; the warehouse list is empty; the warehouse list raises an SDK exception (`RuntimeError`); `SELECT current_timezone()` ends `FAILED`; it raises an SDK exception; it returns `Europe/Berlin` | `main([])` and `main(["--confirm"])` run | Each call prints exactly one line, which starts with `refused, nothing dropped: `; no output contains `Traceback`; exit 2; 0 DROP statements and 0 count queries are sent |
| AC-193 | CI | A call log shared by all fakes; (a) every check passing; (b) to (f) exactly one failing check in turn: time zone, idle set, a row count, empty Bronze weather, missing snapshot | `main(["--confirm"])` runs | (a) Every Jobs API read, the time-zone query and every count query appear in the log before the first DROP. (b) to (f) The log holds no DROP; exit 2; the first line starts with `refused, nothing dropped: ` |
| AC-194 | CI | Both jobs idle, every table check passing | `main([])` runs | Exit 0; the Jobs API reads of the idle check appear in the call log; the output holds the idle line of each job, the three `would DROP TABLE ...` lines and the line starting `dry run:`; 0 statements other than `SELECT` are sent |
| AC-195 | CI | `smart_meter_peak_model_training` with one `RUNNING` run; every table check passing; every environment variable named in the script's docstring set | `main(["--confirm", "--allow-other-counts", "--skip-snapshot-check"])` runs; the parser's options are listed | Exit 2 and 0 DROP statements; the option strings of the parser are exactly `-h`, `--help`, `--confirm`, `--allow-other-counts`, `--skip-snapshot-check` |
| AC-196 | CI | Both jobs idle, every check passing, a fake warehouse whose second DROP ends `FAILED` | `main(["--confirm"])` runs | Exit 1; the first DROP and the failed second DROP were sent, the third was not; one line names `smart_meter_dev.silver.weather_hourly` as dropped and `smart_meter_dev.ml.household_features_daily` as failed with the error text; no output contains `Traceback` or `nothing dropped` |
| AC-197 | CI | The repository at the feature commit and tag `v0.7.3` (or golden values taken from it) | The trees are compared, fixed fake inputs are run through both shipped modes, and the reset module is parsed | Every test function of `tests/test_pipeline_guard.py`, `tests/test_ingestion_guard.py` and `tests/test_peak_reset_script.py` at `v0.7.3` exists with the same name and at least as many `assert` statements, and passes; for at least one idle, one busy and one unreadable input of each mode, `message()` and `exit_value()` equal the `v0.7.3` values byte for byte; `READ_CALLS` and `PIPELINE_READ_CALLS` equal `v0.7.3`; `pipeline_guard` imports no `databricks` module; the reset module imports `pipeline_guard` and defines no string set of run life-cycle states; no file under `resources/`, `notebooks/`, `pipelines/` and no `databricks.yml` differs from `v0.7.3` |
| AC-198 | CI | A recording fake client on every path of AC-189 to AC-196; an error text that contains `Bearer abc`, `dapi123` and `https://example.invalid/x` raised by `jobs.get` | `main` runs on each path | Before the first DROP the only client methods called are in `pipeline_guard.READ_CALLS`, `warehouses.list` and the Statement Execution methods for `SELECT` statements; no output line contains `https://`, `http://`, `dapi`, `Bearer` or `@`; the error text appears redacted |
| AC-199 | CI | The fakes of one busy case (AC-189), one unreadable case (AC-190), one connection failure (AC-192) and the idle dry run (AC-194) | `main` runs twice on each | The two outputs are byte-equal and the exit codes equal; on the refused cases the warehouse received 0 statements other than `SELECT` and no file under the repository changed |
| AC-200 | CI | `time.sleep` replaced by a counter; the fakes of AC-189 (one case per job), AC-190 (each case) and AC-194 | `main` runs | The fake client records at most 4 Jobs API calls per job of the idle set and at most 8 in total; `time.sleep` is called 0 times; at most 25 runs are read per job |
| AC-201 | CI | `docs/runbooks/peak_model.md` and the script's module docstring at the feature commit | The texts are read | Section 9 and the docstring name `smart_meter_peak_model` and `smart_meter_peak_model_training` as the jobs the reset checks, state that the dry run checks them too, contain `refused, nothing dropped: `, state that no flag skips the check and name the window between the check and the DROP; the "Training" bullet of "Concurrency with the ingestion job" names the reset |
| AC-202 | Live | `dev` deployed from the build branch; no run of `smart_meter_peak_model` or `smart_meter_peak_model_training` active; the three tables present with the expected counts; the AC-66 snapshot present | The user runs `python scripts/reset_peak_model_outputs.py` (dry run, no `--confirm`) | Exit 0; the output names both jobs with their deployed job ids and `0 active runs`, and the three `would DROP TABLE ...` lines; the three tables keep their row counts; the full output is copied into the BUILD_REPORT. Q-42 |

### Traceability (FR and NFR to AC)

| Requirement | Covered by |
|---|---|
| FR-105 | AC-189, AC-191, AC-194 |
| FR-106 | AC-190 |
| FR-107 | AC-189, AC-190, AC-191, AC-194 |
| FR-108 | AC-192, AC-193 (b) |
| FR-109 | AC-191, AC-193, AC-194 |
| FR-110 | AC-195 |
| FR-111 | AC-197 |
| FR-112 | AC-196 |
| FR-113 | AC-189 to AC-196, AC-197 (shipped `plan()` tests kept) |
| FR-114 | AC-201 |
| FR-115 | AC-202 |
| NFR-53 | AC-198 |
| NFR-54 | AC-200 |
| NFR-55 | AC-189 (UTC text and `not started`) |
| NFR-56 | AC-199 |
| NFR-57 | AC-197; `pytest` and `check_specs.py` at the feature commit |

Coverage of the required kinds: correctness AC-189, AC-191, AC-194, AC-202; idempotency and
reprocessing AC-199 (same inputs twice, a refusal changes nothing) and AC-191 (the reset drops the
same three statements in the same order); data quality of the read AC-189 (unknown, future and
missing states, missing start time), AC-190 (missing, duplicate and mismatched jobs); failure paths
AC-190, AC-192, AC-193 (b to f), AC-196.

---

## Decisions and Open Items

### Derived in this phase (D-104 confirmed by the user's answer to Q-40, 2026-11-12)

| ID | Statement | Derived from | Where it is used |
|---|---|---|---|
| D-104 | The idle set is `smart_meter_peak_model` and `smart_meter_peak_model_training`. The daily job writes all three tables (`build_weather_silver` writes `silver.weather_hourly`, `build_features` and `build_labels` write the two ML tables, `score_predictions` reads them) and starts its own pipeline update, which shows as an active run of that job. The training job reads both ML tables by Delta version and fails its G-04 guard when they change. The ingestion job (`setup_catalog`, `ingest_files`, `ingest_kafka`, `check_silver_gold_idle`, `refresh_silver_gold`) and the pipeline (`meter_pipeline.py`, `household_data_quality.sql`) reference none of the three tables (A-59). The source row's "ingestion job and the three peak jobs" predates the current bundle, which has two peak jobs | Code reading of `resources/*.yml`, `notebooks/`, `pipelines/` and `peak_config` on 2026-11-12; follow-up Self-Review "DEFINE must fix the exact set" | FR-105, Scope, Q-40 |
| D-105 | The dry run runs the idle check as well, so a dry run predicts the outcome of `--confirm`; the shipped dry run already runs every `plan()` check and exits 2 on a refusal | `main()` on `de5535a` (lines 168 to 177); runbook section 9 "dry run: prints the plan and the counts" | FR-105, FR-109, AC-194 |
| D-106 | Full cycle without a BRAINSTORM: the follow-up triage gives E1 `No` (the change to `pipeline_guard.py` under `src/`) | `F_PEAK_MODEL_03.md` Triage | Metadata |
| D-107 | The rules for "active run" and "job identity" exist once, in `pipeline_guard`; the reset adds no state set of its own | PEAK_MODEL_CONCURRENCY F-02; ADR 0012 Consequences ("one definition of active") | FR-111, AC-197 |
| D-108 | A failure after the first DROP exits with code 1, not 2: exit code 2 keeps the meaning "refused, nothing dropped", which the runbook and the AC-66 order rely on | Shipped exit codes of `main()` (0 and 2 only) | FR-112, AC-196, Data Contracts |
| D-109 | The window between the idle read and the DROP statements is accepted, as for the pre-checks of ADR 0012 and ADR 0013 (C-32); on `dev` the daily schedule is paused by development mode, so only a person starts a run (AC66_ZERO_NEW_RUNS A-53). Whether the check is repeated right before the first DROP is OD-53 | PEAK_MODEL_CONCURRENCY C-11; ADR 0012 Consequences | FR-114, C-32 |

### Questions for the user

| ID | Question | Recommended answer | User answer (2026-11-12) |
|---|---|---|---|
| Q-40 | Which objects must be idle before a reset: only the two jobs that read or write the three tables (`smart_meter_peak_model`, `smart_meter_peak_model_training`), or also `smart_meter_ingestion` and the pipeline `smart_meter_silver_gold`, as the PEAK_MODEL F-03 row literally says? | The two peak jobs only (D-104). The ingestion job and the pipeline never touch the three tables (A-59), a pipeline update started by the peak job is already an active run of that job, and the AC-66 rebuild leg that follows the reset checks the ingestion job and the pipeline itself (`PeakRunner.assert_ingestion_idle`). Adding them would refuse resets for a reason unrelated to the dropped tables and add two reads. If you answer "all four", `/iterate` widens FR-105 and AC-189 to AC-191 to the ingestion job's runs and the pipeline's state | The two peak jobs only (D-104 confirmed) |
| Q-41 | May a flag (like `--allow-other-counts` or `--skip-snapshot-check`) skip the idle check? | No override (FR-110). The check refuses only for a cause a person can fix: wait for the named run to end, or fix the named permission or deployment; skipping it is exactly the drop under a running task that PEAK_MODEL F-03 exists to prevent. If you answer Yes, `/iterate` replaces FR-110 and AC-195 with a named flag that prints the blockers it ignored | No override (FR-110) |
| Q-42 | Is a live leg in scope, or only unit tests with fakes? | One user-run dry run on `dev` with both jobs idle (FR-115, AC-202): it costs no job run and no drop, and it is the only proof that the two deployed jobs are found under their development-mode names (A-57, OD-51). No live busy refusal: it needs a job run started for the test, and the busy and fail-closed rules are the shipped `pipeline_guard` ones, already proven live by PEAK_MODEL_CONCURRENCY and INGESTION_GUARD. No `--confirm` run. If you answer "fakes only", AC-202 becomes `Deferred: <reason>` at build; if you want the busy leg, `/iterate` adds one live AC | One user-run dry run on `dev` (FR-115, AC-202) |
| Q-43 | Release level and package version: v0.8.0 (minor) with package version 0.8.0, or another? | v0.8.0, as the follow-up target says ("Next minor release after v0.7.3"), because the reset gains a new refusal condition and exit code 1, and `src/` changes. Package version 0.8.0 in `pyproject.toml` and `src/smart_meter_peak_prediction/__init__.py`, as PEAK_MODEL F-06 aligned it with the tag when `src/` changed (it stayed 0.4.1 since v0.4.1 only because `src/` did not change) | v0.8.0, package version 0.8.0 |

### Open questions for `/design`

| ID | Question |
|---|---|
| OD-51 | How the reset finds the job ids, since it runs outside the bundle and bundle references are not available: lookup by base name with the development prefix stripped (prior art: `tests/integration/conftest.py` `_job_named`), `databricks bundle summary` of the target, or environment variables. ADR 0012 rejected name lookup for the in-job check because it can match another target's or user's deployment; uniqueness failing closed (FR-106) limits that risk here. Decide whether this needs a new ADR or a note on ADR 0012 (follow-up triage E3 `Unknown`) |
| OD-52 | The shape of the `pipeline_guard` change: an expected-name parameter for `_read_job`, a new public function and report for "jobs idle" (one or more jobs, no pipeline), and the constant for the training job's name; keeping the shipped modes byte-equal (FR-111) and `READ_CALLS` unchanged |
| OD-53 | The order of the checks (idle check before or after the SQL checks), whether refusals of several checks are reported together, and whether the idle check is repeated right before the first DROP to shrink the window of D-109 (cost: up to 8 more calls, NFR-54) |
| OD-54 | How fakes enter `main()` (factory parameters for the workspace client and the warehouse, or module attributes replaced by the tests), whether the reset's workspace client is shared with the warehouse runner, and whether it is built with `pipeline_guard.CLIENT_LIMITS` through `Config` (retry 60 s, HTTP 30 s) |
| OD-55 | The exact refusal line shapes: one line for several blockers or a first line plus indented lines (FR-107 needs only the first-line prefix; FR-108 needs exactly one line), and the idle line text of FR-107 |

---

## Constraints & Assumptions

| ID | Type | Statement | Validated? |
|---|---|---|---|
| METER_INGESTION C-01 to C-07 | Constraint | Inherited: Free Edition serverless only, daily quota, no secrets in code, UTC end to end | Yes |
| C-30 | Constraint | Production change limited to `src/smart_meter_peak_prediction/pipeline_guard.py` (and the package version of Q-43); no change under `resources/`, `notebooks/`, `pipelines/` or to `databricks.yml`; the peak, training and ingestion jobs behave as at `v0.7.3`; the archived PEAK_MODEL and PEAK_MODEL_CONCURRENCY DEFINE and DESIGN are not edited (E4) | Yes (follow-up triage) |
| C-31 | Constraint | The reset is run by the user, never by an agent (script docstring). An agent runs neither the dry run nor `--confirm` unless the user authorizes that run, and the authorization is recorded in the BUILD_REPORT Deviations table with the user's words and the date (AC66_ZERO_NEW_RUNS C-27) | Yes |
| C-32 | Constraint | No lock exists across jobs (PEAK_MODEL_CONCURRENCY C-11): a run started between the idle read and the DROP statements is not seen | Yes (accepted for ADR 0012 and ADR 0013) |
| C-33 | Constraint | `databricks-sdk` is not a runtime dependency; the script and `pipeline_guard` import it lazily or not at all, so CI needs no SDK | Yes (code reading: `Warehouse.__init__` imports it inside the method; `pipeline_guard` never imports it) |
| A-57 | Assumption | On `dev`, each job of the idle set is deployed exactly once under `[dev <user>] <base name>`, and the user's profile sees no other deployment with the same base name | Partly: PEAK_MODEL_CONCURRENCY DA-23 found the ingestion job uniquely by its deployed name (spike 06), and the integration fixtures `peak_job` and `training_job` find both jobs by base name; to be shown live by AC-202. If false, the check fails closed (safe direction) |
| A-58 | Assumption | `jobs.list_runs(job_id=..., active_only=True)` lists a run as soon as `run_now` returned, including queued runs, `--only` runs and runs waiting for a task retry | Partly: spike 06 and the PEAK_MODEL_CONCURRENCY live tests for the ingestion job; a lag would let a reset through right after a run start (unsafe direction, small window, as C-32) |
| A-59 | Assumption | The ingestion job and the pipeline never read or write the three tables | Yes: code reading on 2026-11-12, no reference to `silver_weather_table`, `features_table`, `labels_table` or the three table names in `pipelines/`, `notebooks/setup_catalog.py`, `notebooks/ingest_files.py`, `notebooks/ingest_kafka.py`, `notebooks/check_silver_gold_idle.py` |
| A-60 | Assumption | The user's local profile may read both jobs and their runs (the user deployed them) | Pending: shown by AC-202; a denied read fails closed (FR-106) |

---

## Clarity Score

| Dimension | Score (0-3) | Note |
|---|---|---|
| Problem | 3 | Three measured gaps on `de5535a` with line references, the failure each causes (traceback, drop under a running task, untested exit paths) and the recovery cost |
| Users | 3 | The user who runs the reset, the AC-66 operator, the two protected jobs, the three shipped `pipeline_guard` callers, CI and the reviewer, each with where they read the outcome |
| Scope | 3 | The idle set is fixed from the code (D-104) and confirmed by the user (Q-40), production change fenced to one module (C-30); override, live leg and release answered (Q-41 to Q-43) |
| Acceptance criteria | 3 | Thirteen criteria, twelve CI on fakes with call logs for the order, one live dry run; every FR and NFR covered; DC-01 to DC-03 mapped |
| Constraints | 2 | A-57 and A-60 pending until AC-202; the id lookup (OD-51) must work around ADR 0012's rejection of name lookup; the race window (C-32) stays |
| **Total** | **14/15** | Gate: 12 or more |

---

## Self-Review

- **Weak points:**
  - The check proves "no active run at the moment of the read", not "no run during the drop" (C-32,
    D-109). On `dev` only a person starts runs, so the window is small, but it is not closed.
  - D-104 narrows the follow-up's literal wording (ingestion job and pipeline left out). The reasoning
    rests on code reading (A-59); a future task that writes one of the three tables from the
    ingestion job or the pipeline would silently fall outside the check. The user accepted the
    two-job set (Q-40, 2026-11-12).
  - AC-197 counts `assert` statements to show that no shipped assertion was removed; it catches
    removal, not a weakened condition. Review still reads the diff of the shipped test files.
  - FR-108 changes the shipped time-zone refusal text (`refused:` becomes `refused, nothing dropped:`).
    Nothing parses it today, but it is a visible text change.
- **Risks:**
  - Generalising `_read_job` touches the module behind two daily pre-checks. A careless change could
    alter their messages or exit values; AC-197 pins them byte for byte against `v0.7.3`.
  - Name lookup outside the bundle (OD-51) can find another user's deployment or none; FR-106 makes
    both a refusal, which is safe but can block a legitimate reset until the cause is fixed, with no
    override (Q-41).
  - A slow or failing Jobs API now blocks the reset; the shipped client limits (60 s retry, 30 s HTTP)
    bound the wait only if `/design` applies them (OD-54).
- **Trade-offs:**
  - Running the idle check in the dry run (D-105) costs up to 8 reads per dry run and makes the dry
    run fail while a job runs, in return for a dry run that predicts `--confirm`.
  - Exit code 1 for a drop-phase failure (D-108) adds a third code, in return for keeping code 2
    truthful ("nothing dropped").
  - Reusing `pipeline_guard` (FR-111) means a `src/` change and a full cycle for a user-run script, in
    return for one definition of "active run" across the jobs, the tests and the reset.
- **What I would do differently:** State in the first DEFINE of a destructive script which jobs must
  be idle and that `main()` itself is under test; the PEAK_MODEL criteria covered `plan()` only, so
  the set-up and the run check fell outside every AC.
- **Next improvement:** In `/design`, settle OD-51 first (it decides whether an ADR is needed and what AC-202
  shows), then OD-52 with golden values of the shipped `pipeline_guard` messages taken from `v0.7.3`.

---

## Next Step

`/design .claude/sdd/features/DEFINE_RESET_GUARD.md`

---

## Change Log

| Date | What changed | Why | Downstream impact |
|---|---|---|---|
| 2026-11-12 | Created: FR-105 to FR-115, NFR-53 to NFR-57, AC-189 to AC-202, C-30 to C-33, A-57 to A-60, D-104 to D-109 (derived), Q-40 to Q-43, OD-51 to OD-55. Status `Draft` | Phase 1 of the SDD workflow, from follow-ups PEAK_MODEL F-03 and PEAK_MODEL_CONCURRENCY F-02 | `/design` can start once Q-40 to Q-43 are answered; the requirements are written for the recommended answers |
| 2026-11-12 | User answered Q-40 to Q-43 with the recommended defaults; status `Ready for Design`; clarity 14/15 (Scope 3) | User answers in session | `/design` can start; no requirement changed |
