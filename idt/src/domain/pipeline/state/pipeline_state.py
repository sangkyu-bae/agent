"""Pipeline state definition for LangGraph workflow."""
from typing import Any, List, Optional
from typing_extensions import TypedDict

from src.domain.pipeline.enums.document_category import DocumentCategory


class PipelineState(TypedDict):
    """State for document processing pipeline.

    This TypedDict defines the state passed between LangGraph nodes.

    Input Fields:
        file_path: Path to the PDF file.
        file_bytes: Raw bytes of the file (alternative to file_path).
        filename: Original filename.
        user_id: ID of the user uploading the document.

    Parse Node Fields:
        parsed_documents: List of documents from parsing.
        total_pages: Total number of pages in the document.
        document_id: Generated unique document ID.

    Classify Node Fields:
        category: Classified document category.
        category_confidence: Confidence score (0.0-1.0).
        classification_reasoning: Reasoning for classification.
        sample_pages: Sample pages used for classification.

    Chunk Node Fields:
        chunked_documents: List of chunked documents.
        chunk_count: Total number of chunks created.
        chunking_config_used: Configuration used for chunking.

    Store Node Fields:
        stored_ids: List of stored document IDs.
        collection_name: Qdrant collection name.

    Metadata Fields:
        processing_time_ms: Total processing time in milliseconds.
        errors: List of error messages.
        status: Current pipeline status.
    """

    # Input
    file_path: str
    file_bytes: Optional[bytes]
    filename: str
    user_id: str

    # Parse Node
    parsed_documents: List[Any]  # List[Document] from langchain
    total_pages: int
    document_id: str

    # Classify Node
    category: Optional[DocumentCategory]
    category_confidence: float
    classification_reasoning: str
    sample_pages: List[str]

    # Chunk Node
    chunked_documents: List[Any]  # List[Document] from langchain
    chunk_count: int
    chunking_config_used: dict

    # Store Node
    stored_ids: List[str]
    collection_name: str

    # Metadata
    processing_time_ms: int
    errors: List[str]
    status: str  # pending, parsing, classifying, chunking, storing, completed, failed
