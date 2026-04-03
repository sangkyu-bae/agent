"""Tests for ExcelAnalysisWorkflow."""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime

from src.application.workflows.excel_analysis_workflow import (
    ExcelAnalysisWorkflow,
    ExcelAnalysisState,
)
from src.domain.policies.analysis_policy import (
    AnalysisRetryPolicy,
    AnalysisQualityThreshold,
)
from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.domain.tools.code_execution_result import CodeExecutionResult
from src.infrastructure.llm.schemas import ClaudeResponse


class TestExcelAnalysisWorkflowNodes:
    """각 노드의 단위 테스트."""

    def _create_workflow(self, **overrides) -> ExcelAnalysisWorkflow:
        defaults = {
            "excel_parser": Mock(),
            "claude_client": Mock(),
            "tavily_search": Mock(),
            "hallucination_evaluator": Mock(),
            "code_executor": Mock(),
            "logger": Mock(),
            "retry_policy": AnalysisRetryPolicy(max_retries=3),
            "quality_threshold": AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        }
        defaults.update(overrides)
        return ExcelAnalysisWorkflow(**defaults)

    @pytest.mark.asyncio
    async def test_parse_excel_node(self):
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {"sheets": {"Sheet1": {"data": []}}}
        mock_parser.parse.return_value = mock_excel_data

        workflow = self._create_workflow(excel_parser=mock_parser)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "분석해줘",
            "excel_data": {"file_path": "/tmp/test.xlsx", "user_id": "user-1"},
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._parse_excel_node(state)

        mock_parser.parse.assert_called_once_with("/tmp/test.xlsx", "user-1")
        assert "excel_data" in result
        assert result["current_attempt"] == 0

    @pytest.mark.asyncio
    async def test_analyze_node(self):
        mock_claude = Mock()
        mock_response = ClaudeResponse(
            content="분석 결과입니다.",
            model="claude-sonnet-4-5-20250929",
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
            request_id="test-123",
            latency_ms=500,
        )
        mock_claude.complete = AsyncMock(return_value=mock_response)

        workflow = self._create_workflow(claude_client=mock_claude)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "데이터 요약",
            "excel_data": {"sheets": {"Sheet1": {}}},
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._analyze_node(state)

        assert result["analysis_text"] == "분석 결과입니다."
        assert result["current_attempt"] == 1
        mock_claude.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_node_detects_code(self):
        mock_claude = Mock()
        response_text = "결과:\n```python\nprint('hello')\n```"
        mock_response = ClaudeResponse(
            content=response_text,
            model="claude-sonnet-4-5-20250929",
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
            request_id="test-123",
            latency_ms=500,
        )
        mock_claude.complete = AsyncMock(return_value=mock_response)

        workflow = self._create_workflow(claude_client=mock_claude)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "코드 작성",
            "excel_data": {"sheets": {}},
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._analyze_node(state)

        assert result["needs_code_execution"] is True
        assert result["code_to_execute"] == "print('hello')"

    @pytest.mark.asyncio
    async def test_web_search_node(self):
        mock_search = Mock()
        mock_search.get_search_context.return_value = "검색 결과 컨텍스트"

        workflow = self._create_workflow(tavily_search=mock_search)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "2024년 매출",
            "excel_data": {},
            "current_attempt": 1,
            "max_attempts": 3,
            "analysis_text": "분석 텍스트",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": True,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._web_search_node(state)

        assert result["web_search_results"] == "검색 결과 컨텍스트"
        assert result["needs_web_search"] is False
        mock_search.get_search_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_node_no_hallucination(self):
        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=False)
        )

        workflow = self._create_workflow(hallucination_evaluator=mock_evaluator)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "분석",
            "excel_data": {"sheets": {"Sheet1": {"data": []}}},
            "current_attempt": 1,
            "max_attempts": 3,
            "analysis_text": "분석 결과",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._evaluate_node(state)

        assert result["confidence_score"] == 1.0
        assert result["hallucination_score"] == 0.0
        assert len(result["attempts_history"]) == 1
        assert result["attempts_history"][0]["attempt_number"] == 1

    @pytest.mark.asyncio
    async def test_evaluate_node_with_hallucination(self):
        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=True)
        )

        workflow = self._create_workflow(hallucination_evaluator=mock_evaluator)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "분석",
            "excel_data": {"sheets": {}},
            "current_attempt": 1,
            "max_attempts": 3,
            "analysis_text": "할루시네이션 결과",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._evaluate_node(state)

        assert result["confidence_score"] == 0.0
        assert result["hallucination_score"] == 1.0

    @pytest.mark.asyncio
    async def test_execute_code_node(self):
        mock_executor = Mock()
        mock_executor.execute.return_value = CodeExecutionResult.success("hello")

        workflow = self._create_workflow(code_executor=mock_executor)

        state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "분석",
            "excel_data": {},
            "current_attempt": 1,
            "max_attempts": 3,
            "analysis_text": "결과",
            "confidence_score": 0.9,
            "hallucination_score": 0.1,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": True,
            "code_to_execute": "print('hello')",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow._execute_code_node(state)

        assert result["is_complete"] is True
        assert result["final_status"] == "completed"
        assert result["code_output"]["status"] == "success"
        assert result["code_output"]["output"] == "hello"
        mock_executor.execute.assert_called_once_with("print('hello')", "test-123")


