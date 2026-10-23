# BRAINSTORM: Ingestion Guard

> Phase 0. Explore intent and approaches before capturing requirements.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | INGESTION_GUARD |
| **Date** | 2026-10-23 |
| **Author** | Christian |
| **Status** | Ready for Define |

Allowed status values: `Exploring`, `Ready for Define`.

---

## Initial Idea

**Raw input:** Harden the shipped `smart_meter_ingestion` job (v0.1.0):

1. Set `disable_auto_optimization: true` on `ingest_kafka`, so that serverless auto-optimization
   stops retrying it although `max_retries` is 0 (METER_INGESTION F-02, PEAK_MODEL F-05; cause D-21
   in `archive/PEAK_MODEL/BUILD_REPORT_PEAK_MODEL.md`).
2. Add a reverse pre-check task before the pipeline task of `smart_meter_ingestion`. It reuses
   `pipeline_guard` (PEAK_MODEL_CONCURRENCY, ADR 0012) and fails at once, naming the blocker, when
   the shared pipeline is busy (PEAK_MODEL_CONCURRENCY F-01, D-44).
3. Optional: the reset script's active-run check through `pipeline_guard`, plus a `main()` test
   (PEAK_MODEL F-03, PEAK_MODEL_CONCURRENCY F-02). Moved to Out of Scope (D-52).

**Context observed:**

| Aspect | Observation | Implication |
|---|---|---|
| Existing code or data | `smart_meter_ingestion` has four tasks: `setup_catalog`, then `ingest_files` and `ingest_kafka` in parallel, then the pipeline task `refresh_silver_gold` (F-32). `pipeline_guard` already reads the pipeline's overall state and `latest_updates` and fails closed (F-34), but its job check and its messages are fixed to the peak job's direction (F-35) | Reuse the pipeline half of `pipeline_guard`; generalise it additively so the peak job's behaviour and its 28 unit tests stay unchanged |
| Platform constraints | Free Edition: serverless only, at most 5 concurrent job tasks, a daily quota (ADR 0001, `.claude/kb/databricks/free-edition.md:11,15`). No lock across two jobs on one pipeline (C-11). Serverless auto-optimization retries tasks despite `max_retries: 0` (D-21). Spike 06 validated the guard on serverless environment version 2 with `databricks-sdk` 0.40.0 only | One short sequential task; no waiting or polling; run the check on environment version 2; switch off auto-optimization explicitly |
| Shipped pins | AC-62 (PEAK_MODEL) and AC-78 (PEAK_MODEL_CONCURRENCY) pin `resources/smart_meter_ingestion.job.yml` byte for byte to tag `v0.1.0` (F-41). The archived documents cannot be edited | This feature supersedes the ingestion-file clause of those ACs explicitly with a new AC and a new pin (D-53) |
| Relevant modules / KBs | databricks (Asset Bundles, jobs, Lakeflow pipeline), kafka (`ingest_kafka`, Bronze as replay source, ADR 0006) | Bundle-level change and a notebook task; Bronze is still ingested when the check refuses |

---

## Discovery Questions & Answers

All answers are the user's (Christian, 2026-10-23).

