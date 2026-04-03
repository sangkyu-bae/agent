"""Tests for AnalyzeExcelUseCase."""

import pytest
from unittest.mock import AsyncMock, Mock

from src.application.use_cases.analyze_excel_use_case import AnalyzeExcelUseCase
from src.domain.policies.analysis_policy import (
    AnalysisRetryPolicy,
    AnalysisQualityThreshold,
)


@pytest.mark.asyncio
async def test_analyze_excel_success_first_attempt():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-123",
        "user_query": "데이터 요약",
        "excel_data": {"rows": 100},
        "analysis_text": "분석 결과",
        "confidence_score": 0.9,
        "hallucination_score": 0.1,
        "attempts_history": [{
            "attempt_number": 1,
            "analysis_text": "분석 결과",
            "confidence_score": 0.9,
            "hallucination_score": 0.1,
            "used_web_search": False,
            "timestamp": "2025-02-07T10:00:00",
        }],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": False,
        "code_to_execute": "",
        "code_output": {},
    })

    mock_logger = Mock()

    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=mock_logger,
    )

    result = await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="데이터 요약",
        user_id="user-1",
    )

    assert result.is_successful is True
    assert result.total_attempts == 1
    assert result.final_answer == "분석 결과"
    mock_workflow.run.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_excel_retry_on_hallucination():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-456",
        "user_query": "데이터 분석",
        "excel_data": {"rows": 50},
        "analysis_text": "개선된 분석",
        "confidence_score": 0.8,
        "hallucination_score": 0.15,
        "attempts_history": [
            {
                "attempt_number": 1,
                "confidence_score": 0.0,
                "hallucination_score": 1.0,
                "used_web_search": False,
                "timestamp": "2025-02-07T10:00:00",
                "analysis_text": "첫 시도",
            },
            {
                "attempt_number": 2,
                "confidence_score": 0.8,
                "hallucination_score": 0.15,
                "used_web_search": True,
                "timestamp": "2025-02-07T10:01:00",
                "analysis_text": "개선된 분석",
            },
        ],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": False,
        "code_to_execute": "",
        "code_output": {},
    })

    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=Mock(),
    )

    result = await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="데이터 분석",
        user_id="user-1",
    )

    assert result.total_attempts == 2
    assert result.attempts[1].used_web_search is True


@pytest.mark.asyncio
async def test_analyze_excel_with_code_execution():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-789",
        "user_query": "그래프 그려줘",
        "excel_data": {"rows": 10},
        "analysis_text": "결과",
        "confidence_score": 1.0,
        "hallucination_score": 0.0,
        "attempts_history": [{
            "attempt_number": 1,
            "analysis_text": "결과",
            "confidence_score": 1.0,
            "hallucination_score": 0.0,
            "used_web_search": False,
            "timestamp": "2025-02-07T10:00:00",
        }],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": True,
        "code_to_execute": "print('hello')",
        "code_output": {"status": "success", "output": "hello"},
    })

    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=Mock(),
    )

    result = await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="그래프 그려줘",
        user_id="user-1",
    )

    assert result.executed_code == "print('hello')"
    assert result.code_output == {"status": "success", "output": "hello"}


@pytest.mark.asyncio
async def test_analyze_excel_failed_quality():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-fail",
        "user_query": "분석",
        "excel_data": {},
        "analysis_text": "불확실한 분석",
        "confidence_score": 0.0,
        "hallucination_score": 1.0,
        "attempts_history": [{
            "attempt_number": 1,
            "analysis_text": "불확실",
            "confidence_score": 0.0,
            "hallucination_score": 1.0,
            "used_web_search": False,
            "timestamp": "2025-02-07T10:00:00",
        }],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": False,
        "code_to_execute": "",
        "code_output": {},
    })

    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=Mock(),
    )

    result = await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="분석",
        user_id="user-1",
    )

    assert result.is_successful is False


@pytest.mark.asyncio
async def test_analyze_excel_logs_start_and_complete():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(return_value={
        "request_id": "test-log",
        "user_query": "분석",
        "excel_data": {},
        "analysis_text": "결과",
        "confidence_score": 1.0,
        "hallucination_score": 0.0,
        "attempts_history": [{
            "attempt_number": 1,
            "analysis_text": "결과",
            "confidence_score": 1.0,
            "hallucination_score": 0.0,
            "used_web_search": False,
            "timestamp": "2025-02-07T10:00:00",
        }],
        "is_complete": True,
        "final_status": "completed",
        "needs_code_execution": False,
        "code_to_execute": "",
        "code_output": {},
    })

    mock_logger = Mock()

    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=mock_logger,
    )

    await use_case.execute(
        excel_file_path="/tmp/test.xlsx",
        user_query="분석",
        user_id="user-1",
    )

    info_calls = [call.args[0] for call in mock_logger.info.call_args_list]
    assert "Starting excel analysis" in info_calls
    assert "Excel analysis completed" in info_calls


@pytest.mark.asyncio
async def test_analyze_excel_logs_error_on_exception():
    mock_workflow = Mock()
    mock_workflow.run = AsyncMock(side_effect=RuntimeError("workflow failed"))

    mock_logger = Mock()

    use_case = AnalyzeExcelUseCase(
        workflow=mock_workflow,
        logger=mock_logger,
    )

    with pytest.raises(RuntimeError, match="workflow failed"):
        await use_case.execute(
            excel_file_path="/tmp/test.xlsx",
            user_query="분석",
            user_id="user-1",
        )

    mock_logger.error.assert_called_once()


def test_use_case_validates_retry_policy():
    with pytest.raises(ValueError):
        AnalyzeExcelUseCase(
            workflow=Mock(),
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(max_retries=0),
        )


def test_use_case_validates_quality_threshold():
    with pytest.raises(ValueError):
        AnalyzeExcelUseCase(
            workflow=Mock(),
            logger=Mock(),
            quality_threshold=AnalysisQualityThreshold(min_confidence_score=2.0),
        )
