"""确定性周排程算法：精确计算不交给 LLM。

规则（产品理念"少即是多"）：
- 每日核心任务默认 ≤3 件（daily_task_cap）
- 单任务时长按 15 分钟取整、单段 ≤90 分钟、每日 ≤240 分钟
- 请求总量超过容量 → overloaded=True（等比缩减到容量内），教练 Agent 据此调整或说明
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.time import today_cn

_DAILY_TASK_CAP = 3
_MAX_MINUTES_PER_DAY = 240
_SESSION_MAX = 90
_ROUND_TO = 15


@dataclass(frozen=True)
class SubjectAllocation:
    label: str
    weekly_hours: float


@dataclass(frozen=True)
class ScheduledTask:
    date: date
    title: str
    duration_minutes: int
    category_label: str


@dataclass(frozen=True)
class ScheduleResult:
    tasks: list[ScheduledTask]
    overloaded: bool
    requested_minutes: int
    capacity_minutes: int
    truncated_minutes: int
    note: str


def next_monday(day: date) -> date:
    """下一个周一（今天恰好是周一则从今天起排）。"""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def schedule_week(
    subjects: list[SubjectAllocation],
    weekly_hours_budget: float,
    week_start: date | None = None,
) -> ScheduleResult:
    """把各科目的周时长摊到 7 天，生成任务清单。"""
    start = week_start or next_monday(today_cn())
    requested = int(sum(s.weekly_hours for s in subjects) * 60)
    capacity = int(min(weekly_hours_budget * 60, 7 * _MAX_MINUTES_PER_DAY))
    overloaded = requested > capacity
    if capacity <= 0:
        # 零预算不产出任何任务（保底时长会违背容量承诺）
        return ScheduleResult(
            tasks=[],
            overloaded=overloaded,
            requested_minutes=requested,
            capacity_minutes=0,
            truncated_minutes=requested,
            note="每周预算为 0，未排入任何任务",
        )
    # 超载时等比缩到容量内（保留请求原值供 Agent 解释）
    scale = 1.0 if not overloaded or requested == 0 else capacity / requested

    ordered = sorted(subjects, key=lambda s: s.weekly_hours, reverse=True)
    per_subject_daily: list[tuple[str, int]] = []
    skipped = 0
    for subject in ordered:
        daily_minutes = subject.weekly_hours * 60 * scale / 7
        rounded = int(daily_minutes // _ROUND_TO) * _ROUND_TO
        if rounded < _ROUND_TO:
            # 缩放后不足一个最小粒度的科目整周跳过，分钟数计入未排入
            skipped += int(subject.weekly_hours * 60 * scale)
            continue
        per_subject_daily.append((subject.label, rounded))

    tasks: list[ScheduledTask] = []
    truncated = 0
    for offset in range(7):
        day = start + timedelta(days=offset)
        count = 0
        used = 0
        for label, need in per_subject_daily:
            remaining = need
            while (
                remaining >= _ROUND_TO and count < _DAILY_TASK_CAP and used < _MAX_MINUTES_PER_DAY
            ):
                chunk = min(remaining, _SESSION_MAX, _MAX_MINUTES_PER_DAY - used)
                chunk = int(chunk // _ROUND_TO) * _ROUND_TO
                if chunk < _ROUND_TO:
                    break
                tasks.append(
                    ScheduledTask(
                        date=day,
                        title=f"{label} · 专注 {chunk} 分钟",
                        duration_minutes=chunk,
                        category_label=label,
                    )
                )
                used += chunk
                remaining -= chunk
                count += 1
            truncated += remaining if remaining >= _ROUND_TO else 0

    parts = [f"已生成 {len(tasks)} 件任务（周起始 {start.isoformat()}）"]
    if overloaded:
        parts.append(
            f"注意：请求 {requested} 分钟超出每周预算 {capacity} 分钟，已等比缩减；"
            "建议下调科目时长后重排"
        )
    if truncated + skipped:
        parts.append(f"受预算与每日上限约束，{truncated + skipped} 分钟未能排入")
    return ScheduleResult(
        tasks=tasks,
        overloaded=overloaded,
        requested_minutes=requested,
        capacity_minutes=capacity,
        truncated_minutes=truncated + skipped,
        note="；".join(parts),
    )