| # | Question | Answer | Impact |
|---|---|---|---|
| 1 | Name and release of the feature? | INGESTION_GUARD, release v0.4.0 | Document names; package version and tag `v0.4.0` at ship |
| 2 | Purpose: what must be true afterwards, and how is it measured? | (a) No silent retry of `ingest_kafka`: a failed run shows exactly 1 attempt, checked by extending the AC-10 live test. (b) No refused pipeline update from the ingestion job when a conflict is visible at check time; the run fails at once with a message naming the blocker. Target: 0 refused ingestion refreshes when an update was visible | Two success criteria for DEFINE; AC-10 live test gains an attempt count |
| 3 | What does the reverse check block on: (a) the pipeline only, (b) any active peak daily run plus the pipeline, (c) stage-aware peak runs plus the pipeline? Does it include the training job? | (a) Pipeline only: overall state plus `latest_updates`; `IDLE` and `FAILED` pass, `DELETED` and unreadable fail closed (G-21). No training job, no peak job id | Approach A; no bundle reference to the peak job (F-37), no mutual refusal (F-38) |
| 4 | Must the message name the peak run, or is the update enough? | The update (id, state, UTC creation time) is enough; naming the peak run is out of scope | Follows from 3; the peak run id is not available without the peak job id |
| 5 | Where does the check run: first task, or directly before `refresh_silver_gold`? | Directly before `refresh_silver_gold`, after `ingest_files` and `ingest_kafka` | Shortest race window; a refusal costs the Silver/Gold refresh only, Bronze is still ingested (F-43) |
| 6 | Which tasks get `disable_auto_optimization: true`? | `ingest_kafka` and the new check task only. `ingest_files` is unchanged. Whether the setting applies to a `pipeline_task` is an assumption; if it does not resolve, it is Out of Scope | A-25; `refresh_silver_gold` unchanged in v0.4.0 |
| 7 | Is item 3 (reset script guard and `main()` test) in scope? | No. Out of Scope, next release | Smaller feature; the reset script needs a name-based, multi-job check (F-36) |
| 8 | How are the shipped pins handled? | A new AC supersedes the ingestion-file clause of AC-62 and AC-78 and pins the new ingestion YAML. The pipeline YAML and `databricks.yml` stay pinned to `v0.1.0`, the training job to `v0.2.0`. A new pin fixes the peak daily job to `v0.3.0` | Shipped pin tests change by design (F-41); the supersession is stated in DEFINE |
| 9 | Does the peak side change? | No. `smart_meter_peak_model`, `notebooks/check_pipeline_idle.py` and the current `pipeline_guard` behaviour and messages stay unchanged; all 28 existing `pipeline_guard` tests pass unmodified. The generalisation is additive and backward-compatible | Constraint for DESIGN and BUILD |
| 10 | Which runtime does the check task use? | Serverless environment version 2, for the check task only. A deploy with one task on a job environment and the others on the default is an assumption | A-26; spike 07 |
| 11 | How is the decision recorded? | New ADR 0013 (reverse pre-check), plus dated notes on ADR 0012 and ADR 0008, written at `/design` | ADR work in DESIGN |
| 12 | Is a spike needed before `/design`? | Yes, spike 07: the mixed-environment deploy, and that `disable_auto_optimization` holds on the deployed `ingest_kafka` (read the job back, and one forced failure shows 1 attempt) | A-26, A-27 resolved before `/design` |

---

## Sample Data Inventory

Not applicable: the feature changes a job definition and adds a read-only check of platform state.
It reads and writes no dataset, so there is nothing to profile with `scripts/profile_data.py`. The
inputs are the job and pipeline states returned by the Databricks APIs, whose shape spike 06
recorded (ADR 0012, Platform probe).

| Type | Location | Volume | Notes |
|---|---|---|---|
| Input data | N/A (Jobs and Pipelines API state) | N/A | Shapes from spike 06: `latest_updates` newest first, `creation_time` ISO 8601 with `Z`, overall state `IDLE` or `RUNNING` |
| Expected output | N/A | N/A | A failed task with an operator message, or a passing task with a JSON exit value |
| Ground truth | N/A | N/A | Live runs on `dev` (spike 07 and the AC live tests) |

**Findings** (code and platform evidence; numbering continues after PEAK_MODEL F-31):

