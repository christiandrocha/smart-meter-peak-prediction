# Git conventions

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <summary in imperative, max 72 chars>

<optional body: why, not what>

Refs: <FEATURE_NAME>, AC-03
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, `spec`
(`spec` for changes to `.claude/sdd/` documents).

## Branches and pull requests

- One branch per phase PR of a full spec: `spec/<feature-kebab>`, `build/<feature-kebab>`,
  `ship/<feature-kebab>`. A CHANGE-track change (`.claude/sdd/README.md`): `change/<feature-kebab>`.
  Spikes: `spike/<topic>`.
- A pull request links its DEFINE and DESIGN documents and lists the ACs it covers
  (see `.github/pull_request_template.md`).
- CI must pass: lint, tests, `scripts/check_specs.py`.

## Rules for agents (mandatory)

These rules bind any agent, and any person, running git or `gh` in this repository.

### Verify before acting

- Never take a pull request's state from what was said about it. Before any post-merge step
  (pulling `main`, tagging, deleting a branch), run
  `gh pr view <N> --json state,mergedAt,headRefName`.
- If the observed state differs from the stated one (for example "merged" was said and `gh`
  returns `OPEN`), stop and report the difference. Do not continue.

### Destructive commands

- Never chain a destructive command (with `;`, `&&` or `|`) after a command that reads state.
  Read the state, evaluate the result, and only then run the destructive command in a separate
  call.
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
- For a destructive command, check the exit code of that command itself. Do not combine `-q`
  with pipes, `grep` or `||` fallbacks to produce status messages. After a delete, confirm it with
  a separate read (for example `git ls-remote --heads origin <branch>`).
  Motivation (2026-11-05, #35 and #36): `git push -q origin --delete <branch> 2>&1 | grep -v
  '^remote:' || echo "remote <branch> already gone"` deleted both branches, but the silent push
  left `grep -v` with no input, `grep` exited 1, and the `||` printed "already gone", so the
  deletion was reported as GitHub's.

### Scope

- Act only on the branches and pull requests of the current task of the spec. Do not clean up
  other branches along the way.
- When the ship phase ends, record in the SHIPPED document the merged pull requests (number and
  merge commit SHA) and the branches removed (section *Pull Requests and Branches*).

## Releases

Semantic versioning. A release closes one or more shipped features; `/ship` updates
`CHANGELOG.md`. Tag as `vX.Y.Z`.
