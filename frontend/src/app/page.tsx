"use client";

import LifePills from "@/components/LifePills";
import TaskCard from "@/components/TaskCard";
import MiniSheet from "@/components/MiniSheet";
import { api, type TaskOut, type TodayOut } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import Link from "next/link";
import { useState } from "react";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 11) return "早上好 ☀️";
  if (hour < 18) return "下午好 🌤️";
  return "晚上好 🌙";
}

export default function TodayPage() {
  const [today, setToday] = useState<TodayOut | null>(null);
  const [journal, setJournal] = useState<{
    submitted: boolean;
    mood: number | null;
    today_done: number;
    today_total: number;
  } | null>(null);
  const [journalOpen, setJournalOpen] = useState(false);
  const [journalMood, setJournalMood] = useState(3);
  const [journalNote, setJournalNote] = useState("");
  const [error, setError] = useState("");
  const [needsSetup, setNeedsSetup] = useState(false); // 新用户引导：未配模型

  const load = async () => {
    try {
      const [t, j, llm] = await Promise.all([
        api.today(),
        api.getJournal(),
        api.getLLMSettings().catch(() => null),
      ]);
      setToday(t);
      setJournal(j);
      setNeedsSetup(!llm); // 没配 BYOK → 显示引导卡
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败");
    }
  };

  useLoad(load);

  function onTaskChanged(updated: TaskOut) {
    if (!today) return;
    setToday({ ...today, tasks: today.tasks.map((t) => (t.id === updated.id ? updated : t)) });
  }

  async function submitJournal() {
    try {
      await api.submitJournal(journalMood, journalNote);
      setJournalOpen(false);
      await load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "提交失败");
    }
  }

  if (!today) {
    return <p className="mt-20 text-center text-sm text-gc-muted">{error || "加载中…"}</p>;
  }

  const todoCount = today.tasks.filter((t) => t.status === "todo").length;
  const dateLabel = new Date(`${today.date}T12:00:00`).toLocaleDateString("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <div className="flex flex-col gap-4">
      {/* 问候区 */}
      <header className="flex items-start justify-between pt-1">
        <div>
          <h1 className="text-[26px] font-medium tracking-tight">{greeting()}</h1>
          <p className="mt-1 text-sm text-gc-muted">{dateLabel}</p>
        </div>
        <div className="rounded-2xl bg-gc-peach-soft px-3.5 py-2 text-center">
          <p className="text-xl font-semibold leading-none text-gc-text">{today.streak}</p>
          <p className="mt-0.5 text-[11px] text-gc-muted">连续天数</p>
        </div>
      </header>

      {/* 新用户引导：未配模型时显示醒目卡片 */}
      {needsSetup && (
        <section className="gc-card border-2 border-gc-accent px-5 py-5" style={{ borderStyle: "solid" }}>
          <p className="text-sm font-medium">🚀 欢迎使用！先花 1 分钟完成初始设置</p>
          <p className="mt-2 text-xs leading-5 text-gc-muted">
            教练和复盘师需要一个大模型来工作。你只需配一次自己的 API 密钥（免费额度就够用），
            之后所有功能自动就绪。
          </p>
          <Link
            href="/settings"
            className="mt-4 block rounded-full bg-gc-accent py-3 text-center text-sm text-white active:scale-[0.98]"
          >
            去配置模型 →
          </Link>
        </section>
      )}

      {/* 晨间摘要 */}
      <section className="gc-card px-5 py-4">
        <p className="text-sm leading-6 text-gc-text">
          昨天 {today.yesterday.total > 0 ? `完成 ${today.yesterday.done}/${today.yesterday.total}` : "没有安排任务"}
          {today.yesterday.done < today.yesterday.total && today.yesterday.total > 0
            ? "，落下的今天补一点就好"
            : "，今天继续保持"}
        </p>
      </section>

      {/* 今日任务 */}
      <section>
        <h2 className="mb-2.5 px-1 text-sm font-medium text-gc-muted">
          今日 {today.tasks.length} 件事{todoCount < today.tasks.length ? ` · 还剩 ${todoCount}` : ""}
        </h2>
        <div className="flex flex-col gap-3">
          {today.tasks.length === 0 ? (
            <div className="gc-card px-5 py-8 text-center">
              <p className="text-sm text-gc-muted">今天还没有安排</p>
              <p className="mt-1 text-sm text-gc-muted">
                去「对话」贴入参考计划，教练帮你排进每天
              </p>
            </div>
          ) : (
            today.tasks.map((task) => (
              <TaskCard key={task.id} task={task} onChanged={onTaskChanged} onError={setError} />
            ))
          )}
        </div>
      </section>

      {/* 生活三打卡 */}
      <section>
        <h2 className="mb-2.5 px-1 text-sm font-medium text-gc-muted">生活</h2>
        <LifePills value={today.life_log} onChanged={load} onError={setError} />
      </section>

      {/* 晚间轻复盘 */}
      <section className="gc-card bg-gc-lavender px-5 py-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">晚间一分钟</p>
            <p className="mt-0.5 text-xs text-gc-muted">
              {journal?.submitted
                ? "已记录，好好休息 🌙"
                : `今天 ${journal?.today_done ?? 0}/${journal?.today_total ?? 0}，状态几分？`}
            </p>
          </div>
          {!journal?.submitted && (
            <button
              onClick={() => setJournalOpen(true)}
              className="rounded-full bg-gc-accent px-4 py-2 text-xs text-white active:scale-95"
            >
              开始
            </button>
          )}
        </div>
      </section>

      <MiniSheet open={journalOpen} title="今天状态几分？一句话感想" onClose={() => setJournalOpen(false)}>
        <div className="mb-3 grid grid-cols-5 gap-2">
          {[1, 2, 3, 4, 5].map((m) => (
            <button
              key={m}
              onClick={() => setJournalMood(m)}
              className={`rounded-2xl py-3 text-[15px] ${
                journalMood === m ? "bg-gc-accent text-white" : "bg-gc-lavender"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
        <textarea
          value={journalNote}
          onChange={(e) => setJournalNote(e.target.value)}
          placeholder="一句话就够（可选）"
          maxLength={200}
          rows={2}
          className="mb-3 w-full rounded-2xl bg-gc-bg px-4 py-3 text-sm outline-none placeholder:text-gc-muted"
        />
        <button
          onClick={submitJournal}
          className="w-full rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98]"
        >
          记下今天
        </button>
      </MiniSheet>

      {error && (
        <p className="rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-center text-xs text-gc-text">
          {error}
        </p>
      )}
    </div>
  );
}