| ID | Finding | Evidence | Implication |
|---|---|---|---|
| F-32 | The ingestion task graph: `setup_catalog`, then `ingest_files` (`max_retries: 1`) and `ingest_kafka` (`max_retries: 0`, timeout 840 s) in parallel, then `refresh_silver_gold` (pipeline task, `max_retries: 0`). Widest level 2 tasks, 06:00 UTC, `max_concurrent_runs: 1`. No `environments` block, no `environment_key`, no `disable_auto_optimization` | `resources/smart_meter_ingestion.job.yml:8-68` | The check slots in between the ingest tasks and the pipeline task; the job needs an environment for it |
| F-33 | `ingest_kafka` ran twice despite `max_retries: 0`; the deployed task shows `max_retries` unset. The cause is serverless auto-optimization (D-21). The fix is proven on `train_model` and on the peak `check_pipeline_idle`. `refresh_silver_gold` of the ingestion job also shows `max_retries` unset; the Jobs API documents the field only as "disable auto optimization in serverless", without task types | `archive/METER_INGESTION/BUILD_REPORT_METER_INGESTION.md:215,219`; `archive/PEAK_MODEL/BUILD_REPORT_PEAK_MODEL.md:201,303`; `resources/smart_meter_peak_model_training.job.yml:265-267`; `resources/smart_meter_peak_model.job.yml:121` | Item 1 is a one-line change; its pipeline-task variant is an assumption (A-25) |
| F-34 | `pipeline_guard` parts reusable as they are: `_read_pipeline` (overall state G-21 and `latest_updates`), the terminal and pass state sets, `utc_text`, redaction, `_describe_error`, `CLIENT_LIMITS`, `run` and `enforce`, the fail-closed structure and the read-only call list | `src/smart_meter_peak_prediction/pipeline_guard.py:29-42,52,63-110,352-394,397-433` | The reverse check needs no new API call |
| F-35 | Parts fixed to the peak job's direction: `_read_job` accepts only a job named `smart_meter_ingestion`; `check()` takes exactly one job id; the message names `check_pipeline_idle`, "rerun smart_meter_peak_model" and "08:00 UTC"; the exit value key is `ingestion_job`. Unit tests pin these strings | `pipeline_guard.py:174,208-218,234,263-278,317`; `tests/test_pipeline_guard.py:172-173,352,432` | The generalisation must be additive: the watched job becomes optional and the caller's job name and schedule become inputs, with the current values as defaults |
| F-36 | The reset script has no active-run check. Its client and the time-zone query run outside the `try`; its 3 tests cover `plan()` only. It runs locally under a CLI profile, so bundle references are not available and jobs would be found by name with the development-mode prefix | `scripts/reset_peak_model_outputs.py:148-187,161-165`; `tests/test_peak_reset_script.py:25-51`; `tests/integration/conftest.py:188-202,370` | Item 3 is a separate design problem (D-52) |
| F-37 | The peak job already references the ingestion job id through a bundle resource reference. A reference from the ingestion job back to the peak job makes the two jobs reference each other, which the CLI's resource graph most likely rejects as a cycle. Not verified | `resources/smart_meter_peak_model.job.yml:127`; Databricks CLI v0.298.0 | Approaches that need the peak job id need a spike or a name lookup that ADR 0012 rejected |
| F-38 | A peak run refused by its pre-check stays active while `ingest_weather` and `build_weather_silver` run (up to 900 s each). A reverse check that blocks on any active peak run would then refuse the ingestion run too: both lose the day. It would also break the shipped live assertion that the ingestion run's own refresh succeeds when its upstream succeeded (U-02) | `docs/runbooks/peak_model.md:45-49`; `resources/smart_meter_peak_model.job.yml:144-172`; `tests/integration/test_peak_concurrency.py:150-153` | Rules out Approach B |
| F-39 | Only the daily peak job starts pipeline updates. The training job has no pipeline task and touches only ML tables; the ingestion job never writes ML tables or `silver.weather_hourly` | `resources/smart_meter_peak_model.job.yml:134-142`; `resources/smart_meter_peak_model_training.job.yml:261-276` | The training job is not a blocker |
| F-40 | `score_predictions` resolves its default target date from Gold when it runs. A Gold refresh by the ingestion job between `build_features` and `score_predictions` of a peak run can move the latest complete day, so G-06 or G-07 could fail the scoring. Plausible, not observed; the 06:00 and 08:00 schedules make it a manual-run case. Unchanged by this feature | `src/smart_meter_peak_prediction/scoring.py:66-74`; `notebooks/score_predictions.py:6-7` | Assumption A-28; covered later by Approach C |
| F-41 | `PINNED_SHA256` holds the v0.1.0 digests of the ingestion job YAML, the pipeline YAML and `databricks.yml`. Both `test_ac62_bundle_has_exactly_one_pipeline_and_meter_ingestion_files_unchanged` (also compares `git show v0.1.0:`) and `test_ac78_ingestion_pipeline_and_training_definitions_unchanged_and_retry_kept` assert them. AC-78 and C-08 state "identical to v0.1.0"; the SHIPPED record says a change needs a new feature | `tests/test_peak_bundle.py:48-60,228-255,487-490`; `archive/PEAK_MODEL_CONCURRENCY/DEFINE_PEAK_MODEL_CONCURRENCY.md:160,241`; `archive/PEAK_MODEL_CONCURRENCY/SHIPPED_2026-10-22.md:132` | These tests break by design; a new AC re-pins (D-53) |
| F-42 | Other shipped tests pin the ingestion graph: exactly 4 tasks and their order; `refresh_silver_gold` depends on exactly `ingest_files` and `ingest_kafka`; the timeout and retry lists; AC-10 asserts `ingest_kafka` is a direct dependency of `refresh_silver_gold`; the deployed task set. The deployed-vs-YAML comparison reads `disable_auto_optimization` and follows the YAML. The secret-scope test ("no other task receives the scope") stays valid | `tests/test_bundle_config.py:99-101,110-118,210-213,258-263`; `tests/integration/test_deployment.py:18`; `tests/integration/test_peak_deployment.py:59,69,149` | These tests change by design; DESIGN lists every one in the manifest |
| F-43 | With the check directly before `refresh_silver_gold`, a refusal or a fail-closed result costs only the Silver/Gold refresh: Bronze is already ingested (Kafka is not the replay source, ADR 0006), and the 08:00 peak run's own `refresh_silver_gold` refreshes from it. With the Kafka service off, `ingest_kafka` fails and the check never runs (unchanged behaviour) | `resources/smart_meter_ingestion.job.yml:44-68`; `resources/smart_meter_peak_model.job.yml:11,134-142` | The message can name the next refresh; a live busy test needs the Kafka service on or a run limited to the check task |
| F-44 | Spike 06 validated the guard only on environment version 2 (`databricks-sdk` 0.40.0, `WorkspaceClient(config=Config(...))`). The ingestion job has no environment; without one the task gets the default environment with an unverified SDK version | `docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md` (Platform probe); `notebooks/check_pipeline_idle.py:36-45` | Environment version 2 for the check task only (D-55); mixed deploy is A-26 |
| F-45 | The check adds one serverless task of about 18 to 32 s (measured on the peak side) to each ingestion run. In sequence it keeps the width at 2; with an overlapping peak run at most 2 + 2 tasks run, below the limit of 5 | `archive/PEAK_MODEL_CONCURRENCY/SHIPPED_2026-10-22.md:54`; `.claude/kb/databricks/free-edition.md:11,15` | Fits the Free Edition limits; small quota cost |

