/** Typed fetch wrapper over the FastAPI backend.
 *
 * Response/request shapes come from `schema.d.ts`, generated from the backend's
 * OpenAPI spec (`npm run gen:api`) — never hand-edit them. The JWT lives in
 * localStorage for this demo; the production path swaps token storage for a
 * Cognito session without touching call sites. */

import type { components } from "./schema";

export type Schemas = components["schemas"];

// Browser calls the FastAPI backend directly (CORS-enabled). We use 127.0.0.1
// rather than localhost on purpose: on Windows `localhost` resolves to IPv6
// (::1) first, but uvicorn binds IPv4, so the preflight would fail to connect.
// Override the origin with NEXT_PUBLIC_API_BASE for non-local deployments.
const BASE = `${process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"}/api/v1`;
const TOKEN_KEY = "terrasignal_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface FetchOpts {
  method?: string;
  body?: unknown;
  /** Set false for the login call, which has no token yet. */
  auth?: boolean;
  /** Parse the response as text rather than JSON (e.g. model cards). */
  asText?: boolean;
}

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const { method = "GET", body, auth = true, asText = false } = opts;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") clearToken();
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (asText ? await res.text() : await res.json()) as T;
}
