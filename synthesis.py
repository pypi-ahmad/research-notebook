"""Compatibility exports for the active Ask and Brief implementations.

New code should import ``src.ask`` or ``src.brief`` directly. This module keeps
older callers working without duplicating generation behavior.
"""

from src.ask import ask_question, format_web_snippets
from src.brief import generate_brief

__all__ = ["ask_question", "format_web_snippets", "generate_brief"]
