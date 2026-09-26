"""推送设置模型。"""

from pydantic import BaseModel, ConfigDict, Field


class PushSettingsIn(BaseModel):
    channel: str = Field(pattern=r"^(bark|pushplus|wecom_webhook)$")
    endpoint: str = Field(min_length=10, max_length=500, pattern=r"^https?://")
    enabled: bool = True


class PushSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: str
    endpoint: str  # 用户自己粘贴的，展示无妨（不是密码）
    enabled: bool


class PushTestOut(BaseModel):
    delivered: bool
    message: str
