"""supervisor 문서생성 라우팅 가이드 블록 테스트 (doc-generator D6).

조사 강제가 아니라 문맥 판단 기준 제시 — generator+타 워커 공존 시에만 주입.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import create_supervisor_node
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.llm.interfaces import LLMFactoryInterface


def _compiler() -> WorkflowCompiler:
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    return WorkflowCompiler(
        tool_factory=MagicMock(), llm_factory=llm_factory, logger=MagicMock(),
    )


def _gen_worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="document_generator", worker_id="document_generator_worker",
        description="문서생성기", sort_order=0,
    )


def _search_worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="tavily_search", worker_id="tavily_search_worker",
        description="웹 검색", sort_order=1, category="search",
    )


def _analysis_worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="data_analysis", worker_id="data_analysis_worker",
        description="데이터 분석", sort_order=2, category="analysis",
    )


class TestRenderDocgenGuidanceBlock:
    def test_generator_with_search_and_analysis_renders_block(self):
        block = _compiler()._render_docgen_guidance_block(
            [_gen_worker(), _search_worker(), _analysis_worker()]
        )
        assert "document_generator_worker" in block
        assert "tavily_search_worker" in block
        assert "data_analysis_worker" in block
        # 판단 기준: 충분하면 바로 위임 / 부족하면 수집 후 위임 (순서 강제 아님)
        assert "충분하면" in block
        assert "바로" in block

    def test_generator_only_returns_empty(self):
        assert _compiler()._render_docgen_guidance_block([_gen_worker()]) == ""

    def test_no_generator_returns_empty(self):
        assert _compiler()._render_docgen_guidance_block(
            [_search_worker(), _analysis_worker()]
        ) == ""


class TestSupervisorPromptIncludesDocgenBlock:
    def _llm_capturing(self):
        mock_llm = MagicMock()
        decision = MagicMock()
        decision.next = "FINISH"
        decision.answer = ""
        decision.reasoning = "r"
        structured = MagicMock()
        structured.ainvoke = AsyncMock(return_value=decision)
        mock_llm.with_structured_output.return_value = structured
        return mock_llm, structured

    def _state(self) -> dict:
        return {
            "messages": [HumanMessage(content="휴가계획서 작성해줘")],
            "iteration_count": 0,
            "max_iterations": 10,
            "token_usage": 0,
            "token_limit": 8000,
            "next_worker": "",
            "last_worker_id": "",
            "available_workers": [],
            "quality_gate_enabled": False,
            "retry_counts": {},
            "max_retries_per_worker": 2,
            "forced_worker": "",
            "skipped_workers": [],
            "quality_gate_result": "",
            "attachments": [],
            "viz_decision": "",
        }

    @pytest.mark.asyncio
    async def test_block_included_in_decision_prompt(self):
        mock_llm, structured = self._llm_capturing()
        node = create_supervisor_node(
            llm=mock_llm,
            workers=[_gen_worker(), _search_worker()],
            supervisor_prompt="지침",
            hooks=DefaultHooks(),
            logger=MagicMock(),
            docgen_guidance_block="\n\n[문서 생성 처리 기준]\n충분하면 바로 위임",
        )
        await node(self._state())
        prompt = structured.ainvoke.call_args.args[0][0]["content"]
        assert "[문서 생성 처리 기준]" in prompt

    @pytest.mark.asyncio
    async def test_empty_block_leaves_prompt_unchanged(self):
        mock_llm, structured = self._llm_capturing()
        node = create_supervisor_node(
            llm=mock_llm,
            workers=[_search_worker()],
            supervisor_prompt="지침",
            hooks=DefaultHooks(),
            logger=MagicMock(),
        )
        await node(self._state())
        prompt = structured.ainvoke.call_args.args[0][0]["content"]
        assert "[문서 생성 처리 기준]" not in prompt
