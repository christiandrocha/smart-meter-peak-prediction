# CHANGE: Align confirmation rules with the repository guarantees

> One document for a small tooling or process change that meets every eligibility criterion.
> It replaces DEFINE, DESIGN, BUILD_REPORT and SHIPPED. If any criterion fails, use the full
> cycle (`/define`, `/design`, `/build`, `/ship`).

## Metadata

| Attribute | Value |
|---|---|
| **Feature** | ALIGN_CONFIRMATION_RULES |
| **Date** | 2026-11-06 |
| **Author** | christiandrocha (with Claude Code) |
| **Branch** | `change/align-confirmation-rules` |
| **Status** | Complete |
| **Source** | SDD process retrospective of 2026-11-05, Step 3; SMALL_CHANGE_TRACK D-84 and D-90 (Step 3 uses the CHANGE track with the reinforced E8 gate). Items chosen by the user on 2026-11-06: R1 and R2, R1 limited to branches of the current task |

Allowed status values: `Draft`, `Ready for Build`, `Complete`.

---

## Problem Statement

The agent rules in `docs/conventions/git.md` were written before the repository had any
server-side protection. On 2026-11-05 the user activated `delete_branch_on_merge` and the ruleset
`main-protection` (read again on 2026-11-06, output in Rule Changes). Two rules no longer match
those guarantees:

- **R1.** `git push --force-with-lease` needs the user's confirmation every time
  (`docs/conventions/git.md:44-47`), even on a branch created for the current task, after a
  rebase onto `main`. The ruleset makes `main` impossible to rewrite (`non_fast_forward` on the
  default branch, no bypass actors), and the lease refuses to overwrite commits the agent has not
  seen. On 2026-11-06 the rebase of `ship/small-change-track` after #44 needed a separate
  authorization for exactly this case.
- **R2.** The rule prefers `gh pr merge <N> --delete-branch` (`docs/conventions/git.md:48-49`).
  With `delete_branch_on_merge` GitHub already removes the remote head branch, and
  `--delete-branch` also deletes the local branch without the `git branch -d` merge check. The
  rule does not say that `git push --delete` is unnecessary after a merge.

