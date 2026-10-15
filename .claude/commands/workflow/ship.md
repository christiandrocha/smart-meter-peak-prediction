---
description: Phase 4 - archive a completed feature with lessons learned
argument-hint: <FEATURE name>
---

Use the `ship-agent` subagent to run Phase 4 of the SDD workflow.

Feature: $ARGUMENTS

The build report must have status `Complete`. Archive the documents to
`.claude/sdd/archive/{FEATURE}/`, write `SHIPPED_{YYYY-MM-DD}.md`, accept the feature's ADRs
and update `CHANGELOG.md`.
