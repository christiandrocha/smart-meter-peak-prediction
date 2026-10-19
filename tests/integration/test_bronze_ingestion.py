"""Bronze ingestion on the deployed dev environment (AC-05 to AC-08, AC-10, AC-29).

Run order (runbook): files tests after the first ``ingest_files``; Kafka tests after the first
full replay and job run and *before* the AC-09 replay, because they assert the exact seed-42
counts. The AC-10 pair needs the Aiven service powered off for the failed run.
"""

from __future__ import annotations

import os

import pytest

from smart_meter_peak_prediction.config import BRONZE_KAFKA_READINGS

pytestmark = pytest.mark.integration

STREAM_TASK = "ingest_kafka"
MAX_FAILED_TASK_SECONDS = 900  # AC-10: a broker outage fails the task within 15 minutes


def _file_counts(sql, settings) -> dict[str, int]:
    return {
        "readings": sql.scalar(f"SELECT count(*) FROM {settings.bronze_files_readings}"),
        "households": sql.scalar(f"SELECT count(*) FROM {settings.bronze_files_households}"),
    }


def _checkpoint_offsets(workspace, settings) -> list[str]:
    folder = f"{settings.checkpoint(BRONZE_KAFKA_READINGS)}/offsets"
    return sorted(entry.name for entry in workspace.files.list_directory_contents(folder))


def test_ac05_bronze_file_counts_match_manifest(sql, settings, config_manifest) -> None:
    counts = _file_counts(sql, settings)
    assert counts["readings"] == config_manifest["counts"]["historical_rows"]
    assert counts["households"] == config_manifest["households"]["selected"]
    for table in (settings.bronze_files_readings, settings.bronze_files_households):
        row = sql.one(
            f"SELECT count_if(_source_file IS NULL OR _ingested_at IS NULL) AS null_metadata, "
            f"count_if(_rescued_data IS NOT NULL) AS rescued FROM {table}"
        )
        assert row["null_metadata"] == 0, table
        assert row["rescued"] == 0, table


def test_ac06_rerun_file_ingestion_adds_no_rows(sql, settings, run_tasks) -> None:
    before = _file_counts(sql, settings)
    assert before["readings"] > 0, "nothing ingested yet: run ingest_files once first"
    run_tasks(["ingest_files"])
    assert _file_counts(sql, settings) == before


def test_ac07_kafka_bronze_count_uniqueness_and_payload_parse(
    sql, settings, config_manifest
) -> None:
    table = settings.bronze_kafka_readings
    row = sql.one(
        f"""SELECT count(*) AS n,
  count(DISTINCT _topic, _partition, _offset) AS distinct_keys,
  count_if(kafka_key IS NULL OR payload IS NULL OR _topic IS NULL OR _partition IS NULL
           OR _offset IS NULL OR _kafka_timestamp IS NULL OR _ingested_at IS NULL) AS nulls
FROM {table}"""
    )
    assert row["n"] == config_manifest["counts"]["stream_rows"]
    assert row["distinct_keys"] == row["n"]
    assert row["nulls"] == 0
    evaluated = settings.table("silver", "meter_readings_evaluated")
    unparsed = sql.scalar(
        f"SELECT count_if(NOT payload_ok) FROM {evaluated} WHERE _ingestion_path = 'kafka'"
    )
    assert unparsed == 0


def test_ac08_rerun_kafka_ingestion_adds_no_rows(sql, settings, run_tasks) -> None:
    table = settings.bronze_kafka_readings
    before = sql.scalar(f"SELECT count(*) FROM {table}")
    assert before > 0, "nothing ingested yet: produce and run ingest_kafka once first"
    run_tasks([STREAM_TASK])
    assert sql.scalar(f"SELECT count(*) FROM {table}") == before


def test_ac10_before_outage_snapshot(workspace, sql, settings, evidence) -> None:
    """Store the Bronze count and the checkpoint offsets before the broker is powered off."""
    count = sql.scalar(f"SELECT count(*) FROM {settings.bronze_kafka_readings}")
    assert count > 0, "run a successful Kafka ingestion before the outage test"
    evidence.save(
        "ac10_before_outage",
        {"kafka_rows": count, "checkpoint_offsets": _checkpoint_offsets(workspace, settings)},
    )


def test_ac10_failed_kafka_run_left_bronze_and_checkpoint_unchanged(
    workspace, sql, settings, job, evidence
) -> None:
    """After a job run with Aiven off: the task failed within 15 minutes, nothing changed."""
    before = evidence.load("ac10_before_outage", "test_ac10_before_outage_snapshot")
    failed = None
    for run in workspace.jobs.list_runs(job_id=job.job_id, expand_tasks=True, limit=25):
        if run.start_time and run.start_time < before["saved_at_ms"]:
            break
        for task in run.tasks or []:
            result = task.state.result_state.value if task.state and task.state.result_state else ""
            if task.task_key == STREAM_TASK and result == "FAILED":
                failed = task
                break
        if failed:
            break
    assert (
        failed is not None
    ), "no failed ingest_kafka run after the snapshot: run the job with Aiven off"
    seconds = (failed.end_time - failed.start_time) / 1000
    assert seconds <= MAX_FAILED_TASK_SECONDS, f"the task needed {seconds:.0f} s to fail"
    assert (
        sql.scalar(f"SELECT count(*) FROM {settings.bronze_kafka_readings}") == before["kafka_rows"]
    )
    assert _checkpoint_offsets(workspace, settings) == before["checkpoint_offsets"]


def test_ac29_failed_stream_error_does_not_leak_credentials(workspace) -> None:
    """Manual evidence (I-20): a failing stream must not print the Kafka credentials.

    Run ``ingest_kafka`` once against a scratch secret scope that holds sentinel values (runbook,
    "Stream error redaction"), then export the task run id and the sentinels::

        REDACTION_RUN_ID=<task run id> REDACTION_SENTINELS=<value1>,<value2>
    """
    run_id = os.environ.get("REDACTION_RUN_ID", "").strip()
    sentinels = [s for s in os.environ.get("REDACTION_SENTINELS", "").split(",") if s]
    if not run_id or not sentinels:
        pytest.fail("set REDACTION_RUN_ID and REDACTION_SENTINELS (see the runbook)")
    output = workspace.jobs.get_run_output(int(run_id))
    assert output.error, "the redaction run did not fail, so it proves nothing"
    text = "\n".join(
        str(part)
        for part in (output.error, output.error_trace, output.logs, output.metadata)
        if part
    )
    for sentinel in sentinels:
        assert sentinel not in text
