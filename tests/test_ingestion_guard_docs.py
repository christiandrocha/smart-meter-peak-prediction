"""AC-99: the runbooks and ADRs describe the reverse check, and the specs are clean."""

from __future__ import annotations

import re
from pathlib import Path

import check_specs

ROOT = Path(__file__).resolve().parents[1]
INGESTION_RUNBOOK = ROOT / "docs/runbooks/meter_ingestion.md"
PEAK_RUNBOOK = ROOT / "docs/runbooks/peak_model.md"
ADR_13_NAME = "0013-pipeline-only-pre-check-in-the-ingestion-job.md"
ADR_13 = ROOT / "docs/adr" / ADR_13_NAME
ADR_12 = ROOT / "docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md"
ADR_8 = ROOT / "docs/adr/0008-peak-model-jobs-and-pipeline-dependency.md"
ADR_INDEX = ROOT / "docs/adr/README.md"
NOTE = "Note (2026-10-23, INGESTION_GUARD)"


def _only_lists(text: str) -> list[list[str]]:
    """Task lists after ``--only``, in code blocks (joined over ``\\`` continuations) and prose."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [found.split(",") for found in re.findall(r"--only[ =]+([A-Za-z_,]+)", joined)]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_ac99_runbook_only_commands_include_the_check() -> None:
    lists = [
        tasks
        for tasks in _only_lists(INGESTION_RUNBOOK.read_text(encoding="utf-8"))
        if "refresh_silver_gold" in tasks
    ]
    assert lists, "the ingestion runbook has no --only list with refresh_silver_gold"
    for tasks in lists:
        assert "check_silver_gold_idle" in tasks, tasks


def test_ac99_runbooks_describe_the_check() -> None:
    section = _section(
        INGESTION_RUNBOOK.read_text(encoding="utf-8"), "## Concurrency with the peak job"
    )
    for needle in (
        "check_silver_gold_idle",
        "smart_meter_silver_gold",
        "update id",
        "fails closed",
        "rerun `smart_meter_ingestion`",
        "Bronze",
        "08:00 UTC",
    ):
        assert needle in section, needle
    peak = _section(
        PEAK_RUNBOOK.read_text(encoding="utf-8"), "## Concurrency with the ingestion job"
    )
    assert "check_silver_gold_idle" in peak


def test_ac99_adrs_record_the_reverse_check_and_specs_are_clean() -> None:
    adr = ADR_13.read_text(encoding="utf-8")
    status = re.search(r"\*\*Status\*\*\s*\|\s*([^|]+?)\s*\|", adr)
    assert status is not None
    assert status.group(1) == "Accepted"
    for needle in ("D-48", "D-50", "D-51", "D-55", "Error: Cycle"):
        assert needle in adr, needle
    assert ADR_13_NAME in ADR_INDEX.read_text(encoding="utf-8")
    for path in (ADR_12, ADR_8):
        text = path.read_text(encoding="utf-8")
        assert NOTE in text, path.name
        assert ADR_13_NAME in text, path.name
    assert check_specs.run(ROOT).errors == []


def test_ac99_no_test_asserts_the_v010_four_task_graph() -> None:
    old_sequence = re.compile(r'"ingest_kafka",\s*"refresh_silver_gold"')
    offenders = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if old_sequence.search(text) or "len(tasks()) == 4" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
