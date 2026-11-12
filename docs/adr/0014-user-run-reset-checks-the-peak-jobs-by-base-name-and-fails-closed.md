# 0014. The user-run reset finds the two peak jobs by base name and refuses unless both are idle, failing closed

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-11-12 |
| **Deciders** | Christian |
| **Related** | RESET_GUARD; FR-105 to FR-112, NFR-53 to NFR-56, AC-189 to AC-202; D-104 to D-109; Q-40 to Q-42; OD-51 to OD-53; C-30 to C-33; A-57, A-58, A-60; RESET_GUARD DA-60 to DA-62; follows up PEAK_MODEL F-03 and PEAK_MODEL_CONCURRENCY F-02; reuses ADR 0012 (job identity and active-run rules) and keeps ADR 0013 unchanged |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

`scripts/reset_peak_model_outputs.py --confirm` drops `silver.weather_hourly`,
`ml.household_features_daily` and `ml.household_labels_daily` so that the AC-66 rebuild leg can
rebuild them. The daily job `smart_meter_peak_model` writes all three tables and the training job
`smart_meter_peak_model_training` reads both ML tables by Delta version (its G-04 guard). A drop
while either job runs fails that run and leaves `dev` in a partial state that both AC-66 legs
refuse (RESET_GUARD D-104). The user decided that these two jobs, and only these, must be idle
(Q-40), that no flag may skip the check (Q-41), and that the dry run checks them too (D-105).

The reset is a local script run by the user (C-31), not a bundle task. It therefore has no bundle
resource reference for the job ids, which is how the in-job checks of ADR 0012 and ADR 0013 get
their ids. ADR 0012 rejected identifying the ingestion job by its name for the in-job check,
because a name can match another target's or another user's deployment and depends on the
display prefix of development mode. That check runs every day without a person watching, so a
wrong match would silently read the wrong job.

Facts that bound the choice:
- `databricks.yml` has one target, `dev`, in development mode; the deployed names are
  `[dev <user>] smart_meter_peak_model` and `[dev <user>] smart_meter_peak_model_training`
  (`.claude/kb/databricks/bundles.md`). The prod target is documented only, not deployed.
- The Jobs API `jobs/list` returns at most 100 jobs per page (`limit` 1 to 100, default 20); its
  `name` filter is an exact, case-insensitive match on the deployed name (Jobs API reference).
  The integration fixtures `peak_job` and `training_job` already find both jobs by base name with
  the development prefix stripped, against the live `dev` workspace.
- `pipeline_guard` (ADR 0012) holds the rules for job identity (the id names the expected job, the
  deployed name is unique) and for an active run (any life-cycle state other than `TERMINATED`,
  `SKIPPED` or `INTERNAL_ERROR`, including a missing or future one). Its shipped modes must stay
  byte-equal (RESET_GUARD FR-111) and the module may only grow by additions (INGESTION_GUARD AC-92).
- The option set of the script is fixed (RESET_GUARD FR-110), so a flag cannot carry an id.
- No lock exists across jobs (PEAK_MODEL_CONCURRENCY C-11).

## Decision drivers

- No DROP while a run of either peak job is active or its state is unknown (FR-105, FR-106).
- The operator sees which run blocks and what to do, in one line, with no traceback (FR-107,
  FR-108).
- One definition of "active run" and "job identity", in `pipeline_guard` (D-107).
- A wrong or ambiguous identification must refuse, never pass (fail closed, PEAK_MODEL_CONCURRENCY
  D-45).
