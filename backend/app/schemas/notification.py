"""通知模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import NotificationType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: NotificationType
    title: str
    body: str
    read: bool
    created_at: datetime
