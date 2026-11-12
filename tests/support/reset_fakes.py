"""Fakes for the reset guard tests (RESET_GUARD FR-113, DESIGN "Unit-test fakes").

``FakeClient`` stands in for the Databricks ``WorkspaceClient``: the Jobs API reads,
``warehouses.list`` and the Statement Execution calls are recorded in one shared call log; any
other attribute or method is recorded in ``forbidden`` and raises. No SDK is imported. Fake secrets
are built by concatenation so the repository hygiene scans stay clean.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

PEAK_ID = 101
TRAINING_ID = 102
INGESTION_ID = 103
DEV = "[dev someone] "
RUN_ID = 7
START_MS = 1762941600000  # 2025-11-12T10:00:00Z
START_TEXT = "2025-11-12T10:00:00Z"
WAREHOUSE_ID = "wh-1"

PEAK = "smart_meter_peak_model"
TRAINING = "smart_meter_peak_model_training"
INGESTION = "smart_meter_ingestion"

WEATHER = "smart_meter_dev.silver.weather_hourly"
FEATURES = "smart_meter_dev.ml.household_features_daily"
LABELS = "smart_meter_dev.ml.household_labels_daily"
BRONZE = "smart_meter_dev.bronze.files_weather_hourly"
TABLES = {WEATHER: 21165, FEATURES: 36480, LABELS: 36480, BRONZE: 21165}
DROPS = [f"DROP TABLE {table}" for table in (WEATHER, FEATURES, LABELS)]

DEFAULT_JOBS = [
    (PEAK_ID, DEV + PEAK),
    (TRAINING_ID, DEV + TRAINING),
    (INGESTION_ID, DEV + INGESTION),
]

_BANNED = ("https://", "http://", "dapi", "Bearer", "@")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\S*")


class ApiError(Exception):
    """Carries ``error_code`` as the SDK errors do."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PermissionDenied(ApiError):
    def __init__(self, message: str = "no access to the job") -> None:
        super().__init__(message, "PERMISSION_DENIED")


class NotFound(ApiError):
    def __init__(self, message: str = "does not exist") -> None:
        super().__init__(message, "RESOURCE_DOES_NOT_EXIST")


def run(
    state: Any = "RUNNING", run_id: int = RUN_ID, start_time: Any = START_MS
) -> SimpleNamespace:
    """A listed job run; ``state`` may be a string, an ``Enum`` member or ``None`` (missing)."""
    return SimpleNamespace(
        run_id=run_id, state=SimpleNamespace(life_cycle_state=state), start_time=start_time
    )


class _Api:
    """One API namespace; only ``allowed`` methods are available, every other call is forbidden."""

    def __init__(self, fake: FakeClient, name: str, allowed: tuple[str, ...]) -> None:
        self._fake = fake
        self._name = name
        self._allowed = allowed

    def __getattr__(self, method: str) -> Any:
        key = f"{self._name}.{method}"
        if method.startswith("_") or method not in self._allowed:
            self._fake.forbidden.append(key)
            raise AssertionError(f"forbidden call {key}")
        handler = getattr(self._fake, f"_do_{self._name}_{method}")

        def call(*args: Any, **kwargs: Any) -> Any:
            self._fake.called.append(key)
            override = self._fake.overrides.get(key)
            if isinstance(override, Exception):
                self._fake.log.append(self._fake._entry(key, args, kwargs))
                raise override
            if callable(override):
                self._fake.log.append(self._fake._entry(key, args, kwargs))
                return override(*args, **kwargs)
            return handler(*args, **kwargs)

        return call


