"""Excel analysis API endpoints."""

import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.application.use_cases.analyze_excel_use_case import AnalyzeExcelUseCase
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["Excel Analysis"])


class AnalysisAttemptResponse(BaseModel):
    """시도 기록 응답."""

    attempt_number: int
    confidence_score: float
    hallucination_score: float
    used_web_search: bool
    timestamp: datetime


class AnalysisResponse(BaseModel):
    """분석 응답."""

    request_id: str
    query: str
    final_answer: str
    is_successful: bool
    total_attempts: int
    attempts: List[AnalysisAttemptResponse]
    executed_code: Optional[str] = None
    code_output: Optional[Dict[str, Any]] = None


def get_analyze_excel_use_case() -> AnalyzeExcelUseCase:
    """DI placeholder for AnalyzeExcelUseCase."""
    raise NotImplementedError("Must be overridden via dependency_overrides")


@router.post("/excel", response_model=AnalysisResponse)
async def analyze_excel(
    file: UploadFile = File(...),
    query: str = Form(...),
    user_id: str = Form(default="anonymous"),
    use_case: AnalyzeExcelUseCase = Depends(get_analyze_excel_use_case),
) -> AnalysisResponse:
    """엑셀 파일 분석 엔드포인트.

    엑셀 파싱 → Claude AI 분석 → 할루시네이션 검증 →
    필요 시 웹 검색 및 코드 실행 → 최대 3회 재시도.
    """
    langsmith(project_name="excel-analysis-agent")
    try:
        with tempfile.NamedTemporaryFile(
            suffix=f"_{file.filename}", delete=False
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        result = await use_case.execute(
            excel_file_path=tmp_path,
            user_query=query,
            user_id=user_id,
        )

        return AnalysisResponse(
            request_id=result.request_id,
            query=result.user_query,
            final_answer=result.final_answer,
            is_successful=result.is_successful,
            total_attempts=result.total_attempts,
            attempts=[
                AnalysisAttemptResponse(
                    attempt_number=a.attempt_number,
                    confidence_score=a.confidence_score,
                    hallucination_score=a.hallucination_score,
                    used_web_search=a.used_web_search,
                    timestamp=a.timestamp,
                )
                for a in result.attempts
            ],
            executed_code=result.executed_code,
            code_output=result.code_output,
        )

    except Exception as e:
        logger.error("Excel analysis endpoint failed", exception=e)
        raise HTTPException(status_code=500, detail=str(e))
