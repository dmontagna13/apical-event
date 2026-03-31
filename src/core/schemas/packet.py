"""Session packet schema and validation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from .enums import MeetingClass

ROLE_ID_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z]{2,6}$")


class Role(BaseModel):
    """Role definition in a session packet."""

    role_id: str
    label: str
    is_moderator: bool
    behavioral_directive: str


class Input(BaseModel):
    """Embedded input document content."""

    path: str
    status: Optional[str] = None
    content: str


class AgendaItem(BaseModel):
    """Agenda question item."""

    question_id: str
    text: str


class OutputContract(BaseModel):
    """Definition of consensus output requirements."""

    return_type: str
    required_sections: list[str]
    minimum_counts: Optional[dict[str, int]] = None
    return_header_fields: list[str]
    save_path: str


class Callback(BaseModel):
    """Consensus callback configuration."""

    method: str
    path: str


class SessionPacket(BaseModel):
    """Canonical packet used to initialize a session."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: Optional[str] = Field(default=None, alias="$schema")
    packet_id: str
    project_name: str
    created_at: datetime
    meeting_class: MeetingClass
    objective: str
    constraints: list[str]
    roles: list[Role]
    inputs: list[Input]
    agenda: list[AgendaItem]
    output_contract: OutputContract
    stop_condition: str
    evidence_required: bool
    evidence_instructions: Optional[str] = None
    callback: Callback


def validate_packet(packet: SessionPacket) -> list[str]:
    """Validate packet constraints not enforced by schema types."""

    errors: list[str] = []

    if len(packet.roles) < 2:
        errors.append("Packet must include at least 2 roles.")

    moderator_count = sum(1 for role in packet.roles if role.is_moderator)
    if moderator_count != 1:
        errors.append("Packet must include exactly one moderator role.")

    if len(packet.inputs) < 1:
        errors.append("Packet must include at least 1 input document.")

    role_ids = [role.role_id for role in packet.roles]
    if len(role_ids) != len(set(role_ids)):
        errors.append("Packet role_id values must be unique.")

    for role_id in role_ids:
        if not ROLE_ID_PATTERN.match(role_id):
            errors.append(f"Invalid role_id format: {role_id}.")

    question_ids = [item.question_id for item in packet.agenda]
    if len(question_ids) != len(set(question_ids)):
        errors.append("Agenda question_id values must be unique.")

    if packet.callback.method != "filesystem":
        errors.append("Callback method must be 'filesystem' for v1.")

    return errors
