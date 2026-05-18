import asyncio

import fitz

from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState

QUALITY_THRESHOLD = 0.7
SKIP_TYPES = {"ocr_heavy"}


async def layout_analyze_node(
    state: AdvancedPipelineState,
    layout_analyzer: LayoutAnalyzer,
) -> dict:
    if not state.get("enable_layout_analysis", True):
        return {"layout_applied": False, "layout_quality_score": None}

    doc_type = state.get("document_type", "")
    if doc_type in SKIP_TYPES:
        return {"layout_applied": False, "layout_quality_score": None}

    try:
        pdf_doc = fitz.open(stream=state["file_bytes"], filetype="pdf")
        documents, quality = await asyncio.to_thread(
            layout_analyzer.analyze,
            pdf_doc=pdf_doc,
            filename=state["filename"],
            user_id=state["user_id"],
        )
        pdf_doc.close()

        if quality.score < QUALITY_THRESHOLD:
            return {
                "layout_applied": False,
                "layout_quality_score": quality.score,
                "errors": state["errors"] + [
                    f"Layout quality {quality.score:.2f} < {QUALITY_THRESHOLD}, skipping"
                ],
            }

        return {
            "parsed_documents": documents,
            "layout_applied": True,
            "layout_quality_score": quality.score,
        }
    except Exception as e:
        return {
            "layout_applied": False,
            "layout_quality_score": None,
            "errors": state["errors"] + [f"Layout analysis failed: {str(e)}"],
        }
