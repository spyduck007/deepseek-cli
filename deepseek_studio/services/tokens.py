"""Token loading utilities."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _load_dotenv_file() -> None:
    """Load simple KEY=VALUE pairs from .env into os.environ.

    This keeps us from needing python-dotenv as a hard dependency.
    Existing environment variables win over .env values.
    """
    candidates = (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    )

    for env_path in candidates:
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[len("export ") :].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value

        return


def load_user_token() -> str:
    """Load a DeepSeek web token without hardcoding secrets into the codebase.

    Priority:
      1. DEEPSEEK_USER_TOKEN environment variable
      2. .env file in the current/project directory
      3. ~/.deepseek_token text file
      4. USER_TOKEN = "..." in a sibling deepseek.py / old script
    """
    _load_dotenv_file()

    env_token = os.environ.get("DEEPSEEK_USER_TOKEN", "").strip()
    if env_token:
        return env_token

    token_file = Path.home() / ".deepseek_token"
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token

    candidates = (
        Path.cwd() / "deepseek.py",
        Path(__file__).resolve().parents[2] / "deepseek.py",
    )
    for candidate in candidates:
        if not candidate.exists():
            continue

        text = candidate.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'USER_TOKEN\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            return match.group(1).strip()

    raise RuntimeError(
        "No DeepSeek token found. Set DEEPSEEK_USER_TOKEN in your shell, "
        "create a .env file with DEEPSEEK_USER_TOKEN=your-token, "
        "create ~/.deepseek_token, or keep your original deepseek.py next to this project."
    )