"""AutoBuildReplyUseCase: 보충 답변 수신 → 재추론 → 에이전트 생성."""
from dataclasses import replace

from src.application.auto_agent_builder.agent_spec_inference_service import AgentSpecInferenceService
from src.application.auto_agent_builder.schemas import AutoBuildReplyRequest, AutoBuildResponse
from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.auto_agent_builder.interfaces import AutoBuildSessionRepositoryInterface
from src.domain.auto_agent_builder.policies import AutoAgentBuilderPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AutoBuildReplyUseCase:

    def __init__(
        self,
        inference_service: AgentSpecInferenceService,
        session_repository: AutoBuildSessionRepositoryInterface,
        create_agent_use_case,
        logger: LoggerInterface,
    ) -> None:
        self._inference = inference_service
        self._session_repo = session_repository
        self._create_agent = create_agent_use_case
        self._logger = logger

    async def execute(
        self, session_id: str, request: AutoBuildReplyRequest
    ) -> AutoBuildResponse:
        self._logger.info(
            "AutoBuildReplyUseCase start",
            request_id=request.request_id,
            session_id=session_id,
        )
        try:
            session = await self._session_repo.find(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")

            session.add_answers(request.answers)
            session.attempt_count += 1

            available_ids = {t.tool_id for t in get_all_tools()}

            if AutoAgentBuilderPolicy.should_force_create(session):
                self._logger.info(
                    "AutoBuildReplyUseCase force_create",
                    request_id=request.request_id,
                    session_id=session_id,
                )
                spec = await self._inference.infer(
                    session.user_request,
                    session.conversation_turns,
                    request.request_id,
                    session.model_name,
                )
                AutoAgentBuilderPolicy.validate_tool_ids(spec.tool_ids, available_ids)
                forced = replace(spec, clarifying_questions=[])
                return await self._do_create(forced, session, request.request_id)

            spec = await self._inference.infer(
                session.user_request,
                session.conversation_turns,
                request.request_id,
                session.model_name,
            )
            AutoAgentBuilderPolicy.validate_tool_ids(spec.tool_ids, available_ids)

            if AutoAgentBuilderPolicy.is_confident_enough(spec):
                return await self._do_create(spec, session, request.request_id)

            session.add_questions(spec.clarifying_questions)
            await self._session_repo.save(session)

            self._logger.info(
                "AutoBuildReplyUseCase needs_clarification again",
                request_id=request.request_id,
                session_id=session_id,
            )
            return AutoBuildResponse(
                status="needs_clarification",
                session_id=session_id,
                questions=spec.clarifying_questions,
                partial_info=spec.reasoning,
            )

        except Exception as e:
            self._logger.error(
                "AutoBuildReplyUseCase failed",
                exception=e,
                request_id=request.request_id,
                session_id=session_id,
            )
            raise

    async def _do_create(self, spec, session, request_id: str) -> AutoBuildResponse:
        from src.application.middleware_agent.schemas import (
            CreateMiddlewareAgentRequest,
            MiddlewareConfigRequest,
        )
        create_request = CreateMiddlewareAgentRequest(
            user_id=session.user_id,
            name=f"auto-{spec.tool_ids[0] if spec.tool_ids else 'agent'}",
            description=f"자동 생성: {session.user_request[:100]}",
            system_prompt=spec.system_prompt,
            model_name=session.model_name,
            tool_ids=spec.tool_ids,
            middleware=[
                MiddlewareConfigRequest(type=m["type"], config=m.get("config", {}), sort_order=i)
                for i, m in enumerate(spec.middleware_configs)
            ],
            request_id=request_id,
        )
        created = await self._create_agent.execute(create_request)
        session.status = "created"
        session.created_agent_id = created.agent_id
        await self._session_repo.save(session)

        self._logger.info(
            "AutoBuildReplyUseCase created",
            request_id=request_id,
            session_id=session.session_id,
            agent_id=created.agent_id,
        )
        return AutoBuildResponse(
            status="created",
            session_id=session.session_id,
            agent_id=created.agent_id,
            explanation=spec.reasoning,
            tool_ids=spec.tool_ids,
            middlewares_applied=[m["type"] for m in spec.middleware_configs],
        )
