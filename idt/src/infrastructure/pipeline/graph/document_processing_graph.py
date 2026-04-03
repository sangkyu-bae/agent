"""LangGraph document processing workflow."""
import time
from typing import Optional

from langgraph.graph import StateGraph, END

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.infrastructure.pipeline.nodes.parse_node import parse_node
from src.infrastructure.pipeline.nodes.classify_node import classify_node
from src.infrastructure.pipeline.nodes.chunk_node import chunk_node
from src.infrastructure.pipeline.nodes.store_node import store_node


def create_initial_state(
    file_path: str,
    filename: str,
    user_id: str,
    file_bytes: Optional[bytes] = None,
) -> PipelineState:
    """Create initial pipeline state.

    Args:
        file_path: Path to PDF file.
        filename: Original filename.
        user_id: User ID.
        file_bytes: Optional file bytes (alternative to file_path).

    Returns:
        Initial PipelineState.
    """
    return {
        "file_path": file_path,
        "file_bytes": file_bytes,
        "filename": filename,
        "user_id": user_id,
        "parsed_documents": [],
        "total_pages": 0,
        "document_id": "",
        "category": None,
        "category_confidence": 0.0,
        "classification_reasoning": "",
        "sample_pages": [],
        "chunked_documents": [],
        "chunk_count": 0,
        "chunking_config_used": {},
        "stored_ids": [],
        "collection_name": "",
        "processing_time_ms": 0,
        "errors": [],
        "status": "pending",
    }


def create_document_processing_graph(
    parser: PDFParserInterface,
    llm_provider: LLMProviderInterface,
    chunking_strategy: ChunkingStrategy,
    vectorstore: VectorStoreInterface,
    embedding: EmbeddingInterface,
    collection_name: str,
) -> StateGraph:
    """Create document processing LangGraph workflow.

    Workflow: parse → classify → chunk → store → complete

    Args:
        parser: PDF parser implementation.
        llm_provider: LLM provider for classification.
        chunking_strategy: Chunking strategy to use.
        vectorstore: Vector store implementation.
        embedding: Embedding provider.
        collection_name: Qdrant collection name.

    Returns:
        Compiled StateGraph.
    """

    async def parse_step(state: PipelineState) -> PipelineState:
        """Parse PDF document."""
        start_time = time.time()
        result = await parse_node(state, parser)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {**result, "processing_time_ms": state["processing_time_ms"] + elapsed_ms}

    async def classify_step(state: PipelineState) -> PipelineState:
        """Classify document category."""
        start_time = time.time()
        result = await classify_node(state, llm_provider)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {**result, "processing_time_ms": state["processing_time_ms"] + elapsed_ms}

    async def chunk_step(state: PipelineState) -> PipelineState:
        """Chunk documents."""
        start_time = time.time()
        result = await chunk_node(state, chunking_strategy)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {**result, "processing_time_ms": state["processing_time_ms"] + elapsed_ms}

    async def store_step(state: PipelineState) -> PipelineState:
        """Store documents in vector store."""
        start_time = time.time()
        result = await store_node(state, vectorstore, embedding, collection_name)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {**result, "processing_time_ms": state["processing_time_ms"] + elapsed_ms}

    async def complete_step(state: PipelineState) -> PipelineState:
        """Mark workflow as completed."""
        return {**state, "status": "completed"}

    def should_continue(state: PipelineState) -> str:
        """Determine next step based on status."""
        if state["status"] == "failed":
            return "end"
        return "continue"

    # Build the graph
    workflow = StateGraph(PipelineState)

    # Add nodes
    workflow.add_node("parse", parse_step)
    workflow.add_node("classify", classify_step)
    workflow.add_node("chunk", chunk_step)
    workflow.add_node("store", store_step)
    workflow.add_node("complete", complete_step)

    # Set entry point
    workflow.set_entry_point("parse")

    # Add conditional edges
    workflow.add_conditional_edges(
        "parse",
        should_continue,
        {"continue": "classify", "end": END},
    )
    workflow.add_conditional_edges(
        "classify",
        should_continue,
        {"continue": "chunk", "end": END},
    )
    workflow.add_conditional_edges(
        "chunk",
        should_continue,
        {"continue": "store", "end": END},
    )
    workflow.add_conditional_edges(
        "store",
        should_continue,
        {"continue": "complete", "end": END},
    )
    workflow.add_edge("complete", END)

    return workflow.compile()
