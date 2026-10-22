"""Spike 06 driver. Throwaway code, never imported by src/.

Uploads 06_spike_pipeline_guard_probe.py and submits it as a one-time serverless notebook task on
environment version 2 (idle probe: DA-20, DA-23). Then, with the ingestion job idle, it starts one
update of the pipeline with no new input (full_refresh=False), submits the probe again right
after (busy probe: what a pre-check started after start_update sees, DA-26), and reads
pipelines.get every 2 s until the update is terminal (DA-22, DA-26). It prints PASS or FAIL per
assumption. No table changes beyond what a normal incremental refresh does with no new input.

Record the results in docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md
(Platform probe) and in docs/spikes/README.md.

Prerequisites: the bundle is deployed to dev; Databricks CLI profile or env auth.
Install: pip install -e ".[integration]".

Run:  python spikes/databricks/06_spike_pipeline_guard_probe_submit.py [--profile P]
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
from datetime import timedelta
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.compute import Environment
from databricks.sdk.service.jobs import JobEnvironment, NotebookTask, SubmitTask
from databricks.sdk.service.workspace import ImportFormat, Language

HERE = Path(__file__).resolve().parent
NOTEBOOK = HERE / "06_spike_pipeline_guard_probe.py"
PREFIX = "spike_06"
INGESTION = "smart_meter_ingestion"
TERMINAL_UPDATE = {"COMPLETED", "FAILED", "CANCELED"}


def base_name(name: str) -> str:
    return re.sub(r"^\[dev [^\]]+\] ", "", name or "")


def find_ids(w: WorkspaceClient) -> tuple[int, str]:
    jobs = [j for j in w.jobs.list() if j.settings and base_name(j.settings.name) == INGESTION]
    if len(jobs) != 1:
        raise SystemExit(f"expected one {INGESTION} job, found {len(jobs)}")
    job = w.jobs.get(jobs[0].job_id)
    pipeline_ids = {t.pipeline_task.pipeline_id for t in job.settings.tasks if t.pipeline_task}
    if len(pipeline_ids) != 1:
        raise SystemExit(f"expected one pipeline task in {INGESTION}, found {pipeline_ids}")
    return job.job_id, pipeline_ids.pop()


def submit_probe(w: WorkspaceClient, path: str, label: str, params: dict[str, str]):
    return w.jobs.submit(
        run_name=f"{PREFIX}_{label}",
        tasks=[
            SubmitTask(
                task_key="probe",
                notebook_task=NotebookTask(notebook_path=path, base_parameters=params),
                environment_key="env2",
                timeout_seconds=600,
            )
        ],
        environments=[
            JobEnvironment(environment_key="env2", spec=Environment(environment_version="2"))
        ],
    )


def probe_output(w: WorkspaceClient, waiter) -> dict:
    run_id = waiter.response.run_id
    try:
        waiter.result(timeout=timedelta(minutes=15))
    except Exception as exc:  # noqa: BLE001
        print(f"probe run {run_id} did not succeed: {type(exc).__name__}: {str(exc)[:300]}")
    run = w.jobs.get_run(run_id)
    task = run.tasks[0]
    out = w.jobs.get_run_output(task.run_id)
    if out.error:
        return {"error": out.error[:800], "run_id": run_id}
    result = json.loads(out.notebook_output.result)
    result["run_id"] = run_id
    result["task_start_ms"] = task.start_time
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile")
    parser.add_argument("--idle-only", action="store_true", help="skip the pipeline update")
    args = parser.parse_args()
    w = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    me = w.current_user.me().user_name
    root = f"/Users/{me}/spikes/{PREFIX}"
    path = f"{root}/06_spike_pipeline_guard_probe"
    w.workspace.mkdirs(root)
    w.workspace.import_(
        path,
        content=base64.b64encode(NOTEBOOK.read_bytes()).decode(),
        format=ImportFormat.SOURCE,
        language=Language.PYTHON,
        overwrite=True,
    )
    job_id, pipeline_id = find_ids(w)
    params = {"ingestion_job_id": str(job_id), "pipeline_id": pipeline_id}
    print(f"ingestion job {job_id}, pipeline {pipeline_id}")
    results: dict[str, str] = {}

    # idle probe
    idle = probe_output(w, submit_probe(w, path, "idle", params))
    print("\nidle probe:", json.dumps(idle, indent=1))
    ok20 = "error" not in idle and idle.get("client_with_timeouts") == "ok"
    results["DA-20 sdk, auth, timeouts, reads (no %pip)"] = "PASS" if ok20 else "FAIL"
    results["DA-23 jobs.list(name) returns exactly the job"] = (
        "PASS" if idle.get("jobs_list_by_name_ids") == [job_id] else "FAIL"
    )

    if args.idle_only:
        w.workspace.delete(root, recursive=True)
        for key, value in results.items():
            print(f"  {value:4}  {key}")
        return 0 if all(v == "PASS" for v in results.values()) else 1

    # busy probe during a no-op update
    if list(w.jobs.list_runs(job_id=job_id, active_only=True)):
        print("ingestion job is running; stop here (DA-13)")
        return 1
    started = time.time()
    update_id = w.pipelines.start_update(pipeline_id, full_refresh=False).update_id
    print(f"\nstarted update {update_id}")
    busy_waiter = submit_probe(w, path, "busy", params)
    sequence: list[tuple[float, str]] = []
    first_seen = None
    creation_raw = None
    while True:
        p = w.pipelines.get(pipeline_id)
        latest = (p.latest_updates or [None])[0]
        state = latest.state.value if latest and latest.state else "?"
        if latest and latest.update_id == update_id and first_seen is None:
            first_seen = time.time() - started
            creation_raw = latest.creation_time
        if not sequence or sequence[-1][1] != state:
            sequence.append((round(time.time() - started, 1), state))
            print(f"  t+{sequence[-1][0]:>6} s  {state}")
        if latest and latest.update_id == update_id and state in TERMINAL_UPDATE:
            break
        if time.time() - started > 1800:
            print("update not terminal after 30 min")
            break
        time.sleep(2)
    duration = time.time() - started
    print(f"update {update_id}: {duration:.0f} s, creation_time {creation_raw!r}")
    results["DA-22 latest_updates[0] shows the update with a non-terminal state"] = (
        "PASS"
        if first_seen is not None
        and first_seen < 10
        and any(s not in TERMINAL_UPDATE for _, s in sequence)
        else "FAIL"
    )

    busy = probe_output(w, busy_waiter)
    print("\nbusy probe:", json.dumps(busy, indent=1))
    seen = [u for u in busy.get("latest_updates", []) if u["update_id"] == update_id]
    busy_active = bool(seen) and seen[0]["state"].split(".")[-1] not in TERMINAL_UPDATE
    if busy.get("task_start_ms"):
        lag = busy["task_start_ms"] / 1000 - started
        print(f"busy probe task started {lag:.0f} s after start_update")
    results["DA-26 a pre-check started after start_update sees it active"] = (
        "PASS" if busy_active else "FAIL"
    )

    w.workspace.delete(root, recursive=True)
    print("\nRESULTS")
    for key, value in results.items():
        print(f"  {value:4}  {key}")
    return 0 if all(v == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
