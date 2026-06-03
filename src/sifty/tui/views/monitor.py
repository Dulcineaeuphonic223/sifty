"""Monitor screen: live CPU, memory, disk I/O, network, and process list."""

from __future__ import annotations

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Static

from ...core.monitor import SystemSnapshot, fmt_rate, snapshot
from ..widgets import Panel, usage_gauge
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class MonitorView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("System monitor", classes="title")
        with Horizontal(classes="stat-row"):
            yield Panel(Static("…", id="mon-cpu"), title="CPU")
            yield Panel(Static("…", id="mon-mem"), title="Memory")
        with Horizontal(classes="stat-row"):
            yield Panel(Static("…", id="mon-disk"), title="Disk I/O")
            yield Panel(Static("…", id="mon-net"), title="Network")
        yield Panel(DataTable(id="mon-procs"), title="Top processes")

    def on_mount(self) -> None:
        table = self.query_one("#mon-procs", DataTable)
        table.cursor_type = "row"
        table.add_columns("Process", "PID", "CPU %", "Memory")
        if self.workers_enabled():
            # Seed psutil's per-process CPU counters on first call (returns 0 %).
            self._refresh()
            self.set_interval(2, self._refresh)

    def _refresh(self) -> None:
        self._poll()

    @work(thread=True, exclusive=True, group="monitor-poll")
    def _poll(self) -> None:
        try:
            snap = snapshot()
        except Exception:
            logger.exception("Monitor snapshot failed")
            return
        self.app.call_from_thread(self._apply, snap)

    def _apply(self, snap: SystemSnapshot) -> None:
        self._set("mon-cpu", self._cpu_text(snap))
        self._set("mon-mem", self._mem_text(snap))
        self._set("mon-disk", self._disk_text(snap))
        self._set("mon-net", self._net_text(snap))
        self._update_procs(snap)

    # ----------------------------------------------------------------- helpers

    def _set(self, widget_id: str, content) -> None:
        try:
            self.query_one(f"#{widget_id}", Static).update(content)
        except Exception:
            pass

    @staticmethod
    def _cpu_text(snap: SystemSnapshot) -> Text:
        text = Text()
        pct = snap.cpu_percent
        color = "#f7768e" if pct >= 90 else "#e0af68" if pct >= 75 else "#9ece6a"
        text.append(f"{pct:.0f}%\n", style=f"bold {color}")
        text.append(usage_gauge(pct))
        return text

    @staticmethod
    def _mem_text(snap: SystemSnapshot) -> Text:
        text = Text()
        text.append(
            f"{snap.memory_used_gb:.1f} GB / {snap.memory_total_gb:.1f} GB\n",
            style="bold",
        )
        text.append(usage_gauge(snap.memory_percent))
        return text

    @staticmethod
    def _disk_text(snap: SystemSnapshot) -> Text:
        text = Text()
        text.append("↓ Read   ", style="bold #7dcfff")
        text.append(fmt_rate(snap.disk_read_bytes) + "\n")
        text.append("↑ Write  ", style="bold #9ece6a")
        text.append(fmt_rate(snap.disk_write_bytes))
        return text

    @staticmethod
    def _net_text(snap: SystemSnapshot) -> Text:
        text = Text()
        text.append("↑ Sent   ", style="bold #9ece6a")
        text.append(fmt_rate(snap.net_sent_bytes) + "\n")
        text.append("↓ Recv   ", style="bold #7dcfff")
        text.append(fmt_rate(snap.net_recv_bytes))
        return text

    def _update_procs(self, snap: SystemSnapshot) -> None:
        table = self.query_one("#mon-procs", DataTable)
        table.clear()
        for p in snap.processes:
            cpu_color = (
                "#f7768e" if p.cpu_percent >= 50
                else "#e0af68" if p.cpu_percent >= 20
                else "$text"
            )
            cpu_cell = Text(f"{p.cpu_percent:.1f}", style=cpu_color)
            mem_str = f"{p.memory_mb:.0f} MB" if p.memory_mb >= 1 else f"{p.memory_mb * 1024:.0f} KB"
            table.add_row(p.name, str(p.pid), cpu_cell, mem_str)
