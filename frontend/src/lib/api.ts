"use client";

/**
 * 轻量类型化 API 客户端。
 * 说明：当前接口面小（约 20 个端点），手写类型最直观；
 * API 增长后再引入 orval 从 OpenAPI 生成（技术栈预留的演进路径）。
 */

import { enqueueOffline } from "./offlineQueue";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

const TOKEN_KEY = "gc_tokens";

export function loadTokens(): TokenPair | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(TOKEN_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TokenPair;
  } catch {
    clearTokens(); // 脏数据自愈：解析失败即视为未登录
    return null;
  }
}

function saveTokens(tokens: TokenPair) {
  window.localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
}

export function clearTokens() {
  window.localStorage.removeItem(TOKEN_KEY);
}

let refreshing: Promise<TokenPair | null> | null = null;

async function doRefresh(): Promise<TokenPair | null> {
  const tokens = loadTokens();
  if (!tokens) return null;
  let resp: Response;
  try {
    resp = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
  } catch {
    return null; // 网络故障：本次刷新失败，但不毒化后续重试
  }
  if (!resp.ok) return null;
  try {
    const fresh = (await resp.json()) as TokenPair;
    saveTokens(fresh);
    return fresh;
  } catch {
    return null;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const doFetch = async (accessToken: string | null) =>
    fetch(`${BASE}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

  let tokens = loadTokens();
  let resp: Response;
  try {
    resp = await doFetch(auth ? tokens?.access_token ?? null : null);
  } catch {
    throw new ApiError(0, "网络连接失败，请检查网络后重试");
  }

  if (resp.status === 401 && auth) {
    // 401 → 刷新令牌后重试一次；无论成败都重置单飞 Promise（防拒绝态被复用）
    refreshing = refreshing ?? doRefresh();
    try {
      tokens = await refreshing;
    } finally {
      refreshing = null;
    }
    if (tokens) {
      try {
        resp = await doFetch(tokens.access_token);
      } catch {
        throw new ApiError(0, "网络连接失败，请检查网络后重试");
      }
    }
    if (!tokens || resp.status === 401) {
      clearTokens();
      if (typeof window !== "undefined") window.location.replace("/login");
    }
  }

  if (!resp.ok) {
    let detail = `请求失败（${resp.status}）`;
    try {
      const data = (await resp.json()) as { detail?: string };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* 保底错误信息 */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T; // 204 无响应体（如登出）
  return (await resp.json()) as T;
}

// ---------- 类型 ----------

export interface TaskOut {
  id: number;
  date: string;
  title: string;
  duration_minutes: number;
  category_label: string;
  status: "todo" | "done" | "skipped";
  skip_reason: string | null;
  actual_minutes: number | null;
  completed_at: string | null;
}

export interface TodayOut {
  date: string;
  yesterday: { done: number; total: number };
  tasks: TaskOut[];
  life_log: { date: string; sleep_hours: number | null; exercise: boolean; mood: number | null } | null;
  journal_submitted: boolean;
  streak: number;
}

export interface GoalOut {
  id: number;
  title: string;
  description: string;
  deadline: string | null;
  weekly_hours: number | null;
  category: string;
  status: string;
  created_at: string;
  milestones: { id: number; title: string; status: string }[];
}

export interface ImportOut {
  status: "questions" | "proposal";
  questions: string[];
  proposal_id: number | null;
  plan_id: number | null;
  summary: string;
}

export interface ProposalOut {
  id: number;
  status: string;
  summary: string;
  tasks: { date: string; title: string; duration_minutes: number; category_label: string }[];
  week_start: string;
  version: number;
  created_at: string;
  decided_at: string | null;
}

export interface NotificationOut {
  id: number;
  type: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
}

export interface JournalOut {
  submitted: boolean;
  mood: number | null;
  note: string | null;
  today_done: number;
  today_total: number;
}

export const SKIP_REASONS = ["分心", "太难", "疲劳", "被打断"] as const;
export type SkipReason = (typeof SKIP_REASONS)[number];

/** 提案状态（与后端 ProposalStatus 枚举值对齐，避免魔法字符串）。 */
export const PROPOSAL_STATUS = {
  PENDING: "待审批",
  APPROVED: "已同意",
  REJECTED: "已拒绝",
} as const;

// ---------- API ----------

export const api = {
  register: (username: string, password: string) =>
    request<{ id: number }>("/auth/register", {
      method: "POST",
      body: { username, password },
      auth: false,
    }).then(async () => api.login(username, password)),

  login: async (username: string, password: string) => {
    const tokens = await request<TokenPair>("/auth/login", {
      method: "POST",
      body: { username, password },
      auth: false,
    });
    saveTokens(tokens);
  },

  logout: async () => {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } catch {
      /* 服务端撤销失败也继续清本地（离线登出仍可用） */
    }
    clearTokens();
  },

  today: () => request<TodayOut>("/today"),

  completeTask: async (id: number, actualMinutes?: number) => {
    const body = actualMinutes != null ? { actual_minutes: actualMinutes } : undefined;
    try {
      return await request<TaskOut>(`/tasks/${id}/complete`, { method: "POST", body });
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 0) {
        enqueueOffline("POST", `/tasks/${id}/complete`, body); // 断网→入队
      }
      throw exc;
    }
  },

  skipTask: async (id: number, reason: SkipReason) => {
    try {
      return await request<TaskOut>(`/tasks/${id}/skip`, { method: "POST", body: { reason } });
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 0) {
        enqueueOffline("POST", `/tasks/${id}/skip`, { reason });
      }
      throw exc;
    }
  },

  saveLifeLog: async (payload: {
    sleep_hours?: number;
    exercise?: boolean;
    mood?: number;
  }) => {
    try {
      return await request<TodayOut["life_log"]>("/life-logs", { method: "POST", body: payload });
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 0) {
        enqueueOffline("POST", "/life-logs", payload);
        return null; // 离线已入队：返回 null（无错误），联网后自动补传
      }
      throw exc;
    }
  },

  getJournal: () => request<JournalOut>("/journals/today"),

  submitJournal: (mood: number, note: string) =>
    request<JournalOut>("/journals/today", { method: "POST", body: { mood, note } }),

  listGoals: () => request<GoalOut[]>("/goals"),

  createGoal: (payload: {
    title: string;
    category: string;
    deadline?: string;
    weekly_hours?: number;
  }) => request<GoalOut>("/goals", { method: "POST", body: payload }),

  importPlan: (goalId: number, rawText: string, weeklyHours?: number) =>
    request<ImportOut>("/plans/import", {
      method: "POST",
      body: { goal_id: goalId, raw_text: rawText, weekly_hours: weeklyHours },
    }),

  getProposal: (id: number) => request<ProposalOut>(`/proposals/${id}`),

  listProposals: () => request<ProposalOut[]>("/proposals"),

  listStatsHeatmap: (weeks = 8) =>
    request<{ days: { date: string; done: number; total: number }[]; weeks: number }>(
      `/stats/heatmap?weeks=${weeks}`,
    ),

  listStatsTrends: (weeks = 8) =>
    request<{
      weeks: { week_start: string; done: number; total: number; rate: number }[];
    }>(`/stats/trends?weeks=${weeks}`),

  listStatsSkipReasons: (days = 90) =>
    request<{ items: { reason: string; count: number; pct: number }[]; window_days: number }>(
      `/stats/skip-reasons?days=${days}`,
    ),

  listStatsHours: (days = 90) =>
    request<{ completion_hours: number[]; skip_hours: number[]; window_days: number }>(
      `/stats/hours?days=${days}`,
    ),

  // ---------- 周报 ----------

  listWeeklyReports: () =>
    request<
      {
        id: number;
        week_start: string;
        title: string;
        content: string;
        data_snapshot: Record<string, unknown>;
        created_at: string;
        updated_at: string;
      }[]
    >("/reports/weekly"),

  generateWeeklyReport: () =>
    request<{ id: number; week_start: string; title: string; content: string }>(
      "/reports/weekly",
      { method: "POST" },
    ),

  // ---------- 推送设置 ----------

  getPushSettings: () =>
    request<{ channel: string; endpoint: string; enabled: boolean } | null>("/settings/push"),

  savePushSettings: (payload: { channel: string; endpoint: string; enabled: boolean }) =>
    request<{ channel: string; endpoint: string; enabled: boolean }>("/settings/push", {
      method: "PUT",
      body: payload,
    }),

  testPush: () =>
    request<{ delivered: boolean; message: string }>("/settings/push/test", { method: "POST" }),

  approveProposal: (id: number) =>
    request<ProposalOut>(`/proposals/${id}/approve`, { method: "POST" }),

  rejectProposal: (id: number) =>
    request<ProposalOut>(`/proposals/${id}/reject`, { method: "POST" }),

  listNotifications: () => request<NotificationOut[]>("/notifications"),

  readNotification: (id: number) =>
    request<NotificationOut>(`/notifications/${id}/read`, { method: "POST" }),

  getLLMSettings: () =>
    request<{ base_url: string; model_name: string; api_key_masked: string } | null>(
      "/settings/llm",
    ),

  saveLLMSettings: (payload: { base_url: string; api_key: string; model_name: string }) =>
    request<{ base_url: string; model_name: string; api_key_masked: string }>("/settings/llm", {
      method: "PUT",
      body: payload,
    }),
};
