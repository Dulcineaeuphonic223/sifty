"""Installed-app and startup enumeration + uninstall (engine).

Reads the Windows registry (Uninstall + Run keys) and the Startup folder, and
delegates uninstalls to the winget primitive.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..windows import winget
from .models import InstalledApp, StartupEntry

try:  # Windows-only; tests mock the reader functions.
    import winreg
except ImportError:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore[assignment]

__all__ = ["InstalledApp", "StartupEntry", "installed_apps", "startup_entries", "uninstall_app"]

_UNINSTALL_KEYS = [
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]
_RUN_KEYS = [
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
]


def _hive(name: str):
    return winreg.HKEY_LOCAL_MACHINE if name == "HKLM" else winreg.HKEY_CURRENT_USER


def _read_value(key, name: str, default=""):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def installed_apps() -> list[InstalledApp]:
    """Enumerate installed apps from the registry Uninstall keys."""
    if winreg is None:  # pragma: no cover - non-Windows
        return []
    apps: dict[str, InstalledApp] = {}
    for hive_name, subpath in _UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(_hive(hive_name), subpath)
        except OSError:
            continue
        with root:
            count = winreg.QueryInfoKey(root)[0]
            for i in range(count):
                try:
                    sub_name = winreg.EnumKey(root, i)
                    with winreg.OpenKey(root, sub_name) as sub:
                        name = _read_value(sub, "DisplayName")
                        if not name or _read_value(sub, "SystemComponent", 0) == 1:
                            continue
                        size_kb = _read_value(sub, "EstimatedSize", 0) or 0
                        apps[name.lower()] = InstalledApp(
                            name=name,
                            version=str(_read_value(sub, "DisplayVersion")),
                            publisher=str(_read_value(sub, "Publisher")),
                            size_bytes=int(size_kb) * 1024,
                            uninstall_string=str(_read_value(sub, "UninstallString")),
                            source=hive_name,
                        )
                except OSError:
                    continue
    return sorted(apps.values(), key=lambda a: a.name.lower())


def startup_entries() -> list[StartupEntry]:
    """Enumerate auto-start programs from Run keys and the Startup folder."""
    entries: list[StartupEntry] = []
    if winreg is not None:
        for hive_name, subpath in _RUN_KEYS:
            try:
                key = winreg.OpenKey(_hive(hive_name), subpath)
            except OSError:
                continue
            with key:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        entries.append(StartupEntry(name, str(value), f"{hive_name} Run"))
                    except OSError:
                        continue

    appdata = os.environ.get("APPDATA")
    if appdata:
        folder = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file():
                    entries.append(StartupEntry(item.stem, str(item), "Startup folder"))
    return entries


def uninstall_app(name: str) -> tuple[bool, str]:
    """Uninstall an app by name via winget. Returns (ok, message)."""
    if not winget.available():
        return False, "winget is not available on this system."
    code, out, err = winget.uninstall(name)
    if code == 0:
        return True, f"Uninstalled '{name}'."
    detail = (err or out or "").strip()
    return False, f"winget failed (exit {code}): {detail}"
