export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  department: string | null;
  location: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Citation {
  index: number;
  document: string;
  page: number | null;
  section: string | null;
  excerpt: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  cached?: boolean;
  fallback?: boolean;
  latencyMs?: number;
  createdAt: string;
  feedback?: 1 | -1;
  steps?: AgentStep[];
  escalated?: boolean;
}

export interface AgentStep {
  tool: string;
  args: Record<string, unknown>;
  observation: Record<string, unknown>;
}

export interface DocMeta {
  id: string;
  file_name: string;
  version: number;
  status: string;
  policy_category: string | null;
}

export interface Overview {
  query_volume: number;
  avg_latency_ms: number;
  cache_hit_rate: number;
  feedback: { up: number; down: number; satisfaction: number | null };
  tokens: { in: number; out: number };
  top_questions: Array<{ query: string; count: number }>;
}

async function request<T>(path: string, token: string | null, init?: RequestInit): Promise<T> {
  const doFetch = (t: string | null) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  const readError = async (res: Response): Promise<string> => {
    try {
      const text = await res.text();
      try {
        const parsed = JSON.parse(text) as { detail?: string };
        return parsed.detail ?? text;
      } catch {
        return text;
      }
    } catch {
      return res.statusText;
    }
  };
  let res = await doFetch(token ?? getAccessToken());
  if (res.status === 401 && !path.startsWith("/api/v1/auth/")) {
    try {
      res = await doFetch(await refreshAccess());
    } catch {
      /* refresh failed — report the original 401 below */
      const first = await doFetch(token ?? getAccessToken());
      if (!first.ok) throw new ApiError(first.status, await readError(first));
      return first.json() as Promise<T>;
    }
    if (res.status === 401) {
      const first = await doFetch(token ?? getAccessToken());
      if (!first.ok) throw new ApiError(first.status, await readError(first));
      return first.json() as Promise<T>;
    }
  }
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/* Token store + silent refresh: one 401 triggers rotation, then a single retry. */
let _access: string | null = null;
let _refresh: string | null = null;
let _refreshing: Promise<string> | null = null;

export function setTokens(access: string | null, refresh: string | null) {
  _access = access;
  _refresh = refresh;
}

export function getAccessToken(): string | null {
  return _access;
}

async function refreshAccess(): Promise<string> {
  if (!_refreshing) {
    _refreshing = (async () => {
      if (!_refresh) throw new ApiError(401, "No refresh token");
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: _refresh }),
      });
      if (!res.ok) throw new ApiError(res.status, await res.text());
      const pair = (await res.json()) as TokenPair;
      _access = pair.access_token;
      _refresh = pair.refresh_token;
      try {
        localStorage.setItem("hr-token", pair.access_token);
        localStorage.setItem("hr-refresh", pair.refresh_token);
      } catch {
        /* private mode — session-only */
      }
      return pair.access_token;
    })();
    void _refreshing.finally(() => {
      _refreshing = null;
    });
  }
  return _refreshing;
}

/** Raw fetch with silent refresh (for streams + uploads that bypass request()). */
export async function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  const withAuth = (t: string | null) => {
    const headers = new Headers(init?.headers);
    if (t) headers.set("Authorization", `Bearer ${t}`);
    return fetch(`${API_BASE}${path}`, { ...init, headers });
  };
  let res = await withAuth(getAccessToken());
  if (res.status === 401) {
    try {
      res = await withAuth(await refreshAccess());
    } catch {
      /* refresh failed — caller sees the 401 */
    }
  }
  return res;
}

export const api = {
  register: (body: { email: string; password: string; full_name: string }) =>
    request<User>("/api/v1/auth/register", null, { method: "POST", body: JSON.stringify(body) }),
  login: (email: string, password: string) =>
    request<TokenPair>("/api/v1/auth/login", null, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: (token: string, refresh_token?: string) =>
    request("/api/v1/auth/logout", token, {
      method: "POST",
      body: JSON.stringify({ refresh_token: refresh_token ?? null }),
    }),
  users: (token: string) => request<User[]>("/api/v1/admin/users", token),
  setRole: (token: string, id: string, role: string) =>
    request<User>(`/api/v1/admin/users/${id}/role`, token, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  overview: (token: string) => request<Overview>("/api/v1/admin/overview", token),
  documents: (token: string) => request<DocMeta[]>("/api/v1/documents", token),
  upload: async (
    token: string,
    file: File,
    meta: { department?: string; location?: string; policy_category?: string; access_level?: string },
    onProgress?: (pct: number) => void,
  ): Promise<{ document_id: string; status: string; version: number }> => {
    const params = new URLSearchParams();
    if (meta.department) params.set("department", meta.department);
    if (meta.location) params.set("location", meta.location);
    if (meta.policy_category) params.set("policy_category", meta.policy_category);
    if (meta.access_level) params.set("access_level", meta.access_level);
    const form = new FormData();
    form.append("file", file);
    onProgress?.(10);
    const res = await fetchWithAuth(`/api/v1/documents/upload?${params}`, {
      method: "POST",
      body: form,
    });
    onProgress?.(90);
    if (!res.ok) throw new ApiError(res.status, await res.text());
    onProgress?.(100);
    return res.json();
  },
  feedback: (token: string, query_log_id: string, score: 1 | -1) =>
    request("/api/v1/feedback", token, {
      method: "POST",
      body: JSON.stringify({ query_log_id, score }),
    }),

  /** POST SSE stream: citations event, token events, [DONE]. */
  streamChat: async (
    token: string,
    path: "/api/v1/chat/stream" | "/api/v1/agent/chat",
    body: Record<string, unknown>,
    onEvent: (ev: StreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const res = await fetchWithAuth(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") {
          onEvent({ type: "done" });
          return;
        }
        try {
          const json = JSON.parse(data);
          if (json.citations) onEvent({ type: "citations", citations: json.citations });
          else if (json.token) onEvent({ type: "token", token: json.token });
          else if (json.answer) onEvent({ type: "answer", answer: json.answer, fallback: !!json.fallback });
        } catch {
          /* partial chunk — wait for more */
          buf = part + "\n\n" + buf;
        }
      }
    }
    onEvent({ type: "done" });
  },
};

export type StreamEvent =
  | { type: "citations"; citations: Citation[] }
  | { type: "token"; token: string }
  | { type: "answer"; answer: string; fallback: boolean }
  | { type: "done" };
