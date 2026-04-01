import type {
  ActionCard,
  AgentJournal,
  AgentResponseBundle,
  BundledResponse,
  DecisionQuiz,
  KanbanBoard,
  KanbanTask,
  SessionState,
  SessionSubstate,
} from "../types";

export interface ChatMessage {
  role: string;
  content: string;
  role_id?: string;
}

export interface SessionStateChangedData {
  state: SessionState;
  substate: SessionSubstate | null;
}

export interface ModeratorTextData {
  text: string;
}

export interface ActionCardsCreatedData {
  cards: ActionCard[];
}

export interface DecisionQuizCreatedData {
  quiz: DecisionQuiz;
}

export interface KanbanUpdatedData {
  tasks: KanbanTask[];
  kanban?: KanbanBoard;
}

export interface AgentDispatchStartedData {
  role_ids: string[];
  card_ids: string[];
}

export interface AgentResponseReceivedData {
  role_id: string;
  turn_id: string;
  response_text: string;
  latency_ms: number;
}

export interface AgentResponseErrorData {
  role_id: string;
  status: string;
  error_message: string;
}

export interface AgentBundleCompleteData {
  bundle_id: string;
  responses_count: number;
  errors_count: number;
}

export interface BundleReadyData {
  bundle_id: string;
  responses: BundledResponse[];
}

export interface ConsensusTriggeredData {
  reason: string;
}

export interface ConsensusCompleteData {
  validation_warnings: string[];
  completed_at: string;
}

export interface ToolCallDroppedData {
  tool: string;
  errors: string[];
}

export interface ErrorEventData {
  code: string;
  message: string;
  role_id?: string;
  recoverable?: boolean;
  details?: string[];
}

export interface StateSyncData {
  chat_history: ChatMessage[];
  kanban: KanbanBoard | null;
  pending_actions: ActionCard[];
  pending_quizzes: DecisionQuiz[];
  session_state: SessionState;
  substate: SessionSubstate | null;
  journals?: AgentJournal[];
  bundles?: AgentResponseBundle[];
}

export interface HumanMessageQueuedData {
  text: string;
  queue_position: number;
}

export interface ConnectionLostData {
  reason?: string;
}

export interface ConnectionRestoredData {
  attempts: number;
}

export type ServerEventMap = {
  session_state_changed: SessionStateChangedData;
  moderator_text: ModeratorTextData;
  action_cards_created: ActionCardsCreatedData;
  decision_quiz_created: DecisionQuizCreatedData;
  kanban_updated: KanbanUpdatedData;
  agent_dispatch_started: AgentDispatchStartedData;
  agent_response_received: AgentResponseReceivedData;
  agent_response_error: AgentResponseErrorData;
  agent_bundle_complete: AgentBundleCompleteData;
  bundle_ready: BundleReadyData;
  consensus_triggered: ConsensusTriggeredData;
  consensus_complete: ConsensusCompleteData;
  tool_call_dropped: ToolCallDroppedData;
  error: ErrorEventData;
  state_sync: StateSyncData;
  human_message_queued: HumanMessageQueuedData;
  connection_lost: ConnectionLostData;
  connection_restored: ConnectionRestoredData;
};

export type ClientEvent =
  | { event: "human_message"; data: { text: string } }
  | { event: "action_card_resolved"; data: { card_id: string; status: string; modified_prompt?: string | null; denial_reason?: string | null } }
  | { event: "dispatch_approved"; data?: { card_resolutions?: CardResolution[]; quiz_answers?: QuizAnswer[] } }
  | { event: "decision_quiz_resolved"; data: { quiz_id: string; selected_option: string; freeform_text?: string | null } }
  | { event: "trigger_consensus"; data: {} }
  | { event: "abandon_session"; data: { reason: string } };

export interface CardResolution {
  card_id: string;
  action: "APPROVED" | "MODIFIED" | "DENIED";
  modified_prompt?: string | null;
  denial_reason?: string | null;
}

export interface QuizAnswer {
  quiz_id: string;
  selected_option: string | null;
  freeform_text?: string | null;
}

