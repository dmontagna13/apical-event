import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import { useToast } from "./Toast";
import type { SessionListResponse, SessionSummary } from "../types/api";

interface SidebarProps {
  currentPath: string;
  onOpenSettings: () => void;
}

export function Sidebar({ currentPath, onOpenSettings }: SidebarProps): JSX.Element {
  const { pushToast } = useToast();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  useEffect(() => {
    let mounted = true;
    apiFetch<SessionListResponse>("/api/sessions")
      .then((data) => {
        if (mounted) {
          setSessions(data.sessions);
        }
      })
      .catch((error: Error) => {
        pushToast(error.message, "error");
      });
    return () => {
      mounted = false;
    };
  }, [pushToast]);

  const grouped = useMemo(() => {
    const active = sessions.filter((session) =>
      ["ROLL_CALL", "ACTIVE", "CONSENSUS"].includes(session.state)
    );
    const completed = sessions.filter((session) => session.state === "COMPLETED");
    const abandoned = sessions.filter((session) => session.state === "ABANDONED");
    return { active, completed, abandoned };
  }, [sessions]);

  return (
    <aside className="relative z-10 hidden w-64 shrink-0 flex-col border-r border-white/40 bg-white/60 px-5 pb-8 pt-8 backdrop-blur lg:flex">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Apical</p>
          <p className="font-display text-lg text-ink">Event</p>
        </div>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-300"
        >
          Settings
        </button>
      </div>

      <nav className="mt-8 space-y-6 text-sm">
        {[
          { label: "Active", items: grouped.active },
          { label: "Completed", items: grouped.completed },
          { label: "Abandoned", items: grouped.abandoned },
        ].map((group) => (
          <div key={group.label}>
            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">
              {group.label}
            </p>
            <div className="space-y-2">
              {group.items.length === 0 && (
                <p className="text-xs text-slate-500">No sessions</p>
              )}
              {group.items.map((session) => {
                const isActive = currentPath === `/session/${session.session_id}`;
                return (
                  <Link
                    key={session.session_id}
                    to={`/session/${session.session_id}`}
                    className={`block rounded-2xl px-3 py-2 transition ${
                      isActive ? "bg-ink text-white" : "text-slate-700 hover:bg-white"
                    }`}
                  >
                    <p className="text-xs uppercase tracking-[0.2em] opacity-70">
                      {session.project_name}
                    </p>
                    <p className="font-medium">{session.packet_id}</p>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