---

## Approaches Explored

### Approach A: Pipeline-only reverse check (recommended)

A new notebook task in `smart_meter_ingestion`, directly before `refresh_silver_gold` and after
`ingest_files` and `ingest_kafka`. It runs on serverless environment version 2 with
`max_retries: 0`, `disable_auto_optimization: true` and a 300 s timeout. It reads only the pipeline
`smart_meter_silver_gold`: the overall state and `latest_updates`. `IDLE` and `FAILED` pass, any
other or missing state counts as busy, and `DELETED` or an unreadable state fails closed (G-21). It
fails at once with a message that names the active update (id, state, creation time in UTC with
`Z`) and the action, and never waits or retries. The pipeline id is the existing bundle reference
to the pipeline. `pipeline_guard` gains an additive mode without a watched job, in which the
calling job's name and schedule are inputs to the message. `ingest_kafka` gets
`disable_auto_optimization: true`.

- **Pros:** No peak job id, so no bundle reference cycle (F-37). No mutual refusal: a refused peak
  run never shows up as a pipeline update, so AC-74 still holds (F-38). Reuses the pipeline half of
  `pipeline_guard` with no new API call (F-34). The peak side stays byte-identical. Whenever a peak
  update actually conflicts, it is visible as an active update.
- **Cons:** Names the update, not the peak run. Does not protect a peak run's tasks after its
  refresh from a Gold change (F-40, unchanged from today). The race window between a peak run's
  pre-check and its refresh start remains (C-11).
