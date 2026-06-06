"""Data models shared between the client, agent, and TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChatState:
    session_id: str | None = None
    parent_message_id: int | None = None
    thinking_enabled: bool = False
    thinking_stream_enabled: bool = True
    agent_enabled: bool = True
    busy: bool = False
    messages_sent: int = 0
    last_status: str = "Booting"
    workspace: str = field(default_factory=lambda: str(Path.cwd()))
    search_enabled: bool = False
    token_backend: str = "estimate"
    token_backend_detail: str = "character ratio"
    current_prompt_tokens: int = 0
    current_response_tokens: int = 0
    current_thinking_tokens: int = 0
    session_prompt_tokens: int = 0
    session_response_tokens: int = 0
    session_thinking_tokens: int = 0

    @property
    def current_total_tokens(self) -> int:
        return self.current_prompt_tokens + self.current_response_tokens + self.current_thinking_tokens

    @property
    def session_total_tokens(self) -> int:
        return self.session_prompt_tokens + self.session_response_tokens + self.session_thinking_tokens

    def reset_current_token_usage(self) -> None:
        self.current_prompt_tokens = 0
        self.current_response_tokens = 0
        self.current_thinking_tokens = 0

    def reset_session_token_usage(self) -> None:
        self.reset_current_token_usage()
        self.session_prompt_tokens = 0
        self.session_response_tokens = 0
        self.session_thinking_tokens = 0


@dataclass(frozen=True)
class StreamEvent:
    # Common kinds: status, thinking_start, thinking, response, agent_final,
    # message_id, activity_start, activity_stop, usage_thinking, tool, agent,
    # error, done.
    kind: str
    text: str = ""
