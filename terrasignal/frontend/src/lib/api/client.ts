/** Typed fetch wrapper over the FastAPI backend.
 *
 * Response/request shapes come from `schema.d.ts`, generated from the backend's
 * OpenAPI spec (`npm run gen:api`) — never hand-edit them. The JWT lives in
 * localStorage for this demo; the production path swaps token storage for a
 * Cognito session without touching call sites. */

import type { components } from "./schema";

export type Schemas = components["schemas"];

// Browser calls the FastAPI backend directly (CORS-enabled). Locally we use
// 127.0.0.1 rather than localhost on purpose: on Windows `localhost` resolves to
// IPv6 (::1) first, but uvicorn binds IPv4, so the preflight would fail to
// connect. Deployed builds MUST set NEXT_PUBLIC_API_BASE to the backend origin.
//
// NEXT_PUBLIC_* is inlined at build time, not read at runtime: setting it in the
// hosting dashboard after a deploy has no effect until the next build.
const LOCAL_ORIGIN = "http://127.0.0.1:8000";

/** Backend origin with trailing slashes and a pasted `/api/v1` suffix removed —
 * both are easy to introduce in a hosting dashboard and produce 404s that look
 * like backend outages. Empty string means "unset in a production build". */
function resolveOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (!raw) return process.env.NODE_ENV === "production" ? "" : LOCAL_ORIGIN;
  return raw.replace(/\/+$/, "").replace(/\/api\/v1$/, "");
}

const ORIGIN = resolveOrigin();
const BASE = `${ORIGIN}/api/v1`;
const TOKEN_KEY = "terrasignal_token";

/** Misconfigurations that surface in the browser as an opaque "Failed to fetch".
 * Naming them turns a deploy debugging session into a one-line fix. */
function configError(): string | null {
  if (!ORIGIN) {
    return "NEXT_PUBLIC_API_BASE is not set. Point it at the backend origin (e.g. https://terrasignal-api.onrender.com) and redeploy — the value is baked in at build time.";
  }
  if (
    typeof window !== "undefined" &&
    window.location.protocol === "https:" &&
    ORIGIN.startsWith("http://")
  ) {
    return `Mixed content: this page is served over HTTPS but NEXT_PUBLIC_API_BASE is ${ORIGIN}. The browser blocks the request — use the backend's https:// URL.`;
  }
  return null;
}

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

  const misconfigured = configError();
  if (misconfigured) throw new ApiError(0, misconfigured);

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    // fetch() rejects with an opaque TypeError for both "host unreachable" and
    // "blocked by CORS policy" — the browser deliberately hides which. Name both.
    const origin = typeof window !== "undefined" ? window.location.origin : "this origin";
    throw new ApiError(
      0,
      `Could not reach the API at ${ORIGIN}. Either the backend is down, or it is rejecting ${origin} — add that origin to TERRASIGNAL_CORS_ALLOWED_ORIGINS on the backend and restart it.`,
    );
  }

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
