import time
from typing import Dict, Optional

from langgraph.graph import StateGraph, END

from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState
from src.infrastructure.pipeline.nodes.analyze_node import analyze_node
from src.infrastructure.pipeline.nodes.route_node import route_node
from src.infrastructure.pipeline.nodes.advanced_parse_node import advanced_parse_node
from src.infrastructure.pipeline.nodes.layout_analyze_node import layout_analyze_node
from src.infrastructure.pipeline.nodes.table_preprocess_node import table_preprocess_node
from src.infrastructure.pipeline.nodes.advanced_chunk_node import advanced_chunk_node
from src.infrastructure.pipeline.nodes.morph_node import morph_node
from src.infrastructure.pipeline.nodes.dual_store_node import dual_store_node


def create_advanced_processing_graph(
    analyzer: PDFAnalyzerInterface,
    router: ParserRouterInterface,
    parsers: Dict[str, PDFParserInterface],
    layout_analyzer: LayoutAnalyzer,
    table_preprocessor: TableFlatteningPreprocessor,
    morph_analyzer: MorphAnalyzerInterface,
    embedding: EmbeddingInterface,
    vectorstore: VectorStoreInterface,
    es_repo: ElasticsearchRepositoryInterface,
    routing_config: Optional[ParserRoutingConfig] = None,
):

    def _timed(name: str, result: dict, state: dict) -> dict:
        elapsed = result.pop("_elapsed_ms", 0)
        timings = dict(state.get("step_timings", {}))
        timings[name] = elapsed
        result["step_timings"] = timings
        result["processing_time_ms"] = state.get("processing_time_ms", 0) + elapsed
        return result

    async def analyze_step(state):
        start = time.time()
        r = await analyze_node(state, analyzer)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("analyze", r, state)

    async def route_step(state):
        start = time.time()
        r = await route_node(state, router, routing_config)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("route", r, state)

    async def parse_step(state):
        start = time.time()
        r = await advanced_parse_node(state, parsers)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("parse", r, state)

    async def layout_step(state):
        start = time.time()
        r = await layout_analyze_node(state, layout_analyzer)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("layout_analyze", r, state)

    async def table_step(state):
        start = time.time()
        r = await table_preprocess_node(state, table_preprocessor)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("table_preprocess", r, state)

    async def chunk_step(state):
        start = time.time()
        r = await advanced_chunk_node(state)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("chunk", r, state)

    async def morph_step(state):
        start = time.time()
        r = await morph_node(state, morph_analyzer)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("morph", r, state)

    async def store_step(state):
        start = time.time()
        r = await dual_store_node(state, embedding, vectorstore, es_repo)
        r["_elapsed_ms"] = int((time.time() - start) * 1000)
        return _timed("dual_store", r, state)

    async def complete_step(state):
        return {"status": "completed"}

    def should_continue(state) -> str:
        if state["status"] == "failed":
            return "end"
        return "continue"

    workflow = StateGraph(AdvancedPipelineState)

    workflow.add_node("analyze", analyze_step)
    workflow.add_node("route", route_step)
    workflow.add_node("parse", parse_step)
    workflow.add_node("layout_analyze", layout_step)
    workflow.add_node("table_preprocess", table_step)
    workflow.add_node("chunk", chunk_step)
    workflow.add_node("morph", morph_step)
    workflow.add_node("dual_store", store_step)
    workflow.add_node("complete", complete_step)

    workflow.set_entry_point("analyze")

    workflow.add_conditional_edges("analyze", should_continue, {"continue": "route", "end": END})
    workflow.add_conditional_edges("route", should_continue, {"continue": "parse", "end": END})
    workflow.add_conditional_edges("parse", should_continue, {"continue": "layout_analyze", "end": END})
    workflow.add_conditional_edges("layout_analyze", should_continue, {"continue": "table_preprocess", "end": END})
    workflow.add_conditional_edges("table_preprocess", should_continue, {"continue": "chunk", "end": END})
    workflow.add_conditional_edges("chunk", should_continue, {"continue": "morph", "end": END})
    workflow.add_conditional_edges("morph", should_continue, {"continue": "dual_store", "end": END})
    workflow.add_conditional_edges("dual_store", should_continue, {"continue": "complete", "end": END})
    workflow.add_edge("complete", END)

    return workflow.compile()
