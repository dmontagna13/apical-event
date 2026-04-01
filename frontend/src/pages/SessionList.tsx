import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../api/client";
import { useToast } from "../components/Toast";
import type { SessionListResponse, SessionSummary } from "../types/api";

export function SessionList(): JSX.Element {
  const { pushToast } = useToast();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    apiFetch<SessionListResponse>("/api/sessions")
      .then((data) => {
        if (mounted) {
          setSessions(data.sessions);
        }
      })
      .catch((error: Error) => {
        pushToast(error.message, "error");
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
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
    const other = sessions.filter(
      (session) => !["ROLL_CALL", "ACTIVE", "CONSENSUS", "COMPLETED", "ABANDONED"].includes(session.state)
    );
    return { active, completed, abandoned, other };
  }, [sessions]);

  if (loading) {
    return (
      <div className="rounded-3xl bg-white/70 px-8 py-6 shadow-card">Loading sessions...</div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="rounded-3xl bg-white/80 p-8 shadow-card">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Apical-Event</p>
        <h1 className="mt-3 font-display text-3xl text-ink">Session list</h1>
        <p className="mt-2 text-sm text-slate-600">
          Select a session to continue, or share a packet to initialize a new one.
        </p>
      </header>

      {sessions.length === 0 && (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white/60 p-10 text-center">
          <p className="text-sm text-slate-500">No sessions yet.</p>
        </div>
      )}

      {[
        { label: "Active", items: grouped.active },
        { label: "Completed", items: grouped.completed },
        { label: "Abandoned", items: grouped.abandoned },
        { label: "Other", items: grouped.other },
      ].map((group) =>
        group.items.length ? (
          <section key={group.label} className="space-y-4">
            <h2 className="text-xs uppercase tracking-[0.3em] text-slate-500">{group.label}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              {group.items.map((session) => (
                <Link
                  key={session.session_id}
                  to={`/session/${session.session_id}`}
                  className="rounded-3xl bg-white/80 p-5 shadow-card transition hover:-translate-y-1"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">
                        {session.project_name}
                      </p>
                      <h3 className="mt-2 font-display text-lg text-ink">
                        {session.packet_id}
                      </h3>
                    </div>
                    <span className="rounded-full bg-haze px-3 py-1 text-xs font-semibold text-slate-600">
                      {session.state}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        ) : null
      )}
    </div>
  );
}
