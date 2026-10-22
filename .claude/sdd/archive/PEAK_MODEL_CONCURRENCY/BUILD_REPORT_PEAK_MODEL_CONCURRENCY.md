# BUILD REPORT: Peak Model Concurrency

> Phase 3. Evidence that the design was implemented and the acceptance criteria hold.

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | PEAK_MODEL_CONCURRENCY |
| **Date** | 2026-10-22 |
| **Source** | DESIGN_PEAK_MODEL_CONCURRENCY.md (status Ready for Build) |
| **Status** | Complete |

Allowed status values: `In Progress`, `Blocked`, `Complete`.

Status `Complete` (2026-10-22): every AC passes locally and AC-68 (deployed part) and AC-74 to AC-77 pass live on `dev` (see *Live run*).

---

## Summary

The daily job `smart_meter_peak_model` now starts with a read-only task `check_pipeline_idle` that fails at once, naming the blocking ingestion run or pipeline update, and fails closed when it cannot read the state. The decision logic is the SDK-free library module `pipeline_guard`, unit-tested against a recording fake (57 tests); the integration runner reuses it. Nothing was deployed, run on Databricks or committed. Manifest entries 1 to 3 (spike 06) were done earlier and the ADR part of entry 14 too; this report covers entries 4 to 18.

---

## Files Changed

| # | File | Action | Verified by |
|---|---|---|---|
| 4 | src/smart_meter_peak_prediction/pipeline_guard.py | Created | `tests/test_pipeline_guard.py`; ruff |
| 5 | tests/test_pipeline_guard.py | Created | 77 passed, including the SDK enum cross-check for run, update and pipeline states (SDK 0.153 installed locally) |
| 6 | notebooks/check_pipeline_idle.py | Created | `test_peak_bundle.py` notebook tests (widgets, UTC, no try/except, no `%pip`, library calls exist) |
| 7 | resources/smart_meter_peak_model.job.yml | Modified | `test_ac62_daily_job_graph...`, `test_ac68_...`. `bundle validate` not run (no deploy) |
| 8 | tests/test_peak_bundle.py | Modified | OD-18 changes (additive) and new `test_ac68_*`, `test_ac78_*` |
| 9 | tests/test_secrets_hygiene.py | Modified | new `test_ac80_*` |
| 10 | tests/integration/conftest.py | Modified | collects; `assert_ingestion_idle` uses `pipeline_guard.check`, `require_idle`, `NEVER_RAN`, `start_ingestion_run`, `wait_life_cycle`, `wait_ended`, `task_runs_by_key` |
| 11 | tests/integration/test_peak_deployment.py | Modified | collects; `DAILY_TASKS`, `disable_auto_optimization` views, DA-19 id assertion |
| 12 | tests/integration/test_peak_concurrency.py | Created | collects (4 tests, marker `integration`); not run |
| 13 | docs/runbooks/peak_model.md | Modified | `test_ac79_*` |
| 14 | docs/adr/0012-...md | Unchanged | ADR text matches the code; G-21 bullet added (U-05) and the DA-19 pass recorded after the deploy (2026-10-22) |
| 15 | docs/adr/README.md | Unchanged | row for 0012 `Accepted` checked by `test_ac79_*` |
| 16 | docs/adr/0008-...md | Modified | dated note; `test_ac79_*` |
| 17 | tests/test_peak_concurrency_docs.py | Created | 3 passed |
| 18b | tests/test_integration_layout.py | Modified | file set and collection assertion include `test_peak_concurrency.py` |
| 18 | README.md | Modified | diagram line, coexistence bullet, ADR link |

---

## Acceptance Criteria Evidence

| AC | Result | Evidence |
|---|---|---|
| AC-68 | Pass (local and live) | `test_ac68_pre_check_task_precedes_the_pipeline_and_is_never_retried`, `test_ac62_daily_job_graph_schedule_and_pipeline_dependency`. Live: `test_peak_deployment.py` passed (deployed task graph, ids, `disable_auto_optimization`) |
| AC-69 | Pass | `test_ac69_*` in `tests/test_pipeline_guard.py` |
| AC-70 | Pass | `test_ac70_*` |
| AC-71 | Pass | `test_ac71_both_blockers_are_named` |
| AC-72 | Pass | `test_ac72_*` |
| AC-73 | Pass | `test_ac73_*` (15 unreadable cases, client failure, redaction, `Config` keywords) |
| AC-74 | Pass (live) | `test_ac74_*`: ingestion run 907941063610421 active; peak run 442472208123583 refused by `check_pipeline_idle` in 17 s naming run 907941063610421; the ingestion run's own `refresh_silver_gold` ran and succeeded |
| AC-75 | Pass (live) | `test_ac75_*`: no-op update 862edaf3-f7cb-44b3-ba5d-a43f9f396cc6; peak run 518509146277520 refused naming the update (state `WAITING_FOR_RESOURCES`, pipeline state `RUNNING`); no new update created |
| AC-76 | Pass (live) | `test_ac76_*`: idle full run 506830153412867 succeeded on first attempts, 500 s; `check_pipeline_idle` 32 s (target at most 120 s) |
| AC-77 | Pass (live) | `test_ac77_*`: rerun 8054105796227 after the refusal succeeded (418 s, `check_pipeline_idle` 18 s); predictions for 2014-02-28 (58 rows) differ only in `_scored_at` |
| AC-78 | Pass | `test_ac78_ingestion_pipeline_and_training_definitions_unchanged_and_retry_kept`, `test_ac62_bundle_has_exactly_one_pipeline...` |
| AC-79 | Pass | `tests/test_peak_concurrency_docs.py` (3 tests) |
| AC-80 | Pass | `test_ac80_pre_check_has_no_secret_parameter_and_tracked_files_no_token` |

