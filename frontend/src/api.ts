// REST + WebSocket client for the Solar AI Optimizer backend.

import type {
  AppConfigView,
  Decision,
  EntityInfo,
  ExecutionResult,
  ForecastBundle,
  GridStats,
  Override,
  SessionInfo,
  ShedResult,
  SystemStatus,
  Telemetry,
} from "./types.js";

// Derive a path prefix from the current location so the app works both
// standalone (served at "/") and behind a Home Assistant ingress path.
export function basePrefix(): string {
  const p = location.pathname;
  const ingress = p.match(/^(\/api\/(?:hassio_ingress|ingress)\/[^/]+)/);
  if (ingress) return ingress[1];
  if (p.endsWith("/")) return p.replace(/\/+$/, "");
  return "";
}

/** Current API path prefix (re-read on each call for ingress redirect safety). */
export function getBase(): string {
  return basePrefix();
}

export function getApiToken(): string {
  try {
    return localStorage.getItem("solar-api-token") ?? "";
  } catch {
    return "";
  }
}

export function setApiToken(token: string): void {
  try {
    if (token) localStorage.setItem("solar-api-token", token);
    else localStorage.removeItem("solar-api-token");
  } catch {
    /* ignore */
  }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getApiToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

function fetchInit(init: RequestInit = {}): RequestInit {
  return {
    credentials: "include",
    ...init,
    headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) },
  };
}

async function parseError(res: Response, path: string): Promise<string> {
  if (res.status === 401) {
    return `${path} -> 401 Unauthorized`;
  }
  try {
    const body = (await res.json()) as {
      detail?: string | Array<{ loc?: unknown[]; msg?: string }>;
      error?: string;
    };
    if (Array.isArray(body.detail)) {
      const lines = body.detail.map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.join(".") : "";
        return loc ? `${loc}: ${d.msg ?? "invalid"}` : String(d.msg ?? "invalid");
      });
      return `${path} -> ${res.status}: ${lines.join("; ")}`;
    }
    const msg = typeof body.detail === "string" ? body.detail : body.error;
    if (msg) return `${path} -> ${res.status}: ${msg}`;
  } catch {
    /* ignore */
  }
  return `${path} -> ${res.status}`;
}

export class AuthRequiredError extends Error {
  constructor() {
    super("Unauthorized");
    this.name = "AuthRequiredError";
  }
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${getBase()}${path}`, fetchInit());
  if (!res.ok) throw new Error(await parseError(res, path));
  return (await res.json()) as T;
}

async function sendJSON<T>(method: string, path: string, body: unknown): Promise<T> {
  const res = await fetch(
    `${getBase()}${path}`,
    fetchInit({
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }),
  );
  if (!res.ok) throw new Error(await parseError(res, path));
  return (await res.json()) as T;
}

const postJSON = <T>(path: string, body: unknown) => sendJSON<T>("POST", path, body);
const putJSON = <T>(path: string, body: unknown) => sendJSON<T>("PUT", path, body);

export const api = {
  me: async (): Promise<SessionInfo> => {
    const res = await fetch(`${getBase()}/api/me`, fetchInit());
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error(await parseError(res, "/api/me"));
    return (await res.json()) as SessionInfo;
  },
  login: (username: string, password: string) =>
    postJSON<{ ok: boolean }>("/api/auth/login", { username, password }),
  logout: () => postJSON<{ ok: boolean }>("/api/auth/logout", {}),
  status: () => getJSON<SystemStatus>("/api/status"),
  forecast: () => getJSON<ForecastBundle>("/api/forecast"),
  plan: () =>
    getJSON<{
      decision: Decision | null;
      results: ExecutionResult[];
      shed_results: ShedResult[];
      shadow_mode: boolean;
      paused: boolean;
    }>("/api/plan"),
  gridStats: () => getJSON<GridStats>("/api/grid-stats"),
  config: () => getJSON<AppConfigView>("/api/config"),
  historyTelemetry: (hours = 24) =>
    getJSON<Telemetry[]>(`/api/history/telemetry?hours=${hours}`),
  historyDecisions: (limit = 100) =>
    getJSON<import("./types.js").DecisionHistoryRow[]>(
      `/api/history/decisions?limit=${limit}`,
    ),
  historyGridEvents: (days = 7) =>
    getJSON<import("./types.js").GridEventRow[]>(
      `/api/history/grid-events?days=${days}`,
    ),
  historyExecutions: (limit = 100) =>
    getJSON<import("./types.js").ExecutionHistoryRow[]>(
      `/api/history/executions?limit=${limit}`,
    ),
  historyShedExecutions: (limit = 100) =>
    getJSON<import("./types.js").ShedExecutionRow[]>(
      `/api/history/shed-executions?limit=${limit}`,
    ),
  refreshForecast: () => postJSON<ForecastBundle>("/api/forecast/refresh", {}),
  forceCycle: () => postJSON<Decision>("/api/cycle", {}),
  override: (ov: Override) => postJSON<Record<string, unknown>>("/api/override", ov),
  clearOverride: () => postJSON<{ cleared: boolean }>("/api/override/clear", {}),
  ask: (question: string, apply = false) =>
    postJSON<{
      answer: string;
      intent: Override | null;
      applied: unknown;
      blocked?: boolean;
      block_reason?: string | null;
      llm_enabled: boolean;
    }>("/api/assistant/ask", { question, apply }),
  entities: (domain?: string) =>
    getJSON<{ connected: boolean; entities: EntityInfo[] }>(
      `/api/entities${domain ? `?domain=${encodeURIComponent(domain)}` : ""}`,
    ),
  putConfig: (patch: Record<string, unknown>) =>
    putJSON<{ ok: boolean; error?: string; config?: AppConfigView }>("/api/config", patch),
  resetConfig: () => postJSON<{ ok: boolean }>("/api/config/reset", {}),
  exportModel: () => getJSON<Record<string, unknown>>("/api/model/export"),
  importModel: (data: Record<string, unknown>) =>
    postJSON<{ ok: boolean; ml_import_locked?: boolean }>("/api/model/import", data),
  retrainModel: () =>
    postJSON<{ ok: boolean; trained: boolean; ml_import_locked: boolean }>(
      "/api/model/retrain",
      {},
    ),
};

export type StatusListener = (status: SystemStatus) => void;

export class LiveSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<StatusListener>();
  private reconnectTimer: number | null = null;
  private reconnectAttempt = 0;
  private enabled = false;

  connect(): void {
    this.enabled = true;
    this.open();
  }

  disconnect(): void {
    this.enabled = false;
    if (this.reconnectTimer != null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  private open(): void {
    if (!this.enabled) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const token = getApiToken();
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    const url = `${proto}://${location.host}${getBase()}/ws${qs}`;
    this.ws = new WebSocket(url);
    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
    };
    this.ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data?.type === "ping") return;
        this.listeners.forEach((l) => l(data as SystemStatus));
      } catch {
        /* ignore malformed frame */
      }
    };
    this.ws.onclose = () => this.scheduleReconnect();
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect(): void {
    if (!this.enabled) return;
    if (this.reconnectTimer != null) return;
    const base = 1000;
    const max = 30_000;
    const exp = Math.min(max, base * 2 ** this.reconnectAttempt);
    const jitter = Math.floor(Math.random() * 500);
    const delay = exp + jitter;
    this.reconnectAttempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }

  onStatus(listener: StatusListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const live = new LiveSocket();
