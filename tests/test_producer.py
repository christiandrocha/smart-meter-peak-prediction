"""Unit tests for the replay producer (AC-07, AC-29, AC-31). No broker is contacted."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from smart_meter_peak_prediction import producer

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = yaml.safe_load((ROOT / "docs/contracts/meter-readings.yaml").read_text(encoding="utf-8"))
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
HEADER = "LCLid,tstp,energy(kWh/hh)"
ROWS = [
    "MAC000002,2013-12-01 00:30:00.0000000, 0.25 ",
    "MAC000001,2013-12-01 00:30:00.0000000,Null",
    "MAC000002,2013-12-01 00:00:00.0000000, 0.5 ",
    "MAC000001,2013-12-01 00:00:00.0000000,0",
    "MAC000003,not-a-timestamp, 1.0 ",
    "MAC000003,2013-12-01 01:00:00.0000000,nan",
    "MAC000003,2013-12-01 01:30:00.0000000,inf",
    "MAC000003,2013-12-01 02:00:00.0000000,",
]
SECRET_ENV = {
    "KAFKA_BOOTSTRAP": "broker.example.invalid:12345",
    "KAFKA_USERNAME": "svc-user-xyz",
    "KAFKA_PASSWORD": "pw-not-a-real-secret",
    "KAFKA_CA_PATH": "/certs/ca.pem",
    "KAFKA_SASL_MECHANISM": "",
}


@pytest.fixture
def stream_file(tmp_path: Path) -> Path:
    path = tmp_path / "readings_stream.csv"
    path.write_text("\n".join([HEADER, *ROWS]) + "\n", encoding="utf-8")
    return path


def _events(stream_file: Path) -> list[dict]:
    out = io.StringIO()
    count = producer.dry_run(producer.read_stream(stream_file), out)
    lines = out.getvalue().splitlines()
    assert count == len(lines)
    return [json.loads(line) for line in lines]


class FakeProducer:
    def __init__(self, fail: bool = False, undelivered: int = 0) -> None:
        self.sent: list[tuple[str, bytes, bytes]] = []
        self.callbacks: list = []
        self.fail, self.undelivered = fail, undelivered

    def produce(self, topic, key, value, on_delivery):
        self.sent.append((topic, key, value))
        self.callbacks.append(on_delivery)

    def poll(self, timeout=0):
        return 0

    def flush(self, timeout=None):
        for callback in self.callbacks:
            callback("broker down" if self.fail else None, None)
        return self.undelivered


def test_ac07_event_matches_topic_contract_schema(stream_file):
    schema = {c["name"]: c for c in CONTRACT["value"]["schema"]}
    events = _events(stream_file)
    assert events
    for event in events:
        assert list(event) == list(schema)  # same fields, in contract order
        for name, column in schema.items():
            value = event[name]
            if value is None:
                assert column["nullable"], name
            elif column["type"] == "string":
                assert isinstance(value, str)
            elif column["type"] == "double":
                assert isinstance(value, float)
        assert event["source"] == "replay"
        assert ISO_Z.match(event["produced_at"])  # ISO-8601 UTC (AC-31 uses produced_at)
    parsed = [e for e in events if e["reading_ts"] != "not-a-timestamp"]
    assert all(ISO_Z.match(e["reading_ts"]) for e in parsed)
    assert parsed[0]["reading_ts"] == "2013-12-01T00:00:00Z"
    assert CONTRACT["key"]["field"] == "household_id"
    assert CONTRACT["value"]["format"] == "json"


def test_ac07_non_numeric_energy_becomes_null_not_dropped(stream_file):
    events = _events(stream_file)
    assert len(events) == len(ROWS)  # nothing dropped
    by_key = {(e["household_id"], e["reading_ts"]): e["energy_kwh"] for e in events}
    assert by_key[("MAC000001", "2013-12-01T00:30:00Z")] is None  # 'Null'
    assert by_key[("MAC000002", "2013-12-01T00:30:00Z")] == 0.25  # padded value trimmed
    assert by_key[("MAC000001", "2013-12-01T00:00:00Z")] == 0.0
    assert by_key[("MAC000003", "2013-12-01T01:00:00Z")] is None  # nan
    assert by_key[("MAC000003", "2013-12-01T01:30:00Z")] is None  # inf
    assert by_key[("MAC000003", "2013-12-01T02:00:00Z")] is None  # empty
    assert by_key[("MAC000003", "not-a-timestamp")] == 1.0  # raw timestamp passed through


def test_ac07_events_are_sorted_by_event_time_then_household(stream_file):
    keys = [(e["reading_ts"], e["household_id"]) for e in _events(stream_file)]
    parsed = [k for k in keys if k[0] != "not-a-timestamp"]
    assert parsed == sorted(parsed)
    assert keys[-1][0] == "not-a-timestamp"  # unparsable rows last, never dropped


def test_ac07_messages_are_keyed_by_household_id(stream_file):
    fake = FakeProducer()
    count = producer.publish(producer.read_stream(stream_file), fake, "meter-readings")
    assert count == len(ROWS) == len(fake.sent)
    for topic, key, value in fake.sent:
        assert topic == "meter-readings"
        assert key.decode() == json.loads(value)["household_id"]


def test_ac07_delivery_error_or_unflushed_messages_raise(stream_file):
    with pytest.raises(producer.DeliveryError):
        producer.publish(producer.read_stream(stream_file), FakeProducer(fail=True), "t")
    with pytest.raises(producer.DeliveryError):
        producer.publish(producer.read_stream(stream_file), FakeProducer(undelivered=2), "t")


def test_ac07_main_exits_non_zero_on_bad_input(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert producer.main(["--dry-run", "--input", str(bad)], env={}) == 1
    assert producer.main(["--dry-run"], env={}) == 1  # no input configured
    assert producer.main(["--input", str(bad)], env={}) == 1  # missing credentials


def test_ac07_main_dry_run_writes_json_lines(stream_file, capsys):
    assert producer.main(["--dry-run", "--input", str(stream_file), "--limit", "3"], env={}) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert all(json.loads(line)["source"] == "replay" for line in lines)


def test_ac07_pacing_waits_event_seconds_divided_by_speed(stream_file):
    sleeps: list[float] = []
    now = [0.0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    readings = [r for r in producer.read_stream(stream_file) if r.ts is not None]
    list(producer.paced(readings, speed=1800.0, sleep=sleep, clock=lambda: now[0]))
    # events are 30 minutes apart at most; speed 1800 => at most 1 second per step
    assert sleeps
    assert all(0 < s <= 1.0 for s in sleeps)
    assert sum(sleeps) == pytest.approx((readings[-1].ts - readings[0].ts).total_seconds() / 1800.0)
    sleeps.clear()
    list(producer.paced(readings, speed=0, sleep=sleep, clock=lambda: now[0]))
    assert sleeps == []  # 0 = no pacing


def test_ac29_producer_reads_credentials_from_environment_only():
    config = producer.build_kafka_config(SECRET_ENV)
    assert config["bootstrap.servers"] == SECRET_ENV["KAFKA_BOOTSTRAP"]
    assert config["sasl.username"] == SECRET_ENV["KAFKA_USERNAME"]
    assert config["sasl.password"] == SECRET_ENV["KAFKA_PASSWORD"]
    assert config["ssl.ca.location"] == SECRET_ENV["KAFKA_CA_PATH"]
    assert config["security.protocol"] == "SASL_SSL"
    assert config["sasl.mechanism"] == "SCRAM-SHA-256"  # empty variable -> default
    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert (
        producer.build_kafka_config({**SECRET_ENV, "KAFKA_SASL_MECHANISM": "SCRAM-SHA-512"})[
            "sasl.mechanism"
        ]
        == "SCRAM-SHA-512"
    )


def test_ac29_missing_credentials_name_the_variable_but_never_a_value():
    env = {**SECRET_ENV, "KAFKA_PASSWORD": ""}
    with pytest.raises(producer.ProducerConfigError) as err:
        producer.build_kafka_config(env)
    message = str(err.value)
    assert "KAFKA_PASSWORD" in message
    assert not any(v and v in message for v in SECRET_ENV.values())


def test_ac29_producer_source_has_no_literal_credentials_or_env_file_reads():
    source = (ROOT / "src/smart_meter_peak_prediction/producer.py").read_text(encoding="utf-8")
    assert "dotenv" not in source
    assert not re.search(r"open\([^)]*\.env", source)
    assert not re.search(r"sasl\.(username|password)\"\s*:\s*\"", source)  # no literal values
    assert not re.search(r"(?i)aivencloud", source)


def test_ac29_settings_use_defaults_for_empty_values():
    settings = producer.read_settings(
        {"KAFKA_TOPIC": "", "REPLAY_SPEED": "", "SAMPLE_STREAM_FILE": ""}
    )
    assert settings.topic == "meter-readings"
    assert settings.replay_speed == 0
    assert settings.stream_file is None
    with pytest.raises(producer.ProducerConfigError):
        producer.read_settings({"REPLAY_SPEED": "fast"})
    with pytest.raises(producer.ProducerConfigError):
        producer.read_settings({"REPLAY_SPEED": "-1"})


def test_ac31_produced_at_is_utc_wall_clock_not_event_time():
    reading = producer.Reading(
        "MAC000001", "2013-12-01 00:00:00.0000000", datetime(2013, 12, 1, tzinfo=UTC), "1"
    )
    when = datetime(2026, 10, 15, 12, 0, 0, 123456, tzinfo=UTC)
    event = producer.build_event(reading, produced_at=when)
    assert event["produced_at"] == "2026-10-15T12:00:00.123456Z"
    assert event["reading_ts"] == "2013-12-01T00:00:00Z"
