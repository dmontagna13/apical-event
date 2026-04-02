"""Moderator prompt assembly."""

from __future__ import annotations

from core.schemas import Role, SessionPacket


def assemble_moderator_prompt(
    packet: SessionPacket,
    role: Role,
    non_moderator_role_ids: list[str],
    tool_definitions_text: str,
    kanban_state: str,
) -> str:
    """Assemble the system prompt for the moderator."""

    constraints = "\n".join(f"- {constraint}" for constraint in packet.constraints)
    inputs_blocks = []
    for input_doc in packet.inputs:
        status = f" [{input_doc.status}]" if input_doc.status else ""
        inputs_blocks.append(f"### {input_doc.path}{status}\n{input_doc.content}")
    inputs_text = "\n\n".join(inputs_blocks)
    required_sections = ", ".join(packet.output_contract.required_sections)
    background_ids = ", ".join(non_moderator_role_ids)

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
        "Do not produce the final return — that is the Moderator's job after consensus.\n\n"
        "MODERATOR RESPONSIBILITIES:\n"
        "You are the sole agent the human operator interacts with.\n"
        f"Background agents ({background_ids}) respond to your prompts.\n"
        "Their responses arrive as bundled payloads — one bundle per dispatch round.\n\n"
        "TOOL-USE PROTOCOL\n\n"
        "Use tools by calling them - do not emit tool JSON in plain text.\n\n"
        "When a new bundle has arrived:\n"
        "  Call update_kanban to advance task statuses based on the bundle content.\n"
        "  Then call generate_action_cards OR generate_decision_quiz based on where deliberation stands:\n"
        "    - generate_action_cards: when gaps or tensions in the bundle require follow-up from agents.\n"
        "      One card per agent you are targeting. Target only agents from the current bundle.\n"
        "    - generate_decision_quiz: when deliberation has converged on 2+ viable paths and the\n"
        "      human must choose. Always set allow_freeform: true.\n"
        "  Then respond with your conversational synthesis for the human. When you have no more\n"
        "  tool calls to make, respond with text only - that ends your turn.\n\n"
        "When the human sends a direct message with no new bundle:\n"
        "  Respond conversationally. Call update_kanban only if a status adjustment is warranted.\n\n"
        "A quiz result returns directly to you. It does not trigger agent dispatch.\n"
        "Never target the moderator role in an action card.\n\n"
        "You control the pace and direction of deliberation. The human controls the decisions.\n\n"
        "AVAILABLE TOOLS:\n"
        f"{tool_definitions_text}\n\n"
        "CURRENT KANBAN STATE:\n"
        f"{kanban_state}"
    )
