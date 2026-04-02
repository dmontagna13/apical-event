"""Enums for shared schema fields."""

from enum import Enum


class SessionState(str, Enum):
    """Top-level session state."""

    PACKET_RECEIVED = "PACKET_RECEIVED"
    ROLL_CALL = "ROLL_CALL"
    ACTIVE = "ACTIVE"
    CONSENSUS = "CONSENSUS"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    ABANDONED = "ABANDONED"
    ERROR = "ERROR"


class SessionSubstate(str, Enum):
    """Substate for ACTIVE sessions."""

    INIT_DISPATCH = "INIT_DISPATCH"
    AGENT_AGGREGATION = "AGENT_AGGREGATION"
    MODERATOR_TURN = "MODERATOR_TURN"
    HUMAN_GATE = "HUMAN_GATE"
    AGENT_DISPATCH = "AGENT_DISPATCH"


class TurnType(str, Enum):
    """Agent turn type."""

    INIT = "INIT"
    DELIBERATION = "DELIBERATION"


class BundleType(str, Enum):
    """Agent response bundle type."""

    INIT = "INIT"
    DELIBERATION = "DELIBERATION"


class MeetingClass(str, Enum):
    """Meeting class of a session packet."""

    DISCOVERY = "DISCOVERY"
    ADR_DEBATE = "ADR_DEBATE"
    DESIGN_SPIKE = "DESIGN_SPIKE"
    RISK_REVIEW = "RISK_REVIEW"
    SYNTHESIS = "SYNTHESIS"


class KanbanStatus(str, Enum):
    """Kanban task status values."""

    TO_DISCUSS = "TO_DISCUSS"
    AGENT_DELIBERATION = "AGENT_DELIBERATION"
    PENDING_HUMAN_DECISION = "PENDING_HUMAN_DECISION"
    RESOLVED = "RESOLVED"


class ActionCardStatus(str, Enum):
    """Action card resolution states."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    MODIFIED = "MODIFIED"
    DENIED = "DENIED"


class ErrorCode(str, Enum):
    """API error codes."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    CONFLICT = "CONFLICT"
    BAD_REQUEST = "BAD_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"
