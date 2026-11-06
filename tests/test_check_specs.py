import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import check_specs
import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / ".claude" / "sdd" / "templates"


def write(root: Path, folder: str, name: str, text: str) -> None:
    path = root / ".claude" / "sdd" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def define_doc(status: str = "Ready for Design", total: int = 13) -> str:
    return f"""# DEFINE: X
## Metadata
| **Status** | {status} |
## Problem Statement
Readers need numbers.
## Scope
All of it.
## Functional Requirements
| FR-01 | The system shall load data | Must |
## Acceptance Criteria
| AC-01 | data | load | rows match |
| AC-02 | rerun | load | no new rows |
## Clarity Score
| **Total** | **{total}/15** | gate |
## Self-Review
- Weak points: none known yet.
"""


def design_doc(acs: list[str], status: str = "Ready for Build") -> str:
    rows = "\n".join(f"| {ac} | Unit | tests/test_x.py | proves it |" for ac in acs)
    return f"""# DESIGN: X
## Metadata
| **Status** | {status} |
## Architecture
Simple.
## Components
| loader | loads | python | FR-01 |
## File Manifest
| 1 | src/x.py | Create | load | builder | - |
## Test Strategy
{rows}
## Self-Review
- Weak points: single process.
"""


def test_empty_repository_passes(tmp_path):
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert report.checked == 0


def test_unfilled_template_in_draft_is_allowed(tmp_path):
    text = (TEMPLATES / "DEFINE_TEMPLATE.md").read_text()
    write(tmp_path, "features", "DEFINE_X.md", text)
    report = check_specs.run(tmp_path)
    assert report.errors == []


def test_template_marked_ready_fails_on_placeholders(tmp_path):
    text = (
        (TEMPLATES / "DEFINE_TEMPLATE.md")
        .read_text()
        .replace("| **Status** | Draft |", "| **Status** | Ready for Design |")
    )
    write(tmp_path, "features", "DEFINE_X.md", text)
    errors = " ".join(check_specs.run(tmp_path).errors)
    assert "unfilled placeholders" in errors


def test_all_templates_have_required_sections(tmp_path):
    """AC-117, AC-128: all six templates pass their own section rule, SHIPPED included."""
    names = {
        "BRAINSTORM": "BRAINSTORM_TEMPLATE.md",
        "DEFINE": "DEFINE_TEMPLATE.md",
        "DESIGN": "DESIGN_TEMPLATE.md",
        "BUILD_REPORT": "BUILD_REPORT_TEMPLATE.md",
        "CHANGE": "CHANGE_TEMPLATE.md",
    }
    for phase, file in names.items():
        folder = "reports" if phase == "BUILD_REPORT" else "features"
        write(tmp_path, folder, f"{phase}_X.md", (TEMPLATES / file).read_text())
    shipped = (TEMPLATES / "SHIPPED_TEMPLATE.md").read_text()
    write(tmp_path, "archive/X", "SHIPPED_2026-11-05.md", shipped)  # on the cut-off date
    errors = [e for e in check_specs.run(tmp_path).errors if "missing section" in e]
    assert errors == []


def test_invalid_status(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc(status="Done"))
    assert any("not one of" in e for e in check_specs.run(tmp_path).errors)


def test_low_clarity_score_blocks_gate(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc(total=10))
    assert any("clarity score 10/15" in e for e in check_specs.run(tmp_path).errors)


def test_design_missing_ac_test_fails(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc())
    write(tmp_path, "features", "DESIGN_X.md", design_doc(["AC-01"]))
    errors = " ".join(check_specs.run(tmp_path).errors)
    assert "without a test: AC-02" in errors


def test_design_full_traceability_passes(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc())
    write(tmp_path, "features", "DESIGN_X.md", design_doc(["AC-01", "AC-02"]))
    assert check_specs.run(tmp_path).errors == []


def test_design_draft_missing_ac_only_warns(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc())
    write(tmp_path, "features", "DESIGN_X.md", design_doc(["AC-01"], status="Draft"))
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert any("AC-02" in w for w in report.warnings)


def test_complete_build_with_failing_ac(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc())
    write(tmp_path, "features", "DESIGN_X.md", design_doc(["AC-01", "AC-02"]))
    build = """# BUILD REPORT: X
## Metadata
| **Status** | Complete |
## Files Changed
| 1 | src/x.py | Created | pytest |
## Acceptance Criteria Evidence
| AC-01 | Pass | 1 passed |
| AC-02 | Fail | 3 new rows |
## Self-Review
- Weak points: rerun bug.
"""
    write(tmp_path, "reports", "BUILD_REPORT_X.md", build)
    errors = " ".join(check_specs.run(tmp_path).errors)
    assert "failing criteria: AC-02" in errors


def test_complete_build_ignores_fail_in_test_names_and_prose(tmp_path):
    write(tmp_path, "features", "DEFINE_X.md", define_doc())
    write(tmp_path, "features", "DESIGN_X.md", design_doc(["AC-01", "AC-02"]))
    build = """# BUILD REPORT: X
## Metadata
| **Status** | Complete |
## Files Changed
| 1 | src/x.py | Created | pytest |
## Acceptance Criteria Evidence
| AC-01 | Pass (wired fail rule) | Pass | `test_ac01_failed_run_left_table_unchanged` |
| AC-02 | Pass | Failed live | `test_ac02_rerun` |
## Self-Review
- Weak points: rerun bug.
"""
    write(tmp_path, "reports", "BUILD_REPORT_X.md", build)
    errors = " ".join(check_specs.run(tmp_path).errors)
    assert "failing criteria: AC-02" in errors
    assert "AC-01" not in errors


