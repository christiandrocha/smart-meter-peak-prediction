# FOLLOW-UP: {SPEC} F-{NN} - {short title}

> One file per follow-up task, saved as `.claude/sdd/follow-ups/F_{SPEC}_{NN}.md` (for example
> `F_SMALL_CHANGE_TRACK_05.md`). It carries a follow-up from the Follow-ups table of a SHIPPED
> document (or an open finding of a BUILD_REPORT or CHANGE document) to the work that closes it.
> `scripts/check_specs.py` does not read this folder: keep the file and the source row in step
> by hand (Closure below).

## Metadata

| Attribute | Value |
|---|---|
| **Follow-up** | {SPEC} F-{NN} (always with the spec prefix: IDs repeat across specs) |
| **Source spec** | {SPEC} |
| **Source finding** | {SPEC} I-{NN}, or "none" |
| **Source documents** | `.claude/sdd/archive/{SPEC}/SHIPPED_{YYYY-MM-DD}.md` (Follow-ups row), `.claude/sdd/archive/{SPEC}/BUILD_REPORT_{SPEC}.md` (Issues row) |
| **Created** | {YYYY-MM-DD} |
| **Status** | Open |

Allowed status values: `Open`, `In Progress`, `Closed`, `Dropped`. `Dropped` needs a reason in
Closure.

---

## Problem

{What is wrong or missing, quoted or cited from the source row, measured where possible. Name the
files and lines involved.}

---

## Triage

Predict the files the fix will change and test them against the CHANGE track criteria
(`.claude/sdd/README.md`). Result: `Yes`, `No` or `Unknown`.

| ID | Criterion | Result | Why |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` | {Yes / No / Unknown} | {predicted files} |
| E2 | No change under `docs/contracts/` | {Yes / No / Unknown} | {...} |
| E3 | No new ADR | {Yes / No / Unknown} | {...} |
| E4 | No change to an archived DEFINE or DESIGN (that is `/iterate`) | {Yes / No / Unknown} | {...} |
| E5 | No change to `scripts/check_specs.py` or to a template that the script or the tests read | {Yes / No / Unknown} | {...} |
| E6 | No change under `tests/integration/` | {Yes / No / Unknown} | {...} |
| E7 | No change to the runtime `dependencies` of `pyproject.toml` | {Yes / No / Unknown} | {...} |
| E8 | Agent rules (`docs/conventions/git.md`, the rules for agents in `CLAUDE.md`) change only under a gate; relaxing needs the Rule Changes section of the CHANGE template | {Yes / Relaxing / No / Unknown} | {...} |

Decision: {CHANGE track / full cycle}. The CHANGE track needs every row `Yes` (E8 may be
`Relaxing`); any `No` or `Unknown` means the full cycle (`/define`, `/design`, `/build`,
`/ship`). In doubt, full cycle.

---

## Done Criterion

The measurable outcome that closes this follow-up. It becomes an acceptance criterion of the
CHANGE document or spec that does the work.

| ID | Given | When | Then |
|---|---|---|---|
| DC-01 | {...} | {...} | {Measurable outcome} |

---

## Target and Priority

| Attribute | Value |
|---|---|
| **Severity** | {Low / Medium / High}, inherited from {SPEC} I-{NN}, or "none" |
| **Priority** | {Now / Next / Later} |
| **Target** | {release vX.Y.Z or date YYYY-MM-DD}, or "Not scheduled: {reason}" |

---

## Closure

Fill when the status becomes `Closed` or `Dropped`, in the same PR that does the work.

| Item | Value |
|---|---|
| **Pull request** | #{N} |
| **Merge commit** | {SHA, read with `gh pr view {N} --json state,mergeCommit` after the merge} |
| **Work done in** | `CHANGE_{FEATURE}.md` or the spec `{FEATURE}`, or "Dropped: {reason}" |
| **Source rows updated** | `{file}:{line}`; the Follow-up cell no longer starts with `Open` (for example "Closed in #{N}") |
| **check_specs.py after the update** | {summary line; the rule (b) warning for this finding is gone} |

---

## Self-Review

- **Weak points:** {...}
- **Risks:** {...}
- **Next step:** {...}
