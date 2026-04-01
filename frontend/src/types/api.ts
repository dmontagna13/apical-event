import type { SessionState, SessionSubstate } from "./index";

export interface ProviderConfig {
  display_name: string;
  base_url: string | null;
  api_key_env: string | null;
  api_key: string | null;
  default_model: string | null;
  available_models: string[];
  supports_function_calling: boolean;
  supports_structured_output: boolean;
  max_context_tokens: number;
}

export interface ProviderConfigResponse extends ProviderConfig {
  has_api_key: boolean;
}

export interface ProvidersResponse {
  providers: Record<string, ProviderConfigResponse>;
}

export interface ProviderTestResponse {
  ok: boolean;
  error?: string;
}

export interface SessionSummary {
  session_id: string;
  project_name: string;
  packet_id: string;
  state: SessionState;
  substate: SessionSubstate | null;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
}

export interface SessionMetadataResponse {
  session_id: string;
  project_name: string;
  packet_id: string;
  state: SessionState;
  substate: SessionSubstate | null;
}

export interface RollCallResponse {
  ok: boolean;
  state?: SessionState;
}

export interface Preset {
  name: string;
  created_at: string;
  assignments: { role_id: string; provider: string; model: string }[];
}

export interface PresetsResponse {
  presets: Preset[];
}

export interface SavePresetResponse {
  ok: boolean;
}
