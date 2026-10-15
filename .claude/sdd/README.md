# Spec-Driven Development workflow

Every non-trivial change goes through phases. Each phase produces one document, and the next
phase starts only when the previous document passes its gate.

```text
/brainstorm  ->  features/BRAINSTORM_{FEATURE}.md      (optional, Phase 0)
/define      ->  features/DEFINE_{FEATURE}.md          (Phase 1)
/design      ->  features/DESIGN_{FEATURE}.md          (Phase 2)
/build       ->  code + reports/BUILD_REPORT_{FEATURE}.md  (Phase 3)
/ship        ->  archive/{FEATURE}/SHIPPED_{YYYY-MM-DD}.md (Phase 4)
/iterate     ->  updates any of the documents above, with a change log
/adr         ->  docs/adr/NNNN-title.md                (any phase)
```

## Phase gates

| Phase | Gate to leave the phase | Status value when the gate passes |
|---|---|---|
| Brainstorm | At least 3 discovery questions answered, 2+ approaches compared, one selected by the user, YAGNI list written | `Ready for Define` |
| Define | Clarity score >= 12/15, every acceptance criterion measurable and numbered `AC-NN` | `Ready for Design` |
| Design | Every `AC-NN` mapped to a test, file manifest complete, decisions recorded as ADRs | `Ready for Build` |
| Build | Every manifest file created and verified, every `AC-NN` has evidence | `Complete` |
| Ship | Lessons learned and follow-ups recorded, documents archived | `Shipped` |

`scripts/check_specs.py` enforces the mechanical part of these gates in CI:
required sections, valid status, no unfilled placeholders after the draft stage,
and acceptance-criteria traceability from DEFINE to DESIGN to BUILD_REPORT. It also checks
the structure of ADRs (`docs/adr/`) and data contracts (`docs/contracts/`).

## Rules

1. Specs describe *what* and *why* before code describes *how*. Code written before the spec
   is allowed only as a spike (see `docs/spikes/README.md`).
2. One feature per document set. `{FEATURE}` is UPPER_SNAKE_CASE and identical across phases.
3. Change an approved document only through `/iterate`, which logs the change and checks what
   it invalidates downstream.
4. Decisions that outlive the feature (technology choice, data layout, contract) become ADRs.
5. Every phase document ends with a **Self-Review**: weak points, risks, trade-offs and the
   concrete improvement you would make next. A document without it does not pass the gate.

## Folders

| Folder | Content |
|---|---|
| `templates/` | One template per phase. Agents copy them; do not edit them per feature |
| `features/` | Active feature documents |
| `reports/` | Build reports |
| `archive/` | Shipped features, one folder per feature |
