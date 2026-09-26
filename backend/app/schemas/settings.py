"""BYOK 模型设置模型。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMSettingsIn(BaseModel):
    """OpenAI 兼容三件套（硅基流动/DeepSeek/OpenAI 通吃）。"""

    base_url: str = Field(min_length=8, max_length=500, pattern=r"^https?://")
    api_key: str = Field(min_length=8, max_length=200)
    model_name: str = Field(min_length=1, max_length=100)

    @field_validator("base_url")
    @classmethod
    def validate_no_private(cls, v: str) -> str:
        """SSRF 防护：BYOK base_url 不允许指向内网/环回/元数据地址。"""
        from app.services.push import _validate_no_private_address

        error = _validate_no_private_address(v)
        if error:
            raise ValueError(f"模型地址校验失败：{error}")
        return v


class LLMSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_url: str
    model_name: str
    api_key_masked: str
