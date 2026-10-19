"""Wiring of ``pipelines/meter_pipeline.py`` against the rule catalog (AC-12, AC-26, DA-01, DA-07).

The pipeline file is run with a recording fake ``dlt`` module and a fake ``spark`` whose
configuration is the one the bundle sets. The recorded datasets are compared with ``rules.py``;
a second fixture runs every recorded dataset function in pipeline order over real Bronze tables
on local Spark (fully qualified names in the ``spark_catalog`` catalog), applies the recorded
expectations and checks the result against the local harness.
"""

from __future__ import annotations

import runpy
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from support import builders as b
from support.harness import ROOT, rows, run_update, summary_select_sql

from smart_meter_peak_prediction import metrics, rules
from smart_meter_peak_prediction.config import Settings

PIPELINE = ROOT / "pipelines" / "meter_pipeline.py"
SUMMARY_SQL = ROOT / "pipelines" / "household_data_quality.sql"
LOCAL = Settings(
    catalog="spark_catalog",
    bronze_schema="wiring_bronze",
    silver_schema="wiring_silver",
    gold_schema="wiring_gold",
    ml_schema="wiring_ml",
)


@dataclass
class Dataset:
    name: str
    private: bool
    kwargs: dict
    fn: object
    warn: dict = field(default_factory=dict)
    fail: dict = field(default_factory=dict)


class FakeDlt(types.ModuleType):
    """Records ``@dlt.table`` and the expectation decorators in application order."""

    def __init__(self) -> None:
        super().__init__("dlt")
        self.datasets: list[Dataset] = []
        self.reads: list[str] = []
        self._pending: dict[int, dict] = {}
        self.results: dict[str, object] = {}

    def _remember(self, fn, kind: str, expectations: dict):
        self._pending.setdefault(id(fn), {}).setdefault(kind, {}).update(expectations)
        return fn

    def expect_all(self, expectations: dict):
        return lambda fn: self._remember(fn, "warn", expectations)

    def expect_all_or_fail(self, expectations: dict):
        return lambda fn: self._remember(fn, "fail", expectations)

    def table(self, *, name: str, private: bool = False, **kwargs):
        def decorate(fn):
            pending = self._pending.pop(id(fn), {})
            self.datasets.append(
                Dataset(name, private, kwargs, fn, pending.get("warn", {}), pending.get("fail", {}))
            )
            return fn

        return decorate

    def read(self, name: str):
        self.reads.append(name)
        return self.results[name]


class FakeConf:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, key: str, default: str | None = None) -> str:
        if key in self.values:
            return self.values[key]
        if default is None:
            raise KeyError(key)
        return default


class FakeSpark:
    """Pipeline-runtime ``spark``: configuration from a dict, everything else from a session."""

    def __init__(self, conf: dict[str, str], session=None) -> None:
        self.conf = FakeConf(conf)
        self._session = session

    def __getattr__(self, name: str):
        if self._session is None:
            raise AttributeError(name)
        return getattr(self._session, name)


def bundle_conf(settings: Settings, tz: str = "UTC") -> dict[str, str]:
    conf = {"spark.sql.session.timeZone": tz}
    conf.update(settings.to_pipeline_configuration())
    return conf


def load_pipeline(monkeypatch, settings: Settings, session=None, tz: str = "UTC") -> FakeDlt:
    fake = FakeDlt()
    monkeypatch.setitem(sys.modules, "dlt", fake)
    runpy.run_path(
        str(PIPELINE),
        init_globals={"spark": FakeSpark(bundle_conf(settings, tz), session)},
    )
    return fake


@pytest.fixture
def recorded(monkeypatch) -> FakeDlt:
    return load_pipeline(monkeypatch, Settings())


def by_name(dlt: FakeDlt) -> dict[str, Dataset]:
    return {d.name: d for d in dlt.datasets}


