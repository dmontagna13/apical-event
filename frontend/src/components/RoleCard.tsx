import type { Role } from "../types";
import type { ProviderConfigResponse } from "../types/api";

interface AssignmentState {
  provider: string;
  model: string;
}

interface ConnectivityState {
  status: "idle" | "testing" | "ok" | "error";
  message?: string;
}

interface RoleCardProps {
  role: Role;
  assignment: AssignmentState;
  providerOptions: [string, ProviderConfigResponse][];
  models: string[];
  expanded: boolean;
  connectivity?: ConnectivityState;
  showModeratorWarning: boolean;
  onToggle: () => void;
  onProviderChange: (providerKey: string) => void;
  onModelChange: (model: string) => void;
}

export function RoleCard({
  role,
  assignment,
  providerOptions,
  models,
  expanded,
  connectivity,
  showModeratorWarning,
  onToggle,
  onProviderChange,
  onModelChange,
}: RoleCardProps): JSX.Element {
  const directive = role.behavioral_directive;
  const truncated = directive.length > 200 ? `${directive.slice(0, 200)}…` : directive;

  return (
    <div className="rounded-3xl border border-white/60 bg-white/80 p-6 shadow-card backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-haze px-3 py-1 text-xs font-semibold text-slate-600">
              {role.role_id}
            </span>
            {role.is_moderator && (
              <span className="rounded-full bg-ember/20 px-3 py-1 text-xs font-semibold text-ember">
                Moderator
              </span>
            )}
          </div>
          <h3 className="mt-2 font-display text-xl text-ink">{role.label}</h3>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {connectivity?.status && connectivity.status !== "idle" && (
            <span
              className={`rounded-full px-3 py-1 font-semibold ${
                connectivity.status === "ok"
                  ? "bg-emerald-100 text-emerald-700"
                  : connectivity.status === "testing"
                  ? "bg-slate-100 text-slate-600"
                  : "bg-red-100 text-red-700"
              }`}
            >
              {connectivity.status === "testing"
                ? "Testing"
                : connectivity.status === "ok"
                ? "Connected"
                : "Error"}
            </span>
          )}
        </div>
      </div>

      <div className="mt-4 text-sm text-slate-600">
        <p>{expanded ? directive : truncated}</p>
        {directive.length > 200 && (
          <button
            type="button"
            onClick={onToggle}
            className="mt-2 text-xs font-semibold text-ocean"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="text-sm text-slate-600">
          Provider
          <select
            value={assignment.provider}
            onChange={(event: { target: { value: string } }) =>
              onProviderChange(event.target.value)
            }
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm"
          >
            <option value="">Select provider</option>
            {providerOptions.map(([key, config]) => (
              <option key={key} value={key}>
                {config.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Model
          <select
            value={assignment.model}
            onChange={(event: { target: { value: string } }) =>
              onModelChange(event.target.value)
            }
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm"
            disabled={!assignment.provider}
          >
            <option value="">Select model</option>
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
      </div>

      {showModeratorWarning && (
        <div className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-xs font-semibold text-red-700">
          Selected provider does not support function calling. Choose a different provider.
        </div>
      )}
    </div>
  );
}
