# DeepSeek Terminal Studio

A polished, reasoning-aware terminal workspace for DeepSeek chat and agentic coding/automation. This Textual-based TUI lets you interact with DeepSeek models in a rich terminal environment, with support for streaming reasoning, web search, and a powerful agent that can read, write, edit, and execute commands inside your workspace.

## Features

- **Chat interface** with streaming responses, reasoning display, and optional web search.
- **Agent mode** – turns DeepSeek into an autonomous coding assistant that can:
  - List, read, write, edit, and delete files
  - Search file contents with regex
  - Run shell commands (with timeouts and safety restrictions)
  - Apply git patches
  - Perform git operations (status, diff, add, commit, log, branch, checkout, pull, push)
- **Workspace‑scoped tools** – the agent cannot access files outside the workspace (unless you explicitly change it).
- **Local token counting** – offline estimates using DeepSeek V3 tokenizer (or fallback heuristics).
- **Proof‑of‑work support** – transparently handles PoW challenges required by some DeepSeek endpoints.
- **Slash commands** and **keyboard shortcuts** for quick toggles.
- **Responsive sidebar** that hides on narrow terminals.

## Installation

### Prerequisites
- Python 3.10 or higher
- A terminal with true color support (most modern terminals)
- A DeepSeek user token (get it from the DeepSeek web interface)

### Steps

1. **Clone or download** this repository into a local folder.
2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   Alternatively, if you use `pyproject.toml`:
   ```bash
   pip install .
   ```
4. **Set your DeepSeek token** – choose one of these methods:
   - Environment variable: `export DEEPSEEK_USER_TOKEN="your-token-here"`
   - Token file: `echo "your-token-here" > ~/.deepseek_token && chmod 600 ~/.deepseek_token`
   - `.env` file (copy `.env.example` to `.env` and edit)

### Optional: Offline Tokenizer for Accurate Counts

To get token counts that closely match DeepSeek V3’s actual tokenization, download the tokenizer bundle from DeepSeek and place it in the project root:

```bash
unzip deepseek_v3_tokenizer.zip -d .
```

This should create a folder `deepseek_v3_tokenizer/` containing `tokenizer.json`. The app will automatically use it. You can also point to a different location with the environment variable:

```bash
export DEEPSEEK_TOKENIZER_DIR="/path/to/deepseek_v3_tokenizer"
```

Without the tokenizer, the app falls back to character‑based heuristics (English ≈0.3 token/char, CJK ≈0.6 token/char).

## Running the Application

Start the TUI from your desired workspace directory:

```bash
cd /path/to/your/project
python deepseek_tui.py
```

or:

```bash
python -m deepseek_studio
```

The workspace is set to the current directory. You can change it later with the `/workspace` command.

## Usage

### Chatting
Type your message and press **Enter**. The assistant will reply with streaming text. If reasoning is enabled, you will see a separate reasoning block before the final answer.

### Agent Mode
**Agent mode is ON by default.** In this mode, DeepSeek can use tools to inspect and modify your workspace. The model decides when to call a tool and when to give a final answer. Each tool call is displayed in the TUI, and the tool’s output is fed back to the model.

To switch to pure chat mode (no tool access), use `/chat` or press `Ctrl+A`.

**Important safety notes:**
- The agent is confined to the workspace directory. It cannot access files outside that directory unless you change the workspace with `/workspace`.
- Command execution is non‑interactive and has a 30‑second timeout (configurable per call).
- Dangerous command patterns (e.g., `rm -rf /`, `sudo`, `:(){ :|:& };:`) are blocked unless you set the environment variable `DEEPSEEK_STUDIO_ALLOW_DANGEROUS=1`.
- Always work in a trusted workspace. Commit important changes before giving the agent broad permissions.

### Slash Commands

