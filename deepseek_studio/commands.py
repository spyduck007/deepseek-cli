"""Command parsing and lightweight command metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    """Metadata for a slash command shown in help/autocomplete."""

    name: str
    description: str
    takes_arg: bool = False


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("/agent", "Toggle agent tools."),
    CommandSpec("/chat", "Switch to chat-only mode."),
    CommandSpec("/search", "Toggle DeepSeek web search."),
    CommandSpec("/think", "Toggle DeepSeek reasoning."),
    CommandSpec("/thinkstream", "Show reasoning text or animation only."),
    CommandSpec("/workspace", "Show or change the active workspace.", takes_arg=True),
    CommandSpec("/tools", "List available agent tools."),
    CommandSpec("/new", "Start a new chat session."),
    CommandSpec("/clear", "Clear the transcript."),
    CommandSpec("/help", "Show command help."),
    CommandSpec("/quit", "Exit DeepSeek Terminal Studio."),
    CommandSpec("/exit", "Exit DeepSeek Terminal Studio."),
)

EXIT_COMMANDS = {"/quit", "/exit"}
SUPPORTED_COMMANDS = {command.name for command in COMMANDS}


def normalize_command(command: str) -> str:
    return command.strip().lower()


def split_command(raw_command: str) -> tuple[str, str]:
    """Return (/command, argument text)."""
    stripped = raw_command.strip()
    if not stripped:
        return "", ""
    head, _, tail = stripped.partition(" ")
    return head.lower(), tail.strip()


def _slash_prefix(text: str) -> tuple[str, str] | None:
    """Return (leading whitespace, command prefix) if text is a completable command."""
    stripped_left = text.lstrip()
    leading = text[: len(text) - len(stripped_left)]

    if not stripped_left.startswith("/") or "\n" in stripped_left:
        return None

    head, sep, _tail = stripped_left.partition(" ")
    if sep:
        # The command is already complete enough that the user is typing arguments.
        return None
    return leading, head.lower()


def matching_commands(text: str) -> list[CommandSpec]:
    """Return commands that match the currently typed slash-command prefix."""
    prefix = _slash_prefix(text)
    if prefix is None:
        return []

    _leading, head = prefix
    if not head:
        return []
    return [command for command in COMMANDS if command.name.startswith(head)]


def command_menu(text: str, *, limit: int = 7) -> str:
    """Return a compact floating slash-command menu."""
    matches = matching_commands(text)
    if not matches:
        return ""

    shown = matches[:limit]
    rows = ["Slash commands   Tab completes best match"]
    for index, command in enumerate(shown):
        marker = "▶" if index == 0 else " "
        arg = " <path>" if command.takes_arg else ""
        rows.append(f"{marker} {command.name + arg:<18} {command.description}")

    remaining = len(matches) - len(shown)
    if remaining > 0:
        rows.append(f"  +{remaining} more — keep typing to narrow")
    return "\n".join(rows)


def complete_command(text: str) -> str | None:
    """Complete the slash command currently being typed with the best match."""
    prefix = _slash_prefix(text)
    if prefix is None:
        return None

    leading, head = prefix
    matches = matching_commands(text)
    if not matches:
        return None

    command = matches[0]
    completed = command.name + " "
    if not command.takes_arg:
        # Leave a space anyway so the command feels visibly completed before submit.
        completed = command.name + " "
    if completed.strip() == head:
        return None
    return leading + completed