def test_code_blocks_are_not_placeholders(tmp_path):
    text = define_doc() + '\n```json\n{"entity_id": "x"}\n```\n'
    write(tmp_path, "features", "DEFINE_X.md", text)
    assert check_specs.run(tmp_path).errors == []


# --------------------------------------------------------------------------- ADRs

ROOT = Path(__file__).resolve().parent.parent


def write_adr(root: Path, name: str, status: str = "Proposed", body: str | None = None) -> None:
    folder = root / "docs" / "adr"
    folder.mkdir(parents=True, exist_ok=True)
    text = (
        body
        or f"""# {name}
| **Status** | {status} |
## Context
Facts.
## Options considered
| A | good | bad |
## Decision
We will use A.
## Consequences
- Positive: simple.
"""
    )
    (folder / name).write_text(text, encoding="utf-8")
    index = folder / "README.md"
    previous = index.read_text() if index.exists() else ""
    index.write_text(previous + f"| [{name}]({name}) |\n")


def test_valid_adr_passes(tmp_path):
    write_adr(tmp_path, "0001-use-delta.md", status="Accepted")
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert report.checked == 1


def test_adr_template_copied_and_accepted_fails_on_placeholders(tmp_path):
    text = (ROOT / "docs" / "adr" / "0000-template.md").read_text()
    write_adr(tmp_path, "0001-x.md", body=text.replace("| Proposed |", "| Accepted |"))
    assert any("unfilled placeholders" in e for e in check_specs.run(tmp_path).errors)


def test_adr_bad_name_status_and_duplicate_number(tmp_path):
    write_adr(tmp_path, "0001-a.md")
    write_adr(tmp_path, "0001-b.md", status="Done")
    write_adr(tmp_path, "Decision_two.md")
    errors = " ".join(check_specs.run(tmp_path).errors)
    assert "already used" in errors
    assert "status 'Done'" in errors
    assert "NNNN-kebab-case-title" in errors


def test_adr_superseded_by_missing_record(tmp_path):
    write_adr(tmp_path, "0001-a.md", status="Superseded by 0007")
    assert any("0007, which does not exist" in e for e in check_specs.run(tmp_path).errors)


def test_adr_missing_from_index_warns(tmp_path):
    write_adr(tmp_path, "0001-a.md")
    (tmp_path / "docs" / "adr" / "README.md").write_text("empty index")
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert any("not listed" in w for w in report.warnings)


# ----------------------------------------------------------------------- contracts


def write_contract(root: Path, name: str, text: str) -> None:
    folder = root / "docs" / "contracts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_shipped_contract_templates_are_valid(tmp_path):
    templates = [ROOT / "docs/contracts/_template.yaml"]
    # The topic template lives in the kafka module in the template repository, and in
    # docs/contracts/ in a project initialized with that module.
    for candidate in (
        ROOT / "modules/kafka/files/docs/contracts/_topic_template.yaml",
        ROOT / "docs/contracts/_topic_template.yaml",
    ):
        if candidate.exists():
            templates.append(candidate)
            break
    for i, path in enumerate(templates):
        write_contract(tmp_path, f"contract_{i}.yaml", path.read_text())
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert report.checked == len(templates)


def test_contract_errors(tmp_path):
    write_contract(
        tmp_path,
        "bad.yaml",
        """dataset: cat.silver.readings
kind: table
owner: X
description: readings
grain: one row per reading
primary_key: [household_id, missing_col]
schema:
  - {name: household_id, type: string}
  - {name: energy_kwh}
quality:
  - {rule: energy_kwh >= 0, action: ignore}
""",
    )
    errors = " ".join(check_specs.run(tmp_path).errors)
    assert "primary_key columns not in schema: missing_col" in errors
    assert "schema entry 2 needs 'name' and 'type'" in errors
    assert "quality action 'ignore'" in errors


def test_topic_contract_key_must_exist(tmp_path):
    write_contract(
        tmp_path,
        "t.yaml",
        """dataset: readings
kind: topic
owner: X
description: one message per reading
key: {field: meter}
value:
  schema:
    - {name: household_id, type: string}
""",
    )
    assert any("key field 'meter'" in e for e in check_specs.run(tmp_path).errors)


def test_invalid_yaml(tmp_path):
    write_contract(tmp_path, "broken.yaml", "dataset: [unclosed\n")
    assert any("invalid YAML" in e for e in check_specs.run(tmp_path).errors)


# --------------------------------------------------------------- archive (SPEC_ARCHIVE_GATES)
# AC-107 to AC-119. Fixtures live under tmp_path/.claude/sdd/archive/<FOLDER>/; dates come from
# file names only (NFR-35).


ALLOWLIST = ".claude/sdd/citation_allowlist.json"


