"""Action card and decision quiz schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ActionCard(BaseModel):
    """Moderator action card for agent dispatch."""

    card_id: UUID = Field(default_factory=uuid4)
    target_role_id: str
    prompt_text: str
    context_note: str
    linked_question_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="PENDING", description="PENDING | APPROVED | MODIFIED | DENIED")
    human_modified_prompt: Optional[str] = Field(default=None)
    denial_reason: Optional[str] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)


class DecisionQuiz(BaseModel):
    """Decision quiz surfaced to the human operator."""

    quiz_id: UUID = Field(default_factory=uuid4)
    decision_title: str
    options: list[str]
    allow_freeform: bool = True
    context_summary: str
    linked_question_ids: list[str] = Field(default_factory=list)
    selected_option: Optional[str] = Field(default=None)
    freeform_text: Optional[str] = Field(default=None)
    resolved: bool = False
    resolved_at: Optional[datetime] = Field(default=None)
