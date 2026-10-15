---
description: Phase 1 - write testable requirements, data contracts and acceptance criteria
argument-hint: <path to BRAINSTORM document, notes file, or a request>
---

Use the `define-agent` subagent to run Phase 1 of the SDD workflow.

Input: $ARGUMENTS

Write `.claude/sdd/features/DEFINE_{FEATURE}.md` from
`.claude/sdd/templates/DEFINE_TEMPLATE.md`. Keep the `{FEATURE}` name of the brainstorm when
one exists. When done, run `python scripts/check_specs.py` and report the result.
