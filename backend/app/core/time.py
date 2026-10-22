"""时间工具：产品口径统一用北京时间的"今天"。

演示模式支持"时间快进"：覆盖值只存在进程内存（重启即回到真实时间），
且仅在 GC_DEMO_MODE 下允许设置（config 层守卫，prod 强制拒绝）。
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_CN_TZ = ZoneInfo("Asia/Shanghai")

# 演示时钟覆盖（进程级）：None = 真实时间。所有业务取"今天"都走 today_cn()，
# 因此覆盖它即可让今日任务/连续打卡/统计窗口/周报周期整体穿越。
_clock_override: date | None = None


def now_cn() -> datetime:
    """当前北京时间（带时区）。演示覆盖时以覆盖日期的当前钟点合成。"""
    if _clock_override is not None:
        real = datetime.now(_CN_TZ)
        return datetime.combine(
            _clock_override, real.timetz()
        )  # 保留真实钟点：小时级统计（completed_at 等）仍自然分布
    return datetime.now(_CN_TZ)


def today_cn() -> date:
    """北京时间口径的今天（与用户手机端一致，服务器 UTC 部署也不漂移）。"""
    return now_cn().date()


def set_demo_clock(day: date | None) -> None:
    """设置/清除演示时钟（None=回到真实）。仅 /dev 端点在 demo 模式下调用。"""
    global _clock_override
    _clock_override = day


def demo_clock() -> date | None:
    """读取当前覆盖值（供 /dev/clock 展示；None=未覆盖）。"""
    return _clock_override


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