| Command | Description |
|---------|-------------|
| `/agent` | Toggle agent tools on/off |
| `/chat` | Switch to chat‑only mode (same as `/agent off`) |
| `/search` | Toggle DeepSeek web search |
| `/think` | Toggle reasoning (thinking) |
| `/thinkstream` | Toggle between streaming reasoning text and an animated “thinking…” indicator |
| `/workspace [path]` | Show or change the active workspace (relative paths are resolved inside the current workspace) |
| `/tools` | List available agent tools |
| `/new` | Start a new chat session (clears conversation history) |
| `/clear` | Clear the transcript (keeps session but removes all messages from view) |
| `/help` | Show command help |
| `/quit` or `/exit` | Exit DeepSeek Terminal Studio |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+A` | Toggle agent mode |
| `Ctrl+R` | Toggle web search |
| `Ctrl+T` | Toggle reasoning |
| `Ctrl+N` | New session |
| `Ctrl+L` | Clear transcript |
| `Ctrl+Q` | Quit |
| `Ctrl+S` | Toggle sidebar (hide on narrow terminals) |

While typing, the TUI shows a command menu (e.g., `/` suggests available commands).

## How It Works

### Architecture
- **Textual TUI** (`app.py`, `ui/`) provides the terminal interface with message bubbles, status cards, and a prompt area.
- **DeepSeek Client** (`services/client.py`) handles HTTP streaming requests, including proof‑of‑work challenges (handled by `services/pow.py`).
- **Agent Loop** (`agent/runner.py`) orchestrates the model/tool interaction:
  1. The user sends a message (or the agent continues from a tool result).
  2. The system prompt instructs the model to respond with a **strict JSON** object containing either a tool call or a final answer.
  3. If a tool call is requested, the runner executes the tool via `ToolRegistry` (`agent/tools.py`), appends the tool result as a user message, and repeats the loop.
  4. If a final answer is given, it is displayed to the user.
- **Tool Registry** implements file system operations, command execution, and git helpers. Read‑only tools are cached for performance. Write operations invalidate relevant cache entries.

### Agent JSON Protocol
To keep the model focused, the agent prompt enforces a simple two‑response format:

**Tool call:**
```json
{
  "status": "Brief visible progress note",
  "tool": {
    "name": "tool_name",
    "args": { ... }
  }
}
```

**Final answer:**
```json
{
  "final": "Clear final answer for the user, including what changed, tests run, and any caveats"
}
```

The parser is tolerant of markdown fences and minor JSON deviations (trailing commas, unquoted keys).

### Token Counting
- Uses `tokenizers` library with DeepSeek V3’s `tokenizer.json` if available.
- The `TokenCounter` class (`services/token_usage.py`) provides offline estimates for prompts, responses, and reasoning tokens.
- Estimates are shown in the sidebar and updated per turn. They are **not** billing‑grade but help gauge context usage.

### Proof of Work (PoW)
Some DeepSeek endpoints require a JavaScript‑based proof‑of‑work challenge. The client automatically extracts the challenge, runs the WASM solver (via `wasmtime` in `services/pow.py`), and submits the solution. The UI and agent code remain unaware of this process.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_USER_TOKEN` | Your DeepSeek token (required). |
| `DEEPSEEK_TOKENIZER_DIR` | Path to the DeepSeek V3 tokenizer folder (optional). |
| `DEEPSEEK_STUDIO_ALLOW_DANGEROUS` | Set to `1` to allow potentially destructive shell commands (e.g., `rm -rf`). **Use with caution.** |

You can also store the token in `~/.deepseek_token` (plain text, recommended permissions 600).

## Troubleshooting

- **Startup fails with “Session creation error”** – Check your token and network connection. The token must be a valid DeepSeek web token.
- **Agent can’t read or write files** – Verify the workspace path with `/workspace`. The agent cannot access paths outside the workspace.
- **Commands time out** – Increase the timeout in the tool call (the agent can pass a `timeout` argument). The default is 30 seconds.
- **Tokenizer not found** – Install the tokenizer bundle as described above, or ignore the warning – token estimates will be less accurate but still functional.
- **Terminal flickering or display issues** – Make sure your terminal supports true color and is at least 80 columns wide. The sidebar auto‑hides below 96 columns.

## Compatibility Shim

The files `deepseek_client.py` and `deepseek_tui.py` are small compatibility entrypoints that delegate to the `deepseek_studio` package. Existing scripts that import `deepseek_client` will continue to work.

## License

This project is provided as open source. See the repository for license details (if any).

---

**DeepSeek Terminal Studio** – because your terminal deserves a thinking assistant.
