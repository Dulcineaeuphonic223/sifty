"""Tests for the privilege/elevation helper.

These avoid actually invoking UAC: they patch is_admin / ShellExecuteW so the
relaunch logic is exercised without spawning processes.
"""

from __future__ import annotations

import sys

from sifty import admin


def test_is_admin_returns_bool():
    assert isinstance(admin.is_admin(), bool)


def test_relaunch_target_uses_module_form(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sifty", "junk", "scan"])
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    executable, params = admin._relaunch_target()
    assert executable == sys.executable
    assert params == "-m sifty junk scan"


def test_relaunch_target_frozen_uses_exe(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sifty.exe", "tui"])
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    executable, params = admin._relaunch_target()
    assert executable == sys.executable
    assert params == "tui"


def test_relaunch_no_op_when_already_admin(monkeypatch):
    monkeypatch.setattr(admin, "is_admin", lambda: True)
    monkeypatch.setattr(sys, "platform", "win32")
    assert admin.relaunch_as_admin() is False


def test_relaunch_invokes_shellexecute_when_elevatable(monkeypatch):
    calls = {}

    def fake_shellexecute(hwnd, verb, file, params, directory, show):
        calls["verb"] = verb
        calls["file"] = file
        return 42  # > 32 means success

    monkeypatch.setattr(admin, "is_admin", lambda: False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["sifty", "tui"])
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    class _Shell:
        ShellExecuteW = staticmethod(fake_shellexecute)

    monkeypatch.setattr(admin.ctypes, "windll", type("W", (), {"shell32": _Shell}))

    assert admin.relaunch_as_admin() is True
    assert calls["verb"] == "runas"


def test_relaunch_prefers_windows_terminal(monkeypatch):
    captured = {}
    monkeypatch.setattr(admin, "is_admin", lambda: False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["sifty", "tui"])
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(admin, "_windows_terminal", lambda: r"C:\wt.exe")

    def fake_exec(exe, params):
        captured["exe"] = exe
        captured["params"] = params
        return 42

    monkeypatch.setattr(admin, "_shell_execute", fake_exec)
    assert admin.relaunch_as_admin() is True
    assert captured["exe"] == r"C:\wt.exe"
    assert "-m sifty tui" in captured["params"]  # full command handed to wt


def test_relaunch_falls_back_when_wt_launch_fails(monkeypatch):
    attempts = []
    monkeypatch.setattr(admin, "is_admin", lambda: False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["sifty", "tui"])
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(admin, "_windows_terminal", lambda: r"C:\wt.exe")

    def fake_exec(exe, params):
        attempts.append(exe)
        return 0 if exe == r"C:\wt.exe" else 42  # wt fails, direct succeeds

    monkeypatch.setattr(admin, "_shell_execute", fake_exec)
    assert admin.relaunch_as_admin() is True
    assert attempts == [r"C:\wt.exe", sys.executable]  # tried wt, then direct
