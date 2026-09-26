"use client";

import { api } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import Link from "next/link";
import { useState } from "react";

interface Report {
  id: number;
  week_start: string;
  title: string;
  content: string;
  created_at: string;
}

/** 周报列表页：档案 Tab 的子页面。 */
export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<Report | null>(null);
  const [loaded, setLoaded] = useState(false); // P2-8：区分加载中与确认为空
  const [error, setError] = useState("");

  useLoad(async () => {
    try {
      setReports(await api.listWeeklyReports());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败");
    } finally {
      setLoaded(true);
    }
  });

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center gap-3 pt-1">
        <Link href="/archive" className="text-gc-muted">
          ← 返回
        </Link>
        <h1 className="text-xl font-medium tracking-tight">成长周报</h1>
      </header>

      {error && (
        <p className="rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-xs text-gc-text">{error}</p>
      )}

      {selected ? (
        <article className="gc-card px-5 py-5">
          <h2 className="text-lg font-medium">{selected.title}</h2>
          <p className="mt-1 text-xs text-gc-muted">
            {selected.week_start} 开始的一周 · 生成于{" "}
            {new Date(selected.created_at).toLocaleDateString("zh-CN")}
          </p>
          <div className="mt-4 whitespace-pre-wrap text-sm leading-7">{selected.content}</div>
          <button
            onClick={() => setSelected(null)}
            className="mt-5 text-xs text-gc-muted underline"
          >
            ← 返回列表
          </button>
        </article>
      ) : !loaded ? (
        <div className="gc-card px-5 py-8 text-center text-sm text-gc-muted">加载中…</div>
      ) : reports.length === 0 ? (
        <div className="gc-card px-5 py-8 text-center text-sm text-gc-muted">
          还没有周报——周日晚上复盘师会自动生成
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {reports.map((r) => (
            <button
              key={r.id}
              onClick={() => setSelected(r)}
              className="gc-card px-5 py-4 text-left"
            >
              <p className="text-sm font-medium">{r.title}</p>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-gc-muted">{r.content}</p>
              <p className="mt-2 text-[11px] text-gc-muted">{r.week_start} 开始的一周</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
