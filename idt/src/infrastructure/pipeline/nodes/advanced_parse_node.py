import asyncio
from typing import Dict

from src.domain.parser.interfaces import PDFParserInterface
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def advanced_parse_node(
    state: AdvancedPipelineState,
    parsers: Dict[str, PDFParserInterface],
) -> dict:
    parser_type = state.get("routed_parser_type", "pymupdf")
    parser = parsers.get(parser_type)
    if parser is None:
        parser = parsers.get("pymupdf")
        if parser is None:
            return {
                "status": "failed",
                "errors": state["errors"] + [f"No parser available for '{parser_type}'"],
            }

    try:
        documents = await asyncio.to_thread(
            parser.parse_bytes,
            file_bytes=state["file_bytes"],
            filename=state["filename"],
            user_id=state["user_id"],
        )
        if not documents:
            return {
                "status": "failed",
                "errors": state["errors"] + ["No documents parsed from PDF"],
            }

        document_id = ""
        if documents[0].metadata.get("document_id"):
            document_id = documents[0].metadata["document_id"]

        return {
            "parsed_documents": documents,
            "total_pages": len(documents),
            "document_id": document_id,
            "status": "parsing",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Parse failed: {str(e)}"],
        }
