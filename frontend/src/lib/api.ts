"use client";

/**
 * 轻量类型化 API 客户端。
 * 说明：当前接口面小（约 20 个端点），手写类型最直观；
 * API 增长后再引入 orval 从 OpenAPI 生成（技术栈预留的演进路径）。
 */

import { enqueueOffline } from "./offlineQueue";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8100/api/v1";

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

// ---------- 教练对齐 SSE 流式导入 ----------

/** /plans/import/stream 下发的过程事件（与后端 planner.py 的 emit 一一对应）。 */
export type PlanStreamEvent =
  | { type: "phase"; name: "gather" | "parse"; state: "start" | "done"; subjects?: number; role?: string }
  | { type: "round"; index: number; max: number; role?: string }
  | { type: "thought"; text: string; role?: string }
  | { type: "tool"; name: string; state: "start" | "done" | "error"; detail?: string; role?: string }
  | { type: "proposal"; id: number; role?: string }
  | { type: "questions"; questions: string[]; role?: string };

/**
 * 流式计划导入：教练每一步通过 onEvent 实时回调（渲染过程时间线），
 * 最终结果（done 事件携带的 ImportOut）作为 Promise 值返回。
 * 业务失败在流内以 error 事件传达，转换为 ApiError 抛出（400=需配置模型）。
 */
