"""Custom Textual widgets."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static, TextArea


class MessageBubble(Static):
    """A streaming message widget with role-aware styling."""

    def __init__(self, role: str, *, classes: str = "") -> None:
        super().__init__("")
        self.role = role
        self.body = Text()
        self.border_title = role.upper()
        self.add_class("message")
        self.add_class(role)
        if classes:
            for cls in classes.split():
                self.add_class(cls)

    def append(self, text: str, *, style: str = "") -> None:
        self.body.append(text, style=style)
        self.update(self.body)

    def set_text(self, text: str, *, style: str = "") -> None:
        self.body = Text(text, style=style)
        self.update(self.body)



class PromptTextArea(TextArea):
    """Multiline composer where Enter submits and Shift+Enter adds a line."""

    BINDINGS = [
        Binding("enter", "submit_prompt", "Send", show=False, priority=True),
        Binding("shift+enter", "insert_prompt_newline", "New line", show=False, priority=True),
        Binding("tab", "complete_prompt_command", "Complete command", show=False, priority=True),
    ]

    class Submitted(Message):
        """Posted when the user submits the composer."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class CompleteRequested(Message):
        """Posted when the user presses Tab in the composer."""

    def action_submit_prompt(self) -> None:
        """Submit the current text without inserting a newline."""
        self.post_message(self.Submitted(self.text))

    def action_insert_prompt_newline(self) -> None:
        """Insert a newline for multi-paragraph prompts."""
        try:
            self.insert("\n")
        except Exception:  # pragma: no cover - compatibility fallback for older Textual builds.
            self.text = f"{self.text}\n"

    def action_complete_prompt_command(self) -> None:
        """Autocomplete slash commands, otherwise insert indentation."""
        stripped = self.text.lstrip()
        if stripped.startswith("/") and "\n" not in stripped:
            self.post_message(self.CompleteRequested())
            return
        try:
            self.insert("    ")
        except Exception:  # pragma: no cover - compatibility fallback for older Textual builds.
            self.text = f"{self.text}    "

    def replace_text(self, text: str) -> None:
        """Replace the composer contents across Textual versions."""
        try:
            self.load_text(text)
        except Exception:  # pragma: no cover - compatibility fallback for older Textual builds.
            self.text = text

    def clear_text(self) -> None:
        """Clear the composer across Textual versions."""
        self.replace_text("")
