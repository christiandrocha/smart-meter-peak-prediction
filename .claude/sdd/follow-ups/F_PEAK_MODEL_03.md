# FOLLOW-UP: PEAK_MODEL F-03 - Reset script refuses unless the jobs and the pipeline are idle

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | PEAK_MODEL F-03, taken together with PEAK_MODEL_CONCURRENCY F-02 |
| **Source spec** | PEAK_MODEL |
| **Source finding** | none (PEAK_MODEL BUILD_REPORT Issues row, Low: "Reset script: connection outside the `try`, no active-run check, no `main()` test") |
| **Source documents** | `.claude/sdd/archive/PEAK_MODEL/SHIPPED_2026-10-22.md` (Follow-ups row F-03, line 193), `.claude/sdd/archive/PEAK_MODEL/BUILD_REPORT_PEAK_MODEL.md` (Issues row, line 269), `.claude/sdd/archive/PEAK_MODEL_CONCURRENCY/SHIPPED_2026-10-22.md` (Follow-ups row F-02, line 160) |
| **Created** | 2026-11-12 |
| **Status** | In Progress |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

PEAK_MODEL F-03: "Reset script (PR 3 review, Low, open): a connection outside the `try`, no check
that the ingestion job and the three peak jobs are idle, and no `main()` test. Add the active-run
check and a test for `main()`". PEAK_MODEL_CONCURRENCY F-02: "Reset script: reuse `pipeline_guard`
for its active-run check".

`scripts/reset_peak_model_outputs.py` drops `silver.weather_hourly`, `ml.household_features_daily` and
`ml.household_labels_daily` with `--confirm`. Measured on main `de5535a`:

1. `main()` builds `Warehouse()` and runs `SELECT current_timezone()` (lines 161-162) before the
   `try` at line 168. A `ResetRefused` raised there (no SQL warehouse, failed SQL) or an SDK error
   ends in a raw traceback instead of a `refused, nothing dropped: ...` line and exit code 2.
2. Nothing reads the job runs or the pipeline updates. A `--confirm` while the ingestion job, the
   peak model job, the training job or the `smart_meter_silver_gold` pipeline is running drops
   tables that a running task reads or writes.
3. `tests/test_peak_reset_script.py` has three tests, all on `plan()`; `main()` has no test (the
   exit codes, the dry-run default, the order "check, then drop").

`pipeline_guard._read_job` checks the job name against `INGESTION_JOB` only (line 322), so
reusing it for the peak jobs needs a change under `src/`.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | No | Reusing `pipeline_guard` for the peak jobs changes `src/smart_meter_peak_prediction/pipeline_guard.py` (job name fixed to `INGESTION_JOB`) |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Unknown | Whether the reset reuses the guard or has its own read is a design choice; ADR 0012 may need a note instead |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | PEAK_MODEL and PEAK_MODEL_CONCURRENCY documents only annotated in SHIPPED and BUILD_REPORT rows |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None |
| E6 | No change under `tests/integration/` | Unknown | A live leg for the refusal is a DESIGN choice |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: full cycle (`/define`, `/design`, `/build`, `/ship`), E1 is `No`. No BRAINSTORM: small
feature cycle, as AC66_BOTH_LEGS. Feature name: RESET_GUARD.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A job or pipeline update that the reset depends on is active, or its state cannot be read | `reset_peak_model_outputs.py --confirm` runs | No DROP statement is sent; the output names the blocking run or update (or the unreadable object) and the exit code is 2 |
| DC-02 | The warehouse lookup or the time-zone query fails | `main()` runs, with or without `--confirm` | The output is one `refused, nothing dropped: ...` line, no traceback, exit code 2 |
| DC-03 | Fakes for the warehouse and the workspace client | The unit tests call `main()` | Dry run, `--confirm` on idle jobs, each refusal path and the order "every check before the first DROP" are covered by tests that name their AC |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | Low, inherited from the PEAK_MODEL BUILD_REPORT Issues row |
| **Priority** | Now |
| **Target** | Next minor release after v0.7.3 |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #{N} |
| **Merge commit** | {SHA, read with `gh pr view {N} --json state,mergeCommit` after the merge} |
| **Work done in** | the spec `RESET_GUARD` |
| **Source rows updated** | `{file}:{line}`; the Follow-up cell no longer starts with `Open` (for example "Closed in #{N}") |
| **check_specs.py after the update** | {summary line; the rule (b) warning for this finding is gone} |

---

## Self-Review

- **Weak points:** "the three peak jobs" in the source row does not match the bundle, which has two
  peak jobs (`smart_meter_peak_model`, `smart_meter_peak_model_training`) plus the ingestion job and
  the pipeline. DEFINE must fix the exact set.
- **Risks:** a check that fails closed can block a legitimate reset when the API is slow or a
  permission is missing; DEFINE should say whether an override flag is allowed.
- **Next step:** `/define RESET_GUARD`.
