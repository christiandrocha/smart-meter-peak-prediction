# 0009. Decision threshold stored as a model version tag, highest threshold wins ties

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-21 |
| **Deciders** | Christian |
| **Related** | PEAK_MODEL; FR-25, FR-29, NFR-18; AC-51, AC-56, AC-61; D-23; OD-08; ADR 0007 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

D-23 fixes the output semantics: `label = score >= t`, where t maximises F1 on the validation split
and is stored with the registered model version, so that scoring reads the t of the exact version
it uses (FR-25, AC-56). DEFINE OD-08 asks where t is stored and which threshold wins when several
reach the same validation F1. Spike 05 showed that a model version tag set with
`MlflowClient.set_model_version_tag` round-trips on Free Edition (ADR 0007). Run parameters and
metrics belong to the MLflow run, not to the registered version. Reading them from scoring needs a
second lookup (version to run, then run to data), and a run can back more than one version.

F1 at threshold t is `2 TP / (2 TP + FP + FN)` over the validation rows with `score >= t`. Scores
of a gradient boosting model take a limited set of values, so ties in F1 are possible, and F1 values
computed in floating point can differ in the last bit for counts that are mathematically equal.

## Decision drivers

- Scoring must read t from the version it scores with, in one call (AC-56).
- t must round-trip exactly, because `label = 1` exactly when `score >= t` (QR-20).
- The same validation scores must always give the same t (AC-49, AC-51).
- The model version must be auditable without the training code.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Version tag `decision_threshold` holding `repr(t)` (authoritative, read by scoring), plus the run metric `validation_threshold` and the run parameter `threshold_rule` for audit. Candidates are the distinct validation scores. F1 is compared exactly on integer counts, and the highest t wins a tie** | One registry call from scoring. Exact round trip (`float(repr(t)) == t`). Ties are resolved without floating point. A higher t gives fewer flags at the same F1, which is the conservative choice for an outreach team. The run keeps the value for audit | The tag is mutable, so anyone with write access to the model could change it |
| Run parameter or metric only | Immutable once logged | Scoring needs version to run to value. A metric is a float64 that the UI rounds. No per-version value if a run were registered twice |
| Inside the model (the wrapper returns labels) | A single artifact | `score` and `label` would come from one call, and t would be hidden in a pickle. The threshold could not be read or audited without loading the model |

## Decision

We will store t as the model version tag `decision_threshold`, with the value `repr(t)` of the
Python float, set before alias `champion` moves to the version. The training run also logs t as the
metric `validation_threshold` and the rule as the parameter `threshold_rule`. Scoring resolves
`champion` to a version, reads the tag of that version, and fails when the tag is missing or does
not parse.

Rule: the candidates are the distinct validation scores. For each candidate t, TP, FP and FN count
the validation rows with `score >= t`. F1 values are compared exactly as fractions (cross-multiplied
integer counts). Among the candidates with the maximal F1, the highest t wins. When validation has
no positive row, training fails before any metric or model is logged.

## Consequences

- **Positive:** `label` is reproducible from `score` and the version tag. AC-51 can recompute t from
  the logged validation scores with an independent brute-force implementation and compare exactly.
- **Negative:** The tag is mutable. Write access to `smart_meter_dev.ml.consumption_spike_model` must
  stay with the deploying user, and the run metric is the audit copy. The tie rule favours fewer
  flags, so daily flag volume may be lower than other max-F1 implementations would give.
- **What would make us revisit this:** a real consumer with a precision or capacity target (D-23
  revisit), a challenger flow (v0.3) that needs several thresholds per version, or registry support
  for immutable version metadata.
