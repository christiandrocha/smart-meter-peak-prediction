---
description: Change an approved BRAINSTORM, DEFINE or DESIGN document and report downstream impact
argument-hint: <path to document> "<change requested>"
---

Use the `iterate-agent` subagent.

Input: $ARGUMENTS

Apply the change, append it to the document's Change Log, and list what it invalidates in the
downstream documents. Run `python scripts/check_specs.py` afterwards.
