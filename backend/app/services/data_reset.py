"""用户数据自主：清空执行历史（账号/目标/密钥/推送配置保留）。

分层约定：seed 脚本与设置页按钮走同一条路径（两条实现 = 两套行为，必漂移）。
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.models.journal import DailyJournal, LifeLog
from app.models.plan import Task, WeeklyPlan
from app.models.report import WeeklyReport


class DataResetService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reset_history(self, user_id: int) -> int:
        """清空该用户的执行历史（任务/计划/提案随计划级联、生活打卡/复盘/周报）。

        保留：账号、目标（含截止日与每周时长）、模型密钥、推送配置。
        返回删除的任务数（供前端提示"已清空 N 件任务的历史"）。
        """
        plan_ids = select(WeeklyPlan.id).join(Goal).where(Goal.user_id == user_id)
        result = await self._session.execute(delete(Task).where(Task.weekly_plan_id.in_(plan_ids)))
        removed = int(getattr(result, "rowcount", 0) or 0)  # Result 无 rowcount 注解，运行时有
        await self._session.execute(
            delete(WeeklyPlan).where(
                WeeklyPlan.goal_id.in_(select(Goal.id).where(Goal.user_id == user_id))
            )
        )
        await self._session.execute(delete(LifeLog).where(LifeLog.user_id == user_id))
        await self._session.execute(delete(DailyJournal).where(DailyJournal.user_id == user_id))
        await self._session.execute(delete(WeeklyReport).where(WeeklyReport.user_id == user_id))
        await self._session.commit()
        return removed
