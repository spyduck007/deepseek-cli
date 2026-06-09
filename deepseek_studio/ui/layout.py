"""Composition helpers for the Textual UI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Static

from ..constants import TAGLINE
from .widgets import PromptTextArea


def compose_shell() -> ComposeResult:
    """Yield the stable application layout."""
    yield Header(show_clock=True)
    with Horizontal(id="main"):
        with VerticalScroll(id="sidebar"):
            yield Static("DeepSeek Studio", id="simple-title")
            yield Static(TAGLINE, id="tagline")
            yield Static("", id="status-card")
            yield Static("", id="token-card")
        with Vertical(id="chat-shell"):
            with VerticalScroll(id="transcript"):
                pass
            with Container(id="composer"):
                yield Static("MESSAGE  ·  Enter adds new line  ·  Ctrl+Enter sends", id="composer-title")
                prompt = PromptTextArea("", id="prompt")
                prompt.show_line_numbers = False
                prompt.soft_wrap = True
                yield prompt
                yield Static("", id="command-menu")
