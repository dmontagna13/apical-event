"""Moderator tool definitions (provider-agnostic)."""

from __future__ import annotations

from core.providers.base import ToolDefinition


def get_tool_definitions() -> list[ToolDefinition]:
    """Return the three moderator tool definitions matching §5.1."""

    return [
        ToolDefinition(
            name="generate_action_cards",
            description="Create one or more prompt cards to send to background agents for deliberation.",
            parameters={
                "type": "object",
                "properties": {
                    "cards": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_role_id": {
                                    "type": "string",
                                    "description": "The role_id of the agent to receive this prompt",
                                },
                                "prompt_text": {
                                    "type": "string",
                                    "description": "The exact prompt to send to the agent (subject to human approval)",
                                },
                                "context_note": {
                                    "type": "string",
                                    "description": "Brief note to the human operator explaining why this prompt is needed",
                                },
                                "linked_question_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Which agenda questions this card advances",
                                },
                            },
                            "required": ["target_role_id", "prompt_text", "context_note"],
                        },
                    }
                },
                "required": ["cards"],
            },
        ),
        ToolDefinition(
            name="generate_decision_quiz",
            description="Present a decision point to the human operator with predefined options.",
            parameters={
                "type": "object",
                "properties": {
                    "decision_title": {
                        "type": "string",
                        "description": "The central question or decision point",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Predefined answer choices",
                    },
                    "allow_freeform": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to include an 'Other' text input field",
                    },
                    "linked_question_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which agenda questions this decision resolves",
                    },
                    "context_summary": {
                        "type": "string",
                        "description": "Moderator's synthesis of agent positions leading to this decision",
                    },
                },
                "required": ["decision_title", "options", "context_summary"],
            },
        ),
        ToolDefinition(
            name="update_kanban",
            description="Update the status of Kanban tasks or add notes.",
            parameters={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_id": {
                                    "type": "string",
                                    "description": "The agenda question ID to update",
                                },
                                "new_status": {
                                    "type": "string",
                                    "enum": [
                                        "TO_DISCUSS",
                                        "AGENT_DELIBERATION",
                                        "PENDING_HUMAN_DECISION",
                                        "RESOLVED",
                                    ],
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Moderator's internal notes on progress",
                                },
                            },
                            "required": ["question_id", "new_status"],
                        },
                    }
                },
                "required": ["updates"],
            },
        ),
    ]
