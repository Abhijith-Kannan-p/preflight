// Thin typed client for the Preflight API. Errors carry the server's friendly message.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/Abhijith-Kannan-p/preflight";

const TOKEN_KEY = "preflight.token";
/** Fired when the server no longer recognises the session (an expired demo sandbox). */
export const SESSION_EXPIRED = "preflight:session-expired";

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable (private mode); the session then lives in memory only.
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

/** No request may leave a spinner running: give up after this long with a clear message. */
const TIMEOUT_MS = 45_000;

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function newKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** `idempotencyKey`: the same key for the same intent (e.g. one form submission) makes a
 * repeated request return the first answer instead of running twice. Mutating requests
 * without one get a fresh key, which still protects against network-level retries. */
export async function api<T>(path: string, init: RequestInit & { idempotencyKey?: string } = {}): Promise<T> {
  const { idempotencyKey, ...rest } = init;
  init = rest;
  const headers = new Headers(init.headers);
  if (MUTATING.has((init.method ?? "GET").toUpperCase())) headers.set("Idempotency-Key", idempotencyKey ?? newKey());
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers, signal: init.signal ?? controller.signal });
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(0, "The Preflight engine did not answer within 45 seconds. It may be waking up or busy; please try again.");
    }
    throw new ApiError(0, "Cannot reach the Preflight engine. It may be waking up; try again in a moment.");
  } finally {
    window.clearTimeout(timer);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    if (response.status === 401 && token) window.dispatchEvent(new Event(SESSION_EXPIRED));
    if (response.status === 403) {
      // Wrong role: explain how to get the right one instead of a bare "forbidden".
      const reason = messageFrom(detail, "Your current role cannot do this.");
      throw new ApiError(403, `${reason} Switch to a role that can from the user menu at the top right; the Help panel (?) lists who can do what.`, detail);
    }
    throw new ApiError(response.status, messageFrom(detail, `Request failed (${response.status}).`), detail);
  }
  return body as T;
}

export const fetcher = <T>(path: string) => api<T>(path);

export function post<T>(path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  return api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), idempotencyKey });
}

/** Calls the sandbox API through this site's own origin (see next.config.ts), so the
 * httpOnly sandbox cookie is first-party. */
export async function sandboxCall<T>(action: "session" | "reset", body: { user_id?: string | null }): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/sandbox/${action}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Preflight engine. It may be waking up; try again in a moment.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, messageFrom(data?.detail, `Could not open your demo workspace (${response.status}).`), data?.detail);
  return data as T;
}
