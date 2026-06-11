/**
 * Base API client for the FastAPI backend.
 *
 * All requests go through `apiFetch`. It handles:
 *   - Prefixing with NEXT_PUBLIC_BACKEND_URL
 *   - Injecting the backend JWT from the auth-token store
 *   - Setting Content-Type for JSON bodies
 *   - Extracting the `detail` field from FastAPI error responses
 *   - Throwing a typed ApiError on non-2xx responses
 *   - 401 retry: force-refresh the session once, then signOut on second failure
 */

import { getAuthToken, setAuthToken } from "@/lib/auth-token";

const BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly body: unknown
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  timeoutMs?: number;
};

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
  _isRetry = false
): Promise<T> {
  const { body, timeoutMs = 120_000, headers: extraHeaders, ...rest } = options;

  const headers = new Headers(extraHeaders);
  if (body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const signal = options.signal ?? AbortSignal.timeout(timeoutMs);

  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (response.status === 401 && !_isRetry) {
    // Force-refresh the session to get a new backendToken, then retry once.
    try {
      const { getSession, signOut } = await import("next-auth/react");
      const session = await getSession();
      if (session?.backendToken) {
        setAuthToken(session.backendToken);
        return apiFetch<T>(path, options, true);
      }
      await signOut({ callbackUrl: "/auth/signin" });
    } catch {
      // If next-auth isn't available (e.g. SSR edge), just throw.
    }
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const json = await response.json();
      if (typeof json?.detail === "string") detail = json.detail;
      else if (Array.isArray(json?.detail))
        detail = json.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      detail = response.statusText || detail;
    }
    throw new ApiError(response.status, detail, null);
  }

  // Return raw Response for endpoints that stream or return binary (e.g. PDF download)
  if (response.headers.get("content-type")?.includes("application/pdf")) {
    return response as unknown as T;
  }

  return response.json() as Promise<T>;
}

/** Convenience wrappers */
export const api = {
  get: <T>(path: string, init?: Omit<RequestOptions, "method" | "body">) =>
    apiFetch<T>(path, { ...init, method: "GET" }),

  post: <T>(path: string, body?: unknown, init?: Omit<RequestOptions, "method">) =>
    apiFetch<T>(path, { ...init, method: "POST", body }),

  delete: <T>(path: string, init?: Omit<RequestOptions, "method" | "body">) =>
    apiFetch<T>(path, { ...init, method: "DELETE" }),
};