class FakeClient:
    """Recording fake workspace client with a shared call log."""

    def __init__(
        self,
        *,
        jobs: list[tuple[int, str]] | None = None,
        runs: dict[int, Any] | None = None,
        sql: dict[str, Any] | None = None,
        warehouses: list[Any] | None = None,
        overrides: dict[str, Any] | None = None,
        enum_states: bool = False,
        log: list[str] | None = None,
    ) -> None:
        self.job_list = list(DEFAULT_JOBS if jobs is None else jobs)
        self.runs = dict(runs or {})
        self.sql = dict(sql or {})
        self.warehouse_list = (
            [SimpleNamespace(id=WAREHOUSE_ID)] if warehouses is None else list(warehouses)
        )
        self.overrides = dict(overrides or {})
        self.enum_states = enum_states
        self.log: list[str] = [] if log is None else log
        self.called: list[str] = []
        self.forbidden: list[str] = []
        self.pulled: dict[str, int] = {}
        self.waits: list[Any] = []
        self.jobs = _Api(self, "jobs", ("get", "list", "list_runs"))
        self.warehouses = _Api(self, "warehouses", ("list",))
        self.statement_execution = _Api(
            self, "statement_execution", ("execute_statement", "get_statement", "cancel_execution")
        )
        self._statements: dict[str, str] = {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        self.forbidden.append(name)
        raise AssertionError(f"forbidden attribute {name}")

    @staticmethod
    def _entry(key: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        if key == "jobs.list":
            if kwargs.get("name") is not None:
                return f"jobs.list(name={kwargs['name']})"
            return f"jobs.list(limit={kwargs.get('limit')})"
        if key in ("jobs.get", "jobs.list_runs"):
            return f"{key}({kwargs.get('job_id')})"
        if key == "warehouses.list":
            return key
        if key == "statement_execution.execute_statement":
            return f"sql:{kwargs.get('statement')}"
        return key

    def jobs_entries(self) -> list[str]:
        return [entry for entry in self.log if entry.startswith("jobs.")]

    def statements(self) -> list[str]:
        return [entry.removeprefix("sql:") for entry in self.log if entry.startswith("sql:")]

    def drops(self) -> list[str]:
        return [s for s in self.statements() if s.startswith("DROP")]

    def _counted(self, key: str, items: list[Any]) -> Iterator[Any]:
        self.pulled.setdefault(key, 0)
        for item in items:
            self.pulled[key] += 1
            yield item

    # ------------------------------------------------------------------ jobs
    def _do_jobs_list(self, **kwargs: Any) -> Any:
        self.log.append(self._entry("jobs.list", (), kwargs))
        name = kwargs.get("name")
        if name is not None:
            found = [SimpleNamespace(job_id=i) for i, deployed in self.job_list if deployed == name]
            return self._counted("jobs.list(name)", found)
        every = [
            SimpleNamespace(job_id=i, settings=SimpleNamespace(name=deployed))
            for i, deployed in self.job_list
        ]
        return self._counted("jobs.list", every)

    def _do_jobs_get(self, **kwargs: Any) -> Any:
        self.log.append(self._entry("jobs.get", (), kwargs))
        for job_id, deployed in self.job_list:
            if job_id == kwargs["job_id"]:
                return SimpleNamespace(job_id=job_id, settings=SimpleNamespace(name=deployed))
        raise NotFound(f"job {kwargs['job_id']} does not exist")

    def _do_jobs_list_runs(self, **kwargs: Any) -> Any:
        self.log.append(self._entry("jobs.list_runs", (), kwargs))
        listed = self.runs.get(kwargs["job_id"], [])
        if isinstance(listed, Exception):
            raise listed
        return self._counted(f"runs:{kwargs['job_id']}", list(listed))

    # ------------------------------------------------------------------ warehouses
    def _do_warehouses_list(self, **kwargs: Any) -> Any:
        self.log.append("warehouses.list")
        return list(self.warehouse_list)

    # ------------------------------------------------------------------ statements
    def _result(self, statement: str) -> Any:
        if statement in self.sql:
            return self.sql[statement]
        if statement == "SELECT current_timezone()":
            return "UTC"
        match = re.fullmatch(r"SELECT count\(\*\) FROM (\S+)", statement)
        if match and match.group(1) in TABLES:
            return TABLES[match.group(1)]
        return None

    def _state(self, text: str) -> Any:
        return SimpleNamespace(value=text) if self.enum_states else text

    def _response(self, statement: str, statement_id: str) -> Any:
        result = self._result(statement)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, str) and result.startswith("FAILED:"):
            error = SimpleNamespace(message=result.removeprefix("FAILED:"))
            status = SimpleNamespace(state=self._state("FAILED"), error=error)
            return SimpleNamespace(statement_id=statement_id, status=status, result=None)
        status = SimpleNamespace(state=self._state("SUCCEEDED"), error=None)
        data = None if result is None else SimpleNamespace(data_array=[[str(result)]])
        return SimpleNamespace(statement_id=statement_id, status=status, result=data)

    def _do_statement_execution_execute_statement(self, **kwargs: Any) -> Any:
        statement = kwargs["statement"]
        self.log.append(f"sql:{statement}")
        self.waits.append(kwargs.get("wait_timeout"))
        self._statements[f"st-{len(self._statements)}"] = statement
        return self._response(statement, f"st-{len(self._statements) - 1}")

    def _do_statement_execution_get_statement(self, statement_id: str) -> Any:
        self.log.append(f"statement_execution.get_statement({statement_id})")
        return self._response(self._statements[statement_id], statement_id)

    def _do_statement_execution_cancel_execution(self, statement_id: str) -> None:
        self.log.append(f"statement_execution.cancel_execution({statement_id})")


def factory(client: Any) -> Callable[[], Any]:
    return lambda: client


def raising_factory(exc: Exception) -> Callable[[], Any]:
    def build() -> Any:
        raise exc

    return build


def secret_error() -> RuntimeError:
    """An error whose first line holds a bearer token, a PAT, a URL and an address (NFR-53)."""
    bearer = "Bea" + "rer abc"
    pat = "da" + "pi123"
    url = "https" + "://example.invalid/x"
    address = "someone" + "@" + "example.invalid"
    return RuntimeError(f"denied {bearer} {pat} {url} {address}")


def no_secret(text: str) -> bool:
    """NFR-53: no host, URL, token, bearer or address in the text."""
    return not any(banned in text for banned in _BANNED)


def utc_only(text: str) -> bool:
    """NFR-55: every time-like token is ``YYYY-MM-DDTHH:MM:SSZ``."""
    return all(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", match.strip("),.;"))
        for match in _TIME.findall(text)
    )
