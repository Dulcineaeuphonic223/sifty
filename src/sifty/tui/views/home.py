"""Home dashboard: the health checkup front and center, plus volume gauges.

The checkup hero runs the read-only ``core.checkup`` suite; each finding
renders with an action button that **fixes it right here** where that is safe
(clean junk, clean stale downloads, apply updates — each behind the usual
confirm modal) and deep-links to the owning screen where a human should review
first (registry orphans, disk space, startup). No duplicate stat cards: the
sidebar already covers per-domain detail.
"""

from __future__ import annotations

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from ...console import human_size
from ...core import checkup, cleanup, disk, history, junk, updates
from ...core.checkup import Finding
from ...windows.admin import is_admin
from ..modals import ConfirmModal
from ..widgets import Panel, usage_gauge
from .base import BaseView

logger = logging.getLogger("sifty.tui")

_SEVERITY_DOT = {"ok": "[green]●[/green]", "info": "[yellow]●[/yellow]",
                 "attention": "[red]●[/red]"}

# Domains whose finding can be fixed directly from Home (behind a confirm).
# Everything else navigates to its screen for review via the finding's
# action_key.
_DIRECT_FIX_LABELS = {
    "junk": "Clean junk…",
    "stale": "Clean downloads…",
    "updates": "Update all…",
}


class HomeView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Overview", classes="title")
        if is_admin():
            yield Static("[green]●[/green] Administrator — all tasks available.",
                         classes="subtle")
        else:
            yield Static(
                "[yellow]●[/yellow] Standard user — some tasks need elevation.  "
                "[@click=app.elevate][b]Elevate (F2)[/b][/]",
                classes="subtle",
            )
        with Panel(title="Health checkup", id="checkup-panel"):
            yield Static(
                "Scan everything at once — junk, updates, registry orphans, stale "
                "downloads, disk space, startup — then fix it from right here.",
                classes="subtle",
            )
            with Horizontal(classes="actions"):
                yield Button("Run checkup", id="run-checkup", variant="primary")
            yield Vertical(id="checkup-results")
        yield Panel(Static("Reading volumes…", id="vol-body"), title="Volumes")

    def on_mount(self) -> None:
        self._findings: dict[str, Finding] = {}
        self._render_volumes()  # fast (psutil), no worker needed

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "run-checkup":
            event.button.disabled = True
            results = self.query_one("#checkup-results", Vertical)
            await results.remove_children()
            await results.mount(Static("[dim]Running checkup…[/dim]", classes="subtle"))
            self.run_checkup_worker()
        elif bid.startswith("fix-"):
            domain = bid.removeprefix("fix-")
            if domain in _DIRECT_FIX_LABELS:
                self._fix_flow(domain)
            else:
                finding = self._findings.get(domain)
                if finding is not None and finding.action_key:
                    await self.app.show(finding.action_key)

    # ----------------------------------------------------------------- checkup
    @work(thread=True, exclusive=True, group="home-checkup")
    def run_checkup_worker(self) -> None:
        try:
            findings = checkup.run_checkup()
        except Exception:
            logger.exception("Home: checkup failed")
            findings = []
        self.app.call_from_thread(self._show_findings, findings)

    async def _show_findings(self, findings: list[Finding]) -> None:
        try:
            self.query_one("#run-checkup", Button).disabled = False
            results = self.query_one("#checkup-results", Vertical)
        except Exception:
            return  # view was navigated away mid-scan
        self._findings = {f.domain: f for f in findings}
        await results.remove_children()
        if not findings:
            await results.mount(Static("Checkup failed — see `sifty logs`.", classes="subtle"))
            return
        for f in findings:
            dot = _SEVERITY_DOT.get(f.severity, "")
            row = Horizontal(classes="finding-row", id=f"finding-{f.domain}")
            await results.mount(row)
            await row.mount(
                Static(f"{dot} [b]{f.label}[/b] — {f.summary}", classes="finding-text")
            )
            if f.severity != "ok" and f.action_key:
                label = _DIRECT_FIX_LABELS.get(f.domain, f.action_label or "Review…")
                await row.mount(Button(label, id=f"fix-{f.domain}", classes="fix"))
        issues = sum(1 for f in findings if f.severity != "ok")
        verdict = (f"[b]{issues}[/b] item(s) worth a look." if issues
                   else "[green]All clear — nothing needs attention.[/green]")
        await results.mount(Static(verdict, classes="status"))

    # -------------------------------------------------------------- direct fix
    @work
    async def _fix_flow(self, domain: str) -> None:
        finding = self._findings.get(domain)
        summary = finding.summary if finding else ""
        prompts = {
            "junk": f"Move all junk ({summary}) to the Recycle Bin?",
            "stale": f"Send the stale Downloads items ({summary}) to the Recycle Bin?",
            "updates": f"Upgrade everything via winget ({summary})? This can take a while.",
        }
        ok = await self.app.push_screen_wait(
            ConfirmModal(prompts[domain], confirm_label="Proceed")
        )
        if not ok:
            return
        self._set_row(domain, "[dim]working…[/dim]", drop_button=True)
        self.run_fix(domain)

    @work(thread=True, group="home-fix")
    def run_fix(self, domain: str) -> None:
        try:
            if domain == "junk":
                result = junk.clean(dry_run=False)
                for reason in result.skipped:
                    logger.warning("checkup junk clean skipped: %s", reason)
                history.record_clean("junk", "checkup", result.bytes_freed,
                                     result.items, result.trashed)
                outcome = (f"[green]✓[/green] sent {result.items:,} items "
                           f"({human_size(result.bytes_freed)}) to the Recycle Bin")
                if result.skipped:
                    outcome += f" · {len(result.skipped)} skipped (in use / need admin)"
            elif domain == "stale":
                stale = cleanup.find_stale_downloads()
                result = cleanup.trash_paths([p for p, _s, _m in stale], dry_run=False)
                history.record_clean("cleanup-stale", "checkup", result.bytes_freed,
                                     result.items, result.trashed)
                outcome = (f"[green]✓[/green] sent {result.items:,} items "
                           f"({human_size(result.bytes_freed)}) to the Recycle Bin")
            elif domain == "updates":
                code = updates.apply_upgrades()
                outcome = ("[green]✓[/green] winget upgrade finished"
                           if code == 0 else f"[yellow]⚠[/yellow] winget exited with code {code}")
            else:  # pragma: no cover - guarded by _DIRECT_FIX_LABELS
                return
        except Exception as exc:
            logger.exception("Home: fix %s failed", domain)
            outcome = f"[red]✗ failed:[/red] {exc}"
        self.app.call_from_thread(self._fix_done, domain, outcome)

    def _set_row(self, domain: str, suffix: str, *, drop_button: bool = False) -> None:
        finding = self._findings.get(domain)
        label = finding.label if finding else domain
        try:
            row = self.query_one(f"#finding-{domain}", Horizontal)
        except Exception:
            return  # navigated away
        row.query_one(".finding-text", Static).update(f"[b]{label}[/b] — {suffix}")
        if drop_button:
            for btn in row.query(Button):
                btn.remove()

    def _fix_done(self, domain: str, outcome: str) -> None:
        self._set_row(domain, outcome, drop_button=True)
        finding = self._findings.get(domain)
        self.app.notify(f"{finding.label if finding else domain}: done.", title="Checkup")

    # ----------------------------------------------------------------- volumes
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
