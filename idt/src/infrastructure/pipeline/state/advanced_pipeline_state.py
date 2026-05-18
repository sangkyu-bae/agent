from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class AdvancedPipelineState(TypedDict):
    # Input
    file_path: str
    file_bytes: Optional[bytes]
    filename: str
    user_id: str
    request_id: str
    collection_name: str

    # Config
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    enable_layout_analysis: bool
    enable_table_flattening: bool
    sample_pages: int

    # Analyze Node
    document_type: Optional[str]
    analysis_confidence: float
    analysis_metrics: Dict[str, Any]

    # Route Node
    routed_parser_type: str
    routing_reason: str
    is_fallback: bool

    # Parse Node
    parsed_documents: List[Any]
    total_pages: int
    document_id: str

    # Layout Analyze Node
    layout_quality_score: Optional[float]
    layout_applied: bool

    # Table Preprocess Node
    table_count: int
    table_flattened: bool
    preprocessed_documents: List[Any]

    # Chunk Node
    chunked_documents: List[Any]
    chunk_count: int

    # Morph Node
    morph_applied: bool
    morph_keywords_per_chunk: List[List[str]]

    # Dual Store Node
    qdrant_stored_ids: List[str]
    qdrant_stored_count: int
    es_stored_count: int
    es_index_name: str

    # Metadata
    processing_time_ms: int
    step_timings: Dict[str, int]
    errors: List[str]
    status: str


def create_advanced_initial_state(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    request_id: str,
    collection_name: str = "documents",
    chunking_strategy: str = "parent_child",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    enable_layout_analysis: bool = True,
    enable_table_flattening: bool = True,
    sample_pages: int = 3,
) -> AdvancedPipelineState:
    return {
        "file_path": "",
        "file_bytes": file_bytes,
        "filename": filename,
        "user_id": user_id,
        "request_id": request_id,
        "collection_name": collection_name,
        "chunking_strategy": chunking_strategy,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "enable_layout_analysis": enable_layout_analysis,
        "enable_table_flattening": enable_table_flattening,
        "sample_pages": sample_pages,
        "document_type": None,
        "analysis_confidence": 0.0,
        "analysis_metrics": {},
        "routed_parser_type": "",
        "routing_reason": "",
        "is_fallback": False,
        "parsed_documents": [],
        "total_pages": 0,
        "document_id": "",
        "layout_quality_score": None,
        "layout_applied": False,
        "table_count": 0,
        "table_flattened": False,
        "preprocessed_documents": [],
        "chunked_documents": [],
        "chunk_count": 0,
        "morph_applied": False,
        "morph_keywords_per_chunk": [],
        "qdrant_stored_ids": [],
        "qdrant_stored_count": 0,
        "es_stored_count": 0,
        "es_index_name": "",
        "processing_time_ms": 0,
        "step_timings": {},
        "errors": [],
        "status": "pending",
    }
