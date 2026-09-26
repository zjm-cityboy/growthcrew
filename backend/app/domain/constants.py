"""领域常量：跨模块共享的口径单一事实源。"""

from app.domain.enums import PlanStatus

# 统计口径：草稿/待审批计划的任务对用户不可见（看不到也做不了），不计入任何统计；
# 已替代版本保留——历史事实不因计划迭代被抹掉，streak 按 distinct 日期天然去重。
# repositories/plan 与 repositories/stats 共用，任何一方调整口径必须改这里。
COUNTED_PLAN_STATUSES = [PlanStatus.ACTIVE, PlanStatus.SUPERSEDED]
