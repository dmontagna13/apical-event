// SYNC: These types must match src/core/schemas/*.py

export type SessionState =
  | "PACKET_RECEIVED"
  | "ROLL_CALL"
  | "ACTIVE"
  | "CONSENSUS"
  | "COMPLETED"
  | "COMPLETED_WITH_WARNINGS"
  | "ABANDONED"
  | "ERROR";

export type SessionSubstate =
  | "INIT_DISPATCH"
  | "AGENT_AGGREGATION"
  | "MODERATOR_TURN"
  | "HUMAN_GATE"
  | "AGENT_DISPATCH";

export type MeetingClass =
  | "DISCOVERY"
  | "ADR_DEBATE"
  | "DESIGN_SPIKE"
  | "RISK_REVIEW"
  | "SYNTHESIS";

export type KanbanStatus =
  | "TO_DISCUSS"
  | "AGENT_DELIBERATION"
  | "PENDING_HUMAN_DECISION"
  | "RESOLVED";

export type TurnType = "INIT" | "DELIBERATION";
export type BundleType = "INIT" | "DELIBERATION";

export type ActionCardStatus = "PENDING" | "APPROVED" | "MODIFIED" | "DENIED";

export type ErrorCode =
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "PROVIDER_ERROR"
  | "CONFLICT"
  | "BAD_REQUEST"
  | "INTERNAL_ERROR";

export interface Role {
  role_id: string;
  label: string;
  is_moderator: boolean;
  behavioral_directive: string;
}

export interface Input {
  path: string;
  status?: string | null;
  content: string;
}

export interface AgendaItem {
  question_id: string;
  text: string;
}

export interface OutputContract {
  return_type: string;
  required_sections: string[];
  minimum_counts?: Record<string, number> | null;
  return_header_fields: string[];
  save_path: string;
}

export interface Callback {
  method: string;
  path: string;
}

export interface SessionPacket {
  $schema?: string | null;
  packet_id: string;
  project_name: string;
  created_at: string;
  meeting_class: MeetingClass;
  objective: string;
  constraints: string[];
  roles: Role[];
  inputs: Input[];
  agenda: AgendaItem[];
  output_contract: OutputContract;
  stop_condition: string;
  evidence_required: boolean;
  evidence_instructions?: string | null;
  callback: Callback;
}

export interface RoleAssignment {
  role_id: string;
  provider: string;
  model: string;
}

export interface RollCall {
  assignments: RoleAssignment[];
  confirmed_at: string;
}

export interface ActionCard {
  card_id: string;
  target_role_id: string;
  prompt_text: string;
  context_note: string;
  linked_question_ids: string[];
  status: ActionCardStatus | string;
  human_modified_prompt?: string | null;
  denial_reason?: string | null;
  resolved_at?: string | null;
}

export interface DecisionQuiz {
  quiz_id: string;
  decision_title: string;
  options: string[];
  allow_freeform: boolean;
  context_summary: string;
  linked_question_ids: string[];
  selected_option?: string | null;
  freeform_text?: string | null;
  resolved: boolean;
  resolved_at?: string | null;
}

export interface KanbanTask {
  task_id: string;
  title: string;
  status: KanbanStatus;
  notes: string;
  linked_card_id?: string | null;
  linked_quiz_id?: string | null;
}

export interface KanbanBoard {
  tasks: KanbanTask[];
}

export interface AgentTurn {
  turn_id: string;
  timestamp: string;
  session_id: string;
  role_id: string;
  turn_type: TurnType;
  bundle_id: string | null;
  prompt_hash: string;
  approved_prompt: string;
  agent_response: string;
  status: "OK" | "TIMEOUT" | "ERROR";
  error_message: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentJournal {
  agent_id: string;
  session_id: string;
  turns: AgentTurn[];
}

export interface BundledResponse {
  role_id: string;
  turn_id: string;
  response_text: string;
  status: string;
  error_message?: string | null;
  latency_ms: number;
}

export interface AgentResponseBundle {
  bundle_id: string;
  bundle_type: BundleType;
  timestamp: string;
  responses: BundledResponse[];
}

export type ReturnHeader = Record<string, unknown>;

export interface SessionStatistics {
  total_turns: number;
  agent_turns: Record<string, number>;
  human_decisions: number;
  duration_minutes: number;
}

export interface ConsensusOutput {
  $schema?: string | null;
  packet_id: string;
  session_id: string;
  completed_at: string;
  return_header: ReturnHeader;
  sections: Record<string, Record<string, unknown>>;
  stop_condition_met: boolean;
  dissenting_opinions: string[];
  session_statistics: SessionStatistics;
  validation_warnings?: string[] | null;
}
