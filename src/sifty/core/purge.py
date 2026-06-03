"""Dev-artifact purge engine.

Walks a project tree looking for well-known build/cache directories (node_modules,
dist, __pycache__, target, etc.) and sends them to the Recycle Bin via the safety
layer.  The scan stops descending into a matched directory so nested artefacts are
treated as one unit (e.g. nested node_modules inside node_modules).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..infra.config import load_config
from .models import CleanResult
from .safety import ProtectedPathError, is_protected, trash

__all__ = ["ARTIFACT_DIRS", "ArtifactScan", "scan_artifacts", "purge_artifacts"]

# Directories that are always safe to delete and rebuild.
ARTIFACT_DIRS: frozenset[str] = frozenset({
    # JavaScript / Node
    "node_modules", ".next", ".nuxt", ".svelte-kit", ".parcel-cache",
    # Generic build output
    "dist", "build", ".build", "out", ".output",
    # Java / Kotlin / Gradle / Maven
    "target", ".gradle",
    # Rust
    # (target already covered above)
    # Python
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "htmlcov", "coverage",
    # .NET
    "bin", "obj",
    # General caches
    ".cache",
    # Dart / Flutter
    ".dart_tool",
    # Go
    "vendor",
})


@dataclass
class ArtifactScan:
    path: Path
    size_bytes: int
    pattern: str   # which ARTIFACT_DIRS key matched


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                total += (Path(root) / name).stat(follow_symlinks=False).st_size
            except OSError:
                pass
    return total


def scan_artifacts(
    root: Path,
    patterns: frozenset[str] | None = None,
    config=None,
) -> list[ArtifactScan]:
    """Walk ``root`` and return matched artifact directories, largest first.

    Matched directories are not descended into (so a ``node_modules`` inside
    another ``node_modules`` is not double-counted).  Protected system paths are
    silently skipped.
    """
    config = config or load_config()
    extra = config.section("purge").get("extra_patterns", [])
    active = (patterns or ARTIFACT_DIRS) | frozenset(extra)

    results: list[ArtifactScan] = []
    try:
        for dirpath, dirnames, _files in os.walk(root, onerror=lambda _e: None):
            current = Path(dirpath)
            to_remove: list[str] = []
            for name in list(dirnames):
                if name not in active:
                    continue
                candidate = current / name
                if is_protected(candidate):
                    to_remove.append(name)
                    continue
                size = _dir_size(candidate)
                results.append(ArtifactScan(candidate, size, name))
                to_remove.append(name)   # stop descending
            for name in to_remove:
                if name in dirnames:
                    dirnames.remove(name)
    except OSError:
        pass

    results.sort(key=lambda a: a.size_bytes, reverse=True)
    return results


def purge_artifacts(
    paths: list[Path],
    *,
    dry_run: bool = True,
    config=None,
) -> CleanResult:
    """Send the given artifact directories to the Recycle Bin via the safety layer."""
    config = config or load_config()
    extra_protected = config.section("safety").get("extra_protected_paths", [])

    bytes_freed = 0
    items = 0
    skipped: list[str] = []
    trashed: list[Path] = []

    for p in paths:
        p = Path(p)
        try:
            size = _dir_size(p)
            trash(p, extra_protected=extra_protected, dry_run=dry_run)
            bytes_freed += size
            items += 1
            if not dry_run:
                trashed.append(p)
        except ProtectedPathError as exc:
            skipped.append(str(exc))
        except OSError as exc:
            skipped.append(f"{p}: {exc}")

    return CleanResult(bytes_freed, items, skipped, trashed)
