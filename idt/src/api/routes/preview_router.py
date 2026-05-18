"""Pipeline preview API — parse, table-flatten, full ingest with detailed results.

POST /api/v1/preview/parse          → PDF → Markdown preview (no storage)
POST /api/v1/preview/table-flatten  → Markdown table → semantic sentences preview
POST /api/v1/preview/ingest         → Full pipeline with intermediate results
"""
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel

from src.application.unified_upload.use_case import UnifiedUploadUseCase
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import ParserConfig
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory
from src.infrastructure.chunking.table_flattening.preprocessor import (
    TableFlatteningPreprocessor,
)
from src.infrastructure.chunking.table_flattening.rule_based_generator import (
    RuleBasedTableContentGenerator,
)

router = APIRouter(prefix="/api/v1/preview", tags=["preview"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PagePreview(BaseModel):
    page: int
    has_table: bool
    section_title: str
    markdown_text: str
    char_count: int


class ParsePreviewResponse(BaseModel):
    filename: str
    total_pages: int
    parser: str
    pages: list[PagePreview]


class TableDetail(BaseModel):
    original_markdown: str
    search_optimized_text: str
    metadata: dict


class TableFlattenPreviewResponse(BaseModel):
    table_count: int
    parent_text: str
    child_text: str
    tables: list[TableDetail]


class ChunkSample(BaseModel):
    text: str
    metadata: dict


class ParseSummary(BaseModel):
    total_pages: int
    pages_with_tables: int
    parser: str


class ChunkSummary(BaseModel):
    total_chunks: int
    parent_chunks: int
    child_chunks: int
    table_flattened_chunks: int
    sample_parent: ChunkSample | None = None
    sample_child: ChunkSample | None = None
    sample_flattened_child: ChunkSample | None = None


class StoreSummary(BaseModel):
    collection_name: str
    stored_count: int
    embedding_model: str
    status: str
    error: str | None = None


class EsSummary(BaseModel):
    indexed_count: int
    status: str
    error: str | None = None


class ChunkingConfigSummary(BaseModel):
    strategy: str
    parent_chunk_size: int
    child_chunk_size: int
    child_chunk_overlap: int
    table_flattening: bool


class IngestPreviewResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    parse_result: ParseSummary
    chunk_result: ChunkSummary
    store_result: StoreSummary
    es_result: EsSummary
    chunking_config: ChunkingConfigSummary


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class TableFlattenRequest(BaseModel):
    markdown_text: str
    section_title: str = ""


# ---------------------------------------------------------------------------
# DI placeholders
# ---------------------------------------------------------------------------

def get_preview_parser() -> PDFParserInterface:
    raise NotImplementedError("Configure via dependency_overrides")


def get_preview_upload_use_case() -> UnifiedUploadUseCase:
    raise NotImplementedError("Configure via dependency_overrides")


# ---------------------------------------------------------------------------
# 1. POST /preview/parse
# ---------------------------------------------------------------------------

@router.post("/parse", response_model=ParsePreviewResponse)
async def preview_parse(
    file: UploadFile = File(..., description="PDF file to parse"),
    user_id: str = Query("preview-user", description="User ID"),
    extract_tables: bool = Query(True, description="Include tables in output"),
    parser: PDFParserInterface = Depends(get_preview_parser),
) -> ParsePreviewResponse:
    """Parse a PDF with pymupdf4llm and return per-page Markdown results."""
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"

    config = ParserConfig(extract_tables=extract_tables)
    documents = parser.parse_bytes(file_bytes, filename, user_id, config)

    pages = [
        PagePreview(
            page=doc.metadata.get("page", 0),
            has_table=doc.metadata.get("has_table", False),
            section_title=doc.metadata.get("section_title", ""),
            markdown_text=doc.page_content,
            char_count=len(doc.page_content),
        )
        for doc in documents
    ]

    return ParsePreviewResponse(
        filename=filename,
        total_pages=len(documents),
        parser="pymupdf4llm",
        pages=pages,
    )


# ---------------------------------------------------------------------------
# 2. POST /preview/table-flatten
# ---------------------------------------------------------------------------

_generator = RuleBasedTableContentGenerator()
_preprocessor = TableFlatteningPreprocessor(_generator)


@router.post("/table-flatten", response_model=TableFlattenPreviewResponse)
async def preview_table_flatten(
    body: TableFlattenRequest,
) -> TableFlattenPreviewResponse:
    """Detect markdown tables and convert to semantic sentences."""
    result = _preprocessor.process(body.markdown_text, body.section_title)

    tables: list[TableDetail] = []
    if result.table_count > 0:
        table_spans = _preprocessor._detect_tables(body.markdown_text)
        for span in table_spans:
            table_md = body.markdown_text[span.start : span.end]
            conversion = _generator.generate(table_md, body.section_title)
            tables.append(
                TableDetail(
                    original_markdown=conversion.original_markdown,
                    search_optimized_text=conversion.search_optimized_text,
                    metadata=conversion.metadata,
                )
            )

    return TableFlattenPreviewResponse(
        table_count=result.table_count,
        parent_text=result.parent_text,
        child_text=result.child_text,
        tables=tables,
    )


# ---------------------------------------------------------------------------
# 3. POST /preview/ingest
# ---------------------------------------------------------------------------

SAMPLE_TEXT_LIMIT = 300


def _truncate(text: str, limit: int = SAMPLE_TEXT_LIMIT) -> str:
    return text[:limit] + "..." if len(text) > limit else text


@router.post("/ingest", response_model=IngestPreviewResponse)
async def preview_ingest(
    file: UploadFile = File(..., description="PDF file"),
    user_id: str = Query(..., description="User ID"),
    collection_name: str = Query(..., description="Target Qdrant collection"),
    child_chunk_size: int = Query(500, ge=100, le=4000),
    child_chunk_overlap: int = Query(50, ge=0, le=500),
    use_case: UnifiedUploadUseCase = Depends(get_preview_upload_use_case),
) -> IngestPreviewResponse:
    """Run full ingest pipeline and return detailed intermediate results."""
    from src.application.unified_upload.schemas import UnifiedUploadRequest

    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"
    request_id = str(uuid.uuid4())

    request = UnifiedUploadRequest(
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        collection_name=collection_name,
        child_chunk_size=child_chunk_size,
        child_chunk_overlap=child_chunk_overlap,
    )

    result = await use_case.execute(request, request_id)

    # Re-parse to get page-level info for the preview
    from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

    parser = PyMuPDF4LLMParser()
    parsed_docs = parser.parse_bytes(file_bytes, filename, user_id)
    pages_with_tables = sum(
        1 for d in parsed_docs if d.metadata.get("has_table", False)
    )

    # Re-chunk to get chunk-level detail
    strategy = ChunkingStrategyFactory.create_strategy(
        "parent_child",
        parent_chunk_size=2000,
        child_chunk_size=child_chunk_size,
        child_chunk_overlap=child_chunk_overlap,
    )
    chunks = strategy.chunk(parsed_docs)

    parents = [c for c in chunks if c.metadata.get("chunk_type") == "parent"]
    children = [c for c in chunks if c.metadata.get("chunk_type") == "child"]
    flattened = [c for c in children if c.metadata.get("table_flattened")]

    sample_parent = None
    if parents:
        p = parents[0]
        sample_parent = ChunkSample(
            text=_truncate(p.page_content),
            metadata={k: str(v) for k, v in p.metadata.items()},
        )

    sample_child = None
    non_flattened = [c for c in children if not c.metadata.get("table_flattened")]
    if non_flattened:
        c = non_flattened[0]
        sample_child = ChunkSample(
            text=_truncate(c.page_content),
            metadata={k: str(v) for k, v in c.metadata.items()},
        )

    sample_flattened = None
    if flattened:
        f = flattened[0]
        sample_flattened = ChunkSample(
            text=_truncate(f.page_content),
            metadata={k: str(v) for k, v in f.metadata.items()},
        )

    qdrant_status = "success" if not result.qdrant.error else "failed"
    es_status = "success" if not result.es.error else "failed"

    return IngestPreviewResponse(
        document_id=result.document_id,
        filename=result.filename,
        status=result.status,
        parse_result=ParseSummary(
            total_pages=result.total_pages,
            pages_with_tables=pages_with_tables,
            parser="pymupdf4llm",
        ),
        chunk_result=ChunkSummary(
            total_chunks=len(chunks),
            parent_chunks=len(parents),
            child_chunks=len(children),
            table_flattened_chunks=len(flattened),
            sample_parent=sample_parent,
            sample_child=sample_child,
            sample_flattened_child=sample_flattened,
        ),
        store_result=StoreSummary(
            collection_name=result.collection_name,
            stored_count=len(result.qdrant.stored_ids),
            embedding_model=result.qdrant.embedding_model,
            status=qdrant_status,
            error=result.qdrant.error,
        ),
        es_result=EsSummary(
            indexed_count=result.es.indexed_count,
            status=es_status,
            error=result.es.error,
        ),
        chunking_config=ChunkingConfigSummary(
            strategy="parent_child",
            parent_chunk_size=2000,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
            table_flattening=True,
        ),
    )