export async function importPlanStream(
  goalId: number,
  rawText: string,
  weeklyHours: number | undefined,
  onEvent: (ev: PlanStreamEvent) => void,
): Promise<ImportOut> {
  const tokens = loadTokens();
  let resp: Response;
  try {
    resp = await fetch(`${BASE}/plans/import/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
      },
      body: JSON.stringify({ goal_id: goalId, raw_text: rawText, weekly_hours: weeklyHours }),
    });
  } catch {
    throw new ApiError(0, "网络连接失败，请检查网络后重试");
  }
  if (resp.status === 401) {
    clearTokens();
    if (typeof window !== "undefined") window.location.replace("/login");
    throw new ApiError(401, "登录已过期，请重新登录");
  }
  if (!resp.ok || !resp.body) throw new ApiError(resp.status, "流式导入暂不可用，请稍后重试");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ImportOut | null = null;

  const consume = (payload: string) => {
    if (!payload.startsWith("data: ")) return;
    let ev: PlanStreamEvent | ({ type: "done"; result: ImportOut } | { type: "error"; code: string; message: string });
    try {
      ev = JSON.parse(payload.slice(6));
    } catch {
      return; // 半截/脏数据帧：丢弃等下一帧
    }
    if (ev.type === "done") {
      final = ev.result;
      return;
    }
    if (ev.type === "error") {
      throw new ApiError(ev.code === "need_settings" ? 400 : 502, ev.message);
    }
    onEvent(ev);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? ""; // 末段可能是半截事件，留到下一轮
    for (const part of parts) consume(part.trim());
    if (done) break;
  }
  if (buffer.trim()) consume(buffer.trim());
  if (!final) throw new ApiError(0, "连接中断，请重试");
  return final;
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
  coach_hint: string; // 同因跳过≥3 次/周时的教练即时提示（空=无）
}

export interface TodayOut {
  date: string;
  yesterday: { done: number; total: number };
  tasks: TaskOut[];
  upcoming: TaskOut[]; // 今天无任务时的"即将开始"预览（有任务时为空数组）
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

  /** 归档目标（软删除：退出各列表、生效计划停排，历史保留）。 */
  archiveGoal: (id: number) => request<GoalOut>(`/goals/${id}/archive`, { method: "POST" }),

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

  rejectProposal: (id: number, reason?: string) =>
    request<ProposalOut>(`/proposals/${id}/reject`, {
      method: "POST",
      body: { reason: reason ?? "" },
    }),

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

  /** 用已保存配置按教练同款形态（带 tools）真实验证一次。 */
  verifyLLMSettings: () => request<{ ok: boolean }>("/settings/llm/verify", { method: "POST" }),

  /** 演示时钟（仅后端 GC_DEMO_MODE=true 时可用；404=隐藏该功能）。 */
  getDemoClock: () =>
    request<{ demo_mode: boolean; today: string; override: string | null }>("/dev/clock"),
  advanceDemoClock: (payload: { date?: string; advance_days?: number; reset?: boolean }) =>
    request<{ demo_mode: boolean; today: string; override: string | null }>("/dev/clock", {
      method: "POST",
      body: payload,
    }),

  /** 管理后台（仅 GC_ADMIN_USERNAMES 中的用户可用；403=非管理员，前端隐藏入口）。 */
  adminOverview: () =>
    request<Record<string, number>>("/admin/overview"),
  adminUsers: () =>
    request<
      {
        id: number;
        username: string;
        created_at: string;
        is_active: boolean;
        goals: number;
        active_goals: number;
        tasks_total: number;
        tasks_done: number;
        llm_configured: boolean;
      }[]
    >("/admin/users"),
  adminProposals: () =>
    request<
      {
        id: number;
        username: string;
        goal_title: string;
        status: string;
        rejection_reason: string | null;
        created_at: string;
        summary: string;
      }[]
    >("/admin/proposals"),
  adminResetUser: (userId: number) =>
    request<{ removed_tasks: number; message: string }>(`/admin/users/${userId}/reset-history`, {
      method: "POST",
    }),

  /** 禁用/启用账号（禁用后无法登录、令牌即刻失效）。 */
  adminSetUserActive: (userId: number, active: boolean) =>
    request<{ username: string; is_active: boolean; message: string }>(
      `/admin/users/${userId}/active`,
      { method: "PATCH", body: { active } },
    ),

  /** 重置密码为随机临时密码（返回一次）。 */
  adminResetUserPassword: (userId: number) =>
    request<{ username: string; temp_password: string; message: string }>(
      `/admin/users/${userId}/reset-password`,
      { method: "POST" },
    ),

  /** 删除用户及其全部数据（不可恢复）。 */
  adminDeleteUser: (userId: number) =>
    request<{ message: string }>(`/admin/users/${userId}`, { method: "DELETE" }),

  /** 管理员直接创建账号。 */
  adminCreateUser: (username: string, password: string) =>
    request<{ username: string; message: string }>("/admin/users", {
      method: "POST",
      body: { username, password },
    }),

  /** 目标管理（跨用户）：列表/编辑/删除。 */
  adminGoals: () =>
    request<
      {
        id: number;
        username: string;
        title: string;
        category: string;
        status: string;
        deadline: string | null;
        weekly_hours: number | null;
      }[]
    >("/admin/goals"),
  adminUpdateGoal: (
    goalId: number,
    patch: { title?: string; deadline?: string; weekly_hours?: number; status?: string },
  ) => request<{ message: string }>(`/admin/goals/${goalId}`, { method: "PATCH", body: patch }),
  adminDeleteGoal: (goalId: number) =>
    request<{ message: string }>(`/admin/goals/${goalId}`, { method: "DELETE" }),

  /** 任务管理（跨用户）：列表（可按用户筛）/编辑/删除。 */
  adminTasks: (userId?: number) =>
    request<
      {
        id: number;
        username: string;
        goal_title: string;
        date: string;
        title: string;
        duration_minutes: number;
        status: string;
        skip_reason: string | null;
      }[]
    >(`/admin/tasks${userId ? `?user_id=${userId}` : ""}`),
  adminUpdateTask: (
    taskId: number,
    patch: { title?: string; date?: string; duration_minutes?: number; status?: string },
  ) => request<{ message: string }>(`/admin/tasks/${taskId}`, { method: "PATCH", body: patch }),
  adminDeleteTask: (taskId: number) =>
    request<{ message: string }>(`/admin/tasks/${taskId}`, { method: "DELETE" }),

  /** 提案代批/代拒（管理员，与用户审批同一条业务路径）。 */
  adminApproveProposal: (proposalId: number) =>
    request<{ message: string }>(`/admin/proposals/${proposalId}/approve`, { method: "POST" }),
  adminRejectProposal: (proposalId: number, reason?: string) =>
    request<{ message: string }>(`/admin/proposals/${proposalId}/reject`, {
      method: "POST",
      body: { reason: reason ?? "" },
    }),

  /** 记录类管理（查+删）：周报/复盘/生活打卡/通知。 */
  adminReports: () =>
    request<{ id: number; username: string; week_start: string; title: string; content: string }[]>(
      "/admin/reports",
    ),
  adminDeleteReport: (id: number) =>
    request<{ message: string }>(`/admin/reports/${id}`, { method: "DELETE" }),
  adminJournals: () =>
    request<{ id: number; username: string; date: string; mood: number; note: string }[]>(
      "/admin/journals",
    ),
  adminDeleteJournal: (id: number) =>
    request<{ message: string }>(`/admin/journals/${id}`, { method: "DELETE" }),
  adminLifeLogs: () =>
    request<
      {
        id: number;
        username: string;
        date: string;
        sleep_hours: number | null;
        exercise: boolean;
        mood: number | null;
      }[]
    >("/admin/life-logs"),
  adminDeleteLifeLog: (id: number) =>
    request<{ message: string }>(`/admin/life-logs/${id}`, { method: "DELETE" }),
  adminNotifications: () =>
    request<
      { id: number; username: string; type: string; title: string; body: string; read: boolean }[]
    >("/admin/notifications"),
  adminDeleteNotification: (id: number) =>
    request<{ message: string }>(`/admin/notifications/${id}`, { method: "DELETE" }),

  /** 用户模型配置：查全部 + 清除指定用户的。 */
  adminLLMSettings: () =>
    request<
      {
        user_id: number;
        username: string;
        base_url: string;
        model_name: string;
        updated_at: string;
      }[]
    >("/admin/llm-settings"),
  adminClearLLMSettings: (userId: number) =>
    request<{ message: string }>(`/admin/llm-settings/${userId}`, { method: "DELETE" }),

  /** 全库 JSON 备份下载（管理员；返回 blob 供浏览器存文件）。 */
  adminBackup: async (): Promise<Blob> => {
    const tokens = loadTokens();
    const resp = await fetch(`${BASE}/admin/backup`, {
      headers: tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {},
    });
    if (!resp.ok) throw new ApiError(resp.status, "备份下载失败");
    return resp.blob();
  },
};
