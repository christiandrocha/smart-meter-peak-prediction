"""Check SDD documents against the phase gates in .claude/sdd/README.md.

Checks, per feature document in .claude/sdd/features and .claude/sdd/reports:
  - required sections are present
  - the Status value is one of the allowed values for the phase
  - documents past their draft status contain no unfilled {placeholders}
  - DEFINE in "Ready for Design" has a clarity score of at least 12/15
  - acceptance criteria trace from DEFINE to DESIGN (Test Strategy) and BUILD_REPORT (Evidence)
  - a Complete build report has no failing acceptance criterion

Also checks docs/adr/NNNN-*.md (file name, status, required sections, index entry, superseded
references) and docs/contracts/*.yaml (required keys per kind, key columns present in the
schema, valid quality actions). Files whose name starts with "_" or "0000-" are templates.

Exit code 0 when there are no errors (warnings do not fail). Archived documents and templates
are not checked.

Usage: python scripts/check_specs.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PHASES = {
    "BRAINSTORM": {
        "sections": [
            "Metadata",
            "Initial Idea",
            "Discovery Questions & Answers",
            "Approaches Explored",
            "Selected Approach",
            "Out of Scope (YAGNI)",
            "Self-Review",
        ],
        "statuses": {"Exploring": False, "Ready for Define": True},
    },
    "DEFINE": {
        "sections": [
            "Metadata",
            "Problem Statement",
            "Scope",
            "Functional Requirements",
            "Acceptance Criteria",
            "Clarity Score",
            "Self-Review",
        ],
        "statuses": {"Draft": False, "Ready for Design": True},
    },
    "DESIGN": {
        "sections": [
            "Metadata",
            "Architecture",
            "Components",
            "File Manifest",
            "Test Strategy",
            "Self-Review",
        ],
        "statuses": {"Draft": False, "Ready for Build": True},
    },
    "BUILD_REPORT": {
        "sections": [
            "Metadata",
            "Files Changed",
            "Acceptance Criteria Evidence",
            "Self-Review",
        ],
        "statuses": {"In Progress": False, "Blocked": False, "Complete": True},
    },
}
MIN_CLARITY = 12

FENCE = re.compile(r"```.*?```", re.DOTALL)
PLACEHOLDER = re.compile(r"\{[A-Za-z][^{}\n]{0,80}\}")
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
STATUS = re.compile(r"^\|\s*\*\*Status\*\*\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
AC_ROW = re.compile(r"^\|\s*(AC-\d+)\s*\|(.*)$", re.MULTILINE)
# A result cell that starts with "Fail"; "fail" inside test names or prose does not count.
FAILING_CELL = re.compile(r"^\s*fail", re.IGNORECASE)
CLARITY_TOTAL = re.compile(r"\*\*Total\*\*\s*\|\s*\**\s*(\d+)\s*/\s*15", re.IGNORECASE)


@dataclass
class Doc:
    path: Path
    phase: str
    feature: str
    text: str

    @property
    def body(self) -> str:
        """Text without fenced code blocks, so example code does not count as placeholders."""
        return FENCE.sub("", self.text)

    def section(self, title: str) -> str:
        parts = re.split(r"^##\s+", self.body, flags=re.MULTILINE)
        for part in parts[1:]:
            heading, _, content = part.partition("\n")
            if heading.strip() == title:
                return content
        return ""

    @property
    def status(self) -> str | None:
        m = STATUS.search(self.body)
        return m.group(1).strip() if m else None


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    def error(self, where: Doc | Path, msg: str) -> None:
        self.errors.append(f"{_name(where)}: {msg}")

    def warn(self, where: Doc | Path, msg: str) -> None:
        self.warnings.append(f"{_name(where)}: {msg}")


def _name(where: Doc | Path) -> str:
    return (where.path if isinstance(where, Doc) else where).name


def load_docs(root: Path) -> list[Doc]:
    docs = []
    sdd = root / ".claude" / "sdd"
    for folder in ("features", "reports"):
        for path in sorted((sdd / folder).glob("*.md")):
            for phase in sorted(PHASES, key=len, reverse=True):  # BUILD_REPORT before BRAINSTORM
                prefix = f"{phase}_"
                if path.stem.startswith(prefix):
                    feature = path.stem[len(prefix) :]
                    docs.append(Doc(path, phase, feature, path.read_text(encoding="utf-8")))
                    break
    return docs


def ac_ids(section_text: str) -> dict[str, str]:
    """Map AC id -> rest of its table row, from a markdown table section."""
    return {m.group(1): m.group(2) for m in AC_ROW.finditer(section_text)}


def check_doc(doc: Doc, report: Report) -> None:
    spec = PHASES[doc.phase]
    headings = {h.strip() for h in HEADING.findall(doc.body)}
    for section in spec["sections"]:
        if section not in headings:
            report.error(doc, f"missing section '## {section}'")

    status = doc.status
    if status is None:
        report.error(doc, "no '| **Status** | ... |' row in Metadata")
        return
    if status not in spec["statuses"]:
        allowed = ", ".join(spec["statuses"])
        report.error(doc, f"status '{status}' not one of: {allowed}")
        return

    past_draft = spec["statuses"][status]
    if past_draft:
        leftovers = sorted(set(PLACEHOLDER.findall(doc.body)))
        if leftovers:
            shown = ", ".join(leftovers[:5]) + (" ..." if len(leftovers) > 5 else "")
            report.error(doc, f"status '{status}' but unfilled placeholders remain: {shown}")
        if not doc.section("Self-Review").strip():
            report.error(doc, "Self-Review is empty")

    if doc.phase == "DEFINE" and past_draft:
        m = CLARITY_TOTAL.search(doc.section("Clarity Score"))
        if not m:
            report.error(doc, "clarity score total not found ('**Total** | **N/15**')")
        elif int(m.group(1)) < MIN_CLARITY:
            report.error(doc, f"clarity score {m.group(1)}/15 below gate of {MIN_CLARITY}")
        if not ac_ids(doc.section("Acceptance Criteria")):
            report.error(doc, "no acceptance criteria rows (| AC-01 | ...)")


def check_traceability(docs: list[Doc], report: Report) -> None:
    by_feature: dict[str, dict[str, Doc]] = {}
    for doc in docs:
        by_feature.setdefault(doc.feature, {})[doc.phase] = doc

    for phases in by_feature.values():
        define = phases.get("DEFINE")
        design = phases.get("DESIGN")
        build = phases.get("BUILD_REPORT")
        defined = set(ac_ids(define.section("Acceptance Criteria"))) if define else set()

        if design:
            ready = design.status == "Ready for Build"
            if not define:
                (report.error if ready else report.warn)(design, "no matching DEFINE document")
            else:
                if define.status != "Ready for Design" and ready:
                    report.error(design, "Ready for Build but DEFINE is not Ready for Design")
                tested = set(ac_ids(design.section("Test Strategy")))
                missing = sorted(defined - tested)
                if missing:
                    msg = f"acceptance criteria without a test: {', '.join(missing)}"
                    (report.error if ready else report.warn)(design, msg)
                unknown = sorted(tested - defined)
                if unknown:
                    report.warn(design, f"tests reference ACs not in DEFINE: {', '.join(unknown)}")

        if build:
            complete = build.status == "Complete"
            evidence = ac_ids(build.section("Acceptance Criteria Evidence"))
            missing = sorted(defined - set(evidence))
            if missing:
                msg = f"acceptance criteria without evidence: {', '.join(missing)}"
                (report.error if complete else report.warn)(build, msg)
            if complete:
                failing = sorted(
                    ac
                    for ac, row in evidence.items()
                    if any(FAILING_CELL.match(cell) for cell in row.split("|"))
                )
                if failing:
                    report.error(build, f"Complete with failing criteria: {', '.join(failing)}")


# ---------------------------------------------------------------------------- ADRs
ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_SECTIONS = ["Context", "Options considered", "Decision", "Consequences"]
ADR_STATUS = re.compile(r"^(Proposed|Accepted|Deprecated|Superseded by (\d{4}))$")


def check_adrs(root: Path, report: Report) -> int:
    folder = root / "docs" / "adr"
    if not folder.is_dir():
        return 0
    index = (
        (folder / "README.md").read_text(encoding="utf-8")
        if (folder / "README.md").exists()
        else ""
    )
    files = [
        p
        for p in sorted(folder.glob("*.md"))
        if p.name != "README.md" and not p.name.startswith("0000-")
    ]
    numbers: dict[str, str] = {}
    for path in files:
        m = ADR_NAME.match(path.name)
        if not m:
            report.error(path, "ADR file name must be NNNN-kebab-case-title.md")
            continue
        number = m.group(1)
        if number in numbers:
            report.error(path, f"ADR number {number} already used by {numbers[number]}")
        numbers[number] = path.name

        doc = Doc(path, "ADR", number, path.read_text(encoding="utf-8"))
        headings = {h.strip() for h in HEADING.findall(doc.body)}
        for section in ADR_SECTIONS:
            if section not in headings:
                report.error(path, f"missing section '## {section}'")
        status = doc.status
        sm = ADR_STATUS.match(status or "")
        if not sm:
            report.error(
                path,
                f"status '{status}' not one of: Proposed, Accepted, Deprecated, Superseded by NNNN",
            )
        else:
            if sm.group(2) and not list(folder.glob(f"{sm.group(2)}-*.md")):
                report.error(path, f"superseded by ADR {sm.group(2)}, which does not exist")
            if status != "Proposed":
                leftovers = sorted(set(PLACEHOLDER.findall(doc.body)))
                if leftovers:
                    report.error(
                        path,
                        f"status '{status}' but unfilled placeholders remain: "
                        + ", ".join(leftovers[:5]),
                    )
        if path.name not in index:
            report.warn(path, "not listed in docs/adr/README.md")
    return len(files)


# ----------------------------------------------------------------------- contracts
CONTRACT_KINDS = {"table", "topic", "file", "api"}
QUALITY_ACTIONS = {"warn", "drop", "fail"}


def check_contracts(root: Path, report: Report) -> int:
    folder = root / "docs" / "contracts"
    files = (
        [p for p in sorted(folder.glob("*.y*ml")) if not p.name.startswith("_")]
        if folder.is_dir()
        else []
    )
    if not files:
        return 0
    try:
        import yaml
    except ImportError:
        report.errors.append(
            "docs/contracts: pyyaml is required to check contracts (pip install pyyaml)"
        )
        return 0

    for path in files:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            report.error(path, f"invalid YAML: {str(exc).splitlines()[0]}")
            continue
        if not isinstance(data, dict):
            report.error(path, "contract must be a YAML mapping")
            continue
        for key in ("dataset", "kind", "owner", "description"):
            if not data.get(key):
                report.error(path, f"missing '{key}'")
        kind = data.get("kind")
        if kind and kind not in CONTRACT_KINDS:
            report.error(path, f"kind '{kind}' not one of: {', '.join(sorted(CONTRACT_KINDS))}")

        schema = (data.get("value") or {}).get("schema") if kind == "topic" else data.get("schema")
        if not isinstance(schema, list) or not schema:
            where = "value.schema" if kind == "topic" else "schema"
            report.error(path, f"'{where}' must be a non-empty list of columns")
            schema = []
        names = set()
        for i, column in enumerate(schema):
            if not isinstance(column, dict) or not column.get("name") or not column.get("type"):
                report.error(path, f"schema entry {i + 1} needs 'name' and 'type'")
            else:
                names.add(column["name"])

        if kind == "topic":
            key_field = (data.get("key") or {}).get("field")
            if not key_field:
                report.error(path, "topic contract needs 'key.field'")
            elif names and key_field not in names:
                report.error(path, f"key field '{key_field}' not in value.schema")
        elif kind:
            if not data.get("grain"):
                report.error(path, "missing 'grain'")
            pk = data.get("primary_key")
            if not isinstance(pk, list) or not pk:
                report.error(path, "'primary_key' must be a non-empty list")
            elif names:
                unknown = [c for c in pk if c not in names]
                if unknown:
                    report.error(path, f"primary_key columns not in schema: {', '.join(unknown)}")

        for rule in data.get("quality") or []:
            action = rule.get("action") if isinstance(rule, dict) else None
            if action not in QUALITY_ACTIONS:
                report.error(path, f"quality action '{action}' not one of: warn, drop, fail")
    return len(files)


def run(root: Path) -> Report:
    report = Report()
    docs = load_docs(root)
    for doc in docs:
        check_doc(doc, report)
    check_traceability(docs, report)
    report.checked = len(docs) + check_adrs(root, report) + check_contracts(root, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args()

    report = run(args.root)
    for w in report.warnings:
        print(f"WARN  {w}")
    for e in report.errors:
        print(f"ERROR {e}")
    print(
        f"{report.checked} document(s) checked, "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
