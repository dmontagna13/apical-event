"""Tiered context assembly for Moderator prompts (§7.5.4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .budget import count_tokens

if TYPE_CHECKING:
    from core.providers.base import ProviderAdapter


class ContextBudgetExceeded(Exception):
    """Raised when P0–P3 tiers alone exceed the effective token budget."""


@dataclass
class ContextBlock:
    """A single block of context content tagged with its priority tier."""

    priority: str  # "P0" through "P6"
    content: str

    @property
    def token_count(self) -> int:
        """Estimated token count for this block."""

        return count_tokens(self.content)


async def assemble_moderator_context(
    system_prompt: str,
    inputs_text: str,
    kanban_state: str,
    queued_human_messages: list[str],
    latest_bundle_text: str | None,
    prior_bundle_pairs: list[tuple[str, str]],
    budget: int,
    session_dir: Path | None = None,
    adapter: "ProviderAdapter | None" = None,
    model: str | None = None,
) -> list[ContextBlock]:
    """Assemble the Moderator's context blocks in priority order (§7.5.2–7.5.4).

    Priority tiers (non-negotiable ordering):
      P0 — system prompt + role directive + constraints (always verbatim)
      P1 — packet inputs (always verbatim)
      P2 — current kanban state (always verbatim)
      P3 — queued human messages (always verbatim, only if present)
      P4 — most recent bundle (always included, even if over budget)
      P5 — prior bundles newest-first (verbatim until budget exhausted)
      P6 — bundles that no longer fit verbatim (replaced with summaries)

    Raises:
        ContextBudgetExceeded: if P0–P3 alone exceed the budget.
    """

    blocks: list[ContextBlock] = []
    used = 0

    # P0: system prompt
    p0 = ContextBlock("P0", system_prompt)
    used += p0.token_count
    blocks.append(p0)

    # P1: inputs
    p1 = ContextBlock("P1", inputs_text)
    used += p1.token_count
    if used > budget:
        raise ContextBudgetExceeded(
            f"P0+P1 ({used} tokens) exceeds budget ({budget} tokens). Session cannot continue."
        )
    blocks.append(p1)

    # P2: kanban
    p2 = ContextBlock("P2", kanban_state)
    used += p2.token_count
    if used > budget:
        raise ContextBudgetExceeded(
            f"P0–P2 ({used} tokens) exceeds budget ({budget} tokens). Session cannot continue."
        )
    blocks.append(p2)

    # P3: queued human messages
    if queued_human_messages:
        p3_content = "\n".join(queued_human_messages)
        p3 = ContextBlock("P3", p3_content)
        used += p3.token_count
        if used > budget:
            raise ContextBudgetExceeded(
                f"P0–P3 ({used} tokens) exceeds budget ({budget} tokens). Session cannot continue."
            )
        blocks.append(p3)

    # P4: most recent bundle — always included
    if latest_bundle_text:
        p4 = ContextBlock("P4", latest_bundle_text)
        used += p4.token_count
        blocks.append(p4)

    # P5/P6: prior bundles, newest-first
    for bundle_id, bundle_text in prior_bundle_pairs:
        tokens = count_tokens(bundle_text)
        if used + tokens <= budget:
            blocks.append(ContextBlock("P5", bundle_text))
            used += tokens
        else:
            # P6: try summary
            summary = await _try_get_summary(bundle_id, bundle_text, session_dir, adapter, model)
            if summary:
                summary_tokens = count_tokens(summary)
                if used + summary_tokens <= budget:
                    blocks.append(ContextBlock("P6", summary))
                    used += summary_tokens
            # else: drop entirely — oldest, least critical

    return blocks


async def _try_get_summary(
    bundle_id: str,
    bundle_text: str,
    session_dir: Path | None,
    adapter: "ProviderAdapter | None",
    model: str | None,
) -> str | None:
    """Get or create a bundle summary. Returns None if adapter/session_dir unavailable."""

    if session_dir is None or adapter is None or model is None:
        return None

    from .summarizer import get_or_create_summary

    try:
        return await get_or_create_summary(session_dir, bundle_id, bundle_text, adapter, model)
    except Exception:
        return None
