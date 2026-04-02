import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { apiFetch } from "../api/client";
import { SessionWebSocket, type ChatMessage } from "../api/websocket";
import { useToast } from "../components/Toast";
import { getRoleColor } from "../utils/roleColors";
import type {
  ActionCard,
  ConsensusOutput,
  DecisionQuiz,
  KanbanBoard,
  KanbanTask,
  SessionPacket,
  SessionState,
  SessionSubstate,
} from "../types";
import type { SessionStateResponse } from "../types/api";

interface ChatEntry {
  id: string;
  role: "moderator" | "human" | "agent" | "system";
  content: string;
  roleId?: string;
  queued?: boolean;
}

interface CardDraft {
  prompt: string;
  editedPrompt: string;
  isEditing: boolean;
  action: "PENDING" | "APPROVED" | "MODIFIED" | "DENIED";
  denialReason: string;
  showDenialInput: boolean;
}

interface QuizDraft {
  selectedOption: string;
  freeformText: string;
  submitted: boolean;
}

interface DispatchStatus {
  status: "pending" | "ok" | "error";
  message?: string;
}

const AUTO_SCROLL_THRESHOLD = 80;

export function Workbench(): JSX.Element {
  const { id } = useParams();
  const sessionId = id ?? "";
  const { pushToast } = useToast();
  const [packet, setPacket] = useState<SessionPacket | null>(null);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const [substate, setSubstate] = useState<SessionSubstate | null>(null);
  const [kanban, setKanban] = useState<KanbanBoard | null>(null);
  const [actionCards, setActionCards] = useState<ActionCard[]>([]);
  const [quizzes, setQuizzes] = useState<DecisionQuiz[]>([]);
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [queuedMessages, setQueuedMessages] = useState<ChatEntry[]>([]);
  const [cardDrafts, setCardDrafts] = useState<Record<string, CardDraft>>({});
  const [quizDrafts, setQuizDrafts] = useState<Record<string, QuizDraft>>({});
  const [dispatchStatus, setDispatchStatus] = useState<Record<string, DispatchStatus>>({});
  const [consensus, setConsensus] = useState<ConsensusOutput | null>(null);
  const [consensusUrl, setConsensusUrl] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"actions" | "kanban">("actions");
  const [inputValue, setInputValue] = useState("");
  const [connectionLost, setConnectionLost] = useState(false);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [confirmConsensusOpen, setConfirmConsensusOpen] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const [socket] = useState(() => new SessionWebSocket());
  const actionCardsRef = useRef<ActionCard[]>([]);
  const quizzesRef = useRef<DecisionQuiz[]>([]);

  const normalizeCardAction = useCallback((status: ActionCard["status"]): CardDraft["action"] => {
    if (status === "APPROVED" || status === "MODIFIED" || status === "DENIED" || status === "PENDING") {
      return status;
    }
    return "PENDING";
  }, []);

  const buildCardDraft = useCallback((card: ActionCard): CardDraft => {
    const basePrompt = card.human_modified_prompt ?? card.prompt_text;
    return {
      prompt: basePrompt,
      editedPrompt: basePrompt,
      isEditing: false,
      action: normalizeCardAction(card.status),
      denialReason: card.denial_reason ?? "",
      showDenialInput: false,
    };
  }, [normalizeCardAction]);

  const buildQuizDraft = useCallback((quiz: DecisionQuiz): QuizDraft => {
    return {
      selectedOption: quiz.selected_option ?? "",
      freeformText: quiz.freeform_text ?? "",
      submitted: quiz.resolved,
    };
  }, []);

  const updateCardDraft = useCallback(
    (card: ActionCard, updater: (draft: CardDraft) => CardDraft) => {
      setCardDrafts((prev) => {
        const existing = prev[card.card_id] ?? buildCardDraft(card);
        return {
          ...prev,
          [card.card_id]: updater(existing),
        };
      });
    },
    [buildCardDraft]
  );

  const updateQuizDraft = useCallback(
    (quiz: DecisionQuiz, updater: (draft: QuizDraft) => QuizDraft) => {
      setQuizDrafts((prev) => {
        const existing = prev[quiz.quiz_id] ?? buildQuizDraft(quiz);
        return {
          ...prev,
          [quiz.quiz_id]: updater(existing),
        };
      });
    },
    [buildQuizDraft]
  );

  const isReadOnly =
    sessionState === "COMPLETED" || sessionState === "ABANDONED" || sessionState === "CONSENSUS";

  const unresolvedTasks = useMemo(() => {
    const tasks = kanban?.tasks ?? [];
    return tasks.filter((task) => task.status !== "RESOLVED");
  }, [kanban]);

  const allResolved = unresolvedTasks.length === 0 && (kanban?.tasks?.length ?? 0) > 0;

  const combinedMessages = useMemo(() => {
    return [...messages, ...queuedMessages];
  }, [messages, queuedMessages]);

  useEffect(() => {
    if (!consensus) {
      setConsensusUrl(null);
      return;
    }
    const blob = new Blob([JSON.stringify(consensus, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    setConsensusUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [consensus]);

  const syncCards = useCallback(
    (cards: ActionCard[]) => {
      setActionCards(cards);
      setCardDrafts((prev) => {
        const next = { ...prev };
        cards.forEach((card) => {
          const existing = next[card.card_id];
          const nextAction = normalizeCardAction(card.status);
          if (!existing) {
            next[card.card_id] = buildCardDraft(card);
            return;
          }
          if (existing.action !== nextAction) {
            next[card.card_id] = { ...existing, action: nextAction };
          }
        });
        return next;
      });
    },
    [buildCardDraft, normalizeCardAction]
  );

  const syncQuizzes = useCallback(
    (items: DecisionQuiz[]) => {
      setQuizzes(items);
      setQuizDrafts((prev) => {
        const next = { ...prev };
        items.forEach((quiz) => {
          const existing = next[quiz.quiz_id];
          if (!existing) {
            next[quiz.quiz_id] = buildQuizDraft(quiz);
            return;
          }
          const selectedOption = quiz.selected_option ?? existing.selectedOption;
          const freeformText = quiz.freeform_text ?? existing.freeformText;
          const submitted = existing.submitted || quiz.resolved;
          if (
            selectedOption !== existing.selectedOption ||
            freeformText !== existing.freeformText ||
            submitted !== existing.submitted
          ) {
            next[quiz.quiz_id] = {
              ...existing,
              selectedOption,
              freeformText,
              submitted,
            };
          }
        });
        return next;
      });
    },
    [buildQuizDraft]
  );

  const buildMessagesFromHistory = useCallback((history: ChatMessage[]): ChatEntry[] => {
    return history.map((item, index) => {
      const role =
        item.role === "moderator" ? "moderator" : item.role === "human" ? "human" : "system";
      return {
        id: `history-${index}-${item.role}`,
        role,
        content: item.content,
      };
    });
  }, []);

  const appendMessage = useCallback((entry: ChatEntry) => {
    setMessages((prev) => [...prev, entry]);
  }, []);

  const mergeMessages = useCallback((nextMessages: ChatEntry[]) => {
    setMessages((prev) => {
      if (prev.length === 0) {
        return nextMessages;
      }
      const prevCounts = new Map<string, number>();
      prev.forEach((msg) => {
        const key = `${msg.role}|${msg.roleId ?? ""}|${msg.content}`;
        prevCounts.set(key, (prevCounts.get(key) ?? 0) + 1);
      });
      const seenCounts = new Map<string, number>();
      const merged = [...prev];
      nextMessages.forEach((msg) => {
        const key = `${msg.role}|${msg.roleId ?? ""}|${msg.content}`;
        const prevCount = prevCounts.get(key) ?? 0;
        const seen = seenCounts.get(key) ?? 0;
        if (seen < prevCount) {
          seenCounts.set(key, seen + 1);
          return;
        }
        seenCounts.set(key, seen + 1);
        merged.push(msg);
      });
      return merged;
    });
  }, []);

  const resetQueuedIfNeeded = useCallback((nextSubstate: SessionSubstate | null) => {
    if (nextSubstate !== "AGENT_DISPATCH" && nextSubstate !== "AGENT_AGGREGATION") {
      setQueuedMessages([]);
    }
  }, []);

  useEffect(() => {
    actionCardsRef.current = actionCards;
  }, [actionCards]);

  useEffect(() => {
    quizzesRef.current = quizzes;
  }, [quizzes]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    apiFetch<SessionStateResponse>(`/api/sessions/${sessionId}/state`)
      .then((data) => {
        setPacket(data.packet ?? null);
        setSessionState(data.state ?? null);
        setSubstate(data.substate ?? null);
        setKanban(data.kanban ?? null);
        setConsensus(data.consensus ?? null);
        if (data.pending_action_cards) {
          syncCards(data.pending_action_cards);
        }
        if (data.pending_quizzes) {
          syncQuizzes(data.pending_quizzes);
        }
        if (data.chat_history) {
          mergeMessages(buildMessagesFromHistory(data.chat_history));
        }
      })
      .catch((error: Error) => pushToast(error.message, "error"));
  }, [buildMessagesFromHistory, mergeMessages, pushToast, sessionId, syncCards, syncQuizzes]);

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    const handleStateSync = (data: {
      chat_history: ChatMessage[];
      kanban: KanbanBoard | null;
      pending_actions: ActionCard[];
      pending_quizzes: DecisionQuiz[];
      session_state: SessionState;
      substate: SessionSubstate | null;
      bundles?: { bundle_id: string; responses: { role_id: string; response_text: string; status: string; error_message?: string | null }[] }[];
    }) => {
      setSessionState(data.session_state);
      setSubstate(data.substate);
      setKanban(data.kanban ?? null);
      syncCards(data.pending_actions ?? []);
      syncQuizzes(data.pending_quizzes ?? []);
      const baseMessages = buildMessagesFromHistory(data.chat_history ?? []);
      const bundleMessages: ChatEntry[] = [];
      (data.bundles ?? []).forEach((bundle, bundleIndex) => {
        bundle.responses.forEach((response, responseIndex) => {
          const content = response.status === "OK"
            ? response.response_text
            : response.error_message || "Agent response unavailable";
          bundleMessages.push({
            id: `bundle-${bundleIndex}-${responseIndex}-${response.role_id}`,
            role: "agent",
            roleId: response.role_id,
            content,
          });
        });
      });
      mergeMessages([...baseMessages, ...bundleMessages]);
      resetQueuedIfNeeded(data.substate);
    };

    const handleModerator = (data: { text: string }) => {
      appendMessage({ id: `${Date.now()}-mod`, role: "moderator", content: data.text });
    };

    const handleAgentResponse = (data: { role_id: string; response_text: string }) => {
      appendMessage({
        id: `${Date.now()}-agent-${data.role_id}`,
        role: "agent",
        roleId: data.role_id,
        content: data.response_text,
      });
      setDispatchStatus((prev) => ({
        ...prev,
        [data.role_id]: { status: "ok" },
      }));
    };

    const handleAgentError = (data: { role_id: string; error_message: string }) => {
      appendMessage({
        id: `${Date.now()}-agent-${data.role_id}-error`,
        role: "system",
        content: `${data.role_id} failed: ${data.error_message}`,
      });
      setDispatchStatus((prev) => ({
        ...prev,
        [data.role_id]: { status: "error", message: data.error_message },
      }));
    };

    const handleBundleReady = (data: { bundle_id: string }) => {
      appendMessage({
        id: `${Date.now()}-bundle-${data.bundle_id}`,
        role: "system",
        content: `Bundle ${data.bundle_id} complete.`,
      });
      setDispatchStatus({});
      setQueuedMessages([]);
    };

    const handleDecisionQuiz = (data: { quiz: DecisionQuiz }) => {
      const next = [...(quizzesRef.current ?? []), data.quiz];
      const unique = new Map(next.map((item) => [item.quiz_id, item]));
      syncQuizzes(Array.from(unique.values()));
    };

    const handleActionCards = (data: { cards: ActionCard[] }) => {
      const next = [...(actionCardsRef.current ?? []), ...data.cards];
      const unique = new Map(next.map((item) => [item.card_id, item]));
      syncCards(Array.from(unique.values()));
    };

    const handleKanban = (data: { kanban?: KanbanBoard; tasks: KanbanTask[] }) => {
      if (data.kanban) {
        setKanban(data.kanban);
      } else {
        setKanban((prev) => ({ tasks: data.tasks ?? prev?.tasks ?? [] }));
      }
    };

    const handleConsensusComplete = (data: { completed_at: string }) => {
      appendMessage({
        id: `${Date.now()}-consensus`,
        role: "system",
        content: `Consensus completed at ${data.completed_at}.`,
      });
      apiFetch<SessionStateResponse>(`/api/sessions/${sessionId}/state`)
        .then((state) => {
          setConsensus(state.consensus ?? null);
          setSessionState(state.state ?? null);
          setSubstate(state.substate ?? null);
        })
        .catch(() => undefined);
    };

    const handleConsensusTriggered = () => {
      appendMessage({
        id: `${Date.now()}-consensus-trigger`,
        role: "system",
        content: "Consensus capture triggered.",
      });
    };

    const handleQueued = (data: { text: string }) => {
      pushToast(data.text, "info");
    };

    const handleConnectionLost = () => setConnectionLost(true);
    const handleConnectionRestored = () => setConnectionLost(false);

    socket.on("state_sync", handleStateSync);
    socket.on("moderator_text", handleModerator);
    socket.on("action_cards_created", handleActionCards);
    socket.on("decision_quiz_created", handleDecisionQuiz);
    socket.on("kanban_updated", handleKanban);
    socket.on("agent_response_received", handleAgentResponse);
    socket.on("agent_response_error", handleAgentError);
    socket.on("bundle_ready", handleBundleReady);
    socket.on("consensus_complete", handleConsensusComplete);
    socket.on("consensus_triggered", handleConsensusTriggered);
    socket.on("human_message_queued", handleQueued);
    socket.on("connection_lost", handleConnectionLost);
    socket.on("connection_restored", handleConnectionRestored);

    socket.connect(sessionId);

    return () => {
      socket.off("state_sync", handleStateSync);
      socket.off("moderator_text", handleModerator);
      socket.off("action_cards_created", handleActionCards);
      socket.off("decision_quiz_created", handleDecisionQuiz);
      socket.off("kanban_updated", handleKanban);
      socket.off("agent_response_received", handleAgentResponse);
      socket.off("agent_response_error", handleAgentError);
      socket.off("bundle_ready", handleBundleReady);
      socket.off("consensus_complete", handleConsensusComplete);
      socket.off("consensus_triggered", handleConsensusTriggered);
      socket.off("human_message_queued", handleQueued);
      socket.off("connection_lost", handleConnectionLost);
      socket.off("connection_restored", handleConnectionRestored);
      socket.disconnect();
    };
  }, [
    appendMessage,
    buildMessagesFromHistory,
    mergeMessages,
    pushToast,
    resetQueuedIfNeeded,
    sessionId,
    socket,
    syncCards,
    syncQuizzes,
  ]);

  useEffect(() => {
    if (!autoScrollEnabled) {
      return;
    }
    const node = chatContainerRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [autoScrollEnabled, combinedMessages]);

  const handleScroll = () => {
    const node = chatContainerRef.current;
    if (!node) {
      return;
    }
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    setAutoScrollEnabled(distance < AUTO_SCROLL_THRESHOLD);
  };

  const handleSend = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) {
      return;
    }

    const dispatching = substate === "AGENT_DISPATCH" || substate === "AGENT_AGGREGATION";

    if (dispatching) {
      setQueuedMessages((prev) => [
        ...prev,
        { id: `${Date.now()}-queued-${prev.length}`, role: "human", content: trimmed, queued: true },
      ]);
      socket.send({ event: "human_message", data: { text: trimmed } });
    } else {
      appendMessage({ id: `${Date.now()}-human`, role: "human", content: trimmed });
      socket.send({ event: "human_message", data: { text: trimmed } });
    }

    setInputValue("");
  };

  const approvedCount = useMemo(() => {
    return Object.values(cardDrafts).filter(
      (draft) => draft.action === "APPROVED" || draft.action === "MODIFIED"
    ).length;
  }, [cardDrafts]);

  const handleSendApproved = () => {
    if (approvedCount === 0) {
      return;
    }

    const resolutions = actionCards
      .map((card) => {
        const draft = cardDrafts[card.card_id];
        if (!draft || draft.action === "PENDING") {
          return null;
        }
        const resolution = {
          card_id: card.card_id,
          action: draft.action,
          modified_prompt: draft.action === "MODIFIED" ? draft.editedPrompt : null,
          denial_reason: draft.action === "DENIED" ? draft.denialReason : null,
        };
        return resolution;
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);

    const quizAnswers = quizzes
      .map((quiz) => {
        const draft = quizDrafts[quiz.quiz_id];
        if (!draft?.submitted && !quiz.resolved) {
          return null;
        }
        return {
          quiz_id: quiz.quiz_id,
          selected_option: draft?.selectedOption ?? quiz.selected_option ?? null,
          freeform_text: draft?.freeformText ?? quiz.freeform_text ?? null,
        };
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);

    const pendingRoles = actionCards
      .filter((card) => {
        const draft = cardDrafts[card.card_id];
        return draft?.action === "APPROVED" || draft?.action === "MODIFIED";
      })
      .map((card) => card.target_role_id);

    setDispatchStatus(
      pendingRoles.reduce<Record<string, DispatchStatus>>((acc, roleId) => {
        acc[roleId] = { status: "pending" };
        return acc;
      }, {})
    );

    socket.send({
      event: "dispatch_approved",
      data: { card_resolutions: resolutions, quiz_answers: quizAnswers },
    });
  };

  if (!packet) {
    return (
      <div className="rounded-3xl bg-white/70 px-8 py-6 shadow-card">Loading workbench...</div>
    );
  }

  return (
    <div className="space-y-6">
      {connectionLost && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700">
          Connection lost - reconnecting...
        </div>
      )}

      <header className="rounded-3xl bg-white/80 p-6 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Workbench</p>
            <h1 className="mt-2 font-display text-2xl text-ink">{packet.packet_id}</h1>
            <p className="mt-1 text-sm text-slate-600">
              {packet.meeting_class} - {packet.objective}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-haze px-3 py-1 text-xs font-semibold text-slate-600">
              {sessionState ?? ""}
            </span>
            {allResolved && !isReadOnly && (
              <button
                type="button"
                onClick={() => setConfirmConsensusOpen(true)}
                className="rounded-full bg-emerald-600 px-4 py-2 text-xs font-semibold text-white"
              >
                Trigger Consensus
              </button>
            )}
            {!allResolved && !isReadOnly && (
              <button
                type="button"
                onClick={() => setConfirmConsensusOpen(true)}
                className="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600"
              >
                Force Consensus
              </button>
            )}
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <section className="rounded-3xl bg-white/80 p-6 shadow-card">
          <div
            ref={chatContainerRef}
            onScroll={handleScroll}
            className="h-[60vh] overflow-y-auto pr-2"
          >
            <div className="space-y-4">
              {combinedMessages.map((message) => {
                const isHuman = message.role === "human";
                const isModerator = message.role === "moderator";
                const isSystem = message.role === "system";
                const roleColor = message.roleId ? getRoleColor(message.roleId) : null;
                return (
                  <div
                    key={message.id}
                    className={`flex ${isHuman ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                        isHuman
                          ? "bg-ink text-white"
                          : isModerator
                          ? "bg-ocean/10 text-ink"
                          : isSystem
                          ? "bg-slate-100 text-slate-600"
                          : roleColor
                          ? `${roleColor.bg} ${roleColor.text}`
                          : "bg-slate-200 text-slate-700"
                      }`}
                    >
                      {message.roleId && (
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.2em]">
                          {message.roleId}
                        </p>
                      )}
                      <p className="whitespace-pre-wrap">{message.content}</p>
                      {message.queued && (
                        <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
                          <span>[queued]</span>
                          <span>Will be delivered after agents respond</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {!isReadOnly && (
            <div className="mt-4 flex items-center gap-3">
              <input
                value={inputValue}
                onChange={(event: { target: { value: string } }) =>
                  setInputValue(event.target.value)
                }
                placeholder="Message the moderator..."
                className="flex-1 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm"
              />
              <button
                type="button"
                onClick={handleSend}
                className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white"
              >
                Send
              </button>
            </div>
          )}
        </section>

        <aside className="rounded-3xl bg-white/80 p-6 shadow-card">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("actions")}
              className={`rounded-full px-4 py-1 text-xs font-semibold ${
                activeTab === "actions"
                  ? "bg-ink text-white"
                  : "border border-slate-200 text-slate-600"
              }`}
            >
              Action Area
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("kanban")}
              className={`rounded-full px-4 py-1 text-xs font-semibold ${
                activeTab === "kanban"
                  ? "bg-ink text-white"
                  : "border border-slate-200 text-slate-600"
              }`}
            >
              Kanban
            </button>
          </div>

          {activeTab === "actions" && (
            <div className="mt-4 space-y-4">
              {isReadOnly && consensus && (
                <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  <p className="font-semibold">Consensus output</p>
                  <p className="mt-2 text-xs text-emerald-700/80">
                    Completed at: {consensus.completed_at}
                  </p>
                  <p className="mt-1 text-xs text-emerald-700/80">
                    Sections: {Object.keys(consensus.sections ?? {}).length}
                  </p>
                  {consensus.validation_warnings && consensus.validation_warnings.length > 0 && (
                    <p className="mt-1 text-xs text-amber-700/90">
                      Warnings: {consensus.validation_warnings.length}
                    </p>
                  )}
                  {consensusUrl && (
                    <a
                      href={consensusUrl}
                      download={`consensus-${packet.packet_id}.json`}
                      className="mt-3 inline-flex items-center rounded-full border border-emerald-200 px-3 py-1 text-xs font-semibold text-emerald-700"
                    >
                      Download JSON
                    </a>
                  )}
                </div>
              )}

              {(substate === "AGENT_DISPATCH" ||
                substate === "AGENT_AGGREGATION" ||
                Object.keys(dispatchStatus).length > 0) && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-sm font-semibold text-slate-700">Agents responding...</p>
                  <div className="mt-2 space-y-2">
                    {Object.entries(dispatchStatus).map(([roleId, status]) => {
                      const color = getRoleColor(roleId);
                      return (
                        <div
                          key={roleId}
                          className="flex items-center justify-between rounded-xl bg-white px-3 py-2 text-xs"
                        >
                          <span className={`rounded-full border px-2 py-1 ${color.border} ${color.text}`}>
                            {roleId}
                          </span>
                          {status.status === "pending" && <span className="spinner" />}
                          {status.status === "ok" && <span className="text-emerald-600">OK</span>}
                          {status.status === "error" && <span className="text-red-600">ERR</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {actionCards.length === 0 && quizzes.length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-6 text-center text-sm text-slate-500">
                  Waiting for Moderator...
                </div>
              )}

              {actionCards.map((card) => {
                const draft = cardDrafts[card.card_id] ?? buildCardDraft(card);
                const serverAction = normalizeCardAction(card.status);
                const resolved = draft.action !== "PENDING" || serverAction !== "PENDING";
                const readOnly = isReadOnly || resolved;
                const roleColor = getRoleColor(card.target_role_id);
                return (
                  <div key={card.card_id} className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-center justify-between">
                      <span
                        className={`rounded-full border px-3 py-1 text-xs font-semibold ${roleColor.border} ${roleColor.text}`}
                      >
                        {card.target_role_id}
                      </span>
                      {draft.action !== "PENDING" && (
                        <span className="text-xs font-semibold text-slate-500">{draft.action}</span>
                      )}
                    </div>
                    <p className="mt-2 text-xs text-slate-500">{card.context_note}</p>
                    <textarea
                      value={draft.editedPrompt}
                      readOnly={!draft.isEditing || readOnly}
                      onChange={(event: { target: { value: string } }) => {
                        const value = event.target.value;
                        updateCardDraft(card, (current) => ({
                          ...current,
                          editedPrompt: value,
                        }));
                      }}
                      className="mt-3 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
                      rows={4}
                    />

                    {draft.showDenialInput && !readOnly && (
                      <input
                        value={draft.denialReason}
                        onChange={(event: { target: { value: string } }) => {
                          const value = event.target.value;
                          updateCardDraft(card, (current) => ({
                            ...current,
                            denialReason: value,
                          }));
                        }}
                        placeholder="Reason for denial"
                        className="mt-3 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                      />
                    )}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          if (readOnly) {
                            return;
                          }
                          updateCardDraft(card, (current) => {
                            const edited = current.editedPrompt;
                            const action =
                              current.isEditing && edited !== card.prompt_text ? "MODIFIED" : "APPROVED";
                            return {
                              ...current,
                              action,
                              isEditing: false,
                              showDenialInput: false,
                            };
                          });
                        }}
                        className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-semibold text-white"
                        disabled={readOnly}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (readOnly) {
                            return;
                          }
                          updateCardDraft(card, (current) => ({
                            ...current,
                            isEditing: !current.isEditing,
                          }));
                        }}
                        className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600"
                        disabled={readOnly}
                      >
                        {draft.isEditing ? "Editing" : "Edit & Approve"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (readOnly) {
                            return;
                          }
                          if (!draft.denialReason.trim()) {
                            updateCardDraft(card, (current) => ({
                              ...current,
                              showDenialInput: true,
                            }));
                            return;
                          }
                          updateCardDraft(card, (current) => ({
                            ...current,
                            action: "DENIED",
                            isEditing: false,
                            showDenialInput: false,
                          }));
                        }}
                        className="rounded-full border border-red-200 px-3 py-1 text-xs font-semibold text-red-600"
                        disabled={readOnly}
                      >
                        Deny
                      </button>
                    </div>
                  </div>
                );
              })}

              {quizzes.map((quiz) => {
                const draft = quizDrafts[quiz.quiz_id] ?? buildQuizDraft(quiz);
                const resolved = draft.submitted || quiz.resolved;
                return (
                  <div key={quiz.quiz_id} className="rounded-2xl border border-slate-200 bg-white p-4">
                    <h3 className="text-sm font-semibold text-ink">{quiz.decision_title}</h3>
                    <p className="mt-1 text-xs text-slate-500">{quiz.context_summary}</p>
                    <div className="mt-3 space-y-2 text-sm">
                      {quiz.options.map((option) => (
                        <label key={option} className="flex items-center gap-2">
                          <input
                            type="radio"
                            checked={draft.selectedOption === option}
                            onChange={() => {
                              updateQuizDraft(quiz, (current) => ({
                                ...current,
                                selectedOption: option,
                              }));
                            }}
                            disabled={isReadOnly || resolved}
                          />
                          <span>{option}</span>
                        </label>
                      ))}
                    </div>
                    {quiz.allow_freeform && (
                      <textarea
                        value={draft.freeformText}
                        onChange={(event: { target: { value: string } }) => {
                          updateQuizDraft(quiz, (current) => ({
                            ...current,
                            freeformText: event.target.value,
                          }));
                        }}
                        placeholder="Optional notes"
                        className="mt-3 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
                        rows={3}
                        disabled={isReadOnly || resolved}
                      />
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        updateQuizDraft(quiz, (current) => ({
                          ...current,
                          submitted: true,
                        }));
                      }}
                      className="mt-3 rounded-full bg-ink px-3 py-1 text-xs font-semibold text-white"
                      disabled={isReadOnly || resolved}
                    >
                      Submit
                    </button>
                  </div>
                );
              })}

              {!isReadOnly && (
                <button
                  type="button"
                  onClick={handleSendApproved}
                  disabled={approvedCount === 0}
                  className="w-full rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Send Approved ({approvedCount})
                </button>
              )}
            </div>
          )}

          {activeTab === "kanban" && (
            <div className="mt-4 grid gap-4">
              {["TO_DISCUSS", "AGENT_DELIBERATION", "PENDING_HUMAN_DECISION", "RESOLVED"].map(
                (status) => (
                  <div key={status}>
                    <h3 className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                      {status.replace(/_/g, " ")}
                    </h3>
                    <div className="mt-2 space-y-2">
                      {(kanban?.tasks ?? [])
                        .filter((task) => task.status === status)
                        .map((task) => (
                          <div
                            key={task.task_id}
                            className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm transition-all"
                          >
                            <p className="font-semibold text-slate-700">{task.title}</p>
                            {task.notes && (
                              <p className="mt-1 text-xs text-slate-500">{task.notes}</p>
                            )}
                          </div>
                        ))}
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </aside>
      </div>

      {confirmConsensusOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30">
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-card">
            <h2 className="font-display text-xl text-ink">Trigger consensus?</h2>
            {unresolvedTasks.length > 0 ? (
              <div className="mt-3 text-sm text-slate-600">
                <p>Unresolved tasks:</p>
                <ul className="mt-2 list-disc pl-5">
                  {unresolvedTasks.map((task) => (
                    <li key={task.task_id}>{task.title}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-600">All tasks are resolved.</p>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmConsensusOpen(false)}
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  socket.send({ event: "trigger_consensus", data: {} });
                  setConfirmConsensusOpen(false);
                }}
                className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white"
              >
                Trigger
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
