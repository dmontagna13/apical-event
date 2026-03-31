"""Consensus output schema."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, RootModel


class ReturnHeader(RootModel[dict[str, object]]):
    """Dynamic return header fields defined by the output contract."""


class SessionStatistics(BaseModel):
    """Summary statistics for a session."""

    total_turns: int
    agent_turns: dict[str, int]
    human_decisions: int
    duration_minutes: int


class ConsensusOutput(BaseModel):
    """Consensus output written at session completion."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: Optional[str] = Field(default=None, alias="$schema")
    packet_id: str
    session_id: str
    completed_at: datetime
    return_header: ReturnHeader
    sections: dict[str, dict]
    stop_condition_met: bool
    dissenting_opinions: list[str]
    session_statistics: SessionStatistics
    validation_warnings: Optional[list[str]] = None
