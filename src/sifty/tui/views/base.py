"""Shared base for content views."""

from __future__ import annotations

from textual.containers import VerticalScroll


class BaseView(VerticalScroll):
    """A scrollable content view mounted into the main content pane.

    Views load their data in background workers; tests disable that by setting
    ``app.start_workers = False`` and call the ``_populate`` methods directly.
    """

    def workers_enabled(self) -> bool:
        return getattr(self.app, "start_workers", True)
