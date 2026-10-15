---
description: Phase 2 - architecture, data model, ADRs, file manifest and test strategy
argument-hint: <path to DEFINE document>
---

Use the `design-agent` subagent to run Phase 2 of the SDD workflow.

Input: $ARGUMENTS

The DEFINE document must have status `Ready for Design`. Write
`.claude/sdd/features/DESIGN_{FEATURE}.md` from `.claude/sdd/templates/DESIGN_TEMPLATE.md`
and draft ADRs in `docs/adr/` for lasting decisions. When done, run
`python scripts/check_specs.py` and report the result, including acceptance-criteria
traceability.
