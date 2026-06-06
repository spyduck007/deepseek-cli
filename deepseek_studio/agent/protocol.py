"""Prompt protocol and response parsing for agent mode."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


AGENT_SYSTEM_PROMPT = """
You are DeepSeek Studio Agent, a terminal coding and automation agent.

You are working inside this workspace:
{workspace}

You can inspect files, edit files, and run shell commands through tools. Use tools whenever you need filesystem context, tests, builds, searches, or command output. You may solve coding tasks, build apps, debug projects, and work on CTF-style challenge files in this workspace.

Important operating rules:
- Stay inside the workspace unless the user explicitly asks otherwise. File tools enforce this.
- Make one tool call per response. After the tool result, continue with another tool call or finish.
- Keep commands non-interactive. Use timeouts and flags that avoid prompts.
- Prefer reading/searching before editing.
- After code changes, run the smallest useful test/build/lint command you can find.
- Do not reveal private chain-of-thought. Use the status field for a short visible progress note only.
- Your response must be exactly one JSON object and nothing else. No markdown fences.

Tool response format:
{{
  "status": "short visible summary of what you are doing",
  "tool": {{
    "name": "tool_name",
    "args": {{}}
  }}
}}

Final response format:
{{
  "final": "clear final answer for the user, including what changed, tests run, and any caveats"
}}

Available tools:
{tool_schemas}
""".strip()


@dataclass(frozen=True)
class AgentAction:
    """A parsed agent decision."""

    status: str = ""
    final: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None

    @property
    def is_final(self) -> bool:
        return self.final is not None

    @property
    def is_tool_call(self) -> bool:
        return self.tool_name is not None


class AgentParseError(ValueError):
    """Raised when the model does not follow the JSON action protocol."""


def parse_agent_action(text: str) -> AgentAction:
    """Parse a model response into an AgentAction.

    The prompt asks for bare JSON, but this parser is intentionally tolerant of
    fenced JSON and small amounts of surrounding text so one bad token doesn't
    derail the whole agent loop.
    """
    data = _parse_json_object(text)

    final = data.get("final")
    if isinstance(final, str):
        return AgentAction(status=str(data.get("status", "") or ""), final=final)

    # DeepSeek sometimes drifts to an action/content shape even when asked for
    # {"final": "..."}. Accept it instead of wasting another agent step.
    action = data.get("action")
    content = data.get("content")
    if isinstance(action, str) and action.lower() == "final" and isinstance(content, str):
        return AgentAction(status=str(data.get("status", "") or ""), final=content)

    tool = data.get("tool")
    if isinstance(tool, dict):
        name = tool.get("name")
        args = tool.get("args", {})
        if not isinstance(name, str) or not name.strip():
            raise AgentParseError("Tool call is missing tool.name")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise AgentParseError("tool.args must be an object")
        return AgentAction(status=str(data.get("status", "") or ""), tool_name=name.strip(), tool_args=args)

    # Friendly support for flatter JSON if the model drifts a little.
    name = data.get("tool_name") or data.get("name")
    args = data.get("tool_args") or data.get("args") or {}
    if isinstance(name, str) and isinstance(args, dict):
        return AgentAction(status=str(data.get("status", "") or ""), tool_name=name.strip(), tool_args=args)

    raise AgentParseError("Response JSON must contain either final or tool")


def make_initial_agent_prompt(workspace: str, tool_schemas: str, user_task: str) -> str:
    return (
        AGENT_SYSTEM_PROMPT.format(workspace=workspace, tool_schemas=tool_schemas)
        + "\n\nUser task:\n"
        + user_task.strip()
        + "\n\nStart now. Respond using the JSON protocol."
    )


def make_tool_result_prompt(tool_name: str, result_text: str) -> str:
    return (
        "Tool result for "
        + tool_name
        + ":\n"
        + result_text
        + "\n\nContinue. Respond with exactly one JSON object: either the next tool call or final."
    )


def make_parse_error_prompt(raw_response: str, error: str) -> str:
    clipped = raw_response[-4000:]
    return (
        "Your previous response did not follow the required JSON protocol.\n"
        + f"Parse error: {error}\n\n"
        + "Previous response excerpt:\n"
        + clipped
        + "\n\nRespond again with exactly one JSON object and no markdown."
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    candidates = _json_candidates(text)
    errors: list[str] = []
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(parsed, dict):
            return parsed
        errors.append("top-level JSON was not an object")
    raise AgentParseError("Could not parse JSON object" + (f": {errors[-1]}" if errors else ""))


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []
    if stripped:
        candidates.append(stripped)

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.IGNORECASE | re.DOTALL)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first : last + 1].strip())

    # Preserve order while removing duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique
