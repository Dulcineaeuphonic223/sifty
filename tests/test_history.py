"""Tests for the SQLite history store and undo engine (temp DB, mocked restore)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sifty.core import history, undo
from sifty.windows import recyclebin


@pytest.fixture
def temp_history(monkeypatch, tmp_path):
    """Point the history DB at a temp APPDATA so tests don't touch real data."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


def test_record_and_summary(temp_history):
    history.record_clean("junk", "user-temp", 600, 3, [Path("a.tmp"), Path("b.log")])
    history.record_clean("junk", "browser-cache", 400, 2, [])
    summ = history.summary()
    assert summ["runs"] == 2
    assert summ["bytes_freed"] == 1000
    assert summ["items"] == 5


def test_recent_runs_newest_first(temp_history):
    history.record_clean("junk", "first", 1, 1, [])
    history.record_clean("junk", "second", 2, 1, [])
    runs = history.recent_runs()
    assert [r.detail for r in runs] == ["second", "first"]
    assert runs[0].bytes_freed == 2


def test_restorable_tracking(temp_history):
    rid = history.record_clean("junk", "x", 10, 2, [Path("a"), Path("b")])
    run = history.last_restorable_run()
    assert run is not None and run.id == rid and run.restorable == 2
    items = history.items_to_restore(rid)
    assert {p for _i, p in items} == {"a", "b"}


def test_undo_restores_and_marks(temp_history, monkeypatch):
    restored_paths = []
    monkeypatch.setattr(recyclebin, "restore", lambda p: restored_paths.append(p) or True)
    rid = history.record_clean("junk", "x", 10, 2, [Path("a"), Path("b")])

    restored, failed = undo.undo(rid)
    assert (restored, failed) == (2, 0)
    assert set(restored_paths) == {"a", "b"}
    # Once restored, the run is no longer undoable.
    assert history.last_restorable_run() is None


def test_undo_counts_failures(temp_history, monkeypatch):
    # First path restores, second fails.
    monkeypatch.setattr(recyclebin, "restore", lambda p: p == "a")
    rid = history.record_clean("junk", "x", 10, 2, [Path("a"), Path("b")])

    restored, failed = undo.undo(rid)
    assert (restored, failed) == (1, 1)
    # 'b' is still restorable.
    run = history.last_restorable_run()
    assert run is not None and run.restorable == 1
