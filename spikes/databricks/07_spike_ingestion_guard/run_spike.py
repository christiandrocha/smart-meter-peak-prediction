"""Spike 07 driver (INGESTION_GUARD). Throwaway code, never imported by src/.

Deploys the throwaway bundle in this folder (target dev), reads the deployed jobs back, runs
spike_07_guarded once, prints PASS/FAIL per assumption, then validates and deploys target cycle
(two jobs that reference each other). Both targets are destroyed at the end unless --keep.
Nothing in the project bundle is changed. The Silver/Gold pipeline is only read: the pipeline
task job is deployed and read back, never run.

Assumptions (BRAINSTORM_INGESTION_GUARD, Assumptions)
  A-25  disable_auto_optimization on a pipeline_task is accepted by deploy and kept on the
        deployed task (acceptance only; its effect needs a failed update and is out of scope).
  A-26  a job with one notebook task on environment version 2 and the other notebook tasks on the
        default environment deploys and runs; the probe sees databricks-sdk 0.40.0.
  A-27  with max_retries 0 and disable_auto_optimization, a failed notebook task has exactly 1
        attempt. The control task (max_retries 0 only, the v0.1.0 ingest_kafka settings) shows
        whether auto-optimization retries in this workspace today: 2 attempts reproduces F-33,
        1 attempt makes the A-27 result inconclusive.
  A-29  the run-as identity reads pipelines.get(id) with state and latest_updates.
  A-30  INFO, not pass/fail: does a two-way job reference fail at validate, at deploy, or work?
        The one-way reference (dev target) must resolve to a numeric job id.

Record the results in ADR 0013 (or the BRAINSTORM Assumptions until it exists) and in
docs/spikes/README.md.

Prerequisites: the project bundle is deployed to dev (the pipeline exists); Databricks CLI
v0.298.0 or later with a profile or env auth. Install: pip install -e ".[integration]".

Run:  python spikes/databricks/07_spike_ingestion_guard/run_spike.py [--profile P] [--keep]
          [--engine terraform|direct]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient

HERE = Path(__file__).resolve().parent
INGESTION = "smart_meter_ingestion"
TERMINAL = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}


def base_name(name: str) -> str:
    return re.sub(r"^\[dev [^\]]+\] ", "", name or "")


def find_pipeline_id(w: WorkspaceClient) -> str:
    jobs = [j for j in w.jobs.list() if j.settings and base_name(j.settings.name) == INGESTION]
    if len(jobs) != 1:
        raise SystemExit(f"expected one {INGESTION} job, found {len(jobs)}")
    job = w.jobs.get(jobs[0].job_id)
    ids = {t.pipeline_task.pipeline_id for t in job.settings.tasks if t.pipeline_task}
    if len(ids) != 1:
        raise SystemExit(f"expected one pipeline task in {INGESTION}, found {ids}")
    return ids.pop()


class Bundle:
    def __init__(self, profile: str | None, engine: str | None, pipeline_id: str) -> None:
        self.common = ["--var", f"pipeline_id={pipeline_id}"]
        if profile:
            self.common += ["--profile", profile]
        self.env = dict(os.environ)
        if engine:
            self.env["DATABRICKS_BUNDLE_ENGINE"] = engine

    def run(self, *args: str) -> subprocess.CompletedProcess:
        cmd = ["databricks", "bundle", *args, *self.common]
        print(f"\n$ databricks bundle {' '.join(args)}")
        return subprocess.run(cmd, cwd=HERE, env=self.env, capture_output=True, text=True)

    def job_ids(self, target: str) -> dict[str, int]:
        res = self.run("summary", "-t", target, "-o", "json")
        if res.returncode != 0:
            raise SystemExit(f"bundle summary failed:\n{tail(res)}")
        jobs = json.loads(res.stdout)["resources"]["jobs"]
        return {key: int(value["id"]) for key, value in jobs.items()}


def tail(res: subprocess.CompletedProcess, lines: int = 15) -> str:
    text = (res.stdout + res.stderr).strip().splitlines()
    return "\n".join(f"    {line}" for line in text[-lines:])


def wait_run(w: WorkspaceClient, run_id: int, limit: int = 1800):
    started = time.time()
    while True:
        run = w.jobs.get_run(run_id)
        if run.state and run.state.life_cycle_state and run.state.life_cycle_state.value in TERMINAL:
            return run
        if time.time() - started > limit:
            raise SystemExit(f"run {run_id} not terminal after {limit} s")
        time.sleep(10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile")
    parser.add_argument("--keep", action="store_true", help="do not destroy the spike targets")
    parser.add_argument("--engine", choices=["terraform", "direct"], help="bundle deploy engine")
    args = parser.parse_args()
    w = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    version = subprocess.run(["databricks", "--version"], capture_output=True, text=True)
    print(version.stdout.strip(), "| engine:", args.engine or "default")

    pipeline_id = find_pipeline_id(w)
    print(f"pipeline {pipeline_id} (read only)")
    bundle = Bundle(args.profile, args.engine, pipeline_id)
    results: dict[str, str] = {}
    deployed: list[str] = []

    try:
        # --- target dev: deploy and read back (A-25, A-26, A-30 one-way)
        for step in ("validate", "deploy"):
            res = bundle.run(step, "-t", "dev")
            print(tail(res))
            if res.returncode != 0:
                results[f"A-26 dev target {step}s"] = "FAIL"
                return report(results)
            if step == "deploy":
                deployed.append("dev")
        results["A-26 dev target validates and deploys"] = "PASS"
        ids = bundle.job_ids("dev")
        guarded = w.jobs.get(ids["spike_07_guarded"]).settings
        pipe_job = w.jobs.get(ids["spike_07_pipeline_task"]).settings
        tasks = {t.task_key: t for t in guarded.tasks}
        print("\ndeployed spike_07_guarded tasks:")
        for key, t in tasks.items():
            print(
                f"  {key:14} max_retries={t.max_retries} "
                f"disable_auto_optimization={t.disable_auto_optimization} "
                f"environment_key={t.environment_key}"
            )
        refresh = pipe_job.tasks[0]
        print(
            f"  pipeline task  max_retries={refresh.max_retries} "
            f"disable_auto_optimization={refresh.disable_auto_optimization}"
        )
        results["A-25 pipeline_task keeps disable_auto_optimization (acceptance only)"] = (
            "PASS" if refresh.disable_auto_optimization is True else "FAIL"
        )
        results["A-27 deployed fail_disabled keeps the setting"] = (
            "PASS" if tasks["fail_disabled"].disable_auto_optimization is True else "FAIL"
        )

        # --- one run of spike_07_guarded (A-26, A-27, A-29)
        run_id = w.jobs.run_now(ids["spike_07_guarded"]).run_id
        print(f"\nrun {run_id} started; waiting (failures are expected)")
        run = wait_run(w, run_id)
        by_key: dict[str, list] = {}
        for t in run.tasks or []:
            by_key.setdefault(t.task_key, []).append(t)
        for key, runs in sorted(by_key.items()):
            states = [str(r.state.result_state) for r in runs]
            attempts = [r.attempt_number or 0 for r in runs]
            print(f"  {key:14} entries={len(runs)} attempt_numbers={attempts} results={states}")
        disabled = by_key.get("fail_disabled", [])
        control = by_key.get("fail_control", [])
        results["A-27 fail_disabled has exactly 1 attempt"] = (
            "PASS"
            if len(disabled) == 1 and max(r.attempt_number or 0 for r in disabled) == 0
            else "FAIL"
        )
        results[
            f"A-27 control shows the platform retry ({len(control)} attempt(s); 1 = inconclusive)"
        ] = "PASS" if len(control) >= 2 else "INFO"

        probe_runs = by_key.get("probe", [])
        probe: dict = {}
        if probe_runs:
            out = w.jobs.get_run_output(probe_runs[-1].run_id)
            if out.error:
                probe = {"error": out.error[:800]}
            else:
                probe = json.loads(out.notebook_output.result)
        print("\nprobe:", json.dumps(probe, indent=1))
        results["A-26 probe on environment 2 runs (databricks-sdk 0.40.0)"] = (
            "PASS" if probe.get("sdk_version") == "0.40.0" else "FAIL"
        )
        results["A-29 run-as identity reads the pipeline state"] = (
            "PASS" if probe.get("pipeline_read") == "ok" else "FAIL"
        )
        results["A-30 one-way job reference resolves to a numeric id"] = (
            "PASS" if probe.get("other_job_id") == str(ids["spike_07_pipeline_task"]) else "FAIL"
        )

        # --- target cycle: two-way reference (A-30, informative)
        res = bundle.run("validate", "-t", "cycle")
        print(tail(res))
        if res.returncode != 0:
            results["A-30 two-way reference: validate fails"] = "INFO"
        else:
            res = bundle.run("deploy", "-t", "cycle")
            print(tail(res))
            deployed.append("cycle")
            if res.returncode != 0:
                results["A-30 two-way reference: validate passes, deploy fails"] = "INFO"
            else:
                cyc = bundle.job_ids("cycle")
                params = w.jobs.get(cyc["spike_07_pipeline_task"]).settings.parameters or []
                value = next((p.default for p in params if p.name == "other_job_id"), None)
                ok = value == str(cyc["spike_07_guarded"])
                results[f"A-30 two-way reference deploys (back reference resolved: {ok})"] = "INFO"
    finally:
        if not args.keep:
            for target in deployed:
                res = bundle.run("destroy", "-t", target, "--auto-approve")
                print(tail(res, 5))
    return report(results)


def report(results: dict[str, str]) -> int:
    print("\nRESULTS")
    for key, value in results.items():
        print(f"  {value:4}  {key}")
    return 0 if all(v in ("PASS", "INFO") for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