The other confirmation rules stay: `git push --delete`, `git push origin :<branch>`,
`git branch -D`, `git push --force`, `git reset --hard`, `gh pr close` and `gh repo delete` are
not covered by any guarantee (the ruleset protects only `main`; local commands have none), and
the post-merge state check caught two "merged" statements that `gh` showed as `OPEN` on
2026-11-06 (#45 and #46).

---

## Eligibility

Every criterion must hold for the files the PR changes. Result: `Yes` (E8 may also be
`Relaxing`). The evidence cell is never empty: paste or cite the command output.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | No production file: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` (`git diff --name-only origin/main...HEAD`) | Yes | `git diff --name-only origin/main...HEAD` on 1cbe301 lists only `.claude/sdd/features/CHANGE_ALIGN_CONFIRMATION_RULES.md`, `CLAUDE.md`, `docs/conventions/git.md`: nothing under `src/`, `resources/`, `notebooks/`, `pipelines/`, nor `databricks.yml` |
| E2 | No contract change: nothing under `docs/contracts/` (same output) | Yes | Same output: nothing under `docs/contracts/` |
| E3 | No new ADR: no added `docs/adr/NNNN-*.md` (`git diff --name-status origin/main...HEAD`) | Yes | `git diff --name-status origin/main...HEAD`: `A` for this document, `M` for `CLAUDE.md` and `docs/conventions/git.md`; no `docs/adr/` file |
| E4 | No change to an archived DEFINE or DESIGN, which is `/iterate`; annotating archived BUILD_REPORT or SHIPPED rows is allowed (same output) | Yes | Same output: no file under `.claude/sdd/archive/` changed before the final commit, which only adds this document there |
| E5 | No change to the gates: neither `scripts/check_specs.py` nor a template that the script or the tests read (same output) | Yes | Same output: neither `scripts/check_specs.py` nor a template |
| E6 | No change under `tests/integration/` (same output) | Yes | Same output: nothing under `tests/` |
| E7 | No change to the runtime `dependencies` of `pyproject.toml`; the `dev` extra may change (`git diff origin/main...HEAD -- pyproject.toml`) | Yes | `git diff origin/main...HEAD -- pyproject.toml`: empty (0 lines) |
| E8 | Agent rules (`docs/conventions/git.md` and the rules for agents in `CLAUDE.md`) change only under a gate. Hardening is `Yes`; relaxing is `Relaxing` and needs the Rule Changes section. In doubt, it is relaxing (`git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md`) | Relaxing | R1 narrows what needs confirmation (`--force-with-lease` on a branch of the current task); R2 is hardening. `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md` on 1cbe301: 2 hunks, 22 changed lines, all equal to the Before and After text of Rule Changes (AC-144); `gh api` output in Rule Changes; User OK 2026-11-06, committed in e51e01b before the rules commit 1cbe301 |

---

## Rule Changes

R1 is relaxing, R2 is hardening; both are in this one gate. Exact text, before and after.

Before (`docs/conventions/git.md:44-49`):

```text
- These commands need the explicit confirmation of the user every time, one at a time:
  `git push --delete`, `git push origin :<branch>`, `git branch -D`,
  `git push --force` / `--force-with-lease`, `git reset --hard`, `gh pr close`,
  `gh repo delete`.
- Delete a remote branch only when its pull request state is exactly `MERGED`. Prefer
  `gh pr merge <N> --delete-branch`, which removes the branch only after a successful merge.
```

After (`docs/conventions/git.md:44-57`):

```text
- These commands need the explicit confirmation of the user every time, one at a time:
  `git push --delete`, `git push origin :<branch>`, `git branch -D`, `git push --force`,
  `git reset --hard`, `gh pr close`, `gh repo delete`.
- `git push --force-with-lease` needs the same confirmation, with one exception: it may run
  without it on a branch created for the current task (never `main`, never a branch of another
  task), to publish that branch after a rebase. Before each use, read the ruleset with
  `gh api repos/christiandrocha/smart-meter-peak-prediction/rulesets/26640008`; the exception
  holds only if `main-protection` is `active`, targets the default branch, has the
  `non_fast_forward` rule and no bypass actors. If not, or in doubt, ask.
- Delete a remote branch only when its pull request state is exactly `MERGED`. GitHub removes
  the head branch on merge (`delete_branch_on_merge`), so after a merge do not run
  `git push --delete`: confirm the removal with `git ls-remote --heads origin <branch>`. Merge
  without `--delete-branch`, because `gh pr merge --delete-branch` also deletes the local branch
  on its own; delete the local branch with `git branch -d`, which refuses an unmerged branch.
```

Before (`CLAUDE.md:39-43`):

```text
8. Git and `gh` follow the mandatory rules in `docs/conventions/git.md`: verify a pull request's
   state with `gh` before any post-merge step, never chain a destructive command after a state
   read, get explicit confirmation for each destructive command, check that command's own exit
   code (no `-q` with pipes, `grep` or `||` status messages), and confirm a delete with a
   separate read.
```

After (`CLAUDE.md:39-44`):

```text
8. Git and `gh` follow the mandatory rules in `docs/conventions/git.md`: verify a pull request's
   state with `gh` before any post-merge step, never chain a destructive command after a state
   read, get explicit confirmation for each destructive command (the one exception,
   `--force-with-lease` on a branch of the current task, is in `git.md`), check that
   command's own exit code (no `-q` with pipes, `grep` or `||` status messages), and confirm a
   delete with a separate read.
```

Proof that the matching guarantees are active, read on 2026-11-06:

```text
$ gh api repos/christiandrocha/smart-meter-peak-prediction -q '{delete_branch_on_merge,allow_merge_commit,allow_squash_merge,allow_rebase_merge,default_branch}'
{"allow_merge_commit":true,"allow_rebase_merge":true,"allow_squash_merge":true,"default_branch":"main","delete_branch_on_merge":true}
$ gh api repos/christiandrocha/smart-meter-peak-prediction/rulesets -q '.[]|{id,name,enforcement,target}'
{"enforcement":"active","id":26640008,"name":"main-protection","target":"branch"}
$ gh api repos/christiandrocha/smart-meter-peak-prediction/rulesets/26640008 -q '{name,enforcement,conditions,bypass_actors,rules:[.rules[]|{type,parameters}]}'
{"bypass_actors":[],"conditions":{"ref_name":{"exclude":[],"include":["~DEFAULT_BRANCH"]}},"enforcement":"active","name":"main-protection","rules":[{"parameters":null,"type":"deletion"},{"parameters":null,"type":"non_fast_forward"},{"parameters":{"allowed_merge_methods":["merge","squash","rebase"],"dismiss_stale_reviews_on_push":false,"require_code_owner_review":false,"require_extra_approval_for_unattributed_changes":true,"require_last_push_approval":false,"required_approving_review_count":0,"required_review_thread_resolution":false,"required_reviewers":[]},"type":"pull_request"},{"parameters":{"do_not_enforce_on_create":false,"required_status_checks":[{"context":"checks","integration_id":15368},{"context":"bundle-validate","integration_id":15368}],"strict_required_status_checks_policy":false},"type":"required_status_checks"}]}
```

| Rule | Guarantee | Where in the output |
|---|---|---|
| R1 | `main` cannot be rewritten by any push | ruleset 26640008: `enforcement` `active`, `include` `~DEFAULT_BRANCH`, rule `non_fast_forward`, `bypass_actors` `[]` |
| R2 | GitHub removes the head branch after a merge | repository: `delete_branch_on_merge` `true` |

User OK: 2026-11-06 (the user's explicit OK on the Before and After text above, given in the
session before any commit that changes `docs/conventions/git.md` or `CLAUDE.md`)

---

## Scope

**In scope:**
- `docs/conventions/git.md:44-49`: R1 and R2 as in Rule Changes.
- `CLAUDE.md:39-43`: rule 8 names the R1 exception and points to `git.md`.

**Out of scope:**
- Any other rule of `git.md` or `CLAUDE.md`, including the confirmation of `git push --delete`,
  `git push origin :<branch>`, `git branch -D`, `git push --force`, `git reset --hard`,
  `gh pr close` and `gh repo delete` (no guarantee covers them).
- The exception for branches not created in the current task (user decision 2026-11-06).
- Repository settings and the ruleset (read only; nothing changes on GitHub).
- A machine check of the R1 conditions or of the order of the OK and the commit
  (SMALL_CHANGE_TRACK F-01).

---

## Acceptance Criteria

| ID | Given | When | Then |
|---|---|---|---|
| AC-139 | `docs/conventions/git.md` on the final head | The confirmation list is read | It names `git push --force` and no longer names `--force-with-lease`; the other six commands are unchanged |
| AC-140 | The same file | The R1 rule is read | It allows `--force-with-lease` without confirmation only on a branch created for the current task, never `main` nor another task's branch, only after reading ruleset 26640008 and finding it `active` on the default branch with `non_fast_forward` and no bypass actors, and says to ask otherwise or in doubt |
| AC-141 | The same file | The R2 rule is read | It keeps "only when `MERGED`", says GitHub removes the head branch, forbids `git push --delete` after a merge, requires `git ls-remote --heads origin <branch>`, says to merge without `--delete-branch`, and to delete the local branch with `git branch -d` |
| AC-142 | `CLAUDE.md` rule 8 | It is read | It names the one exception and points to `git.md`; every other clause is unchanged |
| AC-143 | The guarantees on the day of the final head | The three `gh api` reads of Rule Changes run again | The output still shows `delete_branch_on_merge` `true` and ruleset 26640008 `active` on `~DEFAULT_BRANCH` with `non_fast_forward` and `bypass_actors` `[]` |
| AC-144 | The text in the files and in Rule Changes | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md` runs | Its removed and added lines equal the Before and After text of Rule Changes, and nothing else in those files changed |
| AC-145 | The whole repository on the final head | `python scripts/check_specs.py`, `pytest tests/test_check_specs.py` and `pre-commit run --all-files` run | 0 errors (the `Relaxing` gate of this document passes); warnings only as on `main` plus this document's own `Open` findings; all tests pass, all hooks pass |

---

## Test Strategy

The rules are prose, so each criterion is proved by a command whose output goes in Evidence.

| AC | Test type | Test location | How it proves the criterion |
|---|---|---|---|
| AC-139 | Command | `sed -n 44,46p docs/conventions/git.md` and `grep -n 'force-with-lease' docs/conventions/git.md` | The list shows `git push --force` and the six others; `--force-with-lease` appears only in the R1 rule |
| AC-140 | Command | `sed -n 47,52p docs/conventions/git.md` | Every condition of the AC is in the text |
| AC-141 | Command | `sed -n 53,57p docs/conventions/git.md` | Every part of the AC is in the text |
| AC-142 | Command | `git diff origin/main...HEAD -- CLAUDE.md` | Only rule 8 changes, by the exception clause and the rewrap |
| AC-143 | Command | The three `gh api` reads of Rule Changes | Output pasted in Evidence |
| AC-144 | Command | `git diff origin/main...HEAD -- docs/conventions/git.md CLAUDE.md` compared with Rule Changes | Same lines, no other hunk |
| AC-145 | Command | The three commands on the final head | Output pasted in Evidence and in the PR description |

---

## File Manifest

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `docs/conventions/git.md` | Modify | R1 and R2 (AC-139 to AC-141); only after the user's OK |
| 2 | `CLAUDE.md` | Modify | Rule 8 names the R1 exception (AC-142); only after the user's OK |
| 3 | `.claude/sdd/features/CHANGE_ALIGN_CONFIRMATION_RULES.md` | Create, then move to `archive/ALIGN_CONFIRMATION_RULES/` | This document (D-91: the final commit touches only this document) |

Order of commits: this document with `User OK: YYYY-MM-DD` first, then the rules commit (the
evidence commit), then the final commit of this document.

---

## Evidence

Evidence commit: 1cbe301

Process rule D-91 (not checked by the script): the evidence commit is the last commit of the PR
that touches files other than this document. The final commit touches only this document (status
`Complete` and the move to `archive/ALIGN_CONFIRMATION_RULES/`). `python scripts/check_specs.py`
runs again on the final head and its output goes in the PR description.

| AC | Result | Evidence |
|---|---|---|
| AC-139 | Pass | `sed -n 44,46p docs/conventions/git.md`: the list names `git push --delete`, `git push origin :<branch>`, `git branch -D`, `git push --force`, `git reset --hard`, `gh pr close`, `gh repo delete`; `grep -n force-with-lease` matches only line 47, the R1 rule |
| AC-140 | Pass | `sed -n 47,52p`: branch created for the current task, never `main`, never another task's branch, after a rebase; read ruleset 26640008 before each use; `active`, default branch, `non_fast_forward`, no bypass actors; "If not, or in doubt, ask." |
| AC-141 | Pass | `sed -n 53,57p`: "only when ... `MERGED`" kept; GitHub removes the head branch (`delete_branch_on_merge`); no `git push --delete` after a merge; `git ls-remote --heads origin <branch>`; merge without `--delete-branch`; local delete with `git branch -d` |
| AC-142 | Pass | `git diff origin/main...HEAD -- CLAUDE.md`: only rule 8, 3 lines removed and 4 added, adding the exception clause that points to `git.md` and rewrapping; the other clauses keep their words |
| AC-143 | Pass | Read again on 2026-11-06 after 1cbe301: repository `delete_branch_on_merge` `true`, default branch `main`; ruleset 26640008 `main-protection` `enforcement` `active`, `include` `~DEFAULT_BRANCH`, `bypass_actors` `[]`, rules `deletion`, `non_fast_forward`, `pull_request`, `required_status_checks` |
| AC-144 | Pass | `git diff -U0` of the two files: 22 changed lines in 2 hunks; each line is in the Before or After blocks of Rule Changes (0 missing), and no other hunk |
| AC-145 | Pass | On the final tree: `check_specs.py` `59 document(s) checked, 0 error(s), 6 warning(s)`, exit 0, so the `Relaxing` gate of this document passes; the warnings are the four of `main` (INGESTION_GUARD I-11, INGESTION_GUARD I-12, FOLLOW_UP_TEMPLATE I-01, FOLLOW_UP_TEMPLATE I-02) and this document's own ALIGN_CONFIRMATION_RULES I-01 and I-02 (rule b). `pytest tests/test_check_specs.py`: 114 passed, 1 skipped (the AC-119 self-test). `pre-commit run --all-files`: all hooks passed |

---

## Issues & Follow-ups

| ID | Issue | Severity | Follow-up |
|---|---|---|---|
| I-01 | The R1 conditions (branch of the current task, ruleset read before each use) are a process rule; nothing checks them | Low | Open: same class as SMALL_CHANGE_TRACK F-01 (history checks) |
| I-02 | The R1 rule names ruleset id 26640008; if the ruleset is recreated with a new id, the read fails and the exception does not apply until the rule is updated | Low | Open: the failure mode is safe (ask) |

---

## Self-Review

- **Weak points:** The ACs check the text of the rules, not the behaviour of an agent following
  them. The R1 conditions are not machine-checked (I-01).
- **Risks:** A branch that two tasks share could be force-pushed by mistake; the lease and the
  "current task" condition reduce, not remove, that risk. A recreated ruleset breaks the read
  (I-02), which falls back to asking.
- **What I would do differently:** Record the retrospective's Step 3 table in the repository on
  the day it is written; it was not, so the items were chosen again on 2026-11-06.
- **Next improvement:** After the merge, the first rebase of a task branch uses R1 with the
  ruleset read; that run shows whether the condition text is clear enough.
