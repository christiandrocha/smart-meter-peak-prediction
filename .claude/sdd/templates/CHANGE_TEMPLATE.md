# CHANGE: {Change Name}

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | {FEATURE_NAME} |
| **Date** | {YYYY-MM-DD} |
| **Author** | {name} |
| **Branch** | `change/{feature-kebab}` |
| **Status** | Draft |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

{What is wrong or missing, measured where possible.}

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | | |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | | |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | | |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | | |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | | |
| E6 | No change under `tests/integration/` (same output) | | |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | | |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening (adding rules, raising requirements, fixing wording without changing the effect) is `Yes`. Relaxing (removing a rule, narrowing what needs confirmation, widening what is allowed without it, weakening a check) is `Relaxing` and needs the Rule Changes section below. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | | |

When E8 is `Relaxing`, add a `## Rule Changes` section to this document with this content. The
template keeps it inside a fence so that it is not a heading here; the section is required by
`scripts/check_specs.py` only in that case.

```markdown
## Rule Changes

Before (`docs/conventions/git.md:NN`): "{exact old text}"
After (`docs/conventions/git.md:NN`): "{exact new text}"

Proof that the matching infrastructure guarantee is active (in the real section, use a
backtick fence instead of the tildes):

~~~text
$ gh api repos/{owner}/{repo}/rulesets
{output}
~~~

User OK: YYYY-MM-DD
```

Process rule (not checked by the script): STOP and wait for the user's explicit OK on the
Before and After diff before any commit that changes `docs/conventions/git.md` or `CLAUDE.md`.

---

## Scope

**In scope:**
- {...}

**Out of scope:**
- {...}

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-01 | {...} | {...} | {Measurable outcome} |

---

## Test Strategy

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-01 | {Unit / Manual / Command} | {test path or command} | {...} |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | {path} | {Create / Modify} | {...} |

---

## Evidence

Evidence commit: {SHA of 7 to 40 hexadecimal characters}

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/{FEATURE_NAME}/`). `python scripts/check_specs.py` runs again
on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-01 | {Pass / Fail / Not run / Deferred: reason} | {Test output, command output} |

In a `Complete` document `check_specs.py` reports `Fail` and `Not run` as errors. A deliberate
deferral is written `Deferred: <reason>`: the check accepts it and lists it as a warning, so it
stays visible without blocking the change. `Deferred` without a reason is an error.

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | {...} | {Low / Medium / High} | {Open, or what closed it} |

---

## Self-Review

- **Weak points:** {...}
- **Risks:** {...}
- **What I would do differently:** {...}
- **Next improvement:** {Concrete action}
