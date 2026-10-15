---
description: Phase 0 - explore an idea and compare approaches before writing requirements
argument-hint: <idea, problem statement or path to notes>
---

Use the `brainstorm-agent` subagent to run Phase 0 of the SDD workflow.

Input: $ARGUMENTS

Follow `.claude/sdd/README.md`. Write the result to
`.claude/sdd/features/BRAINSTORM_{FEATURE}.md` using
`.claude/sdd/templates/BRAINSTORM_TEMPLATE.md`, where `{FEATURE}` is an UPPER_SNAKE_CASE name
agreed with the user. Ask questions one at a time and confirm the selected approach before
writing the file.
