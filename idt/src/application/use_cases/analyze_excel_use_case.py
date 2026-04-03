"""Use case for excel file analysis.

엑셀 파일을 분석하여 결과를 반환하는 유스케이스.
"""

import uuid
from datetime import datetime

from src.application.workflows.excel_analysis_workflow import ExcelAnalysisWorkflow
from src.domain.entities.analysis_result import AnalysisAttempt, AnalysisResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.policies.analysis_policy import (
    AnalysisQualityThreshold,
    AnalysisRetryPolicy,
)


class AnalyzeExcelUseCase:
    """엑셀 분석 유스케이스."""

    def __init__(
        self,
        workflow: ExcelAnalysisWorkflow,
        logger: LoggerInterface,
        retry_policy: AnalysisRetryPolicy | None = None,
        quality_threshold: AnalysisQualityThreshold | None = None,
    ) -> None:
        self._workflow = workflow
        self._logger = logger
        self._retry_policy = retry_policy or AnalysisRetryPolicy()
        self._quality_threshold = quality_threshold or AnalysisQualityThreshold()

        self._retry_policy.validate()
        self._quality_threshold.validate()

    async def execute(
        self,
        excel_file_path: str,
        user_query: str,
        user_id: str,
        request_id: str | None = None,
    ) -> AnalysisResult:
        """엑셀 분석 실행.

        Args:
            excel_file_path: 엑셀 파일 경로
            user_query: 사용자 질문
            user_id: 사용자 ID
            request_id: 요청 ID (선택)

        Returns:
            AnalysisResult: 분석 결과
        """
        request_id = request_id or str(uuid.uuid4())

        self._logger.info(
            "Starting excel analysis",
            request_id=request_id,
            query=user_query,
            file=excel_file_path,
        )

        try:
            initial_state = {
                "request_id": request_id,
                "user_query": user_query,
                "excel_data": {
                    "file_path": excel_file_path,
                    "user_id": user_id,
                },
                "current_attempt": 0,
                "max_attempts": self._retry_policy.max_retries,
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

            final_state = await self._workflow.run(initial_state)
            result = self._build_result(final_state)

            self._logger.info(
                "Excel analysis completed",
                request_id=request_id,
                success=result.is_successful,
                attempts=result.total_attempts,
            )

            return result

        except Exception as e:
            self._logger.error(
                "Excel analysis failed",
                exception=e,
                request_id=request_id,
            )
            raise

    def _build_result(self, state: dict) -> AnalysisResult:
        """상태를 AnalysisResult로 변환."""
        attempts = [
            AnalysisAttempt(
                attempt_number=a["attempt_number"],
                analysis_text=a["analysis_text"],
                confidence_score=a["confidence_score"],
                hallucination_score=a["hallucination_score"],
                used_web_search=a["used_web_search"],
                timestamp=datetime.fromisoformat(a["timestamp"]),
            )
            for a in state["attempts_history"]
        ]

        is_successful = (
            len(attempts) > 0
            and self._quality_threshold.is_acceptable(
                attempts[-1].confidence_score,
                attempts[-1].hallucination_score,
            )
        )

        code_executed = state.get("needs_code_execution", False)

        return AnalysisResult(
            request_id=state["request_id"],
            user_query=state["user_query"],
            excel_summary=state["excel_data"],
            final_answer=state["analysis_text"],
            is_successful=is_successful,
            attempts=attempts,
            executed_code=(
                state.get("code_to_execute") if code_executed else None
            ),
            code_output=state.get("code_output") if code_executed else None,
        )
