"""SubAgentWorkerBuilder: create/update 공용 서브에이전트 워커 빌더.

서브에이전트 후보 접근 권한은 가시성 기반(`VisibilityPolicy.can_access`)으로 검증한다.
즉, 본인 소유 / 전체공개(public) / 부서공개(department, 동일 부서)만 허용한다.
구독(subscription) 여부는 더 이상 게이트가 아니다.
"""
from src.application.agent_builder.schemas import SubAgentConfigRequest
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import (
    AccessCheckInput,
    CircularReferencePolicy,
    NestingDepthPolicy,
    VisibilityPolicy,
)
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SubAgentWorkerBuilder:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def build(
        self,
        configs: list[SubAgentConfigRequest],
        parent_user_id: str,
        parent_department_ids: list[str],
        existing_tool_count: int,
        request_id: str,
        parent_agent_id: str | None = None,
    ) -> list[WorkerDefinition]:
        workers: list[WorkerDefinition] = []
        for i, config in enumerate(configs):
            sub_agent = await self._validate_candidate(
                config=config,
                parent_user_id=parent_user_id,
                parent_department_ids=parent_department_ids,
                parent_agent_id=parent_agent_id,
                request_id=request_id,
            )
            description = config.description or sub_agent.description
            workers.append(WorkerDefinition(
                tool_id=f"sub_agent_{config.ref_agent_id[:8]}",
                worker_id=f"sub_agent_{sub_agent.name}_{i}",
                description=description,
                sort_order=existing_tool_count + i,
                worker_type="sub_agent",
                ref_agent_id=config.ref_agent_id,
            ))
        return workers

    async def _validate_candidate(
        self,
        config: SubAgentConfigRequest,
        parent_user_id: str,
        parent_department_ids: list[str],
        parent_agent_id: str | None,
        request_id: str,
    ):
        if parent_agent_id and config.ref_agent_id == parent_agent_id:
            raise ValueError("에이전트는 자기 자신을 서브에이전트로 추가할 수 없습니다")

        sub_agent = await self._repository.find_by_id(
            config.ref_agent_id, request_id
        )
        if sub_agent is None or sub_agent.status == "deleted":
            raise ValueError(
                f"서브 에이전트를 찾을 수 없습니다: {config.ref_agent_id}"
            )

        ctx = AccessCheckInput(
            agent_owner_id=sub_agent.user_id,
            agent_visibility=sub_agent.visibility,
            agent_department_id=sub_agent.department_id,
            viewer_user_id=parent_user_id,
            viewer_department_ids=parent_department_ids,
            viewer_role="user",
        )
        if not VisibilityPolicy.can_access(ctx):
            raise PermissionError(
                f"서브 에이전트 '{sub_agent.name}'에 대한 사용 권한이 없습니다"
            )

        # 간접 순환참조 / 중첩 깊이를 서버에서 강제 (Design §4.4/§7).
        await self._validate_graph(sub_agent, parent_agent_id, request_id)
        return sub_agent

    async def _validate_graph(
        self,
        sub_agent: AgentDefinition,
        parent_agent_id: str | None,
        request_id: str,
    ) -> None:
        """후보의 하위 서브에이전트 그래프를 순회하며 순환참조/중첩 깊이를 검증한다."""
        seed: set[str] = {parent_agent_id} if parent_agent_id else set()
        await self._walk(sub_agent, depth=1, visited=seed, request_id=request_id)

    async def _walk(
        self,
        agent: AgentDefinition,
        depth: int,
        visited: set[str],
        request_id: str,
    ) -> None:
        NestingDepthPolicy.validate_depth(depth)
        CircularReferencePolicy.validate_no_cycle(agent.id, visited)
        next_visited = visited | {agent.id}
        for worker in agent.workers:
            if worker.worker_type != "sub_agent" or not worker.ref_agent_id:
                continue
            child = await self._repository.find_by_id(
                worker.ref_agent_id, request_id
            )
            if child is None or child.status == "deleted":
                continue
            await self._walk(child, depth + 1, next_visited, request_id)
