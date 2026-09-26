"""业务层通用错误（API 层统一映射为 HTTP 状态码）。"""


class NotFoundError(Exception):
    """资源不存在或不属于当前用户（统一 404，不泄露存在性）。"""


class StateConflictError(Exception):
    """当前状态不允许该操作（映射 409）。"""


class LLMSettingsError(Exception):
    """BYOK 配置缺失或已失效（映射 400，提示用户去设置页）。"""


class PlannerFailedError(Exception):
    """规划 Agent 未能产出有效结果或上游模型调用失败（映射 502）。"""


class ReviewFailedError(Exception):
    """复盘师 Agent 未能产出有效结果或上游模型调用失败（映射 502）。"""
