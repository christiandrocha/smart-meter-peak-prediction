# 0011. Dense ML tables written by change-only MERGE; training sets kept as run artifacts, not tables

| Attribute | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-21 |
| **Deciders** | Christian |
| **Related** | PEAK_MODEL; FR-19 to FR-23, FR-27, NFR-10, NFR-11, NFR-17; AC-41, AC-42, AC-48, AC-55, AC-57, AC-66; D-32; OD-09; ADR 0005, 0006, 0007 |

Status values: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

## Context

PEAK_MODEL owns five tables:
- `silver.weather_hourly`;
- `ml.household_features_daily`, a UC feature table with time-series column `feature_date`
  (variant 1A, ADR 0007);
- `ml.household_labels_daily`;
- `gold.consumption_spike_predictions`;
- `bronze.files_weather_hourly`, an append-only Bronze table.

They are computed in serverless job tasks, not in a pipeline (ADR 0008).

Requirements and facts:
- Re-running a step with no new input must change 0 rows, and a rebuild from Bronze weather and the
  METER_INGESTION tables must give identical content (NFR-11, AC-66).
- The Feature Engineering lookup is as-of: it returns the latest feature row at or before the lookup
  date, and nulls before the first row (spike 05). A sparse table would silently return an older
  row. FR-20 therefore makes the feature table dense, with one row per household and date.
- The training set must be auditable and rebuildable (AC-48, AC-55, NFR-17). DEFINE OD-09 asks
  whether it is persisted as a table or logged with the run.
- Floating-point sums in Spark depend on the order of partial aggregates, so a recomputation can
  differ in the last bit and rewrite rows that have not changed.
- Unity Catalog managed tables can be vacuumed. Time travel to a logged version then works only
  within the retained history.
- The volume is small: 36,480 rows per ML table for seed 42, and about 21,000 weather rows.

## Decision drivers

- Idempotent and rebuildable outputs (golden rule 4, NFR-11, AC-66).
- An exact point-in-time lookup under the as-of semantics (AC-41, AC-48).
- Reproducing and auditing a model version from its run alone (AC-54, AC-55).
- Few objects in the catalog, inside the Free Edition quota.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| **Recompute the full output of each step as a DataFrame, check density and rules, then MERGE: update only rows whose values differ (null-safe), insert new keys, delete keys that are no longer produced. Floating-point aggregates use a fixed summation order. The training set is not a table: the run logs `training_set.parquet`, the source table names with Delta versions (`mlflow.log_input`), and per-split counts with a content checksum. History retention of the feature and label tables is raised to 90 days** | A rerun with no new input changes 0 rows (MERGE metrics show it). A rebuild after a drop gives the same content. No extra table. Every run carries its exact training data. The logged versions allow a rebuild check (AC-55, 1B branch) | Each step recomputes all rows, which is cheap at this volume. MERGE logic and its change condition are our code. The artifacts grow with every run (about 2 MB each) |
| Overwrite each table on every run | Simplest write | Rewrites every row and creates a new version each day; "changes 0 rows" fails, and lineage and history are noisy |
| Incremental append of new dates only | Least compute | A late correction in Gold (re-ingested month) is never picked up; idempotency depends on watermark state |
| Persist each training set as a Delta table (`ml.training_set_<run>`) | Queryable with SQL | One table per run, or overwrites that break reproducibility; more objects to govern and clean up |

## Decision

We will compute each PEAK_MODEL output in full from its inputs, validate it (density, uniqueness,
quality rules), and write it with one Delta MERGE per run:
- matched rows are updated only when at least one column differs under null-safe equality;
- unmatched source rows are inserted;
- target rows not matched by the source are deleted.

The predictions table is the exception: it replaces the rows of the scored target dates with
`replaceWhere`, because `_scored_at` must change (AC-57).

Sums and means of floating-point values use a fixed order, either a window over ordered rows or
`aggregate` over a sorted array.

The training set is materialised once per training run. It is logged as the artifact
`training_set.parquet`, with the feature and label table names, their Delta versions, and per-split
row counts, positive counts and checksums. The feature and label tables get
`delta.logRetentionDuration` and `delta.deletedFileRetentionDuration` of 90 days.

## Consequences

- **Positive:** AC-66 and NFR-11 hold by construction and are measurable through MERGE metrics and
  table checksums. The feature lookup is exact for every training and scoring row. A model version
  can be audited from its run without querying tables that may have moved on.
- **Negative:** A model whose run is older than the 90-day retention can be rebuilt only from its
  artifact, not by time travel. A full recompute per step costs more as history grows (revisit
  trigger below). Writing a Feature Engineering table with plain MERGE, not with `fe.write_table`, is
  an assumption that `/build` checks first (DESIGN DA-15).
- **What would make us revisit this:**
  - one step recomputing for more than 10 minutes, or more than 10 M rows in an ML table: move to
    incremental windows over the changed dates;
  - a model kept in production beyond the retention window;
  - Feature Engineering lookups gaining an exact-match mode.