def build_doc(issue_rows: str = "| I-01 | a | Low | Fixed |") -> str:
    return f"""# BUILD REPORT: X
## Metadata
| **Status** | Complete |
## Files Changed
| 1 | src/x.py | Created | pytest |
## Acceptance Criteria Evidence
| AC-01 | Pass | 1 passed |
| AC-02 | Pass | 1 passed |
## Issues & Follow-ups
| ID | Issue | Severity | Follow-up |
|---|---|---|---|
{issue_rows}
## Self-Review
- Weak points: none known.
"""


def shipped_doc(
    day: str = "2026-11-04",
    sections: list[str] | None = None,
    shipped_on: str | None = None,
    status: str = "Shipped",
    self_review: str = "- Weak points: none known.",
    extra: str = "",
) -> str:
    parts = ["# SHIPPED: X"]
    for section in check_specs.SHIPPED_SECTIONS if sections is None else sections:
        if section == "Metadata":
            body = f"| **Shipped on** | {shipped_on or day} |\n| **Status** | {status} |"
        elif section == "Self-Review":
            body = self_review
        else:
            body = f"Text of {section}."
        parts.append(f"## {section}\n{body}")
    return "\n".join(parts) + "\n" + extra


def write_archive(root: Path, folder: str, name: str, text: str) -> None:
    write(root, f"archive/{folder}", name, text)


def valid_folder(root: Path, folder: str = "FEAT", define_extra: str = "") -> None:
    write_archive(root, folder, f"DEFINE_{folder}.md", define_doc() + define_extra)
    write_archive(root, folder, f"DESIGN_{folder}.md", design_doc(["AC-01", "AC-02"]))
    write_archive(root, folder, f"BUILD_REPORT_{folder}.md", build_doc())
    write_archive(root, folder, "SHIPPED_2026-11-04.md", shipped_doc())


def write_allowlist(root: Path, entries: list[dict] | None = None, raw: str | None = None) -> None:
    path = root / ALLOWLIST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        raw if raw is not None else json.dumps({"version": 1, "entries": entries or []})
    )


def test_ac107_repository_has_no_errors():
    report = check_specs.run(ROOT)
    assert report.errors == []


def test_ac108_archived_phase_doc_rules(tmp_path):
    valid_folder(tmp_path)
    assert check_specs.run(tmp_path).errors == []

    no_scope = define_doc().replace("## Scope\nAll of it.\n", "")
    write_archive(tmp_path, "FEAT", "DEFINE_FEAT.md", no_scope)
    assert check_specs.run(tmp_path).errors == ["FEAT/DEFINE_FEAT.md: missing section '## Scope'"]

    write_archive(tmp_path, "FEAT", "DEFINE_FEAT.md", define_doc() + "Fill {Owner name} in.\n")
    errors = check_specs.run(tmp_path).errors
    assert len(errors) == 1
    assert errors[0].startswith("FEAT/DEFINE_FEAT.md: status 'Ready for Design' but unfilled")


def test_ac109_traceability_per_archive_folder(tmp_path):
    active = define_doc().replace("| AC-02 |", "| AC-03 | x | y | z |\n| AC-02 |")
    write(tmp_path, "features", "DEFINE_FEAT.md", active)
    write(tmp_path, "features", "DESIGN_FEAT.md", design_doc(["AC-01", "AC-02", "AC-03"]))
    valid_folder(tmp_path)
    write_archive(tmp_path, "FEAT", "DESIGN_FEAT.md", design_doc(["AC-01"]))
    errors = check_specs.run(tmp_path).errors
    assert errors == ["FEAT/DESIGN_FEAT.md: acceptance criteria without a test: AC-02"]


@pytest.mark.parametrize(
    "change",
    ["none", "design-draft", "no-shipped", "two-shipped", "shipped-draft", "unknown-name"],
)
def test_ac110_final_status_and_one_shipped_per_folder(tmp_path, change):
    valid_folder(tmp_path)
    folder = tmp_path / ".claude" / "sdd" / "archive" / "FEAT"
    if change == "design-draft":
        write_archive(tmp_path, "FEAT", "DESIGN_FEAT.md", design_doc(["AC-01", "AC-02"], "Draft"))
    elif change == "no-shipped":
        (folder / "SHIPPED_2026-11-04.md").unlink()
    elif change == "two-shipped":
        write_archive(tmp_path, "FEAT", "SHIPPED_2026-11-03.md", shipped_doc("2026-11-03"))
    elif change == "shipped-draft":
        write_archive(tmp_path, "FEAT", "SHIPPED_2026-11-04.md", shipped_doc(status="Draft"))
    elif change == "unknown-name":
        write_archive(tmp_path, "FEAT", "NOTES.md", "# notes\n")
    errors = check_specs.run(tmp_path).errors
    if change == "none":
        assert errors == []
    else:
        assert len(errors) == 1, errors
        assert "(rule a)" in errors[0]


def cutoff_fixtures(root: Path) -> None:
    without = [s for s in check_specs.SHIPPED_SECTIONS if s != "Pull Requests and Branches"]
    write_archive(root, "BEFORE", "SHIPPED_2026-11-04.md", shipped_doc("2026-11-04", without))
    write_archive(root, "ONCUT", "SHIPPED_2026-11-05.md", shipped_doc("2026-11-05", without))
    write_archive(root, "WITH", "SHIPPED_2026-11-05.md", shipped_doc("2026-11-05"))


