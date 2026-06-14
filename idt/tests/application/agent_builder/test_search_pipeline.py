"""search_pipeline 단위 테스트 (search-node-query-pipeline Design §4-2).

rewrite → search → validate(루프) → compress 파이프라인을 Fake LLM/Tool로 검증.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.search_pipeline import (
    RewrittenQuery,
    SearchResultVerdict,
    create_search_pipeline_node,
    format_search_result,
    is_search_result,
    is_worker_output,
    latest_user_question,
)
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.domain.agent_builder.policies import SearchPipelinePolicy


# ── Fakes ────────────────────────────────────────────────────────


class _StructuredRunner:
    def __init__(self, owner, schema):
        self._owner = owner
        self._schema = schema

    async def ainvoke(self, messages):
        self._owner.structured_calls.append((self._schema, messages))
        item = self._owner.structured_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeLLM:
    """with_structured_output / ainvoke 응답을 큐로 제어하는 Fake."""

    def __init__(self, structured=None, invokes=None):
        self.structured_responses = list(structured or [])
        self.invoke_responses = list(invokes or [])
        self.structured_calls = []
        self.invoke_calls = []

    def with_structured_output(self, schema):
        return _StructuredRunner(self, schema)

    async def ainvoke(self, messages):
        self.invoke_calls.append(messages)
        item = self.invoke_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return AIMessage(content=item)


class FakeTool:
    """ainvoke 응답/예외를 큐로 제어하고 받은 쿼리를 기록하는 Fake."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.queries = []

    async def ainvoke(self, payload):
        self.queries.append(payload["query"])
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_state(question="대한민국 2025년 실업률 그래프 그려줄래?", token_usage=0):
    return {
        "messages": [HumanMessage(content=question)],
        "token_usage": token_usage,
    }


def _make_node(llm, tool, threshold=4000, worker_id="w1"):
    return create_search_pipeline_node(
        worker_id=worker_id,
        tool=tool,
        pipeline_llm=llm,
        policy=SearchPipelinePolicy(compress_threshold=threshold),
        logger=MagicMock(),
    )


_RQ = RewrittenQuery(query="대한민국 2025년 월별 실업률 통계", reasoning="")
_OK = SearchResultVerdict(relevant=True)


def _bad(improved=""):
    return SearchResultVerdict(relevant=False, reason="무관", improved_query=improved)


# ── 규약 함수 ────────────────────────────────────────────────────


class TestMessageContract:
    def test_format_search_result_prefix(self):
        assert format_search_result("w1", "본문") == "[w1 검색결과]\n본문"

    def test_is_search_result_matches_formatted_message(self):
        msg = AIMessage(content=format_search_result("w1", "본문"), name="w1")
        assert is_search_result(msg) is True

    def test_is_search_result_rejects_dict_and_plain_ai(self):
        assert is_search_result({"role": "user", "content": "검색결과"}) is False
        assert is_search_result(AIMessage(content="그냥 답변", name="w1")) is False

    def test_is_worker_output(self):
        assert is_worker_output(AIMessage(content="x", name="w1")) is True
        assert is_worker_output(AIMessage(content="x")) is False
        assert is_worker_output({"role": "user", "content": "x"}) is False

    def test_latest_user_question_returns_last_human(self):
        messages = [
            HumanMessage(content="첫 질문"),
            AIMessage(content="답변"),
            HumanMessage(content="진짜 질문"),
        ]
        assert latest_user_question(messages) == "진짜 질문"

    def test_latest_user_question_skips_quality_feedback(self):
        """D5: 마지막 user 메시지가 quality_gate 피드백이면 건너뛴다."""
        messages = [
            HumanMessage(content="진짜 질문"),
            AIMessage(content="[w1 검색결과]\n빈약", name="w1"),
            HumanMessage(content="[품질검증 실패] 다시 생성해주세요. (재시도 1/2)"),
        ]
        assert latest_user_question(messages) == "진짜 질문"


# ── 파이프라인 본체 ──────────────────────────────────────────────


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_single_pass(self):
        """정상 1회: rewrite → 검색 1회 → validate 통과."""
        llm = FakeLLM(structured=[_RQ, _OK])
        tool = FakeTool(["실업률 3.2%"])
        result = await _make_node(llm, tool)(_make_state())

        assert tool.queries == ["대한민국 2025년 월별 실업률 통계"]
        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert msg.name == "w1"
        assert msg.content.startswith("[w1 검색결과]\n")
        assert "실업률 3.2%" in msg.content
        assert result["last_worker_id"] == "w1"

    @pytest.mark.asyncio
    async def test_token_usage_increases(self):
        llm = FakeLLM(structured=[_RQ, _OK])
        tool = FakeTool(["a" * 100])
        result = await _make_node(llm, tool)(_make_state(token_usage=50))
        assert result["token_usage"] >= 50 + 100 // 4

    @pytest.mark.asyncio
    async def test_step_summary_recorded(self):
        llm = FakeLLM(structured=[_RQ, _OK])
        tool = FakeTool(["결과"])
        result = await _make_node(llm, tool)(_make_state())
        summary = result[STEP_OUTPUT_SUMMARY_KEY]
        assert "attempts=1" in summary
        assert "compressed=False" in summary


