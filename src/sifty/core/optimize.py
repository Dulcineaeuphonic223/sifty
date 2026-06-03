"""Non-destructive system optimization operations.

Each operation is safe by design: it either flushes a cache the OS rebuilds
automatically (DNS, thumbnails, Prefetch) or delegates deletion to the safety
layer (junk.clean) or calls an OS tool that cleans its own store (DISM).

All applied operations are written to the audit log even though they are not
file deletions, so there is a record of what ran and when.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from .safety import audit

__all__ = ["OptimizeOp", "list_operations", "run_op"]


@dataclass
class OptimizeOp:
    key: str
    label: str
    description: str
    reversible: str       # human note: "instant" | "auto-rebuilt" | "not reversible"
    requires_admin: bool = False


def list_operations() -> list[OptimizeOp]:
    return [
        OptimizeOp(
            "dns-flush",
            "Flush DNS cache",
            "Clear cached DNS resolutions (ipconfig /flushdns). "
            "Takes effect immediately; the cache rebuilds on next lookup.",
            "instant",
        ),
        OptimizeOp(
            "thumbnail-cache",
            "Rebuild thumbnail cache",
            "Delete Explorer thumbnail & icon database. "
            "Windows rebuilds it automatically as you browse folders.",
            "auto-rebuilt",
        ),
        OptimizeOp(
            "prefetch",
            "Clear Prefetch",
            "Delete C:\\Windows\\Prefetch\\* (boot/app startup hints). "
            "Windows rebuilds within a few launches.",
            "auto-rebuilt",
            requires_admin=True,
        ),
        OptimizeOp(
            "update-cache",
            "Clear Windows Update download cache",
            "Remove cached update packages from SoftwareDistribution\\Download. "
            "Re-downloaded automatically when updates run next.",
            "re-downloaded if needed",
            requires_admin=True,
        ),
        OptimizeOp(
            "dism-cleanup",
            "DISM component cleanup",
            "Run DISM /Cleanup-Image /StartComponentCleanup to mark superseded "
            "Windows components for removal during the next maintenance window. "
            "Safe but not reversible.",
            "not reversible",
            requires_admin=True,
        ),
    ]


def run_op(op: OptimizeOp, *, dry_run: bool = True) -> tuple[bool, str]:
    """Execute one optimize operation. Returns (success, message)."""
    if dry_run:
        return True, f"[dry-run] would run: {op.label}"

    if op.key == "dns-flush":
        return _run_subprocess(["ipconfig", "/flushdns"], op)

    if op.key == "thumbnail-cache":
        return _clean_junk_category("thumbnail-cache", op)

    if op.key == "prefetch":
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        prefetch = __import__("pathlib").Path(sys_root) / "Prefetch"
        return _delete_dir_contents(prefetch, op)

    if op.key == "update-cache":
        return _clean_junk_category("windows-update-cache", op)

    if op.key == "dism-cleanup":
        return _run_subprocess(
            ["DISM", "/Online", "/Cleanup-Image", "/StartComponentCleanup"],
            op,
            timeout=600,
        )

    return False, f"Unknown operation: {op.key}"


# ---------------------------------------------------------------------------
# helpers

def _run_subprocess(
    cmd: list[str],
    op: OptimizeOp,
    timeout: int = 60,
) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        ok = result.returncode == 0
        msg = (result.stdout or result.stderr or "").strip()
        if ok:
            audit(f"OPTIMIZE {op.key}: {msg or 'ok'}")
        return ok, msg or ("ok" if ok else f"exit {result.returncode}")
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {timeout}s"
    except OSError as exc:
        return False, str(exc)


def _clean_junk_category(key: str, op: OptimizeOp) -> tuple[bool, str]:
    from .junk import clean
    result = clean(only={key}, dry_run=False)
    if result.items:
        audit(f"OPTIMIZE {op.key}: {result.items} items, {result.bytes_freed} bytes freed")
    msg = f"{result.items} items freed"
    if result.skipped:
        msg += f" ({len(result.skipped)} skipped)"
    return True, msg


def _delete_dir_contents(path, op: OptimizeOp) -> tuple[bool, str]:
    """Delete all direct children of path via the safety layer."""
    from .junk import _dir_size
    from .safety import ProtectedPathError, trash
    if not path.exists():
        return True, "directory not found (nothing to do)"
    freed = 0
    count = 0
    skipped = 0
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        return False, str(exc)
    for entry in entries:
        try:
            size = _dir_size(entry) if entry.is_dir() else entry.stat().st_size
            trash(entry, allow_subtrees=[path], dry_run=False)
            freed += size
            count += 1
        except (ProtectedPathError, OSError):
            skipped += 1
    audit(f"OPTIMIZE {op.key}: {count} items, {freed} bytes freed")
    msg = f"{count} items freed"
    if skipped:
        msg += f" ({skipped} skipped)"
    return True, msg