def test_ac26_pipeline_defines_all_silver_and_gold_objects(recorded: FakeDlt) -> None:
    s = Settings()
    datasets = by_name(recorded)
    published = {
        s.table("silver", "meter_readings_evaluated"),
        s.table("silver", "meter_readings"),
        s.table("silver", "meter_readings_quarantine"),
        s.table("silver", "households"),
        s.table("gold", "household_daily_consumption"),
        s.table("gold", "household_data_quality_monthly"),
    }
    private = {
        "households_checked",
        "daily_consumption_orphan_check",
        "household_data_quality_check",
    }
    assert {d.name for d in recorded.datasets if not d.private} == published
    assert {d.name for d in recorded.datasets if d.private} == private
    assert len(recorded.datasets) == len(published) + len(private)
    # Every dataset is a batch ``@dlt.table`` (a materialized view): no streaming table and no
    # streaming read anywhere in the pipeline source.
    source = PIPELINE.read_text(encoding="utf-8")
    assert "readStream" not in source
    assert "dlt.read_stream" not in source
    assert "dlt.view" not in source
    for name in published:
        assert not datasets[name].private
    # The persisted summary view comes from the SQL file, not from a Python dataset.
    assert s.table("gold", "household_data_quality") not in datasets
    # Liquid clustering of the large tables (DESIGN, Data Model).
    assert datasets[s.table("silver", "meter_readings")].kwargs["cluster_by"] == [
        "household_id",
        "reading_date",
    ]
    assert datasets[s.table("gold", "household_data_quality_monthly")].kwargs["cluster_by"] == [
        "household_id"
    ]


def test_ac12_pipeline_expectations_match_rule_catalog(recorded: FakeDlt) -> None:
    s = Settings()
    datasets = by_name(recorded)
    evaluated = datasets[s.table("silver", rules.EVALUATED)]
    # DA-01 fallback: the evaluation dataset is published (fully qualified, not private).
    assert not evaluated.private
    assert evaluated.name == "smart_meter_dev.silver.meter_readings_evaluated"
    assert evaluated.warn == rules.expect_all(rules.EVALUATED, s)
    assert evaluated.fail == rules.expect_all_or_fail(rules.EVALUATED, s)
    # Counters of every drop rule and SF-01, QR-08 and QR-09 are warn expectations on it;
    # QR-01, QR-06 and INV-01 fail.
    for rule_id in ("SF-01", "QR-02", "QR-03", "QR-04", "QR-05", "QR-07", "QR-08", "QR-09"):
        assert rules.rule_by_id(rule_id).name in evaluated.warn, rule_id
    for rule_id in ("QR-01", "QR-06", "INV-01"):
        assert rules.rule_by_id(rule_id).name in evaluated.fail, rule_id
    assert not set(evaluated.warn) & set(evaluated.fail)

    # Every attached rule of the catalog is on exactly the dataset the catalog names.
    attached = {(d_key, r.name, r.attach) for r in rules.RULES if r.attach for d_key in [r.dataset]}
    recorded_pairs = set()
    short_of = {
        s.table("silver", rules.EVALUATED): rules.EVALUATED,
        s.table("silver", rules.QUARANTINE): rules.QUARANTINE,
        s.table("silver", rules.HOUSEHOLDS): rules.HOUSEHOLDS,
        s.table("gold", rules.DAILY): rules.DAILY,
        s.table("gold", rules.MONTHLY): rules.MONTHLY,
    }
    for d in recorded.datasets:
        key = short_of.get(d.name, d.name)
        recorded_pairs |= {(key, n, "warn") for n in d.warn}
        recorded_pairs |= {(key, n, "fail") for n in d.fail}
    assert recorded_pairs == attached


def test_pipeline_fails_when_a_required_configuration_key_is_missing(monkeypatch) -> None:
    conf = bundle_conf(Settings())
    del conf["smart_meter.catalog"]
    fake = FakeDlt()
    monkeypatch.setitem(sys.modules, "dlt", fake)
    with pytest.raises(KeyError):
        runpy.run_path(str(PIPELINE), init_globals={"spark": FakeSpark(conf)})


