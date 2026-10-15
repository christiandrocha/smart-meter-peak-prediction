from pathlib import Path

import check_specs

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
    names = {
        "BRAINSTORM": "BRAINSTORM_TEMPLATE.md",
        "DEFINE": "DEFINE_TEMPLATE.md",
        "DESIGN": "DESIGN_TEMPLATE.md",
        "BUILD_REPORT": "BUILD_REPORT_TEMPLATE.md",
    }
    for phase, file in names.items():
        folder = "reports" if phase == "BUILD_REPORT" else "features"
        write(tmp_path, folder, f"{phase}_X.md", (TEMPLATES / file).read_text())
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
