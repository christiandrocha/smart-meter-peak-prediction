"""Replay producer: publishes the stream sample file to Kafka (topic contract meter-readings).

Reads ``readings_stream.csv`` (source header ``LCLid,tstp,energy(kWh/hh)``), builds one event
per row as defined in ``docs/contracts/meter-readings.yaml`` and publishes it keyed by
``household_id`` in event-time order. Rows are never dropped: a non-numeric energy becomes
``null`` and a timestamp that does not parse is passed through as raw text, so that the
pipeline decides and counts (QR-02, QR-04).

Credentials come from environment variables only (a git-ignored ``.env`` passed with
``docker run --env-file .env``). Nothing here prints, logs or stores their values.

  python -m smart_meter_peak_prediction.producer --dry-run --input readings_stream.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_TOPIC = "meter-readings"
DEFAULT_MECHANISM = "SCRAM-SHA-256"
SOURCE = "replay"
REQUIRED_ENV = ("KAFKA_BOOTSTRAP", "KAFKA_USERNAME", "KAFKA_PASSWORD", "KAFKA_CA_PATH")
SOURCE_HEADER = ("LCLid", "tstp", "energy(kWh/hh)")
_TS_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


class ProducerConfigError(ValueError):
    """Missing or invalid configuration. Messages name variables, never values."""


class DeliveryError(RuntimeError):
    """At least one message was not delivered."""


@dataclass(frozen=True)
class Reading:
    """One input row after parsing. ``ts`` is None when the source text does not parse."""

    household_id: str
    ts_raw: str
    ts: datetime | None
    energy_raw: str


# ----------------------------------------------------------------------------- parsing
def parse_ts(raw: str) -> datetime | None:
    """Parse a source timestamp (``2013-12-01 00:30:00.0000000``) as UTC, or None."""
    text = raw.strip()
    # Python's %f accepts at most 6 digits; the source has 7 (always zeros in the dataset).
    head, dot, frac = text.partition(".")
    if dot:
        if not frac.isdigit() or frac[6:].strip("0"):
            return None
        text = f"{head}.{frac[:6]}"
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def format_ts(ts: datetime) -> str:
    """ISO-8601 UTC with a Z suffix, e.g. 2013-12-01T00:30:00Z."""
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_energy(raw: str | None) -> float | None:
    """A finite float, or None when the value is not numeric (e.g. the literal 'Null')."""
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_stream(path: Path) -> list[Reading]:
    """Read the stream file with the source header and sort by (reading_ts, household_id).

    Rows whose timestamp does not parse sort after the parsed ones, by raw text.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(header) != SOURCE_HEADER:
            raise ProducerConfigError(f"unexpected header in {path.name}: {header}")
        rows = []
        for n, r in enumerate(reader, start=2):
            if not r:
                continue  # blank line
            if len(r) != 3:
                raise ProducerConfigError(f"{path.name} line {n}: expected 3 fields")
            rows.append(Reading(r[0], r[1], parse_ts(r[1]), r[2]))
    rows.sort(
        key=lambda r: (
            r.ts is None,
            r.ts or datetime.min.replace(tzinfo=UTC),
            r.ts_raw if r.ts is None else "",
            r.household_id,
        )
    )
    return rows


