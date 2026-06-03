"""Sifty command-line entry point (thin: wires command groups, calls core)."""

from __future__ import annotations

import sys

import typer

from .. import __version__
from ..console import confirm, console, error, human_size, success, warn
from ..core import history, profiles, undo
from ..core import junk as core_junk
from ..infra.logging import get_logger, log_file, setup_logging
from ..windows.admin import is_admin, relaunch_as_admin
from . import output
from .commands import (
    ai_group, apps, cleanup, disk, junk, organize, profile, schedule, services,
    startup, updates, watch,
)

app = typer.Typer(
    name="sifty",
    help="Sifty — AI-assisted Windows maintenance: junk, disk, apps, updates, files.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(junk.app, name="junk")
app.add_typer(disk.app, name="disk")
app.add_typer(cleanup.app, name="cleanup")
app.add_typer(apps.app, name="apps")
app.add_typer(startup.app, name="startup")
app.add_typer(services.app, name="services")
app.add_typer(profile.app, name="profile")
app.add_typer(schedule.app, name="schedule")
app.add_typer(updates.app, name="update")
app.add_typer(organize.app, name="organize")
app.add_typer(watch.app, name="watch")
app.add_typer(ai_group.app, name="ai")


@app.callback()
def main(
    admin: bool = typer.Option(
        False, "--admin", "--elevate",
        help="Relaunch elevated (UAC) so admin-only tasks can run.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Also write debug logs to stderr.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON (read-only commands).",
    ),
) -> None:
    """Sifty — AI-assisted Windows maintenance."""
    setup_logging(verbose)
    output.set_json(json_output)
    get_logger("sifty.cli").debug("invoked: %s", " ".join(sys.argv[1:]))
    if admin and not is_admin():
        if relaunch_as_admin():
            raise typer.Exit()  # elevated process takes over in a new window
        warn("Elevation was declined; continuing without administrator rights.")


@app.command("tui")
def tui_cmd() -> None:
    """Launch the interactive full-screen TUI."""
    from ..tui.app import run  # lazy import: keeps CLI startup fast

    run()


@app.command("monitor")
def monitor_cmd() -> None:
    """Live system monitor: CPU, memory, disk I/O, network, processes. Ctrl+C to stop."""
    from rich.columns import Columns
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from ..core.monitor import SystemSnapshot, fmt_rate, snapshot
    from ..tui.widgets import usage_gauge

    def _gauge_panel(title: str, pct: float) -> Panel:
        color = "#f7768e" if pct >= 90 else "#e0af68" if pct >= 75 else "#9ece6a"
        body = Text()
        body.append(f"{pct:.0f}%\n", style=f"bold {color}")
        body.append(usage_gauge(pct, width=36))
        return Panel(body, title=title, border_style="#7aa2f7")

    def _io_panel(title: str, label_a: str, val_a: int, label_b: str, val_b: int) -> Panel:
        body = Text()
        body.append(f"{label_a}  ", style="bold #7dcfff")
        body.append(fmt_rate(val_a) + "\n")
        body.append(f"{label_b}  ", style="bold #9ece6a")
        body.append(fmt_rate(val_b))
        return Panel(body, title=title, border_style="#7aa2f7")

    def _proc_table(snap: SystemSnapshot) -> Table:
        table = Table(show_header=True, header_style="bold #7dcfff", box=None, padding=(0, 1))
        table.add_column("Process", min_width=28)
        table.add_column("PID", justify="right", min_width=7)
        table.add_column("CPU %", justify="right", min_width=7)
        table.add_column("Memory", justify="right", min_width=10)
        for p in snap.processes:
            color = "#f7768e" if p.cpu_percent >= 50 else "#e0af68" if p.cpu_percent >= 20 else ""
            cpu_cell = Text(f"{p.cpu_percent:.1f}%", style=color) if color else f"{p.cpu_percent:.1f}%"
            mem = f"{p.memory_mb:.0f} MB" if p.memory_mb >= 1 else f"{p.memory_mb * 1024:.0f} KB"
            table.add_row(p.name, str(p.pid), cpu_cell, mem)
        return table

    def _render(snap: SystemSnapshot):
        from rich.console import Group
        return Group(
            Columns([
                _gauge_panel("CPU", snap.cpu_percent),
                _gauge_panel(
                    f"Memory  {snap.memory_used_gb:.1f}/{snap.memory_total_gb:.1f} GB",
                    snap.memory_percent,
                ),
            ]),
            Columns([
                _io_panel("Disk I/O", "↓ Read ", snap.disk_read_bytes, "↑ Write", snap.disk_write_bytes),
                _io_panel("Network", "↑ Sent ", snap.net_sent_bytes, "↓ Recv ", snap.net_recv_bytes),
            ]),
            Panel(_proc_table(snap), title="Top processes", border_style="#7aa2f7"),
            Text("  Ctrl+C to stop", style="dim"),
        )

    # Show a placeholder until the first real snapshot arrives.
    first = snapshot()   # snapshot() blocks ~1 s (cpu_percent interval=1)
    with Live(_render(first), auto_refresh=False, console=console) as live:
        try:
            while True:
                snap = snapshot()
                live.update(_render(snap), refresh=True)
        except KeyboardInterrupt:
            pass


@app.command("version")
def version_cmd() -> None:
    """Show the Sifty version."""
    console.print(f"Sifty {__version__}")


@app.command("doctor")
def doctor_cmd() -> None:
    """Report environment readiness (admin rights, winget, Ollama)."""
    from ..ai.client import OllamaClient
    from ..windows import winget

    admin = is_admin()
    has_winget = winget.available()
    client = OllamaClient.from_config()
    ollama = client.is_available()
    if output.json_enabled():
        output.emit({
            "administrator": admin,
            "winget": has_winget,
            "ollama_model": client.model,
            "ollama_reachable": ollama,
            "log_file": str(log_file()),
        })
        return
    console.print(f"Administrator: {'[green]yes[/green]' if admin else '[yellow]no[/yellow] (some junk/uninstall actions need it)'}")
    console.print(f"winget: {'[green]available[/green]' if has_winget else '[red]missing[/red]'}")
    console.print(f"Ollama ({client.model}): {'[green]reachable[/green]' if ollama else '[yellow]not running[/yellow]'}")
    console.print(f"Log file: [dim]{log_file()}[/dim]")


@app.command("logs")
def logs_cmd(
    tail: int = typer.Option(40, "--tail", "-n", help="Show the last N lines."),
    path_only: bool = typer.Option(False, "--path", help="Print the log file path only."),
) -> None:
    """Show the diagnostics log (location and recent lines)."""
    path = log_file()
    if path_only:
        console.print(str(path))
        return
    if not path.exists():
        console.print("No log file yet — nothing has been logged.")
        return
    console.print(f"[dim]{path}[/dim]\n")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-tail:]:
        console.print(line, markup=False, highlight=False)


