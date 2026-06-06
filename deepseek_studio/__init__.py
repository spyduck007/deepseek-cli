"""DeepSeek Terminal Studio package."""

from __future__ import annotations

__all__ = ["DeepSeekTUI"]


def __getattr__(name: str):
    if name == "DeepSeekTUI":
        from .app import DeepSeekTUI

        return DeepSeekTUI
    raise AttributeError(name)
