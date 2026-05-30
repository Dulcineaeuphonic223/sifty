"""Home dashboard: volume gauges + reclaimable-junk total."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widgets import Label, Static

from ...commands import disk, junk
from ...console import human_size
from ..widgets import Panel, usage_gauge
from .base import BaseView


class HomeView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Overview", classes="title")
        yield Panel(Static("Reading volumes…", id="vol-body"), title="Volumes")
        yield Panel(Label("Reclaimable junk: …", id="junk-total"), title="Junk")

    def on_mount(self) -> None:
        self._render_volumes()  # fast (psutil), no worker needed
        if self.workers_enabled():
            self.compute_junk_total()

    def _render_volumes(self) -> None:
        text = Text()
        for i, v in enumerate(disk.volumes()):
            if i:
                text.append("\n\n")
            text.append(
                f"{v.mountpoint}   {human_size(v.used)} / {human_size(v.total)}"
                f"   ({human_size(v.free)} free)\n",
                style="bold",
            )
            text.append(usage_gauge(v.percent))
        self.query_one("#vol-body", Static).update(text)

    @work(thread=True, exclusive=True)
    def compute_junk_total(self) -> None:
        try:
            total = sum(cat.size for cat in junk.scan())
        except Exception:
            return
        self.app.call_from_thread(self._set_junk_total, total)

    def _set_junk_total(self, total: int) -> None:
        try:
            self.query_one("#junk-total", Label).update(
                f"Reclaimable junk: [b]{human_size(total)}[/b]  "
                f"[dim](open the Junk screen to clean)[/dim]"
            )
        except Exception:
            pass
