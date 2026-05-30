"""Small shared TUI building blocks."""

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical


def usage_gauge(percent: float, width: int = 30) -> Text:
    """A coloured block-bar gauge for a 0–100% value (theme-matched hex)."""
    pct = max(0.0, min(100.0, percent))
    filled = int(round(pct / 100 * width))
    color = "#f7768e" if pct >= 90 else "#e0af68" if pct >= 75 else "#9ece6a"
    bar = Text()
    bar.append("━" * filled, style=color)
    bar.append("━" * (width - filled), style="#3b4261")
    bar.append(f"  {pct:.0f}%", style=f"bold {color}")
    return bar


class Panel(Vertical):
    """A titled, rounded content card. Set the title via `border_title`."""

    def __init__(self, *children, title: str = "", **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self.add_class("panel")
        if title:
            self.border_title = title
