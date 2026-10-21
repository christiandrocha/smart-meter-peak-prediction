"""Builders and fixtures for the PEAK_MODEL tests: Gold rows, households, Bronze weather.

Dates are UTC calendar dates. Every fixture that states a number (AC-43, AC-45) states how it is
computed, and boundary values are built with the same double arithmetic the library uses
(``threshold * baseline``), so an exact tie is an exact tie.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from pyspark.sql import DataFrame, SparkSession

INGESTED = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
WEATHER_FILE = "/Volumes/c/bronze/landing/weather/weather_hourly_darksky.csv"

DAILY_DDL = (
    "household_id string, reading_date date, total_energy_kwh double, max_energy_kwh double, "
    "reading_count int, is_complete_day boolean"
)
MONTHLY_DDL = (
    "household_id string, has_household_record boolean, reading_month date, "
    "expected_readings int, observed_readings int, zero_readings int, gap_count int, "
    "first_reading_ts timestamp, last_reading_ts timestamp"
)
HOUSEHOLDS_DDL = (
    "household_id string, tariff string, acorn_category string, acorn_group string, "
    "source_block string, _ingested_at timestamp"
)


def day(offset: int, origin: date) -> date:
    return origin + timedelta(days=offset)


# ----------------------------------------------------------------------------- households
def household_row(household_id: str, acorn_group: str = "Affluent", tariff: str = "Std") -> dict:
    return {
        "household_id": household_id,
        "tariff": tariff,
        "acorn_category": "ACORN-E",
        "acorn_group": acorn_group,
        "source_block": "block_0",
        "_ingested_at": INGESTED,
    }


def household_frame(spark: SparkSession, rows: Iterable[dict]) -> DataFrame:
    return _frame(spark, list(rows), HOUSEHOLDS_DDL)


# ----------------------------------------------------------------------------- Gold daily
def daily_row(
    household_id: str, reading_date: date, total: float, *, complete: bool = True
) -> dict:
    return {
        "household_id": household_id,
        "reading_date": reading_date,
        "total_energy_kwh": total,
        "max_energy_kwh": total / 48 * 2,
        "reading_count": 48 if complete else 40,
        "is_complete_day": complete,
    }


def daily_series(
    household_id: str,
    start: date,
    days: int,
    total: Callable[[int], float] = lambda i: 10.0 + (i % 7),
    *,
    incomplete: Iterable[date] = (),
    missing: Iterable[date] = (),
) -> list[dict]:
    """``days`` consecutive Gold rows from ``start``; some days incomplete or without a row."""
    broken, absent = set(incomplete), set(missing)
    return [
        daily_row(household_id, d, total(i), complete=d not in broken)
        for i in range(days)
        if (d := start + timedelta(days=i)) not in absent
    ]


def daily_frame(spark: SparkSession, rows: Iterable[dict]) -> DataFrame:
    return _frame(spark, list(rows), DAILY_DDL)


# ----------------------------------------------------------------------------- Gold monthly
def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def next_month(first: date) -> date:
    return date(first.year + (first.month == 12), first.month % 12 + 1, 1)


def full_month_readings(first: date) -> int:
    return 48 * monthrange(first.year, first.month)[1]


def monthly_row(
    household_id: str,
    month: date,
    *,
    observed: int | None = None,
    zero: int = 0,
    expected: int | None = None,
    has_record: bool = True,
) -> dict:
    """One monthly quality row; defaults give a full month with no zero readings."""
    full = full_month_readings(month)
    return {
        "household_id": household_id,
        "has_household_record": has_record,
        "reading_month": month,
        "expected_readings": full if expected is None else expected,
        "observed_readings": full if observed is None else observed,
        "zero_readings": zero,
        "gap_count": 0,
        "first_reading_ts": None,
        "last_reading_ts": None,
    }


def monthly_series(household_id: str, first: date, last: date, **kwargs: int | None) -> list[dict]:
    """Dense monthly rows from the month of ``first`` to the month of ``last``."""
    rows = []
    month = month_start(first.year, first.month)
    while month <= last:
        rows.append(monthly_row(household_id, month, **kwargs))
        month = next_month(month)
    return rows


def monthly_frame(spark: SparkSession, rows: Iterable[dict]) -> DataFrame:
    return _frame(spark, list(rows), MONTHLY_DDL)


# ----------------------------------------------------------------------------- weather
def weather_bronze_row(
    time_raw: str | None,
    temperature_raw: str | None = "10.5",
    *,
    ingested_at: datetime = INGESTED,
    source_file: str = WEATHER_FILE,
    summary_raw: str = "Clear",
) -> dict:
    return {
        "time_raw": time_raw,
        "temperature_raw": temperature_raw,
        "apparent_temperature_raw": "9.0",
        "dew_point_raw": "5.0",
        "humidity_raw": "0.8",
        "pressure_raw": "1010.0",
        "visibility_raw": "10.0",
        "wind_bearing_raw": "200",
        "wind_speed_raw": "3.0",
        "precip_type_raw": "rain",
        "icon_raw": "clear-day",
        "summary_raw": summary_raw,
        "_rescued_data": None,
        "_source_file": source_file,
        "_ingested_at": ingested_at,
    }


def weather_ddl() -> str:
    from smart_meter_peak_prediction import weather

    return ", ".join(f"`{n}` {t}" for n, t in weather.BRONZE_COLUMNS.items())


def weather_bronze_frame(spark: SparkSession, rows: Iterable[dict]) -> DataFrame:
    return _frame(spark, list(rows), weather_ddl())


def hourly_weather_rows(
    first_day: date, days: int, temperature: Callable[[datetime], float] | None = None
) -> list[dict]:
    """24 Bronze rows per day from ``first_day``; temperature is a function of the instant."""
    pick = temperature or (lambda t: 5.0 + t.hour * 0.5 + (t.toordinal() % 5))
    rows = []
    start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC)
    for i in range(days * 24):
        moment = start + timedelta(hours=i)
        rows.append(weather_bronze_row(f"{moment:%Y-%m-%d %H:%M:%S}", f"{pick(moment):.3f}"))
    return rows


def silver_weather_frame(spark: SparkSession, rows: Iterable[tuple[datetime, float]]) -> DataFrame:
    data = [(moment, temperature, INGESTED) for moment, temperature in rows]
    return spark.createDataFrame(
        data, schema="weather_ts timestamp, temperature_c double, _ingested_at timestamp"
    )


def hourly_silver(
    first_day: date, days: int, skip_days: Iterable[date] = ()
) -> list[tuple[datetime, float]]:
    """Silver weather hours (24 per day) with a deterministic temperature; some days absent."""
    skipped = set(skip_days)
    rows = []
    for i in range(days):
        d = first_day + timedelta(days=i)
        if d in skipped:
            continue
        for hour in range(24):
            moment = datetime(d.year, d.month, d.day, hour, tzinfo=UTC)
            rows.append((moment, 4.0 + 0.1 * hour + (d.toordinal() % 7) * 0.37))
    return rows


# ----------------------------------------------------------------------------- AC-42 fixture
AC42_START = date(2013, 1, 1)
AC42_DAYS = 70
AC42_TARGET = date(2013, 3, 1)  # T; Gold from T, months ending on or after T and weather from T


@dataclass
class Ac42:
    households: list[dict]
    daily: list[dict]
    monthly: list[dict]
    weather: list[tuple[datetime, float]]


def ac42_fixture(*, altered: bool = False) -> Ac42:
    """2 households over 70 days; ``altered`` replaces everything dated T or later.

    Replaced: Gold rows with ``reading_date >= T``, monthly rows of months ending on or after T,
    and weather hours at or after T 00:00Z. The days before T have an incomplete day and a missing
    day so that the baseline and the averages are exercised.
    """
    households = [household_row("H1", "Affluent", "Std"), household_row("H2", "Adversity", "ToU")]
    end = AC42_START + timedelta(days=AC42_DAYS - 1)
    daily: list[dict] = []
    for n, hid in enumerate(("H1", "H2")):
        rows = daily_series(
            hid,
            AC42_START,
            AC42_DAYS,
            lambda i, n=n: 8.0 + n * 3 + (i % 7) * 1.5 + (i % 3) * 0.25,
            incomplete=[date(2013, 1, 20 + n)],
            missing=[date(2013, 2, 3 + n)],
        )
        for row in rows:
            if altered and row["reading_date"] >= AC42_TARGET:
                row["total_energy_kwh"] = row["total_energy_kwh"] * 7.0 + 100.0
                row["max_energy_kwh"] = row["max_energy_kwh"] * 7.0
                row["is_complete_day"] = not row["is_complete_day"]
        daily += rows
    monthly: list[dict] = []
    for hid in ("H1", "H2"):
        for month in monthly_series(hid, date(2012, 10, 1), end):
            last_day = date(month["reading_month"].year, month["reading_month"].month, 1)
            last_day = next_month(last_day) - timedelta(days=1)
            if altered and last_day >= AC42_TARGET:
                month["observed_readings"] = 10
                month["zero_readings"] = 9
            monthly.append(month)
    weather = hourly_silver(AC42_START, AC42_DAYS)
    if altered:
        cut = datetime(2013, 3, 1, tzinfo=UTC)
        weather = [(m, t + 50.0 if m >= cut else t) for m, t in weather]
    return Ac42(households, daily, monthly, weather)


# ----------------------------------------------------------------------------- AC-43 fixture
AC43_T = date(2013, 3, 5)  # a Tuesday
AC43_START = date(2012, 12, 1)
AC43_BASE = [10.1, 12.3, 9.7, 11.9]  # totals of T - 7, T - 14, T - 21, T - 28
LABEL_THRESHOLD = 1.3


def median4(values: list[float]) -> float:
    """Median of four values with the arithmetic the library uses: (a + b) / 2.0."""
    ordered = sorted(values)
    return (ordered[1] + ordered[2]) / 2.0


@dataclass
class Ac43:
    households: list[dict]
    daily: list[dict]
    expected: dict[str, tuple[int | None, float | None, int]]  # id -> label, baseline, day count


def ac43_fixture() -> Ac43:
    """Six cases, one household each; the target date is ``AC43_T`` for all of them."""
    baseline = median4(AC43_BASE)
    rows: dict[str, list[dict]] = {}

    def weekly(hid: str, offsets_totals: dict[int, float], incomplete_weeks: Iterable[int] = ()):
        """Same-weekday days T - 7k (k = weeks back) with the given totals."""
        broken = set(incomplete_weeks)
        rows[hid] = [
            daily_row(hid, AC43_T - timedelta(days=7 * k), total, complete=k not in broken)
            for k, total in offsets_totals.items()
        ]

    def target(hid: str, total: float, *, complete: bool = True) -> None:
        rows[hid].append(daily_row(hid, AC43_T, total, complete=complete))

    four = dict(zip((1, 2, 3, 4), AC43_BASE, strict=True))
    older = {5: 100.0, 6: 100.0, 7: 100.0, 8: 100.0}  # must not enter the median
    # 1 exactly at the bound: T = 1.3 x baseline with the same double arithmetic -> 0
    weekly("C1", four | older)
    target("C1", LABEL_THRESHOLD * baseline)
    # 2 just above the bound -> 1
    weekly("C2", four | older)
    target("C2", LABEL_THRESHOLD * baseline + 0.001)
    # 3 T incomplete -> null
    weekly("C3", four | older)
    target("C3", 99.0, complete=False)
    # 4 only 3 complete same-weekday days in 8 weeks (the 4th is incomplete) -> null
    weekly("C4", {1: 10.1, 2: 12.3, 3: 9.7, 4: 11.9}, incomplete_weeks=[4])
    target("C4", 99.0)
    # 5 the fourth complete same-weekday day lies 9 weeks back -> null
    weekly("C5", {1: 10.1, 2: 12.3, 3: 9.7, 9: 11.9})
    target("C5", 99.0)
    # 6 T - 7 is incomplete: the baseline uses T - 14 to T - 35 (next older complete days) -> 1
    weekly("C6", {1: 99.0, 2: 10.1, 3: 12.3, 4: 9.7, 5: 11.9, 6: 100.0}, incomplete_weeks=[1])
    target("C6", LABEL_THRESHOLD * baseline + 5.0)

    expected = {
        "C1": (0, baseline, 4),
        "C2": (1, baseline, 4),
        "C3": (None, baseline, 4),
        "C4": (None, None, 3),
        "C5": (None, None, 3),
        "C6": (1, baseline, 4),
    }
    ids = list(expected)
    households = [household_row(hid) for hid in ids]
    return Ac43(households, [r for hid in ids for r in rows[hid]], expected)


# ----------------------------------------------------------------------------- AC-45 fixture
AC45_STUDY_START = date(2012, 7, 1)
AC45_LAST_DAY = date(2013, 1, 31)


@dataclass
class Ac45:
    households: list[dict]
    daily: list[dict]
    monthly: list[dict]


def ac45_fixture() -> Ac45:
    """Households for the eligibility cases of AC-45 (monthly rows are the only input that matters).

    - ``FULL``: every study month full and clean.
    - ``LATE``: first reading on 2012-10-15; July to September have 0 observed readings and
      October has 17 days. The window of 2013-01-xx is October to December: 78 / 92 days.
    - ``DEAD``: full coverage, zero share 0.95.
    - ``COV80`` and ``COV7999``: coverage exactly 0.80 and 0.7999 (expected 10,000 per month).
    - ``ZERO90``: zero share exactly 0.90 (expected 1,000 per month).
    """
    ids = ["FULL", "LATE", "DEAD", "COV80", "COV7999", "ZERO90"]
    last = date(2013, 1, 1)
    monthly: list[dict] = []
    monthly += monthly_series("FULL", AC45_STUDY_START, last)
    for month in monthly_series("LATE", AC45_STUDY_START, last):
        first = month["reading_month"]
        if first < date(2012, 10, 1):
            month["observed_readings"] = 0
        elif first == date(2012, 10, 1):
            month["observed_readings"] = 48 * 17
        monthly.append(month)
    for month in monthly_series("DEAD", AC45_STUDY_START, last):
        month["zero_readings"] = round(month["observed_readings"] * 0.95)
        monthly.append(month)
    monthly += monthly_series("COV80", AC45_STUDY_START, last, expected=10000, observed=8000)
    monthly += monthly_series("COV7999", AC45_STUDY_START, last, expected=10000, observed=7999)
    monthly += monthly_series(
        "ZERO90", AC45_STUDY_START, last, expected=1000, observed=1000, zero=900
    )
    daily = [daily_row(hid, AC45_LAST_DAY, 10.0) for hid in ids]
    return Ac45([household_row(hid) for hid in ids], daily, monthly)


# ----------------------------------------------------------------------------- shared
def _frame(spark: SparkSession, rows: list[dict], ddl: str) -> DataFrame:
    names = [part.strip().split(" ")[0].strip("`") for part in ddl.split(",")]
    return spark.createDataFrame([tuple(row.get(n) for n in names) for row in rows], schema=ddl)
