from typing import Optional

from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PDFDocumentType,
    SummaryMetrics,
)
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def route_node(
    state: AdvancedPipelineState,
    router: ParserRouterInterface,
    routing_config: Optional[ParserRoutingConfig] = None,
) -> dict:
    try:
        analysis_result = _reconstruct_analysis_result(state)
        decision = router.route(
            analysis_result=analysis_result,
            config=routing_config,
        )
        return {
            "routed_parser_type": decision.parser_type,
            "routing_reason": decision.reason.value,
            "is_fallback": decision.is_fallback,
            "status": "routing",
        }
    except Exception as e:
        return {
            "routed_parser_type": "pymupdf",
            "routing_reason": "route_error_fallback",
            "is_fallback": True,
            "status": "routing",
            "errors": state["errors"] + [f"Route failed, using fallback: {str(e)}"],
        }


def _reconstruct_analysis_result(
    state: AdvancedPipelineState,
) -> Optional[AnalysisResult]:
    if state["document_type"] is None:
        return None
    metrics = state.get("analysis_metrics", {})
    return AnalysisResult(
        document_type=PDFDocumentType(state["document_type"]),
        confidence=state["analysis_confidence"],
        total_pages=state.get("total_pages", 1),
        sampled_pages=metrics.get("sampled_pages", 1),
        page_features=[],
        summary_metrics=SummaryMetrics(
            avg_text_chars=metrics.get("avg_text_chars", 0.0),
            avg_image_count=metrics.get("avg_image_count", 0.0),
            avg_image_area_ratio=metrics.get("avg_image_area_ratio", 0.0),
            avg_table_count=metrics.get("avg_table_count", 0.0),
            extractable_text_ratio=metrics.get("extractable_text_ratio", 0.0),
        ),
    )
