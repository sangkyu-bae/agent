"""supervisor 보유 분석 데이터 인지 블록 + 분석 노드 부족-명시 규약 테스트.

analysis-data-continuity Design §3.5 (D5) / §3.6 (D6), T6.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    _render_data_context_block,
    create_supervisor_node,
)
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _search_msg(worker: str = "search_worker", body: str = "휴가 15일") -> AIMessage:
    return AIMessage(content=f"[{worker} 검색결과]\n{body}", name=worker)


def _make_state(messages: list) -> dict:
    return {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["data_analysis"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
        "quality_gate_result": "",
        "attachments": [],
        "viz_decision": "",
    }


def _llm_returning(next_: str):
    mock_llm = MagicMock()
    decision = MagicMock()
    decision.next = next_
    decision.answer = ""
    decision.reasoning = "r"
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=decision
    )
    return mock_llm


class TestRenderDataContextBlock:
    def test_검색결과_있으면_보유_데이터_블록_생성(self):
        block = _render_data_context_block(
            [HumanMessage(content="q"), _search_msg()]
        )
        assert "[보유 분석 데이터]" in block
        assert "search_worker" in block
        assert "범위를 벗어나면" in block
        assert "검색 워커" in block

    def test_검색결과_없으면_빈_문자열(self):
        assert _render_data_context_block([HumanMessage(content="q")]) == ""

    def test_dict_히스토리만_있으면_빈_문자열(self):
        messages = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "[w 검색결과]\n데이터"},
        ]
        assert _render_data_context_block(messages) == ""


class TestSupervisorPromptIncludesDataBlock:
    @pytest.mark.asyncio
    async def test_decision_prompt에_보유_데이터_블록_포함(self):
        mock_llm = _llm_returning("FINISH")
        node = create_supervisor_node(
            llm=mock_llm,
            workers=[WorkerDefinition("t", "data_analysis", "분석", 0)],
            supervisor_prompt="지침",
            hooks=DefaultHooks(),
            logger=MagicMock(),
        )
        state = _make_state([HumanMessage(content="전체 사용자 그래프"), _search_msg()])
        await node(state)

        sent = mock_llm.with_structured_output.return_value.ainvoke.call_args[0][0]
        system_content = sent[0]["content"]
        assert "[보유 분석 데이터]" in system_content

    @pytest.mark.asyncio
    async def test_검색결과_없으면_블록_미포함(self):
        mock_llm = _llm_returning("FINISH")
        node = create_supervisor_node(
            llm=mock_llm,
            workers=[WorkerDefinition("t", "data_analysis", "분석", 0)],
            supervisor_prompt="지침",
            hooks=DefaultHooks(),
            logger=MagicMock(),
        )
        await node(_make_state([HumanMessage(content="안녕")]))

        sent = mock_llm.with_structured_output.return_value.ainvoke.call_args[0][0]
        assert "[보유 분석 데이터]" not in sent[0]["content"]


class TestAnalysisPromptDataGapGuide:
    @pytest.mark.asyncio
    async def test_분석_프롬프트에_부족_명시_지시_포함(self):
        """D6: 데이터 부족 시 '제공해달라' 대신 부족분을 명시하도록 지시."""
        compiler = WorkflowCompiler(
            tool_factory=MagicMock(spec=ToolFactory),
            llm_factory=MagicMock(),
            logger=MagicMock(),
        )
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="분석")

        node = compiler._create_analysis_node(mock_llm, "analyst", "시스템")
        await node(_make_state([HumanMessage(content="전체 사용자 분석해줘")]))

        system_content = mock_llm.ainvoke.call_args[0][0][0]["content"]
        assert "데이터 제공을 요청하지 마세요" in system_content
        assert "추가 수집" in system_content
