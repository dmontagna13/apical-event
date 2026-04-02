"""Agent response bundle schema."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import BundleType


class BundledResponse(BaseModel):
    """Single agent response within a bundle."""

    role_id: str
    turn_id: UUID
    response_text: str
    status: str = Field(description="OK | TIMEOUT | ERROR")
    error_message: Optional[str] = Field(default=None)
    latency_ms: int


class AgentResponseBundle(BaseModel):
    """Bundle of responses for a dispatch round."""

    bundle_id: str = Field(description="Monotonically increasing: bundle_001, bundle_002, ...")
    bundle_type: BundleType = Field(description="INIT | DELIBERATION")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    responses: list[BundledResponse]
