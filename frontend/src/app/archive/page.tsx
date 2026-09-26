"use client";

import ChartCard from "@/components/ChartCard";
import { api, loadTokens, type GoalOut, type NotificationOut } from "@/lib/api";
import { chartColors } from "@/lib/chartTheme";
import { useLoad } from "@/lib/useLoad";
import Link from "next/link";
import { useCallback, useState } from "react";

/** 档案 Tab：streak + 四图 + 周报列表 + 目标 + 通知（P2.4 完整版）。 */

// ---------- 模块级常量 loader（P1-2：稳定引用防重复请求） ----------

const loadHeatmap = () => api.listStatsHeatmap(8);
const loadTrends = () => api.listStatsTrends(8);
const loadSkipReasons = () => api.listStatsSkipReasons(90);
const loadHours = () => api.listStatsHours(90);

// ---------- 图表构建 ----------

/** P1-1 修复：按日期自身星期算列号 + 补缺失日（后端只返回有任务的天） */
function heatmapOption(data: unknown): Record<string, unknown> {
  const payload = data as { days: { date: string; done: number; total: number }[] };
  const byDate = new Map(payload.days.map((d) => [d.date, d]));

  // 计算完整日期范围并补洞
  const sorted = [...payload.days].sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return { xAxis: { show: false }, yAxis: { show: false }, series: [] };

  const start = new Date(`${sorted[0].date}T12:00:00`);
  const end = new Date(`${sorted[sorted.length - 1].date}T12:00:00`);
  const allDays: { date: string; rate: number }[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    const iso = cursor.toISOString().slice(0, 10);
    const day = byDate.get(iso);
    allDays.push({
      date: iso,
      rate: day && day.total > 0 ? day.done / day.total : -1,
    });
    cursor.setDate(cursor.getDate() + 1);
  }

  // 按日期自身星期分列（周一=0...周日=6）
  const weeks: { date: string; rate: number }[][] = [];
  let currentWeek: { date: string; rate: number }[] = [];
  let expectedCol = 0; // 下一格应放的列号
  for (const day of allDays) {
    const jsDay = new Date(`${day.date}T12:00:00`).getDay();
    const col = jsDay === 0 ? 6 : jsDay - 1; // 周日(0)→第6列
    // 补前导空格
    while (expectedCol < col) {
      currentWeek.push({ date: "", rate: -1 });
      expectedCol++;
    }
    currentWeek.push(day);
    expectedCol++;
    if (expectedCol === 7) {
      weeks.push(currentWeek);
      currentWeek = [];
      expectedCol = 0;
    }
  }
  if (currentWeek.length > 0) weeks.push(currentWeek);

  const c = chartColors();
  return {
    grid: { left: 8, right: 8, top: 8, bottom: 8 },
    xAxis: { type: "category", data: ["一", "二", "三", "四", "五", "六", "日"], show: false },
    yAxis: { type: "category", data: weeks.map((_, i) => `${i + 1}`), show: false },
    visualMap: { min: 0, max: 1, show: false, inRange: { color: [c.divider, c.accentSoft, c.accent] } },
    series: [
      {
        type: "heatmap",
        data: weeks.flatMap((week, wi) =>
          week.map((cell, di) => [di, wi, cell.rate === -1 ? -1 : cell.rate]),
        ),
        label: { show: false },
        itemStyle: { borderRadius: 4, borderColor: c.bg, borderWidth: 2 },
        tooltip: {
          formatter: (p: { data: [number, number, number] }) => {
            const [, wi, rate] = p.data;
            const cell = weeks[wi]?.[p.data[0]];
            if (!cell || !cell.date) return "";
            return `${cell.date}<br/>完成率 ${Math.round(rate * 100)}%`;
          },
        },
      },
    ],
  };
}

