"""时间工具：产品口径统一用北京时间的"今天"。"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_CN_TZ = ZoneInfo("Asia/Shanghai")


def now_cn() -> datetime:
    """当前北京时间（带时区）。"""
    return datetime.now(_CN_TZ)


def today_cn() -> date:
    """北京时间口径的今天（与用户手机端一致，服务器 UTC 部署也不漂移）。"""
    return now_cn().date()


def cn_day_start_utc_naive(day: date) -> datetime:
    """某北京时间日期的 0 点，转为朴素 UTC 时间。

    用于跨库比较 created_at（SQLite 存朴素 UTC 字符串、PG 存 timestamptz，
    朴素 UTC 参数在两种引擎下语义一致）。
    """
    return (
        datetime.combine(day, time.min, tzinfo=_CN_TZ)
        .astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
    )
