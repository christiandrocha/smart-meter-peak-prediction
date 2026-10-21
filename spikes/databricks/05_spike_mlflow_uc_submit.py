"""Spike 05 driver. STATUS: written, NOT RUN. Throwaway code, never imported by src/.

Uploads 05_spike_mlflow_uc.py as a notebook and submits it as a one-time serverless job with two
notebook tasks: `main` (A-04, A-12, A-16 in one process) and `retrain`, which depends on it
(A-16 across tasks). Then it checks UC lineage from the feature table to the FE model, prints
PASS/FAIL per check and, unless --keep, removes every object the spike created.

Assumptions answered (record them in docs/adr/0007-peak-model-runtime-and-data-assumptions.md):
  A-04  MLflow UC registry, alias `champion`, load by alias
  A-12  Feature Engineering on serverless: install, create_table, create_training_set,
        fe.log_model, fe.score_batch, feature lineage
  A-16  deterministic HistGradientBoostingClassifier, in one process and across tasks
  OD-08 (informational) threshold as a model version tag

Prerequisites (run by the user): catalog and schema `ml` exist (setup task or spike 00);
Databricks CLI profile or env auth. Install: pip install -e ".[integration]".

Run:  python spikes/databricks/05_spike_mlflow_uc_submit.py [--profile P] [--catalog C] \
          [--schema S] [--keep]
For the A-09 fallback layout pass --catalog workspace --schema smart_meter_dev_ml.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import NotebookTask, SubmitTask, TaskDependency
from databricks.sdk.service.workspace import ImportFormat, Language

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "05_spike_mlflow_uc.py"
PREFIX = "spike_05"
LINEAGE_WAIT_S = 300


def lineage_mentions_model(w: WorkspaceClient, table: str, model: str) -> tuple[bool, str]:
    """UC lineage of the feature table, searched for the model name (shape varies by release)."""
    deadline = time.time() + LINEAGE_WAIT_S
    last = ""
    while time.time() < deadline:
        try:
            resp = w.api_client.do(
                "GET",
                "/api/2.0/lineage-tracking/table-lineage",
                query={"table_name": table, "include_entity_lineage": "true"},
            )
            last = json.dumps(resp)
            if model in last or model.split(".")[-1] in last:
                return True, "model found downstream of the feature table"
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {str(exc)[:300]}"
        time.sleep(30)
    return (
        False,
        f"model not in table lineage after {LINEAGE_WAIT_S} s; last response: {last[:600]}",
    )


def cleanup(w: WorkspaceClient, catalog: str, schema: str, root: str, experiment: str) -> None:
    fq = f"{catalog}.{schema}.{PREFIX}"
    for model in (f"{fq}_model_fe", f"{fq}_model_plain"):
        try:
            # UC refuses to delete a model that still has versions: drop aliases and versions first.
            info = w.registered_models.get(model, include_aliases=True)
            for alias in info.aliases or []:
                w.registered_models.delete_alias(model, alias.alias_name)
            for version in w.model_versions.list(model):
                w.model_versions.delete(model, version.version)
            w.registered_models.delete(model)
            print("deleted model", model)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: delete model {model} manually ({type(exc).__name__})")
    for table in (f"{fq}_features", f"{fq}_labels", f"{fq}_scores"):
        try:
            w.tables.delete(table)
            print("deleted table", table)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: delete table {table} manually ({type(exc).__name__})")
    try:
        exp = w.experiments.get_by_name(experiment).experiment
        w.experiments.delete_experiment(exp.experiment_id)
        print("deleted experiment", experiment)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: delete experiment {experiment} manually ({type(exc).__name__})")
    try:
        w.workspace.delete(root, recursive=True)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default="smart_meter_dev")
    parser.add_argument("--schema", default="ml")
    parser.add_argument("--profile")
    parser.add_argument("--keep", action="store_true", help="keep the spike objects for inspection")
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    me = w.current_user.me().user_name
    root = f"/Users/{me}/spikes/{PREFIX}"
    experiment = f"/Users/{me}/spikes/{PREFIX}_experiment"
    notebook_path = f"{root}/05_spike_mlflow_uc"
    w.workspace.mkdirs(root)
    w.workspace.import_(
        notebook_path,
        content=base64.b64encode(NOTEBOOK.read_bytes()).decode(),
        format=ImportFormat.SOURCE,
        language=Language.PYTHON,
        overwrite=True,
    )
    params = {"catalog": args.catalog, "schema": args.schema, "prefix": PREFIX}

    def task(key: str, mode: str, after: str | None = None) -> SubmitTask:
        return SubmitTask(
            task_key=key,
            notebook_task=NotebookTask(
                notebook_path=notebook_path, base_parameters={**params, "mode": mode}
            ),
            depends_on=[TaskDependency(task_key=after)] if after else None,
            timeout_seconds=2400,
        )

    results: dict[str, str] = {}
    started = time.time()
    waiter = w.jobs.submit(
        run_name="spike_05_mlflow_uc",
        tasks=[task("main", "main"), task("retrain", "retrain", after="main")],
    )
    run_id = waiter.response.run_id
    print(f"submitted run {run_id}")
    try:
        waiter.result(timeout=timedelta(minutes=60))
    except Exception as exc:  # noqa: BLE001
        print(f"run did not succeed ({type(exc).__name__}: {str(exc)[:300]}); reading task outputs")
    run = w.jobs.get_run(run_id)
    print(f"run {run_id} after {time.time() - started:.0f} s: {run.state.result_state}")

    for t in run.tasks or []:
        out = w.jobs.get_run_output(t.run_id)
        if out.error:
            print(f"\n[{t.task_key}] task error: {out.error[:800]}")
            results[f"{t.task_key} task"] = "FAIL"
            continue
        payload = json.loads(out.notebook_output.result) if out.notebook_output else {}
        print(f"\n[{t.task_key}] versions: {payload.get('info', {}).get('versions')}")
        for key, check in payload.get("checks", {}).items():
            results[key] = "PASS" if check["pass"] else "FAIL"
            print(f"  {results[key]}  {key}: {check['detail']}")
        for key, value in payload.get("info", {}).items():
            if key != "versions":
                print(f"  info  {key}: {value}")
        for key, value in payload.get("errors", {}).items():
            print(f"  error {key}: {value}")

    fq = f"{args.catalog}.{args.schema}.{PREFIX}"
    if results.get("A-12 fe.log_model (probability pyfunc)") == "PASS":
        ok, detail = lineage_mentions_model(w, f"{fq}_features", f"{fq}_model_fe")
        results["A-12 UC lineage feature table -> model"] = "PASS" if ok else "FAIL"
        print(f"  {'PASS' if ok else 'FAIL'}  A-12 UC lineage: {detail}")
        if not ok:
            print("  check Catalog Explorer > feature table > Lineage before recording a FAIL")

    if args.keep:
        print(f"\n--keep: objects left under {fq}_* and experiment {experiment}")
    else:
        cleanup(w, args.catalog, args.schema, root, experiment)

    print("\nSUMMARY (record in ADR 0007):")
    for key, value in results.items():
        print(f"  {key}: {value}")
    return 1 if not results or "FAIL" in results.values() else 0


if __name__ == "__main__":
    sys.exit(main())