CUTOFF_ERRORS = ["ONCUT/SHIPPED_2026-11-05.md: missing section '## Pull Requests and Branches'"]


@pytest.mark.parametrize(
    ("folder", "day", "with_section", "expected"),
    [
        ("BEFORE", "2026-11-04", False, []),
        ("ONCUT", "2026-11-05", False, CUTOFF_ERRORS),
        ("WITH", "2026-11-05", True, []),
    ],
)
def test_ac111_shipped_cutoff_by_file_name_date(tmp_path, folder, day, with_section, expected):
    sections = [
        s for s in check_specs.SHIPPED_SECTIONS if with_section or s != "Pull Requests and Branches"
    ]
    write_archive(tmp_path, folder, f"SHIPPED_{day}.md", shipped_doc(day, sections))
    assert check_specs.run(tmp_path).errors == expected


def test_ac112_result_does_not_depend_on_mtime(tmp_path):
    cutoff_fixtures(tmp_path)
    baseline = check_specs.run(tmp_path)
    assert baseline.errors == CUTOFF_ERRORS
    files = list((tmp_path / ".claude").rglob("*.md"))
    for moment in (datetime(2026, 1, 1), datetime(2030, 1, 1)):
        stamp = moment.timestamp()
        for path in files:
            os.utime(path, (stamp, stamp))
        again = check_specs.run(tmp_path)
        assert (again.errors, again.warnings) == (baseline.errors, baseline.warnings)


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        ("SHIPPED_2026-13-40.md", shipped_doc("2026-13-40"), "invalid date '2026-13-40'"),
        ("SHIPPED_final.md", shipped_doc(), "must be SHIPPED_YYYY-MM-DD.md"),
        ("SHIPPED_2026-11-04.md", shipped_doc(shipped_on="2026-11-03"), "'Shipped on' is"),
        (
            "SHIPPED_2026-11-05.md",
            shipped_doc("2026-11-05", extra="Owner: {Owner name}\n"),
            "unfilled placeholders",
        ),
        (
            "SHIPPED_2026-11-04.md",
            shipped_doc(sections=check_specs.SHIPPED_SECTIONS[:-1]),
            "missing section '## Self-Review'",
        ),
        ("SHIPPED_2026-11-04.md", shipped_doc(self_review=""), "Self-Review is empty"),
        ("SHIPPED_2026-11-04.md", shipped_doc(extra="Owner: {Owner name}\n"), None),
    ],
    ids=[
        "bad-date",
        "bad-name",
        "shipped-on-mismatch",
        "placeholder-after-cutoff",
        "no-self-review",
        "empty-self-review",
        "placeholder-before-cutoff-passes",
    ],
)
def test_ac113_shipped_name_date_placeholders_and_self_review(tmp_path, name, text, expected):
    write_archive(tmp_path, "FEAT", name, text)
    errors = check_specs.run(tmp_path).errors
    if expected is None:
        assert errors == []
    else:
        assert len(errors) == 1, errors
        assert expected in errors[0]
        assert errors[0].startswith(f"FEAT/{name}: ")


def test_ac114_open_findings_warn_only(tmp_path, monkeypatch):
    rows = "\n".join(
        [
            "| I-01 | a | Low | Open: follow up later |",
            "| I-02 | b | Medium | **Open**, tracked |",
            "| I-03 | c | High | **Closed 2026-11-05**: done |",
            "| I-04 | d | Medium | Watch the margin in later runs |",
        ]
    )
    valid_folder(tmp_path)
    write_archive(tmp_path, "FEAT", "BUILD_REPORT_FEAT.md", build_doc(rows))
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert report.warnings == [
        "FEAT/BUILD_REPORT_FEAT.md: open finding FEAT I-01 (Low) (rule b)",
        "FEAT/BUILD_REPORT_FEAT.md: open finding FEAT I-02 (Medium) (rule b)",
    ]
    monkeypatch.setattr(sys, "argv", ["check_specs.py", "--root", str(tmp_path)])
    assert check_specs.main() == 0


CITATION_CASES = {
    "unprefixed-foreign": ("see I-07 here", True),
    "prefixed": ("see OTHER I-07 here", False),
    "own-id": ("see I-01 here", False),
    "fenced": "```text\nI-07\n```",
    "unknown-word": ("see BOGUS I-07 here", True),
    "soft-wrap": ("see OTHER\n  I-07 here", False),
    "tab": ("see OTHER\tI-07 here", False),
    "blank-line": ("see OTHER\n\nI-07 here", True),
    "crlf-soft-wrap": ("see OTHER\r\n  I-07 here", False),
    "crlf-blank-line": ("see OTHER\r\n\r\nI-07 here", True),
}