def build_event(reading: Reading, produced_at: datetime | None = None) -> dict[str, Any]:
    """The value of one message, matching the topic contract schema."""
    now = (produced_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "household_id": reading.household_id,
        "reading_ts": format_ts(reading.ts) if reading.ts is not None else reading.ts_raw,
        "energy_kwh": parse_energy(reading.energy_raw),
        "source": SOURCE,
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def encode_event(event: Mapping[str, Any]) -> str:
    return json.dumps(event, separators=(",", ":"), allow_nan=False)


# ----------------------------------------------------------------------------- settings
@dataclass(frozen=True)
class Settings:
    topic: str
    replay_speed: float
    stream_file: Path | None


def read_settings(env: Mapping[str, str]) -> Settings:
    """Non-secret settings from the environment; empty values fall back to defaults."""
    speed_text = env.get("REPLAY_SPEED", "").strip() or "0"
    try:
        speed = float(speed_text)
    except ValueError as exc:
        raise ProducerConfigError("REPLAY_SPEED must be a number") from exc
    if speed < 0 or not math.isfinite(speed):
        raise ProducerConfigError("REPLAY_SPEED must be >= 0")
    stream = env.get("SAMPLE_STREAM_FILE", "").strip()
    return Settings(
        topic=env.get("KAFKA_TOPIC", "").strip() or DEFAULT_TOPIC,
        replay_speed=speed,
        stream_file=Path(stream) if stream else None,
    )


def build_kafka_config(env: Mapping[str, str]) -> dict[str, Any]:
    """confluent-kafka configuration from environment variables only (AC-29)."""
    missing = [name for name in REQUIRED_ENV if not env.get(name, "").strip()]
    if missing:
        raise ProducerConfigError(f"missing environment variables: {', '.join(missing)}")
    return {
        "bootstrap.servers": env["KAFKA_BOOTSTRAP"].strip(),
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": env.get("KAFKA_SASL_MECHANISM", "").strip() or DEFAULT_MECHANISM,
        "sasl.username": env["KAFKA_USERNAME"],
        "sasl.password": env["KAFKA_PASSWORD"],
        "ssl.ca.location": env["KAFKA_CA_PATH"].strip(),
        "enable.idempotence": True,
        "acks": "all",
    }


# ----------------------------------------------------------------------------- replay
def paced(
    readings: Iterable[Reading],
    speed: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[Reading]:
    """Yield readings, waiting so that ``speed`` event seconds pass per wall-clock second.

    ``speed == 0`` means no pacing. Rows without a parsed timestamp are never delayed.
    """
    first: datetime | None = None
    started = clock()
    for reading in readings:
        if speed > 0 and reading.ts is not None:
            first = first or reading.ts
            due = (reading.ts - first).total_seconds() / speed
            wait = due - (clock() - started)
            if wait > 0:
                sleep(wait)
        yield reading


def dry_run(readings: Iterable[Reading], out: Any, limit: int | None = None) -> int:
    count = 0
    for reading in readings:
        if limit is not None and count >= limit:
            break
        out.write(encode_event(build_event(reading)) + "\n")
        count += 1
    return count


def publish(
    readings: Iterable[Reading],
    producer: Any,
    topic: str,
    limit: int | None = None,
    flush_timeout: float = 120.0,
) -> int:
    """Publish keyed by household_id; raise ``DeliveryError`` on any delivery failure."""
    errors: list[str] = []

    def on_delivery(err: Any, _msg: Any) -> None:
        if err is not None:
            errors.append(str(err))

    count = 0
    for reading in readings:
        if limit is not None and count >= limit:
            break
        event = build_event(reading)
        while True:
            try:
                producer.produce(
                    topic,
                    key=event["household_id"].encode("utf-8"),
                    value=encode_event(event).encode("utf-8"),
                    on_delivery=on_delivery,
                )
                break
            except BufferError:
                producer.poll(0.5)  # local queue full: serve callbacks, then retry
        producer.poll(0)
        count += 1
        if errors:
            break
    remaining = producer.flush(flush_timeout)
    if errors:
        raise DeliveryError(f"{len(errors)} delivery error(s); first: {errors[0]}")
    if remaining:
        raise DeliveryError(f"{remaining} message(s) not delivered before the flush timeout")
    return count


# ----------------------------------------------------------------------------- entry point
def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, help="stream CSV (default: SAMPLE_STREAM_FILE)")
    parser.add_argument("--topic", help="topic (default: KAFKA_TOPIC or meter-readings)")
    parser.add_argument("--speed", type=float, help="event seconds per wall second; 0 = no pacing")
    parser.add_argument("--limit", type=int, help="publish only the first N events")
    parser.add_argument("--dry-run", action="store_true", help="write JSON lines to stdout")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)

    try:
        settings = read_settings(env)
        path = args.input or settings.stream_file
        if path is None:
            raise ProducerConfigError("no input: pass --input or set SAMPLE_STREAM_FILE")
        speed = settings.replay_speed if args.speed is None else args.speed
        if speed < 0:
            raise ProducerConfigError("--speed must be >= 0")
        topic = args.topic or settings.topic
        readings = paced(read_stream(path), speed)
        if args.dry_run:
            count = dry_run(readings, sys.stdout, args.limit)
        else:
            from confluent_kafka import Producer  # noqa: PLC0415  (only needed to publish)

            producer = Producer(build_kafka_config(env))
            count = publish(readings, producer, topic, args.limit)
    except (ProducerConfigError, DeliveryError, OSError, ImportError) as exc:
        log.error("%s", exc)
        return 1
    log.info("%s %d event(s)", "wrote" if args.dry_run else "published", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
