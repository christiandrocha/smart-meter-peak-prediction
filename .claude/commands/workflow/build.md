---
description: Phase 3 - implement the design file by file and collect evidence for every acceptance criterion
argument-hint: <path to DESIGN document>
---

Use the `build-agent` subagent to run Phase 3 of the SDD workflow.

Input: $ARGUMENTS

The DESIGN document must have status `Ready for Build`. Implement the file manifest in order,
verify each file, and write `.claude/sdd/reports/BUILD_REPORT_{FEATURE}.md` from
`.claude/sdd/templates/BUILD_REPORT_TEMPLATE.md`. Before setting status `Complete`, run the
`code-reviewer` subagent on the changed files and address High findings.
