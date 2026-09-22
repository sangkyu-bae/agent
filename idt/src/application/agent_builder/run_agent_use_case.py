"""RunAgentUseCase: DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 실행.

AGENT-OBS-001 §5-1 통합:
- RunTracker 주입으로 ai_run 라이프사이클 관리
- UsageCallback 등록으로 모든 LLM 호출 자동 수집
- ContextVar로 RAG/Summarizer에 RunContext 전파
- user_message 저장은 graph 실행 전으로 이동 (user_message_id를 ai_run에 연결)

agent-run-streaming-sse Design §5.2 (2026-05-24):
- stream(): transport-독립 AsyncIterator[AgentRunEvent] 반환
- execute(): stream()을 내부 소비해 기존 RunAgentResponse 반환 (호환성 유지)
- LangGraph graph.ainvoke → graph.astream_events(version="v2") 전환
"""
import asyncio
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.application.agent_builder.search_pipeline import (
    format_search_result,
    is_search_result,
    is_worker_output,
)
from src.application.agent_builder.supervisor_nodes import build_initial_state
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.agent_run.auth_context import (
    reset_current_auth_context,
    set_current_auth_context,
)
from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.domain.agent_run.auth_context import AuthContext
from src.application.agent_run.step_tracking import _INPUT_SUMMARY_MAX_CHARS
from src.application.agent_run.tracker import RunTracker
from src.application.conversation.interfaces import ConversationSummarizerInterface
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from src.domain.approval.entity import (
    ApprovalRequest,
    GateSettings,
    ResumeSnapshot,
)
from src.domain.approval.policies import ApprovalPolicy
from src.infrastructure.approval.snapshot import SnapshotSerializer
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.rag_tool_config import clamp_llm_name
from src.domain.agent_builder.policies import (
    AccessCheckInput,
    IterationLimitPolicy,
    VisibilityPolicy,
)
from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.agent_skill.policies import InjectableSkill, SkillInjectionPolicy
from src.domain.agent_builder.schemas import (
    AgentDefinition,
    SupervisorConfig,
    WorkflowDefinition,
)
from src.domain.agent_run.value_objects import (
    AgentRunEvent,
    AgentRunEventType,
    NodeType,
    RunId,
)
from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy
from src.domain.conversation.entities import ConversationMessage, ConversationSummary
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.domain.llm.message_content import coerce_message_text
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import make_agent_run_tracer
from src.infrastructure.langsmith.trace_extractor import TraceExtractor
from src.infrastructure.llm.usage_callback import UsageCallback
from src.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationMessageRepository,
)


