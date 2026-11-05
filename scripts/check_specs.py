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

Archived documents (.claude/sdd/archive/<FEATURE>/, SPEC_ARCHIVE_GATES) are checked too:
  - the rules above, with traceability grouped per archive folder
  - rule (a): each archived phase document has its phase's final status, each folder has exactly
    one SHIPPED_YYYY-MM-DD.md with status Shipped, and no other .md file name
  - SHIPPED documents: file-name date, a matching "Shipped on" row, the SHIPPED sections including
    a non-empty Self-Review; from the cut-off date 2026-11-05 also "Pull Requests and Branches"
    and no unfilled placeholders (dates come from the file name, never from file times)
  - rule (b): a warning for each finding whose Follow-up cell starts with "Open"
  - rule (c): a citation I-NN or F-NN of an ID that the citing spec does not define must carry
    the spec's folder name before it; existing cases are frozen with exact counts in
    .claude/sdd/citation_allowlist.json, and a stale or wrong entry is an error

Exit code 0 when there are no errors (warnings do not fail). Templates are not checked.

Usage: python scripts/check_specs.py [--root PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
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
    folder: str | None = None  # archive folder name; None for features/ and reports/

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

    def error(self, where: Doc | Path | str, msg: str) -> None:
        self.errors.append(f"{_name(where)}: {msg}")

    def warn(self, where: Doc | Path | str, msg: str) -> None:
        self.warnings.append(f"{_name(where)}: {msg}")


def _name(where: Doc | Path | str) -> str:
    if isinstance(where, str):
        return where
    if isinstance(where, Doc) and where.folder:
        return f"{where.folder}/{where.path.name}"  # SHIPPED names repeat across folders
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


# ------------------------------------------------------------------------- archive
ARCHIVE_REL = Path(".claude") / "sdd" / "archive"
ALLOWLIST_REL = Path(".claude") / "sdd" / "citation_allowlist.json"
SHIPPED_SECTIONS = [
    "Metadata",
    "What Shipped",
    "Acceptance Criteria Final Status",
    "Lessons Learned",
    "Decisions to Carry Forward",
    "Template Feedback",
    "Follow-ups",
    "Pull Requests and Branches",
    "Archived Documents",
    "Self-Review",
]
# From this file-name date on, SHIPPED documents also need these sections and no placeholders
# (DESIGN OD-30, DEFINE D-73 and D-81).
SHIPPED_CUTOFF = date(2026, 11, 5)
SHIPPED_CUTOFF_SECTIONS = {"Pull Requests and Branches"}
SHIPPED_NAME = re.compile(r"^SHIPPED_(\d{4}-\d{2}-\d{2})\.md$")
SHIPPED_ON = re.compile(r"^\|\s*\*\*Shipped on\*\*\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
FINAL_STATUS = {
    phase: next(status for status, past_draft in spec["statuses"].items() if past_draft)
    for phase, spec in PHASES.items()
}
FINDING_ROW = re.compile(r"^\|\s*((?:I|F)-\d+)\s*\|(.*)$", re.MULTILINE)  # G-35 definition
CITATION = re.compile(r"(?<![\w-])((?:I|F)-\d+)(?![\w-])")  # G-35 citation
EMPHASIS = re.compile(r"[*_`]")
PREFIX_WINDOW = 80  # characters before a citation searched for its spec prefix


@dataclass
class Folder:
    name: str
    phase_docs: list[Doc]
    shipped: list[Doc]
    unknown: list[str]


def load_archive(root: Path) -> list[Folder]:
    """One entry per folder directly under the archive; files outside folders are ignored."""
    base = root / ARCHIVE_REL
    if not base.is_dir():
        return []
    folders = []
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        name = directory.name
        phase_docs, shipped, unknown = [], [], []
        for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".md"):
            text = path.read_text(encoding="utf-8")  # universal newlines: CRLF reads as LF
            phase = next((ph for ph in PHASES if path.stem == f"{ph}_{name}"), None)
            if phase:
                phase_docs.append(Doc(path, phase, name, text, folder=name))
            elif path.name.startswith("SHIPPED_"):
                shipped.append(Doc(path, "SHIPPED", name, text, folder=name))
            else:
                unknown.append(path.name)
        folders.append(Folder(name, phase_docs, shipped, unknown))
    return folders


def check_final_status(doc: Doc, report: Report) -> None:
    final = FINAL_STATUS[doc.phase]
    if doc.status is not None and doc.status != final:
        report.error(doc, f"archived {doc.phase} has status '{doc.status}', not '{final}' (rule a)")


def check_folder(folder: Folder, report: Report) -> None:
    where = f"archive/{folder.name}"
    if len(folder.shipped) != 1:
        found = len(folder.shipped)
        report.error(where, f"{found} SHIPPED document(s), expected exactly one (rule a)")
    for name in folder.unknown:
        msg = (
            f"unexpected file name '{name}': expected <PHASE>_{folder.name}.md or SHIPPED_ (rule a)"
        )
        report.error(where, msg)


def check_shipped(doc: Doc, report: Report) -> None:
    m = SHIPPED_NAME.match(doc.path.name)
    if not m:
        report.error(doc, "SHIPPED file name must be SHIPPED_YYYY-MM-DD.md")
        return
    try:
        shipped_on = date.fromisoformat(m.group(1))  # G-38: the file name, never file times
    except ValueError:
        report.error(doc, f"SHIPPED file name has an invalid date '{m.group(1)}'")
        return
    if doc.status != "Shipped":
        report.error(doc, f"SHIPPED status '{doc.status}', expected 'Shipped' (rule a)")
    row = SHIPPED_ON.search(doc.body)
    if not row or row.group(1).strip() != m.group(1):
        found = row.group(1).strip() if row else "missing"
        report.error(doc, f"'Shipped on' is {found}, expected {m.group(1)} from the file name")
    after_cutoff = shipped_on >= SHIPPED_CUTOFF
    headings = {h.strip() for h in HEADING.findall(doc.body)}
    for section in SHIPPED_SECTIONS:
        if section in SHIPPED_CUTOFF_SECTIONS and not after_cutoff:
            continue
        if section not in headings:
            report.error(doc, f"missing section '## {section}'")
    if "Self-Review" in headings and not doc.section("Self-Review").strip():
        report.error(doc, "Self-Review is empty")
    if after_cutoff:
        leftovers = sorted(set(PLACEHOLDER.findall(doc.body)))
        if leftovers:
            shown = ", ".join(leftovers[:5]) + (" ..." if len(leftovers) > 5 else "")
            report.error(doc, f"unfilled placeholders remain: {shown}")


def open_findings(doc: Doc, report: Report) -> None:
    """Rule (b): warn for each finding whose Follow-up cell starts with the word Open."""
    for m in FINDING_ROW.finditer(doc.section("Issues & Follow-ups")):
        cells = [c.strip() for c in m.group(2).rstrip().rstrip("|").split("|")]
        severity = cells[1] if len(cells) > 1 else ""
        follow_up = EMPHASIS.sub("", cells[2]).strip() if len(cells) > 2 else ""
        if re.match(r"Open\b", follow_up):
            report.warn(doc, f"open finding {doc.folder} {m.group(1)} ({severity}) (rule b)")


def _blank_fences(text: str) -> str:
    """G-34: fenced code becomes blank lines, so positions and line breaks are kept."""
    return FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def citation_violations(root: Path, folders: list[Folder]) -> Counter:
    """Rule (c): unprefixed citations of IDs the citing folder does not define, per (file, ID)."""
    names = sorted((f.name for f in folders), key=len, reverse=True)
    if not names:
        return Counter()
    # G-37: the folder name, then spaces or tabs with at most one line break, then the ID.
    prefix = re.compile(
        r"\b(?:" + "|".join(map(re.escape, names)) + r")(?:[ \t]+|[ \t]*\n[ \t]*)\Z"
    )
    found: Counter = Counter()
    for folder in folders:
        texts = {doc.path: _blank_fences(doc.text) for doc in folder.phase_docs + folder.shipped}
        defined = {m.group(1) for text in texts.values() for m in FINDING_ROW.finditer(text)}
        for path, text in texts.items():
            definitions = {m.start(1) for m in FINDING_ROW.finditer(text)}
            rel = path.relative_to(root).as_posix()  # G-39
            for m in CITATION.finditer(text):
                cited = m.group(1)
                if m.start(1) in definitions or cited in defined:
                    continue
                if prefix.search(text[max(0, m.start() - PREFIX_WINDOW) : m.start()]):
                    continue
                found[(rel, cited)] += 1
    return found


def load_allowlist(root: Path, report: Report) -> dict[tuple[str, str], int] | None:
    """The frozen rule (c) cases; None when the file is absent."""
    path = root / ALLOWLIST_REL
    if not path.exists():
        return None
    where = ALLOWLIST_REL.as_posix()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["entries"]
        if data.get("version") != 1 or not isinstance(entries, list):
            raise ValueError("expected version 1 and a list of entries")
        allowed: dict[tuple[str, str], int] = {}
        for entry in entries:
            key = (str(entry["file"]), str(entry["id"]))
            count = entry["count"]
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError(f"count of {key[0]} {key[1]} must be a positive integer")
            if key in allowed:
                raise ValueError(f"duplicate entry {key[0]} {key[1]}")
            allowed[key] = count
    except (ValueError, KeyError, TypeError) as exc:  # json.JSONDecodeError is a ValueError
        report.error(where, f"malformed allowlist: {exc}")
        return {}
    return allowed


def check_citations(root: Path, found: Counter, report: Report) -> None:
    allowed = load_allowlist(root, report)
    where = ALLOWLIST_REL.as_posix()
    if allowed is None:
        if found:
            report.error(where, f"missing, but rule (c) found {sum(found.values())} citation(s)")
        allowed = {}
    for (rel, cited), count in sorted(found.items()):
        expected = allowed.get((rel, cited))
        if expected is None:
            msg = f"{cited} cited {count}x without its spec prefix and not in {where} (rule c)"
            report.error(rel, msg)
        elif expected != count:
            msg = f"entry {rel} {cited} has count {expected}, found {count} (rule c)"
            report.error(where, msg)
    for rel, cited in sorted(set(allowed) - set(found)):
        report.error(where, f"stale entry {rel} {cited}: no such citation found (rule c)")


def check_archive(root: Path, report: Report) -> int:
    folders = load_archive(root)
    for folder in folders:
        for doc in folder.phase_docs:
            check_doc(doc, report)
            check_final_status(doc, report)
        for doc in folder.shipped:
            check_shipped(doc, report)
        check_folder(folder, report)
        check_traceability(folder.phase_docs, report)  # FR-65: one folder at a time
        for doc in folder.phase_docs:
            if doc.phase == "BUILD_REPORT":
                open_findings(doc, report)
    check_citations(root, citation_violations(root, folders), report)
    return sum(len(f.phase_docs) + len(f.shipped) for f in folders)


def run(root: Path) -> Report:
    report = Report()
    docs = load_docs(root)
    for doc in docs:
        check_doc(doc, report)
    check_traceability(docs, report)
    report.checked = len(docs) + check_adrs(root, report) + check_contracts(root, report)
    report.checked += check_archive(root, report)
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