class TestExcelAnalysisWorkflowRouting:
    """조건부 엣지 라우팅 테스트."""

    def _create_workflow(self, **overrides) -> ExcelAnalysisWorkflow:
        defaults = {
            "excel_parser": Mock(),
            "claude_client": Mock(),
            "tavily_search": Mock(),
            "hallucination_evaluator": Mock(),
            "code_executor": Mock(),
            "logger": Mock(),
            "retry_policy": AnalysisRetryPolicy(max_retries=3),
            "quality_threshold": AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        }
        defaults.update(overrides)
        return ExcelAnalysisWorkflow(**defaults)

    def test_should_search_with_tag(self):
        workflow = self._create_workflow()
        state = {"analysis_text": "추가 정보 필요 [SEARCH] 확인"}
        assert workflow._should_search(state) == "search"

    def test_should_search_with_korean(self):
        workflow = self._create_workflow()
        state = {"analysis_text": "웹에서 확인이 필요합니다"}
        assert workflow._should_search(state) == "search"

    def test_should_not_search(self):
        workflow = self._create_workflow()
        state = {"analysis_text": "분석 완료"}
        assert workflow._should_search(state) == "evaluate"

    def test_should_retry_or_execute_quality_ok_no_code(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.9,
            "hallucination_score": 0.1,
            "needs_code_execution": False,
            "current_attempt": 1,
        }
        assert workflow._should_retry_or_execute(state) == "complete"

    def test_should_retry_or_execute_quality_ok_with_code(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.9,
            "hallucination_score": 0.1,
            "needs_code_execution": True,
            "current_attempt": 1,
        }
        assert workflow._should_retry_or_execute(state) == "execute"

    def test_should_retry_or_execute_quality_bad_retry(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.0,
            "hallucination_score": 1.0,
            "needs_code_execution": False,
            "current_attempt": 1,
        }
        assert workflow._should_retry_or_execute(state) == "retry"

    def test_should_retry_or_execute_quality_bad_max_retries(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.0,
            "hallucination_score": 1.0,
            "needs_code_execution": False,
            "current_attempt": 3,
        }
        assert workflow._should_retry_or_execute(state) == "complete"