function trendsOption(data: unknown): Record<string, unknown> {
  const c = chartColors();
  const weeks = (data as { weeks: { week_start: string; rate: number }[] }).weeks;
  return {
    grid: { left: 40, right: 16, top: 16, bottom: 24 },
    xAxis: {
      type: "category",
      data: weeks.map((w) => w.week_start.slice(5)),
      axisLabel: { color: c.muted, fontSize: 10 },
    },
    yAxis: { type: "value", max: 100, axisLabel: { color: c.muted, fontSize: 10 } },
    series: [
      {
        type: "bar",
        data: weeks.map((w) => w.rate),
        itemStyle: { color: c.accent, borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 28,
      },
    ],
  };
}

function skipReasonsOption(data: unknown): Record<string, unknown> {
  const c = chartColors();
  const items = (data as { items: { reason: string; count: number; pct: number }[] }).items;
  return {
    grid: { left: 60, right: 40, top: 8, bottom: 8 },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      data: items.map((i) => i.reason).reverse(),
      axisLabel: { color: c.muted, fontSize: 12 },
    },
    series: [
      {
        type: "bar",
        data: items.map((i) => i.pct).reverse(),
        itemStyle: { color: c.peach, borderRadius: [0, 4, 4, 0] },
        barMaxWidth: 20,
        label: { show: true, position: "right", formatter: "{c}%", color: c.muted, fontSize: 10 },
      },
    ],
  };
}

function hoursOption(data: unknown): Record<string, unknown> {
  const c = chartColors();
  const payload = data as { completion_hours: number[]; skip_hours: number[] };
  const hours = Array.from({ length: 24 }, (_, i) => `${i}`);
  return {
    grid: { left: 40, right: 16, top: 24, bottom: 24 },
    xAxis: { type: "category", data: hours, axisLabel: { color: c.muted, fontSize: 8 } },
    yAxis: { type: "value", axisLabel: { color: c.muted, fontSize: 10 } },
    series: [
      {
        name: "完成",
        type: "bar",
        data: payload.completion_hours,
        itemStyle: { color: c.accent, borderRadius: [2, 2, 0, 0] },
        barMaxWidth: 10,
      },
      {
        name: "跳过",
        type: "bar",
        data: payload.skip_hours,
        itemStyle: { color: c.peach, borderRadius: [2, 2, 0, 0] },
        barMaxWidth: 10,
      },
    ],
    legend: { top: 0, textStyle: { color: c.muted, fontSize: 10 } },
  };
}

// ---------- 页面 ----------

