"""Consensus prompt assembly."""

from __future__ import annotations

from core.schemas import SessionPacket


def assemble_consensus_prompt(packet: SessionPacket, session_history: str) -> str:
    """Assemble the consensus capture prompt."""

    header_fields = "\n".join(
        f"{field}: <value>" for field in packet.output_contract.return_header_fields
    )
    required_sections = []
    minimum_counts = packet.output_contract.minimum_counts or {}
    for section in packet.output_contract.required_sections:
        if section in minimum_counts:
            required_sections.append(f"- {section} (minimum: {minimum_counts[section]})")
        else:
            required_sections.append(f"- {section}")
    required_sections_text = "\n".join(required_sections)

    inputs_blocks = []
    for input_doc in packet.inputs:
        status = f" [{input_doc.status}]" if input_doc.status else ""
        inputs_blocks.append(f"### {input_doc.path}{status}\n{input_doc.content}")
    inputs_text = "\n\n".join(inputs_blocks)

    return (
        f"CONSENSUS CAPTURE — {packet.packet_id}\n\n"
        "You are producing the final return for this deliberation session.\n\n"
        "OUTPUT ONLY the return content. No commentary, no preamble, no sign-off.\n\n"
        "RETURN HEADER (include all fields):\n"
        f"{header_fields}\n\n"
        "---\n\n"
        "REQUIRED SECTIONS:\n"
        f"{required_sections_text}\n\n"
        "STOP CONDITION (must be satisfied):\n"
        f"{packet.stop_condition}\n\n"
        "CONTEXT DOCUMENTS:\n"
        f"{inputs_text}\n\n"
        "SESSION HISTORY:\n"
        f"{session_history}"
    )
