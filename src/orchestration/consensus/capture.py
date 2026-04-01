"""CONSENSUS state — run consensus capture from the Moderator LLM (§7.2)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from api.websocket.manager import ConnectionManager
from core.config import ProviderConfig, resolve_api_key
from core.journals import read_all_journals, save_state
from core.journals.session_dir import load_packet, load_roll_call
from core.prompt_assembly.consensus_prompt import assemble_consensus_prompt
from core.providers.base import Message, ProviderAdapter
from core.providers.factory import get_adapter
from core.schemas.constants import CONSENSUS_RETRY_MAX
from core.schemas.enums import SessionState
from orchestration.consensus.archive import build_session_archive, write_archive
from orchestration.consensus.validator import validate_consensus

logger = logging.getLogger(__name__)


async def run_consensus_capture(
    session_dir: Path,
    state: dict,
    manager: ConnectionManager,
    providers_config: dict[str, ProviderConfig],
    data_root: Path | None = None,
) -> dict:
    """Drive the consensus capture flow.

    Steps:
    1. Assemble session history from all agent journals.
    2. Build consensus prompt and call the Moderator LLM.
    3. Parse and validate the JSON response.
    4. Retry up to CONSENSUS_RETRY_MAX on hard validation failures.
    5. Write outputs (consensus.json, session_archive.json, callback path).
    6. Transition state to COMPLETED.

    Returns the updated state dict.
    """
    session_id = state["session_id"]
    packet = load_packet(session_dir)
    roll_call = load_roll_call(session_dir)

    # Resolve the moderator's provider adapter
    moderator_role = next(r for r in packet.roles if r.is_moderator)
    moderator_assignment = next(
        a for a in roll_call.assignments if a.role_id == moderator_role.role_id
    )
    provider_cfg = providers_config[moderator_assignment.provider]
    api_key = resolve_api_key(provider_cfg)
    resolved_cfg = provider_cfg.model_copy(update={"api_key": api_key})
    adapter: ProviderAdapter = get_adapter(moderator_assignment.provider, resolved_cfg)
    model = moderator_assignment.model

    # Build session history from all journals
    session_history = _format_session_history(session_dir)

    # Assemble the consensus system prompt
    system_prompt = assemble_consensus_prompt(packet, session_history)

    messages: list[Message] = [
        Message(role="system", content=system_prompt),
        Message(role="user", content="Produce the final return now."),
    ]

    output: dict | None = None
    hard_errors: list[str] = []
    warnings: list[str] = []

    for attempt in range(CONSENSUS_RETRY_MAX + 1):
        try:
            result = await adapter.complete(
                messages,
                model,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Consensus LLM call failed (attempt %d): %s", attempt + 1, exc)
            if attempt < CONSENSUS_RETRY_MAX:
                await asyncio.sleep(2 ** attempt)
                continue
            state["state"] = SessionState.ERROR.value
            state["error"] = f"Consensus capture failed after {CONSENSUS_RETRY_MAX + 1} attempts: {exc}"
            return state

        try:
            output = json.loads(result.text)
        except json.JSONDecodeError as exc:
            logger.warning("Consensus response is not valid JSON (attempt %d): %s", attempt + 1, exc)
            output = None
            if attempt < CONSENSUS_RETRY_MAX:
                retry_msg = (
                    f"Your response was not valid JSON. Error: {exc}\n"
                    "Please produce ONLY a valid JSON object."
                )
                messages.append(Message(role="assistant", content=result.text))
                messages.append(Message(role="user", content=retry_msg))
                continue
            # Final attempt still bad JSON — write empty output with warnings
            output = {}
            hard_errors = ["Response was not valid JSON"]
            break

        # Validate output
        all_issues = validate_consensus(output, packet.output_contract)
        warnings = [e for e in all_issues if e.startswith("Warning:")]
        hard_errors = [e for e in all_issues if not e.startswith("Warning:")]

        if not hard_errors:
            break  # All hard constraints satisfied

        if attempt < CONSENSUS_RETRY_MAX:
            logger.warning(
                "Consensus validation failed (attempt %d): %s", attempt + 1, hard_errors
            )
            error_list = "\n".join(f"- {e}" for e in hard_errors)
            retry_msg = (
                "Your consensus output failed validation. Please fix these errors:\n"
                f"{error_list}\n\n"
                "Reproduce the full JSON object with these issues corrected."
            )
            messages.append(Message(role="assistant", content=result.text))
            messages.append(Message(role="user", content=retry_msg))

    # Build the final ConsensusOutput dict (validation_warnings if needed)
    all_validation_warnings = hard_errors + warnings if hard_errors else warnings
    now = datetime.now(tz=timezone.utc).isoformat()

    consensus_dict: dict = output or {}
    # Inject metadata fields from state
    consensus_dict.setdefault("$schema", "https://apical.local/schemas/consensus-output/v1")
    consensus_dict.setdefault("packet_id", packet.packet_id)
    consensus_dict.setdefault("session_id", session_id)
    consensus_dict.setdefault("completed_at", now)
    if all_validation_warnings:
        consensus_dict["validation_warnings"] = all_validation_warnings

    # Write archive — includes consensus
    # Temporarily write consensus.json so build_session_archive can include it
    _write_tmp_consensus(session_dir, consensus_dict)

    archive = build_session_archive(session_dir)
    write_archive(session_dir, archive, data_root=data_root)

    # Broadcast completion event
    await manager.broadcast(
        session_id,
        {
            "event": "consensus_complete",
            "data": {
                "validation_warnings": all_validation_warnings,
                "completed_at": now,
            },
        },
    )

    state["state"] = SessionState.COMPLETED.value
    state["substate"] = None
    return state


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_session_history(session_dir: Path) -> str:
    """Render all agent journal turns as chronological text."""
    journals = read_all_journals(session_dir)
    all_turns = []
    for journal in journals:
        for turn in journal.turns:
            all_turns.append(turn)

    # Sort by timestamp (AgentTurn has a timestamp field)
    all_turns.sort(key=lambda t: t.timestamp)

    lines = []
    for turn in all_turns:
        lines.append(
            f"[{turn.bundle_id}] {turn.role_id} — status: {turn.status}\n"
            f"Prompt:\n{turn.approved_prompt}\n\n"
            f"Response:\n{turn.agent_response}"
        )
    return "\n\n---\n\n".join(lines) if lines else "(no agent turns recorded)"


def _write_tmp_consensus(session_dir: Path, consensus_dict: dict) -> None:
    """Write consensus.json to output/ so build_session_archive picks it up."""
    import os

    output_dir = session_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "consensus.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(consensus_dict, indent=2, default=str))
    os.replace(tmp, path)
