from typing import Dict, Optional

from src.domain.advanced_ingest.schemas import AdvancedIngestRequest, AdvancedIngestResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.pipeline.graph.advanced_processing_graph import create_advanced_processing_graph
from src.infrastructure.pipeline.state.advanced_pipeline_state import create_advanced_initial_state


class AdvancedIngestUseCase:

    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        router: ParserRouterInterface,
        parsers: Dict[str, PDFParserInterface],
        layout_analyzer: LayoutAnalyzer,
        table_preprocessor: TableFlatteningPreprocessor,
        morph_analyzer: MorphAnalyzerInterface,
        embedding: EmbeddingInterface,
        vectorstore: VectorStoreInterface,
        es_repo: ElasticsearchRepositoryInterface,
        logger: LoggerInterface,
        routing_config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._analyzer = analyzer
        self._router = router
        self._parsers = parsers
        self._layout_analyzer = layout_analyzer
        self._table_preprocessor = table_preprocessor
        self._morph_analyzer = morph_analyzer
        self._embedding = embedding
        self._vectorstore = vectorstore
        self._es_repo = es_repo
        self._logger = logger
        self._routing_config = routing_config

    async def ingest(self, request: AdvancedIngestRequest) -> AdvancedIngestResult:
        self._logger.info(
            "Advanced ingest started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
        )

        try:
            graph = create_advanced_processing_graph(
                analyzer=self._analyzer,
                router=self._router,
                parsers=self._parsers,
                layout_analyzer=self._layout_analyzer,
                table_preprocessor=self._table_preprocessor,
                morph_analyzer=self._morph_analyzer,
                embedding=self._embedding,
                vectorstore=self._vectorstore,
                es_repo=self._es_repo,
                routing_config=self._routing_config,
            )

            initial_state = create_advanced_initial_state(
                file_bytes=request.file_bytes,
                filename=request.filename,
                user_id=request.user_id,
                request_id=request.request_id,
                collection_name=request.collection_name,
                chunking_strategy=request.chunking_strategy,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap,
                enable_layout_analysis=request.enable_layout_analysis,
                enable_table_flattening=request.enable_table_flattening,
                sample_pages=request.sample_pages,
            )

            final_state = await graph.ainvoke(initial_state)

        except Exception as exc:
            self._logger.error(
                "Advanced ingest failed",
                exception=exc,
                request_id=request.request_id,
            )
            raise

        result = self._map_to_result(final_state, request)

        self._logger.info(
            "Advanced ingest completed",
            request_id=request.request_id,
            document_type=result.document_type,
            routed_parser=result.routed_parser,
            chunk_count=result.chunk_count,
            qdrant_indexed=result.qdrant_indexed,
            es_indexed=result.es_indexed,
            processing_time_ms=result.processing_time_ms,
        )
        return result

    def _map_to_result(
        self, state: dict, request: AdvancedIngestRequest,
    ) -> AdvancedIngestResult:
        return AdvancedIngestResult(
            document_id=state.get("document_id", ""),
            filename=request.filename,
            user_id=request.user_id,
            total_pages=state.get("total_pages", 0),
            document_type=state.get("document_type"),
            analysis_confidence=state.get("analysis_confidence", 0.0),
            routed_parser=state.get("routed_parser_type", ""),
            layout_quality_score=state.get("layout_quality_score"),
            layout_applied=state.get("layout_applied", False),
            table_count=state.get("table_count", 0),
            table_flattened=state.get("table_flattened", False),
            chunk_count=state.get("chunk_count", 0),
            chunking_strategy=request.chunking_strategy,
            qdrant_indexed=state.get("qdrant_stored_count", 0),
            es_indexed=state.get("es_stored_count", 0),
            processing_time_ms=state.get("processing_time_ms", 0),
            step_timings=state.get("step_timings", {}),
            collection_name=request.collection_name,
            request_id=request.request_id,
            errors=state.get("errors", []),
        )