- **Why recommended:** It removes the visible conflict with the smallest change, avoids both
  platform risks of the alternatives, and keeps every shipped peak definition and test intact.

### Approach B: Full mirror of ADR 0012

The check blocks on any active run of `smart_meter_peak_model` and on the pipeline, naming the run.

- **Pros:** Names the peak run; symmetric with the peak side.
- **Cons:** Needs the peak job id, which most likely makes a bundle reference cycle (F-37); the
  fallback is a name lookup, which ADR 0012 rejected because it can match another deployment.
  Mutual refusal in the AC-74 scenario breaks a shipped live AC (F-38). Blocks ingestion for a whole
  peak run (about 8 minutes, up to 7200 s). Rejected (D-48).

### Approach C: Stage-aware check

The check blocks on the pipeline and on active peak daily runs whose `check_pipeline_idle` did not
fail, read from the run's task states.

- **Pros:** Names the peak run; also covers the post-refresh Gold-change risk (F-40); avoids the
  AC-74 mutual refusal.
- **Cons:** Still needs the peak job id (F-37), so a spike or a runtime lookup by name. Adds a new
  read shape (task states of a run) that must be probed on `databricks-sdk` 0.40.0. More logic and
  tests. Mutual refusal stays possible when both checks run in the same second. Rejected for v0.4.0
  and kept as the upgrade path (D-48).

---

## Selected Approach

| Attribute | Value |
|---|---|
| **Chosen** | Approach A |
| **Confirmed by** | Christian (user), 2026-10-23 |
| **Reasoning** | Approach A closes the visible conflict for the ingestion job without a peak job id. It avoids the bundle reference cycle (F-37) and the mutual refusal of Approach B (F-38), and it leaves the shipped peak job and its tests unchanged. Approach C stays the upgrade path if the peak run must be named or the post-refresh Gold-change risk (A-28) is observed |

Architecture (task graph of `smart_meter_ingestion` after the change):

```text
setup_catalog
  -> ingest_files ---------------------+
  -> ingest_kafka (auto-opt off) ------+-> reverse pre-check (env v2, no retry, auto-opt off)
                                                 -> refresh_silver_gold (unchanged)
```

Data flow of the check: read `pipelines.get` for `smart_meter_silver_gold` once; decide pass, busy
or unreadable; on pass, exit with a JSON value; on busy or unreadable, fail the task with the
operator message. `refresh_silver_gold` then ends `UPSTREAM_FAILED` and starts no update. Bronze
written by the ingest tasks stays and is picked up by the next refresh.

---

## Key Decisions

| # | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| D-46 | The feature is INGESTION_GUARD, released as v0.4.0 | A follow-up of an archived feature needs a new feature cycle | `/iterate` on the archived METER_INGESTION documents |
| D-47 | Goals: (a) a failed `ingest_kafka` run shows exactly 1 attempt, checked by extending the AC-10 live test; (b) 0 ingestion refreshes refused while an update was visible at check time; the run fails at once with a message naming the blocker | Measurable outcomes for DEFINE | Unmeasured "harden the job" |
| D-48 | Approach A: the reverse check reads only the pipeline's overall state and `latest_updates` (`IDLE` and `FAILED` pass; `DELETED` and unreadable fail closed, G-21). No training job and no peak job id | No bundle cycle (F-37), no mutual refusal (F-38), training is not a blocker (F-39) | B (cycle, mutual refusal, breaks AC-74); C (needs the peak job id and a new SDK read shape; kept as upgrade path) |
| D-49 | The message names the update: id, state and creation time in UTC with `Z`, plus the action. Naming the peak run is out of scope | Follows from D-48 | Name the peak run (needs the peak job id) |
| D-50 | The check is a new task directly before `refresh_silver_gold`, after `ingest_files` and `ingest_kafka` | Shortest race window; a refusal costs the refresh only and Bronze is kept (F-43) | First task of the job (would also refuse Bronze ingestion) |
| D-51 | `disable_auto_optimization: true` on `ingest_kafka` and on the new check task only. `ingest_files` is unchanged. The pipeline-task case is an assumption (A-25); unresolved, it is Out of Scope | Same cause and fix as D-21 (F-33) | Setting it on every task |
| D-52 | The reset script guard and its `main()` test are Out of Scope, next release | Needs a name-based, multi-job check outside the bundle (F-36) | Include item 3 in v0.4.0 |
| D-53 | A new AC supersedes the ingestion-file clause of AC-62 and AC-78 and pins the new ingestion YAML. The pipeline YAML and `databricks.yml` stay pinned to `v0.1.0`, the training job to `v0.2.0`; a new pin fixes the peak daily job to `v0.3.0` | Archived ACs cannot be edited, so the supersession is explicit (F-41) | Dropping the pins |
| D-54 | The peak side is unchanged: `smart_meter_peak_model`, `notebooks/check_pipeline_idle.py` and the current `pipeline_guard` behaviour and messages; the 28 existing `pipeline_guard` tests pass unmodified. The generalisation is additive and backward-compatible | A shipped v0.3.0 behaviour stays stable (F-35) | Refactoring the peak check into a shared notebook |
| D-55 | The check task runs on serverless environment version 2; the other ingestion tasks keep the default environment | The runtime spike 06 validated (F-44) | Default environment for the check (unverified SDK) |
| D-56 | New ADR 0013 records the reverse pre-check; dated notes go on ADR 0012 and ADR 0008. Written at `/design` | ADR 0012 lists this reverse check as a revisit trigger | Amending ADR 0012 only |
| D-57 | Spike 07 runs before `/design`: the mixed-environment deploy, and `disable_auto_optimization` on the deployed `ingest_kafka` (read the job back; one forced failure shows 1 attempt) | Probe the platform surface before design (PEAK_MODEL_CONCURRENCY lesson) | Discovering the behaviour at the build gate |

---

## Out of Scope (YAGNI)

| Item | Reason | Revisit in |
|---|---|---|
| Reset script active-run check through `pipeline_guard`, connection inside the `try`, `main()` test (PEAK_MODEL F-03, PEAK_MODEL_CONCURRENCY F-02) | Separate problem: local script, name-based multi-job resolution (D-52) | Next release (v0.5.0) |
| Naming the peak run in the ingestion check (Approach C) | Needs the peak job id (F-37) and a new SDK read shape | When A-28 is observed or the update id proves insufficient |
| Blocking on the training job | It starts no pipeline update and shares no table with ingestion (F-39) | Never, unless training starts a pipeline update |
| `disable_auto_optimization` on `refresh_silver_gold` | Applicability to a pipeline task is unknown (A-25) | Next release; spike 07 records the A-25 result as input |
| Any change to the peak daily job, the training job, the pipeline or `databricks.yml` | Pinned (D-53, D-54) | Never in this feature |
| A lock or queue across the two jobs that closes the race window | Not available on Free Edition (C-11) | When the platform offers one (ADR 0012 revisit trigger) |
| Waiting or polling in the check | Burns quota; rejected for the peak side too (D-43) | Never |

---

## Assumptions & Open Questions

