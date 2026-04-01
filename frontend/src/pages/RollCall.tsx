import { useNavigate, useParams } from "react-router-dom";

import { RoleCard } from "../components/RoleCard";
import { PresetSelector } from "../components/PresetSelector";
import { useRollCall } from "../hooks/useRollCall";
import { useToast } from "../components/Toast";

export function RollCall(): JSX.Element {
  const { id } = useParams();
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const sessionId = id ?? "";
  const {
    packet,
    roles,
    providers,
    providerOptions,
    assignments,
    expandedRoles,
    connectivity,
    presets,
    loading,
    submitting,
    errors,
    canBegin,
    moderatorWarning,
    setProvider,
    setModel,
    toggleRole,
    loadPreset,
    savePreset,
    beginSession,
  } = useRollCall(sessionId);

  if (loading) {
    return (
      <div className="rounded-3xl bg-white/70 px-8 py-6 shadow-card">Loading roll call...</div>
    );
  }

  if (!packet) {
    return (
      <div className="rounded-3xl bg-white/70 px-8 py-6 shadow-card">
        Unable to load session packet.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="rounded-3xl bg-white/80 p-8 shadow-card">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Roll call</p>
        <h1 className="mt-3 font-display text-3xl text-ink">{packet.packet_id}</h1>
        <p className="mt-2 text-sm text-slate-600">
          {packet.meeting_class} · {packet.objective}
        </p>
        <div className="mt-4">
          <PresetSelector
            presets={presets}
            onLoad={loadPreset}
            onSave={(name) =>
              savePreset(name).then(() => pushToast("Preset saved", "success"))
            }
          />
        </div>
      </header>

      {errors.length > 0 && (
        <div className="rounded-2xl border border-red-100 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-semibold">Please fix the following:</p>
          <ul className="mt-2 list-disc pl-5">
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-6">
        {roles.map((role) => (
          <RoleCard
            key={role.role_id}
            role={role}
            assignment={assignments[role.role_id] ?? { provider: "", model: "" }}
            providerOptions={providerOptions}
            providers={providers}
            expanded={Boolean(expandedRoles[role.role_id])}
            connectivity={connectivity[assignments[role.role_id]?.provider ?? ""]}
            showModeratorWarning={role.is_moderator && Boolean(moderatorWarning)}
            onToggle={() => toggleRole(role.role_id)}
            onProviderChange={(providerKey) => setProvider(role.role_id, providerKey)}
            onModelChange={(model) => setModel(role.role_id, model)}
          />
        ))}
      </div>

      <div className="rounded-3xl bg-white/80 p-6 shadow-card">
        {moderatorWarning && (
          <p className="mb-4 text-sm font-semibold text-red-700">{moderatorWarning}</p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="text-sm text-slate-600">
            All roles need a provider and model before the session can start.
          </p>
          <button
            type="button"
            onClick={async () => {
              const ok = await beginSession();
              if (ok) {
                navigate(`/session/${sessionId}`);
              }
            }}
            disabled={!canBegin || submitting}
            className="inline-flex items-center rounded-full bg-ink px-5 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Starting..." : "Begin Session"}
          </button>
        </div>
      </div>
    </div>
  );
}
