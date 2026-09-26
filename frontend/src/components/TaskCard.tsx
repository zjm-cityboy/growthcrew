"use client";

import { SKIP_REASONS, api, type SkipReason, type TaskOut } from "@/lib/api";
import { useState } from "react";
import MiniSheet from "./MiniSheet";

/** 任务卡：点圆圈打卡（≤2 步），跳过时一键选卡因。 */
export default function TaskCard({
  task,
  onChanged,
  onError,
}: {
  task: TaskOut;
  onChanged: (t: TaskOut) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [skipOpen, setSkipOpen] = useState(false);

  const done = task.status === "done";
  const skipped = task.status === "skipped";

  async function complete() {
    if (busy || done || skipped) return;
    setBusy(true);
    try {
      onChanged(await api.completeTask(task.id));
    } catch (exc) {
      if (exc instanceof Error && exc.message.includes("网络连接失败")) {
        // 离线：已入队补传，给用户成功反馈（PM #11：不说"失败"）
        onChanged({ ...task, status: "done" as const });
      } else {
        onError(exc instanceof Error ? exc.message : "打卡失败，请重试");
      }
    } finally {
      setBusy(false);
    }
  }

  async function skip(reason: SkipReason) {
    if (busy) return;
    setBusy(true);
    setSkipOpen(false);
    try {
      onChanged(await api.skipTask(task.id, reason));
    } catch (exc) {
      if (exc instanceof Error && exc.message.includes("网络连接失败")) {
        onChanged({ ...task, status: "skipped" as const, skip_reason: reason });
      } else {
        onError(exc instanceof Error ? exc.message : "操作失败，请重试");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="gc-card flex items-center gap-3 px-4 py-3.5">
        <button
          aria-label={done ? "已完成" : "标记完成"}
          onClick={complete}
          disabled={busy || done || skipped}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition-all ${
            done
              ? "border-gc-accent bg-gc-accent text-white"
              : skipped
                ? "border-gc-divider bg-gc-divider/40 text-gc-muted"
                : "border-gc-accent/60 active:scale-90"
          }`}
          style={{ transitionDuration: "350ms" }}
        >
          {done && <span className="text-sm">✓</span>}
          {skipped && <span className="text-xs text-gc-muted">–</span>}
        </button>
        <div className="min-w-0 flex-1">
          <p className={`truncate text-[15px] ${done ? "text-gc-muted line-through" : ""}`}>
            {task.title}
          </p>
          <p className="mt-0.5 text-xs text-gc-muted">
            {task.duration_minutes} 分钟
            {task.category_label ? ` · ${task.category_label}` : ""}
            {skipped && task.skip_reason ? ` · ${task.skip_reason}` : ""}
            {task.actual_minutes != null ? ` · 实际 ${task.actual_minutes} 分钟` : ""}
          </p>
        </div>
        {!done && !skipped && (
          <button
            onClick={() => setSkipOpen(true)}
            className="rounded-full px-2.5 py-1 text-xs text-gc-muted active:bg-gc-lavender"
          >
            跳过
          </button>
        )}
      </div>

      <MiniSheet open={skipOpen} title="跳过的原因是？（一键卡因）" onClose={() => setSkipOpen(false)}>
        <div className="grid grid-cols-2 gap-3">
          {SKIP_REASONS.map((reason) => (
            <button
              key={reason}
              onClick={() => skip(reason)}
              className="rounded-2xl bg-gc-lavender py-4 text-[15px] text-gc-text active:scale-95"
              style={{ transitionDuration: "200ms" }}
            >
              {reason}
            </button>
          ))}
        </div>
      </MiniSheet>
    </>
  );
}
