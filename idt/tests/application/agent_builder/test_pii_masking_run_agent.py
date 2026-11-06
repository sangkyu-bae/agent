"""pii-masking-integration module-3 — RunAgentUseCase 배선 테스트.

Design Ref: §4.5 (FR-09 토큰 원복), §3.1 (FR-08 런 scope), FR-13 (ai_run 스텝)
fake graph가 compile에 전달된 실제 런 scope로 응답을 마스킹한 뒤 토큰을 쪼개
흘린다. 사용자에게 나가는 TOKEN 이벤트에 placeholder 조각이 없어야 한다.
"""

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.domain.agent_run.value_objects import AgentRunEventType
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.pii_masking.schemas import PiiRunScope

from tests.application.agent_builder.test_run_agent_use_case_stream import (
    _ai_message,
    _collect,
    _make_agent,
    _make_llm_model,
    _make_tracker,
)
from tests.application.pii_masking._support import make_masker

PHONE = "010-1234-5678"


def _chunk(content: str):
    chunk = MagicMock()
    chunk.content = content
    return chunk


def _stream_event(text: str, run: str = "llm-1", node: str = "final_answer"):
    return {
        "event": "on_chat_model_stream",
        "name": "ChatOpenAI",
        "data": {"chunk": _chunk(text)},
        "metadata": {"langgraph_node": node},
        "run_id": run,
    }


def _end_event(run: str = "llm-1", node: str = "final_answer"):
    return {
        "event": "on_chat_model_end",
        "name": "ChatOpenAI",
        "data": {},
        "metadata": {"langgraph_node": node},
        "run_id": run,
    }


def _use_case(
    chunks: list[str], *, masker=None, with_tracker=True, extra=None, fail=None
):
    """compile이 받은 pii_scope로 PHONE을 미리 마스킹해 vault를 채운 fake graph."""
    repository, llm_repo, compiler = MagicMock(), MagicMock(), MagicMock()
    message_repo, summary_repo = MagicMock(), MagicMock()
    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    llm_repo.find_by_id = AsyncMock(return_value=_make_llm_model())
    message_repo.find_by_session = AsyncMock(return_value=[])
    saved = MagicMock()
    saved.id.value = 42
    message_repo.save = AsyncMock(return_value=saved)
    summary_repo.find_latest_by_session = AsyncMock(return_value=None)
    tracker = _make_tracker() if with_tracker else None
    captured: dict = {}

    async def _compile(**kwargs):
        captured.update(kwargs)
        scope = kwargs.get("pii_scope")
        if scope is not None and masker is not None:
            masker.mask_messages([HumanMessage(content=PHONE)], scope)
        graph = MagicMock()

        async def _events(*args, **kw):
            for text in chunks:
                yield _stream_event(text)
            if fail is not None:
                raise fail
            yield _end_event()
            for ev in extra or []:
                yield ev
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"messages": [_ai_message("답")]}},
                "metadata": {},
                "run_id": "top",
            }

        graph.astream_events = _events
        return graph

    compiler.compile = AsyncMock(side_effect=_compile)
    use_case = RunAgentUseCase(
        repository=repository,
        llm_model_repository=llm_repo,
        compiler=compiler,
        logger=MagicMock(),
        message_repo=message_repo,
        summary_repo=summary_repo,
        summarizer=MagicMock(),
        policy=SummarizationPolicy(),
        tracker=tracker,
        pii_masker=masker,
    )
    return use_case, agent, captured, tracker


async def _tokens(use_case, agent) -> list[str]:
    request = RunAgentRequest(query="x", user_id="user-1")
    events = await _collect(use_case.stream(agent.id, request, "req-1"))
    return [
        e.payload["chunk"] for e in events if e.event_type == AgentRunEventType.TOKEN
    ]


class TestScope:
    async def test_stream_passes_run_scope_to_compile(self):
        masker = make_masker()
        use_case, agent, captured, _ = _use_case(["답"], masker=masker)
        await _tokens(use_case, agent)
        assert isinstance(captured["pii_scope"], PiiRunScope)

    async def test_stream_without_masker_does_not_pass_scope(self):
        # 기존 compile 호출 인자를 바꾸지 않는다 (해제 시 무회귀).
        use_case, agent, captured, _ = _use_case(["답"])
        await _tokens(use_case, agent)
        assert "pii_scope" not in captured


