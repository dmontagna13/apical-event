"""Agent prompt assembly."""

from __future__ import annotations

from core.schemas import Role, SessionPacket


def assemble_agent_prompt(packet: SessionPacket, role: Role) -> str:
    """Assemble the system prompt for a background agent."""

    constraints = "\n".join(f"- {constraint}" for constraint in packet.constraints)
    inputs_blocks = []
    for input_doc in packet.inputs:
        status = f" [{input_doc.status}]" if input_doc.status else ""
        inputs_blocks.append(f"### {input_doc.path}{status}\n{input_doc.content}")
    inputs_text = "\n\n".join(inputs_blocks)
    required_sections = ", ".join(packet.output_contract.required_sections)

    return (
        f"ROLE: {role.role_id} ({role.label})\n"
        f"SESSION: {packet.packet_id} | {packet.meeting_class} | {packet.created_at}\n\n"
        f"OBJECTIVE: {packet.objective}\n\n"
        "CONSTRAINTS (violations are grounds for output rejection):\n"
        f"{constraints}\n\n"
        "YOUR MISSION:\n"
        f"{role.behavioral_directive}\n\n"
        "CONTEXT DOCUMENTS:\n"
        f"{inputs_text}\n\n"
        "OUTPUT EXPECTATIONS:\n"
        "You are contributing to a deliberation that will produce a "
        f"{packet.output_contract.return_type}.\n"
        f"Required sections: {required_sections}\n"
        "Your responses will be bundled with other agents' responses and delivered to the "
        "Moderator.\n"
        "The human operator reads your responses but does not reply to you directly.\n"
        "Do not produce the final return — that is the Moderator's job after consensus."
    )
