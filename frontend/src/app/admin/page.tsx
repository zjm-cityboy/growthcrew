"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { useState } from "react";

/** 管理端 · 系统总览：全系统统计 + 全库备份。 */

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [backing, setBacking] = useState(false);

  const load = async () => {
    try {
      setOverview(await api.adminOverview());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败（无管理员权限？）");
    }
  };

  useLoad(load);

  async function downloadBackup() {
    setBacking(true);
    try {
      const blob = await api.adminBackup();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `growthcrew-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setNotice("✓ 备份已下载（密码哈希/模型密钥/推送端点不包含在内）");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "备份失败");
    } finally {
      setBacking(false);
    }
  }

  if (error && !overview) {
    return (
      <div className="gc-card mx-auto mt-20 w-full max-w-sm px-6 py-10 text-center">
        <p className="text-2xl">🔒</p>
        <p className="mt-2 text-sm text-gc-muted">{error}</p>
        <p className="mt-1 text-xs text-gc-muted">
          管理员身份由部署者在 backend/.env 的 GC_ADMIN_USERNAMES 中指定
        </p>
      </div>
    );
  }

  const cards = [
    { label: "用户", value: overview?.users, icon: "👥" },
    { label: "目标", value: overview?.goals, icon: "🎯" },
    { label: "任务总数", value: overview?.tasks_total, icon: "📋" },
    { label: "已完成", value: overview?.tasks_done, icon: "✅" },
    { label: "计划提案", value: overview?.proposals, icon: "📝" },
    { label: "周报", value: overview?.reports, icon: "📊" },
    { label: "每日复盘", value: overview?.journals, icon: "🌙" },
    { label: "生活打卡", value: overview?.life_logs, icon: "😴" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">系统总览</h1>
          <p className="mt-0.5 text-xs text-gc-muted">部署者视角：全系统数据一览</p>
        </div>
        <button
          onClick={downloadBackup}
          disabled={backing}
          className="rounded-full bg-gc-accent px-4 py-2 text-xs text-white active:opacity-70 disabled:opacity-50"
        >
          {backing ? "生成中…" : "⬇ 全库备份"}
        </button>
      </header>

      {notice && <p className="text-xs text-gc-accent">{notice}</p>}

      <div className="grid grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="gc-card px-4 py-4">
            <p className="text-xs text-gc-muted">
              {c.icon} {c.label}
            </p>
            <p className="mt-1 text-2xl font-semibold">{c.value ?? "-"}</p>
          </div>
        ))}
      </div>

      <div className="gc-card px-5 py-4 text-xs leading-6 text-gc-muted">
        <p className="text-sm font-medium text-gc-text">常用入口</p>
        <p>· 用户管理：搜索、禁用/启用账号、重置密码、清空数据、删除用户</p>
        <p>· 提案审计：全部用户的计划提案与拒绝原因</p>
        <p>· 备份：下载全库 JSON（敏感字段不导出）</p>
      </div>
    </div>
  );
}
