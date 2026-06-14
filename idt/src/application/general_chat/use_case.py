"""GeneralChatUseCase: ReAct 에이전트 + 멀티턴 대화 메모리 오케스트레이션.

ws-chat-streaming Design §4.1/§4.2 (2026-05-25):
- stream(): transport-독립 AsyncIterator[ChatEvent] 반환
- execute(): stream()을 내부 소비해 기존 GeneralChatResponse 반환 (호환성 유지)
- LangGraph create_react_agent.ainvoke → astream_events(version="v2") 전환
- 기존 테스트 호환: 헬퍼의 astream_events가 내부적으로 ainvoke를 호출하므로
  기존 ainvoke assertion(call_count/side_effect/return_value) 모두 그대로 동작.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from src.application.agent_run.auth_context import (
    reset_current_auth_context,
    set_current_auth_context,
)
from src.application.agent_run.prompt_rendering import render_user_context_block
from src.application.conversation.interfaces import ConversationSummarizerInterface
from src.application.general_chat.tools import ChatToolBuilder
from src.application.repositories.conversation_repository import ConversationMessageRepository
from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.conversation.chart_caption_policy import ChartCaptionPolicy
from src.domain.conversation.entities import ConversationMessage, ConversationSummary
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import AgentId, MessageRole, SessionId, TurnIndex, UserId
from src.domain.general_chat.schemas import DocumentSource, GeneralChatRequest, GeneralChatResponse
from src.domain.general_chat.value_objects import ChatEvent, ChatEventType
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm.message_content import coerce_message_text
from src.domain.llm_model.entity import LlmModel
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.followup_policy import (
    ChartFollowupDecision,
    ChartFollowupPolicy,
)
from src.domain.visualization.interfaces import (
    ChartBuilderInterface,
    ChartTransformerInterface,
    ChartTransformResult,
    VisualizationClassifierInterface,
)
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.domain.visualization.schemas import VizDecision
from src.infrastructure.langsmith.langsmith import langsmith

_SYSTEM_PROMPT = (
    "당신은 사용자의 일반 질문에 답하는 AI 어시스턴트입니다.\n"
    "이전 대화 내용이 있다면 반드시 참고하여 문맥에 맞게 답변하세요.\n"
    "필요에 따라 다음 도구를 사용하세요:\n"
    "- tavily_search: 최신 웹 정보 검색\n"
    "- internal_document_search: 내부 문서(금융/정책 등) 검색\n"
    "- MCP 도구: 등록된 외부 서비스 연동\n"
    "이전 턴에 [생성된 차트: ...] 표기가 있으면 그 차트를 참조하는 "
    "후속 요청을 문맥으로 이해하세요.\n"
    "항상 한국어로 답변하세요."
)

# chart-context-continuity §3.7: 변환 성공 + message 누락 시 기본 확인 답변
_CHART_EDIT_DEFAULT_ANSWER = "요청하신 차트 수정을 적용했습니다."

_CHAT_FAILED_CODE = "CHAT_EXEC_FAILED"
_STEP_NAME_CHAT_AGENT = "chat_agent"  # agent-chat-reasoning-display §10.1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _SeqCounter:
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


@dataclass
class _ChatStreamState:
    tool_start_ts: dict[str, datetime] = field(default_factory=dict)
    final_messages: list = field(default_factory=list)


class GeneralChatUseCase:
    """LangGraph ReAct 에이전트 기반 범용 채팅 UseCase.

    의존성 (CONV-001 재사용):
    - ConversationMessageRepository: 대화 저장/조회
    - ConversationSummaryRepository: 요약 저장
    - ConversationSummarizerInterface: 오래된 턴 요약
    - SummarizationPolicy: 요약 정책 판단
    """

    def __init__(
        self,
        chat_tool_builder: ChatToolBuilder,
        message_repo: ConversationMessageRepository,
        summary_repo: ConversationSummaryRepository,
        summarizer: ConversationSummarizerInterface,
        summarization_policy: SummarizationPolicy,
        logger: LoggerInterface,
        llm_factory: LLMFactoryInterface,
        llm_model: LlmModel,
        max_iterations: int = 10,
        viz_policy: VisualizationRoutingPolicy | None = None,
        viz_classifier: VisualizationClassifierInterface | None = None,
        chart_builder: ChartBuilderInterface | None = None,
        chart_transformer: ChartTransformerInterface | None = None,
        followup_policy: ChartFollowupPolicy | None = None,
        caption_policy: ChartCaptionPolicy | None = None,
    ) -> None:
        self._tool_builder = chat_tool_builder
        self._msg_repo = message_repo
        self._summary_repo = summary_repo
        self._summarizer = summarizer
        self._policy = summarization_policy
        self._logger = logger
        self._llm_factory = llm_factory
        self._llm_model = llm_model
        self._max_iterations = max_iterations
        # chart-builder: 모두 Optional → 미주입 시 차트 비활성(하위호환)
        self._viz_policy = viz_policy
        self._viz_classifier = viz_classifier
        self._chart_builder = chart_builder
        # chart-context-continuity: transformer 미주입 시 편집 분기 비활성(하위호환).
        # 캡션은 D7-rev1 핵심 동작이므로 기본 활성.
        self._chart_transformer = chart_transformer
        self._followup_policy = followup_policy or ChartFollowupPolicy()
        self._caption_policy = caption_policy or ChartCaptionPolicy()

    def _create_agent(self, tools: list, auth_ctx: AuthContext | None = None):
        """ReAct 에이전트 생성 (테스트에서 패치 가능).

        agent-user-context Design §4.4.3:
        - auth_ctx가 있으면 system prompt 앞에 사용자 컨텍스트 블록 prepend.
        - render_user_context_block은 None/anonymous면 빈 문자열 반환 (graceful).
        """
        llm = self._llm_factory.create(self._llm_model, temperature=0)
        prompt = render_user_context_block(auth_ctx) + _SYSTEM_PROMPT
        return create_react_agent(llm, tools=tools, prompt=prompt)

    # ── Public API ──────────────────────────────────────────────────────────

    async def stream(
        self,
        request: GeneralChatRequest,
        request_id: str,
        *,
        auth_ctx: AuthContext | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """transport-독립 SSE/WS용 이벤트 스트림 (Design §4.1).

        이벤트 시퀀스:
          CHAT_STARTED → (TOKEN | TOOL_STARTED | TOOL_COMPLETED)* → ANSWER_COMPLETED → CHAT_DONE
          (예외 시 ANSWER/DONE 대신 CHAT_FAILED, generator 정상 종료)
        """
        seq = _SeqCounter()
        langsmith(project_name="general-chat")
        self._logger.info(
            "GeneralChatUseCase.stream start",
            request_id=request_id, user_id=request.user_id,
            session_id=request.session_id,
        )

        session_id_str = request.session_id or str(uuid.uuid4())
        user_id = UserId(request.user_id)
        session_id = SessionId(session_id_str)

        yield self._build_event(
            seq, ChatEventType.CHAT_STARTED, session_id_str,
            {"session_id": session_id_str},
        )

        # agent-user-context Design §4.4.3: AuthContext ContextVar 세팅
        auth_token = (
            set_current_auth_context(auth_ctx) if auth_ctx is not None else None
        )

        try:
            history = await self._msg_repo.find_by_session(user_id, session_id)

            # chart-context-continuity D4: 차트 편집 의도 → ReAct 우회 전용 분기.
            # 실패/미해당 시 None → 아래 일반 경로로 폴백.
            edited = await self._try_chart_edit(request.message, history)
            if edited is not None:
                answer, charts = edited
                await self._persist_messages(
                    user_id, session_id, request.message, answer, len(history),
                    charts=charts,
                )
                yield self._build_event(
                    seq, ChatEventType.ANSWER_COMPLETED, session_id_str,
                    {
                        "answer": answer,
                        "tools_used": ["chart_transformer"],
                        "sources": [],
                        "was_summarized": False,
                        "charts": charts,
                    },
                )
                yield self._build_event(
                    seq, ChatEventType.CHAT_DONE, session_id_str,
                    {"session_id": session_id_str},
                )
                return

            if self._policy.needs_summarization(history):
                was_summarized = True
                context = await self._build_summarized_context(
                    history, request.message, user_id, session_id,
                    AgentId.super(), request_id,
                )
            else:
                was_summarized = False
                context = self._build_full_context(history, request.message)

            tools = await self._tool_builder.build(
                top_k=request.top_k, request_id=request_id, auth_ctx=auth_ctx,
            )
            agent = self._create_agent(tools, auth_ctx=auth_ctx)

            state = _ChatStreamState()
            async for raw in agent.astream_events(
                {"messages": context}, version="v2",
            ):
                mapped = self._map_event(raw, seq, session_id_str, state)
                if mapped is not None:
                    yield mapped

            answer, tools_used, sources = self._parse_agent_output(
                {"messages": state.final_messages}, tools,
            )

            # chat-chart-persistence D4: 차트 생성 → 저장 순서.
            # (저장이 먼저면 charts를 영속화할 수 없음. 빌드 실패 시 [] graceful)
            charts = await self._maybe_build_charts(
                request.message, answer, sources, tools_used,
            )

            await self._persist_messages(
                user_id, session_id, request.message, answer, len(history),
                charts=charts or None,
            )

            yield self._build_event(
                seq, ChatEventType.ANSWER_COMPLETED, session_id_str,
                {
                    "answer": answer,
                    "tools_used": tools_used,
                    "sources": [s.model_dump() for s in sources],
                    "was_summarized": was_summarized,
                    "charts": charts,
                },
            )
            yield self._build_event(
                seq, ChatEventType.CHAT_DONE, session_id_str,
                {"session_id": session_id_str},
            )
        except asyncio.CancelledError:
            self._logger.warning(
                "GeneralChatUseCase.stream cancelled", request_id=request_id,
            )
            raise
        except Exception as e:
            self._logger.error(
                "GeneralChatUseCase failed", exception=e, request_id=request_id,
            )
            yield self._build_event(
                seq, ChatEventType.CHAT_FAILED, session_id_str,
                {"code": _CHAT_FAILED_CODE, "message": str(e)[:512]},
            )
        finally:
            if auth_token is not None:
                reset_current_auth_context(auth_token)

    async def execute(
        self,
        request: GeneralChatRequest,
        request_id: str,
        *,
        auth_ctx: AuthContext | None = None,
    ) -> GeneralChatResponse:
        """기존 시그니처. stream()을 내부 소비해 GeneralChatResponse 조립.

        Breaking change 0 — 호출자(테스트/라우터/외부)는 코드 변경 불필요.
        auth_ctx는 키워드 전용으로 추가.
        """
        answer = ""
        tools_used: list[str] = []
        sources: list[DocumentSource] = []
        was_summarized = False
        charts: list[dict] = []
        session_id_str = request.session_id or ""
        failure_message: Optional[str] = None

        async for ev in self.stream(request, request_id, auth_ctx=auth_ctx):
            if ev.event_type == ChatEventType.CHAT_STARTED:
                session_id_str = ev.payload["session_id"]
            elif ev.event_type == ChatEventType.ANSWER_COMPLETED:
                answer = ev.payload["answer"]
                tools_used = list(ev.payload["tools_used"])
                sources = [DocumentSource(**s) for s in ev.payload["sources"]]
                was_summarized = ev.payload["was_summarized"]
                charts = list(ev.payload.get("charts", []))
            elif ev.event_type == ChatEventType.CHAT_FAILED:
                failure_message = ev.payload.get("message", "unknown")

        if failure_message is not None:
            raise RuntimeError(failure_message)

        return GeneralChatResponse(
            user_id=request.user_id,
            session_id=session_id_str,
            answer=answer,
            tools_used=tools_used,
            sources=sources,
            was_summarized=was_summarized,
            request_id=request_id,
            charts=charts,
        )

    # ── chart-context-continuity (편집 분기) ────────────────────────────────

    async def _try_chart_edit(
        self, message: str, history: list[ConversationMessage],
    ) -> tuple[str, list[dict]] | None:
        """편집 의도 + 세션 저장 차트 → 변환 결과 (answer, charts).

        미해당/실패 시 None 반환해 호출측이 일반 경로로 폴백한다 (D4).
        """
        if self._chart_transformer is None:
            return None
        recent_charts = self._find_recent_charts(history)
        if not recent_charts:
            return None  # 오분류 안전망: 저장 차트 없으면 일반 경로
        decision = self._followup_policy.decide(message)
        if decision != ChartFollowupDecision.EDIT:
            return None
        result = await self._transform_safe(message, recent_charts)
        if not result.charts:
            return None
        charts = [c.model_dump(exclude_none=True) for c in result.charts]
        return (result.message or _CHART_EDIT_DEFAULT_ANSWER, charts)

    @staticmethod
    def _find_recent_charts(
        history: list[ConversationMessage],
    ) -> list[dict] | None:
        """세션 내 최근 charts 부속 assistant 메시지의 charts (역순 첫 발견)."""
        for msg in sorted(
            history, key=lambda m: m.turn_index.value, reverse=True,
        ):
            if msg.role == MessageRole.ASSISTANT and msg.charts:
                return msg.charts
        return None

    async def _transform_safe(
        self, instruction: str, charts: list[dict],
    ) -> ChartTransformResult:
        """변환 예외 → 빈 결과 (일반 경로 폴백). _classify_safe 동형."""
        try:
            return await self._chart_transformer.transform(instruction, charts)
        except Exception as e:
            self._logger.error(
                "chart transform failed, fallback to agent", exception=e,
            )
            return ChartTransformResult(charts=[], message="")

    # ── chart-builder ───────────────────────────────────────────────────────

    async def _maybe_build_charts(
        self,
        question: str,
        answer: str,
        sources: list[DocumentSource],
        tools_used: list[str],
    ) -> list[dict]:
        """시각화 판단 후 Chart.js config 리스트 생성 (Design §5.2).

        실패/비-visualize/미주입 시 항상 [] 반환해 본 흐름을 막지 않는다.
        """
        if self._chart_builder is None or not answer:
            return []
        policy = self._viz_policy or VisualizationRoutingPolicy()
        decision = policy.decide(question, answer)
        if decision is None:
            decision = await self._classify_safe(question, answer)
        if decision != VizDecision.VISUALIZE.value:
            return []
        context = self._build_chart_context(sources)
        try:
            charts = await self._chart_builder.build(question, answer, context)
        except Exception as e:
            self._logger.error("maybe_build_charts failed", exception=e)
            return []
        return [c.model_dump(exclude_none=True) for c in charts]

    async def _classify_safe(self, question: str, answer: str) -> str:
        """애매구간 LLM 분류. 미주입/예외 시 보수적으로 'text'."""
        if self._viz_classifier is None:
            return VizDecision.TEXT.value
        try:
            return await self._viz_classifier.classify(question, answer)
        except Exception as e:
            self._logger.error("viz classify failed, fallback=text", exception=e)
            return VizDecision.TEXT.value

    def _build_chart_context(self, sources: list[DocumentSource]) -> str:
        """수치 근거 보강용 컨텍스트 (Design §5.2, D3)."""
        if not sources:
            return ""
        return "\n".join(s.content for s in sources if s.content)[:2000]

    # ── Stream helpers ─────────────────────────────────────────────────────

    def _build_event(
        self,
        seq: _SeqCounter,
        event_type: ChatEventType,
        session_id: Optional[str],
        payload: dict,
    ) -> ChatEvent:
        return ChatEvent(
            seq=seq.next(),
            event_type=event_type,
            session_id=session_id,
            payload=payload,
            timestamp=_utcnow(),
        )

    def _map_event(
        self,
        raw: dict,
        seq: _SeqCounter,
        session_id: str,
        state: _ChatStreamState,
    ) -> Optional[ChatEvent]:
        """LangGraph astream_events(v2) dict → ChatEvent (또는 None=skip)."""
        ev_type = raw.get("event", "")
        data = raw.get("data", {}) or {}

        if ev_type == "on_chain_end":
            output = data.get("output")
            if isinstance(output, dict) and "messages" in output:
                state.final_messages = list(output["messages"])
            return None  # chain_end는 UI 표시 안 함
        if ev_type == "on_chat_model_stream":
            return self._map_token(data, seq, session_id)
        if ev_type == "on_chat_model_end":
            # agent-chat-reasoning-display §4.1
            return self._map_model_reasoning(data, seq, session_id)
        if ev_type == "on_tool_start":
            return self._map_tool_start(raw, data, seq, session_id, state)
        if ev_type == "on_tool_end":
            return self._map_tool_end(raw, data, seq, session_id, state)
        return None

    def _map_model_reasoning(
        self, data: dict, seq: _SeqCounter, session_id: str,
    ) -> Optional[ChatEvent]:
        """on_chat_model_end + tool_calls + content → STEP_REASONING.

        agent-chat-reasoning-display Design §4.1.
        - tool_calls가 비어 있으면 일반 응답 — 발행하지 않음 (token 스트림으로 이미 노출).
        - content가 비어 있으면 잡음 방지 — 발행하지 않음.
        """
        output = data.get("output")
        tool_calls = getattr(output, "tool_calls", None)
        if not tool_calls:
            return None
        content = getattr(output, "content", None)
        if not isinstance(content, str) or not content.strip():
            return None
        return self._build_event(
            seq, ChatEventType.STEP_REASONING, session_id,
            {
                "step_name": _STEP_NAME_CHAT_AGENT,
                "reasoning": content,
                "tool_calls": [
                    tc.get("name", "") for tc in tool_calls if isinstance(tc, dict)
                ],
            },
        )

    def _map_token(
        self, data: dict, seq: _SeqCounter, session_id: str,
    ) -> Optional[ChatEvent]:
        chunk_obj = data.get("chunk")
        # content가 content block 리스트로 내려올 수 있어 평탄화 문자열로 정규화.
        # (정규화하지 않으면 WS payload에 list가 실려 프론트에서 [object Object]로 표시됨)
        chunk_text = coerce_message_text(getattr(chunk_obj, "content", None))
        if not chunk_text:
            return None
        return self._build_event(
            seq, ChatEventType.TOKEN, session_id, {"chunk": chunk_text},
        )

    def _map_tool_start(
        self, raw: dict, data: dict,
        seq: _SeqCounter, session_id: str, state: _ChatStreamState,
    ) -> ChatEvent:
        tool_call_id = raw.get("run_id", "")
        state.tool_start_ts[tool_call_id] = _utcnow()
        return self._build_event(
            seq, ChatEventType.TOOL_STARTED, session_id,
            {
                "tool_name": raw.get("name", ""),
                "tool_call_id": tool_call_id,
                "input_preview": str(data.get("input", ""))[:1024],
            },
        )

    def _map_tool_end(
        self, raw: dict, data: dict,
        seq: _SeqCounter, session_id: str, state: _ChatStreamState,
    ) -> ChatEvent:
        tool_call_id = raw.get("run_id", "")
        start = state.tool_start_ts.pop(tool_call_id, None)
        duration_ms = (
            int((_utcnow() - start).total_seconds() * 1000) if start else 0
        )
        return self._build_event(
            seq, ChatEventType.TOOL_COMPLETED, session_id,
            {
                "tool_name": raw.get("name", ""),
                "tool_call_id": tool_call_id,
                "output_preview": str(data.get("output", ""))[:1024],
                "duration_ms": duration_ms,
            },
        )

    async def _persist_messages(
        self, user_id: UserId, session_id: SessionId,
        user_query: str, answer: str, base_turn: int,
        *, charts: list[dict] | None = None,
    ) -> None:
        """사용자 메시지 + AI 응답 DB 저장 (기존 execute() §7과 동일 동작).

        chat-chart-persistence: charts는 assistant 메시지에만 부속 (D8).
        D7-rev1(chart-context-continuity): full config는 컨텍스트/요약에
        재투입하지 않되, 캡션 1줄은 _to_langchain_message에서 부착한다.
        """
        super_agent = AgentId.super()
        user_msg = ConversationMessage(
            id=None, user_id=user_id, session_id=session_id,
            agent_id=super_agent, role=MessageRole.USER, content=user_query,
            turn_index=TurnIndex(base_turn + 1), created_at=datetime.utcnow(),
        )
        await self._msg_repo.save(user_msg)
        ai_msg = ConversationMessage(
            id=None, user_id=user_id, session_id=session_id,
            agent_id=super_agent, role=MessageRole.ASSISTANT, content=answer,
            turn_index=TurnIndex(base_turn + 2), created_at=datetime.utcnow(),
            charts=charts,
        )
        await self._msg_repo.save(ai_msg)

    # ── Conversation helpers (기존 그대로) ──────────────────────────────────

    async def _build_summarized_context(
        self,
        history: list[ConversationMessage],
        new_message: str,
        user_id: UserId,
        session_id: SessionId,
        agent_id: AgentId,
        request_id: str,
    ) -> list:
        """오래된 턴 요약 → 저장 → (SystemMessage(요약) + 최근 3턴 + 새 메시지)."""
        to_summarize = self._policy.get_turns_to_summarize(history)
        start_turn, end_turn = self._policy.get_summary_range(history)

        summary_text = await self._summarizer.summarize(to_summarize, request_id)

        summary = ConversationSummary(
            id=None,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            summary_content=summary_text,
            start_turn=start_turn,
            end_turn=end_turn,
            created_at=datetime.utcnow(),
        )
        await self._summary_repo.save(summary)

        recent = self._policy.get_recent_turns(history)
        messages = [SystemMessage(content=f"[이전 대화 요약]\n{summary_text}")]
        for msg in sorted(recent, key=lambda m: m.turn_index.value):
            messages.append(self._to_langchain_message(msg))
        messages.append(HumanMessage(content=new_message))
        return messages

    def _build_full_context(
        self,
        history: list[ConversationMessage],
        new_message: str,
    ) -> list:
        """전체 히스토리 + 새 메시지 → LangChain 메시지 목록."""
        messages = []
        for msg in sorted(history, key=lambda m: m.turn_index.value):
            messages.append(self._to_langchain_message(msg))
        messages.append(HumanMessage(content=new_message))
        return messages

    def _to_langchain_message(self, msg: ConversationMessage):
        """저장 메시지 → LangChain 메시지.

        chart-context-continuity D7-rev1: charts 부속 assistant 메시지는
        캡션 1줄을 부착한다 (full config는 미투입). 요약 본문에는 미포함
        (summarizer 입력은 content만 사용하므로 기존과 동일).
        """
        if msg.role == MessageRole.USER:
            return HumanMessage(content=msg.content)
        content = msg.content
        if msg.charts:
            caption = self._caption_policy.build_caption(msg.charts)
            if caption:
                content = f"{content}\n\n{caption}"
        return AIMessage(content=content)

    def _parse_agent_output(
        self,
        result: dict,
        tools: list,
    ) -> tuple[str, list[str], list[DocumentSource]]:
        """에이전트 결과 파싱.

        Returns:
            (answer, tools_used, sources)
        """
        raw_messages = result.get("messages", [])

        answer = ""
        for msg in reversed(raw_messages):
            if isinstance(msg, AIMessage) and msg.content:
                answer = msg.content
                break

        tools_used = [
            msg.name
            for msg in raw_messages
            if isinstance(msg, ToolMessage) and getattr(msg, "name", None)
        ]

        sources: list[DocumentSource] = []
        for tool in tools:
            if getattr(tool, "name", None) == "internal_document_search":
                for src in getattr(tool, "collected_sources", []):
                    if isinstance(src, DocumentSource):
                        sources.append(src)
                    else:
                        sources.append(
                            DocumentSource(
                                content=src.content,
                                source=src.source,
                                chunk_id=src.chunk_id,
                                score=src.score,
                            )
                        )
                break

        return answer, tools_used, sources
