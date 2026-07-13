"""analysis_node/워크플로우 원천 방출 테스트 (analysis-source-preservation T2/T5)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_compiler(excel_getter=None) -> WorkflowCompiler:
    return WorkflowCompiler(
        tool_factory=MagicMock(spec=ToolFactory),
        llm_factory=MagicMock(),
        logger=MagicMock(),
        excel_analysis_workflow_getter=excel_getter,
    )


def _state(messages, token_usage=0, attachments=None):
    return {
        "messages": messages, "token_usage": token_usage,
        "attachments": attachments or [],
    }


_PARSED = {
    "file_id": "f1", "filename": "vac.xlsx",
    "sheets": {"Sheet1": {"sheet_name": "Sheet1", "columns": ["월", "잔여"],
                          "data": [{"월": "1월", "잔여": 14}],
                          "dtypes": {}, "row_count": 1, "column_count": 2}},
    "metadata": {},
}
_EXCEL_ATTACH = [{"type": "excel", "file_path": "/tmp/s.xlsx", "user_id": "u1"}]


class TestRunExcelAnalysisTuple:
    @pytest.mark.asyncio
    async def test_파싱된_원천을_텍스트와_함께_반환(self):
        wf = MagicMock()
        wf.run = AsyncMock(return_value={
            "analysis_text": "남은 연차 14일", "excel_data": _PARSED,
        })
        compiler = _make_compiler()
        text, raw = await compiler._run_excel_analysis(
            wf, "휴가 분석", {"file_path": "/tmp/s.xlsx"}, MagicMock(),
        )
        assert text == "남은 연차 14일"
        assert raw is _PARSED

    @pytest.mark.asyncio
    async def test_미파싱_excel_data는_raw_None(self):
        """워크플로우가 원천 미산출(원본 {file_path}만) → raw=None."""
        wf = MagicMock()
        wf.run = AsyncMock(return_value={
            "analysis_text": "분석", "excel_data": {"file_path": "/tmp/s.xlsx"},
        })
        compiler = _make_compiler()
        text, raw = await compiler._run_excel_analysis(
            wf, "q", {"file_path": "/tmp/s.xlsx"}, MagicMock(),
        )
        assert raw is None

    @pytest.mark.asyncio
    async def test_워크플로우_예외시_text에러_raw_None(self):
        wf = MagicMock()
        wf.run = AsyncMock(side_effect=RuntimeError("parse fail"))
        compiler = _make_compiler()
        text, raw = await compiler._run_excel_analysis(
            wf, "q", {"file_path": "/tmp/s.xlsx"}, MagicMock(),
        )
        assert "엑셀 분석 실패" in text
        assert raw is None


class TestAnalysisNodeEmitsSource:
    @pytest.mark.asyncio
    async def test_엑셀_분기는_analysis_source에_raw_source_방출(self):
        wf = MagicMock()
        wf.run = AsyncMock(return_value={
            "analysis_text": "남은 연차 14일", "excel_data": _PARSED,
        })
        compiler = _make_compiler(excel_getter=lambda: wf)
        node = compiler._create_analysis_node(AsyncMock(), "analyst", "프롬프트")
        result = await node(_state(
            [HumanMessage(content="휴가 분석")], attachments=_EXCEL_ATTACH,
        ))
        assert "analysis_source" in result
        src = result["analysis_source"][0]
        assert src["kind"] == "raw_source"
        assert src["origin"] == "analyst"
        assert src["excel"] is _PARSED

    @pytest.mark.asyncio
    async def test_context_분기는_analysis_source_키_미포함(self):
        compiler = _make_compiler(excel_getter=None)
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="문맥 분석")
        node = compiler._create_analysis_node(mock_llm, "analyst", "프롬프트")
        result = await node(_state([HumanMessage(content="분석")]))
        assert "analysis_source" not in result

    @pytest.mark.asyncio
    async def test_원천_None이면_analysis_source_키_미포함(self):
        wf = MagicMock()
        wf.run = AsyncMock(return_value={
            "analysis_text": "분석", "excel_data": {"file_path": "/tmp/s.xlsx"},
        })
        compiler = _make_compiler(excel_getter=lambda: wf)
        node = compiler._create_analysis_node(AsyncMock(), "analyst", "프롬프트")
        result = await node(_state(
            [HumanMessage(content="q")], attachments=_EXCEL_ATTACH,
        ))
        assert "analysis_source" not in result
