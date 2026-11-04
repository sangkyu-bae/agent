"""ForkAgentUseCase: 에이전트 포크 (전체 복사)."""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.application.agent_builder.schemas import ForkAgentResponse, WorkerInfo
from src.application.agent_builder.update_agent_use_case import sync_tool_guidelines
from src.application.tool_access.validation import (
    excluded_info,
    partition_tool_workers,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, ForkPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_opener.interfaces import AgentOpenerRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

if TYPE_CHECKING:
    from src.application.tool_access.resolver import ToolAccessResolver


class ForkAgentUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
        opener_repo: AgentOpenerRepositoryInterface | None = None,
        tool_access_resolver: "ToolAccessResolver | None" = None,
    ) -> None:
        self._agent_repo = agent_repo
        self._logger = logger
        # Design Ref: tool-access-control §2.2 (FR-08) — 포크하는 사용자에게 허용되지
        # 않은 도구는 빼고 복제. 미주입 = 전체 복사(기존 동작).
        self._tool_access_resolver = tool_access_resolver
        # agent-opener FR-07: 포크 시 원본 오프너 복사 (미주입 시 생략)
        self._opener_repo = opener_repo

    async def execute(
        self,
        source_agent_id: str,
        user_id: str,
        custom_name: str | None,
        viewer_department_ids: list[str],
        request_id: str,
    ) -> ForkAgentResponse:
        self._logger.info(
            "ForkAgentUseCase start",
            request_id=request_id,
            source_agent_id=source_agent_id,
            user_id=user_id,
        )
        try:
            source = await self._agent_repo.find_by_id(source_agent_id, request_id)
            if source is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {source_agent_id}")

            ctx = AccessCheckInput(
                agent_owner_id=source.user_id,
                agent_visibility=source.visibility,
                agent_department_id=source.department_id,
                viewer_user_id=user_id,
                viewer_department_ids=viewer_department_ids,
                viewer_role="user",
            )
            if not ForkPolicy.can_fork(ctx):
                if source.user_id == user_id:
                    raise ValueError("자신의 에이전트는 포크할 수 없습니다")
                raise PermissionError("접근 권한이 없습니다")

            ForkPolicy.validate_source_status(source.status)

            # tool-access-control FR-08: 포크 허용 판정 **후**에 도구 권한을 본다.
            workers = list(source.workers)
            excluded = []
            if self._tool_access_resolver is not None:
                access = await self._tool_access_resolver.for_user_id(
                    user_id, request_id
                )
                workers, excluded = partition_tool_workers(access, workers)

            now = datetime.now(timezone.utc)
            forked_name = custom_name or f"{source.name} (사본)"
            new_id = str(uuid.uuid4())

            forked = AgentDefinition(
                id=new_id,
                user_id=user_id,
                name=forked_name,
                description=source.description,
                system_prompt=source.system_prompt,
                flow_hint=source.flow_hint,
                workers=workers,
                llm_model_id=source.llm_model_id,
                status="active",
                visibility="private",
                department_id=None,
                temperature=source.temperature,
                max_iterations=source.max_iterations,
                forked_from=source_agent_id,
                forked_at=now,
                created_at=now,
                updated_at=now,
            )
            if excluded:
                # 제외한 도구를 프롬프트의 `## Tool Guidelines` 가 계속 안내하지 않게
                # 남은 도구 기준으로 다시 만든다 (헤딩이 없으면 무변경).
                sync_tool_guidelines(
                    forked, [w for w in workers if w.worker_type == "tool"]
                )
                self._logger.info(
                    "fork excluded tools — no permission",
                    request_id=request_id,
                    tool_ids=[w.tool_id for w in excluded],
                )

            await self._agent_repo.save(forked, request_id)

            if self._opener_repo is not None:
                source_openers = await self._opener_repo.list_by_agent_id(
                    source_agent_id, request_id
                )
                if source_openers:
                    await self._opener_repo.replace(
                        new_id, source_openers, request_id
                    )

            self._logger.info(
                "ForkAgentUseCase done",
                request_id=request_id,
                new_agent_id=new_id,
            )
            return ForkAgentResponse(
                agent_id=new_id,
                name=forked_name,
                forked_from=source_agent_id,
                forked_at=now.isoformat(),
                system_prompt=forked.system_prompt,
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                        tool_config=w.tool_config,
                    )
                    for w in workers
                ],
                excluded_tools=excluded_info(excluded),
                visibility="private",
                temperature=source.temperature,
                llm_model_id=source.llm_model_id,
            )
        except Exception as e:
            self._logger.error(
                "ForkAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
