import pandas as pd
import profile_data
import pytest


@pytest.fixture
def readings_csv(tmp_path):
    rows = []
    for meter in ("M1", "M2", "DEAD"):
        for i in range(48 * 3):
            ts = pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=30 * i)
            value = "0" if meter == "DEAD" else f" {0.1 + i % 5 / 10:.3f} "
            rows.append((meter, str(ts), value))
    rows = [r for r in rows if not (r[0] == "M2" and 10 <= rows.index(r) % 144 < 60)]  # gaps
    rows.append(("M1", "2024-01-02 15:13:42", "Null"))  # off-grid system row
    rows.append(rows[0])  # duplicate key
    path = tmp_path / "readings.csv"
    pd.DataFrame(rows, columns=["meter_id", "ts", "energy(kWh)"]).to_csv(path, index=False)
    return path


def run(path, *extra):
    args = profile_data.parse_args([str(path), *extra])
    return profile_data.run(args)


def by_title(prof, text):
    return [f for f in prof.findings if text in f.finding]


def test_detects_all_issue_types(readings_csv):
    prof = run(
        readings_csv,
        "--key",
        "meter_id,ts",
        "--time",
        "ts",
        "--entity",
        "meter_id",
        "--value",
        "energy(kWh)",
        "--grid",
        "30min",
    )
    assert by_title(prof, "not safe for Delta")
    assert "1 literal 'Null'" in by_title(prof, "Null-like")[0].evidence
    assert by_title(prof, "Whitespace-padded")
    assert "1 duplicated rows" in by_title(prof, "Duplicate keys")[0].evidence
    assert "1 off the 30min grid" in by_title(prof, "off the 30min grid")[0].evidence
    assert "1 below 80%" in by_title(prof, "time coverage")[0].evidence
    assert "DEAD (100% zero)" in by_title(prof, "mostly-zero")[0].evidence


def test_ids_are_sequential_from_start_id(readings_csv):
    prof = run(readings_csv, "--key", "meter_id,ts", "--start-id", "7")
    ids = [f.id for f in prof.findings]
    assert ids[0] == "F-07"
    assert ids == [f"F-{n:02d}" for n in range(7, 7 + len(ids))]


def test_clean_data_reports_unique_key(tmp_path):
    path = tmp_path / "clean.csv"
    pd.DataFrame({"id": ["a", "b"], "value": ["1", "2"]}).to_csv(path, index=False)
    prof = run(path, "--key", "id")
    assert [f.finding for f in prof.findings] == ["Key (id) is unique"]


def test_mostly_numeric_with_junk_token(tmp_path):
    path = tmp_path / "junk.csv"
    values = [str(i) for i in range(99)] + ["n.a."]
    pd.DataFrame({"amount": values}).to_csv(path, index=False)
    prof = run(path)
    assert "'n.a.'" in by_title(prof, "Non-numeric tokens")[0].evidence


def test_markdown_and_json_outputs(readings_csv, tmp_path):
    out, js = tmp_path / "p.md", tmp_path / "p.json"
    code = profile_data.main(
        [str(readings_csv), "--key", "meter_id,ts", "--out", str(out), "--json", str(js)]
    )
    assert code == 0
    text = out.read_text()
    assert "| ID | Finding | Evidence | Implication |" in text
    assert '"id": "F-01"' in js.read_text()


def test_missing_file_exits_cleanly(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        run(tmp_path / "nope.csv")