@pytest.mark.parametrize("case", sorted(CITATION_CASES))
def test_ac115_unprefixed_foreign_citations(tmp_path, case):
    value = CITATION_CASES[case]
    snippet, fails = (value, False) if isinstance(value, str) else value
    valid_folder(tmp_path)
    valid_folder(tmp_path, "OTHER")
    write_allowlist(tmp_path)
    text = define_doc() + "\n" + snippet + "\n"
    path = tmp_path / ".claude" / "sdd" / "archive" / "FEAT" / "DEFINE_FEAT.md"
    if case.startswith("crlf"):
        # Written as bytes with CRLF line ends; check_specs reads with universal newlines.
        path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    else:
        path.write_text(text, encoding="utf-8")
    errors = check_specs.run(tmp_path).errors
    if fails:
        assert errors == [
            ".claude/sdd/archive/FEAT/DEFINE_FEAT.md: I-07 cited 1x without its spec prefix "
            f"and not in {ALLOWLIST} (rule c)"
        ]
    else:
        assert errors == []


THREE = "First I-07, then I-07, and again I-07.\n"
ENTRY = {"file": ".claude/sdd/archive/FEAT/DEFINE_FEAT.md", "id": "I-07"}


@pytest.mark.parametrize(
    ("allowlist", "cite", "expected"),
    [
        ([{**ENTRY, "count": 3}], True, None),
        ([{**ENTRY, "count": 4}], True, "has count 4, found 3 (rule c)"),
        ([{**ENTRY, "count": 2}], True, "has count 2, found 3 (rule c)"),
        ([{**ENTRY, "count": 3}], False, "stale entry .claude/sdd/archive/FEAT/DEFINE_FEAT.md"),
        ([], True, "I-07 cited 3x without its spec prefix"),
        ("missing", True, "missing, but rule (c) found 3 citation(s)"),
        ("{not json", True, "malformed allowlist"),
    ],
    ids=["exact", "count-high", "count-low", "stale", "no-entry", "no-file", "malformed"],
)
def test_ac116_allowlist_exact_counts(tmp_path, allowlist, cite, expected):
    valid_folder(tmp_path, define_extra=THREE if cite else "")
    if isinstance(allowlist, list):
        write_allowlist(tmp_path, allowlist)
    elif allowlist != "missing":
        write_allowlist(tmp_path, raw=allowlist)
    errors = check_specs.run(tmp_path).errors
    if expected is None:
        assert errors == []
    else:
        assert any(expected in e for e in errors), errors


def test_ac117_shipped_template_sections_equal_the_rule():
    text = (TEMPLATES / "SHIPPED_TEMPLATE.md").read_text(encoding="utf-8")
    headings = [h.strip() for h in check_specs.HEADING.findall(text)]
    assert headings == check_specs.SHIPPED_SECTIONS
    assert headings[-1] == "Self-Review"


def test_ac118_docs_describe_the_archive_rules():
    readme = (ROOT / ".claude" / "sdd" / "README.md").read_text(encoding="utf-8")
    for text in (check_specs.__doc__, readme):
        for needle in ("archive/", "citation_allowlist.json", "2026-11-05"):
            assert needle in text, needle


def generated_shipped(day: str = "2026-11-06") -> str:
    """OD-35: a valid SHIPPED document with every section, fixed date after the cut-off."""
    return shipped_doc(day, self_review="- Weak points: generated for the AC-119 self-test.")


def simulate_archive(tmp_path: Path, docs: list) -> list[str]:
    """AC-119 (OD-35): real archive and allowlist, plus each feature as a new folder."""
    sdd = ROOT / ".claude" / "sdd"
    target_sdd = tmp_path / ".claude" / "sdd"
    shutil.copytree(sdd / "archive", target_sdd / "archive")
    shutil.copy(sdd / "citation_allowlist.json", target_sdd / "citation_allowlist.json")
    added = []
    for feature in sorted({d.feature for d in docs}):
        folder = target_sdd / "archive" / feature
        assert not folder.exists(), f"AC-119: archive/{feature} already exists; not merging"
        folder.mkdir()
        for doc in (d for d in docs if d.feature == feature):
            (folder / doc.path.name).write_text(doc.text, encoding="utf-8")
            added.append(f"{feature}/{doc.path.name}")
        if any(d.phase == "CHANGE" for d in docs if d.feature == feature):
            continue  # AC-129: a change folder holds the CHANGE document alone
        (folder / "SHIPPED_2026-11-06.md").write_text(generated_shipped(), encoding="utf-8")
    return added


def final_status_docs(root: Path = ROOT) -> list:
    docs = check_specs.load_docs(root)
    return [d for d in docs if d.status == check_specs.FINAL_STATUS[d.phase]]


def test_ac119_final_status_feature_docs_pass_the_archive_rules(tmp_path):
    final = final_status_docs()
    if not final:
        pytest.skip("no document of features/ or reports/ is in its phase's final status")
    added = simulate_archive(tmp_path, final)
    print(f"AC-119: added {len(added)} document(s) to the temporary archive: {', '.join(added)}")
    errors = check_specs.run(tmp_path).errors
    assert errors == [], errors


def test_ac119_folder_name_collision_fails_without_merging(tmp_path):
    """AC-119 safeguard: a feature named like an existing archive folder is refused, not merged."""
    existing = sorted(p.name for p in (ROOT / ".claude/sdd/archive").iterdir() if p.is_dir())[0]
    clash = check_specs.Doc(Path(f"DEFINE_{existing}.md"), "DEFINE", existing, define_doc())
    with pytest.raises(AssertionError, match=re.escape(f"archive/{existing} already exists")):
        simulate_archive(tmp_path, [clash])
    copied = tmp_path / ".claude/sdd/archive" / existing / f"DEFINE_{existing}.md"
    assert copied.read_text(encoding="utf-8") == (
        ROOT / ".claude/sdd/archive" / existing / f"DEFINE_{existing}.md"
    ).read_text(encoding="utf-8")  # the archived document was not overwritten


