# FOLLOW-UP: AC66_BOTH_LEGS F-06 - the AC-119 archive simulation runs in every test run

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | AC66_BOTH_LEGS F-06 |
| **Source spec** | AC66_BOTH_LEGS |
| **Source finding** | none |
| **Source documents** | `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md` (Follow-ups row F-06; Template Feedback row "Test (`check_specs` AC-119, SPEC_ARCHIVE_GATES)") |
| **Created** | 2026-11-10 |
| **Status** | In Progress |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

AC66_BOTH_LEGS F-06: "The default pytest run skips
`tests/test_check_specs.py::test_ac119_final_status_feature_docs_pass_the_archive_rules`
(SPEC_ARCHIVE_GATES AC-119): it simulates the archive rules only on documents of `features/` and
`reports/` in their final status, and none is left after this ship. [...] Until a feature reaches
`Complete` again, the archive simulation is not run in CI. Give the test a fixture document in a
temporary folder, so that it does not depend on the state of the repository".

Measured again on 2026-11-10: the test ran while AC66_ZERO_NEW_RUNS was in `features/` and
`reports/`, and caught an unprefixed citation in its DESIGN before the commit. After the
AC66_ZERO_NEW_RUNS ship the default run is back to `789 passed, 1 skipped`: the simulation code
(`simulate_archive`, `final_status_docs`) is not exercised at all between features.

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | Yes | Predicted: `tests/test_check_specs.py` only (plus the CHANGE document and this file) |
| E2 | No change under `docs/contracts/` | Yes | None |
| E3 | No new ADR | Yes | None |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | Yes | AC66_BOTH_LEGS SHIPPED row F-06 is annotated at closure (allowed) |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | Yes | The script and the templates are unchanged; only a test file changes |
| E6 | No change under `tests/integration/` | Yes | None |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | Yes | None |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | Yes | None |

Decision: CHANGE track (every row `Yes`). Document: `CHANGE_AC119_FIXTURE.md`, branch
`change/ac119-fixture`.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | A repository with no document of `features/` or `reports/` in its final status | The default `pytest` runs | The archive simulation of AC-119 runs on a fixture feature built in a temporary folder, over a copy of the real archive, and is not skipped |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | none |
| **Priority** | Now |
| **Target** | Next release after v0.7.1 (test only) |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | Pending |
| **Merge commit** | Pending |
| **Work done in** | `CHANGE_AC119_FIXTURE.md` |
| **Source rows updated** | Pending: `.claude/sdd/archive/AC66_BOTH_LEGS/SHIPPED_2026-11-09.md`, Follow-ups row F-06 |
| **check_specs.py after the update** | Pending |

---

## Self-Review

- **Weak points:** A fixture feature proves that the simulation machinery and the archive rules
  work over the real archive; it cannot prove that the next real feature's documents pass. The
  repository-state test keeps doing that, and keeps skipping when nothing is in a final status.
- **Risks:** A fixture that is too simple passes without exercising the rule that matters
  (cross-spec citations, rule c); the CHANGE document adds a negative case for it.
- **Next step:** `CHANGE_AC119_FIXTURE.md` to `Ready for Build`.