- Bounded, read-only and cheap: at most 4 Jobs API reads per job, no wait (NFR-53, NFR-54).
- Testable without a workspace or the SDK (DC-03).

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Find each job by base name in one page of `jobs.list(limit=100)` with the development prefix stripped; refuse unless exactly one job matches and the page is not full; then apply the shipped `pipeline_guard` identity and active-run reads to that id (a new job-only mode, added to the module without changing its shipped lines). The check is the last read before the first DROP and also runs in the dry run** | No id to configure; works from any checkout with the user's CLI profile; every way the lookup can go wrong (no match, two matches from another user or a future prod target, a renamed job, a changed prefix format, more than 100 jobs) refuses with a named cause; the dry run shows the resolved ids, so the user sees which jobs were read (AC-202); reuses the shipped rules | Depends on the development-mode prefix format and on the user's view of the workspace; a second deployment of the same base name blocks every reset until it is removed; two more Jobs API reads per job than an exact id would need |
| `databricks bundle summary -t dev -o json` in a subprocess, reading the job ids of the deployed target | Ids exact and scoped to the target, as bundle references are | Needs the CLI on the path, a bundle root and its local or remote deployment state; a second process with its own authentication and time-out to fail closed on; output format of the CLI not yet probed (a spike); harder to fake in CI |
| Job ids from environment variables (for example `SMART_METER_PEAK_JOB_ID`) | Exact ids, no listing | The user must look the ids up and keep them current after a redeploy; a stale id is caught only by the identity check; one more set-up step on a destructive path |
| Job ids from command-line flags | Explicit | Excluded by FR-110: the option set is fixed |
| Build the exact deployed name from `current_user.me()` and use the `name` filter of `jobs.list` | Exact name, one short read | `current_user.me` is outside the read calls allowed by NFR-53; still depends on the prefix format |
| Run the reset as a bundle task with bundle references | Exact ids as in ADR 0012 | The reset is user-run by design (C-31); a job run of its own costs serverless quota and does not lock the peak jobs either |
| No idle check (status quo) | No code | The drop under a running task that PEAK_MODEL F-03 exists to prevent |

## Decision

We will make the reset find `smart_meter_peak_model` and `smart_meter_peak_model_training` by
base name in one page of `jobs.list(limit=100)` (development prefix stripped), refuse unless
exactly one job matches and fewer than 100 jobs were listed, and then read that id with the shipped
`pipeline_guard` rules: `jobs.get` (the id names the job), `jobs.list(name=<deployed name>)` (unique)
and `jobs.list_runs(job_id=..., active_only=True)` (at most 25 runs, any non-terminal or missing
state is active). The reads are a new job-only mode of `pipeline_guard`, appended without changing a
shipped line. The check runs after the SQL checks and immediately before the first DROP, also in the
dry run, and is never skipped. Any case in which the state of a job cannot be established refuses
with exit code 2 and one line that names the job and the cause.

**Live check (2026-11-12):** AC-202 passed on `dev` from the build branch (RESET_GUARD
BUILD_REPORT, AC-202 record). The dry run resolved `smart_meter_peak_model` to job id
324283392483306 and `smart_meter_peak_model_training` to job id 628754932821673, each with 0
active runs, before listing three `would DROP TABLE` lines and exiting 0. The base-name lookup,
`jobs.list` and the `Config(profile=...)` client worked with the local SDK (A-57, DA-60, DA-63).
This record is the one live evidence of the idle path; the busy and unreadable paths are proven
on fakes only.

This decision applies to the user-run reset only. ADR 0012's rejection of name lookup for the
in-job pre-check stands: there a bundle reference exists and no person reads the outcome before the
next task runs.

## Consequences

- **Positive:**
  - A reset can no longer drop the three tables while a peak run writes or reads them, as far as
    the Jobs API shows at the moment of the read.
  - The refusal line names the job, its job id, the run id, the state and the UTC start time, or
    what could not be read, and the action; a refusal never leaves a traceback.
  - The rules for "active" and "identity" stay in one module, now usable for any job name.
  - The dry run prints the resolved job ids, so the identification is visible before `--confirm`.
- **Negative:**
  - The race window stays: a run started between the idle read and the DROP statements is not
    seen (C-32). On `dev`, development mode pauses the schedule, so only a person starts a run.
  - A second deployment with the same base name (another user's `dev`, a future prod target in
    the same workspace) or a workspace with 100 or more visible jobs blocks every reset until it
    is resolved; there is no override (Q-41).
  - A change of the development-mode prefix format makes every reset refuse with "no deployed job
    named ..." until `strip_dev_prefix` follows it.
  - A slow or failing Jobs API blocks the reset; the shipped client limits (60 s retry, 30 s HTTP)
    bound the wait.
- **What would make us revisit this:**
  - A second target or a shared workspace where two deployments of the bundle are normal: switch
    to exact ids from `databricks bundle summary` after a spike, keeping the name match as a
    cross-check.
  - A lock, a queue across jobs or a pause API that closes the race window (verified by a spike).
  - A table that the ingestion job or the pipeline starts to read or write among the three dropped
    tables (D-104, A-59): widen the idle set through `/iterate`.
