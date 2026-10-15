# MLflow and ML data patterns

## Tracking

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")  # registry in Unity Catalog
mlflow.set_experiment("/Users/<user>/<project>")

with mlflow.start_run(run_name="train-v1") as run:
    mlflow.log_params({"model": "lgbm", "label_threshold": 1.3})
    mlflow.log_param("training_table_version", delta_version)  # reproducibility
    ...
    mlflow.log_metric("val_pr_auc", pr_auc)
```

Log enough to rebuild the run: data version, feature table names, parameters, code commit.

## Unity Catalog model registry

- Model name is three-level: `<catalog>.<schema>.<model_name>`.
- A **signature is required** to register in UC: pass `signature=infer_signature(X, y_pred)`
  or an `input_example`.
- Promotion uses **aliases**, not stages:

```python
from mlflow import MlflowClient

client = MlflowClient()
client.set_registered_model_alias(name, "champion", version)
model = mlflow.pyfunc.load_model(f"models:/{name}@champion")
```

- Challenger flow: register a new version with alias `challenger`, compare on the same
  holdout, then move `champion`.

## Feature tables (Databricks Feature Engineering in UC)

```python
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup

fe = FeatureEngineeringClient()

fe.create_table(
    name="cat.ml.household_features_daily",
    primary_keys=["household_id", "feature_date"],
    timeseries_columns="feature_date",  # enables point-in-time lookups
    df=features_df,
)

training_set = fe.create_training_set(
    df=labels_df,  # household_id, label_date, label
    feature_lookups=[
        FeatureLookup(
            table_name="cat.ml.household_features_daily",
            lookup_key="household_id",
            timestamp_lookup_key="label_date",  # takes the latest feature row at or before this time
        )
    ],
    label="label",
    exclude_columns=["label_date"],
)
```

A point-in-time lookup returns the latest feature row with a timestamp at or before the label
timestamp. If a feature row dated D summarises day D itself, it must not be used to predict a
label for day D: align feature dates so the row is only complete strictly before the label
time (for example, label for D+1 joins features dated D). Logging the model with
`fe.log_model(..., training_set=training_set)` records feature lineage in UC.

## Temporal splits and evaluation

```text
|---------- train ----------|-- validation --|-- test --|   time ->
```

- Choose split dates in the DESIGN; never shuffle.
- With class imbalance, report PR-AUC and precision/recall at the operating threshold.
- Break metrics down by segment and by month when the positive rate varies.

## Leakage checklist

- Rolling windows end before the prediction time (`rows between N preceding and 1 preceding`).
- Baselines used to build the label are not features unless lagged.
- Dimensions are joined as of the event time, not their current value (SCD Type 2).
- Normalisation statistics are fitted on train only.

Sources: https://mlflow.org/docs/latest/ ,
https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle/ ,
https://docs.databricks.com/aws/en/machine-learning/feature-store/time-series
