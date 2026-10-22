"use client";

import {
  ApiError,
  PROPOSAL_STATUS,
  api,
  importPlanStream,
  type GoalOut,
  type ImportOut,
  type PlanStreamEvent,
  type ProposalOut,
} from "@/lib/api";
import MiniSheet from "@/components/MiniSheet";
import { useLoad } from "@/lib/useLoad";
import Link from "next/link";
import { useEffect, useState } from "react";

/** 对话 Tab（P1.4 形态）：计划导入对齐 + 提案审批卡；P2 接入总编自由对话。 */

type TimelineItem = {
  text: string;
  state: "done" | "run" | "err" | "thought";
  role?: string; // 事件归属角色（目前 coach=教练；架构上支持复盘师等接入）
};

const ROLE_LABELS: Record<string, string> = {
  coach: "教练",
};

const TOOL_LABELS: Record<string, string> = {
  get_goal_context: "查看目标详情",
  schedule_week: "计算一周排程",
  submit_proposal: "整理并提交提案",
  get_hour_patterns: "查看历史时段规律",
};

/** 后端过程事件 → 时间线条目（角色叙事：教练在干什么、为什么这么调整）。 */
function eventToItem(ev: PlanStreamEvent): TimelineItem {
  const role = ev.role ?? "coach";
  switch (ev.type) {
    case "phase":
      if (ev.name === "gather")
        return { text: "读取目标信息", state: "done", role };
      return ev.state === "start"
        ? { text: "解析计划中的科目…", state: "run", role }
        : { text: `解析出 ${ev.subjects ?? "?"} 个科目`, state: "done", role };
    case "round":
      return { text: `第 ${ev.index}/${ev.max} 轮决策`, state: "run", role };
    case "thought":
      // 教练本轮的判断说明（预算够不够、超载了怎么调）——计划的"为什么"在这里
      return { text: ev.text, state: "thought", role };
    case "tool": {
      if (ev.detail) return { text: ev.detail, state: ev.state === "error" ? "err" : "done", role };
      const label = TOOL_LABELS[ev.name] ?? ev.name;
      return { text: `${label}…`, state: ev.state === "error" ? "err" : "done", role };
    }
    case "proposal":
      return { text: "提案已生成，等你审批", state: "done", role };
    case "questions":
      return { text: "信息不全，需要补充", state: "done", role };
  }
}
const DRAFT_KEY = "gc_chat_draft"; // 对话页草稿：计划文本 + 目标创建表单，切页不丢

/** 首载恢复草稿（SSR 无 window 返回空；脏数据自愈返回空）。 */
function loadDraft() {
  const empty = {
    rawText: "",
    weeklyHours: "",
    newGoalTitle: "",
    newGoalDeadline: "",
    newGoalHours: "",
    showNewGoal: false,
  };
  if (typeof window === "undefined") return empty;
  try {
    const d = JSON.parse(window.localStorage.getItem(DRAFT_KEY) ?? "{}") as Record<
      string,
      unknown
    >;
    return {
      rawText: typeof d.rawText === "string" ? d.rawText : "",
      weeklyHours: typeof d.weeklyHours === "string" ? d.weeklyHours : "",
      newGoalTitle: typeof d.newGoalTitle === "string" ? d.newGoalTitle : "",
      newGoalDeadline: typeof d.newGoalDeadline === "string" ? d.newGoalDeadline : "",
      newGoalHours: typeof d.newGoalHours === "string" ? d.newGoalHours : "",
      showNewGoal: d.showNewGoal === true,
    };
  } catch {
    return empty;
  }
}

