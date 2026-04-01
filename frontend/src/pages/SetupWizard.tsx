import { useMemo, useState } from "react";

import { apiFetch } from "../api/client";
import { useToast } from "../components/Toast";
import type { ProviderConfigResponse, ProvidersResponse } from "../types/api";

interface SetupWizardProps {
  providers: ProvidersResponse["providers"];
  onConfigured: () => void;
}

interface DraftState {
  apiKey: string;
  baseUrl: string;
}

export function SetupWizard({ providers, onConfigured }: SetupWizardProps): JSX.Element {
  const { pushToast } = useToast();
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [testing, setTesting] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const hasConfiguredProvider = useMemo(() => {
    const providerList = Object.values(providers) as ProviderConfigResponse[];
    const configured = providerList.some((provider) => provider.has_api_key);
    const drafted = Object.values(drafts).some((draft) => draft.apiKey.trim().length > 0);
    return configured || drafted;
  }, [providers, drafts]);

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

  const handleContinue = async () => {
    setSaving(true);
    try {
      const entries = Object.entries(providers) as [string, ProviderConfigResponse][];
      await Promise.all(entries.map(([key, provider]) => persistProvider(key, provider)));
      await onConfigured();
      pushToast("Providers saved", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save providers";
      pushToast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen px-6 py-10">
      <div className="mx-auto max-w-4xl">
        <div className="rounded-3xl bg-white/80 p-8 shadow-card backdrop-blur">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">First run</p>
          <h1 className="mt-3 font-display text-3xl text-ink">Connect your providers</h1>
          <p className="mt-2 text-sm text-slate-600">
            Add at least one API key to unlock Apical-Event. You can update these later from
            settings.
          </p>
        </div>

        <div className="mt-8 grid gap-6">
          {(Object.entries(providers) as [string, ProviderConfigResponse][]).map(
            ([key, provider]) => {
              const status = testing[key];
              const draft = drafts[key];
              return (
                <div
                  key={key}
                  className="rounded-3xl border border-white/60 bg-white/70 p-6 shadow-card backdrop-blur"
                >
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <h2 className="font-display text-xl text-ink">{provider.display_name}</h2>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{key}</p>
                    </div>
                    {provider.has_api_key && !draft?.apiKey && (
                      <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                        Configured
                      </span>
                    )}
                  </div>

                  <div className="mt-5 grid gap-4 md:grid-cols-2">
                    <label className="text-sm text-slate-600">
                      API key
                      <input
                        type="password"
                        placeholder={provider.has_api_key ? "Key is set" : "Paste API key"}
                        value={draft?.apiKey ?? ""}
                      onChange={(event: { target: { value: string } }) =>
                        updateDraft(key, { apiKey: event.target.value })
                      }
                        className="mt-2 w-full rounded-2xl border border-slate-200 bg-white/90 px-4 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-ocean"
                      />
                    </label>
                    {(provider.base_url === null || key === "custom") && (
                      <label className="text-sm text-slate-600">
                        Base URL
                        <input
                          type="text"
                          placeholder="https://api.example.com"
                          value={draft?.baseUrl ?? ""}
                        onChange={(event: { target: { value: string } }) =>
                          updateDraft(key, { baseUrl: event.target.value })
                        }
                          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white/90 px-4 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-ocean"
                        />
                      </label>
                    )}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => handleTest(key, provider)}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 transition hover:border-slate-300"
                    >
                      Test connection
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
                </div>
              );
            }
          )}
        </div>

        <div className="mt-8 flex items-center justify-between rounded-3xl bg-white/80 p-6 shadow-card">
          <div>
            <h3 className="font-display text-lg text-ink">Ready to proceed?</h3>
            <p className="text-sm text-slate-600">
              You need at least one configured provider to start a session.
            </p>
          </div>
          <button
            type="button"
            onClick={handleContinue}
            disabled={!hasConfiguredProvider || saving}
            className="inline-flex items-center rounded-full bg-ink px-5 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? "Saving..." : "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
