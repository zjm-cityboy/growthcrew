"""数据导出路由：用户的全部数据一份 CSV（数据主权的产品承诺）。

安全要点：
- CSV 公式注入防护：以 =/+/-/@/\t/\r 开头的单元格加 ' 前缀（OWASP 标准）；
- UTF-8 BOM：中文用户在 Windows Excel 双击打开不乱码。
"""

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_session
from app.core.time import today_cn
from app.models.goal import Goal
from app.models.journal import DailyJournal, LifeLog
from app.models.notification import Notification
from app.models.plan import Task, WeeklyPlan
from app.models.report import WeeklyReport
from app.models.user import User

router = APIRouter(prefix="/export", tags=["export"])

_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object) -> str:
    """CSV 公式注入防护：以 =/+/-/@/\t/\r 开头的值加 ' 前缀。"""
    text = str(value) if value is not None else ""
    if text.startswith(_INJECTION_PREFIXES):
        return f"'{text}"
    return text


@router.get("/csv")
async def export_csv(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """导出用户全部数据（目标/任务/卡因/生活/复盘/周报/通知）为单文件 CSV。"""
    user_id = current_user.id
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM：Windows Excel 中文兼容
    writer = csv.writer(output)

    def _row(values: list[object]) -> None:
        writer.writerow([_safe(v) for v in values])

    def _section(title: str) -> None:
        writer.writerow([])
        writer.writerow([f"## {title} ##"])

    # ---------- 目标 ----------
    goals_result = await session.execute(
        select(Goal)
        .where(Goal.user_id == user_id)
        .options(selectinload(Goal.milestones))
        .order_by(Goal.id)
    )
    goals = list(goals_result.scalars().all())

    _section("目标")
    _row(["ID", "标题", "类别", "状态", "截止日", "每周时长", "创建时间"])
    for g in goals:
        _row([g.id, g.title, g.category, g.status, g.deadline, g.weekly_hours, g.created_at])

    _section("里程碑")
    _row(["目标", "标题", "顺序", "截止日", "状态"])
    for g in goals:
        for m in g.milestones:
            _row([g.title, m.title, m.order, m.due_date, m.status])

    # ---------- 任务 ----------
    tasks_result = await session.execute(
        select(Task, WeeklyPlan)
        .join(WeeklyPlan, Task.weekly_plan_id == WeeklyPlan.id)
        .join(Goal, WeeklyPlan.goal_id == Goal.id)
        .where(Goal.user_id == user_id)
        .order_by(Task.date, Task.id)
    )
    _section("任务（含卡因与自报时长）")
    _row(
        [
            "日期",
            "任务名",
            "时长(分钟)",
            "科目",
            "状态",
            "卡因",
            "实际时长",
            "完成时刻",
            "计划版本",
            "计划状态",
        ]
    )
    for task, plan in tasks_result.all():
        _row(
            [
                task.date,
                task.title,
                task.duration_minutes,
                task.category_label,
                task.status,
                task.skip_reason or "",
                task.actual_minutes or "",
                task.completed_at or "",
                f"v{plan.version}",
                plan.status,
            ]
        )

    # ---------- 生活打卡 ----------
    life_result = await session.execute(
        select(LifeLog).where(LifeLog.user_id == user_id).order_by(LifeLog.date)
    )
    _section("生活三打卡")
    _row(["日期", "睡眠(小时)", "运动", "心情(1-5)"])
    for log in life_result.scalars():
        _row([log.date, log.sleep_hours or "", "是" if log.exercise else "否", log.mood or ""])

    # ---------- 晚间复盘 ----------
    journal_result = await session.execute(
        select(DailyJournal).where(DailyJournal.user_id == user_id).order_by(DailyJournal.date)
    )
    _section("晚间复盘")
    _row(["日期", "心情(1-5)", "一句话感想"])
    for j in journal_result.scalars():
        _row([j.date, j.mood, j.note])

    # ---------- 错题本 ----------
    from app.models.mistake import Mistake

    mistake_result = await session.execute(
        select(Mistake).where(Mistake.user_id == user_id).order_by(Mistake.created_at)
    )
    _section("错题本")
    _row(
        [
            "题目",
            "我的答案",
            "正确答案",
            "讲解",
            "来源",
            "已复习次数",
            "间隔天数",
            "已掌握",
            "下次复习",
        ]
    )
    for mistake in mistake_result.scalars():
        _row(
            [
                mistake.question,
                mistake.wrong_answer,
                mistake.correct_answer,
                mistake.explanation,
                mistake.source,
                mistake.review_count,
                mistake.interval_days,
                "是" if mistake.mastered else "否",
                mistake.next_review_at,
            ]
        )

    # ---------- 周报 ----------
    report_result = await session.execute(
        select(WeeklyReport)
        .where(WeeklyReport.user_id == user_id)
        .order_by(WeeklyReport.week_start)
    )
    _section("成长周报")
    _row(["周起始", "标题", "正文"])
    for r in report_result.scalars():
        _row([r.week_start, r.title, r.content])

    # ---------- 通知 ----------
    notif_result = await session.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at)
    )
    _section("通知历史")
    _row(["时间", "类型", "标题", "内容"])
    for n in notif_result.scalars():
        _row([n.created_at, n.type, n.title, n.body])

    output.seek(0)
    filename = f"growthcrew_export_{today_cn().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
