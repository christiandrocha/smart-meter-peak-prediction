# FOLLOW-UP: AC66_BOTH_LEGS F-03 - a refused leg asserts that it started no job run

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC66_BOTH_LEGS F-03 |
| **Source spec** | AC66_BOTH_LEGS |
| **Source finding** | none |
| **Source documents** | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` (Follow-ups row F-03), `.claude/sdd/archive/AC66_BOTH_LEGS/BUILD_REPORT_AC66_BOTH_LEGS.md` (AC-162 and AC-164 rows, Self-Review) |
| **Created** | 2026-11-10 |
| **Status** | In Progress |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC66_BOTH_LEGS F-03: "The '0 new runs' of AC-162 and AC-164 is read by the operator. The leg tests
should read the job run list before and after a refusal and assert it themselves (DESIGN and
BUILD_REPORT Self-Review). The DESIGN left it out to keep the leg's side effects to those the
DEFINE names; it costs two Jobs API reads per leg and a fake in AC-158".

`run_leg` in `tests/support/ac66_rules.py` raises before `run_tasks` when the table state is wrong,
and AC66_BOTH_LEGS AC-158 proves that order on fakes. The live tests
(`tests/integration/test_peak_data.py`, `test_ac66_rerun_leg_*` and `test_ac66_rebuild_leg_*`) do
not check the workspace: on 2026-11-09 the operator read the newest run of `smart_meter_peak_model`
with the CLI before and after each refusal (`457575248055458` and `323617648524483`, unchanged).
A regression that starts a run and then refuses would only be seen by an operator who looks.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Predicted: `tests/support/ac66_rules.py`, `tests/test_ac66_rules.py`, `tests/integration/test_peak_data.py`, possibly `tests/integration/conftest.py` and `docs/runbooks/peak_model.md` |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None expected |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | AC66_BOTH_LEGS documents are only cited |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None |
| E6 | No change under `tests/integration/` | No | The leg tests live in `tests/integration/test_peak_data.py` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: full cycle (`/define`, `/design`, `/build`, `/ship`), E6 is `No`. No BRAINSTORM: small
feature cycle, as AC66_BOTH_LEGS and AC97_TIMING_EVIDENCE. Feature name: AC66_ZERO_NEW_RUNS.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A leg in the wrong table state on `dev` | The leg test runs | The test itself reads the runs of `smart_meter_peak_model` before and after the refusal and fails if a run was started; the operator no longer reads it from the CLI |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | none |
| **Priority** | Now |
| **Target** | Next release after v0.7.0 |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | Pending |
| **Merge commit** | Pending |
| **Work done in** | The spec AC66_ZERO_NEW_RUNS |
| **Source rows updated** | Pending: `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md`, Follow-ups row F-03 |
| **check_specs.py after the update** | Pending |

---

## Self-Review

- **Weak points:** The done criterion needs live refusals on `dev`; a refusal of the rebuild leg
  needs the three tables present, and a refusal of the rerun leg needs them dropped by the
  user-run reset script.
- **Risks:** A run started by someone else (the daily schedule, another operator) between the two
  reads would look like a run started by the leg; the DEFINE must say how the check tells them
  apart or accept the risk.
- **Next step:** `/define AC66_ZERO_NEW_RUNS`.
