"use client";

import { api } from "@/lib/api";
import { useState } from "react";
import MiniSheet from "./MiniSheet";

type LifeLog = {
  sleep_hours: number | null;
  exercise: boolean;
  mood: number | null;
} | null;

const SLEEP_OPTIONS = [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5];

/** 生活三打卡：😴睡眠 / 🏃运动 / 😊心情，各一次点击（睡眠与心情用小抽屉选值）。 */
export default function LifePills({
  value,
  onChanged,
  onError,
}: {
  value: LifeLog;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [sheet, setSheet] = useState<"sleep" | "mood" | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(payload: { sleep_hours?: number; exercise?: boolean; mood?: number }) {
    if (busy) return;
    setBusy(true);
    try {
      await api.saveLifeLog(payload);
      onChanged();
    } catch (exc) {
      onError(exc instanceof Error ? exc.message : "保存失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  const sleepSet = value?.sleep_hours != null;
  const moodSet = value?.mood != null;

  return (
    <>
      <div className="grid grid-cols-3 gap-3">
        <button
          onClick={() => setSheet("sleep")}
          className={`rounded-full py-3 text-sm transition-colors ${
            sleepSet ? "bg-gc-lavender text-gc-text" : "border border-gc-divider text-gc-muted"
          }`}
        >
          😴 {sleepSet ? `${value!.sleep_hours}h` : "睡眠"}
        </button>
        <button
          onClick={() => save({ exercise: !value?.exercise })}
          className={`rounded-full py-3 text-sm transition-colors ${
            value?.exercise ? "bg-gc-accent-soft text-gc-text" : "border border-gc-divider text-gc-muted"
          }`}
        >
          🏃 {value?.exercise ? "已运动" : "运动"}
        </button>
        <button
          onClick={() => setSheet("mood")}
          className={`rounded-full py-3 text-sm transition-colors ${
            moodSet ? "bg-gc-peach-soft text-gc-text" : "border border-gc-divider text-gc-muted"
          }`}
        >
          😊 {moodSet ? `${value!.mood}分` : "心情"}
        </button>
      </div>

      <MiniSheet open={sheet === "sleep"} title="昨晚睡了多久？" onClose={() => setSheet(null)}>
        <div className="grid grid-cols-3 gap-3">
          {SLEEP_OPTIONS.map((h) => (
            <button
              key={h}
              onClick={async () => {
                await save({ sleep_hours: h });
                setSheet(null);
              }}
              className="rounded-2xl bg-gc-lavender py-3.5 text-[15px]"
            >
              {h} 小时
            </button>
          ))}
        </div>
      </MiniSheet>

      <MiniSheet open={sheet === "mood"} title="今天状态几分？" onClose={() => setSheet(null)}>
        <div className="grid grid-cols-5 gap-2">
          {[1, 2, 3, 4, 5].map((m) => (
            <button
              key={m}
              onClick={async () => {
                await save({ mood: m });
                setSheet(null);
              }}
              className="rounded-2xl bg-gc-peach-soft py-3.5 text-[15px]"
            >
              {m}
            </button>
          ))}
        </div>
      </MiniSheet>
    </>
  );
}