class TestRetryLoop:
    @pytest.mark.asyncio
    async def test_invalid_result_triggers_resarch_with_improved_query(self):
        llm = FakeLLM(structured=[_RQ, _bad("개선 쿼리"), _OK])
        tool = FakeTool(["무관한 결과", "정확한 결과"])
        result = await _make_node(llm, tool)(_make_state())

        assert tool.queries == ["대한민국 2025년 월별 실업률 통계", "개선 쿼리"]
        assert "정확한 결과" in result["messages"][0].content
        assert "attempts=2" in result[STEP_OUTPUT_SUMMARY_KEY]

    @pytest.mark.asyncio
    async def test_exhaustion_uses_last_result_and_skips_final_validate(self):
        """D1: 3회 소진 — 검색 3회, validate는 2회만, 마지막 결과 채택."""
        llm = FakeLLM(structured=[_RQ, _bad("q2"), _bad("q3")])
        tool = FakeTool(["r1", "r2", "r3"])
        result = await _make_node(llm, tool)(_make_state())

        assert tool.queries == ["대한민국 2025년 월별 실업률 통계", "q2", "q3"]
        # rewrite 1 + validate 2 = structured 3회 (마지막 시도 validate 생략)
        assert len(llm.structured_calls) == 3
        assert "r3" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_empty_improved_query_reuses_previous(self):
        llm = FakeLLM(structured=[_RQ, _bad(improved=""), _OK])
        tool = FakeTool(["bad", "good"])
        await _make_node(llm, tool)(_make_state())
        assert tool.queries[1] == tool.queries[0]


class TestFallbacks:
    @pytest.mark.asyncio
    async def test_rewrite_failure_falls_back_to_question(self):
        llm = FakeLLM(structured=[RuntimeError("llm down"), _OK])
        tool = FakeTool(["결과"])
        question = "대한민국 2025년 실업률 그래프 그려줄래?"
        await _make_node(llm, tool)(_make_state(question))
        assert tool.queries == [question]

    @pytest.mark.asyncio
    async def test_rewrite_empty_query_falls_back_to_question(self):
        llm = FakeLLM(structured=[RewrittenQuery(query="  "), _OK])
        tool = FakeTool(["결과"])
        question = "원본 질문"
        await _make_node(llm, tool)(_make_state(question))
        assert tool.queries == [question]

    @pytest.mark.asyncio
    async def test_validate_failure_passes_through(self):
        """validate LLM 예외 → 통과 처리, 재검색 없음."""
        llm = FakeLLM(structured=[_RQ, RuntimeError("judge down")])
        tool = FakeTool(["결과"])
        result = await _make_node(llm, tool)(_make_state())
        assert len(tool.queries) == 1
        assert "결과" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_tool_error_retries_without_validate(self):
        """D4: 도구 예외 → validate 생략 즉시 재시도."""
        llm = FakeLLM(structured=[_RQ, _OK])
        tool = FakeTool([RuntimeError("timeout"), "복구된 결과"])
        result = await _make_node(llm, tool)(_make_state())
        assert len(tool.queries) == 2
        assert "복구된 결과" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_tool_error_exhaustion_returns_failure_message(self):
        llm = FakeLLM(structured=[_RQ])
        tool = FakeTool([RuntimeError("boom")] * 3)
        result = await _make_node(llm, tool)(_make_state())
        msg = result["messages"][0]
        assert "검색 실패" in msg.content
        assert "boom" in msg.content
        assert msg.content.startswith("[w1 검색결과]")


class TestCompression:
    @pytest.mark.asyncio
    async def test_long_result_is_compressed(self):
        llm = FakeLLM(structured=[_RQ, _OK], invokes=["압축본: 3.2%"])
        tool = FakeTool(["긴 결과 " * 100])
        result = await _make_node(llm, tool, threshold=50)(_make_state())
        assert len(llm.invoke_calls) == 1
        assert "압축본: 3.2%" in result["messages"][0].content
        assert "compressed=True" in result[STEP_OUTPUT_SUMMARY_KEY]

    @pytest.mark.asyncio
    async def test_short_result_is_not_compressed(self):
        llm = FakeLLM(structured=[_RQ, _OK], invokes=["호출되면 안 됨"])
        tool = FakeTool(["짧은 결과"])
        result = await _make_node(llm, tool, threshold=4000)(_make_state())
        assert llm.invoke_calls == []
        assert "짧은 결과" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_compress_failure_keeps_original(self):
        llm = FakeLLM(structured=[_RQ, _OK], invokes=[RuntimeError("down")])
        original = "원문 결과 " * 100
        tool = FakeTool([original])
        result = await _make_node(llm, tool, threshold=50)(_make_state())
        assert original.strip() in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_failed_search_is_not_compressed(self):
        """검색 실패 메시지는 압축 대상이 아니다."""
        llm = FakeLLM(structured=[_RQ], invokes=["호출되면 안 됨"])
        tool = FakeTool([RuntimeError("x" * 200)] * 3)
        await _make_node(llm, tool, threshold=50)(_make_state())
        assert llm.invoke_calls == []


class TestRewriteInput:
    @pytest.mark.asyncio
    async def test_question_extracted_when_last_message_is_feedback(self):
        """D5: 마지막 메시지가 quality_gate 피드백이어도 진짜 질문으로 rewrite."""
        llm = FakeLLM(structured=[_RQ, _OK])
        tool = FakeTool(["결과"])
        state = {
            "messages": [
                HumanMessage(content="진짜 질문"),
                AIMessage(content="[w1 검색결과]\n빈약", name="w1"),
                HumanMessage(content="[품질검증 실패] 다시 생성해주세요."),
            ],
            "token_usage": 0,
        }
        await _make_node(llm, tool)(state)

        _, rewrite_messages = llm.structured_calls[0]
        user_content = rewrite_messages[-1]["content"]
        assert "진짜 질문" in user_content
        # 워커 산출물은 rewrite 맥락에서 제외
        assert "빈약" not in user_content
