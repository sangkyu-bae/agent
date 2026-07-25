"""supervisor 과차단 방지 지시 테스트 (supervisor-overblock-fix D3).

Design §6.2:
- TC-O01: 결정 프롬프트에 권한·개인정보를 이유로 한 FINISH 금지 지시 포함 (FR-02)
- TC-O02: FINISH+answer+워커 미실행의 정당한 직접 응답 경로 보존 (FR-05)

캡처 패턴은 test_supervisor_data_context.py와 동일 (mock LLM system 메시지 검사).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import create_supervisor_node
from src.domain.agent_builder.schemas import WorkerDefinition


def _make_state(messages: list) -> dict:
    return {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["search_worker"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
        "attachments": [],
        "viz_decision": "",
    }


def _llm_returning(next_: str, answer: str = ""):
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = next_
    decision.answer = answer
    decision.reasoning = "r"
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=decision
    )
    return mock_llm


def _make_node(mock_llm):
    return create_supervisor_node(
        llm=mock_llm,
        workers=[WorkerDefinition("t", "search_worker", "내부 문서 검색", 0)],
        supervisor_prompt="지침",
        hooks=DefaultHooks(),
        logger=MagicMock(),
    )


class TestOverblockGuardInstruction:
    @pytest.mark.asyncio
    async def test_decision_prompt에_과차단_금지_지시_포함(self):
        """TC-O01: 권한·개인정보를 이유로 FINISH 금지 + 도구 위임 명시."""
        mock_llm = _llm_returning("search_worker")
        node = _make_node(mock_llm)

        await node(_make_state([HumanMessage(content="나의 남은 휴가 개수")]))

        sent = mock_llm.with_structured_output.return_value.ainvoke.call_args[0][0]
        system_content = sent[0]["content"]
        assert "'FINISH'를 선택하지 마세요" in system_content
        assert "도구가 자동으로 검증" in system_content

    @pytest.mark.asyncio
    async def test_finish_직접_응답_경로_보존(self):
        """TC-O02 (FR-05): 단순 대화의 FINISH+answer 직접 응답은 기존 동작 유지."""
        mock_llm = _llm_returning("FINISH", answer="안녕하세요!")
        node = _make_node(mock_llm)

        result = await node(_make_state([HumanMessage(content="안녕")]))

        assert result["next_worker"] == "__end__"
        assert result["messages"][0].content == "안녕하세요!"
