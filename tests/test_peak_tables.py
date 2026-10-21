"""Schemas equal the contracts, DDL, MERGE text and rebuild stability (AC-64, AC-66), plus names and
parameters (AC-50, AC-63)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from support import peak_builders as pb

from smart_meter_peak_prediction import (
    delta_sync,
    features,
    labels,
    metrics,
    peak_config,
    peak_setup,
    scoring,
    weather,
)
from smart_meter_peak_prediction.config import Settings
from smart_meter_peak_prediction.peak_config import PeakParameters

CONTRACTS = Path(__file__).resolve().parents[1] / "docs" / "contracts"
PEAK_CONTRACTS = [
    "bronze_files_weather_hourly",
    "silver_weather_hourly",
    "ml_household_features_daily",
    "ml_household_labels_daily",
    "gold_consumption_spike_predictions",
]
PROCESSING_NAMES = {"ingested_at", "source_file", "rescued_data", "scored_at"}


def contract(name: str) -> dict:
    return yaml.safe_load((CONTRACTS / f"{name}.yaml").read_text(encoding="utf-8"))


def contract_columns(name: str) -> list[tuple[str, str]]:
    return [(c["name"], c["type"]) for c in contract(name)["schema"]]


def schema_of(df) -> list[tuple[str, str]]:
    return [(f.name, f.dataType.simpleString()) for f in df.schema.fields]


@pytest.fixture(scope="module")
def outputs(spark):
    fixture = pb.ac42_fixture()
    params = PeakParameters()
    households = pb.household_frame(spark, fixture.households)
    daily = pb.daily_frame(spark, fixture.daily)
    monthly = pb.monthly_frame(spark, fixture.monthly)
    bronze = pb.weather_bronze_frame(spark, pb.hourly_weather_rows(date(2013, 1, 1), 3))
    silver = weather.silver_weather(bronze).frame
    feature_table = features.build_features(
        households, daily, pb.silver_weather_frame(spark, fixture.weather), params, pb.AC42_START
    )
    label_table = labels.build_labels(households, daily, monthly, params, pb.AC42_START)
    scored = label_table.where("is_eligible").select(
        "household_id",
        "target_date",
        label_table["baseline_day_count"].cast("double").alias("prediction"),
    )
    predictions = scoring.assemble_predictions(
        scored.withColumn("prediction", scored["prediction"] / 10),
        7,
        0.5,
        datetime(2026, 10, 21, tzinfo=UTC),
    )
    return {
        "bronze_files_weather_hourly": bronze,
        "silver_weather_hourly": silver,
        "ml_household_features_daily": feature_table,
        "ml_household_labels_daily": label_table,
        "gold_consumption_spike_predictions": predictions,
    }


# ----------------------------------------------------------------------------- AC-64
@pytest.mark.parametrize("name", PEAK_CONTRACTS)
def test_ac64_library_schemas_equal_contracts_and_underscore_rule(outputs, name) -> None:
    assert schema_of(outputs[name]) == contract_columns(name)
    for column, _ in contract_columns(name):
        bare = column.lstrip("_")
        assert (column.startswith("_")) == (bare in PROCESSING_NAMES)


@pytest.mark.parametrize("name", PEAK_CONTRACTS[1:])
def test_ac64_non_nullable_contract_columns_hold_no_null(outputs, name) -> None:
    df = outputs[name]
    assert df.count() > 0
    for column in contract(name)["schema"]:
        if column["nullable"] is False:
            assert df.where(f"`{column['name']}` IS NULL").count() == 0, column["name"]


def test_ac64_label_column_name_and_primary_keys_are_in_the_contracts() -> None:
    assert "label_consumption_spike" in dict(contract_columns("ml_household_labels_daily"))
    assert contract("ml_household_features_daily")["primary_key"] == [
        "household_id",
        "feature_date",
    ]
    assert contract("ml_household_features_daily")["timeseries_column"] == "feature_date"
    assert contract("bronze_files_weather_hourly")["primary_key"] == ["_source_file", "time_raw"]
    assert contract("gold_consumption_spike_predictions")["owner"] == "PEAK_MODEL"


def test_ac64_ddl_nullability_and_feature_schema_follow_the_contracts() -> None:
    settings = Settings()
    ddl = {
        "bronze_files_weather_hourly": peak_setup.bronze_weather_ddl(settings),
        "silver_weather_hourly": peak_setup.silver_weather_ddl(settings),
        "ml_household_labels_daily": peak_setup.labels_ddl(settings),
        "gold_consumption_spike_predictions": peak_setup.predictions_ddl(settings),
    }
    for name, statement in ddl.items():
        not_null = set(re.findall(r"`(\w+)` [A-Z<>]+ NOT NULL", statement))
        want = {c["name"] for c in contract(name)["schema"] if c["nullable"] is False}
        assert not_null == want, name
        declared = re.findall(r"^\s+`(\w+)` ([A-Z<>]+)", statement, flags=re.MULTILINE)
        assert [(n, t.lower()) for n, t in declared] == contract_columns(name), name

    schema = peak_setup.feature_table_schema()
    contract_features = contract("ml_household_features_daily")["schema"]
    assert [(f.name, f.dataType.simpleString(), f.nullable) for f in schema.fields] == [
        (c["name"], c["type"], c["nullable"]) for c in contract_features
    ]


def test_ac64_ddl_properties_and_statement_order() -> None:
    settings = Settings()
    bronze = peak_setup.bronze_weather_ddl(settings)
    assert "smart_meter_dev.bronze.files_weather_hourly" in bronze
    assert "'delta.appendOnly' = 'true'" in bronze
    assert "delta.appendOnly" not in peak_setup.silver_weather_ddl(settings)
    labels_ddl = peak_setup.labels_ddl(settings)
    assert "'delta.logRetentionDuration' = 'interval 90 days'" in labels_ddl
    assert "'delta.deletedFileRetentionDuration' = 'interval 90 days'" in labels_ddl
    assert "`ineligibility_reasons` ARRAY<STRING>" in labels_ddl
    assert "smart_meter_dev.gold.consumption_spike_predictions" in peak_setup.predictions_ddl(
        settings
    )
    assert all(
        s.startswith("CREATE TABLE IF NOT EXISTS") for s in peak_setup.setup_statements(settings)
    )
    assert "interval 90 days" in peak_setup.feature_retention_sql(settings)
    fallback = Settings.fallback_layout()
    assert "workspace.smart_meter_dev_ml.household_labels_daily" in peak_setup.labels_ddl(fallback)


def test_ac64_schema_precondition_names_the_missing_schemas() -> None:
    def fake(names):
        return SimpleNamespace(sql=lambda statement: SimpleNamespace(collect=lambda: names))

    settings = Settings()
    peak_setup.require_schemas(
        fake([("bronze",), ("silver",), ("gold",), ("ml",), ("x",)]), settings
    )
    with pytest.raises(RuntimeError, match="ml.*smart_meter_dev"):
        peak_setup.require_schemas(fake([("bronze",), ("silver",), ("gold",)]), settings)


# ----------------------------------------------------------------------------- AC-66
@pytest.mark.parametrize(
    ("name", "keys"),
    [
        ("silver_weather_hourly", ["weather_ts"]),
        ("ml_household_features_daily", ["household_id", "feature_date"]),
        ("ml_household_labels_daily", ["household_id", "target_date"]),
    ],
)
def test_ac66_merge_updates_only_changed_rows_and_deletes_missing_keys(name, keys) -> None:
    columns = [c for c, _ in contract_columns(name)]
    sql = delta_sync.merge_sql("cat.s.target", "recomputed", keys, columns)

    assert sql.startswith("MERGE INTO cat.s.target AS t\nUSING recomputed AS s\nON ")
    on_clause = sql.split("ON ", 1)[1].split("\n", 1)[0]
    assert on_clause == " AND ".join(f"t.`{k}` = s.`{k}`" for k in keys)
    condition = re.search(r"WHEN MATCHED AND NOT \((.*)\) THEN UPDATE SET \*", sql).group(1)
    compared = re.findall(r"t\.`(\w+)` <=> s\.`\1`", condition)
    assert compared == [c for c in columns if c not in keys]  # every non-key column
    assert "WHEN NOT MATCHED THEN INSERT *" in sql
    assert sql.endswith("WHEN NOT MATCHED BY SOURCE THEN DELETE")


def test_ac66_merge_sql_rejects_bad_input_and_keys_only_tables_skip_the_update() -> None:
    with pytest.raises(ValueError, match="at least one key"):
        delta_sync.merge_sql("t", "s", [], ["a"])
    with pytest.raises(ValueError, match="not in the column list"):
        delta_sync.merge_sql("t", "s", ["k"], ["a"])
    with pytest.raises(ValueError, match="unsafe column name"):
        delta_sync.merge_sql("t", "s", ["k"], ["k", "a; DROP TABLE x"])
    assert "WHEN MATCHED" not in delta_sync.merge_sql("t", "s", ["k"], ["k"])


def test_ac66_merge_metrics_replace_where_and_properties_text() -> None:
    assert delta_sync.parse_merge_metrics(
        {"numTargetRowsInserted": "3", "numTargetRowsUpdated": "0", "numOutputRows": "9"}
    ) == {"inserted": 3, "updated": 0, "deleted": 0}
    assert delta_sync.replace_where_predicate(
        "target_date", date(2013, 12, 1), date(2014, 2, 27)
    ) == ("`target_date` >= DATE'2013-12-01' AND `target_date` <= DATE'2014-02-27'")
    with pytest.raises(ValueError, match="ends before"):
        delta_sync.replace_where_predicate("target_date", date(2014, 2, 27), date(2014, 2, 26))
    assert delta_sync.set_properties_sql("t", {"a.b": "it's", "c": "1"}) == (
        "ALTER TABLE t SET TBLPROPERTIES ('a.b' = 'it\\'s', 'c' = '1')"
    )
    with pytest.raises(ValueError, match="at least one"):
        delta_sync.set_properties_sql("t", {})


def checksum(spark, df, view: str):
    df.createOrReplaceTempView(view)
    row = spark.sql(metrics.table_checksum_sql(view, df.columns)).collect()[0]
    return row.row_count, row.checksum


def test_ac66_recomputation_with_another_partitioning_is_bitwise_equal(spark) -> None:
    fixture = pb.ac42_fixture()
    params = PeakParameters()
    bronze_rows = pb.hourly_weather_rows(date(2013, 1, 1), 5) + pb.hourly_weather_rows(
        date(2013, 1, 3), 2
    )  # overlapping days: duplicates with equal values, resolved by the tie-break
    builds = {}
    for partitions in (1, 7):

        def frame(maker, rows, n=partitions):
            return maker(spark, rows).repartition(n)

        households = frame(pb.household_frame, fixture.households)
        daily = frame(pb.daily_frame, fixture.daily)
        monthly = frame(pb.monthly_frame, fixture.monthly)
        silver = weather.silver_weather(frame(pb.weather_bronze_frame, bronze_rows)).frame
        hourly = frame(pb.silver_weather_frame, fixture.weather)
        builds[partitions] = {
            "silver": silver,
            "features": features.build_features(households, daily, hourly, params, pb.AC42_START),
            "labels": labels.build_labels(households, daily, monthly, params, pb.AC42_START),
        }
    for table in ("silver", "features", "labels"):
        one = checksum(spark, builds[1][table], f"one_{table}")
        seven = checksum(spark, builds[7][table], f"seven_{table}")
        assert one == seven
        assert one[0] > 0
    one_rows = sorted(tuple(r) for r in builds[1]["features"].collect())
    seven_rows = sorted(tuple(r) for r in builds[7]["features"].collect())
    assert one_rows == seven_rows  # equal values, not only equal hashes


# ----------------------------------------------------------------------------- names, parameters
def test_ac64_object_names_follow_the_layout() -> None:
    s = Settings()
    assert peak_config.bronze_weather_table(s) == "smart_meter_dev.bronze.files_weather_hourly"
    assert peak_config.silver_weather_table(s) == "smart_meter_dev.silver.weather_hourly"
    assert peak_config.features_table(s) == "smart_meter_dev.ml.household_features_daily"
    assert peak_config.labels_table(s) == "smart_meter_dev.ml.household_labels_daily"
    assert peak_config.predictions_table(s) == "smart_meter_dev.gold.consumption_spike_predictions"
    assert peak_config.model_name(s) == "smart_meter_dev.ml.consumption_spike_model"
    assert peak_config.weather_landing_path(s) == (
        "/Volumes/smart_meter_dev/bronze/landing/weather"
    )
    assert peak_config.weather_checkpoint(s) == (
        "/Volumes/smart_meter_dev/bronze/checkpoints/files_weather_hourly"
    )
    assert peak_config.experiment_path("me@x.org") == "/Users/me@x.org/smart_meter_peak_model"
    fallback = Settings.fallback_layout()
    assert (
        peak_config.model_name(fallback) == "workspace.smart_meter_dev_ml.consumption_spike_model"
    )


def test_ac63_parameters_default_parse_from_widgets_and_validate() -> None:
    defaults = PeakParameters()
    assert defaults.label_threshold == 1.3
    assert defaults.baseline_day_count == 4
    assert defaults.label_lookback_weeks == 8
    assert defaults.coverage_min == 0.80
    assert defaults.zero_share_max == 0.90
    assert defaults.eligibility_months == 3
    assert defaults.train_start == date(2012, 7, 29)
    assert defaults.test_end == date(2014, 2, 27)
    assert defaults.random_seed == 42

    widgets = {
        "label_threshold": "1.5",
        "coverage_min": "0.90",
        "target_date": "",
        "target_date_end": "",
        "random_seed": "7",
        "unrelated": "x",
    }
    parsed = PeakParameters.from_widgets(lambda name: widgets.get(name, ""))
    assert parsed.label_threshold == 1.5
    assert parsed.coverage_min == 0.90
    assert parsed.random_seed == 7
    assert parsed.target_date is None
    assert parsed.baseline_day_count == 4  # empty widget: default
    assert parsed.label_properties()["smart_meter.label_threshold"] == "1.5"
    with pytest.raises(ValueError, match="parameter label_threshold"):
        PeakParameters.from_mapping({"label_threshold": "high"})
    with pytest.raises(ValueError, match="not a date"):
        PeakParameters.from_mapping({"target_date": "2014-13-01"})
    with pytest.raises(ValueError, match="baseline_day_count must not exceed"):
        PeakParameters(baseline_day_count=5, label_lookback_weeks=4)


def test_ac63_baseline_day_count_above_lookback_weeks_is_rejected() -> None:
    """G-09: N baseline days can never be found in fewer than N weeks, so nothing would be labelled.

    Guards AC-63: the label parameters are job parameters, and a combination that silently labels
    nothing must stop the task before any table is touched.
    """
    with pytest.raises(ValueError, match=r"G-09.*baseline_day_count must not exceed"):
        PeakParameters(baseline_day_count=9)  # default lookback is 8 weeks
    with pytest.raises(ValueError, match=r"G-09.*baseline_day_count must not exceed"):
        PeakParameters.from_mapping({"baseline_day_count": "5", "label_lookback_weeks": "4"})
    equal = PeakParameters(baseline_day_count=6, label_lookback_weeks=6)  # boundary: allowed
    assert equal.baseline_day_count == equal.label_lookback_weeks
    assert PeakParameters(baseline_day_count=9, label_lookback_weeks=9).baseline_day_count == 9


def test_ac50_training_parameters_exclude_the_scoring_only_target_date() -> None:
    logged = PeakParameters(target_date=date(2014, 2, 28)).training_parameters()
    assert "target_date" not in logged
    assert "target_date_end" not in logged
    assert logged["random_seed"] == "42"
    assert logged["validation_end"] == "2013-11-30"


def test_ac63_label_parameters_round_trip_through_table_properties() -> None:
    params = PeakParameters(label_threshold=1.5, coverage_min=0.9, eligibility_months=2)
    parsed = peak_config.label_parameters_from_properties(params.label_properties())
    assert parsed == {
        "label_threshold": 1.5,
        "baseline_day_count": 4,
        "label_lookback_weeks": 8,
        "coverage_min": 0.9,
        "zero_share_max": 0.9,
        "eligibility_months": 2,
    }
    with pytest.raises(ValueError, match="lacks parameter properties"):
        peak_config.label_parameters_from_properties({})


def test_ac50_pinned_versions_are_checked_by_guard_g01() -> None:
    assert peak_config.PINNED_REQUIREMENTS == (
        "databricks-feature-engineering==0.18.2",
        "scikit-learn==1.3.0",
    )
    good = {"databricks-feature-engineering": "0.18.2", "scikit-learn": "1.3.0"}
    assert peak_config.check_versions(good) == good
    with pytest.raises(RuntimeError, match=r"G-01.*scikit-learn 1\.4\.0"):
        peak_config.check_versions(good | {"scikit-learn": "1.4.0"})
    with pytest.raises(RuntimeError, match="databricks-feature-engineering not installed"):
        peak_config.check_versions(good | {"databricks-feature-engineering": None})


def test_ac64_calendar_months_cover_partial_months() -> None:
    assert peak_config.calendar_months(date(2013, 8, 1), date(2013, 11, 30)) == [
        (2013, 8), (2013, 9), (2013, 10), (2013, 11),
    ]  # fmt: skip
    assert peak_config.calendar_months(date(2013, 12, 1), date(2014, 2, 27)) == [
        (2013, 12), (2014, 1), (2014, 2),
    ]  # fmt: skip
    assert len(peak_config.date_range(date(2013, 12, 1), date(2014, 2, 27))) == 89


def test_ac66_no_cache_or_persist_in_library_code_for_serverless() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "smart_meter_peak_prediction"
    offenders = [
        p.name
        for p in src.glob("*.py")
        if ".cache(" in p.read_text() or ".persist(" in p.read_text()
    ]
    assert offenders == []


def test_ac66_merge_metrics_ignore_an_earlier_merge_when_nothing_was_committed() -> None:
    class _Column:
        def __gt__(self, other):
            return True

        def desc(self):
            return self

    class History:
        def __init__(self, rows):
            self.rows = rows

        def where(self, expr):
            return self

        def __getitem__(self, name):
            return _Column()

        def orderBy(self, *a):  # noqa: N802
            return self

        def limit(self, n):
            return self

        def collect(self):
            return self.rows

    class Spark:
        def __init__(self, rows):
            self.rows = rows

        def sql(self, statement):
            return History(self.rows)

    # no MERGE newer than the version before the statement: zeros, not the earlier load
    assert delta_sync.last_merge_metrics(Spark([]), "t", after_version=5) == {
        "inserted": 0,
        "updated": 0,
        "deleted": 0,
    }
