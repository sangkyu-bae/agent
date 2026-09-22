"""ListApprovalsUseCase: 승인 대기 목록 + 벨 배지 건수.

Design Ref: §4.1, §5.5.

리포지토리가 agent_definition 을 참조하지 않으므로(공유 Base.metadata 오염
방지, module-1 에서 측정된 문제), 소유 에이전트 id 해석은 여기서 한다.
"""
from dataclasses import dataclass, field

from src.domain.approval.entity import ApprovalRequest, ApprovalStatus
from src.domain.approval.interfaces import ApprovalRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# 기본 조회 대상 — 사람이 아직 볼 이유가 있는 상태
DEFAULT_STATUSES: tuple[ApprovalStatus, ...] = ("pending", "scheduled")


@dataclass(frozen=True)
class ApprovalPage:
    items: list[ApprovalRequest]
    total: int
    # Check G6: agent_id → 이름. 소유 에이전트 조회 결과에서 만들어 추가 쿼리 없음.
    agent_names: dict[str, str] = field(default_factory=dict)


class ListApprovalsUseCase:
    def __init__(
        self,
        approval_repo: ApprovalRepositoryInterface,
        agent_repo,
        logger: LoggerInterface,
    ) -> None:
        self._repo = approval_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def list(
        self,
        *,
        user_id: str,
        request_id: str,
        statuses: tuple[ApprovalStatus, ...] = DEFAULT_STATUSES,
        page: int = 1,
        size: int = 20,
    ) -> ApprovalPage:
        agents = await self._owned_agents(user_id, request_id)
        if not agents:
            return ApprovalPage(items=[], total=0)
        items, total = await self._repo.list_for_user(
            tuple(agents), request_id, statuses=statuses,
            offset=max(0, (page - 1) * size), limit=size,
        )
        return ApprovalPage(items=items, total=total, agent_names=agents)

    async def count_unseen(self, *, user_id: str, request_id: str) -> int:
        """벨 배지 — 미확인 승인 건수 (Design §5.5)."""
        agent_ids = await self._owned_agent_ids(user_id, request_id)
        if not agent_ids:
            return 0
        return await self._repo.count_unseen(agent_ids, request_id)

    async def mark_seen(
        self, approval_id: str, *, user_id: str, request_id: str
    ) -> None:
        """Check G7 — 소유 에이전트 범위의 건만 확인 처리한다.

        이전에는 user_id 를 받기만 하고 저장소가 쓰지 않아, 아무 사용자나
        타인의 approval_id 로 벨 배지를 해제할 수 있었다. 범위 밖이면 조용히
        무시한다(존재 여부를 노출하지 않는다).
        """
        agent_ids = await self._owned_agent_ids(user_id, request_id)
        if not agent_ids:
            return
        await self._repo.mark_seen(approval_id, agent_ids, request_id)

    async def _owned_agent_ids(
        self, user_id: str, request_id: str
    ) -> tuple[str, ...]:
        """승인 권한이 있는 에이전트 id.

        현재는 소유자 기준(Plan FR-08). 역할 기반으로 확장할 때 이 메서드와
        ApprovalPolicy.can_decide 두 곳만 맞추면 된다.
        """
        return tuple(await self._owned_agents(user_id, request_id))

    async def _owned_agents(self, user_id: str, request_id: str) -> dict[str, str]:
        """소유 에이전트 id → 이름 (삽입 순서 유지)."""
        agents = await self._agent_repo.list_by_user(user_id, request_id)
        return {a.id: getattr(a, "name", None) or a.id for a in agents or []}
