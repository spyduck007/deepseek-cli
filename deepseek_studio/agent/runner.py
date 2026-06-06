"""Agent execution loop."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from ..models import StreamEvent
from ..services.client import DeepSeekClient
from .protocol import (
    AgentParseError,
    make_initial_agent_prompt,
    make_parse_error_prompt,
    make_tool_result_prompt,
    parse_agent_action,
)
from .tools import ToolRegistry, ToolResult


class AgentRunner:
    """Runs the model/tool/model loop for agent mode."""

    def __init__(self, client: DeepSeekClient, tools: ToolRegistry | None = None) -> None:
        self.client = client
        self.tools = tools or ToolRegistry()

    @property
    def workspace(self) -> Path:
        return self.tools.workspace

    def set_workspace(self, workspace: str | Path) -> None:
        self.tools.set_workspace(workspace)

    def tool_help(self) -> str:
        return self.tools.schema_text()

    def run(
        self,
        session_id: str,
        task: str,
        *,
        thinking_enabled: bool = False,
        stream_thinking: bool = True,
        parent_id: int | None = None,
        search_enabled: bool = False,
    ) -> Generator[StreamEvent, None, None]:
        """Run an agent task, yielding UI events."""
        prompt = make_initial_agent_prompt(str(self.workspace), self.tools.schema_text(), task)
        parse_failures = 0
        current_parent_id = parent_id

        while True:
            yield StreamEvent("status", "Working")
            yield StreamEvent("thinking_start", "")
            yield StreamEvent("usage_prompt", prompt)
            model_text, current_parent_id = yield from self._collect_model_response(
                session_id,
                prompt,
                parent_id=current_parent_id,
                thinking_enabled=thinking_enabled,
                emit_thinking=stream_thinking,
                search_enabled=search_enabled,
            )
            yield StreamEvent("usage_response", model_text)

            try:
                action = parse_agent_action(model_text)
            except AgentParseError as exc:
                parse_failures += 1
                yield StreamEvent("tool", f"Protocol error: {exc}")
                if parse_failures >= 2:
                    yield StreamEvent(
                        "response",
                        "I could not get a valid tool/final JSON response after two tries. "
                        "Here is the last raw response:\n\n" + model_text,
                    )
                    yield StreamEvent("done", "")
                    return
                prompt = make_parse_error_prompt(model_text, str(exc))
                continue

            parse_failures = 0
            if action.status:
                yield StreamEvent("status", action.status)

            if action.is_final:
                yield StreamEvent("agent_final", action.final or "")
                yield StreamEvent("done", "")
                return

            if not action.is_tool_call:
                yield StreamEvent("agent_final", "Agent stopped without a final answer or tool call.")
                yield StreamEvent("done", "")
                return

            tool_name = action.tool_name or ""
            tool_args = action.tool_args or {}
            yield StreamEvent("status", f"Running {tool_name}")
            result = self.tools.execute(tool_name, tool_args)
            yield StreamEvent("tool", self._format_tool_result(tool_name, tool_args, result))
            prompt = make_tool_result_prompt(tool_name, result.for_model())

    def _collect_model_response(
        self,
        session_id: str,
        prompt: str,
        *,
        parent_id: int | None,
        thinking_enabled: bool,
        emit_thinking: bool,
        search_enabled: bool,
    ) -> Generator[StreamEvent, None, tuple[str, int | None]]:
        response_parts: list[str] = []
        latest_parent_id = parent_id
        hidden_response_started = False
        for event in self.client.stream_message(
            session_id,
            prompt,
            parent_id=latest_parent_id,
            thinking_enabled=thinking_enabled,
            emit_thinking=emit_thinking,
            search_enabled=search_enabled,
        ):
            if event.kind == "message_id":
                try:
                    latest_parent_id = int(event.text)
                except ValueError:
                    pass
                yield event
                continue
            if event.kind == "response":
                response_parts.append(event.text)
                if not hidden_response_started:
                    hidden_response_started = True
                    yield StreamEvent("activity_start", "Reading model action")
                continue
            if event.kind == "done":
                if hidden_response_started:
                    yield StreamEvent("activity_stop", "")
                    hidden_response_started = False
                continue
            yield event
        if hidden_response_started:
            yield StreamEvent("activity_stop", "")
        return "".join(response_parts).strip(), latest_parent_id

    @staticmethod
    def _format_tool_result(name: str, args: dict[str, object], result: ToolResult) -> str:
        icon = "✓" if result.ok else "✗"
        title = _tool_title(name, args)
        message = _summarize_tool_message(name, args, result.message, result.ok)
        return f"{icon} {title}\n{message}" if message else f"{icon} {title}"


def _tool_title(name: str, args: dict[str, object]) -> str:
    if name == "run_command":
        command = str(args.get("command", "")).strip()
        return f"run_command: {command}" if command else "run_command"
    path = args.get("path")
    if path is not None:
        return f"{name}: {path}"
    query = args.get("query")
    if query is not None:
        return f"{name}: {query}"
    return name


def _summarize_tool_message(name: str, args: dict[str, object], message: str, ok: bool) -> str:
    if not ok:
        return _clip_display(message, 1600)

    stripped = message.strip()
    if not stripped:
        return "OK"

    if name in {"write_file", "edit_file", "mkdir", "delete_path", "apply_patch", "workspace_info"}:
        return _clip_display(stripped, 700)

    if name == "read_file":
        first_line = stripped.splitlines()[0] if stripped.splitlines() else "Read file."
        return first_line

    if name == "list_files":
        lines = [line for line in stripped.splitlines() if line.strip()]
        count = max(0, len(lines) - 1) if lines else 0
        target = args.get("path", ".")
        return f"Listed {count} item{'s' if count != 1 else ''} under {target}."

    if name == "search_files":
        if stripped == "No matches.":
            return "No matches."
        count = len([line for line in stripped.splitlines() if line.strip() and not line.startswith("... truncated")])
        return f"Found {count} match{'es' if count != 1 else ''}."

    if name == "run_command":
        return _summarize_command_output(stripped)

    return _clip_display(stripped, 900)


def _summarize_command_output(message: str) -> str:
    lines = message.splitlines()
    exit_line = next((line for line in lines if line.startswith("exit_code:")), "exit_code: unknown")
    interesting: list[str] = [exit_line]

    stdout_index = _index_of(lines, "stdout:")
    stderr_index = _index_of(lines, "stderr:")
    if stdout_index is not None:
        stdout_end = stderr_index if stderr_index is not None and stderr_index > stdout_index else len(lines)
        stdout = "\n".join(lines[stdout_index + 1 : stdout_end]).strip()
        if stdout:
            interesting.append("stdout:\n" + _clip_display(stdout, 900))
    if stderr_index is not None:
        stderr = "\n".join(lines[stderr_index + 1 :]).strip()
        if stderr:
            interesting.append("stderr:\n" + _clip_display(stderr, 900))

    return "\n\n".join(interesting)


def _index_of(lines: list[str], value: str) -> int | None:
    try:
        return lines.index(value)
    except ValueError:
        return None


def _clip_display(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit].rstrip() + f"\n... hidden {omitted} characters"
