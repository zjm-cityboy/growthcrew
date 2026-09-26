"""通知业务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.notification import NotificationRepository
from app.schemas.notification import NotificationOut
from app.services.errors import NotFoundError


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._notifications = NotificationRepository(session)
        self._session = session

    async def list(self, user_id: int) -> list[NotificationOut]:
        items = await self._notifications.list_for_user(user_id)
        return [NotificationOut.model_validate(item) for item in items]

    async def mark_read(self, user_id: int, notification_id: int) -> NotificationOut:
        item = await self._notifications.get_for_user(notification_id, user_id)
        if item is None:
            raise NotFoundError("通知不存在")
        item.read = True
        await self._session.commit()
        return NotificationOut.model_validate(item)