@app.command("clean")
def clean_cmd(
    profile_name: str = typer.Option(..., "--profile", "-p", help="Cleanup profile to run."),
    apply: bool = typer.Option(False, "--apply", help="Actually move items to the Recycle Bin."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Run a saved cleanup profile (used by scheduled tasks)."""
    prof = profiles.get(profile_name)
    if prof is None:
        error(f"No profile named '{profile_name}'. See `sifty profile list`.")
        raise typer.Exit(1)
    only = set(prof.categories) or None

    preview = core_junk.clean(only=only, dry_run=True)
    if preview.items == 0:
        success("Nothing to clean — already tidy.")
        return
    console.print(
        f"Profile [bold]{profile_name}[/bold]: {preview.items:,} items "
        f"({human_size(preview.bytes_freed)})."
    )
    if not apply:
        console.print("[dim]Dry-run — re-run with --apply to remove.[/dim]")
        return
    if not confirm(f"Move {preview.items:,} items ({human_size(preview.bytes_freed)}) to the Recycle Bin?", assume_yes=yes):
        warn("Cancelled.")
        return
    result = core_junk.clean(only=only, dry_run=False)
    history.record_clean(f"profile:{profile_name}", ",".join(sorted(prof.categories)),
                         result.bytes_freed, result.items, result.trashed)
    success(f"Sent {result.items:,} items ({human_size(result.bytes_freed)}) to the Recycle Bin.")


@app.command("history")
def history_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="How many recent runs to show."),
) -> None:
    """Show what Sifty has cleaned and how much space it reclaimed."""
    from rich.table import Table

    runs = history.recent_runs(limit)
    summ = history.summary()

    if output.json_enabled():
        output.emit({
            "summary": summ,
            "runs": [
                {"id": r.id, "ts": r.ts, "action": r.action, "detail": r.detail,
                 "bytes_freed": r.bytes_freed, "items": r.items,
                 "success": r.success, "restorable": r.restorable}
                for r in runs
            ],
        })
        return

    console.print(
        f"[bold]{summ['runs']}[/bold] runs · [bold]{human_size(summ['bytes_freed'])}[/bold] "
        f"reclaimed · [bold]{summ['items']:,}[/bold] items\n"
    )
    if not runs:
        console.print("No history yet — run [cyan]sifty junk clean --apply[/cyan] first.")
        return
    table = Table(title="Recent runs")
    table.add_column("When (UTC)", style="dim")
    table.add_column("Action")
    table.add_column("Detail", style="dim")
    table.add_column("Items", justify="right")
    table.add_column("Freed", justify="right")
    table.add_column("Restorable", justify="right")
    for r in runs:
        table.add_row(r.ts, r.action, r.detail, f"{r.items:,}",
                      human_size(r.bytes_freed), str(r.restorable) if r.restorable else "—")
    console.print(table)


@app.command("undo")
def undo_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Restore the items from the most recent clean (from the Recycle Bin)."""
    run = undo.last_undoable()
    if run is None:
        console.print("Nothing to undo — no restorable items in history.")
        return
    if not confirm(
        f"Restore {run.restorable} item(s) from the {run.action} clean at {run.ts}?",
        assume_yes=yes,
    ):
        warn("Cancelled.")
        return
    with console.status("Restoring from the Recycle Bin…"):
        restored, failed = undo.undo(run.id)
    success(f"Restored {restored} item(s).")
    if failed:
        warn(f"{failed} item(s) could not be restored (see `sifty logs`).")


def entrypoint() -> None:
    """Console-script entry point: set up logging and capture fatal crashes."""
    setup_logging()
    try:
        app()
    except SystemExit:
        raise  # normal Typer/Click exit
    except KeyboardInterrupt:
        raise
    except Exception:
        get_logger("sifty.cli").exception("Fatal error")
        error(f"Sifty hit an unexpected error. Details written to {log_file()}")
        raise SystemExit(1)


if __name__ == "__main__":
    entrypoint()
