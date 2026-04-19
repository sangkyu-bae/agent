"""AutoBuildUseCase: 자연어 요청 → 에이전트 자동 빌드 시작."""
import uuid
from datetime import datetime, timedelta

from src.application.auto_agent_builder.agent_spec_inference_service import AgentSpecInferenceService
from src.application.auto_agent_builder.schemas import AutoBuildRequest, AutoBuildResponse
from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.auto_agent_builder.interfaces import AutoBuildSessionRepositoryInterface
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.auto_agent_builder.schemas import AutoBuildSession, ConversationTurn
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AutoBuildUseCase:

    def __init__(
        self,
        inference_service: AgentSpecInferenceService,
        session_repository: AutoBuildSessionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        # DB-001 §10.4: lifespan singleton UC 는 DB 세션 보유 UC 를 생성자에서 받지 않는다.
        # create_agent_use_case 는 execute() 호출 시 요청 스코프로 주입받는다.
        self._inference = inference_service
        self._session_repo = session_repository
        self._logger = logger

    async def execute(
        self,
        request: AutoBuildRequest,
        *,
        create_agent_use_case,
    ) -> AutoBuildResponse:
        self._logger.info(
            "AutoBuildUseCase start",
            request_id=request.request_id,
            user_id=request.user_id,
        )
        try:
            available_ids = {t.tool_id for t in get_all_tools()}
            spec = await self._inference.infer(
                request.user_request, [], request.request_id, request.model_name
            )
            AutoAgentBuilderPolicy.validate_tool_ids(spec.tool_ids, available_ids)

            session_id = str(uuid.uuid4())
            now = datetime.utcnow()
            expires = now + timedelta(seconds=AutoAgentBuilderPolicy.SESSION_TTL_SECONDS)

            if AutoAgentBuilderPolicy.is_confident_enough(spec):
                return await self._create_and_respond(
                    spec, request, session_id, now, expires,
                    create_agent_use_case=create_agent_use_case,
                )

            session = AutoBuildSession(
                session_id=session_id,
                user_id=request.user_id,
                user_request=request.user_request,
                model_name=request.model_name,
                conversation_turns=[
                    ConversationTurn(questions=spec.clarifying_questions, answers=[])
                ],
                attempt_count=1,
                status="pending",
                created_at=now,
                expires_at=expires,
            )
            await self._session_repo.save(session)

            self._logger.info(
                "AutoBuildUseCase needs_clarification",
                request_id=request.request_id,
                session_id=session_id,
                questions_count=len(spec.clarifying_questions),
            )
            return AutoBuildResponse(
                status="needs_clarification",
                session_id=session_id,
                questions=spec.clarifying_questions,
                partial_info=spec.reasoning,
            )

        except Exception as e:
            self._logger.error(
                "AutoBuildUseCase failed",
                exception=e,
                request_id=request.request_id,
            )
            raise

    async def _create_and_respond(
        self, spec, request: AutoBuildRequest, session_id: str,
        now: datetime, expires: datetime,
        *,
        create_agent_use_case,
    ) -> AutoBuildResponse:
        from src.application.middleware_agent.schemas import (
            CreateMiddlewareAgentRequest,
            MiddlewareConfigRequest,
        )
        create_request = CreateMiddlewareAgentRequest(
            user_id=request.user_id,
            name=request.name or f"auto-{spec.tool_ids[0] if spec.tool_ids else 'agent'}",
            description=f"자동 생성: {request.user_request[:100]}",
            system_prompt=spec.system_prompt,
            model_name=request.model_name,
            tool_ids=spec.tool_ids,
            middleware=[
                MiddlewareConfigRequest(
                    type=m["type"],
                    config=m.get("config", {}),
                    sort_order=i,
                )
                for i, m in enumerate(spec.middleware_configs)
            ],
            request_id=request.request_id,
        )
        created = await create_agent_use_case.execute(create_request)

        session = AutoBuildSession(
            session_id=session_id,
            user_id=request.user_id,
            user_request=request.user_request,
            model_name=request.model_name,
            attempt_count=1,
            status="created",
            created_agent_id=created.agent_id,
            created_at=now,
            expires_at=expires,
        )
        await self._session_repo.save(session)

        return AutoBuildResponse(
            status="created",
            session_id=session_id,
            agent_id=created.agent_id,
            explanation=spec.reasoning,
            tool_ids=spec.tool_ids,
            middlewares_applied=[m["type"] for m in spec.middleware_configs],
        )
