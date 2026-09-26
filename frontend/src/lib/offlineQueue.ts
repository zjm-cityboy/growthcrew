"use client";

/**
 * 离线打卡队列：断网时暂存写操作（打卡/跳过/生活记录），
 * 恢复联网后按序补传（自习室地下室场景的核心保障）。
 *
 * 存储：localStorage key "gc_offline_queue"
 * 格式：[{ method, path, body, queuedAt, retryCount }]
 * 上限：50 条（超过丢弃最旧的——打卡是时效性数据，太旧的没意义）
 */

import { loadTokens, clearTokens } from "./api";

const QUEUE_KEY = "gc_offline_queue";
const MAX_QUEUE_SIZE = 50;
const MAX_RETRIES = 3;

interface QueuedRequest {
  method: string;
  path: string;
  body?: unknown;
  queuedAt: number;
  retryCount: number;
}

export function getOfflineQueue(): QueuedRequest[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(QUEUE_KEY) ?? "[]") as QueuedRequest[];
  } catch {
    return [];
  }
}

export function enqueueOffline(method: string, path: string, body?: unknown): void {
  const queue = getOfflineQueue();
  queue.push({ method, path, body, queuedAt: Date.now(), retryCount: 0 });
  while (queue.length > MAX_QUEUE_SIZE) queue.shift();
  window.localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export function getQueueSize(): number {
  return getOfflineQueue().length;
}

async function refreshTokens(): Promise<string | null> {
  const tokens = loadTokens();
  if (!tokens) return null;
  try {
    const resp = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1"}/auth/refresh`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      },
    );
    if (!resp.ok) return null;
    const fresh = (await resp.json()) as { access_token: string; refresh_token: string };
    window.localStorage.setItem("gc_tokens", JSON.stringify(fresh));
    return fresh.access_token;
  } catch {
    return null;
  }
}

/** 按序补传全部离线请求；返回 { synced, failed }。 */
export async function syncOfflineQueue(): Promise<{ synced: number; failed: number }> {
  const queue = getOfflineQueue();
  if (queue.length === 0) return { synced: 0, failed: 0 };

  const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";
  let tokens = loadTokens();
  let synced = 0;
  const remaining: QueuedRequest[] = [];

  for (const item of queue) {
    try {
      const doFetch = () =>
        fetch(`${BASE}${item.path}`, {
          method: item.method,
          headers: {
            ...(item.body !== undefined ? { "Content-Type": "application/json" } : {}),
            ...(tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
          },
          body: item.body !== undefined ? JSON.stringify(item.body) : undefined,
        });

      let resp = await doFetch();

      // P0 修复：401 时先刷新 token 重试（access 只有 15 分钟，断网 >15 分钟后必过期）
      if (resp.status === 401) {
        const newToken = await refreshTokens();
        if (newToken) {
          tokens = loadTokens(); // refreshTokens 内已更新 localStorage
          resp = await doFetch();
        } else {
          clearTokens(); // refresh 也失败：登录态彻底失效
          if (typeof window !== "undefined") window.location.replace("/login");
          return { synced, failed: remaining.length };
        }
      }

      if (resp.ok || resp.status === 409 || resp.status === 422) {
        // 409（已完成再打卡=幂等）/ 422（过期数据被拒）：视为已处理
        synced++;
      } else {
        item.retryCount++;
        if (item.retryCount < MAX_RETRIES) remaining.push(item);
        else synced++;
      }
    } catch {
      item.retryCount++;
      if (item.retryCount < MAX_RETRIES) remaining.push(item);
      else synced++;
    }
  }

  window.localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
  return { synced, failed: remaining.length };
}

/** 注册离线队列监听（在根布局调用一次）。P1 修复：加载时也补传一次。 */
export function registerOfflineQueueSync(): void {
  if (typeof window === "undefined") return;

  const sync = async () => {
    const result = await syncOfflineQueue();
    if (result.synced > 0) {
      console.info(`[offline-queue] 补传 ${result.synced} 条，剩余 ${result.failed} 条`);
    }
  };

  window.addEventListener("online", sync);
  void sync(); // 页面加载即补传（最常见恢复路径：断网打卡→关页面→重新打开）
}
