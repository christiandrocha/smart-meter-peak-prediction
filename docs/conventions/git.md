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

- One branch per feature: `feat/<feature-kebab>`. Spikes: `spike/<topic>`.
- A pull request links its DEFINE and DESIGN documents and lists the ACs it covers
  (see `.github/pull_request_template.md`).
- CI must pass: lint, tests, `scripts/check_specs.py`.

## Releases

Semantic versioning. A release closes one or more shipped features; `/ship` updates
`CHANGELOG.md`. Tag as `vX.Y.Z`.
