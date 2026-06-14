"""final_answer 노드 단위 테스트 (TC-F01~F07).

final-answer-node Design §3-3 — 검색·분석·차트 결과를 종합하는 필수 최종 답변 노드.
멀티턴 회귀(TC-F04)는 구 answer_agent의 fix-answer-node-multiturn-context에서 이관.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_compiler() -> WorkflowCompiler:
    tool_factory = MagicMock(spec=ToolFactory)
    llm_factory = MagicMock()
    logger = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
    )


def _make_node(mock_llm, system_prompt: str = "당신은 AI 에이전트입니다."):
    return _make_compiler()._create_final_answer_node(mock_llm, system_prompt)


def _mock_llm(answer: str = "종합 답변입니다.") -> AsyncMock:
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content=answer)
    return llm


def _make_state(messages: list, charts: list | None = None, token_usage: int = 0) -> dict:
    state = {"messages": messages, "token_usage": token_usage}
    if charts is not None:
        state["charts"] = charts
    return state


def _content_of(msg) -> str:
    return msg["content"] if isinstance(msg, dict) else getattr(msg, "content", "")


def _role_of(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("role", "")
    msg_type = getattr(msg, "type", "")
    if msg_type == "human":
        return "user"
    if msg_type == "ai":
        return "assistant"
    return msg_type


class TestFinalAnswerSynthesis:
    @pytest.mark.asyncio
    async def test_mixed_search_and_work_results_in_blocks(self):
        """TC-F01: 검색결과+분석결과 혼합 → 두 블록 모두 system prompt에 포함."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state([
            HumanMessage(content="부서별 매출 분석해줘"),
            AIMessage(content="[web_searcher 검색결과]\n시장 동향 자료", name="web_searcher"),
            AIMessage(content="매출은 영업부가 가장 높습니다.", name="data_analyst"),
        ])
        await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "[수집된 검색 결과]" in system_content
        assert "시장 동향 자료" in system_content
        assert "[워커 작업 결과]" in system_content
        assert "매출은 영업부가 가장 높습니다." in system_content
        # 작업 결과에는 worker_id 라벨 포함
        assert "[data_analyst]" in system_content

    @pytest.mark.asyncio
    async def test_search_only_collects_by_tag(self):
        """이관 TC-A01: 검색결과 메시지 수집."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state([
            HumanMessage(content="AI 기술 동향 알려줘"),
            AIMessage(content="[w 검색결과]\n문서1: AI 기술", name="w"),
            AIMessage(content="[w 검색결과]\n문서2: 최신 동향", name="w"),
        ])
        await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "문서1: AI 기술" in system_content
        assert "문서2: 최신 동향" in system_content

    @pytest.mark.asyncio
    async def test_includes_system_prompt(self):
        """이관 TC-A02: system_prompt가 answer prompt에 포함."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm, system_prompt="커스텀 프롬프트")

        state = _make_state([
            HumanMessage(content="질문"),
            AIMessage(content="[w 검색결과]\n데이터", name="w"),
        ])
        await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "커스텀 프롬프트" in system_content

    @pytest.mark.asyncio
    async def test_no_worker_outputs_uses_fallback(self):
        """TC-F05: 워커 산출물 0건 → '(수집된 결과 없음)' fallback."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state([HumanMessage(content="질문")])
        await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "(수집된 결과 없음)" in system_content

    @pytest.mark.asyncio
    async def test_returns_final_answer_worker_id_and_token_usage(self):
        """TC-F06: last_worker_id == 'final_answer', token_usage 증가."""
        mock_llm = _mock_llm("정제된 최종 답변")
        node = _make_node(mock_llm)

        state = _make_state(
            [
                HumanMessage(content="질문"),
                AIMessage(content="[w 검색결과]\n데이터", name="w"),
            ],
            token_usage=100,
        )
        result = await node(state)

        assert result["last_worker_id"] == "final_answer"
        assert result["token_usage"] > 100
        assert result["messages"][0].content == "정제된 최종 답변"


class TestFinalAnswerCharts:
    def _chart(self, chart_type: str = "bar", title: str = "부서별 매출") -> dict:
        return {
            "type": chart_type,
            "data": {"labels": ["a"], "datasets": []},
            "options": {"plugins": {"title": {"text": title}}},
        }

    @pytest.mark.asyncio
    async def test_charts_meta_in_prompt_and_not_in_result(self):
        """TC-F02: 차트 존재 → 메타(개수/type/title)+JSON 금지 지시, 반환에 charts 키 없음."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state(
            [
                HumanMessage(content="매출 차트로 보여줘"),
                AIMessage(content="분석 결과입니다.", name="analyst"),
            ],
            charts=[self._chart("bar", "부서별 매출"), self._chart("line", "월별 추이")],
        )
        result = await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "[생성된 차트]" in system_content
        assert "2개" in system_content
        assert "bar — 부서별 매출" in system_content
        assert "line — 월별 추이" in system_content
        assert "JSON" in system_content  # JSON 출력 금지 지시
        # charts 비파괴: 반환 dict에 charts 미포함 → state 병합으로 보존
        assert "charts" not in result

    @pytest.mark.asyncio
    async def test_empty_charts_omits_block(self):
        """TC-F03: charts 빈 리스트 → 차트 블록 생략."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state(
            [
                HumanMessage(content="질문"),
                AIMessage(content="[w 검색결과]\n데이터", name="w"),
            ],
            charts=[],
        )
        await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "[생성된 차트]" not in system_content

    @pytest.mark.asyncio
    async def test_chart_without_title_is_graceful(self):
        """차트 메타 키 부재 시 graceful — '(제목 없음)' 표기."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state(
            [
                HumanMessage(content="질문"),
                AIMessage(content="분석", name="analyst"),
            ],
            charts=[{"type": "pie", "data": {}}],
        )
        await node(state)

        system_content = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "pie — (제목 없음)" in system_content


