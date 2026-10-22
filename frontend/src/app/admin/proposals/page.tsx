"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { useState } from "react";

/** 管理端 · 提案审计：全部用户的计划提案（状态/拒绝原因/摘要），按状态筛选。 */

type AdminProposal = {
  id: number;
  username: string;
  goal_title: string;
  status: string;
  rejection_reason: string | null;
  created_at: string;
  summary: string;
};

const STATUS_FILTERS = ["全部", "待审批", "已同意", "已拒绝"];

export default function AdminProposalsPage() {
  const [proposals, setProposals] = useState<AdminProposal[]>([]);
  const [filter, setFilter] = useState("全部");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState<{ id: number; action: string } | null>(null);

  const load = async () => {
    try {
      setProposals(await api.adminProposals());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败（无管理员权限？）");
    }
  };

  useLoad(load);

  // 代批/代拒两步确认
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

  async function decide(id: number, approve: boolean) {
    if (!arm(id, approve ? "approve" : "reject")) return;
    try {
      const out = approve
        ? await api.adminApproveProposal(id)
        : await api.adminRejectProposal(id, "管理员代拒");
      setNotice(`✓ ${out.message}`);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    }
  }

  const filtered =
    filter === "全部" ? proposals : proposals.filter((p) => p.status === filter);

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">提案审计</h1>
          <p className="mt-0.5 text-xs text-gc-muted">
            全部用户的计划提案——看得到每个计划的来龙去脉与拒绝原因
          </p>
        </div>
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`rounded-full px-3 py-1.5 text-xs transition-colors ${
                filter === s
                  ? "bg-gc-accent text-white"
                  : "bg-gc-card text-gc-muted hover:bg-gc-accent-soft"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <p className="rounded-xl bg-red-50 px-4 py-2.5 text-xs text-red-600">{error}</p>
      )}
      {notice && <p className="text-xs text-gc-accent">{notice}</p>}

      <div className="gc-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gc-divider text-left text-xs text-gc-muted">
              <th className="px-4 py-3 font-normal">时间</th>
              <th className="px-4 py-3 font-normal">用户 · 目标</th>
              <th className="px-4 py-3 font-normal">状态</th>
              <th className="px-4 py-3 font-normal">拒绝原因</th>
              <th className="px-4 py-3 font-normal">摘要</th>
              <th className="px-4 py-3 text-right font-normal">管理操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.id} className="border-b border-gc-divider/50 last:border-0">
                <td className="whitespace-nowrap px-4 py-3 text-xs text-gc-muted">
                  {p.created_at.slice(5, 16).replace("T", " ")}
                </td>
                <td className="px-4 py-3">
                  <span className="font-medium">{p.username}</span>
                  <span className="ml-1.5 text-xs text-gc-muted">{p.goal_title}</span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      p.status === "已同意"
                        ? "bg-gc-accent-soft text-gc-accent"
                        : p.status === "已拒绝"
                          ? "bg-red-50 text-red-600"
                          : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {p.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gc-muted">
                  {p.rejection_reason ?? "—"}
                </td>
                <td className="max-w-xs truncate px-4 py-3 text-xs text-gc-muted">
                  {p.summary || "—"}
                </td>
                <td className="px-4 py-3">
                  {p.status === "待审批" ? (
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={() => decide(p.id, true)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          confirming?.id === p.id && confirming.action === "approve"
                            ? "bg-gc-accent text-white"
                            : "bg-gc-accent-soft text-gc-accent"
                        }`}
                      >
                        {confirming?.id === p.id && confirming.action === "approve"
                          ? "确认代批？"
                          : "代批"}
                      </button>
                      <button
                        onClick={() => decide(p.id, false)}
                        className={`rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                          confirming?.id === p.id && confirming.action === "reject"
                            ? "bg-red-600 text-white"
                            : "bg-gc-bg text-red-500"
                        }`}
                      >
                        {confirming?.id === p.id && confirming.action === "reject"
                          ? "确认代拒？"
                          : "代拒"}
                      </button>
                    </div>
                  ) : (
                    <span className="float-right text-xs text-gc-muted">已决</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-xs text-gc-muted">
                  {filter === "全部" ? "暂无提案" : `没有「${filter}」的提案`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
