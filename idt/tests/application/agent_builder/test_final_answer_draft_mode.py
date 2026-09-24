"""final_answer 초안 보존 모드 테스트.

Design Ref: action-category-compose-node §8.2 #22~#24 / D-07 / Plan FR-17·FR-20
  - 초안 메시지가 없으면 프롬프트에 초안 블록·지시가 붙지 않는다 (무회귀)
  - 초안 메시지가 있으면 초안 원문 + 집행 결과 블록, user tail 에 재작성 금지 지시
  - 재개 시 주입된 같은 워커의 후속 산출이 집행 결과가 된다
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.search_pipeline import format_draft_output
from tests.application.agent_builder.test_final_answer_node import (
    _content_of,
    _make_node,
    _make_state,
    _mock_llm,
    _role_of,
)

_DRAFT = "안녕하세요 고객님,\n문의하신 건은 처리되었습니다."


class TestFinalAnswerDraftMode:
    @pytest.mark.asyncio
    async def test_no_draft_prompt_has_no_draft_block(self):
        mock_llm = _mock_llm()
        await _make_node(mock_llm)(_make_state([
            HumanMessage(content="분석해줘"),
            AIMessage(content="결과", name="analyst"),
        ]))
        messages = mock_llm.ainvoke.call_args[0][0]
        assert "[작성된 초안" not in _content_of(messages[0])
        assert "재작성하지" not in _content_of(messages[0])

    @pytest.mark.asyncio
    async def test_draft_is_included_verbatim_with_outcome(self):
        mock_llm = _mock_llm()
        await _make_node(mock_llm)(_make_state([
            HumanMessage(content="회신 보내줘"),
            AIMessage(
                content=format_draft_output("mailer", _DRAFT, "메일 발송 성공"),
                name="mailer",
            ),
        ]))
        messages = mock_llm.ainvoke.call_args[0][0]
        system = _content_of(messages[0])
        assert "[작성된 초안" in system and _DRAFT in system
        assert "[집행 결과]" in system and "메일 발송 성공" in system
        # 초안 메시지는 [워커 작업 결과]에 중복 게재되지 않는다
        assert system.count(_DRAFT) == 1
        # 지시는 system prompt에 — user tail은 마지막이 assistant일 때만 붙는다
        assert "그대로" in system and "재작성" in system
        assert _role_of(messages[-1]) == "user"

    @pytest.mark.asyncio
    async def test_resumed_outcome_overrides_pending_notice(self):
        mock_llm = _mock_llm()
        await _make_node(mock_llm)(_make_state([
            HumanMessage(content="회신 보내줘"),
            AIMessage(
                content=format_draft_output("mailer", _DRAFT, "승인 대기로 등록되었습니다."),
                name="mailer",
            ),
            AIMessage(content="메일 발송 성공 (id=42)", name="mailer"),
        ]))
        system = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        outcome_part = system.split("[집행 결과]")[1]
        assert "메일 발송 성공 (id=42)" in outcome_part
        assert "승인 대기로 등록되었습니다." not in outcome_part

    @pytest.mark.asyncio
    async def test_other_workers_still_summarized(self):
        """초안 모드에서도 검색 결과 블록은 그대로 실린다."""
        mock_llm = _mock_llm()
        await _make_node(mock_llm)(_make_state([
            HumanMessage(content="회신 보내줘"),
            AIMessage(content="[searcher 검색결과]\n배송 지연 이력", name="searcher"),
            AIMessage(content=format_draft_output("mailer", _DRAFT, "ok"), name="mailer"),
        ]))
        system = _content_of(mock_llm.ainvoke.call_args[0][0][0])
        assert "[수집된 검색 결과]" in system and "배송 지연 이력" in system
