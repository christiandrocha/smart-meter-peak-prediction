"""Deduplication, replays, determinism and `_source_ref` (AC-09, AC-11, AC-17, AC-27).

First ingested wins: rank by ``(_ingested_at, _source_ref)`` over rows that failed no rule and
are in scope. Every update recomputes from the Bronze snapshot, so the result must not depend on
input order or partitioning.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta

import pytest
from support import builders as b
from support.harness import ExpectationFailed, build_update, checksum, rows, totals

from smart_meter_peak_prediction import metrics, silver
from smart_meter_peak_prediction.config import Settings

T = datetime(2013, 1, 1, tzinfo=UTC)
K = datetime(2013, 12, 1, tzinfo=UTC)
EARLY = datetime(2024, 1, 1, 10, tzinfo=UTC)
LATE = datetime(2024, 1, 5, 10, tzinfo=UTC)
SILVER_COLS = [
    "household_id",
    "reading_ts",
    "reading_date",
    "energy_kwh",
    "_ingestion_path",
    "_source_ref",
    "_ingested_at",
    "_produced_at",
]
QUARANTINE_COLS = [
    "_source_ref",
    "_dedup_key",
    "_ingestion_path",
    "household_id",
    "reading_ts_raw",
    "energy_kwh_raw",
    "payload",
    "rule_name",
    "failed_rules",
    "_ingested_at",
]


def kafka_rows(n: int, *, offset0: int = 0, ingested_at: datetime = EARLY) -> list[dict]:
    return [
        b.kafka_row(
            b.kafka_payload(
                f"MAC00000{i % 3 + 1}", moment=K + timedelta(minutes=30 * (i // 3)), energy_kwh=0.1
            ),
            offset=offset0 + i,
            partition=i % 2,
            ingested_at=ingested_at,
        )
        for i in range(n)
    ]


def test_ac09_replayed_messages_counted_as_duplicates_and_silver_unchanged(spark) -> None:
    files = b.day_rows("MAC000001", T, count=4)
    original = kafka_rows(12)
    # the producer republishes the whole stream: same events at new offsets, ingested later
    replay = [{**row, "_offset": row["_offset"] + 1000, "_ingested_at": LATE} for row in original]
    before = build_update(spark, files, original)
    after = build_update(spark, files, original + replay)

    assert checksum(after, "silver", SILVER_COLS) == checksum(before, "silver", SILVER_COLS)
    assert checksum(after, "quarantine", QUARANTINE_COLS) == checksum(
        before, "quarantine", QUARANTINE_COLS
    )
    assert totals(after)["qr_09"] == totals(before)["qr_09"] + len(replay)
    assert totals(before)["qr_09"] == 0
    kept = {r["_ingested_at"] for r in rows(after.silver.where("_ingestion_path = 'kafka'"))}
    assert kept == {EARLY}  # the originals win, replays always rank after them


def _invalid_message_fixture() -> tuple[list[dict], list[dict]]:
    """Valid messages plus one failing QR-07, one QR-03 and QR-04, one QR-05, and their replay.

    The replay delivers every message again at a new offset, later, and for payloads that parse
    with a different ``produced_at`` (the replay producer stamps a new one into every message).
    """

    def messages(*, offset0: int, ingested_at: datetime, produced_at: str) -> list[dict]:
        payloads = [
            b.kafka_payload("MAC000002", moment=K, produced_at=produced_at),
            b.kafka_payload("MAC000002", moment=K + timedelta(minutes=30), produced_at=produced_at),
            "not json",  # QR-07
            b.kafka_payload(  # QR-03 and QR-04
                "MAC000002",
                moment=K + timedelta(minutes=45),
                energy_kwh=None,
                produced_at=produced_at,
            ),
            b.kafka_payload(  # QR-05
                "MAC000002", moment=K + timedelta(hours=2), energy_kwh=-1.0, produced_at=produced_at
            ),
        ]
        return [
            b.kafka_row(payload, offset=offset0 + i, partition=i % 2, ingested_at=ingested_at)
            for i, payload in enumerate(payloads)
        ]

    original = messages(offset0=0, ingested_at=EARLY, produced_at="2024-01-01T10:00:00.111111Z")
    replay = messages(offset0=1000, ingested_at=LATE, produced_at="2024-01-05T10:00:00.222222Z")
    return original, replay


def test_ac09_replayed_invalid_messages_not_quarantined_again(spark) -> None:
    original, replay = _invalid_message_fixture()
    before = build_update(spark, [], original)
    after = build_update(spark, [], original + replay)
    t_before, t_after = totals(before), totals(after)

    assert t_before["quarantine_rows"] == 3  # the three invalid messages
    assert checksum(after, "silver", SILVER_COLS) == checksum(before, "silver", SILVER_COLS)
    assert checksum(after, "quarantine", QUARANTINE_COLS) == checksum(
        before, "quarantine", QUARANTINE_COLS
    )
    assert after.quarantine.count() == before.quarantine.count() == 3
    for column in ("qr_02", "qr_03", "qr_04", "qr_05", "qr_07", "quarantine_rows", "sf_01"):
        assert t_after[column] == t_before[column], column
    assert t_before["qr_09"] == 0
    assert t_after["qr_09"] == t_before["qr_09"] + len(replay)  # valid and invalid replays
    assert t_after["quarantine_duplicates"] == 3
    # the first-ingested row is the one kept in the quarantine
    assert {r["_ingested_at"] for r in rows(after.quarantine)} == {EARLY}
    assert after.quarantine.select("_dedup_key").distinct().count() == 3


def test_ac09_dedup_key_is_per_path_and_offset_independent(spark) -> None:
    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    ts = "2013-12-01T00:00:00Z"
    garbage = "not json"
    files = [
        b.file_row("MAC000001", reading_ts_raw=ts, source_file="/v/key.csv"),
        # same raw values in another file and at another time: same key
        b.file_row("MAC000001", reading_ts_raw=ts, source_file="/v/key2.csv", ingested_at=LATE),
        # no household id, then no timestamp: the key is the hash of the raw record values
        b.file_row(None, reading_ts_raw=ts, energy_kwh_raw="7", source_file="/v/nohh.csv"),
        {
            **b.file_row("MAC000001", energy_kwh_raw=None, rescued="x", source_file="/v/nots.csv"),
            "reading_ts_raw": None,
        },
    ]
    kafka = [
        b.kafka_row(
            b.kafka_payload("MAC000001", reading_ts=ts, produced_at="2024-01-01T10:00:00Z"),
            offset=1,
        ),
        # the replay: other offset, other partition, later, other produced_at
        b.kafka_row(
            b.kafka_payload("MAC000001", reading_ts=ts, produced_at="2024-01-09T10:00:00Z"),
            offset=77,
            partition=1,
            ingested_at=LATE,
        ),
        b.kafka_row(garbage, offset=2),
        b.kafka_row(garbage, offset=88, partition=1, ingested_at=LATE),
    ]
    evaluated = silver.evaluate(
        b.bronze_files(spark, files), b.bronze_kafka(spark, kafka), Settings()
    )
    keys = {r["_source_ref"]: r["_dedup_key"] for r in rows(evaluated)}

    def key_of(fragment: str) -> str:
        (match,) = (v for ref, v in keys.items() if fragment in ref)
        return match

    files_key = f"files:key:MAC000001#{ts}"
    assert key_of("/v/key.csv") == key_of("/v/key2.csv") == files_key
    assert key_of("/00000000000000000001") == key_of("/00000000000000000077")
    assert key_of("/00000000000000000001") == f"kafka:key:MAC000001#{ts}"
    assert key_of("/00000000000000000001") != files_key  # the path prefix keeps them apart
    # QR-07: no business key can be read, so the key hashes the payload
    assert key_of("/00000000000000000002") == f"kafka:payload:{sha(garbage)}"
    assert key_of("/00000000000000000002") == key_of("/00000000000000000088")
    nul, sep = "\x00", "\x01"
    assert key_of("/v/nohh.csv") == "files:row:" + sha(sep.join([nul, ts, "7", nul]))
    assert key_of("/v/nots.csv") == "files:row:" + sha(sep.join(["MAC000001", nul, nul, "x"]))


def test_ac09_dropped_repeat_sharing_key_with_valid_row_is_a_quarantine_duplicate(spark) -> None:
    """A QR-05 row and a valid row share (household, ts); dropped and valid never compete."""
    valid = b.kafka_row(b.kafka_payload("MAC000002", moment=K), offset=1, ingested_at=EARLY)
    bad = b.kafka_payload("MAC000002", moment=K, energy_kwh=-1.0)
    first = b.kafka_row(bad, offset=2, ingested_at=LATE)
    # equal ingestion time: the smaller _source_ref (offset 3) is kept in the quarantine
    tie_a = b.kafka_row(bad, offset=4, ingested_at=LATE)
    tie_b = b.kafka_row(bad, offset=3, ingested_at=LATE)
    update = build_update(spark, [], [valid, first, tie_a, tie_b])
    assert update.silver.count() == 1  # the valid row is not displaced by the dropped ones
    kept = [r["_source_ref"] for r in rows(update.quarantine)]
    assert kept == ["kafka:meter-readings/0/00000000000000000002"]
    update.register_views()
    recon = spark.sql(
        metrics.reconciliation_sql("evaluated", "silver", "quarantine", Settings())
    ).collect()[0]
    assert (recon.in_silver, recon.in_quarantine) == (1, 1)
    assert (recon.is_duplicate, recon.is_quarantine_duplicate) == (0, 2)
    assert recon.unclassified == 0
    assert recon.double_classified == 0
    assert totals(update)["qr_05"] == 1


def test_ac09_quarantine_tie_on_ingested_at_keeps_smaller_source_ref(spark) -> None:
    bad = "not json"
    rows_ = [b.kafka_row(bad, offset=9), b.kafka_row(bad, offset=5)]
    update = build_update(spark, [], rows_)
    kept = [r["_source_ref"] for r in rows(update.quarantine)]
    assert kept == ["kafka:meter-readings/0/00000000000000000005"]


def test_ac11_source_ref_unique_per_bronze_row(spark) -> None:
    files = [
        b.file_row(" MAC000001 ", moment=T, source_file="/v/a.csv"),
        b.file_row("MAC000001", moment=T, source_file="/v/b.csv"),
        b.file_row("MAC000001", reading_ts_raw="garbage", source_file="/v/a.csv"),
    ]
    update = build_update(spark, files, kafka_rows(3, offset0=41))
    refs = {r["_source_ref"] for r in rows(update.evaluated.select("_source_ref"))}
    assert len(refs) == 6
    # files: raw Bronze values, untrimmed, with the raw timestamp text
    assert "files:/v/a.csv# MAC000001 #2013-01-01 00:00:00.0000000" in refs
    assert "files:/v/a.csv#MAC000001#garbage" in refs
    # kafka: topic, partition and offset left-padded to 20 digits
    assert "kafka:meter-readings/0/00000000000000000041" in refs
    assert "kafka:meter-readings/1/00000000000000000042" in refs
    assert update.evaluated.where("source_ref_row_count <> 1").count() == 0


def test_ac11_inv_01_fails_on_a_duplicated_csv_line(spark) -> None:
    line = b.file_row("MAC000001", moment=T, source_file="/v/a.csv")
    with pytest.raises(ExpectationFailed) as failure:
        build_update(spark, [line, dict(line)])
    assert failure.value.expectation == "inv_01_source_ref_unique"


def test_ac17_earlier_ingested_at_wins_and_tie_uses_smaller_source_ref(spark) -> None:
    files = [
        # pair A: the earlier ingestion wins although its file name sorts last
        b.file_row("MAC000001", moment=T, source_file="/v/z.csv", ingested_at=EARLY),
        b.file_row("MAC000001", moment=T, source_file="/v/a.csv", ingested_at=LATE),
    ]
    kafka = [
        # pair B: same ingestion time, the smaller offset (smaller _source_ref) wins
        b.kafka_row(b.kafka_payload("MAC000002", moment=K), offset=6, ingested_at=EARLY),
        b.kafka_row(b.kafka_payload("MAC000002", moment=K), offset=5, ingested_at=EARLY),
    ]
    update = build_update(spark, files, kafka)
    winners = {r["_source_ref"] for r in rows(update.silver.select("_source_ref"))}
    assert winners == {
        "files:/v/z.csv#MAC000001#2013-01-01 00:00:00.0000000",
        "kafka:meter-readings/0/00000000000000000005",
    }
    assert totals(update)["qr_09"] == 2
    ranks = {r["_source_ref"]: r["dedup_rank"] for r in rows(update.evaluated)}
    assert sorted(ranks.values()) == [1, 1, 2, 2]


def _ac17_pairs() -> tuple[list[dict], list[dict]]:
    files = [
        b.file_row("MAC000001", moment=T, source_file="/v/z.csv", ingested_at=EARLY),
        b.file_row("MAC000001", moment=T, source_file="/v/a.csv", ingested_at=LATE),
    ]
    kafka = [
        b.kafka_row(b.kafka_payload("MAC000002", moment=K), offset=6, ingested_at=EARLY),
        b.kafka_row(b.kafka_payload("MAC000002", moment=K), offset=5, ingested_at=EARLY),
    ]
    return files, kafka


def _silver_state(update) -> list[tuple]:
    return sorted(
        tuple(r[c] for c in SILVER_COLS) for r in rows(update.silver.select(*SILVER_COLS))
    )


def test_ac17_rerun_keeps_same_winners(spark) -> None:
    pair_files, pair_kafka = _ac17_pairs()
    pairs = build_update(spark, pair_files, pair_kafka)
    for variant in (
        build_update(spark, pair_files, pair_kafka),
        build_update(spark, pair_files[::-1], pair_kafka[::-1]),
        build_update(spark, pair_files, pair_kafka, partitions=5),
    ):
        assert _silver_state(variant) == _silver_state(pairs)
        assert totals(variant)["qr_09"] == 2
    files = [
        b.file_row(
            "MAC000001",
            moment=T + timedelta(minutes=30 * (i % 4)),
            ingested_at=EARLY + timedelta(hours=i),
            source_file=f"/v/{i}.csv",
        )
        for i in range(12)
    ]
    kafka = kafka_rows(9) + kafka_rows(9, offset0=100, ingested_at=LATE)
    base = _silver_state(build_update(spark, files, kafka))
    assert _silver_state(build_update(spark, files, kafka)) == base  # a second run
    assert _silver_state(build_update(spark, files[::-1], kafka[::-1])) == base  # reversed order
    assert _silver_state(build_update(spark, files, kafka, partitions=5)) == base  # partitioning
    assert len(base) == 4 + 3 * 3  # 4 distinct file slots, 3 households x 3 slots


def test_ac27_rebuild_is_identical_for_any_input_order(spark) -> None:
    files = (
        b.day_rows("MAC000001", T, count=48)
        + b.day_rows("MAC000002", T, count=40, skip=[3, 4, 5])
        + [b.file_row("MAC000001", moment=T + timedelta(minutes=15), energy_kwh_raw="Null")]
        + [b.file_row("MAC000001", moment=datetime(2011, 1, 1, tzinfo=UTC))]
        # a dropped pair: the earlier ingestion sits on the larger _source_ref
        + [
            b.file_row("MAC000002", moment=T, energy_kwh_raw="-3", source_file="/v/z.csv"),
            b.file_row(
                "MAC000002",
                moment=T,
                energy_kwh_raw="-3",
                source_file="/v/a.csv",
                ingested_at=LATE,
            ),
        ]
    )
    kafka = (
        kafka_rows(12)
        + kafka_rows(12, offset0=500, ingested_at=LATE)
        + [b.kafka_row("not json", offset=900)]
    )
    households = [
        b.household_row("MAC000001"),
        b.household_row("MAC000002", "ToU", "ACORN-A", "Comfortable"),
        b.household_row("MAC000003", "Std", "ACORN-J", "Adversity"),
    ]
    tables = {
        "silver": SILVER_COLS,
        "quarantine": QUARANTINE_COLS,
        "daily": None,
        "monthly": None,
    }

    def digest(update):
        out = {}
        for name, columns in tables.items():
            cols = columns or getattr(update, "daily" if name == "daily" else "monthly").columns
            out[name] = checksum(update, name, cols)
        return out

    reference = digest(build_update(spark, files, kafka, households))
    rng = random.Random(11)  # noqa: S311
    for partitions in (1, 3, 7):
        shuffled_files, shuffled_kafka, shuffled_hh = list(files), list(kafka), list(households)
        for rows_ in (shuffled_files, shuffled_kafka, shuffled_hh):
            rng.shuffle(rows_)
        again = digest(
            build_update(spark, shuffled_files, shuffled_kafka, shuffled_hh, partitions=partitions)
        )
        assert again == reference
    assert all(count > 0 for count, _ in reference.values())
