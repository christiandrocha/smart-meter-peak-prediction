"""AC-79: the runbook, ADR 0012 and ADR 0008 describe the pre-check, and the specs are clean."""

from __future__ import annotations

import re
from pathlib import Path

import check_specs

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/peak_model.md"
ADR_12 = ROOT / "docs/adr/0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md"
ADR_8 = ROOT / "docs/adr/0008-peak-model-jobs-and-pipeline-dependency.md"
ADR_INDEX = ROOT / "docs/adr/README.md"


def _only_lists(text: str) -> list[list[str]]:
    """Task lists after ``--only``, in code blocks (joined over ``\\`` continuations) and prose."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [found.split(",") for found in re.findall(r"--only[ =]+([A-Za-z_,]+)", joined)]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_ac79_runbook_only_commands_include_the_pre_check() -> None:
    lists = [
        tasks
        for tasks in _only_lists(RUNBOOK.read_text(encoding="utf-8"))
        if "refresh_silver_gold" in tasks
    ]
    assert lists, "the runbook has no --only list with refresh_silver_gold"
    for tasks in lists:
        assert "check_pipeline_idle" in tasks, tasks


def test_ac79_concurrency_section_and_troubleshooting_describe_the_pre_check() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    section = _section(text, "## Concurrency with the ingestion job")
    for needle in (
        "check_pipeline_idle",
        "smart_meter_ingestion",
        "run id",
        "update id",
        "rerun",
        "08:00 UTC",
    ):
        assert needle in section, needle
    troubleshooting = _section(text, "## 11. Troubleshooting")
    rows = [line for line in troubleshooting.splitlines() if line.startswith("|")]
    symptoms = [line.split("|")[1] for line in rows]
    assert any("check_pipeline_idle" in symptom for symptom in symptoms)


def test_ac79_adr_0012_accepted_records_d39_and_check_specs_is_clean() -> None:
    adr = ADR_12.read_text(encoding="utf-8")
    status = re.search(r"\*\*Status\*\*\s*\|\s*([^|]+?)\s*\|", adr)
    assert status is not None
    assert status.group(1) == "Accepted"
    assert "D-39" in adr
    assert ADR_12.name in ADR_INDEX.read_text(encoding="utf-8")
    note = ADR_8.read_text(encoding="utf-8")
    assert "PEAK_MODEL_CONCURRENCY" in note
    assert "0012-read-only-pipeline-pre-check-in-the-daily-peak-job.md" in note
    assert check_specs.run(ROOT).errors == []