# ----------------------------------------------------------------- SMALL_CHANGE_TRACK
CHANGE_SECTIONS = [
    "Metadata",
    "Problem Statement",
    "Eligibility",
    "Scope",
    "Acceptance Criteria",
    "Test Strategy",
    "File Manifest",
    "Evidence",
    "Issues & Follow-ups",
    "Self-Review",
]
SHA = "0a1b2c3d4e5f"
RULE_CHANGES = """## Rule Changes
Before (docs/conventions/git.md:20): "old text"
After (docs/conventions/git.md:20): "new text"
```text
$ gh api repos/o/r/rulesets
{"enforcement": "active"}
```
User OK: 2026-11-05
"""


def change_doc(
    status: str = "Complete",
    drop: tuple[str, ...] = (),
    eligibility: dict[str, tuple[str, str]] | None = None,
    extra_rows: str = "",
    test_acs: tuple[str, ...] = ("AC-01", "AC-02"),
    evidence_acs: tuple[str, ...] = ("AC-01", "AC-02"),
    evidence_result: str = "Pass",
    evidence_line: str | None = None,
    issues: str = "| F-01 | later | Low | Closed |",
    self_review: str = "- Weak points: none known.",
    tail: str = "",
    placeholder: str = "",
) -> str:
    results = {f"E{n}": ("Yes", f"`git diff` shows E{n} untouched") for n in range(1, 9)}
    results.update(eligibility or {})
    rows = "\n".join(
        f"| {crit} | criterion {crit} | {res} | {ev} |" for crit, (res, ev) in results.items()
    )
    sections = {
        "Metadata": f"| **Status** | {status} |",
        "Problem Statement": "Small problem." + placeholder,
        "Eligibility": "| ID | Criterion | Result | Evidence |\n|---|---|---|---|\n"
        + rows
        + extra_rows,
        "Scope": "All of it.",
        "Acceptance Criteria": "\n".join(
            f"| {ac} | given | when | then |" for ac in ("AC-01", "AC-02")
        ),
        "Test Strategy": "\n".join(f"| {ac} | Unit | tests/t.py | proves |" for ac in test_acs),
        "File Manifest": "| 1 | docs/x.md | Modify | text |",
        "Evidence": (evidence_line if evidence_line is not None else f"Evidence commit: {SHA}")
        + "\n"
        + "\n".join(f"| {ac} | {evidence_result} | output |" for ac in evidence_acs),
        "Issues & Follow-ups": "| ID | Issue | Severity | Follow-up |\n|---|---|---|---|\n"
        + issues,
        "Self-Review": self_review,
    }
    parts = ["# CHANGE: X"]
    parts += [f"## {name}\n{body}" for name, body in sections.items() if name not in drop]
    return "\n".join(parts) + "\n" + tail


def run_change(tmp_path: Path, text: str, name: str = "CHANGE_X.md") -> list[str]:
    write(tmp_path, "features", name, text)
    return check_specs.run(tmp_path).errors


def test_ac120_repository_has_no_errors():
    report = check_specs.run(ROOT)
    assert report.errors == []


@pytest.mark.parametrize(
    ("folder", "name", "errors"),
    [
        ("features", "NOTES.md", 1),
        ("reports", "draft.md", 1),
        ("features", ".gitkeep", 0),
        ("reports", ".gitkeep", 0),
        ("features", "DEFINE_X.md", 0),
        ("reports", "BUILD_REPORT_X.md", 0),
    ],
)
def test_ac121_unrecognized_names_fail(tmp_path, folder, name, errors):
    write(tmp_path, folder, name, define_doc() if name.startswith("DEFINE") else build_doc())
    report = check_specs.run(tmp_path)
    assert len(report.errors) == errors, report.errors
    assert report.warnings == []
    if errors:
        assert report.errors[0].startswith(f"{name}: unrecognized document name")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"status": "Draft"}, None),
        ({"status": "Ready for Build"}, None),
        ({"status": "Complete"}, None),
        ({"drop": ("Scope",)}, "missing section '## Scope'"),
        ({"placeholder": " {todo}"}, "unfilled placeholders remain: {todo}"),
        ({"self_review": ""}, "Self-Review is empty"),
    ],
)
def test_ac122_change_document_rules(tmp_path, kwargs, expected):
    errors = run_change(tmp_path, change_doc(**kwargs))
    if expected is None:
        assert errors == []
    else:
        assert len(errors) == 1, errors
        assert errors[0].startswith("CHANGE_X.md: ")
        assert expected in errors[0]