type EventHandler<K extends keyof ServerEventMap> = (data: ServerEventMap[K]) => void;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && !Number.isNaN(value) ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function resolveWsBaseUrl(): string {
  const env = import.meta.env as { VITE_WS_BASE_URL?: string };
  if (env.VITE_WS_BASE_URL) {
    return env.VITE_WS_BASE_URL;
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}`;
}

export class SessionWebSocket {
  private socket: WebSocket | null = null;

  private sessionId: string | null = null;

  private reconnectAttempts = 0;

  private reconnectTimer: number | null = null;

  private shouldReconnect = false;

  private hasConnectedOnce = false;

  private lostSinceLastConnect = false;

  private listeners = new Map<keyof ServerEventMap, Set<(data: unknown) => void>>();

  connect(sessionId: string): void {
    if (this.sessionId === sessionId && this.socket) {
      const state = this.socket.readyState;
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
        this.shouldReconnect = true;
        return;
      }
    }

    if (this.sessionId && this.sessionId !== sessionId) {
      this.disconnect();
    }

    this.sessionId = sessionId;
    this.shouldReconnect = true;
    this.openSocket();
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.clearReconnectTimer();
    if (this.socket) {
      this.socket.close();
    }
    this.socket = null;
  }

  send(event: ClientEvent): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const normalized = this.normalizeOutgoing(event);
    this.socket.send(JSON.stringify(normalized));
  }

  on<K extends keyof ServerEventMap>(eventType: K, handler: EventHandler<K>): void {
    const handlers = this.listeners.get(eventType) ?? new Set<(data: unknown) => void>();
    handlers.add(handler as (data: unknown) => void);
    this.listeners.set(eventType, handlers);
  }

  off<K extends keyof ServerEventMap>(eventType: K, handler: EventHandler<K>): void {
    const handlers = this.listeners.get(eventType);
    handlers?.delete(handler as (data: unknown) => void);
  }

  private emit<K extends keyof ServerEventMap>(eventType: K, data: ServerEventMap[K]): void {
    this.listeners.get(eventType)?.forEach((handler) => handler(data));
  }

  private openSocket(): void {
    if (!this.sessionId) {
      return;
    }
    if (this.socket) {
      const state = this.socket.readyState;
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) {
        return;
      }
    }
    const url = `${resolveWsBaseUrl()}/ws/session/${this.sessionId}`;
    this.socket = new WebSocket(url);

    this.socket.addEventListener("open", () => {
      this.clearReconnectTimer();
      const restored = this.lostSinceLastConnect;
      this.lostSinceLastConnect = false;
      if (this.hasConnectedOnce && restored) {
        this.emit("connection_restored", { attempts: this.reconnectAttempts });
      }
      this.hasConnectedOnce = true;
      this.reconnectAttempts = 0;
    });

    this.socket.addEventListener("message", (event) => {
      if (typeof event.data !== "string") {
        return;
      }
      let payload: unknown;
      try {
        payload = JSON.parse(event.data) as unknown;
      } catch {
        return;
      }
      this.handleIncoming(payload);
    });

    this.socket.addEventListener("close", () => {
      this.socket = null;
      if (!this.shouldReconnect) {
        return;
      }
      this.lostSinceLastConnect = true;
      this.emit("connection_lost", { reason: "Connection closed" });
      this.scheduleReconnect();
    });
  }

  private handleIncoming(payload: unknown): void {
    if (!isRecord(payload)) {
      return;
    }
    const eventType = payload.event;
    const data = payload.data;
    if (typeof eventType !== "string") {
      return;
    }

    switch (eventType) {
      case "session_state_changed":
        if (isRecord(data)) {
          this.emit("session_state_changed", {
            state: asString(data.state) as SessionState,
            substate: (data.substate as SessionSubstate | null) ?? null,
          });
        }
        return;
      case "moderator_text":
        this.emit("moderator_text", { text: asString(isRecord(data) ? data.text : "") });
        return;
      case "moderator_turn":
        this.emit("moderator_text", { text: asString(isRecord(data) ? data.text : "") });
        return;
      case "action_cards_created":
        if (isRecord(data) && Array.isArray(data.cards)) {
          this.emit("action_cards_created", { cards: data.cards as ActionCard[] });
        }
        return;
      case "decision_quiz_created":
        if (isRecord(data)) {
          this.emit("decision_quiz_created", { quiz: data.quiz as DecisionQuiz });
        }
        return;
      case "kanban_updated":
        if (isRecord(data)) {
          const kanban = isRecord(data.kanban)
            ? (data.kanban as unknown as KanbanBoard)
            : undefined;
          const tasks = Array.isArray(data.tasks)
            ? (data.tasks as KanbanTask[])
            : kanban?.tasks ?? [];
          this.emit("kanban_updated", { tasks, kanban });
        }
        return;
      case "agent_dispatch_started":
        if (isRecord(data)) {
          this.emit("agent_dispatch_started", {
            role_ids: asStringArray(data.role_ids),
            card_ids: asStringArray(data.card_ids),
          });
        }
        return;
      case "agent_response_received":
        if (isRecord(data)) {
          this.emit("agent_response_received", {
            role_id: asString(data.role_id),
            turn_id: asString(data.turn_id),
            response_text: asString(data.response_text),
            latency_ms: asNumber(data.latency_ms),
          });
        }
        return;
      case "agent_response_error":
        if (isRecord(data)) {
          this.emit("agent_response_error", {
            role_id: asString(data.role_id),
            status: asString(data.status),
            error_message: asString(data.error_message),
          });
        }
        return;
      case "agent_bundle_complete":
        if (isRecord(data)) {
          this.emit("agent_bundle_complete", {
            bundle_id: asString(data.bundle_id),
            responses_count: asNumber(data.responses_count),
            errors_count: asNumber(data.errors_count),
          });
        }
        return;
      case "bundle_ready":
        if (isRecord(data)) {
          this.emit("bundle_ready", {
            bundle_id: asString(data.bundle_id),
            responses: Array.isArray(data.responses) ? (data.responses as BundledResponse[]) : [],
          });
        }
        return;
      case "agent_response":
        if (isRecord(data)) {
          const status = asString(data.status, "OK");
          if (status === "OK") {
            this.emit("agent_response_received", {
              role_id: asString(data.role_id),
              turn_id: asString(data.turn_id),
              response_text: asString(data.response_text),
              latency_ms: asNumber(data.latency_ms),
            });
          } else {
            this.emit("agent_response_error", {
              role_id: asString(data.role_id),
              status,
              error_message: asString(data.error_message, "Agent error"),
            });
          }
        }
        return;
      case "consensus_triggered":
        if (isRecord(data)) {
          this.emit("consensus_triggered", { reason: asString(data.reason) });
        }
        return;
      case "consensus_complete":
        if (isRecord(data)) {
          this.emit("consensus_complete", {
            validation_warnings: Array.isArray(data.validation_warnings)
              ? data.validation_warnings.filter((item): item is string => typeof item === "string")
              : [],
            completed_at: asString(data.completed_at),
          });
        }
        return;
      case "tool_call_dropped":
        if (isRecord(data)) {
          this.emit("tool_call_dropped", {
            tool: asString(data.tool),
            errors: Array.isArray(data.errors)
              ? data.errors.filter((item): item is string => typeof item === "string")
              : [],
          });
        }
        return;
      case "error":
        if (isRecord(data)) {
          this.emit("error", {
            code: asString(data.code),
            message: asString(data.message),
            role_id: typeof data.role_id === "string" ? data.role_id : undefined,
            recoverable: typeof data.recoverable === "boolean" ? data.recoverable : undefined,
            details: Array.isArray(data.details)
              ? data.details.filter((item): item is string => typeof item === "string")
              : undefined,
          });
        }
        return;
      case "state_sync":
        this.emit("state_sync", data as StateSyncData);
        return;
      case "human_message_queued":
        if (isRecord(data)) {
          this.emit("human_message_queued", {
            text: asString(data.text),
            queue_position: asNumber(data.queue_position),
          });
        }
        return;
      case "message_queued":
        if (isRecord(data)) {
          this.emit("human_message_queued", {
            text: asString(data.message),
            queue_position: 0,
          });
        }
        return;
      default:
        return;
    }
  }

  private normalizeOutgoing(event: ClientEvent): { event: string; data: Record<string, unknown> } {
    if (event.event === "human_message") {
      return { event: "chat_message", data: { content: event.data.text } };
    }

    if (event.event === "dispatch_approved") {
      return {
        event: "dispatch_approved",
        data: {
          card_resolutions: event.data?.card_resolutions ?? [],
          quiz_answers: event.data?.quiz_answers ?? [],
        },
      };
    }

    return {
      event: event.event,
      data: (event.data ?? {}) as Record<string, unknown>,
    };
  }

  private scheduleReconnect(): void {
    if (!this.sessionId) {
      return;
    }
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
    this.reconnectAttempts += 1;
    this.clearReconnectTimer();
    this.reconnectTimer = window.setTimeout(() => {
      this.openSocket();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = null;
  }
}
