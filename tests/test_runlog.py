"""Tests for the runlog module."""

from collector import runlog


def test_append_then_tail_returns_entries_oldest_first(tmp_path):
    path = str(tmp_path / "runs.jsonl")
    runlog.append(path, {"run_at": "2026-07-29T05:17:00+00:00", "outcome": "ok"})
    runlog.append(path, {"run_at": "2026-07-30T05:17:00+00:00", "outcome": "outage"})

    entries = runlog.tail(path, 10)
    assert [e["outcome"] for e in entries] == ["ok", "outage"]


def test_tail_keeps_only_the_last_entries(tmp_path):
    path = str(tmp_path / "runs.jsonl")
    for day in range(1, 6):
        runlog.append(path, {"run_at": f"2026-07-0{day}", "outcome": "ok"})

    assert len(runlog.tail(path, 2)) == 2
    assert runlog.tail(path, 2)[0]["run_at"] == "2026-07-04"


def test_tail_on_a_missing_log_is_empty_not_an_error(tmp_path):
    assert runlog.tail(str(tmp_path / "never-written.jsonl"), 10) == []


def test_a_corrupted_line_does_not_take_down_the_reader(tmp_path):
    """A truncated write must cost one entry, not the whole log."""
    path = tmp_path / "runs.jsonl"
    path.write_text('{"outcome": "ok"}\n{"outcome": "trunca\n{"outcome": "ok"}\n')

    assert len(runlog.tail(str(path), 10)) == 2
