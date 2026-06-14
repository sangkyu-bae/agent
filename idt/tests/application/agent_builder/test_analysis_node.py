"""Analysis Node 단위 테스트 — category='analysis' 전용 노드 (TC-AN01~AN08).

분석 노드 동작:
- attachments에 엑셀이 있으면 주입된 ExcelAnalysisWorkflow를 래핑 호출
- 없으면 검색결과(있으면)/전체 대화 문맥(없으면)을 질문 기준으로 LLM 분석
- 분석 결과만 AIMessage(name=worker_id)로 반환 후 supervisor 복귀
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_compiler(excel_getter=None) -> WorkflowCompiler:
    tool_factory = MagicMock(spec=ToolFactory)
    llm_factory = MagicMock()
    logger = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
        excel_analysis_workflow_getter=excel_getter,
    )


def _state(messages: list, token_usage: int = 0, attachments=None) -> dict:
    return {
        "messages": messages,
        "token_usage": token_usage,
        "attachments": attachments or [],
    }


class TestAnalysisNodeExcelBranch:
    @pytest.mark.asyncio
    async def test_excel_branch_wraps_workflow(self):
        """TC-AN01: attachments 엑셀 존재 시 ExcelAnalysisWorkflow.run 호출 + analysis_text 반환."""
        fake_wf = MagicMock()
        fake_wf.run = AsyncMock(return_value={"analysis_text": "매출 15% 증가"})
        compiler = _make_compiler(excel_getter=lambda: fake_wf)

        node = compiler._create_analysis_node(AsyncMock(), "analyst", "프롬프트")
        state = _state(
            [HumanMessage(content="매출 추이 분석해줘")],
            attachments=[{"type": "excel", "file_path": "/tmp/s.xlsx", "user_id": "u1"}],
        )
        result = await node(state)

        fake_wf.run.assert_awaited_once()
        called_initial = fake_wf.run.call_args[0][0]
        assert called_initial["user_query"] == "매출 추이 분석해줘"
        assert called_initial["excel_data"]["file_path"] == "/tmp/s.xlsx"
        assert "매출 15% 증가" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_excel_workflow_failure_returns_error_message(self):
        """TC-AN02: 워크플로우 예외 시 에러 메시지 반환 (그래프 비중단)."""
        fake_wf = MagicMock()
        fake_wf.run = AsyncMock(side_effect=RuntimeError("parse error"))
        compiler = _make_compiler(excel_getter=lambda: fake_wf)

        node = compiler._create_analysis_node(AsyncMock(), "analyst", "프롬프트")
        state = _state(
            [HumanMessage(content="분석")],
            attachments=[{"type": "excel", "file_path": "/tmp/s.xlsx", "user_id": "u1"}],
        )
        result = await node(state)

        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert "엑셀 분석 실패" in msg.content
        assert "parse error" in msg.content

    @pytest.mark.asyncio
    async def test_no_excel_getter_graceful_falls_back_to_context(self):
        """TC-AN03: getter=None인데 엑셀 첨부 시 LLM 문맥 분석으로 fallback (워크플로우 미호출)."""
        compiler = _make_compiler(excel_getter=None)
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="문맥 기반 분석")

        node = compiler._create_analysis_node(mock_llm, "analyst", "프롬프트")
        state = _state(
            [HumanMessage(content="분석")],
            attachments=[{"type": "excel", "file_path": "/tmp/s.xlsx"}],
        )
        result = await node(state)

        mock_llm.ainvoke.assert_awaited_once()
        assert "문맥 기반 분석" in result["messages"][0].content


class TestAnalysisNodeContextBranch:
    @pytest.mark.asyncio
    async def test_uses_search_results_when_present(self):
        """TC-AN04: 검색결과 AIMessage가 있으면 분석 컨텍스트로 LLM에 전달."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="분석 결과")

        node = compiler._create_analysis_node(mock_llm, "analyst", "시스템")
        state = _state([
            HumanMessage(content="이 자료 분석해줘"),
            AIMessage(content="[search_worker 검색결과]\n매출표 데이터", name="search_worker"),
        ])
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        system_content = sent[0]["content"]
        assert "매출표 데이터" in system_content
        assert "이 자료 분석해줘" in system_content

    @pytest.mark.asyncio
    async def test_uses_full_context_when_no_search(self):
        """TC-AN05: 검색결과 없으면 전체 대화 문맥 기준 분석 안내 문구 포함."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="분석")

        node = compiler._create_analysis_node(mock_llm, "analyst", "시스템")
        state = _state([
            HumanMessage(content="대화 내용 요약 분석해줘"),
        ])
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        system_content = sent[0]["content"]
        assert "전체 대화 문맥" in system_content

    @pytest.mark.asyncio
    async def test_search_result_excluded_from_conversation_body(self):
        """TC-AN06: 검색결과 AIMessage는 LLM messages 본체에서 제외."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="분석")

        node = compiler._create_analysis_node(mock_llm, "analyst", "시스템")
        state = _state([
            HumanMessage(content="질문"),
            AIMessage(content="[w 검색결과]\n자료", name="w"),
        ])
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        body = sent[1:]
        for m in body:
            content = m["content"] if isinstance(m, dict) else getattr(m, "content", "")
            assert "검색결과" not in content


class TestAnalysisNodeReturn:
    @pytest.mark.asyncio
    async def test_returns_aimessage_named_worker_id(self):
        """TC-AN07: 분석 결과를 name=worker_id AIMessage로 반환, last_worker_id 설정."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="결과")

        node = compiler._create_analysis_node(mock_llm, "my_analyst", "시스템")
        result = await node(_state([HumanMessage(content="q")]))

        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert msg.name == "my_analyst"
        assert result["last_worker_id"] == "my_analyst"

    @pytest.mark.asyncio
    async def test_increments_token_usage(self):
        """TC-AN08: token_usage 증가."""
        compiler = _make_compiler()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="a" * 200)

        node = compiler._create_analysis_node(mock_llm, "w", "시스템")
        result = await node(_state([HumanMessage(content="q")], token_usage=10))

        assert result["token_usage"] > 10
