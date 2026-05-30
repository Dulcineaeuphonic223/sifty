"""Recycle Bin primitive — the single place that calls Send2Trash."""

from __future__ import annotations

import os
from pathlib import Path

from send2trash import send2trash


def send_to_trash(path: str | Path) -> None:
    """Send a path to the Recycle Bin."""
    send2trash(os.fspath(Path(path)))
