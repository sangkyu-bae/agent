import asyncio

from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def analyze_node(
    state: AdvancedPipelineState,
    analyzer: PDFAnalyzerInterface,
) -> dict:
    try:
        config = AnalysisConfig(sample_pages=state["sample_pages"])
        result = await asyncio.to_thread(
            analyzer.analyze_bytes,
            file_bytes=state["file_bytes"],
            config=config,
        )
        return {
            "document_type": result.document_type.value,
            "analysis_confidence": result.confidence,
            "analysis_metrics": {
                "total_pages": result.total_pages,
                "sampled_pages": result.sampled_pages,
                "avg_text_chars": result.summary_metrics.avg_text_chars,
                "avg_table_count": result.summary_metrics.avg_table_count,
                "avg_image_area_ratio": result.summary_metrics.avg_image_area_ratio,
                "extractable_text_ratio": result.summary_metrics.extractable_text_ratio,
            },
            "total_pages": result.total_pages,
            "status": "analyzing",
        }
    except Exception as e:
        return {
            "status": "analyzing",
            "errors": state["errors"] + [f"Analyze failed: {str(e)}"],
        }
