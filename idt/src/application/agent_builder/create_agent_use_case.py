"""CreateAgentUseCase: 에이전트 생성 오케스트레이션."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.schemas import CreateAgentRequest, CreateAgentResponse, WorkerInfo
from src.application.agent_builder.tool_selector import ToolSelector
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AgentBuilderPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateAgentUseCase:
    def __init__(
        self,
        tool_selector: ToolSelector,
        prompt_generator: PromptGenerator,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._selector = tool_selector
        self._generator = prompt_generator
        self._repository = repository
        self._logger = logger

    async def execute(
        self, request: CreateAgentRequest, request_id: str
    ) -> CreateAgentResponse:
        self._logger.info(
            "CreateAgentUseCase start", request_id=request_id, user_id=request.user_id
        )
        try:
            # Step 1: 도구 선택 + 플로우 결정
            skeleton = await self._selector.select(request.user_request, request_id)

            # Step 2: Policy 검증
            AgentBuilderPolicy.validate_tool_count(len(skeleton.workers))
            AgentBuilderPolicy.validate_name(request.name)

            # Step 3: 시스템 프롬프트 자동 생성
            tool_metas = [get_tool_meta(w.tool_id) for w in skeleton.workers]
            system_prompt = await self._generator.generate(
                request.user_request, skeleton, tool_metas, request_id
            )
            AgentBuilderPolicy.validate_system_prompt(system_prompt)

            # Step 4: AgentDefinition 저장
            now = datetime.now(timezone.utc)
            agent = AgentDefinition(
                id=str(uuid.uuid4()),
                user_id=request.user_id,
                name=request.name,
                description=request.user_request,
                system_prompt=system_prompt,
                flow_hint=skeleton.flow_hint,
                workers=skeleton.workers,
                model_name=request.model_name,
                status="active",
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(agent, request_id)

            self._logger.info(
                "CreateAgentUseCase done", request_id=request_id, agent_id=saved.id
            )
            return CreateAgentResponse(
                agent_id=saved.id,
                name=saved.name,
                system_prompt=saved.system_prompt,
                tool_ids=[w.tool_id for w in saved.workers],
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                    )
                    for w in saved.workers
                ],
                flow_hint=saved.flow_hint,
                model_name=saved.model_name,
                created_at=saved.created_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "CreateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
