---
description: Record an architecture decision as a numbered ADR
argument-hint: "<decision title>"
---

Create a new Architecture Decision Record for: $ARGUMENTS

1. Find the highest number in `docs/adr/` and use the next one, zero-padded to four digits.
2. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-kebab-case-title.md`.
3. Fill it from the current conversation and the related feature documents. Ask the user for
   anything missing about the options considered; do not invent rejected options.
4. Status starts as `Proposed`.
5. Add a row to the index in `docs/adr/README.md`.
