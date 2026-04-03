"""PDF Ingest API — parse + chunk + embed + store.

POST /api/v1/ingest/pdf
  - User selects parser (pymupdf | llamaparser)
  - User selects chunking strategy (full_token | parent_child | semantic)
  - System parses → chunks → embeds → stores in Qdrant
"""
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile

from src.application.ingest.ingest_use_case import IngestDocumentUseCase
from src.domain.ingest.schemas import IngestRequest, IngestResult

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def get_ingest_use_case() -> IngestDocumentUseCase:
    """DI placeholder — overridden in create_app() via dependency_overrides."""
    raise NotImplementedError("Configure IngestDocumentUseCase dependency")


@router.post("/pdf", response_model=IngestResult)
async def ingest_pdf(
    file: UploadFile = File(..., description="PDF file to ingest"),
    user_id: str = Query(..., description="Owner user ID"),
    parser_type: str = Query(
        "pymupdf",
        description="PDF parser: 'pymupdf' (fast) | 'llamaparser' (OCR/AI)",
    ),
    chunking_strategy: str = Query(
        "full_token",
        description="Chunking strategy: 'full_token' | 'parent_child' | 'semantic'",
    ),
    chunk_size: int = Query(1000, ge=100, le=8000, description="Tokens per chunk"),
    chunk_overlap: int = Query(100, ge=0, le=500, description="Overlap between chunks"),
    use_case: IngestDocumentUseCase = Depends(get_ingest_use_case),
) -> IngestResult:
    """Ingest a PDF file into the vector store.

    1. Parse PDF with selected parser (pymupdf or llamaparser)
    2. Chunk documents with selected strategy
    3. Embed chunks with OpenAI embeddings
    4. Store vectors in Qdrant
    """
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"
    request_id = str(uuid.uuid4())

    request = IngestRequest(
        filename=filename,
        user_id=user_id,
        request_id=request_id,
        file_bytes=file_bytes,
        parser_type=parser_type,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return await use_case.ingest(request)