_PREVIEW_MAX = _INPUT_SUMMARY_MAX_CHARS  # 1024 chars (Design §7.4)
_RUN_FAILED_CODE_GRAPH = "GRAPH_EXEC_FAILED"
_STEP_NAME_SUPERVISOR = "supervisor"  # agent-chat-reasoning-display §10.1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _SeqCounter:
    """AgentRunEvent.seq 단조 증가 카운터 (1부터)."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


@dataclass
class _StreamState:
    """stream() 실행 중 변경 가능한 누적 상태."""

    token_acc: dict[str, list[str]] = field(default_factory=dict)
    node_start_ts: dict[str, datetime] = field(default_factory=dict)
    tool_start_ts: dict[str, datetime] = field(default_factory=dict)
    final_messages: list = field(default_factory=list)
    # agent-recursion-limit D7: supervisor 가드의 limit_reached 캡처 → payload 플래그.
    limit_reached: bool = False
    # supervisor-chart-builder-node: chart_builder 노드가 생성한 Chart.js config.
    charts: list = field(default_factory=list)
    # analysis-source-preservation: analysis_node가 방출한 원천 데이터 채널.
    analysis_source: list = field(default_factory=list)
    # approval-gate Design §2.1 ④: 게이트가 차단한 도구 호출 신호 (limit_reached 동형).
    approval_pending: dict = field(default_factory=dict)
    # approval-gate Design §3.1(v0.2): 재개용 최종 SupervisorState 스냅샷.
    # 최상위 chain_end 출력이 전체 상태다 — 워커 진입 후크가 없어 최종 상태를 쓴다.
    final_state: dict = field(default_factory=dict)


def _effective_model_id(agent: Any, request: RunAgentRequest) -> str:
    """요청 오버라이드가 있으면 그것을, 없으면 에이전트 설정을 쓴다 (D1).

    _prepare_graph(컴파일)와 _begin_observability(기록)가 같은 답을 내야
    ai_run.llm_model_id가 실제 호출된 모델을 가리킨다 (Plan FR-02).
    """
    return request.llm_model_id_override or agent.llm_model_id


def _effective_temperature(agent: Any, request: RunAgentRequest) -> float:
    """temperature 오버라이드 해석 (D9).

    0.0은 falsy이므로 `or`를 쓰면 에이전트 값으로 새어나가 재현성이 깨진다.
    """
    if request.temperature_override is not None:
        return request.temperature_override
    return agent.temperature


def _node_type_for(name: str) -> NodeType:
    if name == "supervisor":
        return NodeType.SUPERVISOR
    if name == "quality_gate":
        return NodeType.GATE
    if name == "final_answer":
        return NodeType.OTHER
    return NodeType.WORKER


def _truncate_json(obj: Any, max_chars: int = _PREVIEW_MAX) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        text = str(obj)
    return text[:max_chars] if len(text) > max_chars else text


def _collect_node_names(workflow: WorkflowDefinition) -> set[str]:
    """WorkflowCompiler가 graph.add_node로 등록할 노드 이름 집합."""
    names = {"supervisor", "quality_gate", "final_answer"}
    for w in workflow.workers:
        names.add(w.worker_id)
    return names


def _has_excel_attachment(attachments: list[dict] | None) -> bool:
    """analysis-data-continuity §3.3: 엑셀 첨부 턴 판정 (excel 항목 수집 조건)."""
    return any(a.get("type") == "excel" for a in attachments or [])


class RunAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        compiler: WorkflowCompiler,
        logger: LoggerInterface,
        message_repo: ConversationMessageRepository,
        summary_repo: ConversationSummaryRepository,
        summarizer: ConversationSummarizerInterface,
        policy: SummarizationPolicy,
        tracker: Optional[RunTracker] = None,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        agent_skill_repo: Optional[AgentSkillRepositoryInterface] = None,
        snapshot_policy: Optional[AnalysisSnapshotPolicy] = None,
        # approval-gate Design §2.1 ④: session -> ApprovalRepository 팩토리.
        # 미주입이면 적재를 건너뛴다 (기존 호출자 무회귀).
        approval_repo_factory=None,
        approval_gate_config: Optional[dict] = None,
        # Check G4: (session, agent_id, request_id) -> 게이트 config
        approval_gate_config_resolver=None,
    ) -> None:
        self._repository = repository
        self._approval_repo_factory = approval_repo_factory
        self._approval_gate_config = approval_gate_config
        self._approval_gate_config_resolver = approval_gate_config_resolver
        self._llm_model_repository = llm_model_repository
        self._compiler = compiler
        self._logger = logger
        self._message_repo = message_repo
        self._summary_repo = summary_repo
        self._summarizer = summarizer
        self._policy = policy
        self._tracker = tracker  # None이면 관측성 비활성 (개발/테스트)
        # skill-agent-integration Phase A: 부착 Skill instruction 주입용 저장소.
        # None이면 주입 비활성 → 기존 동작 100% 유지.
        self._agent_skill_repo = agent_skill_repo
        # AGENT-OBS-001 fix: user_message는 별도 세션에서 즉시 commit해야
        # Tracker의 별도 세션 ai_run INSERT가 FK 락 대기에 빠지지 않는다.
        self._session_factory = session_factory
        # analysis-data-continuity: 분석 데이터 스냅샷 영속·재주입 정책.
        # None이면 기능 비활성 → 기존 동작 100% 유지 (하위호환).
        self._snapshot_policy = snapshot_policy

    # ── Public API ─────────────────────────────────────────────────────

    async def stream(
        self,
        agent_id: str,
        request: RunAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_department_ids: list[str] | None = None,
        *,
        auth_ctx: AuthContext | None = None,
    ) -> AsyncIterator[AgentRunEvent]:
        """transport-독립 SSE/WS용 이벤트 스트림 (Design §5.2.2).

        이벤트 시퀀스:
            RUN_STARTED → (NODE_STARTED|NODE_COMPLETED|TOOL_*|TOKEN)*
            → ANSWER_COMPLETED → RUN_COMPLETED
            (예외 시 ANSWER 대신 RUN_FAILED, generator는 정상 종료)
        """
        seq = _SeqCounter()
        # pipeline-langsmith-tracing FR-07: 전역 `langsmith()` 제거.
        # `_build_graph_config` 의 per-run tracer(make_agent_run_tracer)가 이미
        # 프로젝트를 지정하므로 기능 손실이 없고, 전역을 켜면 이후 다른 경로의
        # run 까지 'agent-run' 으로 흘러간다.
        self._logger.info(
            "RunAgentUseCase.stream start",
            request_id=request_id, agent_id=agent_id,
        )

        agent = await self._authorize_and_load(
            agent_id, request_id, viewer_user_id, viewer_department_ids,
        )
        session_id = request.session_id or str(uuid.uuid4())
        user_message_id = await self._save_user_message(
            request.query, request.user_id, session_id, agent_id,
            persist=request.persist_conversation,
        )

        run_id, callback, ctx_token = await self._begin_observability(
            agent=agent, request=request, session_id=session_id,
            user_message_id=user_message_id, agent_id=agent_id,
            request_id=request_id,
        )

        # agent-user-context Design §4.4.1: AuthContext ContextVar 세팅
        # — graph 외부 호출(Tool, Repository)에서 fallback 조회 가능하게 함.
        auth_token = (
            set_current_auth_context(auth_ctx) if auth_ctx is not None else None
        )

        yield self._build_event(
            seq, AgentRunEventType.RUN_STARTED, run_id,
            {
                "run_id": run_id.value if run_id is not None else None,
                "session_id": session_id,
                "agent_id": agent_id,
            },
        )

        state = _StreamState()
        try:
            graph, initial_state, graph_config = await self._prepare_graph(
                agent=agent, request=request, session_id=session_id,
                callback=callback, run_id=run_id, request_id=request_id,
                auth_ctx=auth_ctx,
            )
            node_names = _collect_node_names(agent.to_workflow_definition())

            async for raw_ev in graph.astream_events(
                initial_state, config=graph_config, version="v2",
            ):
                mapped = self._map_event(raw_ev, seq, run_id, node_names, state)
                if mapped is not None:
                    yield mapped
                # agent-chat-reasoning-display §4.1: NODE_COMPLETED(supervisor) 직후
                extra = self._maybe_supervisor_reasoning(raw_ev, seq, run_id)
                if extra is not None:
                    yield extra

            answer, tools_used = self._parse_result({"messages": state.final_messages})
            # analysis-data-continuity D3: 턴의 분석 원천 데이터 스냅샷 수집.
            # analysis-source-preservation: 엑셀 원천(state.analysis_source) 병합.
            snapshot = self._collect_snapshot(
                request, state.final_messages, state.analysis_source,
            )
            # chat-chart-persistence D5: 차트 페이로드를 메시지와 함께 영속화.
            # 빈 리스트는 None으로 저장 (D2) — 재진입 시 이력 API가 복원.
            await self._save_assistant_message(
                answer, request.user_id, session_id, agent_id,
                charts=state.charts or None,
                analysis_data=snapshot,
                persist=request.persist_conversation,
            )
            # approval-gate Design §2.1 ④: 게이트가 걸렸으면 승인 요청을 영속한다.
            # 답변 이벤트보다 먼저 — 사용자가 "승인 대기" 문구를 본 시점에는
            # 이미 대기함에 건이 있어야 한다.
            approval_id = await self._persist_approval_if_pending(
                agent=agent, state=state, run_id=run_id,
                request=request, request_id=request_id,
                session_id=session_id,
            )
            answer_payload: dict = {"answer": answer, "tools_used": tools_used}
            if approval_id:
                answer_payload["approval_pending"] = True
                answer_payload["approval_id"] = approval_id
            # agent-recursion-limit D7: True일 때만 부착 (charts 선례와 동형).
            if state.limit_reached:
                answer_payload["limit_reached"] = True
            if state.charts:
                answer_payload["charts"] = state.charts
            yield self._build_event(
                seq, AgentRunEventType.ANSWER_COMPLETED, run_id, answer_payload,
            )

            run_url: Optional[str] = None
            if self._tracker is not None and run_id is not None:
                trace_id, run_url = TraceExtractor.extract()
                await self._tracker.complete_run(
                    run_id,
                    langsmith_trace_id=trace_id,
                    langsmith_run_url=run_url,
                )

            yield self._build_event(
                seq, AgentRunEventType.RUN_COMPLETED, run_id,
                {
                    "run_id": run_id.value if run_id is not None else None,
                    "langsmith_run_url": run_url,
                },
            )
        except asyncio.CancelledError as ce:
            self._logger.warning(
                "RunAgentUseCase.stream cancelled",
                request_id=request_id,
            )
            if self._tracker is not None and run_id is not None:
                await self._tracker.fail_run(run_id, ce)
            raise
        except GraphRecursionError as gre:
            # agent-recursion-limit D9: 파생 recursion_limit(D3)으로 도달 확률은
            # 낮지만, 발동 시에도 축적 메시지로 강등 답변을 시도한다 (오류 대신 답변).
            async for ev in self._degraded_completion_events(
                gre, seq=seq, run_id=run_id, state=state,
                request=request, session_id=session_id,
                agent_id=agent_id, request_id=request_id,
            ):
                yield ev
        except Exception as e:
            self._logger.error(
                "RunAgentUseCase.stream failed",
                exception=e, request_id=request_id,
            )
            if self._tracker is not None and run_id is not None:
                await self._tracker.fail_run(run_id, e)
            yield self._build_event(
                seq, AgentRunEventType.RUN_FAILED, run_id,
                {"code": _RUN_FAILED_CODE_GRAPH, "message": str(e)[:512]},
            )
        finally:
            if ctx_token is not None:
                reset_run_context(ctx_token)
            if auth_token is not None:
                reset_current_auth_context(auth_token)

    async def execute(
        self,
        agent_id: str,
        request: RunAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_department_ids: list[str] | None = None,
        *,
        auth_ctx: AuthContext | None = None,
    ) -> RunAgentResponse:
        """기존 시그니처. stream()을 내부 소비하여 RunAgentResponse 조립.

        Breaking change 0: 호출자(테스트, 라우터, 외부)는 코드 변경 불필요.
        auth_ctx는 키워드 전용으로 추가 — 기존 호출자는 영향 없음.
        """
        final_answer = ""
        tools_used: list[str] = []
        run_id_str: Optional[str] = None
        session_id: str = request.session_id or ""
        failure_message: Optional[str] = None

        async for ev in self.stream(
            agent_id, request, request_id,
            viewer_user_id, viewer_department_ids,
            auth_ctx=auth_ctx,
        ):
            if ev.event_type == AgentRunEventType.RUN_STARTED:
                run_id_str = ev.payload.get("run_id")
                session_id = ev.payload.get("session_id", session_id)
            elif ev.event_type == AgentRunEventType.ANSWER_COMPLETED:
                final_answer = ev.payload["answer"]
                tools_used = list(ev.payload["tools_used"])
            elif ev.event_type == AgentRunEventType.RUN_FAILED:
                failure_message = ev.payload.get("message", "unknown failure")

        if failure_message is not None:
            raise RuntimeError(failure_message)

        return RunAgentResponse(
            agent_id=agent_id,
            query=request.query,
            answer=final_answer,
            tools_used=tools_used,
            request_id=request_id,
            session_id=session_id,
            run_id=run_id_str,
        )

    async def _degraded_completion_events(
        self,
        error: GraphRecursionError,
        *,
        seq: _SeqCounter,
        run_id: Optional[RunId],
        state: _StreamState,
        request: RunAgentRequest,
        session_id: str,
        agent_id: str,
        request_id: str,
    ) -> AsyncIterator[AgentRunEvent]:
        """GraphRecursionError 안전망 (agent-recursion-limit D9).

        축적 메시지(state.final_messages)로 답변을 구성할 수 있으면 정상 완료
        시퀀스(ANSWER_COMPLETED[limit_reached]→RUN_COMPLETED)로 강등 처리하고,
        불가능할 때만 기존 RUN_FAILED 경로를 따른다.
        """
        self._logger.warning(
            "RunAgentUseCase.stream recursion limit hit — degraded completion",
            request_id=request_id, error=str(error)[:256],
        )
        answer, tools_used = self._parse_result({"messages": state.final_messages})
        if not answer:
            if self._tracker is not None and run_id is not None:
                await self._tracker.fail_run(run_id, error)
            yield self._build_event(
                seq, AgentRunEventType.RUN_FAILED, run_id,
                {"code": _RUN_FAILED_CODE_GRAPH, "message": str(error)[:512]},
            )
            return

        snapshot = self._collect_snapshot(
            request, state.final_messages, state.analysis_source,
        )
        await self._save_assistant_message(
            answer, request.user_id, session_id, agent_id,
            charts=state.charts or None,
            analysis_data=snapshot,
            persist=request.persist_conversation,
        )
        yield self._build_event(
            seq, AgentRunEventType.ANSWER_COMPLETED, run_id,
            {"answer": answer, "tools_used": tools_used, "limit_reached": True},
        )
        run_url: Optional[str] = None
        if self._tracker is not None and run_id is not None:
            trace_id, run_url = TraceExtractor.extract()
            await self._tracker.complete_run(
                run_id, langsmith_trace_id=trace_id, langsmith_run_url=run_url,
            )
        yield self._build_event(
            seq, AgentRunEventType.RUN_COMPLETED, run_id,
            {
                "run_id": run_id.value if run_id is not None else None,
                "langsmith_run_url": run_url,
            },
        )

    # ── Stream helpers ─────────────────────────────────────────────────

    async def _authorize_and_load(
        self,
        agent_id: str,
        request_id: str,
        viewer_user_id: str | None,
        viewer_department_ids: list[str] | None,
    ) -> AgentDefinition:
        agent = await self._repository.find_by_id(agent_id, request_id)
        if agent is None:
            raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

        if viewer_user_id is not None:
            ac = AccessCheckInput(
                agent_owner_id=agent.user_id,
                agent_visibility=agent.visibility,
                agent_department_id=agent.department_id,
                viewer_user_id=viewer_user_id,
                viewer_department_ids=viewer_department_ids or [],
                viewer_role="user",
            )
            if not VisibilityPolicy.can_access(ac):
                raise PermissionError("이 에이전트에 대한 실행 권한이 없습니다")
        return agent

    async def _begin_observability(
        self,
        *,
        agent: AgentDefinition,
        request: RunAgentRequest,
        session_id: str,
        user_message_id: int | None,
        agent_id: str,
        request_id: str,
    ) -> tuple[Optional[RunId], Optional[UsageCallback], Any]:
        """RunTracker.start_run + UsageCallback 생성 + RunContext 설정."""
        if self._tracker is None:
            return None, None, None

        run_id = RunId(str(uuid.uuid4()))
        try:
            await self._tracker.start_run(
                run_id=run_id,
                conversation_id=session_id,
                user_id=request.user_id,
                agent_id=agent_id,
                # Plan FR-02: 실효 모델을 기록해야 토큰·비용이 실제로 호출된
                # 모델에 귀속된다. 원본 모델로 찍으면 스윕 집계가 통째로 틀어진다.
                agent_llm_model_id=_effective_model_id(agent, request),
                user_message_id=user_message_id,
                langgraph_thread_id=session_id,
            )
        except RuntimeError as e:
            # 관측성 시작 실패는 본 흐름을 막지 않는다 (degraded mode).
            self._logger.warning(
                "Observability degraded — start_run failed, continuing",
                exception=e,
                request_id=request_id,
            )
            return None, None, None

        callback = UsageCallback(
            tracker=self._tracker,
            run_id=run_id,
            user_id=request.user_id,
            agent_id=agent_id,
            logger=self._logger,
        )
        ctx_token = set_current_run_context(
            RunContext(
                run_id=run_id,
                user_id=request.user_id,
                agent_id=agent_id,
                callback=callback,
            )
        )
        return run_id, callback, ctx_token

    async def _prepare_graph(
        self,
        *,
        agent: AgentDefinition,
        request: RunAgentRequest,
        session_id: str,
        callback: Optional[UsageCallback],
        run_id: Optional[RunId],
        request_id: str,
        auth_ctx: AuthContext | None = None,
    ) -> tuple[Any, dict, dict]:
        """messages 빌드 + llm_model 로드 + compile + initial_state + graph_config."""
        messages = await self._build_messages(
            request.query,
            request.user_id,
            session_id,
            request.session_id is not None,
        )

        # agent-model-benchmark D1: 모델·temperature 오버라이드 해석 단일 지점.
        # 하위 컴포넌트(컴파일러·워커·툴)는 오버라이드의 존재를 알지 못한다.
        model_id = _effective_model_id(agent, request)
        llm_model = await self._llm_model_repository.find_by_id(model_id, request_id)
        if llm_model is None:
            raise ValueError(
                f"에이전트에 연결된 LLM 모델을 찾을 수 없습니다: {model_id}"
            )

        workflow = agent.to_workflow_definition()
        workflow = await self._inject_attached_skills(workflow, agent, request_id)
        # agent-recursion-limit D1: 에이전트별 반복 한도를 단일 소스로 주입.
        sv_config = SupervisorConfig(max_iterations=agent.max_iterations)
        graph = await self._compiler.compile(
            workflow=workflow,
            llm_model=llm_model,
            temperature=_effective_temperature(agent, request),
            request_id=request_id,
            supervisor_config=sv_config,
            depth=0,
            visited={agent.id},
            tracker=self._tracker,
            callback=callback,
            run_id=run_id,
            auth_ctx=auth_ctx,
            include_user_context=agent.include_user_context,
            # wiki-agentic-navigation D2: wiki_read 목차 활성 조건 (최상위만)
            agent_id=agent.id,
        )

        initial_state = build_initial_state(
            messages=messages,
            config=sv_config,
            available_workers=[w.worker_id for w in workflow.workers],
            attachments=getattr(request, "attachments", None),
        )

        graph_config = self._build_graph_config(
            agent=agent, session_id=session_id, run_id=run_id,
            user_id=request.user_id, callback=callback,
        )
        return graph, initial_state, graph_config

    async def _inject_attached_skills(
        self,
        workflow: WorkflowDefinition,
        agent: AgentDefinition,
        request_id: str,
    ) -> WorkflowDefinition:
        """부착 Skill instruction을 supervisor_prompt에 병합 (Design §2.3/D3).

        agent_skill_repo 미주입(None)이거나 부착 0개면 workflow를 그대로 반환한다.
        compile 내부의 user_context_block prepend는 병합 결과 위에 최외곽으로 적용된다.
        """
        if self._agent_skill_repo is None:
            return workflow
        skills = await self._agent_skill_repo.list_attached_skills(
            agent.id, request_id
        )
        if not skills:
            return workflow
        injectables = [
            InjectableSkill(name=s.name, instruction=s.instruction, sort_order=i)
            for i, s in enumerate(skills)
        ]
        merged = SkillInjectionPolicy.merge(workflow.supervisor_prompt, injectables)
        self._logger.info(
            "skill injection applied",
            request_id=request_id, agent_id=agent.id, attached=len(skills),
        )
        return replace(workflow, supervisor_prompt=merged)

    @staticmethod
    def _build_graph_config(
        *,
        agent: AgentDefinition,
        session_id: str,
        run_id: Optional[RunId],
        user_id: str,
        callback: Optional[UsageCallback],
    ) -> dict:
        """LangGraph 실행 config — 에이전트별 LangSmith 프로젝트/네이밍.

        agent-run-langsmith-per-agent-project Design §3.2.2:
        - run_name=에이전트명, tags·metadata에 agent_name (항상 설정)
        - per-run LangChainTracer를 callbacks 선두에 주입 → 전역 os.environ 변경
          없이 run별 프로젝트 지정(동시성 race 없음). 명시적 tracer가 있으면
          langchain_core가 전역 auto-tracer를 추가하지 않아 중복도 없다.
        """
        tags = ["agent-platform", agent.id, agent.name]
        tracer = make_agent_run_tracer(agent.name, tags=tags)

        callbacks: list = []
        if tracer is not None:
            callbacks.append(tracer)
        if callback is not None:
            callbacks.append(callback)

        metadata: dict = {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "conversation_id": session_id,
            "user_id": user_id,
        }
        if run_id is not None:
            metadata["run_id"] = run_id.value

        config: dict = {
            "configurable": {"thread_id": session_id},
            "run_name": agent.name,
            "tags": tags,
            "metadata": metadata,
            # agent-recursion-limit D3: 시스템 recursion_limit(기본 25 스텝)이
            # state 가드보다 먼저 터지지 않도록 반복 한도에서 파생 설정.
            "recursion_limit": IterationLimitPolicy.derive_recursion_limit(
                agent.max_iterations
            ),
        }
        if callbacks:
            config["callbacks"] = callbacks
        return config

    def _build_event(
        self,
        seq: _SeqCounter,
        event_type: AgentRunEventType,
        run_id: Optional[RunId],
        payload: dict,
    ) -> AgentRunEvent:
        return AgentRunEvent(
            seq=seq.next(),
            event_type=event_type,
            run_id=run_id.value if run_id is not None else None,
            payload=payload,
            timestamp=_utcnow(),
        )

    def _map_event(
        self,
        raw: dict,
        seq: _SeqCounter,
        run_id: Optional[RunId],
        node_names: set[str],
        state: _StreamState,
    ) -> Optional[AgentRunEvent]:
        """LangGraph astream_events(v2) dict → AgentRunEvent (또는 None=skip)."""
        ev_type = raw.get("event", "")
        name = raw.get("name", "")
        data = raw.get("data", {}) or {}

        if ev_type == "on_chain_start":
            return self._map_chain_start(name, node_names, seq, run_id, state)
        if ev_type == "on_chain_end":
            return self._map_chain_end(name, data, node_names, seq, run_id, state)
        if ev_type == "on_tool_start":
            return self._map_tool_start(name, raw, data, seq, run_id, state)
        if ev_type == "on_tool_end":
            return self._map_tool_end(name, raw, data, seq, run_id, state)
        if ev_type == "on_chat_model_stream":
            return self._map_chat_stream(raw, data, seq, run_id, state)
        return None

    def _map_chain_start(
        self, name: str, node_names: set[str],
        seq: _SeqCounter, run_id: Optional[RunId], state: _StreamState,
    ) -> Optional[AgentRunEvent]:
        if name not in node_names:
            return None
        state.node_start_ts[name] = _utcnow()
        return self._build_event(
            seq, AgentRunEventType.NODE_STARTED, run_id,
            {"node_name": name, "node_type": _node_type_for(name).value},
        )

    async def resume_from_snapshot(
        self, approval, *, outcome: str, request_id: str
    ) -> str:
        """approval-gate Design §2.1 — 승인/거절 결과를 주입해 런을 이어 돌린다.

        RunResumerInterface 구현. 재개 실행이 여기 있는 이유는 compile 이
        관측성(tracker/run_id)·스킬 주입·모델 오버라이드까지 아우르기
        때문이다 — 별도 UseCase 가 복제하면 재개 런에서만 조용히 빠진다.

        재개 불가 사유(정의 변경·스키마 불일치·깨진 스냅샷)는 예외로 올리지
        않는다: 집행은 이미 끝났으므로 재개 실패가 집행을 무효로 만들면 안 된다.
        """
        agent = await self._repository.find_by_id(approval.agent_id, request_id)
        if agent is None:
            self._logger.warning(
                "resume skipped — agent not found",
                request_id=request_id, approval_id=approval.id,
            )
            return ""
        if not self._can_resume(agent, approval, request_id):
            return ""
        try:
            state = self._restore_state(approval, outcome)
        except Exception as e:
            self._logger.error(
                "resume snapshot restore failed",
                request_id=request_id, approval_id=approval.id, exception=e,
            )
            return ""
        answer = await self._resume_graph(state, agent, request_id)
        await self._save_resumed_answer(approval, answer, request_id)
        self._logger.info(
            "run resumed", request_id=request_id, approval_id=approval.id,
        )
        return answer

    async def _save_resumed_answer(
        self, approval, answer: str, request_id: str
    ) -> None:
        """재개 답변을 원래 대화 세션에 저장한다.

        Check G1: 이전에는 session_id 를 "" 로 넘겨 SessionId 가 ValueError 를
        던졌고, 호출측이 그 예외를 삼켜 최종 답변이 조용히 유실됐다.
        세션·요청자 신원이 없으면(구버전 행, 웹훅 런) 저장만 건너뛰고
        답변은 반환한다 — 답변 자체를 잃는 것보다 낫다.
        """
        if not approval.session_id or not approval.requested_by:
            self._logger.warning(
                "resumed answer not persisted — missing session or requester",
                request_id=request_id, approval_id=approval.id,
                has_session=bool(approval.session_id),
                has_requester=bool(approval.requested_by),
            )
            return
        await self._save_assistant_message(
            answer, approval.requested_by, approval.session_id,
            approval.agent_id, charts=None, analysis_data=None, persist=True,
        )

    def _can_resume(self, agent, approval, request_id: str) -> bool:
        """스키마 버전 + 에이전트 정의 대조 (FR-14).

        승인 시점에도 검사하지만, 예약 집행은 그 사이에 며칠이 흐른다 —
        집행 직전에 다시 본다.
        """
        if not SnapshotSerializer.is_supported(approval.snapshot.schema_version):
            self._logger.warning(
                "resume skipped — snapshot schema mismatch",
                request_id=request_id, approval_id=approval.id,
                version=approval.snapshot.schema_version,
            )
            return False
        if getattr(agent, "updated_at", None) != approval.snapshot.agent_updated_at:
            self._logger.warning(
                "resume skipped — agent definition changed",
                request_id=request_id, approval_id=approval.id,
            )
            return False
        return True

    @staticmethod
    def _restore_state(approval, outcome: str) -> dict:
        """스냅샷 복원 + 결과 주입 + 종결 신호 초기화.

        approval_pending·next_worker 를 비우지 않으면 재진입 즉시 라우팅이
        다시 __end__ 로 빠져 런이 한 발도 못 나간다.
        """
        state = SnapshotSerializer.loads(approval.snapshot.state_json)
        state["messages"] = list(state.get("messages") or []) + [
            AIMessage(
                content=outcome,
                name=clamp_llm_name(approval.worker_id or "approval"),
            )
        ]
        state["approval_pending"] = {}
        state["next_worker"] = ""
        state["finish_challenge_pending"] = False
        return state

    async def _resume_graph(self, state: dict, agent, request_id: str) -> str:
        """복원 상태로 그래프를 1회 실행하고 최종 답변을 돌려준다."""
        llm_model = await self._llm_model_repository.find_by_id(
            agent.llm_model_id, request_id
        )
        if llm_model is None:
            raise ValueError(f"LLM 모델 없음: {agent.llm_model_id}")
        workflow = agent.to_workflow_definition()
        workflow = await self._inject_attached_skills(workflow, agent, request_id)
        graph = await self._compiler.compile(
            workflow=workflow,
            llm_model=llm_model,
            temperature=agent.temperature,
            request_id=request_id,
            supervisor_config=SupervisorConfig(
                max_iterations=agent.max_iterations
            ),
            depth=0,
            visited={agent.id},
            tracker=self._tracker,
            include_user_context=agent.include_user_context,
            agent_id=agent.id,
        )
        result = await graph.ainvoke(state)
        answer, _ = self._parse_result(result)
        return answer

    async def _persist_approval_if_pending(
        self, *, agent, state, run_id, request, request_id: str,
        session_id: str | None = None,
    ) -> str | None:
        """approval-gate Design §2.1 ④ — 게이트 신호를 ApprovalRequest 로 영속.

        신호가 없으면 아무것도 하지 않는다(게이트 미적용 런은 완전 무회귀).
        리포지토리 팩토리가 미주입이면 경고 후 건너뛴다 — 기존 호출자
        (테스트·구버전 배선)가 깨지지 않게 하는 additive 계약.

        영속 실패를 삼키지 않는 이유: 게이트는 이미 도구를 차단했으므로,
        여기서 실패하면 사용자는 "승인 대기" 를 보는데 대기함에는 아무것도
        없는 상태가 된다. 조용한 유실보다 런 실패가 낫다.
        """
        pending = state.approval_pending
        if not pending:
            return None
        if self._approval_repo_factory is None:
            self._logger.warning(
                "approval pending but repository not wired — skipped",
                request_id=request_id, agent_id=agent.id,
            )
            return None

        payload, truncated = SnapshotSerializer.dumps_with_limit(
            state.final_state or {"messages": state.final_messages}
        )
        if truncated:
            self._logger.warning(
                "resume snapshot truncated", request_id=request_id,
                agent_id=agent.id,
            )
        # Check G4: 게이트 설정 해석과 적재를 같은 세션·트랜잭션에서 한다
        # (한 UseCase 안에서 저장소마다 다른 세션을 쓰지 않는다 — CLAUDE.md).
        async with self._session_factory() as session:
            async with session.begin():
                gate_config = await self._resolve_gate_config(
                    session, agent.id, request_id
                )
                approval = self._build_approval(
                    agent=agent, pending=pending, snapshot_json=payload,
                    run_id=run_id, request=request, request_id=request_id,
                    gate_config=gate_config,
                )
                # Check G1: 재개 답변을 원래 대화로 되돌려 놓기 위해 세션 보존.
                approval.session_id = session_id
                repo = self._approval_repo_factory(session)
                await repo.create(approval, request_id)
        self._logger.info(
            "approval request persisted", request_id=request_id,
            approval_id=approval.id, tool_id=approval.tool_id,
        )
        return approval.id

    async def _resolve_gate_config(
        self, session, agent_id: str, request_id: str
    ) -> dict:
        """Check G4 — 해당 에이전트의 게이트 설정(카탈로그 default ∪ 에이전트 override).

        이전에는 생성자 상수를 읽었고 main.py 가 넘기지 않아 만료가 항상
        168h 였다. 리졸버는 승인 쪽 _GateConfigReader 와 같은 해석 함수를
        공유한다(MergePolicy 단일 출처). 미주입이면 생성자 값 → 도메인 기본.
        """
        resolver = getattr(self, "_approval_gate_config_resolver", None)
        if resolver is not None:
            return await resolver(session, agent_id, request_id) or {}
        return getattr(self, "_approval_gate_config", None) or {}

    def _build_approval(
        self, *, agent, pending: dict, snapshot_json: str, run_id, request,
        request_id: str, gate_config: dict | None = None,
    ):
        now = _utcnow()
        worker_id = pending.get("worker_id", "")
        gate = GateSettings.from_config(gate_config or {}, is_enforced=False)
        return ApprovalRequest(
            id=str(uuid.uuid4()),
            run_id=run_id.value if run_id is not None else "",
            agent_id=agent.id,
            requested_by=request.user_id,
            worker_id=worker_id,
            tool_id=pending.get("tool_id", ""),
            tool_args=pending.get("tool_args") or {},
            draft=pending.get("draft", ""),
            status="pending",
            idempotency_key=ApprovalPolicy.build_idempotency_key(
                run_id=run_id.value if run_id is not None else request_id,
                worker_id=worker_id or "unknown",
                tool_call_id=pending.get("tool_call_id") or request_id,
            ),
            snapshot=ResumeSnapshot(
                schema_version=SnapshotSerializer.SCHEMA_VERSION,
                agent_updated_at=agent.updated_at,
                worker_id=worker_id,
                state_json=snapshot_json,
            ),
            expires_at=ApprovalPolicy.resolve_expires_at(now, gate.expires_hours),
            request_id=request_id,
            created_at=now,
            updated_at=now,
        )

    def _map_chain_end(
        self, name: str, data: dict, node_names: set[str],
        seq: _SeqCounter, run_id: Optional[RunId], state: _StreamState,
    ) -> Optional[AgentRunEvent]:
        # 어떤 chain_end이든 messages가 있으면 final_messages 갱신 (top-level이 마지막)
        output = data.get("output")
        if isinstance(output, dict) and "messages" in output:
            state.final_messages = list(output["messages"])
        # agent-recursion-limit D7: supervisor 가드의 limit_reached 캡처 (latch).
        if isinstance(output, dict) and output.get("limit_reached"):
            state.limit_reached = True
        # supervisor-chart-builder-node: chart_builder 노드 output의 charts 캡처.
        # truthy일 때만 갱신 → 빈 배열이 유효 charts를 덮어쓰지 않음.
        if isinstance(output, dict) and output.get("charts"):
            state.charts = list(output["charts"])
        # analysis-source-preservation: analysis_node output의 원천 데이터 캡처.
        if isinstance(output, dict) and output.get("analysis_source"):
            state.analysis_source = list(output["analysis_source"])
        # approval-gate Design §2.1 ④: 게이트 신호 + 재개 스냅샷 캡처.
        # truthy일 때만 갱신 — 뒤따르는 빈 델타가 유효 신호를 덮지 않는다
        # (charts 캡처와 동형). 스냅샷은 messages를 가진 최신 출력을 쓴다.
        if isinstance(output, dict) and output.get("approval_pending"):
            state.approval_pending = dict(output["approval_pending"])
        if isinstance(output, dict) and "messages" in output:
            state.final_state = dict(output)

        if name not in node_names:
            return None
        start = state.node_start_ts.pop(name, None)
        duration_ms = (
            int((_utcnow() - start).total_seconds() * 1000) if start else 0
        )
        return self._build_event(
            seq, AgentRunEventType.NODE_COMPLETED, run_id,
            {"node_name": name, "duration_ms": duration_ms},
        )

    def _map_tool_start(
        self, name: str, raw: dict, data: dict,
        seq: _SeqCounter, run_id: Optional[RunId], state: _StreamState,
    ) -> AgentRunEvent:
        tool_call_id = raw.get("run_id", "")
        state.tool_start_ts[tool_call_id] = _utcnow()
        return self._build_event(
            seq, AgentRunEventType.TOOL_STARTED, run_id,
            {
                "tool_name": name,
                "tool_call_id": tool_call_id,
                "input_preview": _truncate_json(data.get("input")),
            },
        )

    def _map_tool_end(
        self, name: str, raw: dict, data: dict,
        seq: _SeqCounter, run_id: Optional[RunId], state: _StreamState,
    ) -> AgentRunEvent:
        tool_call_id = raw.get("run_id", "")
        start = state.tool_start_ts.pop(tool_call_id, None)
        duration_ms = (
            int((_utcnow() - start).total_seconds() * 1000) if start else 0
        )
        return self._build_event(
            seq, AgentRunEventType.TOOL_COMPLETED, run_id,
            {
                "tool_name": name,
                "tool_call_id": tool_call_id,
                "output_preview": _truncate_json(data.get("output")),
                "duration_ms": duration_ms,
            },
        )

    def _maybe_supervisor_reasoning(
        self,
        raw: dict,
        seq: _SeqCounter,
        run_id: Optional[RunId],
    ) -> Optional[AgentRunEvent]:
        """supervisor on_chain_end output에 _step_output_summary가 있으면 STEP_REASONING 발행.

        agent-chat-reasoning-display Design §4.1.
        """
        if raw.get("event") != "on_chain_end":
            return None
        if raw.get("name") != _STEP_NAME_SUPERVISOR:
            return None
        output = (raw.get("data", {}) or {}).get("output")
        if not isinstance(output, dict):
            return None
        summary = output.get("_step_output_summary")
        if not summary:
            return None
        return self._build_event(
            seq, AgentRunEventType.STEP_REASONING, run_id,
            {
                "step_name": _STEP_NAME_SUPERVISOR,
                "reasoning": summary,
                "next_worker": output.get("next_worker", ""),
            },
        )

    def _map_chat_stream(
        self, raw: dict, data: dict,
        seq: _SeqCounter, run_id: Optional[RunId], state: _StreamState,
    ) -> Optional[AgentRunEvent]:
        chunk_obj = data.get("chunk")
        # content가 content block 리스트로 내려올 수 있어 평탄화 문자열로 정규화.
        # (정규화하지 않으면 WS payload에 list가 실려 프론트에서 [object Object]로 표시됨)
        chunk_text = coerce_message_text(getattr(chunk_obj, "content", None))
        if not chunk_text:
            return None
        metadata = raw.get("metadata", {}) or {}
        node_name = metadata.get("langgraph_node", "") or "unknown"
        state.token_acc.setdefault(node_name, []).append(chunk_text)
        return self._build_event(
            seq, AgentRunEventType.TOKEN, run_id,
            {"chunk": chunk_text, "node_name": node_name},
        )

    # ── analysis-data-continuity (스냅샷 수집·재주입) ────────────────────

    def _collect_snapshot(
        self, request: RunAgentRequest, final_messages: list,
        analysis_source: list | None = None,
    ) -> Optional[dict]:
        """턴의 분석 원천 데이터 수집 → 스냅샷 (Design §3.3).

        analysis-source-preservation: 엑셀 파싱 원천(analysis_source)을
        raw_source 항목으로 병합 (직렬화·샘플링은 policy가 전담).
        미주입/수집 실패 시 None — 본 답변 흐름을 막지 않는다 (graceful).
        """
        if self._snapshot_policy is None:
            return None
        try:
            items = self._snapshot_items(request, final_messages)
            for src in analysis_source or []:
                body = self._snapshot_policy.render_raw_source(
                    src.get("excel") or {}
                )
                if body:
                    items.append({
                        "origin": src.get("origin", ""),
                        "kind": "raw_source",
                        "content": body,
                    })
            return self._snapshot_policy.build_snapshot(request.query, items)
        except Exception as e:
            self._logger.error("analysis snapshot collect failed", exception=e)
            return None

    def _snapshot_items(
        self, request: RunAgentRequest, final_messages: list,
    ) -> list[dict]:
        """search: 검색결과 전부(재주입분 제외) / excel: 엑셀 첨부 턴의 워커 산출."""
        policy = self._snapshot_policy
        items = [
            {"origin": getattr(m, "name", ""), "kind": "search",
             "content": getattr(m, "content", "")}
            for m in final_messages
            if is_search_result(m)
            and not policy.is_reinjected(getattr(m, "content", ""))
        ]
        if _has_excel_attachment(getattr(request, "attachments", None)):
            items += [
                {"origin": getattr(m, "name", ""), "kind": "excel",
                 "content": getattr(m, "content", "")}
                for m in final_messages
                if is_worker_output(m) and not is_search_result(m)
            ]
        return items

    def _inject_snapshot_messages(
        self, existing: list[ConversationMessage], messages: list,
    ) -> list:
        """최신 스냅샷을 검색결과 규약 AIMessage로 새 user 직전에 삽입 (Design §3.4).

        - 세션 전체 히스토리 스캔(select_recent) — 요약 발동과 무관 (compact 공존)
        - 재주입 메시지는 저장하지 않음 (컨텍스트 빌드 산출물)
        """
        if self._snapshot_policy is None:
            return messages
        injected = [
            AIMessage(
                # 저장된 origin 은 상한 도입 전 65자 worker_id 일 수 있다.
                name=clamp_llm_name(item.get("origin", "")),
                content=format_search_result(
                    item.get("origin", ""),
                    self._snapshot_policy.render_reinjection_body(snap, item),
                ),
            )
            for snap in self._snapshot_policy.select_recent(existing)
            for item in snap.get("items", [])
        ]
        if not injected:
            return messages
        return [*messages[:-1], *injected, messages[-1]]

    # ── Conversation helpers (기존 그대로) ──────────────────────────────

    async def _build_messages(
        self,
        query: str,
        user_id: str,
        session_id: str,
        has_session: bool,
    ) -> list:
        if not has_session:
            return [{"role": "user", "content": query}]

        existing = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id)
        )

        if not existing:
            return [{"role": "user", "content": query}]

        if self._policy.needs_summarization(existing):
            messages = await self._build_summarized_context(
                existing, query, user_id, session_id
            )
        else:
            messages = [
                {"role": msg.role.value, "content": msg.content}
                for msg in sorted(existing, key=lambda m: m.turn_index.value)
            ]
            messages.append({"role": "user", "content": query})
        return self._inject_snapshot_messages(existing, messages)

    async def _build_summarized_context(
        self,
        existing: list[ConversationMessage],
        query: str,
        user_id: str,
        session_id: str,
    ) -> list[dict]:
        to_summarize = self._policy.get_turns_to_summarize(existing)
        start_turn, end_turn = self._policy.get_summary_range(existing)

        summary_text = await self._summarizer.summarize(to_summarize, session_id)

        summary = ConversationSummary(
            id=None,
            user_id=UserId(user_id),
            session_id=SessionId(session_id),
            agent_id=existing[0].agent_id,
            summary_content=summary_text,
            start_turn=start_turn,
            end_turn=end_turn,
            created_at=datetime.now(timezone.utc),
        )
        await self._summary_repo.save(summary)

        recent = self._policy.get_recent_turns(existing)
        messages: list[dict] = [
            {"role": "system", "content": f"[이전 대화 요약]\n{summary_text}"}
        ]
        for msg in sorted(recent, key=lambda m: m.turn_index.value):
            messages.append({"role": msg.role.value, "content": msg.content})
        messages.append({"role": "user", "content": query})
        return messages

    async def _save_user_message(
        self,
        query: str,
        user_id: str,
        session_id: str,
        agent_id: str,
        *,
        persist: bool = True,
    ) -> int | None:
        """user message 저장 후 message_id 반환 (Design §5-2).

        agent-model-benchmark D2: persist=False면 저장을 건너뛰고 None을 돌려준다.
        ai_run.user_message_id는 nullable(V021)이라 관측은 그대로 이어진다.

        AGENT-OBS-001 fix: session_factory가 주입되었으면 별도 세션에서 즉시 commit한다.
        - Tracker가 ai_run INSERT 시 FK 체크하는 conversation_message.id row 락이 즉시 풀려야
          Lock wait timeout (Error 1205)을 피할 수 있다.
        - 의미적으로도 user 질문은 어시스턴트 실패와 무관하게 영속화되는 것이 자연스럽다.
        - session_factory가 없으면(테스트/기존 호출 경로) 메인 세션 사용 (legacy fallback).
        """
        if not persist:
            return None
        if self._session_factory is not None:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SQLAlchemyConversationMessageRepository(session)
                    existing = await repo.find_by_session(
                        UserId(user_id), SessionId(session_id)
                    )
                    base_turn = len(existing)
                    user_msg = ConversationMessage(
                        id=None,
                        user_id=UserId(user_id),
                        session_id=SessionId(session_id),
                        agent_id=AgentId(agent_id),
                        role=MessageRole.USER,
                        content=query,
                        turn_index=TurnIndex(base_turn + 1),
                        created_at=datetime.now(timezone.utc),
                    )
                    saved = await repo.save(user_msg)
                    return saved.id.value if saved.id is not None else None

        # legacy fallback (session_factory 미주입 시) — 기존 동작 유지
        existing = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id)
        )
        base_turn = len(existing)
        user_msg = ConversationMessage(
            id=None,
            user_id=UserId(user_id),
            session_id=SessionId(session_id),
            agent_id=AgentId(agent_id),
            role=MessageRole.USER,
            content=query,
            turn_index=TurnIndex(base_turn + 1),
            created_at=datetime.now(timezone.utc),
        )
        saved = await self._message_repo.save(user_msg)
        return saved.id.value if saved.id is not None else None

    async def _save_assistant_message(
        self,
        answer: str,
        user_id: str,
        session_id: str,
        agent_id: str,
        *,
        charts: Optional[list[dict]] = None,
        analysis_data: Optional[dict] = None,
        persist: bool = True,
    ) -> None:
        """assistant message 저장 (user message 이후 turn_index 자동 계산).

        agent-model-benchmark D2: persist=False면 건너뛴다 (강등 경로도 동시 적용).
        chat-chart-persistence: charts는 표시 전용 메타 — LLM 컨텍스트(_build_messages)
        에는 재투입하지 않는다 (Design D7).
        analysis-data-continuity: analysis_data는 다음 턴 컨텍스트에 재주입되는
        데이터 스냅샷 (요약 입력에는 미포함).
        """
        if not persist:
            return
        existing = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id)
        )
        base_turn = len(existing)
        assistant_msg = ConversationMessage(
            id=None,
            user_id=UserId(user_id),
            session_id=SessionId(session_id),
            agent_id=AgentId(agent_id),
            role=MessageRole.ASSISTANT,
            content=answer,
            turn_index=TurnIndex(base_turn + 1),
            created_at=datetime.now(timezone.utc),
            charts=charts,
            analysis_data=analysis_data,
        )
        await self._message_repo.save(assistant_msg)

    def _parse_result(self, result: dict) -> tuple[str, list[str]]:
        messages = result.get("messages", [])
        answer = ""
        if messages:
            last = messages[-1]
            answer = last.content if hasattr(last, "content") else str(last)

        tools_used = list({
            getattr(m, "name", None)
            for m in messages
            if getattr(m, "name", None)
        })
        return answer, tools_used
