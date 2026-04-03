"""Parse node for document processing pipeline."""
from typing import List

from langchain_core.documents import Document

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.pipeline.state.pipeline_state import PipelineState


async def parse_node(
    state: PipelineState,
    parser: PDFParserInterface,
) -> PipelineState:
    """Parse PDF document and update pipeline state.

    Uses file_bytes if provided, otherwise uses file_path.

    Args:
        state: Current pipeline state.
        parser: PDF parser implementation.

    Returns:
        Updated pipeline state with parsed documents.
    """
    try:
        documents: List[Document] = []

        # Prefer file_bytes over file_path
        if state.get("file_bytes"):
            documents = parser.parse_bytes(
                file_bytes=state["file_bytes"],
                filename=state["filename"],
                user_id=state["user_id"],
            )
        else:
            documents = parser.parse(
                file_path=state["file_path"],
                user_id=state["user_id"],
            )

        if not documents:
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + ["No documents parsed from PDF"],
            }

        # Extract document_id from first document metadata
        document_id = ""
        if documents and documents[0].metadata.get("document_id"):
            document_id = documents[0].metadata["document_id"]

        return {
            **state,
            "parsed_documents": documents,
            "total_pages": len(documents),
            "document_id": document_id,
            "status": "parsing",
        }

    except Exception as e:
        return {
            **state,
            "status": "failed",
            "errors": state["errors"] + [f"Parse failed: {str(e)}"],
        }
