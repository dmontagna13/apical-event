import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  Link,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";

import { apiFetch } from "./api/client";
import { useToast } from "./components/Toast";
import { SettingsPanel } from "./components/SettingsPanel";
import { Sidebar } from "./components/Sidebar";
import { RollCall } from "./pages/RollCall";
import { SetupWizard } from "./pages/SetupWizard";
import { SessionList } from "./pages/SessionList";
import { Workbench } from "./pages/Workbench";
import type { ProviderConfigResponse, ProvidersResponse, SessionMetadataResponse } from "./types/api";

function LoadingScreen({ message }: { message: string }): JSX.Element {
  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="rounded-3xl bg-white/80 shadow-card px-8 py-6 text-center">
        <div className="mx-auto mb-4 h-10 w-10 rounded-full bg-mist/60" />
        <p className="text-sm text-slate-600">{message}</p>
      </div>
    </div>
  );
}

function SessionRouter(): JSX.Element {
  const { id } = useParams();
  const { pushToast } = useToast();
  const location = useLocation();
  const [session, setSession] = useState<SessionMetadataResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) {
      return;
    }
    let mounted = true;
    setLoading(true);
    apiFetch<SessionMetadataResponse>(`/api/sessions/${id}`)
      .then((data) => {
        if (mounted) {
          setSession(data);
        }
      })
      .catch((error: Error) => {
        pushToast(error.message, "error");
        if (mounted) {
          setSession(null);
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [id, location.key, pushToast]);

  if (loading) {
    return <LoadingScreen message="Loading session..." />;
  }

  if (!session) {
    return (
      <div className="p-10">
        <h1 className="font-display text-2xl text-ink">Session not found</h1>
        <p className="mt-3 text-sm text-slate-600">
          We couldn’t find that session. Return to the session list to try another.
        </p>
        <Link
          to="/"
          className="mt-6 inline-flex items-center rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white"
        >
          Back to sessions
        </Link>
      </div>
    );
  }

  if (session.state === "ROLL_CALL") {
    return <RollCall />;
  }

  if (session.state === "ACTIVE" || session.state === "CONSENSUS") {
    return <Workbench />;
  }

  if (session.state === "COMPLETED" || session.state === "ABANDONED") {
    return <Workbench />;
  }

  return (
    <div className="p-10">
      <h1 className="font-display text-2xl text-ink">Session status</h1>
      <p className="mt-3 text-sm text-slate-600">
        Current state: {session.state}
      </p>
    </div>
  );
}

function Shell(): JSX.Element {
  const { pushToast } = useToast();
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const location = useLocation();

  const refreshProviders = useCallback(async () => {
    try {
      setLoadingProviders(true);
      const data = await apiFetch<ProvidersResponse>("/api/config/providers");
      setProviders(data);
      setProviderError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load providers";
      setProviderError(message);
      pushToast(message, "error");
    } finally {
      setLoadingProviders(false);
    }
  }, [pushToast]);

  useEffect(() => {
    refreshProviders();
  }, [refreshProviders]);

  const hasConfiguredProvider = useMemo(() => {
    if (!providers) {
      return false;
    }
    const providerList = Object.values(providers.providers) as ProviderConfigResponse[];
    return providerList.some((provider) => provider.has_api_key);
  }, [providers]);

  if (loadingProviders && !providers) {
    return <LoadingScreen message="Checking provider setup..." />;
  }

  if (!hasConfiguredProvider) {
    return (
      <SetupWizard
        providers={providers?.providers ?? {}}
        onConfigured={refreshProviders}
        errorMessage={providerError}
      />
    );
  }

  return (
    <div className="app-shell">
      <div className="relative z-10 flex min-h-screen">
        <Sidebar
          currentPath={location.pathname}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <main className="flex-1 px-6 pb-10 pt-8">
          <Routes>
            <Route path="/" element={<SessionList />} />
            <Route path="/session/:id" element={<SessionRouter />} />
            <Route
              path="*"
              element={
                <div className="p-10">
                  <h1 className="font-display text-2xl text-ink">Page not found</h1>
                  <Link
                    to="/"
                    className="mt-6 inline-flex items-center rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white"
                  >
                    Back to sessions
                  </Link>
                </div>
              }
            />
          </Routes>
        </main>
      </div>
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        providers={providers?.providers ?? {}}
        onUpdated={refreshProviders}
      />
    </div>
  );
}

export default function App(): JSX.Element {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