def test_ac123_final_status_is_explicit():
    assert check_specs.FINAL_STATUS == {
        "BRAINSTORM": "Ready for Define",
        "DEFINE": "Ready for Design",
        "DESIGN": "Ready for Build",
        "BUILD_REPORT": "Complete",
        "CHANGE": "Complete",
    }
    assert check_specs.FINAL_STATUS["CHANGE"] != "Ready for Build"
    assert set(check_specs.FINAL_STATUS) == set(check_specs.PHASES)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, None),
        ({"eligibility": {"E8": ("Yes", "")}}, "E8 has an empty evidence cell"),
        ({"eligibility": {"E5": ("No", "changed the script")}}, "E5 result 'No'"),
        ({"extra_rows": "\n| E3 | again | Yes | dup |"}, "E3 appears 2 times"),
        ({"eligibility": {"E8": ("Relaxing", "see below")}}, "'## Rule Changes' is missing"),
    ],
)
def test_ac124_eligibility_rows(tmp_path, kwargs, expected):
    errors = run_change(tmp_path, change_doc(**kwargs))
    if expected is None:
        assert errors == []
        return
    assert len(errors) == 1, errors
    assert expected in errors[0]


def test_ac124_missing_row_names_the_criterion(tmp_path):
    text = change_doc().replace("| E8 | criterion E8 | Yes | `git diff` shows E8 untouched |\n", "")
    errors = run_change(tmp_path, text)
    assert len(errors) == 1, errors
    assert "E8 is missing" in errors[0]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, None),
        ({"status": "Ready for Build", "test_acs": ("AC-01",)}, "not in Test Strategy: AC-02"),
        ({"evidence_acs": ("AC-01",)}, "not in Evidence: AC-02"),
        ({"evidence_result": "Fail"}, "failing criteria: AC-01, AC-02"),
        ({"evidence_line": "No commit named."}, "no 'Evidence commit <SHA>' line"),
        ({"evidence_line": "Evidence commit: abc12"}, "no 'Evidence commit <SHA>' line"),
        ({"evidence_line": "Evidence commit: defaced"}, "no 'Evidence commit <SHA>' line"),
    ],
)
def test_ac125_change_traceability_and_evidence_commit(tmp_path, kwargs, expected):
    errors = run_change(tmp_path, change_doc(**kwargs))
    if expected is None:
        assert errors == []
        return
    assert len(errors) == 1, errors
    assert expected in errors[0]
    assert errors[0].startswith("CHANGE_X.md: ")


def archived_change(root: Path, folder: str = "FEAT", **kwargs) -> None:
    write_archive(root, folder, f"CHANGE_{folder}.md", change_doc(**kwargs))


def test_ac126_archived_change_folders(tmp_path):
    write_allowlist(tmp_path)
    archived_change(tmp_path, "OK")
    archived_change(tmp_path, "DRAFTED", status="Ready for Build")
    archived_change(tmp_path, "SHIP")
    write_archive(tmp_path, "SHIP", "SHIPPED_2026-11-05.md", shipped_doc("2026-11-05"))
    archived_change(tmp_path, "DEF")
    write_archive(tmp_path, "DEF", "DEFINE_DEF.md", define_doc())
    errors = check_specs.run(tmp_path).errors
    assert not [e for e in errors if "OK" in e.split(":")[0]], errors
    by_folder = {f: [e for e in errors if f in e.split(":")[0]] for f in ("DRAFTED", "SHIP", "DEF")}
    assert len(by_folder["DRAFTED"]) == 1
    assert "not 'Complete' (rule a)" in by_folder["DRAFTED"][0]
    assert len(by_folder["SHIP"]) == 1, by_folder["SHIP"]
    assert "archive/SHIP" in by_folder["SHIP"][0]
    assert "SHIPPED_2026-11-05.md" in by_folder["SHIP"][0]
    assert len(by_folder["DEF"]) == 1, by_folder["DEF"]
    assert "archive/DEF" in by_folder["DEF"][0]
    assert "DEFINE_DEF.md" in by_folder["DEF"][0]
    assert len(errors) == 3, errors


def test_ac127_rules_b_and_c_read_change_documents(tmp_path):
    write_allowlist(tmp_path)
    valid_folder(tmp_path, "OTHER")
    issues = "| F-01 | a | Low | Open: later |\n| F-02 | b | Low | Closed |"
    archived_change(
        tmp_path, issues=issues, tail="Own F-01 and F-02 are fine. Foreign I-07 here.\n"
    )
    report = check_specs.run(tmp_path)
    assert report.warnings == ["FEAT/CHANGE_FEAT.md: open finding FEAT F-01 (Low) (rule b)"]
    assert len(report.errors) == 1, report.errors
    assert "I-07 cited 1x without its spec prefix" in report.errors[0]
    assert "CHANGE_FEAT.md" in report.errors[0]


def test_ac128_change_template_sections_and_criteria():
    text = (TEMPLATES / "CHANGE_TEMPLATE.md").read_text(encoding="utf-8")
    headings = [h.strip() for h in check_specs.HEADING.findall(check_specs.FENCE.sub("", text))]
    assert headings == CHANGE_SECTIONS == check_specs.PHASES["CHANGE"]["sections"]
    rows = re.findall(r"^\|\s*(E[1-8])\s*\|", text, flags=re.MULTILINE)
    assert rows == [f"E{n}" for n in range(1, 9)]
    for needle in ("Relaxing", "Rule Changes", "User OK", "Evidence commit", "final commit"):
        assert needle in text, needle
    assert "check_specs.py" in text
    assert "last commit" in text


