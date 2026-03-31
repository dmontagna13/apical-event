"""Roll call schema for role assignments."""

from datetime import datetime

from pydantic import BaseModel, Field


class RoleAssignment(BaseModel):
    """Role assignment to provider and model."""

    role_id: str
    provider: str = Field(description="Key from providers.yaml")
    model: str = Field(description="Model ID from provider's available_models")


class RollCall(BaseModel):
    """Collection of role assignments."""

    assignments: list[RoleAssignment]
    confirmed_at: datetime = Field(default_factory=datetime.utcnow)
