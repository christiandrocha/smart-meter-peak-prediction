# Databricks Asset Bundles

A bundle is the project's deployable unit: code plus jobs, pipelines and other resources as
YAML, deployed per target.

```text
databricks.yml            bundle name, variables, targets, includes
resources/
├── jobs.yml              jobs and tasks
├── pipelines.yml         Lakeflow pipelines
└── schemas.yml           schemas and volumes (optional)
src/                      code referenced by resources
```

## Commands

```bash
databricks auth login --host <workspace-url>   # OAuth, writes a profile
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev <job_or_pipeline_key>
databricks bundle destroy -t dev                # removes deployed resources
```

## Conventions

- `mode: development` on the dev target prefixes resource names with the user and pauses
  schedules, so experiments never collide with a shared deployment.
- Everything environment-specific is a variable (`${var.catalog}`); targets override them.
- No credentials in YAML. Jobs read secrets with `dbutils.secrets.get(scope, key)`.
- CI runs `databricks bundle validate`; deployment from CI uses a service principal.

Source: https://docs.databricks.com/aws/en/dev-tools/bundles/
