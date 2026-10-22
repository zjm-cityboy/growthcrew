"use client";

import LifePills from "@/components/LifePills";
import TaskCard from "@/components/TaskCard";
import MiniSheet from "@/components/MiniSheet";
import { api, type GoalOut, type NotificationOut, type TaskOut, type TodayOut } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import Link from "next/link";
import { useState } from "react";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 11) return "早上好 ☀️";
  if (hour < 18) return "下午好 🌤️";
  return "晚上好 🌙";
}

/** ISO 日期 → "周一 9-28" 样式（今日页空态的即将开始预览用）。 */
function formatShortDate(iso: string): string {
  const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const d = new Date(`${iso}T00:00:00`);
  return `${WEEKDAYS[d.getDay()]} ${d.getMonth() + 1}-${d.getDate()}`;
}

/** 截止日 → "距截止 N 天"徽章文案（无截止日/已过期返回空）。 */
function deadlineLabel(deadline: string | null): string {
  if (!deadline) return "";
  const days = Math.ceil((new Date(`${deadline}T00:00:00`).getTime() - Date.now()) / 86400000);
  if (days < 0) return "已过截止";
  if (days === 0) return "今天截止";
  return `距截止 ${days} 天`;
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
  const [goal, setGoal] = useState<GoalOut | null>(null);
  const [unread, setUnread] = useState<NotificationOut[]>([]);

  const load = async () => {
    try {
      // llm 用三态区分：null=请求失败（不弹引导，别把网络抖动当成没配置）
      const [t, j, llm, goals, notifications] = await Promise.all([
        api.today(),
        api.getJournal(),
        api.getLLMSettings().then(
          (s) => s !== null,
          () => null,
        ),
        api.listGoals().catch(() => []), // 目标/通知加载失败不阻塞首页
        api.listNotifications().catch(() => []),
      ]);
      setToday(t);
      setJournal(j);
      setNeedsSetup(llm === false); // 明确没配置才显示引导卡
      setGoal(goals.find((g) => g.status === "进行中") ?? goals[0] ?? null);
      setUnread(notifications.filter((n) => !n.read));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败");
    }
  };

  useLoad(load);

  async function markRead(id: number) {
    setUnread((prev) => prev.filter((n) => n.id !== id)); // 乐观移除，失败也不弹错
    await api.readNotification(id).catch(() => undefined);
  }

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
        <div className="flex items-center gap-2.5">
          <Link
            href="/settings"
            aria-label="设置"
            className="flex h-11 w-11 items-center justify-center rounded-2xl text-lg text-gc-muted active:opacity-70"
          >
            ⚙️
          </Link>
          <div className="rounded-2xl bg-gc-peach-soft px-3.5 py-2 text-center">
            <p className="text-xl font-semibold leading-none text-gc-text">{today.streak}</p>
            <p className="mt-0.5 text-[11px] text-gc-muted">连续天数</p>
          </div>
        </div>
      </header>

      {/* 我的目标 + 通知：用户最关心的两件事放最显眼处 */}
      <section className="gc-card px-5 py-4">
        {goal ? (
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] text-gc-muted">我的目标</p>
              <p className="mt-0.5 truncate text-sm font-medium text-gc-text">🎯 {goal.title}</p>
            </div>
            {deadlineLabel(goal.deadline) && (
              <span className="shrink-0 rounded-full bg-gc-accent-soft px-3 py-1.5 text-xs text-gc-text">
                {deadlineLabel(goal.deadline)}
              </span>
            )}
          </div>
        ) : (
          <Link href="/chat" className="flex items-center justify-between">
            <p className="text-sm text-gc-muted">还没有目标</p>
            <span className="text-xs text-gc-accent">创建第一个 →</span>
          </Link>
        )}
        {unread[0] && (
          <button
            onClick={() => markRead(unread[0].id)}
            className="mt-3 flex w-full items-start gap-2.5 border-t border-gc-muted/15 pt-3 text-left active:opacity-70"
          >
            <span className="shrink-0 text-sm">🔔</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-gc-text">{unread[0].title}</span>
              <span className="block truncate text-xs text-gc-muted">{unread[0].body}</span>
            </span>
            <span className="shrink-0 text-[10px] text-gc-muted">知道了</span>
          </button>
        )}
      </section>

      {/* 新用户引导：未配模型时显示醒目卡片 */}
      {needsSetup && (
        <section className="gc-card border-2 border-gc-accent px-5 py-5" style={{ borderStyle: "solid" }}>
          <p className="text-sm font-medium">🚀 欢迎使用！先花 1 分钟完成初始设置</p>
          <p className="mt-2 text-xs leading-5 text-gc-muted">
            AI 教练需要一个大模型才能工作。去设置页选服务商、粘贴密钥（免费额度就够用），
            配一次就永久生效——配好后这张卡片会自动消失。
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
          {today.tasks.length === 0 && today.upcoming.length > 0 ? (
            <div className="gc-card px-5 py-5">
              <p className="text-sm text-gc-text">今天没有安排，你的新计划马上开始 👇</p>
              <div className="mt-3 flex flex-col gap-2.5">
                {today.upcoming.map((task) => (
                  <div key={task.id} className="flex items-center gap-3 text-sm text-gc-muted">
                    <span className="w-14 shrink-0 text-xs">{formatShortDate(task.date)}</span>
                    <span className="min-w-0 flex-1 truncate">{task.title}</span>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-gc-muted">
                从{formatShortDate(today.upcoming[0].date)}开始，任务会在对应日期自动出现在这里
              </p>
            </div>
          ) : today.tasks.length === 0 ? (
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
