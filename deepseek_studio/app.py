"""DeepSeek Terminal Studio Textual application."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static, TextArea

from .agent.runner import AgentRunner
from .commands import EXIT_COMMANDS, command_menu, complete_command, split_command
from .constants import APP_SUBTITLE, APP_TITLE, HELP_TEXT, WELCOME_TEXT
from .models import ChatState, StreamEvent
from .services.client import DeepSeekClient
from .services.token_usage import TokenCounter
from .ui.layout import compose_shell
from .ui.styles import APP_CSS
from .ui.widgets import MessageBubble, PromptTextArea


class DeepSeekTUI(App[None]):
    """Main Textual application."""

    TITLE = APP_TITLE
    SUB_TITLE = APP_SUBTITLE
    CSS = APP_CSS
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
        Binding("ctrl+a", "toggle_agent", "Agent", show=False),
        Binding("ctrl+r", "toggle_search", "Search", show=False),
        Binding("ctrl+t", "toggle_thinking", "Thinking", show=False),
        Binding("ctrl+n", "new_session", "New chat", show=False),
        Binding("ctrl+l", "clear_chat", "Clear", show=False),
        Binding("ctrl+s", "toggle_sidebar", "Sidebar", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.state = ChatState()
        self.token_counter = TokenCounter()
        self.state.token_backend = self.token_counter.backend_name
        self.state.token_backend_detail = self.token_counter.detail
        self.client: DeepSeekClient | None = None
        self.agent_runner: AgentRunner | None = None
        self.current_assistant: MessageBubble | None = None
        self.current_thinking: MessageBubble | None = None
        self.current_response_text = ""
        self.current_thinking_text = ""
        self.current_activity: MessageBubble | None = None
        self.activity_timer: Any = None
        self.activity_text = ""
        self.activity_frame = 0
        self.session_response_tokens_at_turn_start = 0
        self.session_thinking_tokens_at_turn_start = 0

    def compose(self) -> ComposeResult:
        yield from compose_shell()

    def on_mount(self) -> None:
        self.query_one("#prompt", PromptTextArea).focus()
        self._update_command_menu("")
        self._apply_responsive_sidebar()
        self._refresh_status("Starting client")
        self._system(WELCOME_TEXT)
        self._system("Creating a chat session...")
        self.run_worker(self._boot_client, thread=True, exclusive=True)

    def on_resize(self, event) -> None:  # noqa: ANN001 - Textual supplies the event object.
        self._apply_responsive_sidebar()

    def _apply_responsive_sidebar(self) -> None:
        """Hide the sidebar on narrow terminals without relying on CSS @media support."""
        try:
            sidebar = self.query_one("#sidebar")
            sidebar.display = self.size.width >= 96
        except Exception:
            # Best effort only; keep the app usable on older Textual versions.
            pass

    def _boot_client(self) -> None:
        try:
            client = DeepSeekClient()
            session_id = client.create_session()
        except Exception as exc:  # noqa: BLE001 - show failures in the TUI
            self.call_from_thread(self._system, f"Startup failed: {exc}")
            self.call_from_thread(self._refresh_status, "Startup failed")
            return
        self.call_from_thread(self._set_ready, client, session_id)

    def _set_ready(self, client: DeepSeekClient, session_id: str) -> None:
        self.client = client
        self.agent_runner = AgentRunner(client)
        self.state.workspace = str(self.agent_runner.workspace)
        self.state.session_id = session_id
        self.state.parent_message_id = None
        self.state.busy = False
        self._system(f"Session ready: {session_id}")
        self._refresh_status("Ready")
        self._update_token_card()

    def _refresh_status(self, status: str | None = None) -> None:
        if status is not None:
            self.state.last_status = status
        thinking = "ON" if self.state.thinking_enabled else "OFF"
        think_view = "TEXT" if self.state.thinking_stream_enabled else "ANIM"
        agent = "ON" if self.state.agent_enabled else "OFF"
        search = "ON" if self.state.search_enabled else "OFF"
        workspace = self.state.workspace
        if len(workspace) > 34:
            workspace = "..." + workspace[-31:]
        text = (
            f"Status    {self.state.last_status}\n"
            f"Agent     {agent}\n"
            f"Search    {search}\n"
            f"Thinking  {thinking} / {think_view}\n"
            f"Workspace {workspace}"
        )
        self.query_one("#status-card", Static).update(Text(text))

    def _format_token_usage(self) -> str:
        # Helper to right-align numbers with commas
        def fmt(val: int) -> str:
            return f"{val:>10,}"

        lines = [
            "Token Usage",
            "─" * 14,
            "Current turn",
            f"  In:     {fmt(self.state.current_prompt_tokens)}",
            f"  Out:    {fmt(self.state.current_response_tokens)}",
            f"  Think:  {fmt(self.state.current_thinking_tokens)}",
            f"  Total:  {fmt(self.state.current_total_tokens)}",
            "",
            "Session",
            f"  In:     {fmt(self.state.session_prompt_tokens)}",
            f"  Out:    {fmt(self.state.session_response_tokens)}",
            f"  Think:  {fmt(self.state.session_thinking_tokens)}",
            f"  Total:  {fmt(self.state.session_total_tokens)}",
        ]
        return "\n".join(lines)

    def _update_token_card(self) -> None:
        """Update the token usage card in the sidebar."""
        text = self._format_token_usage()
        self.query_one("#token-card", Static).update(Text(text))

    def _show_usage(self) -> None:
        self._system(self._format_token_usage())

    def _update_command_menu(self, text: str | None = None) -> None:
        if text is None:
            text = self.query_one("#prompt", PromptTextArea).text
        menu = command_menu(text)
        menu_widget = self.query_one("#command-menu", Static)
        menu_widget.update(menu)
        menu_widget.display = bool(menu)

    def _append_message(self, bubble: MessageBubble) -> MessageBubble:
        transcript = self.query_one("#transcript", VerticalScroll)
        transcript.mount(bubble)
        transcript.scroll_end(animate=False)
        return bubble

    def _system(self, text: str) -> None:
        bubble = self._append_message(MessageBubble("system"))
        bubble.set_text(text)

    def _tool(self, text: str) -> None:
        bubble = self._append_message(MessageBubble("tool"))
        bubble.set_text(text)

    def _start_activity(self, text: str) -> None:
        """Show a lightweight animated working indicator while hidden JSON streams."""
        self.activity_text = text
        self.activity_frame = 0
        if self.current_activity is None:
            self.current_activity = self._append_message(MessageBubble("working"))
        self._tick_activity()
        if self.activity_timer is None:
            self.activity_timer = self.set_interval(0.18, self._tick_activity, pause=False)

    def _tick_activity(self) -> None:
        if self.current_activity is None:
            return
        frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        frame = frames[self.activity_frame % len(frames)]
        self.activity_frame += 1
        self.current_activity.set_text(f"{frame} {self.activity_text}", style="dim #8b93a7")
        self._scroll_to_bottom()

    def _stop_activity(self) -> None:
        if self.activity_timer is not None:
            self.activity_timer.stop()
            self.activity_timer = None
        if self.current_activity is not None:
            self.current_activity.remove()
            self.current_activity = None
        self.activity_text = ""
        self.activity_frame = 0

    def _user(self, text: str) -> None:
        bubble = self._append_message(MessageBubble("user"))
        bubble.set_text(text)

    def _prepare_assistant_stream(self) -> None:
        self._stop_activity()
        self.current_thinking = None
        self.current_assistant = None
        self.current_response_text = ""
        self.current_thinking_text = ""
        self.session_response_tokens_at_turn_start = self.state.session_response_tokens
        self.session_thinking_tokens_at_turn_start = self.state.session_thinking_tokens
        self.state.reset_current_token_usage()
        self._update_token_card()

    def _ensure_assistant_bubble(self) -> MessageBubble:
        if self.current_assistant is None:
            self.current_assistant = self._append_message(MessageBubble("assistant"))
        return self.current_assistant

    def _ensure_thinking_bubble(self) -> MessageBubble:
        if self.current_thinking is None:
            self.current_thinking = self._append_message(MessageBubble("thinking"))
        return self.current_thinking

    def _append_stream_event(self, event: StreamEvent) -> None:
        if event.kind == "status":
            self._refresh_status(event.text)
            return
        if event.kind == "thinking_start":
            # Each agent/model turn gets its own reasoning block instead of appending
            # all hidden thinking into the first one. Token accounting still uses
            # current_thinking_text for the whole user turn.
            self.current_thinking = None
            return
        if event.kind == "activity_start":
            self._start_activity(event.text or "Waiting for model action")
            return
        if event.kind == "activity_stop":
            self._stop_activity()
            return
        if event.kind == "message_id":
            try:
                self.state.parent_message_id = int(event.text)
            except ValueError:
                pass
            return
        if event.kind == "thinking":
            bubble = self._ensure_thinking_bubble()
            bubble.append(event.text, style="dim #8b93a7 italic")
            self._record_thinking_tokens(event.text)
            self._scroll_to_bottom()
            return
        if event.kind == "response":
            self._stop_activity()
            bubble = self._ensure_assistant_bubble()
            bubble.append(event.text)
            self._record_response_tokens(event.text)
            self._scroll_to_bottom()
            return
        if event.kind == "agent_final":
            self._stop_activity()
            bubble = self._ensure_assistant_bubble()
            bubble.append(event.text)
            self._scroll_to_bottom()
            return
        if event.kind == "tool":
            self._stop_activity()
            self._tool(event.text)
            return
        if event.kind == "agent":
            # Agent progress stays in the status panel; transcript output should stay quiet.
            self._refresh_status(event.text)
            return
        if event.kind == "usage_prompt":
            self._record_prompt_tokens(event.text)
            return
        if event.kind == "usage_response":
            self._record_response_tokens(event.text)
            return
        if event.kind == "usage_thinking":
            self._record_thinking_tokens(event.text)
            return
        if event.kind == "error":
            self._stop_activity()
            self._system(event.text)
            return
        if event.kind == "done":
            self._stop_activity()
            self._finish_stream()


    def _record_prompt_tokens(self, prompt: str) -> None:
        prompt_tokens = self.token_counter.count(prompt)
        self.state.current_prompt_tokens += prompt_tokens
        self.state.session_prompt_tokens += prompt_tokens
        self._update_token_card()

    def _record_response_tokens(self, text: str) -> None:
        self.current_response_text += text
        new_count = self.token_counter.count(self.current_response_text)
        self.state.current_response_tokens = new_count
        self.state.session_response_tokens = self.session_response_tokens_at_turn_start + new_count
        self._update_token_card()

    def _record_thinking_tokens(self, text: str) -> None:
        self.current_thinking_text += text
        new_count = self.token_counter.count(self.current_thinking_text)
        self.state.current_thinking_tokens = new_count
        self.state.session_thinking_tokens = self.session_thinking_tokens_at_turn_start + new_count
        self._update_token_card()

    def _scroll_to_bottom(self) -> None:
        self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    def _finish_stream(self) -> None:
        self.state.busy = False
        self.state.messages_sent += 1
        prompt = self.query_one("#prompt", PromptTextArea)
        prompt.disabled = False
        prompt.focus()
        self._refresh_status("Ready")

    @on(TextArea.Changed)
    def on_prompt_changed(self, event: TextArea.Changed) -> None:
        self._update_command_menu(self.query_one("#prompt", PromptTextArea).text)

    @on(PromptTextArea.CompleteRequested)
    def on_prompt_complete_requested(self, event: PromptTextArea.CompleteRequested) -> None:
        prompt = self.query_one("#prompt", PromptTextArea)
        completed = complete_command(prompt.text)
        if completed is None:
            return
        prompt.replace_text(completed)
        self._update_command_menu(completed)

    @on(PromptTextArea.Submitted)
    def on_prompt_submitted(self, event: PromptTextArea.Submitted) -> None:
        prompt = event.text.strip()
        self.query_one("#prompt", PromptTextArea).clear_text()
        self._update_command_menu("")
        if prompt:
            self._handle_prompt(prompt)

    def _handle_prompt(self, prompt: str) -> None:
        if prompt.startswith("/"):
            self._handle_command(prompt)
            return
        if self.state.busy:
            self._system("Still streaming. Let the current answer finish first.")
            return
        if not self.client or not self.state.session_id:
            self._system("Client is not ready yet.")
            return

        self._user(prompt)
        self._prepare_assistant_stream()
        if not self.state.agent_enabled:
            self._record_prompt_tokens(prompt)
        self.state.busy = True
        self.query_one("#prompt", PromptTextArea).disabled = True
        self._refresh_status("Sending")
        self.run_worker(lambda: self._stream_prompt(prompt), thread=True, exclusive=True)

    def _stream_prompt(self, prompt: str) -> None:
        assert self.client is not None
        assert self.state.session_id is not None
        try:
            if self.state.agent_enabled:
                if self.agent_runner is None:
                    raise RuntimeError("Agent runner is not ready")
                event_source = self.agent_runner.run(
                    self.state.session_id,
                    prompt,
                    thinking_enabled=self.state.thinking_enabled,
                    stream_thinking=self.state.thinking_stream_enabled,
                    parent_id=self.state.parent_message_id,
                    search_enabled=self.state.search_enabled,
                )
            else:
                event_source = self.client.stream_message(
                    self.state.session_id,
                    prompt,
                    parent_id=self.state.parent_message_id,
                    thinking_enabled=self.state.thinking_enabled,
                    emit_thinking=self.state.thinking_stream_enabled,
                    search_enabled=self.state.search_enabled,
                )
            for event in event_source:
                self.call_from_thread(self._append_stream_event, event)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._append_stream_event, StreamEvent("error", f"Request failed: {exc}"))
            self.call_from_thread(self._append_stream_event, StreamEvent("done", ""))

    def _handle_command(self, raw_command: str) -> None:
        command, arg = split_command(raw_command)
        if command in EXIT_COMMANDS:
            self.exit()
        elif command == "/agent":
            self.action_toggle_agent()
        elif command == "/chat":
            self.state.agent_enabled = False
            self._system("Chat-only mode: ON. Agent tools are disabled until /agent.")
            self._refresh_status("Ready")
        elif command == "/think":
            self.action_toggle_thinking()
        elif command == "/thinkstream":
            self.action_toggle_thinking_stream()
        elif command == "/search":
            self.action_toggle_search()
        elif command == "/new":
            self.action_new_session()
        elif command == "/clear":
            self.action_clear_chat()
        elif command == "/workspace":
            self._handle_workspace(arg)
        elif command == "/tools":
            self._show_tools()
        elif command == "/help":
            self._system(HELP_TEXT)
        else:
            self._system(f"Unknown command: {command}")

    def action_toggle_agent(self) -> None:
        self.state.agent_enabled = not self.state.agent_enabled
        self._system(f"Agent mode: {'ON' if self.state.agent_enabled else 'OFF'}")
        self._refresh_status("Ready")

    def action_toggle_thinking(self) -> None:
        self.state.thinking_enabled = not self.state.thinking_enabled
        self._system(f"DeepSeek reasoning: {'ON' if self.state.thinking_enabled else 'OFF'}")
        self._refresh_status("Ready")

    def action_toggle_search(self) -> None:
        self.state.search_enabled = not self.state.search_enabled
        self._system(f"DeepSeek web search: {'ON' if self.state.search_enabled else 'OFF'}")
        self._refresh_status("Ready")

    def action_toggle_thinking_stream(self) -> None:
        self.state.thinking_stream_enabled = not self.state.thinking_stream_enabled
        mode = "streaming text" if self.state.thinking_stream_enabled else "animation only"
        self._system(f"Thinking display mode: {mode}")
        self._refresh_status("Ready")

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display
        self._system(f"Sidebar {'hidden' if not sidebar.display else 'shown'}")

    def _show_tools(self) -> None:
        if not self.agent_runner:
            self._system("Agent runner is not ready yet.")
            return
        self._system("Agent tools\n" + self.agent_runner.tool_help())

    def _handle_workspace(self, arg: str) -> None:
        if not arg:
            self._system(f"Workspace: {self.state.workspace}")
            return
        if self.state.busy:
            self._system("Cannot change workspace while busy.")
            return
        if not self.agent_runner:
            self._system("Agent runner is not ready yet.")
            return
        try:
            self.agent_runner.set_workspace(arg)
        except Exception as exc:  # noqa: BLE001
            self._system(f"Could not set workspace: {exc}")
            return
        self.state.workspace = str(self.agent_runner.workspace)
        self._system(f"Workspace set: {self.state.workspace}")
        self._refresh_status("Ready")

    def action_new_session(self) -> None:
        if self.state.busy:
            self._system("Cannot start a new session while streaming.")
            return
        if not self.client:
            self._system("Client is not ready yet.")
            return
        self.state.busy = True
        self._refresh_status("Creating session")
        self.run_worker(self._new_session_worker, thread=True, exclusive=True)

    def _new_session_worker(self) -> None:
        assert self.client is not None
        try:
            session_id = self.client.create_session()
            self.call_from_thread(self._finish_new_session, session_id)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._finish_new_session_failed, str(exc))

    def _finish_new_session_failed(self, message: str) -> None:
        self.state.busy = False
        self._system(f"Could not create new session: {message}")
        self._refresh_status("Ready")

    def _finish_new_session(self, session_id: str) -> None:
        self.state.session_id = session_id
        self.state.parent_message_id = None
        self.state.busy = False
        self.state.reset_session_token_usage()
        self._stop_activity()
        self.current_assistant = None
        self.current_thinking = None
        self.current_response_text = ""
        self.current_thinking_text = ""
        self.session_response_tokens_at_turn_start = 0
        self.session_thinking_tokens_at_turn_start = 0
        self._update_token_card()
        self._system(f"New session ready: {session_id}")
        self._refresh_status("Ready")

    def action_clear_chat(self) -> None:
        self._stop_activity()
        transcript = self.query_one("#transcript", VerticalScroll)
        for child in list(transcript.children):
            child.remove()
        self.current_assistant = None
        self.current_thinking = None
        self._system("Transcript cleared.")


def main() -> None:
    DeepSeekTUI().run()
