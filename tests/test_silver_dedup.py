"""Deduplication, replays, determinism and `_source_ref` (AC-09, AC-11, AC-17, AC-27).

First ingested wins: rank by ``(_ingested_at, _source_ref)`` over rows that failed no rule and
are in scope. Every update recomputes from the Bronze snapshot, so the result must not depend on
input order or partitioning.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from support import builders as b
from support.harness import ExpectationFailed, build_update, checksum, rows, totals

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


def test_ac09_replay_of_an_invalid_message_is_quarantined_again(spark) -> None:
    """Documented behaviour: only rows that pass every rule are deduplicated (QR-09).

    A replayed invalid message is a new Bronze row that fails the same rule, so it is
    quarantined again. The seed-42 stream holds no invalid message, so the AC-09 figures hold.
    """
    bad = b.kafka_row("not json", offset=1)
    again = {**bad, "_offset": 2, "_ingested_at": LATE}
    update = build_update(spark, [], [bad, again])
    assert update.quarantine.count() == 2
    assert totals(update)["qr_09"] == 0


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


def _silver_state(update) -> list[tuple]:
    return sorted(
        tuple(r[c] for c in SILVER_COLS) for r in rows(update.silver.select(*SILVER_COLS))
    )


def test_ac17_rerun_keeps_same_winners(spark) -> None:
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
