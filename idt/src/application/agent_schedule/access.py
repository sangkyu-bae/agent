"""agent-schedule UseCase 공용 접근 검사 헬퍼.

정책 판단(SchedulePolicy)을 호출하는 조회+검사 조합만 담당 — 규칙 자체는 domain.
"""
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.agent_schedule.policies import SchedulePolicy


async def ensure_owned_agent(
    agent_repo: AgentDefinitionRepositoryInterface,
    agent_id: str,
    user_id: str,
    request_id: str,
) -> None:
    agent = await agent_repo.find_by_id(agent_id, request_id)
    if agent is None:
        raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")
    if agent.user_id != user_id:
        raise PermissionError("본인 소유 에이전트에만 스케줄을 관리할 수 있습니다")


async def get_owned_schedule(
    schedule_repo: ScheduleRepositoryInterface,
    agent_id: str,
    schedule_id: str,
    user_id: str,
    request_id: str,
) -> AgentSchedule:
    schedule = await schedule_repo.find_by_id(schedule_id, request_id)
    if schedule is None or schedule.agent_id != agent_id:
        raise ValueError(f"스케줄을 찾을 수 없습니다: {schedule_id}")
    if not SchedulePolicy.can_modify(schedule.user_id, user_id):
        raise PermissionError("스케줄 소유자만 접근할 수 있습니다")
    return schedule
