"""supervisor 위키 지침·수집 실패 블록 테스트 (wiki-guided-routing D3/D4).

- D3: wiki_guidance_block은 전달된 그대로 결정 프롬프트에 실린다(빈 문자열이면 무영향).
- D4: state.last_worker_error가 비어 있지 않을 때만 "[직전 수집 실패]" 블록을 렌더하고,
  결정 직후 ""로 리셋한다. wiki 워커가 있고 이번 턴에 미열람이면 위키 안내 줄을 넣는다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    _render_worker_error_block,
    build_initial_state,
    create_supervisor_node,
)
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition
from src.domain.conversation.analysis_snapshot_policy import REINJECTED_MARKER

WIKI = "wiki_read_worker"
SCRAPE = "mcp_scrape_worker"


def _wiki_worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="wiki_read", worker_id=WIKI, description="위키 열람", sort_order=0,
    )


def _scrape_worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="mcp:srv:scrape_url", worker_id=SCRAPE, description="스크래핑", sort_order=1,
    )


def _llm_capturing(next_worker: str = "FINISH"):
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = next_worker
    decision.answer = ""
    decision.reasoning = "r"
    decision.task = "t"
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=decision)
    mock_llm.with_structured_output.return_value = structured
    return mock_llm, structured


def _state(messages=None, last_worker_error: str = "", last_worker_id: str = "") -> dict:
    state = build_initial_state(
        messages=messages or [HumanMessage(content="저축은행 금리 표 보여줘")],
        config=SupervisorConfig(max_iterations=10, token_limit=8000),
        available_workers=[WIKI, SCRAPE],
    )
    state["last_worker_error"] = last_worker_error
    state["last_worker_id"] = last_worker_id
    return state


def _node(llm, workers, **kwargs):
    return create_supervisor_node(
        llm=llm, workers=workers, supervisor_prompt="지침",
        hooks=DefaultHooks(), logger=MagicMock(), **kwargs,
    )


def _prompt(structured) -> str:
    return structured.ainvoke.call_args.args[0][0]["content"]


class TestInitialState:
    def test_last_worker_error_defaults_to_empty(self):
        state = build_initial_state(
            messages=[], config=SupervisorConfig(), available_workers=[],
        )
        assert state["last_worker_error"] == ""


class TestRenderWorkerErrorBlock:
    def test_empty_error_renders_nothing(self):
        assert _render_worker_error_block(_state(), WIKI) == ""

    def test_error_with_unread_wiki_mentions_wiki_first(self):
        block = _render_worker_error_block(
            _state(last_worker_error="Error executing tool scrape_url: DNS", last_worker_id=SCRAPE),
            WIKI,
        )
        assert block.startswith("\n\n[직전 수집 실패]")
        assert SCRAPE in block and "Error executing tool scrape_url: DNS" in block
        assert WIKI in block
        assert "FINISH" in block and "추측" in block

    def test_error_after_wiki_read_this_turn_omits_wiki_line(self):
        msgs = [
            HumanMessage(content="질문"),
            AIMessage(content="지침: https://www.fsb.or.kr/x", name=WIKI),
            AIMessage(content="실패", name=SCRAPE),
        ]
        block = _render_worker_error_block(
            _state(messages=msgs, last_worker_error="DNS 실패", last_worker_id=SCRAPE), WIKI,
        )
        assert "[직전 수집 실패]" in block
        assert WIKI not in block

    def test_wiki_read_in_previous_turn_does_not_count(self):
        msgs = [
            HumanMessage(content="이전 질문"),
            AIMessage(content="지침", name=WIKI),
            HumanMessage(content="새 질문"),
            AIMessage(content="실패", name=SCRAPE),
        ]
        block = _render_worker_error_block(
            _state(messages=msgs, last_worker_error="DNS 실패", last_worker_id=SCRAPE), WIKI,
        )
        assert WIKI in block

    def test_reinjected_snapshot_does_not_count_as_wiki_read(self):
        msgs = [
            HumanMessage(content="새 질문"),
            AIMessage(content=f"{REINJECTED_MARKER} (질문: q)\n지침", name=WIKI),
            AIMessage(content="실패", name=SCRAPE),
        ]
        block = _render_worker_error_block(
            _state(messages=msgs, last_worker_error="DNS 실패", last_worker_id=SCRAPE), WIKI,
        )
        assert WIKI in block

    def test_no_wiki_worker_keeps_fallback_without_wiki_line(self):
        block = _render_worker_error_block(
            _state(last_worker_error="DNS 실패", last_worker_id=SCRAPE), "",
        )
        assert "[직전 수집 실패]" in block
        assert "wiki" not in block.lower()
        assert "FINISH" in block


class TestSupervisorNodeIntegration:
    @pytest.mark.asyncio
    async def test_wiki_guidance_block_included_verbatim(self):
        llm, structured = _llm_capturing()
        node = _node(
            llm, [_wiki_worker(), _scrape_worker()],
            wiki_guidance_block="\n\n[위키 지침 처리 기준]\n먼저 wiki_read_worker",
            wiki_worker_id=WIKI,
        )
        await node(_state())
        assert "[위키 지침 처리 기준]" in _prompt(structured)

    @pytest.mark.asyncio
    async def test_no_blocks_when_no_error_and_no_guidance(self):
        llm, structured = _llm_capturing()
        node = _node(llm, [_scrape_worker()])
        await node(_state())
        prompt = _prompt(structured)
        assert "[직전 수집 실패]" not in prompt and "[위키 지침 처리 기준]" not in prompt

    @pytest.mark.asyncio
    async def test_error_block_rendered_and_state_reset(self):
        llm, structured = _llm_capturing(next_worker=WIKI)
        node = _node(llm, [_wiki_worker(), _scrape_worker()], wiki_worker_id=WIKI)
        out = await node(_state(last_worker_error="DNS 실패", last_worker_id=SCRAPE))
        assert "[직전 수집 실패]" in _prompt(structured)
        assert out["last_worker_error"] == ""
        assert out["next_worker"] == WIKI

    @pytest.mark.asyncio
    async def test_finish_with_answer_also_resets_error(self):
        llm, structured = _llm_capturing()
        structured.ainvoke.return_value.answer = "어느 사이트를 대상으로 할까요?"
        node = _node(llm, [_scrape_worker()])
        out = await node(_state(last_worker_error="DNS 실패"))
        assert out["last_worker_error"] == ""
        assert out["next_worker"] == "__end__"

    @pytest.mark.asyncio
    async def test_legacy_state_without_key_is_tolerated(self):
        llm, structured = _llm_capturing()
        node = _node(llm, [_scrape_worker()])
        state = _state()
        del state["last_worker_error"]
        out = await node(state)
        assert "[직전 수집 실패]" not in _prompt(structured)
        assert out["last_worker_error"] == ""
