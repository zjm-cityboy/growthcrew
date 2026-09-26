"""APScheduler 装配：晨推（默认 07:00）与晚间提醒（默认 21:30，北京时间）。

多 worker 部署时只在一个进程启用 GC_JOBS_ENABLED；即便误开多份，
任务体自带"每用户每类型每天一条"的去重守卫，不会重复推送。
"""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.jobs.briefs import evening_reminder_job, morning_brief_job
from app.jobs.reports import midweek_brief_job, weekly_report_job

_CN_TZ = ZoneInfo("Asia/Shanghai")


def build_scheduler(
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=_CN_TZ)
    scheduler.add_job(
        morning_brief_job,
        "cron",
        args=[session_maker],
        hour=settings.morning_brief_hour,
        minute=0,
        id="morning_brief",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        evening_reminder_job,
        "cron",
        args=[session_maker],
        hour=settings.evening_reminder_hour,
        minute=30,
        id="evening_reminder",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
    )
    # 复盘师：周日 20:00 周报（LLM，含 BYOK 过滤与同周去重）
    scheduler.add_job(
        weekly_report_job,
        "cron",
        args=[session_maker],
        day_of_week="sun",
        hour=20,
        minute=0,
        id="weekly_report",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # 复盘师：周三 20:00 小结（LLM，当日去重）
    scheduler.add_job(
        midweek_brief_job,
        "cron",
        args=[session_maker],
        day_of_week="wed",
        hour=20,
        minute=0,
        id="midweek_brief",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    return scheduler
