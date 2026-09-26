"""确定性排程算法测试。"""

from collections import Counter
from datetime import date

from app.agents.scheduler import SubjectAllocation, next_monday, schedule_week


def test_next_monday() -> None:
    assert next_monday(date(2026, 9, 28)).weekday() == 0  # 周一输入返回本周一
    ws = next_monday(date(2026, 9, 23))  # 周三输入
    assert ws.weekday() == 0
    assert ws > date(2026, 9, 23)


def test_schedule_within_budget() -> None:
    result = schedule_week([SubjectAllocation("数学", 10.0)], 10.0, week_start=date(2026, 9, 28))
    assert result.overloaded is False
    assert len(result.tasks) == 7  # 每天 75 分钟 = 1 段
    per_day = Counter(t.date for t in result.tasks)
    assert set(per_day.values()) == {1}
    assert all(t.duration_minutes <= 90 for t in result.tasks)


def test_schedule_overload_detected_and_scaled() -> None:
    result = schedule_week(
        [SubjectAllocation("A", 20.0), SubjectAllocation("B", 10.0)],
        10.0,
        week_start=date(2026, 9, 28),
    )
    assert result.overloaded is True
    assert result.requested_minutes == 1800
    assert result.capacity_minutes == 600
    total = sum(t.duration_minutes for t in result.tasks)
    assert total <= 600  # 等比缩减进容量


def test_daily_cap_respected() -> None:
    result = schedule_week(
        [SubjectAllocation("A", 30.0)],
        30.0,
        week_start=date(2026, 9, 28),
    )
    per_day = Counter(t.date for t in result.tasks)
    assert max(per_day.values()) <= 3  # 少即是多：每日 ≤3 件


def test_zero_budget_produces_nothing() -> None:
    result = schedule_week([SubjectAllocation("A", 5.0)], 0, week_start=date(2026, 9, 28))
    assert result.tasks == []
    assert result.truncated_minutes == 300


def test_tiny_subject_skipped_after_scaling() -> None:
    """缩放后不足最小粒度（15 分钟/日）的科目整周跳过，不靠保底时长挤占容量。"""
    result = schedule_week(
        [SubjectAllocation("主科", 20.0), SubjectAllocation("边角", 0.1)],
        10.0,
        week_start=date(2026, 9, 28),
    )
    labels = {t.category_label for t in result.tasks}
    assert "边角" not in labels
    assert result.truncated_minutes > 0
