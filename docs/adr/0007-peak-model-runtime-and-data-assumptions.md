# 0007. PEAK_MODEL runtime and data assumptions

| Attribute | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-10-21 |
| **Deciders** | Christian |
| **Related** | PEAK_MODEL; FR-21, FR-22, FR-32; AC-41, AC-44, AC-47, AC-49, AC-55, AC-63, AC-67; D-19, D-27, D-32, D-34; ADR 0001 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

`DEFINE_PEAK_MODEL.md` depends on four assumptions that must be proven before `/design`. Three are
about the platform: MLflow with the Unity Catalog registry, Feature Engineering in UC on
serverless, and deterministic training. They are answered by spike 05. One is about the data: the
seed-42 label and eligibility figures that AC-44 and AC-47 assert were first computed by a scratch
script outside the repository. This record lists each assumption, its spike, the pass criterion,
the result and the fallback, in the same form as ADR 0001.

| ID | Assumption | Spike | Pass criterion | Result | Fallback |
|---|---|---|---|---|---|
| A-17 | The seed-42 label and eligibility figures of F-28, F-30 and F-31 follow from the written definitions | `spikes/local/a17_peak_labels_eligibility.py` | Recomputed from `data/sample/seed42` with the DEFINE definitions (FR-21, FR-22, D-19, D-27, D-34) on top of the METER_INGESTION Silver and Gold rules: AC-41, AC-44 and AC-47 figures match; with label threshold 1.5 and coverage threshold 0.90 the AC-63 checks hold | Pass (2026-10-21). Silver 1,679,914 rows, 60 households. Label table 36,480 rows, unique keys, 0 QR-19 violations. 33,093 labelled rows at 14.61% positive, T from 2012-07-29 to 2014-02-27. Eligible labelled rows: train 16,969 (14.03%), validation 7,170 (15.79%), test 5,116 (13.57%); first eligible T 2012-10-01, last ineligible T 2013-10-31. Ineligible labelled rows by reason: `insufficient_history` 3,054, `low_coverage` 663, `high_zero_share` 121, with no row carrying two reasons. AC-63 run: 7.91% positive, 29,100 eligible labelled rows (default 29,255) | ACs change through `/iterate`, not in `/build` |
| A-04 | MLflow registers models in UC and resolves aliases on Free Edition serverless; a scikit-learn model with a signature loads by `models:/...@champion` | `spikes/databricks/05_spike_mlflow_uc.py`, submitted as a two-task serverless job by `05_spike_mlflow_uc_submit.py` | A version is registered in `smart_meter_dev.ml`, alias `champion` is set, and the model loads by alias and scores | Pending | None inside the decided scope; would reopen D-32 and the registry choice through `/iterate` |
| A-12 | Feature Engineering in UC works on Free Edition serverless: the client installs in the job environment, `create_table` with `timeseries_columns`, `create_training_set` with `timestamp_lookup_key`, `fe.log_model`, `fe.score_batch`, lineage from model to feature table | spike 05 | Every listed call succeeds in a serverless job task and the lineage graph shows the feature table upstream of the model | Pending | Variant 1B (D-32): plain Delta tables, explicit join on `feature_date = target_date - 1`, table names and Delta versions logged with the run |
| A-16 | Training is deterministic on serverless: two runs on the same input and seed give identical scores | spike 05 | Two `HistGradientBoostingClassifier` fits with `random_state` fixed and `early_stopping=False` give bitwise identical scores on the same input, in one process and in a second job task | Pending | AC-49 relaxed to a stated tolerance through `/iterate` |

## Decision drivers

- `/design` must not build on unproven platform capabilities (CLAUDE.md, spike rule).
- Numeric acceptance criteria must come from committed, rerunnable code (golden rule 3, the A-13
  precedent).
- A failed spike should change configuration or one variant, not the architecture.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Spike each assumption and record pass, result and fallback here before `/design`** | Failures are found before design; the fallback is chosen with evidence | Spike 05 needs workspace time on the Free Edition quota |
| Design for variant 1A and find out in `/build` | No delay before `/design` | A failed A-12 would force a redesign of tasks 2, 4 and 5 mid-build |
| Design only for the 1B fallback | No dependency on Feature Engineering | Gives up UC feature lineage (AC-55, variant 1A) without evidence that it is unavailable |

## Decision

We will prove A-17, A-04, A-12 and A-16 with the spikes listed above before `/design`. A-17 has
passed and AC-41, AC-44, AC-47 and AC-63 keep their figures. The variant (1A, or the 1B fallback of
D-32) is decided here once spike 05 has run, and this record moves to `Accepted` then (AC-67).

## Consequences

- **Positive:** the seed-42 figures in the acceptance criteria now come from a committed script that
  follows the written definitions, so `/build` tests can cite it as their oracle.
- **Negative:** `/design` stays blocked until spike 05 runs on the workspace.
- **What would make us revisit this:** a change to the label or eligibility definitions (rerun
  A-17), a new seed or sample (rerun A-17), or a Free Edition change to serverless ML libraries
  (rerun spike 05).
