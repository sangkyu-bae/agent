"""InterviewUseCase: Human-in-the-Loop 인터뷰 방식 에이전트 생성."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.interview_session_store import (
    InMemoryInterviewSessionStore,
    InterviewSession,
    QAPair,
)
from src.application.agent_builder.interviewer import Interviewer
from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.schemas import (
    AgentDraftPreview,
    CreateAgentResponse,
    InterviewAnswerRequest,
    InterviewAnswerResponse,
    InterviewFinalizeRequest,
    InterviewStartRequest,
    InterviewStartResponse,
    WorkerInfo,
)
from src.application.agent_builder.tool_selector import ToolSelector
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AgentBuilderPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class InterviewUseCase:
    """Human-in-the-Loop 인터뷰를 통한 에이전트 생성 오케스트레이션."""

    def __init__(
        self,
        interviewer: Interviewer,
        tool_selector: ToolSelector,
        prompt_generator: PromptGenerator,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        session_store: InMemoryInterviewSessionStore,
        logger: LoggerInterface,
    ) -> None:
        self._interviewer = interviewer
        self._selector = tool_selector
        self._generator = prompt_generator
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._store = session_store
        self._logger = logger

    async def start(
        self, request: InterviewStartRequest, request_id: str
    ) -> InterviewStartResponse:
        """인터뷰 시작: 초기 명확화 질문 생성 + 세션 저장."""
        self._logger.info("InterviewUseCase start", request_id=request_id, user_id=request.user_id)
        try:
            llm_model_id = await self._resolve_llm_model_id(
                request.llm_model_id, request_id
            )
            questions = await self._interviewer.generate_initial_questions(
                request.user_request, request_id
            )
            session = InterviewSession(
                session_id=str(uuid.uuid4()),
                user_request=request.user_request,
                name=request.name,
                user_id=request.user_id,
                llm_model_id=llm_model_id,
                status="questioning",
                current_questions=questions,
            )
            self._store.create(session)
            self._logger.info(
                "InterviewUseCase start done",
                request_id=request_id,
                session_id=session.session_id,
            )
            return InterviewStartResponse(session_id=session.session_id, questions=questions)
        except Exception as e:
            self._logger.error("InterviewUseCase start failed", exception=e, request_id=request_id)
            raise

    async def answer(
        self,
        session_id: str,
        request: InterviewAnswerRequest,
        request_id: str,
    ) -> InterviewAnswerResponse:
        """답변 수신 → 완성도 평가 → 추가 질문 OR 초안 미리보기."""
        self._logger.info(
            "InterviewUseCase answer", request_id=request_id, session_id=session_id
        )
        try:
            session = self._store.get(session_id)
            if session is None:
                raise ValueError(f"인터뷰 세션을 찾을 수 없습니다: {session_id}")

            # Q&A 누적
            for question, answer in zip(session.current_questions, request.answers):
                session.qa_pairs.append(QAPair(question=question, answer=answer))

            # 완성도 평가
            sufficient, followup_questions = await self._interviewer.evaluate_and_get_followup(
                session.user_request, session.qa_pairs, request_id
            )

            if not sufficient:
                session.status = "questioning"
                session.current_questions = followup_questions
                self._store.update(session)
                return InterviewAnswerResponse(
                    session_id=session_id,
                    status="questioning",
                    questions=followup_questions,
                )

            # 충분한 정보 수집 → 초안 생성
            enriched_context = self._interviewer.build_enriched_context(
                session.user_request, session.qa_pairs
            )
            skeleton = await self._selector.select(enriched_context, request_id)
            tool_metas = [get_tool_meta(w.tool_id) for w in skeleton.workers]
            system_prompt = await self._generator.generate(
                enriched_context, skeleton, tool_metas, request_id
            )

            session.draft_skeleton = skeleton
            session.draft_system_prompt = system_prompt
            session.status = "reviewing"
            self._store.update(session)

            preview = AgentDraftPreview(
                tool_ids=[w.tool_id for w in skeleton.workers],
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                    )
                    for w in skeleton.workers
                ],
                flow_hint=skeleton.flow_hint,
                system_prompt=system_prompt,
            )
            self._logger.info(
                "InterviewUseCase answer done — reviewing",
                request_id=request_id,
                session_id=session_id,
            )
            return InterviewAnswerResponse(
                session_id=session_id, status="reviewing", preview=preview
            )
        except Exception as e:
            self._logger.error(
                "InterviewUseCase answer failed", exception=e, request_id=request_id
            )
            raise

    async def finalize(
        self,
        session_id: str,
        request: InterviewFinalizeRequest,
        request_id: str,
    ) -> CreateAgentResponse:
        """초안 확정 + 사용자 프롬프트 수정 반영 → DB 저장."""
        self._logger.info(
            "InterviewUseCase finalize", request_id=request_id, session_id=session_id
        )
        try:
            session = self._store.get(session_id)
            if session is None:
                raise ValueError(f"인터뷰 세션을 찾을 수 없습니다: {session_id}")
            if session.draft_skeleton is None:
                raise ValueError("아직 초안이 생성되지 않았습니다. 먼저 답변을 완료해주세요.")

            final_prompt = request.system_prompt or session.draft_system_prompt
            AgentBuilderPolicy.validate_system_prompt(final_prompt)
            AgentBuilderPolicy.validate_tool_count(len(session.draft_skeleton.workers))

            now = datetime.now(timezone.utc)
            agent = AgentDefinition(
                id=str(uuid.uuid4()),
                user_id=session.user_id,
                name=session.name,
                description=session.user_request,
                system_prompt=final_prompt,
                flow_hint=session.draft_skeleton.flow_hint,
                workers=session.draft_skeleton.workers,
                llm_model_id=session.llm_model_id,
                status="active",
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(agent, request_id)
            self._store.delete(session_id)

            self._logger.info(
                "InterviewUseCase finalize done",
                request_id=request_id,
                agent_id=saved.id,
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
                llm_model_id=saved.llm_model_id,
                visibility=saved.visibility,
                department_id=saved.department_id,
                temperature=saved.temperature,
                created_at=saved.created_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "InterviewUseCase finalize failed", exception=e, request_id=request_id
            )
            raise

    async def _resolve_llm_model_id(
        self, llm_model_id: str | None, request_id: str
    ) -> str:
        """요청에 model_id가 없으면 기본 모델 사용."""
        if llm_model_id:
            found = await self._llm_model_repository.find_by_id(
                llm_model_id, request_id
            )
            if found is None:
                raise ValueError(f"LLM 모델을 찾을 수 없습니다: {llm_model_id}")
            return found.id

        default = await self._llm_model_repository.find_default(request_id)
        if default is None:
            raise ValueError("기본 LLM 모델이 설정되지 않았습니다.")
        return default.id
