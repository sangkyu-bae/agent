"""Doc-Chunk API: 파일 업로드 → 텍스트 추출 → 청킹 → 결과 반환.

벡터 저장 없이 청킹 결과만 반환한다 (테스트/미리보기 용도).
지원 형식: .pdf, .xlsx, .xls, .txt, .md
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from src.application.doc_chunk.use_case import DocChunkUseCase
from src.domain.doc_chunk.schemas import (
    SUPPORTED_EXTENSIONS,
    VALID_STRATEGY_TYPES,
    DocChunkRequest,
    DocChunkResult,
)

router = APIRouter(prefix="/api/v1/doc-chunk", tags=["doc-chunk"])


def get_doc_chunk_use_case() -> DocChunkUseCase:
    """DI placeholder — overridden in create_app() via dependency_overrides."""
    raise NotImplementedError("Configure DocChunkUseCase dependency")


@router.post("/upload", response_model=DocChunkResult)
async def upload_and_chunk(
    file: UploadFile = File(..., description="업로드할 파일 (.pdf/.xlsx/.xls/.txt/.md)"),
    user_id: str = Query(..., description="사용자 ID"),
    strategy_type: str = Query(
        "parent_child",
        description=f"청킹 전략: {sorted(VALID_STRATEGY_TYPES)}",
    ),
    chunk_size: int = Query(500, ge=100, le=8000, description="청크 크기 (토큰, 100~8000)"),
    chunk_overlap: int = Query(50, ge=0, le=500, description="청크 간 겹침 (토큰, 0~500)"),
    use_case: DocChunkUseCase = Depends(get_doc_chunk_use_case),
) -> DocChunkResult:
    """파일을 업로드하고 청킹 결과를 반환한다.

    1. 파일 형식에 따라 텍스트 추출 (PDF/Excel/TXT)
    2. 선택한 청킹 전략으로 분할
    3. 벡터 저장 없이 청크 목록 반환

    지원 형식: .pdf, .xlsx, .xls, .txt, .md
    """
    if strategy_type not in VALID_STRATEGY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"strategy_type must be one of: {sorted(VALID_STRATEGY_TYPES)}",
        )

    file_bytes = await file.read()
    filename = file.filename or "unknown"
    request_id = str(uuid.uuid4())

    request = DocChunkRequest(
        filename=filename,
        user_id=user_id,
        request_id=request_id,
        file_bytes=file_bytes,
        strategy_type=strategy_type,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    try:
        return await use_case.execute(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
