"""RunAgentUseCase 분석 스냅샷 저장/복원 테스트 (analysis-data-continuity T4/T5)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_builder.search_pipeline import (
    format_search_result,
    is_search_result,
)
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.conversation.analysis_snapshot_policy import (
    REINJECTED_MARKER,
    AnalysisSnapshotPolicy,
)
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.domain.llm_model.entity import LlmModel


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="GPT-4o Mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()), user_id="user-1", name="테스트 에이전트",
        description="설명", system_prompt="시스템 프롬프트", flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id="model-1", status="active", created_at=now, updated_at=now,
    )


def _conv_msg(turn: int, role: str, content: str = "msg",
              analysis_data: dict | None = None) -> ConversationMessage:
    return ConversationMessage(
        id=None, user_id=UserId("user-1"), session_id=SessionId("sess-1"),
        agent_id=AgentId("agent-1"), role=MessageRole(role), content=content,
        turn_index=TurnIndex(turn), created_at=datetime.now(timezone.utc),
        analysis_data=analysis_data,
    )


_SNAPSHOT = {
    "version": 1,
    "question": "나의 휴가데이터",
    "items": [
        {"origin": "search_worker", "kind": "search",
         "content": "휴가 15일 사용", "truncated": False}
    ],
}


def _make_use_case(existing_messages=None, final_messages=None,
                   snapshot_policy=...):
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    logger = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()

    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    llm_model_repository.find_by_id = AsyncMock(return_value=_make_llm_model())
    message_repo.find_by_session = AsyncMock(return_value=existing_messages or [])
    message_repo.save = AsyncMock()
    summary_repo.save = AsyncMock()
    summarizer.summarize = AsyncMock(return_value="이전 대화 요약입니다.")

    final = final_messages if final_messages is not None else [
        AIMessage(content="최종 답변입니다.")
    ]
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"messages": final})

    def _astream_side_effect(*args, **kwargs):
        async def _gen():
            result = await mock_graph.ainvoke(*args, **kwargs)
            yield {
                "event": "on_chain_end", "name": "LangGraph",
                "data": {"output": {"messages": result.get("messages", [])}},
                "metadata": {}, "run_id": "top",
            }
        return _gen()

    mock_graph.astream_events = MagicMock(side_effect=_astream_side_effect)
    compiler.compile = AsyncMock(return_value=mock_graph)

    policy = (
        AnalysisSnapshotPolicy() if snapshot_policy is ... else snapshot_policy
    )
    use_case = RunAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        compiler=compiler,
        logger=logger,
        message_repo=message_repo,
        summary_repo=summary_repo,
        summarizer=summarizer,
        policy=SummarizationPolicy(),
        snapshot_policy=policy,
    )
    return use_case, agent, message_repo, mock_graph


def _saved_assistant_analysis_data(message_repo):
    saved = [c.args[0] for c in message_repo.save.call_args_list]
    assistants = [m for m in saved if m.role == MessageRole.ASSISTANT]
    assert len(assistants) == 1
    return assistants[0].analysis_data


class TestSnapshotCollect:
    """T4 — 턴 종료 시 스냅샷 수집·저장 (Design §3.3)."""

    @pytest.mark.asyncio
    async def test_검색결과_메시지가_스냅샷으로_저장된다(self):
        final = [
            AIMessage(
                content=format_search_result("search_worker", "휴가 15일 사용"),
                name="search_worker",
            ),
            AIMessage(content="최종 답변입니다."),
        ]
        use_case, agent, message_repo, _ = _make_use_case(final_messages=final)
        request = RunAgentRequest(query="나의 휴가데이터", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")

        data = _saved_assistant_analysis_data(message_repo)
        assert data is not None
        assert data["question"] == "나의 휴가데이터"
        assert data["items"][0]["origin"] == "search_worker"
        assert data["items"][0]["kind"] == "search"
        assert "휴가 15일 사용" in data["items"][0]["content"]

    @pytest.mark.asyncio
    async def test_재주입_마커_메시지는_재캡처하지_않는다(self):
        final = [
            AIMessage(
                content=format_search_result(
                    "search_worker", f"{REINJECTED_MARKER} (질문: q)\n옛 데이터"
                ),
                name="search_worker",
            ),
            AIMessage(content="최종 답변입니다."),
        ]
        use_case, agent, message_repo, _ = _make_use_case(final_messages=final)
        request = RunAgentRequest(query="후속 질문", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")

        assert _saved_assistant_analysis_data(message_repo) is None

    @pytest.mark.asyncio
    async def test_엑셀_첨부_턴은_비검색_워커_출력을_excel_항목으로_포함(self):
        final = [
            AIMessage(content="매출 분석: 1월 100, 2월 200", name="analysis_worker"),
            AIMessage(content="최종 답변입니다."),
        ]
        use_case, agent, message_repo, _ = _make_use_case(final_messages=final)
        request = RunAgentRequest(
            query="엑셀 분석해줘", user_id="user-1",
            attachments=[{"type": "excel", "file_path": "/tmp/x.xlsx"}],
        )
        await use_case.execute(agent.id, request, "req-1")

        data = _saved_assistant_analysis_data(message_repo)
        assert data is not None
        assert data["items"][0]["kind"] == "excel"
        assert data["items"][0]["origin"] == "analysis_worker"

    @pytest.mark.asyncio
    async def test_정책_미주입이면_스냅샷_저장_안_함(self):
        final = [
            AIMessage(
                content=format_search_result("search_worker", "데이터"),
                name="search_worker",
            ),
            AIMessage(content="최종 답변입니다."),
        ]
        use_case, agent, message_repo, _ = _make_use_case(
            final_messages=final, snapshot_policy=None,
        )
        request = RunAgentRequest(query="질문", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")

        assert _saved_assistant_analysis_data(message_repo) is None

    @pytest.mark.asyncio
    async def test_수집_예외는_본_흐름을_막지_않는다(self):
        broken = MagicMock(spec=AnalysisSnapshotPolicy)
        broken.is_reinjected = MagicMock(side_effect=RuntimeError("boom"))
        broken.select_recent = MagicMock(return_value=[])
        use_case, agent, message_repo, _ = _make_use_case(
            final_messages=[
                AIMessage(
                    content=format_search_result("w", "d"), name="w"
                ),
                AIMessage(content="최종 답변입니다."),
            ],
            snapshot_policy=broken,
        )
        request = RunAgentRequest(query="질문", user_id="user-1")
        result = await use_case.execute(agent.id, request, "req-1")

        assert result.answer == "최종 답변입니다."
        assert _saved_assistant_analysis_data(message_repo) is None


class TestSnapshotReinject:
    """T5 — 후속 턴 컨텍스트 재주입 (Design §3.4)."""

    @pytest.mark.asyncio
    async def test_스냅샷이_검색결과_규약_AIMessage로_재주입된다(self):
        existing = [
            _conv_msg(1, "user", "나의 휴가데이터"),
            _conv_msg(2, "assistant", "차트를 그렸습니다.", analysis_data=_SNAPSHOT),
        ]
        use_case, agent, _, mock_graph = _make_use_case(existing_messages=existing)
        request = RunAgentRequest(
            query="전체 사용자 그래프", user_id="user-1", session_id="sess-1",
        )
        await use_case.execute(agent.id, request, "req-1")

        messages = mock_graph.ainvoke.call_args[0][0]["messages"]
        injected = [m for m in messages if is_search_result(m)]
        assert len(injected) == 1
        assert injected[0].name == "search_worker"
        assert REINJECTED_MARKER in injected[0].content
        assert "휴가 15일 사용" in injected[0].content
        # 마지막은 새 user 질문 (재주입은 그 직전)
        assert messages[-1] == {"role": "user", "content": "전체 사용자 그래프"}

    @pytest.mark.asyncio
    async def test_요약_경로에서도_재주입된다(self):
        existing = [
            _conv_msg(i, "user" if i % 2 else "assistant", f"m{i}")
            for i in range(1, 7)
        ] + [_conv_msg(7, "assistant", "차트", analysis_data=_SNAPSHOT)]
        use_case, agent, _, mock_graph = _make_use_case(existing_messages=existing)
        request = RunAgentRequest(
            query="후속 질문", user_id="user-1", session_id="sess-1",
        )
        await use_case.execute(agent.id, request, "req-1")

        messages = mock_graph.ainvoke.call_args[0][0]["messages"]
        assert any(is_search_result(m) for m in messages)
        assert messages[-1] == {"role": "user", "content": "후속 질문"}

    @pytest.mark.asyncio
    async def test_스냅샷_없으면_기존_컨텍스트와_동일(self):
        existing = [
            _conv_msg(1, "user", "q1"),
            _conv_msg(2, "assistant", "a1"),
        ]
        use_case, agent, _, mock_graph = _make_use_case(existing_messages=existing)
        request = RunAgentRequest(
            query="q2", user_id="user-1", session_id="sess-1",
        )
        await use_case.execute(agent.id, request, "req-1")

        messages = mock_graph.ainvoke.call_args[0][0]["messages"]
        assert all(isinstance(m, dict) for m in messages)
        assert not any(is_search_result(m) for m in messages)
