"""Bundle summarization with disk-based caching (§7.5.3)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.journals.bundle_io import read_bundle_summary, write_bundle_summary
from core.providers.base import Message
from core.schemas.constants import SUMMARY_MAX_TOKENS

if TYPE_CHECKING:
    from core.providers.base import ProviderAdapter


async def summarize_bundle(bundle_text: str, adapter: "ProviderAdapter", model: str) -> str:
    """Call the provider to produce a 2–3 sentence summary of a bundle (§7.5.3).

    Sends max_tokens=SUMMARY_MAX_TOKENS to keep the summary short.
    """

    prompt = (
        "Summarize the following agent response bundle in 2-3 sentences, "
        "preserving key decisions, agreements, and unresolved tensions:\n\n"
        f"{bundle_text}"
    )
    result = await adapter.complete(
        messages=[Message(role="user", content=prompt)],
        model=model,
        response_format={"max_tokens": SUMMARY_MAX_TOKENS},
    )
    return result.text.strip()


async def get_or_create_summary(
    session_dir: Path,
    bundle_id: str,
    bundle_text: str,
    adapter: "ProviderAdapter",
    model: str,
) -> str:
    """Return the cached summary for bundle_id, generating and caching it if absent.

    First call: generates summary via provider and persists to
    ``{session_dir}/bundles/{bundle_id}_summary.txt``.
    Subsequent calls: reads from disk — never calls the provider again.
    """

    try:
        return read_bundle_summary(session_dir, bundle_id)
    except FileNotFoundError:
        pass

    summary = await summarize_bundle(bundle_text, adapter, model)
    write_bundle_summary(session_dir, bundle_id, summary)
    return summary
