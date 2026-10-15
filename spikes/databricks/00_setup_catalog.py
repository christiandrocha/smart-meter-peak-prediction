# Databricks notebook source
# Spike 00 (A-09, DA-06). STATUS: written, NOT RUN. Throwaway code, never imported by src/.
#
# Questions
#   A-09  Can Free Edition create the catalog `smart_meter_dev`?
#   DA-06 Does `databricks bundle deploy` create a pipeline before its target catalog exists?
#
# Pass criteria
#   A-09  `CREATE CATALOG IF NOT EXISTS smart_meter_dev` succeeds, the schemas bronze, silver,
#         gold, ml and the Volumes bronze.landing and bronze.checkpoints exist afterwards.
#         On failure the notebook creates the fallback layout `workspace.smart_meter_dev_<layer>`
#         (ADR 0003) and prints FAIL for A-09 and PASS/FAIL for the fallback.
#   DA-06 (manual, do this BEFORE running this notebook, while the catalog does not exist):
#         1. mkdir a scratch folder outside the repository and put this `databricks.yml` in it:
#              bundle: {name: spike_da06}
#              targets: {dev: {mode: development, default: true}}
#              resources:
#                pipelines:
#                  da06:
#                    name: da06
#                    serverless: true
#                    catalog: smart_meter_dev
#                    schema: silver
#                    libraries: [{file: {path: ./p.sql}}]
#            plus a one-line `p.sql`:  CREATE MATERIALIZED VIEW da06_mv AS SELECT 1 AS x;
#         2. `databricks bundle deploy -t dev` from that folder.
#            PASS = deploy succeeds with the catalog absent; FAIL = it errors on the catalog.
#         3. `databricks bundle destroy -t dev` to remove it (one pipeline per type only).
#         Record the outcome of step 2 in ADR 0001 (DA-06).
#
# Run: attach to serverless compute and run all cells. Idempotent.

# COMMAND ----------

CATALOG = "smart_meter_dev"
FALLBACK_CATALOG = "workspace"
LAYERS = ["bronze", "silver", "gold", "ml"]
VOLUMES = [("bronze", "landing"), ("bronze", "checkpoints")]


def create_layout(catalog: str, schema_of) -> None:
    for layer in LAYERS:
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema_of(layer)}")
    for layer, volume in VOLUMES:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema_of(layer)}.{volume}")


def layout_exists(catalog: str, schema_of) -> bool:
    schemas = {r[0] for r in spark.sql(f"SHOW SCHEMAS IN {catalog}").collect()}
    if not {schema_of(layer) for layer in LAYERS} <= schemas:
        return False
    for layer, volume in VOLUMES:
        names = {r["volume_name"] for r in spark.sql(f"SHOW VOLUMES IN {catalog}.{schema_of(layer)}").collect()}
        if volume not in names:
            return False
    return True


# COMMAND ----------

results = {}
try:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
    create_layout(CATALOG, lambda layer: layer)
    results["A-09"] = layout_exists(CATALOG, lambda layer: layer)
    print(f"A-09 main layout {CATALOG}.<layer>: {'PASS' if results['A-09'] else 'FAIL'}")
except Exception as exc:  # noqa: BLE001  (spike: report any failure and try the fallback)
    results["A-09"] = False
    print(f"A-09 FAIL: {type(exc).__name__}: {str(exc).splitlines()[0]}")
    schema_of = lambda layer: f"smart_meter_dev_{layer}"  # noqa: E731
    try:
        create_layout(FALLBACK_CATALOG, schema_of)
        ok = layout_exists(FALLBACK_CATALOG, schema_of)
        print(f"A-09 fallback {FALLBACK_CATALOG}.smart_meter_dev_<layer>: {'PASS' if ok else 'FAIL'}")
    except Exception as exc2:  # noqa: BLE001
        print(f"A-09 fallback FAIL: {type(exc2).__name__}: {str(exc2).splitlines()[0]}")

# COMMAND ----------

# Rerun safety: the same statements again must change nothing (idempotent setup, OD-05).
if results["A-09"]:
    create_layout(CATALOG, lambda layer: layer)
    print("rerun: PASS (no error)")
print("Record A-09 and DA-06 in docs/adr/0001-runtime-environment-constraints.md")
