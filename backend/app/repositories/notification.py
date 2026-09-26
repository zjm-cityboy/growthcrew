"""通知的数据访问。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import NotificationType
from app.models.notification import Notification

_LIST_LIMIT = 50


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, user_id: int, type: NotificationType, title: str, body: str
    ) -> Notification:
        notification = Notification(user_id=user_id, type=type, title=title, body=body)
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def exists_since(
        self, user_id: int, type: NotificationType, since_utc_naive: datetime
    ) -> bool:
        """该用户自 since（朴素 UTC）起是否已有同类型通知（定时任务当日去重）。"""
        result = await self._session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.type == type,
                Notification.created_at >= since_utc_naive,
            )
        )
        return (result.scalar_one() or 0) > 0

    async def list_for_user(self, user_id: int) -> list[Notification]:
        result = await self._session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.read, Notification.id.desc())
            .limit(_LIST_LIMIT)
        )
        return list(result.scalars().all())

    async def get_for_user(self, notification_id: int, user_id: int) -> Notification | None:
        result = await self._session.execute(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
