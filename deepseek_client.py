"""Compatibility imports for older scripts that imported deepseek_client."""

from deepseek_studio.models import StreamEvent
from deepseek_studio.services.client import DeepSeekClient
from deepseek_studio.services.tokens import load_user_token

__all__ = ["DeepSeekClient", "StreamEvent", "load_user_token"]