def test_ac128_template_copied_as_draft_has_no_missing_section(tmp_path):
    write(tmp_path, "features", "CHANGE_X.md", (TEMPLATES / "CHANGE_TEMPLATE.md").read_text())
    assert check_specs.run(tmp_path).errors == []


def test_ac129_self_test_simulates_change_documents(tmp_path):
    root = tmp_path / "repo"
    write(root, "features", "CHANGE_DONE.md", change_doc("Complete"))
    write(root, "features", "CHANGE_WIP.md", change_doc("Ready for Build"))
    final = final_status_docs(root)
    assert [d.feature for d in final] == ["DONE"]
    added = simulate_archive(tmp_path / "sim", final)
    assert added == ["DONE/CHANGE_DONE.md"]
    folder = tmp_path / "sim" / ".claude" / "sdd" / "archive" / "DONE"
    assert sorted(p.name for p in folder.iterdir()) == ["CHANGE_DONE.md"]
    assert check_specs.run(tmp_path / "sim").errors == []


def test_ac130_docs_describe_the_change_track():
    readme = (ROOT / ".claude" / "sdd" / "README.md").read_text(encoding="utf-8")
    for needle in ("CHANGE", "E1", "E8", "unrecognized", "Evidence commit", "final commit"):
        assert needle in readme, needle
    assert "check_specs.py" in readme
    assert "final head" in readme
    git = (ROOT / "docs" / "conventions" / "git.md").read_text(encoding="utf-8")
    for needle in ("change/", "spec/", "build/", "ship/"):
        assert needle in git, needle
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "CHANGE" in claude


@pytest.mark.parametrize(
    ("rule_changes", "e8", "expected"),
    [
        (RULE_CHANGES, "Relaxing", None),
        ("", "Yes", None),
        ("", "Relaxing", "'## Rule Changes' is missing"),
        (
            RULE_CHANGES.replace("After (docs/conventions/git.md:20)", "After"),
            "Relaxing",
            "'After' line has no path:line",
        ),
        (RULE_CHANGES.replace("gh api", "curl"), "Relaxing", "no fenced block with 'gh api'"),
        (RULE_CHANGES.replace("User OK: 2026-11-05", ""), "Relaxing", "no 'User OK: YYYY-MM-DD'"),
    ],
)
def test_ac131_relaxing_needs_the_rule_changes_gate(tmp_path, rule_changes, e8, expected):
    text = change_doc(eligibility={"E8": (e8, "diff quoted below")}, tail=rule_changes)
    errors = run_change(tmp_path, text)
    if expected is None:
        assert errors == []
    else:
        assert len(errors) == 1, errors
        assert expected in errors[0]


def test_ac125_fail_word_in_evidence_text_is_not_a_failure(tmp_path):
    text = change_doc().replace(
        "| AC-01 | Pass | output |", "| AC-01 | Pass | fails before, passes after |"
    )
    assert run_change(tmp_path, text) == []


@pytest.mark.parametrize("result", ["Not run", "not run", "**Not run**", "Not run: no fixture"])
def test_ac125_not_run_blocks_complete(tmp_path, result):
    errors = run_change(tmp_path, change_doc(evidence_result=result))
    assert errors == ["CHANGE_X.md: Complete with criteria not run: AC-01, AC-02"]


def test_ac125_not_run_allowed_before_complete(tmp_path):
    assert run_change(tmp_path, change_doc("Ready for Build", evidence_result="Not run")) == []


def test_ac125_deferred_with_reason_passes_and_is_listed(tmp_path):
    text = change_doc().replace(
        "| AC-02 | Pass | output |", "| AC-02 | Deferred: needs a live workspace | none yet |"
    )
    write(tmp_path, "features", "CHANGE_X.md", text)
    report = check_specs.run(tmp_path)
    assert report.errors == []
    assert report.warnings == ["CHANGE_X.md: AC-02 deferred: needs a live workspace"]


@pytest.mark.parametrize("result", ["Deferred:", "Deferred: ", "Deferred", "Deferred - later"])
def test_ac125_deferred_without_reason_is_an_error(tmp_path, result):
    text = change_doc().replace("| AC-02 | Pass | output |", f"| AC-02 | {result} | none |")
    write(tmp_path, "features", "CHANGE_X.md", text)
    report = check_specs.run(tmp_path)
    assert report.errors == [
        "CHANGE_X.md: AC-02 is Deferred without a reason ('Deferred: <reason>')"
    ]
    assert report.warnings == []


def test_ac122_no_acceptance_criteria_rows_is_an_error(tmp_path):
    text = (
        change_doc()
        .replace("| AC-01 | given | when | then |", "none")
        .replace("| AC-02 | given | when | then |", "")
    )
    errors = run_change(tmp_path, text)
    assert any("no acceptance criteria rows" in e for e in errors), errors


def test_ac131_template_example_fence_does_not_hide_the_real_section(tmp_path):
    fenced = "```markdown\n## Rule Changes\nnothing\n```\n"
    text = change_doc(eligibility={"E8": ("Relaxing", "below")}, tail=RULE_CHANGES)
    text = text.replace("## Scope\n", fenced + "## Scope\n")
    assert run_change(tmp_path, text) == []
