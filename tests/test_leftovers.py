"""Tests for the post-uninstall leftover scanner (sandboxed roots)."""

from __future__ import annotations

from pathlib import Path

from sifty.core import leftovers, safety
from sifty.core.leftovers import Leftover, clean_leftovers, find_leftovers


def _mkdir(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    path.mkdir(parents=True)
    (path / "settings.json").write_bytes(b"x" * 100)
    return path


def test_finds_exact_and_squashed_name_matches(tmp_path):
    target = _mkdir(tmp_path, "SuperApp")
    squashed = _mkdir(tmp_path, "super-app")
    _mkdir(tmp_path, "OtherThing")
    found = find_leftovers("Super App", roots=[tmp_path], shortcut_roots=[])
    assert {f.path for f in found} == {target, squashed}
    assert all(f.size_bytes > 0 for f in found)


def test_strips_version_noise_from_app_name(tmp_path):
    target = _mkdir(tmp_path, "SuperApp")
    found = find_leftovers("Super App 2.4.1 (x64)", roots=[tmp_path], shortcut_roots=[])
    assert [f.path for f in found] == [target]


def test_publisher_two_level_layout(tmp_path):
    target = _mkdir(tmp_path, "AcmeSoft", "SuperApp")
    found = find_leftovers("Super App", publisher="AcmeSoft",
                           roots=[tmp_path], shortcut_roots=[])
    assert [f.path for f in found] == [target]


def test_never_matches_generic_vendor_names(tmp_path):
    _mkdir(tmp_path, "Microsoft")
    _mkdir(tmp_path, "Google")
    assert find_leftovers("Microsoft", roots=[tmp_path], shortcut_roots=[]) == []
    assert find_leftovers("Google", roots=[tmp_path], shortcut_roots=[]) == []


def test_short_names_never_match(tmp_path):
    _mkdir(tmp_path, "Git")
    assert find_leftovers("Git", roots=[tmp_path], shortcut_roots=[]) == []


def test_finds_start_menu_shortcuts(tmp_path):
    menu = tmp_path / "menu"
    menu.mkdir()
    lnk = menu / "Super App.lnk"
    lnk.write_bytes(b"shortcut")
    found = find_leftovers("Super App", roots=[], shortcut_roots=[menu])
    assert [f.path for f in found] == [lnk]
    assert found[0].kind == "shortcut"


def test_clean_leftovers_trashes_and_reports(tmp_path, monkeypatch):
    trashed = []
    monkeypatch.setattr(safety, "send_to_trash", lambda p: trashed.append(p))
    monkeypatch.setattr(safety, "audit", lambda msg: None)
    target = _mkdir(tmp_path, "SuperApp")
    items = [Leftover(target, 100, "data-dir")]

    dry = clean_leftovers(items, dry_run=True)
    assert dry.items == 1 and trashed == []

    applied = clean_leftovers(items, dry_run=False)
    assert applied.items == 1 and trashed == [target]


def test_clean_leftovers_refuses_system_trees(tmp_path, monkeypatch):
    monkeypatch.setattr(
        safety, "send_to_trash",
        lambda p: (_ for _ in ()).throw(AssertionError("must not trash system paths")),
    )
    sysroot = tmp_path / "Windows"
    (sysroot / "System32").mkdir(parents=True)
    monkeypatch.setenv("SystemRoot", str(sysroot))
    items = [Leftover(sysroot / "System32", 100, "data-dir")]
    result = clean_leftovers(items, dry_run=False)
    assert result.items == 0
    assert result.skipped and "refused" in result.skipped[0]


def test_normalize_handles_trademarks_and_separators():
    assert leftovers._normalize("Super-App™ v3.1 (x64)") == "super app"
    assert leftovers._normalize("EPSON_Scan 2") == "epson scan"
