import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../api/client";
import type { Role, SessionPacket } from "../types";
import type {
  Preset,
  PresetsResponse,
  ProviderConfigResponse,
  ProvidersResponse,
  ProviderTestResponse,
  RollCallResponse,
  SessionStateResponse,
} from "../types/api";

interface AssignmentState {
  provider: string;
  model: string;
}

interface ConnectivityState {
  status: "idle" | "testing" | "ok" | "error";
  message?: string;
}

interface UseRollCallResult {
  packet: SessionPacket | null;
  roles: Role[];
  providers: ProvidersResponse["providers"];
  providerOptions: [string, ProviderConfigResponse][];
  assignments: Record<string, AssignmentState>;
  expandedRoles: Record<string, boolean>;
  connectivity: Record<string, ConnectivityState>;
  presets: Preset[];
  loading: boolean;
  submitting: boolean;
  errors: string[];
  canBegin: boolean;
  moderatorWarning: string | null;
  setProvider: (roleId: string, provider: string) => void;
  setModel: (roleId: string, model: string) => void;
  toggleRole: (roleId: string) => void;
  loadPreset: (preset: Preset) => void;
  savePreset: (name: string) => Promise<void>;
  beginSession: () => Promise<boolean>;
  reloadPresets: () => Promise<void>;
}

export function useRollCall(sessionId: string): UseRollCallResult {
  const [packet, setPacket] = useState<SessionPacket | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [providers, setProviders] = useState<ProvidersResponse["providers"]>({});
  const [assignments, setAssignments] = useState<Record<string, AssignmentState>>({});
  const [expandedRoles, setExpandedRoles] = useState<Record<string, boolean>>({});
  const [connectivity, setConnectivity] = useState<Record<string, ConnectivityState>>({});
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const providerOptions = useMemo(() => {
    const entries = Object.entries(providers) as [string, ProviderConfigResponse][];
    return entries.filter(([, provider]) => provider.has_api_key);
  }, [providers]);

  const moderatorWarning = useMemo(() => {
    const moderator = roles.find((role) => role.is_moderator);
    if (!moderator) {
      return null;
    }
    const assignment = assignments[moderator.role_id];
    if (!assignment || !assignment.provider) {
      return null;
    }
    const provider = providers[assignment.provider];
    if (!provider) {
      return null;
    }
    return provider.supports_function_calling
      ? null
      : "Moderator provider must support function calling";
  }, [assignments, providers, roles]);

  const canBegin = useMemo(() => {
    if (!roles.length) {
      return false;
    }
    const allAssigned = roles.every((role) => {
      const assignment = assignments[role.role_id];
      return assignment?.provider && assignment?.model;
    });
    return allAssigned && !moderatorWarning && !submitting;
  }, [assignments, moderatorWarning, roles, submitting]);

  const toggleRole = (roleId: string) => {
    setExpandedRoles((prev) => ({ ...prev, [roleId]: !prev[roleId] }));
  };

  const setProvider = (roleId: string, providerKey: string) => {
    const provider = providers[providerKey];
    const fallbackModel = provider?.default_model ?? provider?.available_models[0] ?? "";
    setAssignments((prev) => ({
      ...prev,
      [roleId]: { provider: providerKey, model: fallbackModel },
    }));
  };

  const setModel = (roleId: string, model: string) => {
    setAssignments((prev) => ({
      ...prev,
      [roleId]: { provider: prev[roleId]?.provider ?? "", model },
    }));
  };

  const loadPreset = (preset: Preset) => {
    setAssignments((prev) => {
      const next = { ...prev };
      preset.assignments.forEach((assignment) => {
        next[assignment.role_id] = {
          provider: assignment.provider,
          model: assignment.model,
        };
      });
      return next;
    });
  };

  const reloadPresets = useCallback(async () => {
    try {
      const data = await apiFetch<PresetsResponse>("/api/config/presets");
      setPresets(data.presets);
    } catch {
      setPresets([]);
    }
  }, []);

  const savePreset = useCallback(
    async (name: string) => {
      const assignmentsList = roles.map((role) => {
        const assignment = assignments[role.role_id];
        return {
          role_id: role.role_id,
          provider: assignment?.provider ?? "",
          model: assignment?.model ?? "",
        };
      });
      await apiFetch("/api/config/presets", {
        method: "POST",
        body: { name, assignments: assignmentsList },
      });
      await reloadPresets();
    },
    [assignments, reloadPresets, roles]
  );

  const testProviders = useCallback(async (providerKeys: string[]) => {
    const results: Record<string, ConnectivityState> = {};
    await Promise.all(
      providerKeys.map(async (key) => {
        try {
          setConnectivity((prev) => ({
            ...prev,
            [key]: { status: "testing" },
          }));
          const response = await apiFetch<ProviderTestResponse>(
            `/api/config/providers/${key}/test`,
            { method: "POST" }
          );
          if (response.ok) {
            results[key] = { status: "ok" };
          } else {
            results[key] = { status: "error", message: response.error ?? "Unavailable" };
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : "Connection failed";
          results[key] = { status: "error", message };
        }
      })
    );
    setConnectivity((prev) => ({ ...prev, ...results }));
    return results;
  }, []);

  const beginSession = useCallback(async () => {
    if (!packet) {
      return false;
    }
    setSubmitting(true);
    setErrors([]);

    try {
      const selectedProviders = Array.from(
        new Set(
          roles
            .map((role) => assignments[role.role_id]?.provider)
            .filter((provider): provider is string => Boolean(provider))
        )
      );

      const connectivityResults = await testProviders(selectedProviders);
      const failures = Object.entries(connectivityResults)
        .filter(([, result]) => result.status === "error")
        .map(([key, result]) => `${key}: ${result.message ?? "Connection failed"}`);

      if (failures.length) {
        setErrors(failures);
        return false;
      }

      const payload = {
        assignments: roles.map((role) => ({
          role_id: role.role_id,
          provider: assignments[role.role_id]?.provider ?? "",
          model: assignments[role.role_id]?.model ?? "",
        })),
      };

      const response = await apiFetch<RollCallResponse>(
        `/api/sessions/${sessionId}/roll-call`,
        {
          method: "POST",
          body: payload,
        }
      );

      if (!response.ok) {
        setErrors(["Roll call submission failed."]);
        return false;
      }

      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start session";
      setErrors([message]);
      return false;
    } finally {
      setSubmitting(false);
    }
  }, [assignments, packet, roles, sessionId, testProviders]);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([
      apiFetch<SessionStateResponse>(`/api/sessions/${sessionId}/state`),
      apiFetch<ProvidersResponse>("/api/config/providers"),
    ])
      .then(([stateResponse, providersResponse]) => {
        if (!mounted) {
          return;
        }
        const nextPacket = stateResponse.packet ?? null;
        setPacket(nextPacket);
        setRoles(nextPacket?.roles ?? []);
        setProviders(providersResponse.providers);
        setAssignments((prev) => {
          if (!nextPacket) {
            return prev;
          }
          const nextAssignments: Record<string, AssignmentState> = { ...prev };
          nextPacket.roles.forEach((role) => {
            if (!nextAssignments[role.role_id]) {
              nextAssignments[role.role_id] = { provider: "", model: "" };
            }
          });
          return nextAssignments;
        });
      })
      .catch((error: Error) => {
        if (mounted) {
          setErrors([error.message]);
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });

    reloadPresets();

    return () => {
      mounted = false;
    };
  }, [reloadPresets, sessionId]);

  return {
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
    reloadPresets,
  };
}
