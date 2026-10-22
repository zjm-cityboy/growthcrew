"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import { useState } from "react";

/** 管理端 · 记录管理：周报/每日复盘/生活打卡/通知（查+删）+ 用户模型配置（查+清）。 */

type Row = { id: number; username: string; [k: string]: unknown };

const SECTIONS = ["周报", "每日复盘", "生活打卡", "通知", "模型配置"] as const;

export default function AdminRecordsPage() {
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("周报");
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmId, setConfirmId] = useState<number | null>(null);

  async function load(target = section) {
    setError("");
    try {
      let data: Row[] = [];
      if (target === "周报") data = (await api.adminReports()) as unknown as Row[];
      else if (target === "每日复盘") data = (await api.adminJournals()) as unknown as Row[];
      else if (target === "生活打卡") data = (await api.adminLifeLogs()) as unknown as Row[];
      else if (target === "通知") data = (await api.adminNotifications()) as unknown as Row[];
      else
        data = (await api.adminLLMSettings()).map((r) => ({
          ...r,
          id: r.user_id,
        })) as unknown as Row[];
      setRows(data);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败（无管理员权限？）");
    }
  }

  useLoad(() => load());

  async function remove(row: Row) {
    if (confirmId !== row.id) {
      setConfirmId(row.id);
      window.setTimeout(() => setConfirmId((cur) => (cur === row.id ? null : cur)), 4000);
      return;
    }
    setConfirmId(null);
    try {
      if (section === "周报") await api.adminDeleteReport(row.id);
      else if (section === "每日复盘") await api.adminDeleteJournal(row.id);
      else if (section === "生活打卡") await api.adminDeleteLifeLog(row.id);
      else if (section === "通知") await api.adminDeleteNotification(row.id);
      else await api.adminClearLLMSettings(row.id);
      setNotice("✓ 已删除/清除");
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    }
  }

  // 各区块的列渲染（小而专：每类记录的关键字段）
  function cells(row: Row): string[] {
    if (section === "周报")
      return [
        String(row.week_start ?? ""),
        `${String(row.title ?? "").slice(0, 40)}`,
        `${String(row.content ?? "").slice(0, 50)}…`,
      ];
    if (section === "每日复盘")
      return [String(row.date ?? ""), `${row.mood ?? "-"} 分`, String(row.note ?? "").slice(0, 40)];
    if (section === "生活打卡")
      return [
        String(row.date ?? ""),
        row.sleep_hours != null ? `${row.sleep_hours}h 睡眠` : "睡眠未记",
        row.exercise ? "运动 ✓" : "未运动",
        row.mood != null ? `${row.mood} 分` : "-",
      ];
    if (section === "通知")
      return [String(row.type ?? ""), String(row.title ?? ""), row.read ? "已读" : "未读"];
    return [String(row.model_name ?? ""), String(row.base_url ?? ""), String(row.updated_at ?? "").slice(0, 10)];
  }

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">记录管理</h1>
        <p className="mt-0.5 text-xs text-gc-muted">
          周报 / 每日复盘 / 生活打卡 / 通知 / 用户模型配置——查与删
        </p>
      </header>

      <div className="flex gap-1.5">
        {SECTIONS.map((s) => (
          <button
            key={s}
            onClick={() => {
              setSection(s);
              setRows([]);
              void load(s);
            }}
            className={`rounded-full px-3.5 py-1.5 text-xs transition-colors ${
              section === s
                ? "bg-gc-accent text-white"
                : "bg-gc-card text-gc-muted hover:bg-gc-accent-soft"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {error && <p className="rounded-xl bg-red-50 px-4 py-2.5 text-xs text-red-600">{error}</p>}
      {notice && <p className="text-xs text-gc-accent">{notice}</p>}

      <div className="gc-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gc-divider text-left text-xs text-gc-muted">
              <th className="px-4 py-3 font-normal">用户</th>
              {(section === "周报"
                ? ["周", "标题", "内容摘要"]
                : section === "每日复盘"
                  ? ["日期", "心情", "一句话"]
                  : section === "生活打卡"
                    ? ["日期", "睡眠", "运动", "心情"]
                    : section === "通知"
                      ? ["类型", "标题", "状态"]
                      : ["模型", "服务商地址", "更新于"]
              ).map((h) => (
                <th key={h} className="px-4 py-3 font-normal">
                  {h}
                </th>
              ))}
              <th className="px-4 py-3 text-right font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-gc-divider/50 last:border-0">
                <td className="px-4 py-3 font-medium">{row.username}</td>
                {cells(row).map((c, i) => (
                  <td key={i} className="max-w-xs truncate px-4 py-3 text-xs text-gc-muted">
                    {c}
                  </td>
                ))}
                <td className="px-4 py-3">
                  <button
                    onClick={() => remove(row)}
                    className={`float-right rounded-full px-2.5 py-1 text-xs active:opacity-70 ${
                      confirmId === row.id ? "bg-red-600 text-white" : "bg-gc-bg text-red-500"
                    }`}
                  >
                    {confirmId === row.id
                      ? "确认？"
                      : section === "模型配置"
                        ? "清除配置"
                        : "删除"}
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && !error && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-xs text-gc-muted">
                  暂无{section}记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
