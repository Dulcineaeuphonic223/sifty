"""Sifty TUI — full-screen interactive app.

A thin frontend over the same core functions as the CLI. The sidebar selects a
content view (see ``views/``); views load their data in background workers and
route destructive actions through confirm modals + ``safety.trash()``.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Label, ListItem, ListView

from .views import VIEWS

# (nav key, sidebar label) — order defines the menu.
SECTIONS: list[tuple[str, str]] = [
    ("home", "🏠  Home"),
    ("junk", "🧹  Junk"),
    ("disk", "💾  Disk"),
    ("apps", "📦  Apps"),
    ("updates", "⬆  Updates"),
    ("ai", "🤖  AI"),
]


class SiftyApp(App):
    """The top-level Sifty terminal application."""

    CSS_PATH = "styles.tcss"
    BINDINGS = [("q", "quit", "Quit")]
    TITLE = "Sifty"
    SUB_TITLE = "Windows maintenance"

    def __init__(self, start_workers: bool = True) -> None:
        super().__init__()
        # Tests set this False to mount views without firing the slow workers.
        self.start_workers = start_workers

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield ListView(
                *[ListItem(Label(label), id=f"nav-{key}") for key, label in SECTIONS],
                id="sidebar",
            )
            yield VerticalScroll(id="content")
        yield Footer()

    async def on_mount(self) -> None:
        self.theme = "nord"
        await self.show("home")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = (event.item.id or "nav-home").removeprefix("nav-")
        await self.show(key)

    async def show(self, key: str) -> None:
        content = self.query_one("#content", VerticalScroll)
        await content.remove_children()
        view_cls = VIEWS.get(key)
        if view_cls is not None:
            await content.mount(view_cls())


def run() -> None:
    """Entry point used by the ``sifty tui`` command."""
    SiftyApp().run()