export default function ArchivePage() {
  const [streak, setStreak] = useState(0);
  const [goals, setGoals] = useState<GoalOut[]>([]);
  const [notifications, setNotifications] = useState<NotificationOut[]>([]);
  const [reports, setReports] = useState<
    { id: number; week_start: string; title: string; content: string }[]
  >([]);
  const [loaded, setLoaded] = useState(false); // P2-8：区分加载中与确认为空
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [today, goalList, notificationList, reportList] = await Promise.all([
        api.today(),
        api.listGoals(),
        api.listNotifications(),
        api.listWeeklyReports().catch(() => []),
      ]);
      setStreak(today.streak);
      setGoals(goalList);
      setNotifications(notificationList);
      setReports(reportList);
      setLoaded(true);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败");
      setLoaded(true);
    }
  }, []);

  useLoad(load);

  async function read(id: number) {
    try {
      await api.readNotification(id);
      await load();
    } catch {
      /* 已读失败不打断浏览 */
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="pt-1">
        <h1 className="text-[26px] font-medium tracking-tight">成长档案</h1>
      </header>

      {/* streak */}
      <section className="gc-card flex items-center gap-4 px-5 py-4">
        <div className="rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-center">
          <p className="text-2xl font-semibold leading-none">{streak}</p>
          <p className="mt-1 text-[11px] text-gc-muted">连续天数</p>
        </div>
        <p className="text-sm leading-6 text-gc-muted">
          断了不打断、不惩罚——
          <br />
          每一次记录都在帮你归因。
        </p>
      </section>

      {/* 周报 */}
      <section>
        <div className="mb-2.5 flex items-center justify-between px-1">
          <h2 className="text-sm font-medium text-gc-muted">本周周报</h2>
          {reports.length > 0 && (
            <Link href="/archive/reports" className="text-xs text-gc-accent underline">
              查看全部 →
            </Link>
          )}
        </div>
        {!loaded ? (
          <div className="gc-card px-5 py-6 text-center text-sm text-gc-muted">加载中…</div>
        ) : reports.length === 0 ? (
          <div className="gc-card px-5 py-6 text-center text-sm text-gc-muted">
            还没有周报——周日晚上复盘师会自动生成，或
            <Link href="/settings" className="mx-1 underline">
              配好模型
            </Link>
            后手动触发
          </div>
        ) : (
          reports.slice(0, 1).map((r) => (
            <Link key={r.id} href="/archive/reports" className="gc-card block px-5 py-4">
              <p className="text-sm font-medium">{r.title}</p>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-gc-muted">{r.content}</p>
            </Link>
          ))
        )}
      </section>

      {/* 四图（loader 为模块级常量，稳定引用） */}
      <ChartCard title="打卡热力图（近 8 周）" loader={loadHeatmap} buildOption={heatmapOption} height={160} />
      <ChartCard title="完成率趋势（近 8 周）" loader={loadTrends} buildOption={trendsOption} height={180} />
      <ChartCard title="跳过的原因（近 90 天）" loader={loadSkipReasons} buildOption={skipReasonsOption} height={160} />
      <ChartCard title="你的高效时段（近 90 天）" loader={loadHours} buildOption={hoursOption} height={180} />

      {/* 目标 */}
      <section>
        <h2 className="mb-2.5 px-1 text-sm font-medium text-gc-muted">我的目标</h2>
        <div className="flex flex-col gap-3">
          {!loaded ? (
            <div className="gc-card px-5 py-6 text-center text-sm text-gc-muted">加载中…</div>
          ) : goals.length === 0 ? (
            <div className="gc-card px-5 py-6 text-center text-sm text-gc-muted">
              还没有目标，去「对话」创建第一个
            </div>
          ) : (
            goals.map((goal) => (
              <div key={goal.id} className="gc-card flex items-center justify-between px-5 py-4">
                <div className="min-w-0">
                  <p className="truncate text-[15px]">{goal.title}</p>
                  <p className="mt-0.5 text-xs text-gc-muted">
                    {goal.category}
                    {goal.deadline ? ` · 截止 ${goal.deadline.slice(0, 10)}` : ""}
                    {goal.weekly_hours ? ` · 每周 ${goal.weekly_hours}h` : ""}
                  </p>
                </div>
                <span className="ml-3 shrink-0 rounded-full bg-gc-accent-soft px-3 py-1 text-xs text-gc-accent">
                  {goal.status}
                </span>
              </div>
            ))
          )}
        </div>
      </section>

      {/* 通知 */}
      <section>
        <h2 className="mb-2.5 px-1 text-sm font-medium text-gc-muted">通知</h2>
        <div className="flex flex-col gap-2.5">
          {!loaded ? (
            <div className="gc-card px-5 py-6 text-center text-sm text-gc-muted">加载中…</div>
          ) : notifications.length === 0 ? (
            <div className="gc-card px-5 py-6 text-center text-sm text-gc-muted">暂无通知</div>
          ) : (
            notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => !n.read && read(n.id)}
                className={`gc-card px-5 py-3.5 text-left ${n.read ? "opacity-60" : ""}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium">
                    {!n.read && (
                      <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-gc-accent align-middle" />
                    )}
                    {n.title}
                  </p>
                  <span className="shrink-0 text-[11px] text-gc-muted">
                    {new Date(n.created_at).toLocaleDateString("zh-CN", {
                      month: "numeric",
                      day: "numeric",
                    })}
                  </span>
                </div>
                {n.body && (
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-gc-muted">{n.body}</p>
                )}
              </button>
            ))
          )}
        </div>
      </section>

      <Link href="/settings" className="mt-1 px-1 text-xs text-gc-muted underline">
        模型与推送设置 →
      </Link>

      {/* 数据导出（数据主权承诺） */}
      <a
        href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1"}/export/csv`}
        className="px-1 text-xs text-gc-muted underline"
        onClick={(e) => {
          e.preventDefault();
          const tokens = loadTokens();
          if (!tokens) return;
          const url = `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1"}/export/csv`;
          fetch(url, { headers: { Authorization: `Bearer ${tokens.access_token}` } })
            .then((resp) => {
              if (!resp.ok) throw new Error(`导出失败（${resp.status}）`);
              return resp.blob();
            })
            .then((blob) => {
              const link = document.createElement("a");
              link.href = URL.createObjectURL(blob);
              link.download = "growthcrew_export.csv";
              link.click();
              URL.revokeObjectURL(link.href);
            })
            .catch((err) => {
              setError(err instanceof Error ? err.message : "导出失败");
            });
        }}
      >
        导出全部数据（CSV） ↓
      </a>

      {error && (
        <p className="rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-center text-xs text-gc-text">
          {error}
        </p>
      )}
    </div>
  );
}
