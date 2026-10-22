"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { useState } from "react";

/** 管理端 · 目标管理：全部用户的目标，行内编辑（标题/截止/每周时长/状态）与删除。 */

type AdminGoal = {
  id: number;
  username: string;
  title: string;
  category: string;
  status: string;
  deadline: string | null;
  weekly_hours: number | null;
};

const GOAL_STATUSES = ["进行中", "已归档", "已完成"];

export default function AdminGoalsPage() {
  const [goals, setGoals] = useState<AdminGoal[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<AdminGoal | null>(null); // 行内编辑中的目标
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const load = async () => {
    try {
      setGoals(await api.adminGoals());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败（无管理员权限？）");
    }
  };

  useLoad(load);

  async function saveEdit() {
    if (!editing) return;
    try {
      await api.adminUpdateGoal(editing.id, {
        title: editing.title,
        deadline: editing.deadline ?? undefined,
        weekly_hours: editing.weekly_hours ?? undefined,
        status: editing.status,
      });
      setNotice(`✓ 目标「${editing.title}」已更新`);
      setEditing(null);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    }
  }

  async function remove(g: AdminGoal) {
    if (confirmId !== g.id) {
      setConfirmId(g.id);
      window.setTimeout(() => setConfirmId((cur) => (cur === g.id ? null : cur)), 4000);
      return;
    }
    setConfirmId(null);
    try {
      await api.adminDeleteGoal(g.id);
      setNotice(`✓ 目标「${g.title}」及其计划任务已删除`);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "删除失败");
    }
  }

  const filtered = goals.filter(
    (g) =>
      g.username.toLowerCase().includes(query.trim().toLowerCase()) ||
      g.title.includes(query.trim()),
  );

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">目标管理</h1>
          <p className="mt-0.5 text-xs text-gc-muted">共 {goals.length} 个目标（全部用户）</p>
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索用户或目标名…"
          className="w-64 rounded-full bg-gc-card px-4 py-2 text-sm outline-none placeholder:text-gc-muted"
        />
      </header>

      {error && <p className="rounded-xl bg-red-50 px-4 py-2.5 text-xs text-red-600">{error}</p>}
      {notice && <p className="text-xs text-gc-accent">{notice}</p>}

      <div className="gc-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gc-divider text-left text-xs text-gc-muted">
              <th className="px-4 py-3 font-normal">用户 · 目标</th>
              <th className="px-4 py-3 font-normal">分类</th>
              <th className="px-4 py-3 font-normal">状态</th>
              <th className="px-4 py-3 font-normal">截止</th>
              <th className="px-4 py-3 font-normal">每周时长</th>
              <th className="px-4 py-3 text-right font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((g) =>
              editing?.id === g.id ? (
                <tr key={g.id} className="border-b border-gc-divider/50 bg-gc-accent-soft/40">
                  <td className="px-4 py-2.5">
                    <p className="text-xs text-gc-muted">{editing.username}</p>
                    <input
                      value={editing.title}
                      onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                      className="mt-1 w-48 rounded-lg bg-gc-card px-2 py-1 text-sm outline-none"
                    />
                  </td>
                  <td className="px-4 py-2.5 text-xs text-gc-muted">{g.category}</td>
                  <td className="px-4 py-2.5">
                    <select
                      value={editing.status}
                      onChange={(e) => setEditing({ ...editing, status: e.target.value })}
                      className="rounded-lg bg-gc-card px-2 py-1 text-xs outline-none"
                    >
                      {GOAL_STATUSES.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      type="date"
                      value={editing.deadline ?? ""}
                      onChange={(e) => setEditing({ ...editing, deadline: e.target.value })}
                      className="rounded-lg bg-gc-card px-2 py-1 text-xs outline-none"
                    />
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      type="number"
                      value={editing.weekly_hours ?? ""}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          weekly_hours: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                      className="w-16 rounded-lg bg-gc-card px-2 py-1 text-center text-xs outline-none"
                    />
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
                <tr key={g.id} className="border-b border-gc-divider/50 last:border-0">
                  <td className="px-4 py-3">
                    <span className="font-medium">{g.username}</span>
                    <span className="ml-1.5">{g.title}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gc-muted">{g.category}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        g.status === "进行中"
                          ? "bg-gc-accent-soft text-gc-accent"
                          : "bg-gc-bg text-gc-muted"
                      }`}
                    >
                      {g.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gc-muted">{g.deadline ?? "—"}</td>
                  <td className="px-4 py-3 text-xs text-gc-muted">
                    {g.weekly_hours ? `${g.weekly_hours}h` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={() => setEditing(g)}
                        className="rounded-full bg-gc-bg px-2.5 py-1 text-xs text-gc-muted active:opacity-70"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => remove(g)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          confirmId === g.id ? "bg-red-600 text-white" : "bg-gc-bg text-red-500"
                        }`}
                      >
                        {confirmId === g.id ? "确认删除？" : "删除"}
                      </button>
                    </div>
                  </td>
                </tr>
              ),
            )}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-xs text-gc-muted">
                  没有匹配的目标
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
