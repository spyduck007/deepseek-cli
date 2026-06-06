"""Streaming DeepSeek web chat client."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import requests

from ..constants import BASE_URL, STATIC_HEADERS
from ..models import StreamEvent
from .pow import get_pow_solver
from .tokens import load_user_token


class DeepSeekClient:
    """Minimal client for DeepSeek's web chat endpoints."""

    def __init__(self, token: str | None = None, base_url: str = BASE_URL) -> None:
        self.token = token or load_user_token()
        self.base_url = base_url.rstrip("/")

    def _headers(self, *, pow_response: str | None = None) -> dict[str, str]:
        headers = STATIC_HEADERS.copy()
        headers["Authorization"] = f"Bearer {self.token}"
        if pow_response:
            headers["x-ds-pow-response"] = pow_response
        return headers

    def get_pow_header(self, target_path: str = "/api/v0/chat/completion") -> str:
        resp = requests.post(
            f"{self.base_url}/api/v0/chat/create_pow_challenge",
            headers=self._headers(),
            json={"target_path": target_path},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        biz_data = data.get("data", {}).get("biz_data")
        if not biz_data:
            raise RuntimeError(f"Missing biz_data in PoW response: {data}")
        challenge_config = biz_data["challenge"]
        return get_pow_solver().solve_challenge(challenge_config)

    def create_session(self) -> str:
        resp = requests.post(
            f"{self.base_url}/api/v0/chat_session/create",
            headers=self._headers(),
            json={},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        session_id = data.get("data", {}).get("biz_data", {}).get("chat_session", {}).get("id")
        if not session_id:
            raise RuntimeError(f"Missing session ID: {data}")
        return session_id

    @staticmethod
    def _is_thinking_fragment(fragment_type: str | None) -> bool:
        return (fragment_type or "").upper() in {"THINK", "THINKING", "REASONING"}

    @staticmethod
    def _is_response_fragment(fragment_type: str | None) -> bool:
        return (fragment_type or "").upper() in {"RESPONSE", "ANSWER"}

    def stream_message(
        self,
        session_id: str,
        prompt: str,
        *,
        parent_id: int | None = None,
        thinking_enabled: bool = False,
        emit_thinking: bool = True,
        search_enabled: bool = False,
    ) -> Generator[StreamEvent, None, None]:
        """Yield StreamEvent objects while DeepSeek streams its answer.

        DeepSeek streams THINK content first, then appends plain string patches to
        the current fragment. Later it appends a RESPONSE fragment, and following
        string patches belong to the response. Tracking `current_fragment_type`
        is what keeps reasoning and final answer output separated.

        When ``emit_thinking`` is false, thinking chunks are not streamed to
        the TUI one-by-one. The client still asks DeepSeek to reason, shows a
        compact activity indicator, and sends one aggregate usage event when
        the thinking phase ends.
        """
        yield StreamEvent("status", "Solving proof-of-work...")
        pow_header = self.get_pow_header()
        yield StreamEvent("status", "Streaming response...")

        payload: dict[str, Any] = {
            "chat_session_id": session_id,
            "parent_message_id": parent_id,
            "model_type": "default",
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": thinking_enabled,
            "search_enabled": search_enabled,
            "action": None,
            "preempt": False,
        }

        current_fragment_type: str | None = None
        silent_thinking_active = False
        silent_thinking_parts: list[str] = []

        def start_silent_thinking() -> StreamEvent | None:
            nonlocal silent_thinking_active
            if thinking_enabled and not emit_thinking and not silent_thinking_active:
                silent_thinking_active = True
                return StreamEvent("activity_start", "Thinking")
            return None

        def stop_silent_thinking() -> list[StreamEvent]:
            nonlocal silent_thinking_active
            events: list[StreamEvent] = []
            if not silent_thinking_active:
                return events
            if silent_thinking_parts:
                events.append(StreamEvent("usage_thinking", "".join(silent_thinking_parts)))
                silent_thinking_parts.clear()
            events.append(StreamEvent("activity_stop", ""))
            silent_thinking_active = False
            return events

        def handle_thinking_text(content: str) -> Generator[StreamEvent, None, None]:
            if not thinking_enabled:
                return
            if emit_thinking:
                yield StreamEvent("thinking", content)
                return
            start_event = start_silent_thinking()
            if start_event is not None:
                yield start_event
            silent_thinking_parts.append(content)

        def events_from_fragment(frag: dict[str, Any]) -> Generator[StreamEvent, None, None]:
            nonlocal current_fragment_type
            frag_type = frag.get("type")
            if frag_type:
                current_fragment_type = str(frag_type)
            content = frag.get("content", "")
            if self._is_response_fragment(current_fragment_type):
                yield from stop_silent_thinking()
            if not content:
                return
            if self._is_thinking_fragment(current_fragment_type):
                yield from handle_thinking_text(str(content))
            elif self._is_response_fragment(current_fragment_type):
                yield StreamEvent("response", str(content))

        with requests.post(
            f"{self.base_url}/api/v0/chat/completion",
            headers=self._headers(pow_response=pow_header),
            json=payload,
            stream=True,
            timeout=120,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Completion failed: {response.status_code} {response.text}")

            current_event: str | None = None
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    if current_event == "close":
                        break
                    continue
                if not line.startswith("data:"):
                    continue

                data = self._parse_sse_data(line)
                if data is None:
                    continue

                response_id = self._extract_response_message_id(data)
                if response_id is not None:
                    yield StreamEvent("message_id", str(response_id))

                value = data.get("v")
                if isinstance(value, dict):
                    resp_obj = value.get("response")
                    fragments = resp_obj.get("fragments", []) if resp_obj else []
                    for frag in fragments:
                        if isinstance(frag, dict):
                            yield from events_from_fragment(frag)
                    continue

                if data.get("p") == "response/fragments" and isinstance(value, list):
                    for frag in value:
                        if isinstance(frag, dict):
                            yield from events_from_fragment(frag)
                    continue

                if isinstance(value, str):
                    fragment = value
                    if fragment == "FINISHED" or not fragment:
                        continue
                    path = data.get("p", "")
                    if path.endswith("/content") or path == "response/fragments/-1/content" or not path:
                        if self._is_thinking_fragment(current_fragment_type):
                            yield from handle_thinking_text(fragment)
                        elif self._is_response_fragment(current_fragment_type):
                            yield from stop_silent_thinking()
                            yield StreamEvent("response", fragment)

        yield from stop_silent_thinking()
        yield StreamEvent("done", "")


    @staticmethod
    def _extract_response_message_id(data: dict[str, Any]) -> int | None:
        """Return the assistant message ID from DeepSeek stream metadata.

        The web API sends this near the beginning as `response_message_id` and
        may also include it later as `v.response.message_id`. Future requests
        must use that ID as `parent_message_id`; otherwise DeepSeek creates
        sibling/edited branches instead of advancing the same conversation.
        """
        direct_id = data.get("response_message_id")
        if isinstance(direct_id, int):
            return direct_id

        value = data.get("v")
        if isinstance(value, dict):
            response_obj = value.get("response")
            if isinstance(response_obj, dict):
                nested_id = response_obj.get("message_id")
                if isinstance(nested_id, int):
                    return nested_id
        return None

    @staticmethod
    def _parse_sse_data(line: str) -> dict[str, Any] | None:
        data_str = line[5:].strip()
        if not data_str:
            return None
        try:
            parsed = json.loads(data_str)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