class TestExcelAnalysisWorkflowIntegration:
    """그래프 전체 흐름 테스트."""

    @pytest.mark.asyncio
    async def test_full_flow_success_first_attempt(self):
        """첫 시도에 성공하는 흐름."""
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {"sheets": {"Sheet1": {"data": [{"a": 1}]}}}
        mock_parser.parse.return_value = mock_excel_data

        mock_claude = Mock()
        mock_response = ClaudeResponse(
            content="분석 결과입니다.",
            model="claude-sonnet-4-5-20250929",
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
            request_id="test-123",
            latency_ms=500,
        )
        mock_claude.complete = AsyncMock(return_value=mock_response)

        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=False)
        )

        workflow = ExcelAnalysisWorkflow(
            excel_parser=mock_parser,
            claude_client=mock_claude,
            tavily_search=Mock(),
            hallucination_evaluator=mock_evaluator,
            code_executor=Mock(),
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(max_retries=3),
            quality_threshold=AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        )

        initial_state: ExcelAnalysisState = {
            "request_id": "test-123",
            "user_query": "데이터 요약",
            "excel_data": {"file_path": "/tmp/test.xlsx", "user_id": "user-1"},
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow.run(initial_state)

        assert result["analysis_text"] == "분석 결과입니다."
        assert result["confidence_score"] == 1.0
        assert result["hallucination_score"] == 0.0
        assert len(result["attempts_history"]) == 1
        mock_parser.parse.assert_called_once()
        mock_claude.complete.assert_called_once()
        mock_evaluator.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_flow_retry_then_success(self):
        """할루시네이션으로 재시도 후 성공."""
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {"sheets": {}}
        mock_parser.parse.return_value = mock_excel_data

        mock_claude = Mock()
        # 첫 번째: 할루시네이션, 두 번째: 성공
        mock_claude.complete = AsyncMock(
            side_effect=[
                ClaudeResponse(
                    content="할루시네이션 결과",
                    model="claude-sonnet-4-5-20250929",
                    stop_reason="end_turn",
                    input_tokens=100,
                    output_tokens=50,
                    request_id="test-456",
                    latency_ms=500,
                ),
                ClaudeResponse(
                    content="개선된 분석",
                    model="claude-sonnet-4-5-20250929",
                    stop_reason="end_turn",
                    input_tokens=100,
                    output_tokens=50,
                    request_id="test-456",
                    latency_ms=500,
                ),
            ]
        )

        mock_search = Mock()
        mock_search.get_search_context.return_value = "웹 검색 결과"

        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            side_effect=[
                HallucinationEvaluationResult(is_hallucinated=True),
                HallucinationEvaluationResult(is_hallucinated=False),
            ]
        )

        workflow = ExcelAnalysisWorkflow(
            excel_parser=mock_parser,
            claude_client=mock_claude,
            tavily_search=mock_search,
            hallucination_evaluator=mock_evaluator,
            code_executor=Mock(),
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(
                max_retries=3,
                require_web_search_on_retry=True,
            ),
            quality_threshold=AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        )

        initial_state: ExcelAnalysisState = {
            "request_id": "test-456",
            "user_query": "분석",
            "excel_data": {"file_path": "/tmp/test.xlsx", "user_id": "user-1"},
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow.run(initial_state)

        assert result["analysis_text"] == "개선된 분석"
        assert len(result["attempts_history"]) == 2
        assert result["confidence_score"] == 1.0
        assert mock_claude.complete.call_count == 2
        assert mock_search.get_search_context.call_count == 1

    @pytest.mark.asyncio
    async def test_full_flow_with_code_execution(self):
        """코드 실행이 포함된 흐름."""
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {"sheets": {}}
        mock_parser.parse.return_value = mock_excel_data

        mock_claude = Mock()
        mock_claude.complete = AsyncMock(
            return_value=ClaudeResponse(
                content="결과:\n```python\nprint('hello')\n```",
                model="claude-sonnet-4-5-20250929",
                stop_reason="end_turn",
                input_tokens=100,
                output_tokens=50,
                request_id="test-789",
                latency_ms=500,
            )
        )

        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=False)
        )

        mock_executor = Mock()
        mock_executor.execute.return_value = CodeExecutionResult.success("hello")

        workflow = ExcelAnalysisWorkflow(
            excel_parser=mock_parser,
            claude_client=mock_claude,
            tavily_search=Mock(),
            hallucination_evaluator=mock_evaluator,
            code_executor=mock_executor,
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(max_retries=3),
            quality_threshold=AnalysisQualityThreshold(),
        )

        initial_state: ExcelAnalysisState = {
            "request_id": "test-789",
            "user_query": "코드 실행",
            "excel_data": {"file_path": "/tmp/test.xlsx", "user_id": "user-1"},
            "current_attempt": 0,
            "max_attempts": 3,
            "analysis_text": "",
            "confidence_score": 0.0,
            "hallucination_score": 0.0,
            "needs_web_search": False,
            "web_search_results": "",
            "needs_code_execution": False,
            "code_to_execute": "",
            "code_output": {},
            "attempts_history": [],
            "is_complete": False,
            "final_status": "pending",
            "error_message": "",
        }

        result = await workflow.run(initial_state)

        assert result["is_complete"] is True
        assert result["code_output"]["output"] == "hello"
        mock_executor.execute.assert_called_once()
