# FOLLOW-UP: PEAK_MODEL F-15 - AC-66 green only when both legs have passed

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | PEAK_MODEL F-15 |
| **Source spec** | PEAK_MODEL |
| **Source finding** | none |
| **Source documents** | `.claude/sdd/archive/PEAK_MODEL/SHIPPED_2026-10-22.md` (Follow-ups row F-15), `.claude/sdd/archive/PEAK_MODEL/BUILD_REPORT_PEAK_MODEL.md` (AC-66 rows) |
| **Created** | 2026-11-09 |
| **Status** | In Progress |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

PEAK_MODEL F-15: "AC-66 test: `test_ac66_after_rerun_and_rebuild_checksums_equal` passes on either
leg. Split it so that AC-66 is green only when both the rerun leg and the rebuild leg have passed,
and rerun it to confirm that the rerun leg alone fails the AC".

PEAK_MODEL AC-66 asks for both a rerun with no new input and a rebuild after the outputs are
dropped. The test (`tests/integration/test_peak_data.py:403-422`) picks its mode from whether the
three tables exist (`rebuild = not all(_table_exists(...))`), asserts the MERGE counts of that one
mode, and records `rebuild_after_reset` in the evidence file. A run with only the rerun leg is
green: on 2026-10-22 the build run passed with `rebuild_after_reset` false (BUILD_REPORT line 407),
and the rebuild leg was proved only by a separate run during `/ship` (line 412). Nothing fails when
one leg is missing.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Predicted: `tests/integration/test_peak_data.py`, `docs/runbooks/peak_model.md`, possibly `tests/test_integration_layout.py` |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None expected |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | PEAK_MODEL documents only annotated in SHIPPED and BUILD_REPORT rows |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | None |
| E6 | No change under `tests/integration/` | No | The AC-66 tests live in `tests/integration/test_peak_data.py` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: full cycle (`/define`, `/design`, `/build`, `/ship`), E6 is `No`. No BRAINSTORM: small
feature cycle, as AC97_TIMING_EVIDENCE. Feature name: AC66_BOTH_LEGS.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A fresh PEAK_MODEL AC-66 snapshot | Only the rerun leg runs, then the AC-66 verdict runs | The verdict fails and names the missing rebuild leg; after the rebuild leg also passes, the verdict passes |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | none |
| **Priority** | Now |
| **Target** | Next minor release after v0.6.0 |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | Planned |
| **Merge commit** | Planned |
| **Work done in** | The spec AC66_BOTH_LEGS |
| **Source rows updated** | Planned |
| **check_specs.py after the update** | Planned |

---

## Self-Review

- **Weak points:** The done criterion needs live runs on the dev workspace, and the rebuild leg
  needs the user-run reset script, which drops three tables.
- **Risks:** A verdict that reads evidence files can be fooled by stale files from an older
  snapshot; the DEFINE must tie both legs to the same snapshot.
- **Next step:** `/define AC66_BOTH_LEGS`.