---

## Verification Log

| Step | Command | Result |
|---|---|---|
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` and system `ruff format --check .` | clean with both |
| Unit tests | `.venv/bin/pytest -q` | 415 passed, 84 deselected (integration), 352 s, after the G-21 change (before it: 395 passed, 373 s). An earlier run caught `test_integration_layout` listing the new integration file; fixed |
| Spec check | `python3 scripts/check_specs.py` | 0 errors, 0 warnings |
| Collect | `.venv/bin/pytest --collect-only -o addopts= -m integration` | 64 integration tests collected |
| Hooks | `.venv/bin/pre-commit run --all-files` after `git add` | all passed (second run; the first reformatted two asserts, see Deviations) |
| Code review | `code-reviewer` subagent | no High findings; see Issues |

---

## Deviations from Design

| Item | Design said | Build did | Why | DESIGN updated via /iterate? |
|---|---|---|---|---|
| Error text | first line, at most 200 characters | also redacts bearer tokens, `dapi` tokens and URLs | review finding (Medium); error text reaches run pages and emails | No (additive) |
| Utility tests | listed tests | extra tests for redaction, `Config` keywords and edge inputs | review findings | No |
| `PeakRunner.wait_ended` | helpers `start_ingestion_run`, `wait_life_cycle`, `task_runs_by_key` | one more helper, `wait_ended` | AC-74 needs it | No |
| Assert style | - | long asserts use a `msg` variable | pre-commit ruff 0.6.9 and CI ruff 0.17 format them differently | No |
| Pipeline state (G-21, U-05) | the decision used `latest_updates` only; `state` was diagnostic | `pipelines.get(...).state` also decides: `IDLE`, `FAILED` pass; other or missing values are busy (message: "pipeline state X, no active update listed in latest_updates"); `DELETED` fails closed. Constants `PASS_PIPELINE_STATES`, `ACTIVE_PIPELINE_STATES`, `UNUSABLE_PIPELINE_STATE`; `GuardReport.pipeline_busy`; 20 new unit tests. ADR 0012 gained a dated decision bullet | Review finding I-01 (Medium), decided by the user 2026-10-22 | Yes, 2026-10-22 (G-21, U-05) |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The decision ignored `pipelines.get(...).state`, so an update missing from `latest_updates` while the pipeline is `RUNNING` would have read idle | Medium | Fixed 2026-10-22: G-21 through `/iterate` (U-05); see Deviations |
| I-02 | DA-19 (bundle reference to another job's id) is unproven until deploy | Medium | `bundle validate`, deploy; add the result to ADR 0012 |
| I-03 | The SDK in environment version 2 is 0.40.0; locally 0.153. Signatures of the four calls are believed unchanged, proven only by spike 06 and AC-76 | Low | AC-76 |

---

## Self-Review

- **Weak points:** the live behaviour (busy cases, deploy references) is unproven; AC-75 depends on timing (DA-26); the integration tests were only collected.
- **Risks:** fail-closed turns an API problem into a lost day; SDK drift in the serverless environment.
- **What I would do differently:** probe the bundle reference with `bundle validate` before writing tests that depend on it.
- **Next improvement:** deploy and run the live sequence below, then record the output here and set `Complete`.

---

## Live run (`dev`, 2026-10-22)

- Deploy of `4714acb`: `bundle validate` exit 0, `bundle deploy` exit 0. DA-19 Pass: the deployed `check_pipeline_idle` task received `ingestion_job_id` 801565150507596 and the pipeline id `b72d0498-56c0-42be-982e-3e4c200778ad` from the bundle references; `max_retries` 0, `disable_auto_optimization` true, timeout 300 s; `refresh_silver_gold` depends on it.
- AC-76 (531 s), AC-74 (226 s, Aiven Kafka service on, U-02), AC-77 (442 s): pass. AC-75 and `test_peak_deployment.py` first errored in setup because the CLI profile's refresh token had expired (no Databricks call made); after the user re-authenticated they passed (129 s and 9 s).
- AC-74 message (run 442472208123583): "check_pipeline_idle stopped the run before refresh_silver_gold: the shared pipeline is busy (checked at 2026-10-22T19:13:31Z). Blocking: job smart_meter_ingestion (job id 801565150507596): active run 907941063610421, state RUNNING, started 2026-10-22T19:13:14Z".
- AC-75 message (run 518509146277520): "... pipeline smart_meter_silver_gold (pipeline id b72d0498-...): update 862edaf3-f7cb-44b3-ba5d-a43f9f396cc6, state WAITING_FOR_RESOURCES, pipeline state RUNNING, created 2026-10-22T19:27:14Z".
- DA-21 (an active run is listed by `active_only`) and DA-25 (one attempt with auto-optimization off) hold in AC-74 and AC-75.

## Live commands (user-run on `dev`)

```bash
databricks bundle validate -t dev -p dev; echo "validate exit $?"
databricks bundle deploy -t dev -p dev;   echo "deploy exit $?"
export DATABRICKS_CONFIG_PROFILE=dev
pytest -m integration tests/integration/test_peak_concurrency.py -k "ac76"   # idle full run
pytest -m integration tests/integration/test_peak_concurrency.py -k "ac74"   # Aiven Kafka service ON (U-02)
pytest -m integration tests/integration/test_peak_concurrency.py -k "ac77"
pytest -m integration tests/integration/test_peak_concurrency.py -k "ac75"
pytest -m integration tests/integration/test_peak_deployment.py              # AC-68 deployed part
```

---

## Next Step

`/ship PEAK_MODEL_CONCURRENCY` after PRs #23, #24 and #25 merge.
