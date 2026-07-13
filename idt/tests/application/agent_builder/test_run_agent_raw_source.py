"""RunAgentUseCase 원천 스냅샷 캡처/병합 테스트 (analysis-source-preservation T3/T4)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_builder.search_pipeline import is_search_result
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.conversation.analysis_snapshot_policy import (
    REINJECTED_MARKER,
    AnalysisSnapshotPolicy,
)
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import (
    AgentId, MessageRole, SessionId, TurnIndex, UserId,
)
from src.domain.llm_model.entity import LlmModel

_PARSED = {
    "file_id": "f1", "filename": "vac.xlsx",
    "sheets": {"Sheet1": {"sheet_name": "Sheet1", "columns": ["월", "잔여"],
                          "data": [{"월": "1월", "잔여": 14}, {"월": "2월", "잔여": 13}],
                          "dtypes": {}, "row_count": 2, "column_count": 2}},
    "metadata": {},
}


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="M", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()), user_id="user-1", name="A", description="d",
        system_prompt="p", flow_hint="h",
        workers=[WorkerDefinition("data_analysis", "analyst", "분석", 0)],
        llm_model_id="model-1", status="active", created_at=now, updated_at=now,
    )


def _conv_msg(turn, role, content="msg", analysis_data=None):
    return ConversationMessage(
        id=None, user_id=UserId("user-1"), session_id=SessionId("sess-1"),
        agent_id=AgentId("agent-1"), role=MessageRole(role), content=content,
        turn_index=TurnIndex(turn), created_at=datetime.now(timezone.utc),
        analysis_data=analysis_data,
    )


def _make_use_case(existing_messages=None, final_messages=None,
                   analysis_source=None, snapshot_policy=...):
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()

    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    llm_model_repository.find_by_id = AsyncMock(return_value=_make_llm_model())
    message_repo.find_by_session = AsyncMock(return_value=existing_messages or [])
    message_repo.save = AsyncMock()
    summary_repo.save = AsyncMock()
    summarizer.summarize = AsyncMock(return_value="요약")

    final = final_messages if final_messages is not None else [
        AIMessage(content="최종 답변입니다.")
    ]
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={"messages": final})

    def _astream_side_effect(*args, **kwargs):
        async def _gen():
            result = await mock_graph.ainvoke(*args, **kwargs)
            output = {"messages": result.get("messages", [])}
            # analysis_node이 방출하는 원천 채널을 on_chain_end output에 포함.
            if analysis_source is not None:
                output["analysis_source"] = analysis_source
            yield {
                "event": "on_chain_end", "name": "LangGraph",
                "data": {"output": output}, "metadata": {}, "run_id": "top",
            }
        return _gen()

    mock_graph.astream_events = MagicMock(side_effect=_astream_side_effect)
    compiler.compile = AsyncMock(return_value=mock_graph)

    policy = AnalysisSnapshotPolicy() if snapshot_policy is ... else snapshot_policy
    use_case = RunAgentUseCase(
        repository=repository, llm_model_repository=llm_model_repository,
        compiler=compiler, logger=MagicMock(), message_repo=message_repo,
        summary_repo=summary_repo, summarizer=summarizer,
        policy=SummarizationPolicy(), snapshot_policy=policy,
    )
    return use_case, agent, message_repo, mock_graph


def _saved_analysis_data(message_repo):
    saved = [c.args[0] for c in message_repo.save.call_args_list]
    assistants = [m for m in saved if m.role == MessageRole.ASSISTANT]
    assert len(assistants) == 1
    return assistants[0].analysis_data


class TestRawSourceCapture:
    @pytest.mark.asyncio
    async def test_analysis_source_채널_캡처하여_raw_source_저장(self):
        src = [{"origin": "analyst", "kind": "raw_source", "excel": _PARSED}]
        uc, agent, message_repo, _ = _make_use_case(
            final_messages=[AIMessage(content="남은 연차 분석")],
            analysis_source=src,
        )
        req = RunAgentRequest(query="휴가 분석", user_id="user-1")
        await uc.execute(agent.id, req, "req-1")

        data = _saved_analysis_data(message_repo)
        assert data is not None
        raw = [it for it in data["items"] if it["kind"] == "raw_source"]
        assert len(raw) == 1
        assert "vac.xlsx" in raw[0]["content"]
        assert "1월" in raw[0]["content"] and "2월" in raw[0]["content"]

    @pytest.mark.asyncio
    async def test_원천과_검색결과_병합(self):
        from src.application.agent_builder.search_pipeline import format_search_result
        src = [{"origin": "analyst", "kind": "raw_source", "excel": _PARSED}]
        uc, agent, message_repo, _ = _make_use_case(
            final_messages=[
                AIMessage(content=format_search_result("sw", "웹 자료"), name="sw"),
                AIMessage(content="답변"),
            ],
            analysis_source=src,
        )
        req = RunAgentRequest(query="q", user_id="user-1")
        await uc.execute(agent.id, req, "req-1")

        data = _saved_analysis_data(message_repo)
        kinds = {it["kind"] for it in data["items"]}
        assert "raw_source" in kinds
        assert "search" in kinds

    @pytest.mark.asyncio
    async def test_analysis_source_없으면_기존과_동일(self):
        uc, agent, message_repo, _ = _make_use_case(
            final_messages=[AIMessage(content="답변")], analysis_source=None,
        )
        req = RunAgentRequest(query="q", user_id="user-1")
        await uc.execute(agent.id, req, "req-1")
        assert _saved_analysis_data(message_repo) is None


class TestRawSourceReinject:
    @pytest.mark.asyncio
    async def test_원천_스냅샷이_검색결과_규약으로_재주입(self):
        snap = {
            "version": 1, "question": "휴가 분석",
            "items": [{"origin": "analyst", "kind": "raw_source",
                       "content": "[원천 데이터: vac.xlsx]\n월,잔여\n1월,14",
                       "truncated": False}],
        }
        existing = [
            _conv_msg(1, "user", "휴가 분석"),
            _conv_msg(2, "assistant", "차트", analysis_data=snap),
        ]
        uc, agent, _, mock_graph = _make_use_case(existing_messages=existing)
        req = RunAgentRequest(
            query="분기별로 다시", user_id="user-1", session_id="sess-1",
        )
        await uc.execute(agent.id, req, "req-1")

        messages = mock_graph.ainvoke.call_args[0][0]["messages"]
        injected = [m for m in messages if is_search_result(m)]
        assert len(injected) == 1
        assert REINJECTED_MARKER in injected[0].content
        assert "월,잔여" in injected[0].content  # 원천 표가 재주입됨
        assert messages[-1] == {"role": "user", "content": "분기별로 다시"}
