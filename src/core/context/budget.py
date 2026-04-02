"""Context budget calculation helpers."""

from __future__ import annotations

from core.schemas.constants import (
    CONTEXT_SAFETY_MARGIN_MIN,
    CONTEXT_SAFETY_MARGIN_RATIO,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
)


def calculate_budget(max_context_tokens: int) -> int:
    """Return the usable token budget for the Moderator's prompt (§7.5.1).

    Reserves a safety margin for the Moderator's response and function-calling overhead:
        safety_margin = max(
            CONTEXT_SAFETY_MARGIN_MIN,
            max_context_tokens * CONTEXT_SAFETY_MARGIN_RATIO,
        )
        effective_budget = max_context_tokens - safety_margin
    """

    safety_margin = max(
        CONTEXT_SAFETY_MARGIN_MIN,
        int(max_context_tokens * CONTEXT_SAFETY_MARGIN_RATIO),
    )
    return max_context_tokens - safety_margin


def count_tokens(text: str) -> int:
    """Estimate token count using the character-based heuristic (§0.4).

    Uses TOKEN_ESTIMATE_CHARS_PER_TOKEN from constants — no tokenizer library.
    """

    return len(text) // TOKEN_ESTIMATE_CHARS_PER_TOKEN