class TestFinalAnswerMultiturn:
    """TC-F04: 멀티턴 회귀 — 구 answer_agent TC-A06~A08 이관."""

    @pytest.mark.asyncio
    async def test_passes_full_conversation_with_latest_user_question(self):
        """멀티턴 state에서 LLM에 전체 대화 + 최신 user 질문이 마지막에 위치."""
        mock_llm = _mock_llm("내부문서 기반 답변")
        node = _make_node(mock_llm, system_prompt="당신은 어시스턴트입니다.")

        state = _make_state([
            HumanMessage(content="안녕"),
            AIMessage(content="안녕하세요!"),
            HumanMessage(content="우리 내부문서에서 X 알려줘"),
            AIMessage(
                content="[research_worker 검색결과]\nX는 ...",
                name="research_worker",
            ),
        ])
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        assert _role_of(sent[0]) == "system"
        system_content = _content_of(sent[0])
        assert "[수집된 검색 결과]" in system_content
        assert "X는 ..." in system_content

        body = sent[1:]
        assert len(body) >= 3, f"전체 대화 맥락이 전달되어야 함, got {len(body)} messages"

        user_msgs = [m for m in body if _role_of(m) == "user"]
        assert len(user_msgs) == 2
        assert _content_of(user_msgs[0]) == "안녕"
        assert _content_of(user_msgs[-1]) == "우리 내부문서에서 X 알려줘"

        for m in body:
            assert "검색결과" not in _content_of(m), "워커 산출물은 본체에서 제외되어야 함"

    @pytest.mark.asyncio
    async def test_first_user_message_alone_is_not_sent(self):
        """레거시 버그 회귀 방지 — 단일 user='안녕'만 LLM에 전달되면 안 된다."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state([
            HumanMessage(content="안녕"),
            AIMessage(content="안녕하세요!"),
            HumanMessage(content="내부문서 X"),
            AIMessage(content="[w 검색결과]\n데이터", name="w"),
        ])
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        user_contents = [_content_of(m) for m in sent if _role_of(m) == "user"]
        assert user_contents != ["안녕"], "레거시 버그 회귀: 첫 user='안녕'만 전달되고 있음"
        assert "내부문서 X" in user_contents

    @pytest.mark.asyncio
    async def test_all_worker_outputs_excluded_from_body(self):
        """워커 산출물(AIMessage name 보유)은 전부 본체 제외 — 검색·분석 공통 (DQ4)."""
        mock_llm = _mock_llm()
        node = _make_node(mock_llm)

        state = _make_state([
            HumanMessage(content="질문"),
            AIMessage(content="[research 검색결과]\n자료1", name="research"),
            AIMessage(content="분석결과: 매출 상승", name="analyst"),
            AIMessage(content="name 없는 일반 assistant 메시지"),
        ])
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        body = sent[1:]
        body_contents = [_content_of(m) for m in body]
        assert all("자료1" not in c for c in body_contents)
        assert all("분석결과" not in c for c in body_contents)
        # name 없는 assistant 메시지는 대화 본체에 유지
        assert any("name 없는 일반" in c for c in body_contents)

        system_content = _content_of(sent[0])
        assert "자료1" in system_content
        assert "매출 상승" in system_content
