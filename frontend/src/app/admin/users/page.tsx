"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { useState } from "react";

/** 管理端 · 用户管理：表格 + 搜索 + 管理操作（禁用/重置密码/清空/删除）。 */

type AdminUser = {
  id: number;
  username: string;
  created_at: string;
  is_active: boolean;
  goals: number;
  active_goals: number;
  tasks_total: number;
  tasks_done: number;
  llm_configured: boolean;
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tempPassword, setTempPassword] = useState<{ username: string; password: string } | null>(
    null,
  );
  const [confirming, setConfirming] = useState<{ id: number; action: string } | null>(null);
  const [creating, setCreating] = useState(false); // 新增账号表单展开
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const load = async () => {
    try {
      setUsers(await api.adminUsers());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败（无管理员权限？）");
    }
  };

  useLoad(load);

  async function createUser() {
    if (!newUsername.trim() || newPassword.trim().length < 8) {
      setError("用户名必填，密码至少 8 位");
      return;
    }
    try {
      const out = await api.adminCreateUser(newUsername.trim(), newPassword.trim());
      setNotice(`✓ ${out.message}——请把密码转告用户`);
      setCreating(false);
      setNewUsername("");
      setNewPassword("");
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "创建失败");
    }
  }

  // 危险操作两步确认（项目禁用 window.confirm）：第一次点亮，再点执行
  function arm(id: number, action: string): boolean {
    if (confirming?.id !== id || confirming.action !== action) {
      setConfirming({ id, action });
      window.setTimeout(
        () => setConfirming((cur) => (cur?.id === id && cur.action === action ? null : cur)),
        4000,
      );
      return false;
    }
    setConfirming(null);
    return true;
  }

  async function toggleActive(u: AdminUser) {
    if (!arm(u.id, "toggle")) return;
    try {
      const out = await api.adminSetUserActive(u.id, !u.is_active);
      setNotice(`✓ ${out.message}`);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    }
  }

  async function resetPassword(u: AdminUser) {
    if (!arm(u.id, "password")) return;
    try {
      const out = await api.adminResetUserPassword(u.id);
      setTempPassword({ username: out.username, password: out.temp_password });
      setNotice(`✓ ${out.message}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    }
  }

  async function resetHistory(u: AdminUser) {
    if (!arm(u.id, "reset")) return;
    try {
      const out = await api.adminResetUser(u.id);
      setNotice(`✓ ${out.message}（清掉 ${out.removed_tasks} 件任务）`);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    }
  }

  async function deleteUser(u: AdminUser) {
    if (!arm(u.id, "delete")) return;
    try {
      const out = await api.adminDeleteUser(u.id);
      setNotice(`✓ ${out.message}`);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    }
  }

  const filtered = users.filter((u) =>
    u.username.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">用户管理</h1>
          <p className="mt-0.5 text-xs text-gc-muted">共 {users.length} 个账号</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCreating(!creating)}
            className="rounded-full bg-gc-accent px-4 py-2 text-xs text-white active:opacity-70"
          >
            {creating ? "收起" : "＋ 新增账号"}
          </button>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索用户名…"
            className="w-56 rounded-full bg-gc-card px-4 py-2 text-sm outline-none placeholder:text-gc-muted"
          />
        </div>
      </header>

      {creating && (
        <div className="gc-card flex flex-wrap items-center gap-3 px-5 py-4">
          <input
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            placeholder="用户名"
            className="w-40 rounded-full bg-gc-bg px-4 py-2 text-sm outline-none"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="初始密码（至少 8 位，创建后转告用户）"
            className="w-64 rounded-full bg-gc-bg px-4 py-2 text-sm outline-none"
          />
          <button
            onClick={createUser}
            className="rounded-full bg-gc-accent px-5 py-2 text-xs text-white"
          >
            创建
          </button>
        </div>
      )}

      {error && (
        <p className="rounded-xl bg-red-50 px-4 py-2.5 text-xs text-red-600">{error}</p>
      )}
      {notice && <p className="text-xs text-gc-accent">{notice}</p>}
      {tempPassword && (
        <div className="rounded-xl bg-gc-accent-soft px-4 py-3 text-sm">
          <p className="font-medium">
            {tempPassword.username} 的临时密码：
            <code className="ml-2 rounded bg-gc-card px-2 py-0.5 font-mono">
              {tempPassword.password}
            </code>
          </p>
          <p className="mt-1 text-xs text-gc-muted">
            仅此一次可见，请立即复制转告用户（关闭提示后无法再查）
          </p>
          <button
            onClick={() => setTempPassword(null)}
            className="mt-2 text-xs text-gc-muted underline"
          >
            我已转告，关闭
          </button>
        </div>
      )}

      <div className="gc-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gc-divider text-left text-xs text-gc-muted">
              <th className="px-4 py-3 font-normal">用户</th>
              <th className="px-4 py-3 font-normal">状态</th>
              <th className="px-4 py-3 font-normal">目标</th>
              <th className="px-4 py-3 font-normal">任务</th>
              <th className="px-4 py-3 font-normal">模型</th>
              <th className="px-4 py-3 font-normal">注册</th>
              <th className="px-4 py-3 text-right font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => {
              const armed = (action: string) =>
                confirming?.id === u.id && confirming.action === action;
              return (
                <tr key={u.id} className="border-b border-gc-divider/50 last:border-0">
                  <td className="px-4 py-3 font-medium">{u.username}</td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="rounded-full bg-gc-accent-soft px-2 py-0.5 text-xs text-gc-accent">
                        正常
                      </span>
                    ) : (
                      <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-600">
                        已禁用
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gc-muted">
                    {u.goals}（进行中 {u.active_goals}）
                  </td>
                  <td className="px-4 py-3 text-gc-muted">
                    {u.tasks_done}/{u.tasks_total}
                  </td>
                  <td className="px-4 py-3 text-gc-muted">{u.llm_configured ? "✓" : "—"}</td>
                  <td className="px-4 py-3 text-xs text-gc-muted">{u.created_at.slice(0, 10)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={() => toggleActive(u)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          armed("toggle")
                            ? "bg-red-100 text-red-600"
                            : "bg-gc-bg text-gc-muted"
                        }`}
                      >
                        {armed("toggle")
                          ? "确认？"
                          : u.is_active
                            ? "禁用"
                            : "启用"}
                      </button>
                      <button
                        onClick={() => resetPassword(u)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          armed("password")
                            ? "bg-gc-accent-soft text-gc-text"
                            : "bg-gc-bg text-gc-muted"
                        }`}
                      >
                        {armed("password") ? "确认？" : "重置密码"}
                      </button>
                      <button
                        onClick={() => resetHistory(u)}
                        disabled={u.tasks_total === 0}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 disabled:opacity-40 ${
                          armed("reset")
                            ? "bg-red-100 text-red-600"
                            : "bg-gc-bg text-gc-muted"
                        }`}
                      >
                        {armed("reset") ? "确认？" : "清空数据"}
                      </button>
                      <button
                        onClick={() => deleteUser(u)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          armed("delete")
                            ? "bg-red-600 text-white"
                            : "bg-gc-bg text-red-500"
                        }`}
                      >
                        {armed("delete") ? "确认删除？" : "删除"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-xs text-gc-muted">
                  没有匹配的用户
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
