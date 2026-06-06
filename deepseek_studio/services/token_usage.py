"""Token counting helpers for DeepSeek Terminal Studio.

The preferred path uses DeepSeek's published tokenizer bundle. Put the extracted
``deepseek_v3_tokenizer`` directory in the project root, or point
``DEEPSEEK_TOKENIZER_DIR`` at it.

If the tokenizer package/files are unavailable, we fall back to DeepSeek's rough
character ratios: English-ish characters ~= 0.3 token and CJK characters ~= 0.6
token. That keeps the TUI useful even before the tokenizer is installed.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Protocol


class _Encoder(Protocol):
    def count(self, text: str) -> int:
        """Return a token count for text."""


class TokenCounter:
    """Count tokens using DeepSeek's tokenizer when available, otherwise estimate."""

    def __init__(self, tokenizer_dir: str | Path | None = None) -> None:
        _load_dotenv_file()

        self._encoder: _Encoder | None = None
        self.backend_name = "estimate"
        self.detail = "character ratio"

        resolved_dir = self._resolve_tokenizer_dir(tokenizer_dir)
        if resolved_dir is None:
            return

        encoder = self._load_tokenizers_encoder(resolved_dir)
        if encoder is not None:
            self._encoder = encoder
            self.backend_name = "exact"
            self.detail = f"tokenizers:{resolved_dir.name}"
            return

        encoder = self._load_transformers_encoder(resolved_dir)
        if encoder is not None:
            self._encoder = encoder
            self.backend_name = "exact"
            self.detail = f"transformers:{resolved_dir.name}"

    def count(self, text: str) -> int:
        """Return an exact count when possible, otherwise a rough estimate."""
        if not text:
            return 0
        if self._encoder is not None:
            return self._encoder.count(text)
        return estimate_deepseek_tokens(text)

    @staticmethod
    def _resolve_tokenizer_dir(tokenizer_dir: str | Path | None) -> Path | None:
        candidates: list[Path] = []
        if tokenizer_dir:
            candidates.append(Path(tokenizer_dir).expanduser())
        env_dir = os.environ.get("DEEPSEEK_TOKENIZER_DIR", "").strip()
        if env_dir:
            candidates.append(Path(env_dir).expanduser())

        project_root = Path(__file__).resolve().parents[2]
        candidates.extend(
            [
                Path.cwd() / "deepseek_v3_tokenizer",
                project_root / "deepseek_v3_tokenizer",
                Path.cwd(),
                project_root,
            ]
        )

        for candidate in candidates:
            if (candidate / "tokenizer.json").exists():
                return candidate
        return None

    @staticmethod
    def _load_tokenizers_encoder(tokenizer_dir: Path) -> _Encoder | None:
        try:
            from tokenizers import Tokenizer  # type: ignore[import-not-found]
        except Exception:
            return None

        try:
            tokenizer = Tokenizer.from_file(str(tokenizer_dir / "tokenizer.json"))
        except Exception:
            return None

        class TokenizersEncoder:
            def count(self, text: str) -> int:
                return len(tokenizer.encode(text).ids)

        return TokenizersEncoder()

    @staticmethod
    def _load_transformers_encoder(tokenizer_dir: Path) -> _Encoder | None:
        try:
            from transformers import AutoTokenizer  # type: ignore[import-not-found]
        except Exception:
            return None

        try:
            tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_dir), trust_remote_code=True)
        except Exception:
            return None

        class TransformersEncoder:
            def count(self, text: str) -> int:
                return len(tokenizer.encode(text))

        return TransformersEncoder()


def estimate_deepseek_tokens(text: str) -> int:
    """Estimate token count from DeepSeek's published character ratios."""
    score = 0.0
    for char in text:
        score += 0.6 if _is_cjk(char) else 0.3
    return int(math.ceil(score))


def _load_dotenv_file() -> None:
    """Load simple KEY=VALUE pairs from .env into os.environ if present."""
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


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2A6DF
        or 0x2A700 <= codepoint <= 0x2B73F
        or 0x2B740 <= codepoint <= 0x2B81F
        or 0x2B820 <= codepoint <= 0x2CEAF
    )
