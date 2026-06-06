"""Shared constants for DeepSeek Terminal Studio."""

from __future__ import annotations

APP_TITLE = "DeepSeek Terminal Studio"
APP_SUBTITLE = "Agentic terminal workspace"

BASE_URL = "https://chat.deepseek.com"

STATIC_HEADERS: dict[str, str] = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "origin": "https://chat.deepseek.com",
    "pragma": "no-cache",
    "referer": "https://chat.deepseek.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "x-app-version": "2.0.0",
    "x-client-locale": "en_US",
    "x-client-platform": "web",
    "x-client-timezone-offset": "-14400",
    "x-client-version": "2.0.0",
}

LOGO = """
╭────────────────────╮
│        DS          │
│    DeepSeek        │
│ Terminal Studio    │
╰────────────────────╯
""".strip("\n")

TAGLINE = "Focused agent workspace"

HELP_TEXT = """Commands
  /agent        Toggle agent tools
  /chat         Chat-only mode
  /search       Toggle DeepSeek web search
  /think        Toggle DeepSeek reasoning
  /thinkstream  Reasoning text vs animation
  /workspace    Show/set workspace
  /tools        List available tools
  /new          New session
  /clear        Clear transcript
  /help         Show help
  /quit         Exit

Autocomplete
  Type / to see matching commands
  Tab completes the best match
""".strip()

WELCOME_TEXT = """DeepSeek Terminal Studio
An agentic terminal workspace for chat, coding, files, and commands.

Agent mode is ON by default. Start the app in the project/challenge directory you want it to work in, or use /workspace to switch.""".strip()
