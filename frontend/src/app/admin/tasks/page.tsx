"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { useState } from "react";

/** 管理端 · 任务管理：全部用户的任务（按用户筛选），行内编辑与删除。 */

type AdminTask = {
  id: number;
  username: string;
  goal_title: string;
  date: string;
  title: string;
  duration_minutes: number;
  status: string;
  skip_reason: string | null;
};

type AdminUser = { id: number; username: string };

const TASK_STATUSES = ["todo", "done", "skipped"]; // 与后端 TaskStatus 枚举一致（英文值）

const TASK_STATUS_LABELS: Record<string, string> = {
  todo: "待办",
  done: "已完成",
  skipped: "已跳过",
};

export default function AdminTasksPage() {
  const [tasks, setTasks] = useState<AdminTask[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userFilter, setUserFilter] = useState<number | "all">("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<AdminTask | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const load = async () => {
    try {
      const [ts, us] = await Promise.all([api.adminTasks(), api.adminUsers()]);
      setTasks(ts);
      setUsers(us);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败（无管理员权限？）");
    }
  };

  useLoad(load);

  async function saveEdit() {
    if (!editing) return;
    try {
      await api.adminUpdateTask(editing.id, {
        title: editing.title,
        date: editing.date,
        duration_minutes: editing.duration_minutes,
        status: editing.status,
      });
      setNotice(`✓ 任务「${editing.title.slice(0, 20)}…」已更新`);
      setEditing(null);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    }
  }

  async function remove(t: AdminTask) {
    if (confirmId !== t.id) {
      setConfirmId(t.id);
      window.setTimeout(() => setConfirmId((cur) => (cur === t.id ? null : cur)), 4000);
      return;
    }
    setConfirmId(null);
    try {
      await api.adminDeleteTask(t.id);
      setNotice("✓ 任务已删除");
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "删除失败");
    }
  }

  const filtered = tasks
    .filter((t) => (userFilter === "all" ? true : t.username === users.find((u) => u.id === userFilter)?.username))
    .filter((t) => t.title.includes(query.trim()) || t.username.includes(query.trim()));

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">任务管理</h1>
          <p className="mt-0.5 text-xs text-gc-muted">
            共 {tasks.length} 件任务（全部用户，显示最近 100）
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value === "all" ? "all" : Number(e.target.value))}
            className="rounded-full bg-gc-card px-3 py-2 text-sm outline-none"
          >
            <option value="all">全部用户</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username}
              </option>
            ))}
          </select>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索任务或用户…"
            className="w-56 rounded-full bg-gc-card px-4 py-2 text-sm outline-none placeholder:text-gc-muted"
          />
        </div>
      </header>

      {error && <p className="rounded-xl bg-red-50 px-4 py-2.5 text-xs text-red-600">{error}</p>}
      {notice && <p className="text-xs text-gc-accent">{notice}</p>}

      <div className="gc-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gc-divider text-left text-xs text-gc-muted">
              <th className="px-4 py-3 font-normal">日期</th>
              <th className="px-4 py-3 font-normal">用户 · 目标</th>
              <th className="px-4 py-3 font-normal">任务</th>
              <th className="px-4 py-3 font-normal">时长</th>
              <th className="px-4 py-3 font-normal">状态</th>
              <th className="px-4 py-3 text-right font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) =>
              editing?.id === t.id ? (
                <tr key={t.id} className="border-b border-gc-divider/50 bg-gc-accent-soft/40">
                  <td className="px-4 py-2.5">
                    <input
                      type="date"
                      value={editing.date}
                      onChange={(e) => setEditing({ ...editing, date: e.target.value })}
                      className="rounded-lg bg-gc-card px-2 py-1 text-xs outline-none"
                    />
                  </td>
                  <td className="px-4 py-2.5 text-xs text-gc-muted">
                    {editing.username} · {editing.goal_title}
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      value={editing.title}
                      onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                      className="w-64 rounded-lg bg-gc-card px-2 py-1 text-sm outline-none"
                    />
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      type="number"
                      value={editing.duration_minutes}
                      onChange={(e) =>
                        setEditing({ ...editing, duration_minutes: Number(e.target.value) })
                      }
                      className="w-16 rounded-lg bg-gc-card px-2 py-1 text-center text-xs outline-none"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={editing.status}
                      onChange={(e) => setEditing({ ...editing, status: e.target.value })}
                      className="rounded-lg bg-gc-card px-2 py-1 text-xs outline-none"
                    >
                      {TASK_STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {TASK_STATUS_LABELS[s]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={saveEdit}
                        className="rounded-full bg-gc-accent px-3 py-1 text-xs text-white"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setEditing(null)}
                        className="rounded-full bg-gc-bg px-3 py-1 text-xs text-gc-muted"
                      >
                        取消
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={t.id} className="border-b border-gc-divider/50 last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-gc-muted">{t.date}</td>
                  <td className="px-4 py-3 text-xs">
                    <span className="font-medium">{t.username}</span>
                    <span className="ml-1 text-gc-muted">{t.goal_title}</span>
                  </td>
                  <td className="max-w-xs truncate px-4 py-3">{t.title}</td>
                  <td className="px-4 py-3 text-xs text-gc-muted">{t.duration_minutes} 分钟</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        t.status === "done"
                          ? "bg-gc-accent-soft text-gc-accent"
                          : t.status === "skipped"
                            ? "bg-red-50 text-red-600"
                            : "bg-gc-bg text-gc-muted"
                      }`}
                    >
                      {TASK_STATUS_LABELS[t.status] ?? t.status}
                      {t.skip_reason ? `·${t.skip_reason}` : ""}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={() => setEditing(t)}
                        className="rounded-full bg-gc-bg px-2.5 py-1 text-xs text-gc-muted active:opacity-70"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => remove(t)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          confirmId === t.id ? "bg-red-600 text-white" : "bg-gc-bg text-red-500"
                        }`}
                      >
                        {confirmId === t.id ? "确认删除？" : "删除"}
                      </button>
                    </div>
                  </td>
                </tr>
              ),
            )}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-xs text-gc-muted">
                  没有匹配的任务
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