def test_da07_pipeline_asserts_session_time_zone_is_utc(monkeypatch) -> None:
    load_pipeline(monkeypatch, Settings(), tz="UTC")
    with pytest.raises(AssertionError, match="UTC"):
        load_pipeline(monkeypatch, Settings(), tz="Europe/Berlin")


def test_pipeline_configuration_drives_settings_and_src_path(monkeypatch) -> None:
    custom = Settings(catalog="workspace", silver_schema="smart_meter_dev_silver")
    fake = load_pipeline(monkeypatch, custom)
    assert {d.name for d in fake.datasets if not d.private} >= {
        "workspace.smart_meter_dev_silver.meter_readings_evaluated"
    }


# ----------------------------------------------------------------------------- end to end
class ExpectationFailure(Exception):  # noqa: N818
    pass


def apply_expectations(session, dataset: Dataset, df) -> None:
    from pyspark.sql import functions as F

    for predicates, action in ((dataset.warn, "warn"), (dataset.fail, "fail")):
        for name, predicate in predicates.items():
            failed = df.where(~F.coalesce(F.expr(predicate), F.lit(False))).count()
            if failed and action == "fail":
                raise ExpectationFailure(f"{dataset.name}: {name}")


def run_pipeline_locally(session, dlt: FakeDlt) -> dict[str, object]:
    """Run each recorded dataset function in definition order, as one pipeline update."""
    session.sql(f"CREATE DATABASE IF NOT EXISTS {LOCAL.schema('gold')}")
    for dataset in dlt.datasets:
        if dataset.name == "household_data_quality_check":
            # The persisted view of the SQL file (full CREATE VIEW statement) exists by now.
            text = SUMMARY_SQL.read_text(encoding="utf-8")
            text = text.replace("${smart_meter.catalog}", LOCAL.catalog)
            text = text.replace("${smart_meter.gold_schema}", LOCAL.gold_schema)
            session.sql("DROP VIEW IF EXISTS spark_catalog.wiring_gold.household_data_quality")
            session.sql(text.strip().rstrip(";"))
        df = dataset.fn()
        apply_expectations(session, dataset, df)
        if dataset.private:
            dlt.results[dataset.name] = df
        else:
            df.write.mode("overwrite").saveAsTable(dataset.name)
    return dlt.results


@pytest.fixture
def wired_session(spark):
    for layer in ("bronze", "silver", "gold"):
        spark.sql(f"DROP DATABASE IF EXISTS {LOCAL.schema(layer)} CASCADE")
        spark.sql(f"CREATE DATABASE {LOCAL.schema(layer)}")
    yield spark
    for layer in ("bronze", "silver", "gold"):
        spark.sql(f"DROP DATABASE IF EXISTS {LOCAL.schema(layer)} CASCADE")


def save_bronze(spark, files, kafka, households) -> None:
    b.bronze_files(spark, files).write.saveAsTable(LOCAL.bronze_files_readings)
    b.bronze_kafka(spark, kafka).write.saveAsTable(LOCAL.bronze_kafka_readings)
    b.bronze_households(spark, households).write.saveAsTable(LOCAL.bronze_files_households)


