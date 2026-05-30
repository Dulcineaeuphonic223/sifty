"""Small shared TUI building blocks."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical


def usage_gauge(percent: float, width: int = 28) -> Text:
    """A coloured block-bar gauge for a 0–100% value."""
    pct = max(0.0, min(100.0, percent))
    filled = int(round(pct / 100 * width))
    color = "red" if pct >= 90 else "yellow" if pct >= 75 else "green"
    bar = Text()
    bar.append("█" * filled, style=color)
    bar.append("░" * (width - filled), style="grey37")
    bar.append(f"  {pct:.0f}%", style=f"bold {color}")
    return bar


class Panel(Vertical):
    """A titled, rounded content card. Set the title via `border_title`."""

    def __init__(self, *children, title: str = "", **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.add_class("panel")
        if title:
            self.border_title = title
