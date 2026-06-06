# DeepSeek Terminal Studio

A polished, reasoning-aware terminal workspace for DeepSeek chat and agentic coding/automation.

## Project layout

```text
deepseek_tui.py                 # small compatibility entrypoint
deepseek_client.py              # compatibility shim for older imports
requirements.txt
.env.example
README.md

deepseek_studio/
  __init__.py
  __main__.py                   # python -m deepseek_studio
  app.py                        # Textual app controller
  commands.py                   # slash command parsing
  constants.py                  # shared labels, copy, headers
  models.py                     # ChatState and StreamEvent
  agent/
    protocol.py                 # JSON agent protocol and parser
    runner.py                   # model/tool/model loop
    tools.py                    # local file, search, patch, and command tools
  services/
    client.py                   # DeepSeek streaming HTTP client
    pow.py                      # PoW / WASM solver isolated here
    tokens.py                   # token loading
    token_usage.py              # offline token counting / estimates
  ui/
    layout.py                   # Textual layout composition
    styles.py                   # Textual CSS
    widgets.py                  # custom message bubble widget
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your token with one of these options:

```bash
export DEEPSEEK_USER_TOKEN="your-token"
```

or:

```bash
echo "your-token" > ~/.deepseek_token
chmod 600 ~/.deepseek_token
```

## Optional: exact offline token counting

The app always shows a token estimate. For closer DeepSeek V3 counts, use the tokenizer bundle from DeepSeek:

```bash
unzip deepseek_v3_tokenizer.zip -d .
pip install -r requirements.txt
```

That should create this path in the project root:

```text
deepseek_v3_tokenizer/tokenizer.json
```

If you keep the tokenizer somewhere else, point the app at it:

```bash
export DEEPSEEK_TOKENIZER_DIR="/path/to/deepseek_v3_tokenizer"
```

Without the tokenizer files/package, the app falls back to DeepSeek's rough published ratios: English-ish characters ≈ 0.3 token and CJK characters ≈ 0.6 token.

## Run

```bash
python deepseek_tui.py
```

or:

```bash
python -m deepseek_studio
```

## Agent mode

Agent mode is ON by default. Start the app from the project or CTF challenge directory you want it to work in:

```bash
cd /path/to/project-or-challenge
python /path/to/deepseek_tui.py
```

The agent can list/search/read/write/edit files, create directories, apply git-style patches, and run non-interactive shell commands in the workspace. File tools are workspace-scoped. Command execution runs from the workspace with a timeout and blocks a few obviously dangerous command patterns unless `DEEPSEEK_STUDIO_ALLOW_DANGEROUS=1` is set.

Use `/chat` when you want normal chatbot mode without tools.

## Commands

```text
/agent        Toggle agent mode
/chat         Chat-only mode
/think        Toggle DeepSeek reasoning on/off
/thinkstream  Toggle reasoning text vs animation-only display
/workspace    Show or set the agent workspace path
/tools        Show available agent tools
/steps N      Set max agent tool steps for one task
/usage        Show token usage
/new          Start a fresh chat session
/clear        Clear transcript
/help         Show help
/quit         Exit
```

## Keybindings

```text
Ctrl+A   Toggle agent mode
Ctrl+T   Toggle reasoning
Ctrl+N   New session
Ctrl+L   Clear transcript
Ctrl+Q   Quit
```

## Notes

- Secrets are not hardcoded. Keep your token in `.env`, `DEEPSEEK_USER_TOKEN`, or `~/.deepseek_token`.
- The proof-of-work WASM blob is isolated in `deepseek_studio/services/pow.py` so UI and client code stay readable.
- `deepseek_client.py` remains as a compatibility shim in case another local script imports it.
- Token counts are meant as local/offline guidance. Billing should still be trusted from DeepSeek usage results when available.
- Agent tools can modify files and run commands in your workspace. Use trusted workspaces and commit/checkpoint important work before large tasks.