def test_ac12_wired_pipeline_matches_harness_and_totals_come_from_published_table(
    spark, wired_session, monkeypatch
) -> None:
    """DA-01: counts are table totals over the published evaluation table, as the harness gives."""
    files, kafka = b.mixed_fixture()
    households = [b.household_row("MAC000001"), b.household_row("MAC000002", tariff="ToU")]
    save_bronze(spark, files, kafka, households)

    dlt = load_pipeline(monkeypatch, LOCAL, session=spark)
    run_pipeline_locally(spark, dlt)

    published = LOCAL.table("silver", rules.EVALUATED)
    wired = spark.sql(metrics.rule_counts_sql(published)).collect()[0].asDict()
    expected = run_update(
        spark,
        LOCAL,
        b.bronze_files(spark, files),
        b.bronze_kafka(spark, kafka),
        b.bronze_households(spark, households),
    )
    from support.harness import totals

    assert wired == totals(expected)
    assert wired["evaluated_rows"] == len(files) + len(kafka)
    assert wired["quarantine_rows"] == spark.table(LOCAL.table("silver", rules.QUARANTINE)).count()
    assert wired["silver_rows"] == spark.table(LOCAL.table("silver", "meter_readings")).count()
    # Gold and the summary view come out of the same wiring.
    assert spark.table(LOCAL.table("gold", rules.DAILY)).count() == expected.daily.count()
    assert spark.table(LOCAL.table("gold", rules.MONTHLY)).count() == expected.monthly.count()
    assert "households_checked" in dlt.results
    assert "household_data_quality_check" in dlt.results


def test_ac15_wired_fail_rule_aborts_the_update(spark, wired_session, monkeypatch) -> None:
    """A QR-01 violation (malformed household id) raises in the wired expectations."""
    files = [b.file_row("MAC12345", moment=b.T_FILES)]
    save_bronze(spark, files, [], [b.household_row("MAC000001")])
    dlt = load_pipeline(monkeypatch, LOCAL, session=spark)
    with pytest.raises(ExpectationFailure, match="qr_01_household_id_shape"):
        run_pipeline_locally(spark, dlt)
    assert not spark.catalog.tableExists(LOCAL.table("silver", "meter_readings"))


# ----------------------------------------------------------------------------- summary view
def test_ac25_summary_create_view_statement_runs_and_matches_select_body(
    spark, wired_session
) -> None:
    """I-17: the full ``CREATE VIEW`` statement (not only its SELECT body) is valid SQL."""
    text = SUMMARY_SQL.read_text(encoding="utf-8")
    assert (
        "CREATE VIEW ${smart_meter.catalog}.${smart_meter.gold_schema}.household_data_quality"
        in text
    )
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    assert code.count("${") == code.count("${smart_meter.")  # only pipeline configuration keys
    files = b.day_rows("MAC000001", b.T_FILES, count=40)
    households = [b.household_row("MAC000001")]
    save_bronze(spark, files, [], households)
    update = run_update(
        spark,
        LOCAL,
        b.bronze_files(spark, files),
        b.bronze_kafka(spark),
        b.bronze_households(spark, households),
    )
    update.monthly.write.saveAsTable(LOCAL.table("gold", rules.MONTHLY))
    statement = text.replace("${smart_meter.catalog}", LOCAL.catalog).replace(
        "${smart_meter.gold_schema}", LOCAL.gold_schema
    )
    spark.sql(statement.strip().rstrip(";"))
    view = spark.table(LOCAL.table("gold", "household_data_quality"))
    select_body = spark.sql(summary_select_sql(LOCAL.catalog, LOCAL.gold_schema))
    assert rows(view.orderBy("household_id")) == rows(select_body.orderBy("household_id"))
    assert view.count() == 1


def test_ac26_summary_sql_is_a_pipeline_library_and_names_match_contract() -> None:
    import yaml

    pipeline = yaml.safe_load(
        (ROOT / "resources" / "smart_meter_silver_gold.pipeline.yml").read_text(encoding="utf-8")
    )["resources"]["pipelines"]["smart_meter_silver_gold"]
    paths = [Path(lib["file"]["path"]).name for lib in pipeline["libraries"]]
    assert "household_data_quality.sql" in paths
    assert "meter_pipeline.py" in paths
    contract = yaml.safe_load(
        (ROOT / "docs" / "contracts" / "gold_household_data_quality.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert "household_data_quality" in str(contract.get("name", contract))
    # The substitution keys the SQL file uses are set by the bundle pipeline configuration.
    for key in ("smart_meter.catalog", "smart_meter.gold_schema"):
        assert key in pipeline["configuration"]