/** 明天的 ISO 日期（截止日期选择器的 min 值：截止必须晚于今天）。 */
function tomorrowISO(): string {
  const d = new Date(Date.now() + 86400000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function ChatPage() {
  const [goals, setGoals] = useState<GoalOut[]>([]);
  const [goalId, setGoalId] = useState<number | null>(null);
  const [initialDraft] = useState(loadDraft);
  const [rawText, setRawText] = useState(initialDraft.rawText);
  const [weeklyHours, setWeeklyHours] = useState(initialDraft.weeklyHours);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [needSettings, setNeedSettings] = useState(false);
  const [result, setResult] = useState<ImportOut | null>(null);
  const [proposal, setProposal] = useState<ProposalOut | null>(null);
  const [decided, setDecided] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("排得太满，压力大");
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [newGoalTitle, setNewGoalTitle] = useState(initialDraft.newGoalTitle);
  const [newGoalDeadline, setNewGoalDeadline] = useState(initialDraft.newGoalDeadline);
  const [newGoalHours, setNewGoalHours] = useState(initialDraft.newGoalHours);
  const [showNewGoal, setShowNewGoal] = useState(initialDraft.showNewGoal);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);

  const loadGoals = async () => {
    try {
      const list = await api.listGoals();
      const active = list.filter((g) => g.status === "进行中"); // 归档目标不进下拉
      setGoals(active);
      setGoalId((current) => current ?? active[0]?.id ?? null);
      if (active.length === 0) setShowNewGoal(true); // 无进行中目标时自动展开创建表单
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "目标加载失败");
    }
  };

  useLoad(loadGoals);

  // 草稿防抖落盘：输入停顿 300ms 后保存（计划文本+目标表单+展开状态），切页/刷新都可恢复
  useEffect(() => {
    const timer = window.setTimeout(() => {
      window.localStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({
          rawText,
          weeklyHours,
          newGoalTitle,
          newGoalDeadline,
          newGoalHours,
          showNewGoal,
        }),
      );
    }, 300);
    return () => window.clearTimeout(timer);
  }, [rawText, weeklyHours, newGoalTitle, newGoalDeadline, newGoalHours, showNewGoal]);

  async function startAlign() {
    if (!goalId) {
      setError("还没有目标：先在上面填目标名并点「创建」");
      return;
    }
    if (rawText.trim().length < 5) {
      setError("写一句话就行，比如'我要3个月拿下软考'");
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);
    setProposal(null);
    setDecided("");
    setTimeline([]);
    try {
      const out = await importPlanStream(
        goalId,
        rawText.trim(),
        weeklyHours ? Number(weeklyHours) : undefined,
        (ev) => {
          const item = eventToItem(ev);
          setTimeline((prev) => [
            ...prev.map((t) => (t.state === "run" ? { ...t, state: "done" as const } : t)),
            item,
          ]);
        },
      );
      setTimeline((prev) => prev.map((t) => (t.state === "run" ? { ...t, state: "done" as const } : t)));
      setResult(out);
      setRawText(""); // 提交完成：结果与审批卡已展示，清空输入与草稿
      setWeeklyHours("");
      window.localStorage.removeItem(DRAFT_KEY);
      if (out.proposal_id) {
        setProposal(await api.getProposal(out.proposal_id));
      }
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "导入失败";
      setError(message);
      setNeedSettings(exc instanceof ApiError && exc.status === 400);
    } finally {
      setBusy(false);
    }
  }

  async function decide(approve: boolean) {
    if (!proposal) return;
    if (approve) {
      try {
        const updated = await api.approveProposal(proposal.id);
        setProposal(updated);
        setDecided("新计划已生效，去「今日」看看 ✅");
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "操作失败");
      }
      return;
    }
    setRejectOpen(true); // 拒绝先问原因：教练下轮据此针对性调整
  }

  async function confirmReject() {
    if (!proposal) return;
    try {
      const updated = await api.rejectProposal(proposal.id, rejectReason);
      setProposal(updated);
      setDecided("已拒绝。你的反馈我记下了——重新贴入计划时教练会针对性调整");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
    } finally {
      setRejectOpen(false);
    }
  }

  async function createGoal() {
    const title = newGoalTitle.trim();
    if (!title) return;
    try {
      const goal = await api.createGoal({
        title,
        category: "备考",
        deadline: newGoalDeadline || undefined,
        weekly_hours: newGoalHours ? Number(newGoalHours) : undefined,
      });
      await loadGoals();
      setGoalId(goal.id);
      setNewGoalTitle("");
      setNewGoalDeadline("");
      setNewGoalHours("");
      setShowNewGoal(false);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "创建失败");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="pt-1">
        <h1 className="text-[26px] font-medium tracking-tight">和教练聊聊</h1>
        <p className="mt-1 text-sm text-gc-muted">一句话也行，教练帮你排出每天的事</p>
      </header>

      {/* AI 气泡 */}
      <section className="flex gap-2.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gc-lavender text-xs">
          编
        </div>
        <div className="rounded-3xl rounded-tl-lg bg-gc-lavender px-4 py-3 text-sm leading-6">
          写一句话（如&ldquo;我要3个月拿下软考&rdquo;）或贴入详细计划，我来排进每天。
        </div>
      </section>

      {/* 导入对齐卡 */}
      <section className="gc-card px-5 py-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <select
            value={goalId ?? ""}
            onChange={(e) => setGoalId(Number(e.target.value))}
            className="min-w-0 flex-1 rounded-full bg-gc-bg px-4 py-2.5 text-sm outline-none"
          >
            {goals.length === 0 && <option value="">（先创建一个目标）</option>}
            {goals.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowNewGoal(!showNewGoal)}
            className="shrink-0 rounded-full bg-gc-accent-soft px-3.5 py-2 text-xs"
          >
            {showNewGoal ? "取消" : "+ 新目标"}
          </button>
        </div>
        {showNewGoal && (
          <div className="mb-3 flex flex-col gap-2">
            <div className="flex gap-2">
              <input
                value={newGoalTitle}
                onChange={(e) => setNewGoalTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && createGoal()}
                placeholder="目标名称（如：软考高级冲刺）"
                maxLength={200}
                autoFocus
                className="min-w-0 flex-1 rounded-full bg-gc-bg px-4 py-2.5 text-sm outline-none placeholder:text-gc-muted"
              />
              <button
                onClick={createGoal}
                disabled={!newGoalTitle.trim()}
                className="shrink-0 rounded-full bg-gc-accent px-4 py-2.5 text-xs text-white disabled:opacity-50"
              >
                创建
              </button>
            </div>
            <div className="flex gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <span className="shrink-0 text-xs text-gc-muted">截止</span>
                <input
                  type="date"
                  value={newGoalDeadline}
                  min={tomorrowISO()} // 截止必须是未来某天（后端同校验）
                  onChange={(e) => setNewGoalDeadline(e.target.value)}
                  className="min-w-0 flex-1 rounded-full bg-gc-bg px-4 py-2 text-xs text-gc-muted outline-none"
                />
              </div>
              <input
                type="number"
                value={newGoalHours}
                onChange={(e) => setNewGoalHours(e.target.value)}
                placeholder="每周小时"
                min={1}
                max={80}
                className="w-24 shrink-0 rounded-full bg-gc-bg px-3 py-2 text-center text-xs outline-none placeholder:text-gc-muted"
              />
            </div>
            <p className="text-[11px] leading-4 text-gc-muted">
                截止日期可选：知道考试日就填（须晚于今天）；不填也行，教练会从你写的“3 个月拿下…”这类话里自动推
              </p>
          </div>
        )}
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder={"一句话就行，比如：\n· 我要3个月拿下软考\n· 秋招冲刺，每天晚上2小时\n· 也可以贴详细计划/经验帖"}

          rows={5}
          maxLength={20000}
          className="mb-3 w-full rounded-2xl bg-gc-bg px-4 py-3 text-sm outline-none placeholder:text-gc-muted"
        />
        <div className="mb-3 flex items-center gap-2 text-xs text-gc-muted">
          <span>每周可投入</span>
          <input
            value={weeklyHours}
            onChange={(e) => setWeeklyHours(e.target.value)}
            inputMode="decimal"
            placeholder="10"
            className="w-16 rounded-full bg-gc-bg px-3 py-1.5 text-center text-sm outline-none"
          />
          <span>小时（首次必填，之后记住你）</span>
        </div>
        {timeline.length > 0 && (
          <div className="mb-3 flex flex-col gap-1.5 rounded-2xl bg-gc-bg px-4 py-3 text-xs leading-5">
            {timeline.map((item, i) =>
              item.state === "thought" ? (
                // 教练的判断说明：气泡样式的"工作直播"，展示计划变化的原因
                <div key={i} className="flex items-start gap-2">
                  <span className="mt-0.5 shrink-0 rounded-full bg-gc-lavender px-1.5 py-0.5 text-[10px] text-gc-text">
                    {ROLE_LABELS[item.role ?? "coach"]}
                  </span>
                  <p className="rounded-xl rounded-tl-sm bg-gc-lavender/60 px-2.5 py-1.5 text-gc-text">
                    {item.text}
                  </p>
                </div>
              ) : (
                <div
                  key={i}
                  className={`flex items-center gap-2 ${
                    item.state === "err" ? "text-red-500" : "text-gc-muted"
                  }`}
                >
                  <span className="w-4 shrink-0 text-center">
                    {item.state === "done" ? (
                      "✓"
                    ) : item.state === "err" ? (
                      "×"
                    ) : (
                      <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border border-gc-muted border-t-transparent" />
                    )}
                  </span>
                  <span>{item.text}</span>
                </div>
              ),
            )}
            {busy && timeline[timeline.length - 1]?.state !== "run" && (
              <div className="flex items-center gap-2 text-gc-muted">
                <span className="inline-block h-2.5 w-2.5 shrink-0 animate-spin rounded-full border border-gc-muted border-t-transparent" />
                <span>教练正在排计划，全程约十几秒…</span>
              </div>
            )}
          </div>
        )}
        <button
          onClick={startAlign}
          disabled={busy || !goalId}
          className="w-full rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98] disabled:opacity-60"
        >
          {busy ? "教练正在排计划，约十几秒…" : goalId ? "生成我的周计划" : "先创建一个目标，再生成计划"}
        </button>
        {error && (
          <p className="mt-3 rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-xs leading-5 text-gc-text">
            {error}
            {needSettings && (
              <>
                {" "}
                <Link href="/settings" className="underline">
                  去设置模型 →
                </Link>
              </>
            )}
          </p>
        )}
      </section>

      {/* 追问 */}
      {result?.status === "questions" && (
        <section className="gc-card bg-gc-lavender px-5 py-4">
          <p className="text-sm font-medium">教练想先了解两件事</p>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-gc-muted">
            {result.questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-gc-muted">在目标里补上截止日期、在上方填每周时长即可</p>
        </section>
      )}

      {/* 审批卡 */}
      {proposal && proposal.status === PROPOSAL_STATUS.PENDING && (
        <section className="gc-card border border-gc-lavender px-5 py-4" style={{ borderStyle: "solid" }}>
          <p className="text-sm font-medium">教练的新周计划提案</p>
          <p className="mt-1 text-xs leading-5 text-gc-muted">{proposal.summary}</p>
          <ul className="mt-3 space-y-1.5 text-sm">
            {(showAllTasks ? proposal.tasks : proposal.tasks.slice(0, 5)).map((t, i) => (
              <li key={i} className="flex justify-between text-gc-text">
                <span className="truncate pr-2">{t.title}</span>
                <span className="shrink-0 text-xs text-gc-muted">{t.date.slice(5)}</span>
              </li>
            ))}
            {proposal.tasks.length > 5 && (
              <li>
                <button
                  onClick={() => setShowAllTasks(!showAllTasks)}
                  className="text-xs text-gc-accent underline"
                >
                  {showAllTasks ? "收起" : `展开全部 ${proposal.tasks.length} 件`}
                </button>
              </li>
            )}
          </ul>
          <div className="mt-4 flex gap-3">
            <button
              onClick={() => decide(true)}
              className="flex-1 rounded-full bg-gc-accent py-2.5 text-sm text-white active:scale-95"
            >
              同意
            </button>
            <button
              onClick={() => decide(false)}
              className="flex-1 rounded-full border border-gc-divider py-2.5 text-sm active:scale-95"
            >
              再想想
            </button>
          </div>
        </section>
      )}

      {decided && <p className="text-center text-sm text-gc-accent">{decided}</p>}

      {/* 拒绝原因：教练下一轮排程的自适应输入（拒绝不是死胡同） */}
      <MiniSheet open={rejectOpen} title="这次计划哪里不合适？" onClose={() => setRejectOpen(false)}>
        <div className="flex flex-col gap-2">
          {[
            "排得太满，压力大",
            "时段不合适",
            "科目或动作不合适",
            "换个思路重新规划",
          ].map((r) => (
            <button
              key={r}
              onClick={() => setRejectReason(r)}
              className={`rounded-full px-4 py-2.5 text-sm active:opacity-70 ${
                rejectReason === r ? "bg-gc-accent text-white" : "bg-gc-bg text-gc-text"
              }`}
            >
              {r}
            </button>
          ))}
          <button
            onClick={confirmReject}
            className="mt-2 rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98]"
          >
            提交反馈并拒绝
          </button>
          <p className="text-center text-xs text-gc-muted">
            教练会记住原因，下次生成时针对性调整
          </p>
        </div>
      </MiniSheet>

      <p className="mt-2 px-1 text-xs leading-5 text-gc-muted">
        即将上线：与教练自由对话（补救方案、数据问答）。
      </p>
    </div>
  );
}
