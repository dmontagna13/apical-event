"""Agent journal schema."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentTurn(BaseModel):
    """Single agent turn within a dispatch bundle."""

    turn_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    role_id: str
    bundle_id: str = Field(description="Which dispatch round this turn belongs to")
    prompt_hash: str = Field(description="SHA-256 of the approved prompt text")
    approved_prompt: str = Field(
        description="The exact text sent, after human approval/modification"
    )
    agent_response: str = Field(description="The raw output returned by the model")
    status: str = Field(default="OK", description="OK | TIMEOUT | ERROR")
    error_message: Optional[str] = Field(default=None)
    metadata: dict = Field(
        default_factory=dict, description="Token counts, latency_ms, finish_reason"
    )


class AgentJournal(BaseModel):
    """Append-only journal for a single agent."""

    agent_id: str = Field(description="Matches role_id from packet")
    session_id: str
    turns: list[AgentTurn] = Field(default_factory=list)
