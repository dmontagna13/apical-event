"""Tests for core/context — budget, assembler, summarizer."""

from __future__ import annotations

import pytest

from core.context.assembler import ContextBudgetExceeded, assemble_moderator_context
from core.context.budget import calculate_budget, count_tokens
from core.context.summarizer import get_or_create_summary, summarize_bundle
from core.providers.base import CompletionResult, ProviderAdapter
from core.schemas.constants import (
    CONTEXT_SAFETY_MARGIN_MIN,
    CONTEXT_SAFETY_MARGIN_RATIO,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text(tokens: int) -> str:
    """Return a string that estimates to exactly `tokens` tokens."""
    return "a" * (tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN)


def _make_provider(text: str = "canned summary") -> ProviderAdapter:
    """Return a mock provider that always returns `text`."""

    class _Mock:
        def __init__(self) -> None:
            self.call_count = 0

        async def complete(self, messages, model, tools=None, response_format=None, tool_choice=None):
            self.call_count += 1
            return CompletionResult(
                text=text, tool_calls=[], usage={}, finish_reason="stop", latency_ms=0
            )

        async def health_check(self) -> bool:
            return True

    return _Mock()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# budget.py
# ---------------------------------------------------------------------------


def test_calculate_budget_uses_min_margin():
    # When max_tokens is small, CONTEXT_SAFETY_MARGIN_MIN dominates
    small = 10_000
    result = calculate_budget(small)
    assert result == small - CONTEXT_SAFETY_MARGIN_MIN


def test_calculate_budget_uses_ratio_margin():
    # When max_tokens is large, the ratio dominates
    large = 200_000
    expected_margin = int(large * CONTEXT_SAFETY_MARGIN_RATIO)
    assert expected_margin > CONTEXT_SAFETY_MARGIN_MIN
    assert calculate_budget(large) == large - expected_margin


def test_calculate_budget_matches_spec():
    # Spec §7.5.1: safety_margin = max(4096, tokens * 0.05)
    tokens = 128_000
    margin = max(CONTEXT_SAFETY_MARGIN_MIN, int(tokens * CONTEXT_SAFETY_MARGIN_RATIO))
    assert calculate_budget(tokens) == tokens - margin


def test_count_tokens_heuristic():
    text = "a" * 400
    assert count_tokens(text) == 100  # 400 // 4 = 100


def test_count_tokens_empty():
    assert count_tokens("") == 0


# ---------------------------------------------------------------------------
# assembler.py — basic structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembler_returns_p0_through_p4():
    blocks = await assemble_moderator_context(
        system_prompt=_text(100),
        inputs_text=_text(200),
        kanban_state=_text(50),
        queued_human_messages=[],
        latest_bundle_text=_text(100),
        prior_bundle_pairs=[],
        budget=10_000,
    )
    priorities = [b.priority for b in blocks]
    assert priorities == ["P0", "P1", "P2", "P4"]


@pytest.mark.asyncio
async def test_assembler_includes_p3_when_messages_present():
    blocks = await assemble_moderator_context(
        system_prompt=_text(100),
        inputs_text=_text(200),
        kanban_state=_text(50),
        queued_human_messages=["Hello moderator"],
        latest_bundle_text=None,
        prior_bundle_pairs=[],
        budget=10_000,
    )
    priorities = [b.priority for b in blocks]
    assert "P3" in priorities


@pytest.mark.asyncio
async def test_assembler_no_prior_bundles_no_p5_p6():
    blocks = await assemble_moderator_context(
        system_prompt=_text(50),
        inputs_text=_text(50),
        kanban_state=_text(50),
        queued_human_messages=[],
        latest_bundle_text=None,
        prior_bundle_pairs=[],
        budget=10_000,
    )
    assert not any(b.priority in ("P5", "P6") for b in blocks)


# ---------------------------------------------------------------------------
# assembler.py — exact budget arithmetic from the spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembler_prior_bundle_fits_as_p5():
    """Prior bundle at 300 tokens fits in budget — appears as P5."""

    budget = 4_000
    # P0+P1+P2 = 1000+2000+100 = 3100; P4 = 500; used = 3600. Remaining = 400.
    # prior bundle = 300 tokens → fits verbatim as P5.
    blocks = await assemble_moderator_context(
        system_prompt=_text(1_000),
        inputs_text=_text(2_000),
        kanban_state=_text(100),
        queued_human_messages=[],
        latest_bundle_text=_text(500),
        prior_bundle_pairs=[("bundle_001", _text(300))],
        budget=budget,
    )
    p5 = [b for b in blocks if b.priority == "P5"]
    assert len(p5) == 1


@pytest.mark.asyncio
async def test_assembler_prior_bundle_too_large_uses_p6_summary(tmp_path):
    """Prior bundle doesn't fit verbatim; summary fits — appears as P6."""

    budget = 4_000
    # P0(1000)+P1(2000)+P2(100)+P4(500) = 3600 used. Remaining = 400.
    # Prior bundle at 400 tokens → doesn't fit (used would be 4000, equals budget, but
    # we use strict <, so if 3600+400==4000, it DOES fit. Use 401 to exceed).
    # Actually the check is `used + tokens <= budget`, so 3600+400=4000 <=4000 fits.
    # Use 450 tokens for prior bundle, summary at 100 tokens.
    provider = _make_provider("Summary of bundle 001 in two sentences.")

    blocks = await assemble_moderator_context(
        system_prompt=_text(1_000),
        inputs_text=_text(2_000),
        kanban_state=_text(100),
        queued_human_messages=[],
        latest_bundle_text=_text(500),
        prior_bundle_pairs=[("bundle_001", _text(450))],
        budget=budget,
        session_dir=tmp_path,
        adapter=provider,
        model="mock-model",
    )
    # 3600 + 450 = 4050 > 4000 → doesn't fit as P5
    p5 = [b for b in blocks if b.priority == "P5"]
    p6 = [b for b in blocks if b.priority == "P6"]
    assert len(p5) == 0
    assert len(p6) == 1


@pytest.mark.asyncio
async def test_assembler_spec_exact_arithmetic(tmp_path):
    """Spec §7.5 example: system(1000)+inputs(2000)+kanban(100)+human(50)+latest(500)=3650.
    Budget=4000. Remaining=350. Prior bundle at 400 tokens doesn't fit verbatim.
    Summary at 100 tokens fits as P6."""

    budget = 4_000
    provider = _make_provider(_text(100))  # summary text = 100 tokens

    blocks = await assemble_moderator_context(
        system_prompt=_text(1_000),
        inputs_text=_text(2_000),
        kanban_state=_text(100),
        queued_human_messages=[_text(50)],
        latest_bundle_text=_text(500),
        prior_bundle_pairs=[("bundle_001", _text(400))],
        budget=budget,
        session_dir=tmp_path,
        adapter=provider,
        model="mock-model",
    )
    # used after P0-P4 = 1000+2000+100+50+500 = 3650; remaining = 350
    # prior bundle at 400 tokens → 3650+400=4050 > 4000 → P6
    p5 = [b for b in blocks if b.priority == "P5"]
    p6 = [b for b in blocks if b.priority == "P6"]
    assert len(p5) == 0
    assert len(p6) == 1


@pytest.mark.asyncio
async def test_assembler_budget_exactly_met():
    """Budget exactly met (0 tokens remaining) → succeeds."""

    budget = 1_000
    blocks = await assemble_moderator_context(
        system_prompt=_text(500),
        inputs_text=_text(500),
        kanban_state="",
        queued_human_messages=[],
        latest_bundle_text=None,
        prior_bundle_pairs=[],
        budget=budget,
    )
    assert blocks  # no exception raised


@pytest.mark.asyncio
async def test_assembler_raises_when_p0_p3_exceed_budget():
    """P0–P3 together exceed budget → ContextBudgetExceeded."""

    with pytest.raises(ContextBudgetExceeded):
        await assemble_moderator_context(
            system_prompt=_text(5_000),
            inputs_text=_text(5_000),
            kanban_state=_text(100),
            queued_human_messages=[],
            latest_bundle_text=None,
            prior_bundle_pairs=[],
            budget=1_000,
        )


# ---------------------------------------------------------------------------
# summarizer.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_bundle_calls_provider():
    provider = _make_provider("Short summary.")
    result = await summarize_bundle("bundle content here", provider, "mock-model")
    assert result == "Short summary."
    assert provider.call_count == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_or_create_summary_creates_and_caches(tmp_path):
    """First call creates the file; second call reads from disk without calling provider."""

    provider = _make_provider("Cached summary text.")
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()

    # First call — provider is invoked, file is written
    result1 = await get_or_create_summary(tmp_path, "bundle_001", "bundle content", provider, "m")
    assert result1 == "Cached summary text."
    assert provider.call_count == 1  # type: ignore[attr-defined]

    # Second call — reads from disk, provider NOT invoked
    result2 = await get_or_create_summary(tmp_path, "bundle_001", "bundle content", provider, "m")
    assert result2 == "Cached summary text."
    assert provider.call_count == 1  # type: ignore[attr-defined]  # unchanged


@pytest.mark.asyncio
async def test_get_or_create_summary_file_is_persisted(tmp_path):
    provider = _make_provider("Persisted summary.")
    (tmp_path / "bundles").mkdir()

    await get_or_create_summary(tmp_path, "bundle_002", "content", provider, "m")

    summary_file = tmp_path / "bundles" / "bundle_002_summary.txt"
    assert summary_file.exists()
    assert summary_file.read_text() == "Persisted summary."


@pytest.mark.asyncio
async def test_assembler_no_summarizer_drops_bundle_gracefully():
    """Without adapter/session_dir, bundles that don't fit are silently dropped."""

    budget = 200
    blocks = await assemble_moderator_context(
        system_prompt=_text(50),
        inputs_text=_text(50),
        kanban_state=_text(10),
        queued_human_messages=[],
        latest_bundle_text=None,
        prior_bundle_pairs=[("bundle_001", _text(200))],
        budget=budget,
        session_dir=None,
        adapter=None,
        model=None,
    )
    assert not any(b.priority in ("P5", "P6") for b in blocks)
