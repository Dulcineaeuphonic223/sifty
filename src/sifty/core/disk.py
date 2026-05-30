"""Disk and volume analysis (engine): usage, biggest items, duplicates."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path

import psutil

from .models import VolumeUsage

__all__ = ["VolumeUsage", "volumes", "biggest", "find_duplicates"]


def volumes() -> list[VolumeUsage]:
    """Return usage for every fixed volume."""
    results: list[VolumeUsage] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        results.append(
            VolumeUsage(part.device, part.mountpoint, part.fstype, usage.total, usage.used, usage.free)
        )
    return results


def _entry_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat(follow_symlinks=False).st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                total += (Path(root) / name).stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return total


def biggest(path: Path, top: int = 15) -> list[tuple[Path, int]]:
    """Return the largest immediate children of ``path`` by total size."""
    items: list[tuple[Path, int]] = []
    try:
        for entry in path.iterdir():
            items.append((entry, _entry_size(entry)))
    except OSError:
        return []
    items.sort(key=lambda t: t[1], reverse=True)
    return items[:top]


def find_duplicates(path: Path, min_size: int = 1) -> dict[str, list[Path]]:
    """Find duplicate files under ``path`` by size, then content hash."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            fp = Path(root) / name
            try:
                size = fp.stat(follow_symlinks=False).st_size
            except OSError:
                continue
            if size >= min_size:
                by_size[size].append(fp)

    dupes: dict[str, list[Path]] = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue  # unique size → cannot be a duplicate
        for fp in paths:
            digest = _hash_file(fp)
            if digest:
                dupes[digest].append(fp)
    return {d: ps for d, ps in dupes.items() if len(ps) > 1}


def _hash_file(path: Path, chunk: int = 1 << 20) -> str | None:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while block := fh.read(chunk):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()