| ID | Assumption or question | How it will be resolved | Status |
|---|---|---|---|
| A-25 | `disable_auto_optimization` on a `pipeline_task` is accepted and has an effect | Spike 07: deploy and read the job back; documentation | Pending |
| A-26 | A job with one notebook task on a job environment (version 2) and other notebook tasks on the default environment deploys and runs | Spike 07: `bundle validate`, `bundle deploy -t dev` and one run | Pending |
| A-27 | With `disable_auto_optimization: true`, a failed `ingest_kafka` run shows exactly 1 attempt | Spike 07: read the deployed job, one forced failure with the Kafka service off; later the extended AC-10 live test | Pending |
| A-28 | A Gold refresh by the ingestion job during a peak run's `build_features` to `score_predictions` can fail the scoring (F-40). Not observed; not changed by this feature | Watch the runs; revisit with Approach C if observed | Accepted, watch |
| A-29 | The ingestion job's run-as identity can read the pipeline state with no extra grant (it already starts the pipeline's updates) | Spike 07 run; live AC on `dev` | Pending |
| A-30 | A bundle reference from the ingestion job to the peak job would form a cycle (F-37) | Not resolved: the chosen approach needs no such reference. Record in ADR 0013 as the reason against B and C | Not needed for v0.4.0 |

---

## Suggested Requirements for Define

- **Problem statement (draft):** The ingestion job can be retried silently by serverless
  auto-optimization, and its pipeline task is refused without a clear message when the shared
  pipeline already has an update in progress.
- **Success criteria (draft):** A failed `ingest_kafka` run shows exactly 1 attempt (extended AC-10
  live test). 0 ingestion refreshes refused while an update was visible at check time; the check
  fails within 120 s with a message naming the update id, state and UTC time and the action. The
  check task lasts at most 120 s on an idle pipeline. The peak job, training job, pipeline and
  `databricks.yml` stay identical to their pinned tags, and the 28 existing `pipeline_guard` tests
  pass unmodified.
- **Constraints:** Free Edition serverless, at most 5 concurrent tasks, daily quota; no secrets;
  UTC end to end; read-only check, no wait, no retry, fail closed; environment version 2 with
  `databricks-sdk` 0.40.0; explicit supersession of the ingestion-file clause of AC-62 and AC-78.
- **Risks to carry:**
  - Race window (C-11) in both directions: an update started between a check and the pipeline
    task start still ends `INTERNAL_ERROR` ("Pipeline update already in progress.").
  - Fail-closed cost: an API fault now also costs the ingestion refresh. Bronze is kept and the
    08:00 peak refresh catches up.
  - SDK drift (PEAK_MODEL_CONCURRENCY F-04) now affects both jobs.
  - Live test cost: about 9 minutes per serverless run; a busy test needs the Kafka service on (or
    a run limited to the check task) and depends on the timing of a no-op update, like AC-75.
  - Shipped tests break by design (F-41, F-42): the pin tests in `tests/test_peak_bundle.py`, the
    graph tests in `tests/test_bundle_config.py`, `tests/integration/test_deployment.py`. Archived
    ACs are superseded explicitly in DEFINE, not edited.

---

## Self-Review

- **Weak points:** The bundle reference cycle (F-37) is inferred, not verified; it decides against B
  and C only together with F-38. A-25 to A-27 are open until spike 07. The post-refresh Gold-change
  risk (F-40) is reasoned from code, not observed. The message names the update, so an operator has
  to find the peak run from the update's time.
- **Risks:** The race window remains in both directions. Fail-closed turns an API outage into a lost
  ingestion refresh. Environment version 2 or its SDK may change, and then both checks fail closed
  every day. Changing pinned shipped files can hide an unintended change unless the new pins are
  exact.
- **Trade-offs:** A pipeline-only check gives up naming the peak run and covering a peak run's later
  tasks, in exchange for no cycle, no mutual refusal and no peak-side change. Placing the check after
  the ingest tasks keeps Bronze ingestion when the pipeline is busy, but with the Kafka service off
  the check never runs. One more serverless task per ingestion run (about 30 s) costs quota.
- **What I would do differently:** Verify the cycle question (A-30) with a throwaway bundle in
  spike 07 as well, so ADR 0013 can state it as a fact.
- **Next improvement:** Run spike 07 (A-25, A-26, A-27, A-29), record it, then start `/define`.

---

## Next Step

Spike 07, then `/define .claude/sdd/features/BRAINSTORM_INGESTION_GUARD.md`
