"""Names, parameters and pinned versions of the peak model feature (FR-31, NFR-13, G-01, G-09).

``PeakParameters`` holds every FR-31 parameter with its default. It is built from job parameters
(widgets, always strings; an empty string means "use the default") and validated once (G-09), so a
bad value stops the task before any table is touched. Object names are built on top of the
existing ``Settings`` without changing it, so the main layout and the A-09 fallback layout use the
same code.

All dates are UTC calendar dates. Nothing here reads the session time zone.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import date, timedelta

from smart_meter_peak_prediction.config import LANDING_VOLUME, Settings

# ----------------------------------------------------------------------------- pinned versions
# ADR 0007: serverless keeps scikit-learn 1.3.0 and the FE client is installed by %pip.
PINNED_SKLEARN = "1.3.0"
PINNED_FEATURE_ENGINEERING = "0.18.2"
PINNED_REQUIREMENTS = (
    f"databricks-feature-engineering=={PINNED_FEATURE_ENGINEERING}",
    f"scikit-learn=={PINNED_SKLEARN}",
)
PINNED_PACKAGES = {
    "databricks-feature-engineering": PINNED_FEATURE_ENGINEERING,
    "scikit-learn": PINNED_SKLEARN,
}


def check_versions(installed: Mapping[str, str | None] | None = None) -> dict[str, str]:
    """G-01: fail unless the pinned ML libraries are installed. Returns the versions found.

    ``installed`` is for tests; by default the versions come from the environment.
    """
    found: dict[str, str | None] = {}
    for package in PINNED_PACKAGES:
        if installed is not None:
            found[package] = installed.get(package)
            continue
        try:
            found[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            found[package] = None
    wrong = [
        f"{package} {found[package] or 'not installed'} (expected {expected})"
        for package, expected in PINNED_PACKAGES.items()
        if found[package] != expected
    ]
    if wrong:
        raise RuntimeError("G-01 pinned library versions differ: " + "; ".join(wrong))
    return {package: str(version) for package, version in found.items()}


# ----------------------------------------------------------------------------- object names
BRONZE_WEATHER = "files_weather_hourly"
SILVER_WEATHER = "weather_hourly"
FEATURES = "household_features_daily"
LABELS = "household_labels_daily"
PREDICTIONS = "consumption_spike_predictions"
MODEL = "consumption_spike_model"
WEATHER_FOLDER = "weather"
EXPERIMENT = "smart_meter_peak_model"
CHAMPION_ALIAS = "champion"
THRESHOLD_TAG = "decision_threshold"

# Tables of METER_INGESTION that PEAK_MODEL reads (C-08).
GOLD_DAILY = "household_daily_consumption"
GOLD_MONTHLY = "household_data_quality_monthly"
SILVER_HOUSEHOLDS = "households"


def bronze_weather_table(settings: Settings) -> str:
    return settings.table("bronze", BRONZE_WEATHER)


def silver_weather_table(settings: Settings) -> str:
    return settings.table("silver", SILVER_WEATHER)


def features_table(settings: Settings) -> str:
    return settings.table("ml", FEATURES)


def labels_table(settings: Settings) -> str:
    return settings.table("ml", LABELS)


def predictions_table(settings: Settings) -> str:
    return settings.table("gold", PREDICTIONS)


def model_name(settings: Settings) -> str:
    return settings.table("ml", MODEL)


def gold_daily_table(settings: Settings) -> str:
    return settings.table("gold", GOLD_DAILY)


def gold_monthly_table(settings: Settings) -> str:
    return settings.table("gold", GOLD_MONTHLY)


def silver_households_table(settings: Settings) -> str:
    return settings.table("silver", SILVER_HOUSEHOLDS)


def weather_landing_path(settings: Settings) -> str:
    return settings.volume_path(LANDING_VOLUME, WEATHER_FOLDER)


def weather_checkpoint(settings: Settings) -> str:
    return settings.checkpoint(BRONZE_WEATHER)


def experiment_path(user: str) -> str:
    return f"/Users/{user}/{EXPERIMENT}"


# ----------------------------------------------------------------------------- table properties
PROPERTY_PREFIX = "smart_meter."
LABEL_PROPERTY_NAMES = (
    "label_threshold",
    "baseline_day_count",
    "label_lookback_weeks",
    "coverage_min",
    "zero_share_max",
    "eligibility_months",
)
FEATURE_PROPERTY_NAMES = ("baseline_day_count", "label_lookback_weeks")


# ----------------------------------------------------------------------------- parameters
def _parse_date(name: str, value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"parameter {name}: '{value}' is not a date (YYYY-MM-DD)") from exc


@dataclass(frozen=True)
class PeakParameters:
    label_threshold: float = 1.3
    baseline_day_count: int = 4
    label_lookback_weeks: int = 8
    coverage_min: float = 0.80
    zero_share_max: float = 0.90
    eligibility_months: int = 3
    train_start: date = date(2012, 7, 29)
    train_end: date = date(2013, 7, 31)
    validation_start: date = date(2013, 8, 1)
    validation_end: date = date(2013, 11, 30)
    test_start: date = date(2013, 12, 1)
    test_end: date = date(2014, 2, 27)
    random_seed: int = 42
    target_date: date | None = None  # scoring only (D-38)
    target_date_end: date | None = None  # scoring only: set for a backfill range

    def __post_init__(self) -> None:
        self.validate()

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> PeakParameters:
        """Build from job parameters; unknown keys are ignored, empty values use the default."""
        known = {f.name: f for f in fields(cls)}
        picked: dict[str, object] = {}
        for key, raw in values.items():
            if key not in known or raw is None or str(raw).strip() == "":
                continue
            text = str(raw).strip()
            kind = known[key].type
            try:
                if "float" in kind:
                    picked[key] = float(text)
                elif "int" in kind:
                    picked[key] = int(text)
                else:
                    picked[key] = _parse_date(key, text)
            except ValueError as exc:
                if str(exc).startswith("parameter "):
                    raise
                raise ValueError(f"parameter {key}: '{text}' is not a valid {kind}") from exc
        return cls(**picked)

    @classmethod
    def from_widgets(cls, get: Callable[[str], str]) -> PeakParameters:
        """Notebook entry: ``PeakParameters.from_widgets(dbutils.widgets.get)``."""
        return cls.from_mapping({f.name: get(f.name) for f in fields(cls)})

    # ------------------------------------------------------------------ G-09
    def validate(self) -> None:
        problems: list[str] = []
        if not self.label_threshold > 0:
            problems.append("label_threshold must be > 0")
        for name in ("coverage_min", "zero_share_max"):
            if not 0 < getattr(self, name) <= 1:
                problems.append(f"{name} must be in (0, 1]")
        for name in (
            "baseline_day_count",
            "label_lookback_weeks",
            "eligibility_months",
            "random_seed",
        ):
            if getattr(self, name) < 1:
                problems.append(f"{name} must be an integer >= 1")
        if self.baseline_day_count > self.label_lookback_weeks:
            problems.append("baseline_day_count must not exceed label_lookback_weeks")
        ranges = list(self.split_ranges().items())
        for name, (start, end) in ranges:
            if start > end:
                problems.append(f"{name} range starts after it ends ({start} > {end})")
        for (first, (_, first_end)), (second, (second_start, _)) in zip(
            ranges, ranges[1:], strict=False
        ):
            if first_end >= second_start:
                problems.append(
                    f"split ranges must be ordered and disjoint: {first} ends {first_end}, "
                    f"{second} starts {second_start}"
                )
        if self.target_date_end is not None:
            if self.target_date is None:
                problems.append("target_date_end needs target_date")
            elif self.target_date_end < self.target_date:
                problems.append("target_date_end must not be before target_date")
        if problems:
            raise ValueError("G-09 invalid parameters: " + "; ".join(problems))

    # ------------------------------------------------------------------ views
    def split_ranges(self) -> dict[str, tuple[date, date]]:
        return {
            "train": (self.train_start, self.train_end),
            "validation": (self.validation_start, self.validation_end),
            "test": (self.test_start, self.test_end),
        }

    def label_properties(self) -> dict[str, str]:
        """Table properties that record the label and eligibility parameters of a build."""
        return {
            PROPERTY_PREFIX + name: _property_text(getattr(self, name))
            for name in LABEL_PROPERTY_NAMES
        }

    def feature_properties(self) -> dict[str, str]:
        return {
            PROPERTY_PREFIX + name: _property_text(getattr(self, name))
            for name in FEATURE_PROPERTY_NAMES
        }

    def training_parameters(self) -> dict[str, str]:
        """FR-31 parameters a training run logs (D-38: every one except ``target_date``)."""
        names = [f.name for f in fields(self) if f.name not in ("target_date", "target_date_end")]
        return {name: _property_text(getattr(self, name)) for name in names}


def _property_text(value: object) -> str:
    return repr(value) if isinstance(value, float) else str(value)


def label_parameters_from_properties(properties: Mapping[str, str]) -> dict[str, float | int]:
    """Parse the label and eligibility parameters stored as table properties (FR-31)."""
    parsed: dict[str, float | int] = {}
    defaults = PeakParameters()
    missing = []
    for name in LABEL_PROPERTY_NAMES:
        text = properties.get(PROPERTY_PREFIX + name)
        if text is None:
            missing.append(PROPERTY_PREFIX + name)
            continue
        parsed[name] = type(getattr(defaults, name))(text)
    if missing:
        raise ValueError("labels table lacks parameter properties: " + ", ".join(missing))
    return parsed


# ----------------------------------------------------------------------------- calendar
def calendar_months(start: date, end: date) -> list[tuple[int, int]]:
    """Every calendar month ``(year, month)`` that has a day in ``[start, end]``."""
    months: list[tuple[int, int]] = []
    day = date(start.year, start.month, 1)
    while day <= end:
        months.append((day.year, day.month))
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return months


def date_range(start: date, end: date) -> list[date]:
    """Every UTC date from ``start`` to ``end`` inclusive."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
