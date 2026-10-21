# 0007. PEAK_MODEL runtime and data assumptions

| Attribute | Value |
|---|---|
| **Status** | Accepted |
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
| A-04 | MLflow registers models in UC and resolves aliases on Free Edition serverless; a scikit-learn model with a signature loads by `models:/...@champion` | `spikes/databricks/05_spike_mlflow_uc.py`, submitted as a two-task serverless job by `05_spike_mlflow_uc_submit.py` | A version is registered in `smart_meter_dev.ml`, alias `champion` is set, and the model loads by alias and scores | Pass (run 624093996306456, 2026-10-21, 234 s, two serverless notebook tasks; Python 3.11.10, MLflow 3.17.2, scikit-learn 1.3.0, `databricks-feature-engineering` 0.18.2, 4 CPUs, session time zone `Etc/UTC`). A probability pyfunc with a signature registered as version 1, `champion` resolved to 1, and `models:/...@champion` reproduced the local scores exactly (max abs diff 0). A model version tag (`decision_threshold`) round-tripped, an option for OD-08. A registered model with versions cannot be deleted until its aliases and versions are removed | None inside the decided scope; would reopen D-32 and the registry choice through `/iterate` |
| A-12 | Feature Engineering in UC works on Free Edition serverless: the client installs in the job environment, `create_table` with `timeseries_columns`, `create_training_set` with `timestamp_lookup_key`, `fe.log_model`, `fe.score_batch`, lineage from model to feature table | spike 05 | Every listed call succeeds in a serverless job task and the lineage graph shows the feature table upstream of the model | Pass (same run). `%pip install databricks-feature-engineering` in the notebook task installed 0.18.2. `create_table` with `timeseries_columns`; `create_training_set` with `timestamp_lookup_key` on 2,860 labels gave 0 rows different from the explicit join on `feature_date = target_date - 1`, in both tasks. `fe.log_model` accepted a probability pyfunc with `artifact_path` and `signature`; `fe.score_batch` through `@champion` reproduced the local probabilities exactly; the model carries `feature_spec.yaml` naming the feature table; the UC table-lineage API lists the model downstream of the feature table. As-of semantics: a lookup after the last feature date returns the last row, and one before the first returns nulls, so FR-20's dense table is what keeps the lookup exact | Variant 1B (D-32): plain Delta tables, explicit join on `feature_date = target_date - 1`, table names and Delta versions logged with the run |
| A-16 | Training is deterministic on serverless: two runs on the same input and seed give identical scores | spike 05 | Two `HistGradientBoostingClassifier` fits with `random_state` fixed and `early_stopping=False` give bitwise identical scores on the same input, in one process and in a second job task | Pass (same run). 920 test scores identical in one process and in the `retrain` task (max abs diff 0). scikit-learn 1.3.0 is preinstalled and `%pip install scikit-learn` does not upgrade it, so the version must be pinned in the job environment | AC-49 relaxed to a stated tolerance through `/iterate` |

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

We proved A-17, A-04, A-12 and A-16 with the spikes listed above before `/design`; all four pass.
AC-41, AC-44, AC-47 and AC-63 keep their figures. Because A-12 passes, PEAK_MODEL uses variant 1A
of D-32: a UC Feature Engineering table with a point-in-time training set, `fe.log_model` and
`fe.score_batch`. The 1B fallback (plain Delta tables and an explicit join) stays documented and
was exercised by the spike as the reference join.

## Consequences

- **Positive:** the seed-42 figures in the acceptance criteria come from a committed script that
  follows the written definitions, so `/build` tests can cite it as their oracle. Variant 1A gives
  platform lineage from the model to the feature table (AC-55) and probability scores through
  `fe.score_batch`.
- **Negative:** `/design` must pin `databricks-feature-engineering` and `scikit-learn` in the job
  environment, because the serverless default scikit-learn (1.3.0) does not follow a plain
  install. Removing a registered model needs its aliases and versions deleted first, which matters
  for test cleanup.
- **Note (2026-10-21, PR 2 gate):** the facts above hold for serverless environment version 2,
  the default of one-off submitted runs where spike 05 ran. Jobs deployed from the bundle without
  an explicit environment got Python 3.12, where the `scikit-learn==1.3.0` pin has no wheel. Both
  PEAK_MODEL jobs therefore pin `environment_version: "2"` (DESIGN G-01, build deviation D-19).
  Environment 3 has Python 3.12, scikit-learn 1.4.2 and numpy 1.26; environment 4 has
  scikit-learn 1.6.1 and numpy 2.1.
- **What would make us revisit this:** a change to the label or eligibility definitions (rerun
  A-17), a new seed or sample (rerun A-17), or a Free Edition change to serverless ML libraries,
  or the retirement of serverless environment version 2 (rerun spike 05).
