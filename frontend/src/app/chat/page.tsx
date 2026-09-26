"use client";

import { ApiError, PROPOSAL_STATUS, api, type GoalOut, type ImportOut, type ProposalOut } from "@/lib/api";
import { useLoad } from "@/lib/useLoad";
import Link from "next/link";
import { useState } from "react";

/** 对话 Tab（P1.4 形态）：计划导入对齐 + 提案审批卡；P2 接入总编自由对话。 */
export default function ChatPage() {
  const [goals, setGoals] = useState<GoalOut[]>([]);
  const [goalId, setGoalId] = useState<number | null>(null);
  const [rawText, setRawText] = useState("");
  const [weeklyHours, setWeeklyHours] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [needSettings, setNeedSettings] = useState(false);
  const [result, setResult] = useState<ImportOut | null>(null);
  const [proposal, setProposal] = useState<ProposalOut | null>(null);
  const [decided, setDecided] = useState("");
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [newGoalTitle, setNewGoalTitle] = useState("");
  const [newGoalDeadline, setNewGoalDeadline] = useState("");
  const [newGoalHours, setNewGoalHours] = useState("");
  const [showNewGoal, setShowNewGoal] = useState(false);

  const loadGoals = async () => {
    try {
      const list = await api.listGoals();
      setGoals(list);
      setGoalId((current) => current ?? list[0]?.id ?? null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "目标加载失败");
    }
  };

  useLoad(loadGoals);

  async function startAlign() {
    if (!goalId || rawText.trim().length < 5) {
      setError("写一句话就行，比如'我要3个月拿下软考'");
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);
    setProposal(null);
    setDecided("");
    try {
      const out = await api.importPlan(goalId, rawText.trim(), weeklyHours ? Number(weeklyHours) : undefined);
      setResult(out);
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
    try {
      const updated = approve
        ? await api.approveProposal(proposal.id)
        : await api.rejectProposal(proposal.id);
      setProposal(updated);
      setDecided(approve ? "新计划已生效，去「今日」看看 ✅" : "已拒绝，可重新贴入再试");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "操作失败");
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
              <input
                type="date"
                value={newGoalDeadline}
                onChange={(e) => setNewGoalDeadline(e.target.value)}
                className="min-w-0 flex-1 rounded-full bg-gc-bg px-4 py-2 text-xs text-gc-muted outline-none"
              />
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
        <button
          onClick={startAlign}
          disabled={busy}
          className="w-full rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98] disabled:opacity-60"
        >
          {busy ? "教练对齐中，约十几秒…" : "开始对齐"}
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

      <p className="mt-2 px-1 text-xs leading-5 text-gc-muted">
        即将上线：与教练自由对话（补救方案、数据问答）。
      </p>
    </div>
  );
}
