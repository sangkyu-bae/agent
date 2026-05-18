import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field

from src.application.advanced_ingest.use_case import AdvancedIngestUseCase
from src.domain.advanced_ingest.schemas import AdvancedIngestRequest


router = APIRouter(prefix="/api/v1/ingest/pdf", tags=["advanced-ingest"])


class AdvancedIngestAPIResponse(BaseModel):
    document_id: str
    filename: str
    user_id: str
    total_pages: int
    document_type: Optional[str] = None
    analysis_confidence: float = 0.0
    routed_parser: str = ""
    layout_quality_score: Optional[float] = None
    layout_applied: bool = False
    table_count: int = 0
    table_flattened: bool = False
    chunk_count: int = 0
    chunking_strategy: str = ""
    qdrant_indexed: int = 0
    es_indexed: int = 0
    processing_time_ms: int = 0
    step_timings: Dict[str, int] = Field(default_factory=dict)
    collection_name: str = ""
    request_id: str = ""
    errors: List[str] = Field(default_factory=list)


def get_advanced_ingest_use_case() -> AdvancedIngestUseCase:
    raise NotImplementedError("Configure AdvancedIngestUseCase dependency")


@router.post("/advanced", response_model=AdvancedIngestAPIResponse)
async def advanced_ingest_pdf(
    file: UploadFile = File(..., description="PDF file to ingest"),
    user_id: str = Query(..., description="Owner user ID"),
    collection_name: str = Query("documents", description="Collection name"),
    chunking_strategy: str = Query("parent_child", description="full_token | parent_child | semantic"),
    chunk_size: int = Query(500, ge=100, le=8000, description="Tokens per chunk"),
    chunk_overlap: int = Query(50, ge=0, le=500, description="Overlap between chunks"),
    enable_layout_analysis: bool = Query(True, description="Enable layout analysis"),
    enable_table_flattening: bool = Query(True, description="Enable table flattening"),
    sample_pages: int = Query(3, ge=1, le=10, description="Pages to sample for analysis"),
    use_case: AdvancedIngestUseCase = Depends(get_advanced_ingest_use_case),
) -> AdvancedIngestAPIResponse:
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"
    request_id = str(uuid.uuid4())

    request = AdvancedIngestRequest(
        filename=filename,
        user_id=user_id,
        request_id=request_id,
        file_bytes=file_bytes,
        collection_name=collection_name,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        enable_layout_analysis=enable_layout_analysis,
        enable_table_flattening=enable_table_flattening,
        sample_pages=sample_pages,
    )

    result = await use_case.ingest(request)

    return AdvancedIngestAPIResponse(
        document_id=result.document_id,
        filename=result.filename,
        user_id=result.user_id,
        total_pages=result.total_pages,
        document_type=result.document_type,
        analysis_confidence=result.analysis_confidence,
        routed_parser=result.routed_parser,
        layout_quality_score=result.layout_quality_score,
        layout_applied=result.layout_applied,
        table_count=result.table_count,
        table_flattened=result.table_flattened,
        chunk_count=result.chunk_count,
        chunking_strategy=result.chunking_strategy,
        qdrant_indexed=result.qdrant_indexed,
        es_indexed=result.es_indexed,
        processing_time_ms=result.processing_time_ms,
        step_timings=result.step_timings,
        collection_name=result.collection_name,
        request_id=result.request_id,
        errors=result.errors,
    )
