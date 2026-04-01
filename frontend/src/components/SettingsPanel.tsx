import { useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import { useToast } from "./Toast";
import type {
  ProviderConfigResponse,
  ProviderModelsResponse,
  ProvidersResponse,
} from "../types/api";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  providers: ProvidersResponse["providers"];
  onUpdated: () => void;
}

interface DraftState {
  apiKey: string;
  baseUrl: string;
}

export function SettingsPanel({
  open,
  onClose,
  providers,
  onUpdated,
}: SettingsPanelProps): JSX.Element {
  const { pushToast } = useToast();
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<Record<string, string>>({});
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (open) {
      onUpdated();
    }
  }, [onUpdated, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    const entries = Object.entries(providers) as [string, ProviderConfigResponse][];
    Promise.all(
      entries.map(async ([key, provider]) => {
        const fallback = provider.available_models ?? [];
        try {
          const response = await apiFetch<ProviderModelsResponse>(
            `/api/config/providers/${key}/models`
          );
          const models = response.models.length ? response.models : fallback;
          if (!cancelled) {
            setModelsByProvider((prev) => ({ ...prev, [key]: models }));
          }
        } catch {
          if (!cancelled) {
            setModelsByProvider((prev) => ({ ...prev, [key]: fallback }));
          }
        }
      })
    ).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open, providers]);

  const updateDraft = (key: string, next: Partial<DraftState>) => {
    setDrafts((prev) => ({
      ...prev,
      [key]: {
        apiKey: prev[key]?.apiKey ?? "",
        baseUrl: prev[key]?.baseUrl ?? "",
        ...next,
      },
    }));
  };

  const persistProvider = async (key: string, provider: ProviderConfigResponse) => {
    const draft = drafts[key];
    const apiKey = draft?.apiKey.trim() ? draft.apiKey.trim() : provider.api_key ?? null;
    const baseUrl = draft?.baseUrl.trim() ? draft.baseUrl.trim() : provider.base_url ?? null;
    const { has_api_key: _hasApiKey, ...payload } = provider;
    await apiFetch(`/api/config/providers/${key}`, {
      method: "PUT",
      body: { ...payload, api_key: apiKey, base_url: baseUrl },
    });
  };

  const handleTest = async (key: string, provider: ProviderConfigResponse) => {
    try {
      setTesting((prev) => ({ ...prev, [key]: "testing" }));
      await persistProvider(key, provider);
      const result = await apiFetch<{ ok: boolean; error?: string }>(
        `/api/config/providers/${key}/test`,
        { method: "POST" }
      );
      if (result.ok) {
        setTesting((prev) => ({ ...prev, [key]: "success" }));
      } else {
        setTesting((prev) => ({ ...prev, [key]: result.error ?? "error" }));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to test provider";
      setTesting((prev) => ({ ...prev, [key]: "error" }));
      pushToast(message, "error");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const entries = Object.entries(providers) as [string, ProviderConfigResponse][];
      await Promise.all(entries.map(([key, provider]) => persistProvider(key, provider)));
      await onUpdated();
      pushToast("Settings saved", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save settings";
      pushToast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className={`fixed inset-0 z-40 transition ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
    >
      <div
        className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm"
        onClick={onClose}
        role="presentation"
      />
      <div
        className={`absolute right-0 top-0 h-full w-full max-w-lg transform bg-white/90 p-6 shadow-2xl transition ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Settings</p>
            <h2 className="font-display text-2xl text-ink">Provider configuration</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600"
          >
            Close
          </button>
        </div>

        <div className="mt-6 space-y-5 overflow-y-auto pr-2">
          {(Object.entries(providers) as [string, ProviderConfigResponse][]).map(
            ([key, provider]) => {
              const status = testing[key];
              const draft = drafts[key];
              const models = modelsByProvider[key] ?? provider.available_models ?? [];
              return (
                <div key={key} className="rounded-2xl border border-slate-100 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{key}</p>
                      <h3 className="font-display text-lg text-ink">{provider.display_name}</h3>
                    </div>
                    {provider.has_api_key && !draft?.apiKey && (
                      <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                        Configured
                      </span>
                    )}
                  </div>

                  <div className="mt-4 space-y-3 text-sm text-slate-600">
                    <label className="block">
                      API key
                      <input
                        type="password"
                        placeholder={provider.has_api_key ? "Key is set" : "Paste API key"}
                        value={draft?.apiKey ?? ""}
                        onChange={(event: { target: { value: string } }) =>
                          updateDraft(key, { apiKey: event.target.value })
                        }
                        className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                      />
                    </label>
                    {(provider.base_url === null || key === "custom") && (
                      <label className="block">
                        Base URL
                        <input
                          type="text"
                          placeholder="https://api.example.com"
                          value={draft?.baseUrl ?? ""}
                          onChange={(event: { target: { value: string } }) =>
                            updateDraft(key, { baseUrl: event.target.value })
                          }
                          className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                        />
                      </label>
                    )}
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleTest(key, provider)}
                      className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600"
                    >
                      Test
                    </button>
                    {status === "testing" && (
                      <span className="text-xs text-slate-500">Testing...</span>
                    )}
                    {status === "success" && (
                      <span className="text-xs font-semibold text-emerald-600">Connected</span>
                    )}
                    {status && status !== "testing" && status !== "success" && (
                      <span className="text-xs font-semibold text-red-600">{status}</span>
                    )}
                  </div>

                  {models.length > 0 && (
                    <div className="mt-3 text-xs text-slate-500">
                      <p className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                        Models
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {models.map((model) => (
                          <span
                            key={model}
                            className="rounded-full border border-slate-200 px-2 py-1 text-[11px]"
                          >
                            {model}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            }
          )}
        </div>

        <div className="mt-6 border-t border-slate-200 pt-4">
          <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
            Preset management is available on the roll call screen for now.
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="mt-4 w-full rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
