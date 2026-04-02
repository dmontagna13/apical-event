"""Kanban board schema."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import KanbanStatus
from .packet import AgendaItem


class KanbanTask(BaseModel):
    """Single kanban task derived from an agenda item."""

    task_id: str = Field(description="Maps to agenda question_id")
    title: str
    status: KanbanStatus = Field(default=KanbanStatus.TO_DISCUSS)
    notes: str = ""
    linked_card_id: Optional[UUID] = None
    linked_quiz_id: Optional[UUID] = None


class KanbanBoard(BaseModel):
    """Collection of kanban tasks."""

    tasks: list[KanbanTask] = Field(default_factory=list)

    @classmethod
    def from_agenda(cls, agenda: list[AgendaItem]) -> "KanbanBoard":
        """Create a kanban board from agenda items."""

        tasks = [
            KanbanTask(
                task_id=item.question_id,
                title=item.text,
                status=KanbanStatus.TO_DISCUSS,
            )
            for item in agenda
        ]
        return cls(tasks=tasks)