class TestTokenRestore:
    async def test_split_placeholder_restored_without_fragments(self):
        masker = make_masker()
        use_case, agent, _, _ = _use_case(["[PH", "ONE_1]", " 입니다"], masker=masker)
        tokens = await _tokens(use_case, agent)
        assert "".join(tokens) == f"{PHONE} 입니다"
        assert not any("[" in t or "PH" in t for t in tokens)

    async def test_pending_tail_flushed_at_model_end(self):
        masker = make_masker()
        use_case, agent, _, _ = _use_case(["끝 [PHO"], masker=masker)
        tokens = await _tokens(use_case, agent)
        assert tokens == ["끝 ", "[PHO"]

    async def test_flush_token_keeps_node_name(self):
        masker = make_masker()
        use_case, agent, _, _ = _use_case(["값 [PHONE_1"], masker=masker)
        request = RunAgentRequest(query="x", user_id="user-1")
        events = await _collect(use_case.stream(agent.id, request, "req-1"))
        tokens = [e for e in events if e.event_type == AgentRunEventType.TOKEN]
        # `]` 없이 끝난 꼬리는 placeholder가 아니라 그대로 나간다(원본 PII 없음).
        assert [t.payload["chunk"] for t in tokens] == ["값 ", "[PHONE_1"]
        assert {t.payload["node_name"] for t in tokens} == {"final_answer"}

    async def test_without_masker_tokens_unchanged(self):
        use_case, agent, _, _ = _use_case(["[PH", "ONE_1]"])
        assert await _tokens(use_case, agent) == ["[PH", "ONE_1]"]

    async def test_model_end_without_pending_emits_nothing(self):
        masker = make_masker()
        use_case, agent, _, _ = _use_case(["안녕"], masker=masker)
        assert await _tokens(use_case, agent) == ["안녕"]


class TestStep:
    async def test_pii_step_recorded_with_counts_only(self):
        masker = make_masker()
        use_case, agent, _, tracker = _use_case(["답"], masker=masker)
        await _tokens(use_case, agent)
        steps = [
            c
            for c in tracker.record_step.call_args_list
            if c.kwargs.get("node_name") == "pii_masking"
        ]
        assert len(steps) == 1
        summaries = [
            c.kwargs.get("output_summary") for c in tracker.update_step.call_args_list
        ]
        summary = next(s for s in summaries if s and s.startswith("mode="))
        assert summary == "mode=on phone=1"
        assert PHONE not in repr(tracker.mock_calls)

    async def test_no_step_without_masker(self):
        use_case, agent, _, tracker = _use_case(["답"])
        await _tokens(use_case, agent)
        names = [c.kwargs.get("node_name") for c in tracker.record_step.call_args_list]
        assert "pii_masking" not in names


def _summaries(logger) -> list[str]:
    return [
        c.kwargs["summary"]
        for c in logger.info.call_args_list
        if c.args and c.args[0] == "PII masking summary"
    ]


class TestSummaryLog:
    """Check G-2 — 런 요약은 성공·실패·한도 초과·승인 재개 모두에 남는다."""

    async def test_summary_logged_once_on_success(self):
        use_case, agent, _, _ = _use_case(["답"], masker=make_masker())
        await _tokens(use_case, agent)
        assert _summaries(use_case._logger) == ["mode=on phone=1"]

    async def test_summary_logged_when_graph_fails(self):
        use_case, agent, _, _ = _use_case(
            ["답"], masker=make_masker(), fail=RuntimeError("boom")
        )
        await _tokens(use_case, agent)
        assert _summaries(use_case._logger) == ["mode=on phone=1"]

    async def test_summary_logged_on_recursion_limit(self):
        from langgraph.errors import GraphRecursionError

        use_case, agent, _, _ = _use_case(
            ["답"], masker=make_masker(), fail=GraphRecursionError("limit")
        )
        await _tokens(use_case, agent)
        assert _summaries(use_case._logger) == ["mode=on phone=1"]

    async def test_no_summary_without_masker(self):
        use_case, agent, _, _ = _use_case(["답"], fail=RuntimeError("boom"))
        await _tokens(use_case, agent)
        assert _summaries(use_case._logger) == []

    async def test_resume_graph_uses_own_scope_and_logs_summary(self):
        masker = make_masker()
        use_case, agent, captured, _ = _use_case(["답"], masker=masker)
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={"messages": [_ai_message("재개 답")]}
        )

        async def _compile(**kwargs):
            captured.update(kwargs)
            masker.mask_messages([HumanMessage(content=PHONE)], kwargs["pii_scope"])
            return graph

        use_case._compiler.compile = AsyncMock(side_effect=_compile)
        use_case._inject_attached_skills = AsyncMock(side_effect=lambda w, a, r: w)
        await use_case._resume_graph({"messages": []}, agent, "req-1")
        assert isinstance(captured["pii_scope"], PiiRunScope)
        assert _summaries(use_case._logger) == ["mode=on phone=1"]


def test_class_default_masker_is_none_for_new_fixtures():
    assert RunAgentUseCase.__new__(RunAgentUseCase)._pii_masker is None
