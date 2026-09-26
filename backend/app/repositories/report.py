"""周报表数据访问。"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import WeeklyReport


class WeeklyReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        user_id: int,
        week_start: date,
        title: str,
        content: str,
        data_snapshot: dict[str, object],
    ) -> WeeklyReport:
        """同周重跑覆盖（并发首写撞唯一约束按更新处理）。

        注意：首插必须带全部 NOT NULL 字段一次 flush——先建空对象再补字段
        会在 flush 时触发 NOT NULL 违约。
        """
        report = await self.get_for_user_by_week(user_id, week_start)
        if report is None:
            report = WeeklyReport(
                user_id=user_id,
                week_start=week_start,
                title=title,
                content=content,
                data_snapshot=data_snapshot,
            )
            self._session.add(report)
            try:
                await self._session.flush()
                return report
            except IntegrityError:
                await self._session.rollback()
                report = await self.get_for_user_by_week(user_id, week_start)
                if report is None:
                    raise
        report.title = title
        report.content = content
        report.data_snapshot = data_snapshot
        await self._session.flush()
        return report

    async def get_for_user_by_week(self, user_id: int, week_start: date) -> WeeklyReport | None:
        result = await self._session.execute(
            select(WeeklyReport).where(
                WeeklyReport.user_id == user_id, WeeklyReport.week_start == week_start
            )
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, report_id: int, user_id: int) -> WeeklyReport | None:
        result = await self._session.execute(
            select(WeeklyReport).where(
                WeeklyReport.id == report_id, WeeklyReport.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int, limit: int = 12) -> list[WeeklyReport]:
        result = await self._session.execute(
            select(WeeklyReport)
            .where(WeeklyReport.user_id == user_id)
            .order_by(WeeklyReport.week_start.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
