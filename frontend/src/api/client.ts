import { ErrorCode } from "../types";

export interface ApiErrorPayload {
  code: ErrorCode | string;
  message: string;
  details: string[];
}

export class ApiError extends Error {
  public readonly status: number;

  public readonly code: ErrorCode | string;

  public readonly details: string[];

  constructor(status: number, code: ErrorCode | string, message: string, details: string[]) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export class BadRequestError extends ApiError {}

export class NotFoundError extends ApiError {}

export class ConflictError extends ApiError {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function extractApiError(data: unknown): ApiErrorPayload | null {
  if (!isRecord(data)) {
    return null;
  }
  const error = data.error;
  if (!isRecord(error)) {
    return null;
  }
  const code = typeof error.code === "string" ? error.code : "UNKNOWN";
  const message = typeof error.message === "string" ? error.message : "Request failed";
  const details = Array.isArray(error.details)
    ? error.details.filter((item): item is string => typeof item === "string")
    : [];
  return { code, message, details };
}

function resolveBaseUrl(): string {
  const env = import.meta.env as { VITE_API_BASE_URL?: string };
  return env.VITE_API_BASE_URL ?? "";
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const baseUrl = resolveBaseUrl();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  let body: BodyInit | null | undefined = options.body as BodyInit | null | undefined;
  if (
    body &&
    typeof body === "object" &&
    !(body instanceof FormData) &&
    !(body instanceof Blob) &&
    !(body instanceof ArrayBuffer) &&
    !(body instanceof URLSearchParams)
  ) {
    body = JSON.stringify(body);
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    body,
  });

  let payload: unknown = null;
  if (response.status !== 204) {
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text) as unknown;
      } catch {
        payload = text;
      }
    }
  }

  if (!response.ok) {
    const apiError = extractApiError(payload);
    const message = apiError?.message ?? response.statusText;
    const details = apiError?.details ?? [];
    const code = apiError?.code ?? "UNKNOWN";

    if (response.status === 400) {
      throw new BadRequestError(400, code, message, details);
    }
    if (response.status === 404) {
      throw new NotFoundError(404, code, message, details);
    }
    if (response.status === 409) {
      throw new ConflictError(409, code, message, details);
    }

    throw new ApiError(response.status, code, message, details);
  }

  return payload as T;
}
