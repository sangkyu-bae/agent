"""FastAPI application entry point."""
# import sys
# import asyncio
# if sys.platform == "win32":
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient

# Load .env file into environment variables (for LangChain/OpenAI)
load_dotenv()


from src.config import settings
from src.api.routes.document_upload import (
    router as document_router,
    GraphDocumentProcessor,
    DocumentProcessor,
    get_document_processor,
)
from src.api.routes.analysis_router import (
    router as analysis_router,
    get_analyze_excel_use_case,
)
from src.api.routes.excel_upload import (
    router as excel_upload_router,
    get_excel_upload_use_case,
)
from src.api.routes.retrieval_router import (
    router as retrieval_router,
    get_retrieval_use_case,
)
from src.api.routes.hybrid_search_router import (
    router as hybrid_search_router,
    get_hybrid_search_use_case,
)
from src.api.routes.chunk_index_router import (
    router as chunk_index_router,
    get_chunk_index_use_case,
)
from src.api.routes.morph_index_router import (
    router as morph_index_router,
    get_morph_index_use_case,
)
from src.api.routes.rag_agent_router import (
    router as rag_agent_router,
    get_rag_agent_use_case,
)
from src.api.routes.conversation_router import (
    router as conversation_router,
    get_conversation_use_case,
)
from src.api.routes.ingest_router import (
    router as ingest_router,
    get_ingest_use_case,
)
from src.api.routes.doc_chunk_router import (
    router as doc_chunk_router,
    get_doc_chunk_use_case,
)
from src.api.routes.agent_builder_router import (
    router as agent_builder_router,
    get_create_agent_use_case,
    get_update_agent_use_case,
    get_run_agent_use_case,
    get_get_agent_use_case,
    get_interview_use_case,
)
from src.api.routes.auto_agent_builder_router import (
    router as auto_agent_builder_router,
    get_auto_build_use_case,
    get_auto_build_reply_use_case,
    get_session_repository as get_auto_build_session_repository,
)
from src.application.doc_chunk.use_case import DocChunkUseCase
from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.application.ingest.ingest_use_case import IngestDocumentUseCase
from src.application.chunk_and_index.use_case import ChunkAndIndexUseCase
from src.application.morph_index.use_case import MorphAndDualIndexUseCase
from src.application.conversation.use_case import ConversationUseCase
from src.application.rag_agent.use_case import RAGAgentUseCase
from src.application.retrieval.retrieval_use_case import RetrievalUseCase
from src.application.use_cases.excel_upload_use_case import ExcelUploadUseCase
from src.application.agent_builder.tool_selector import ToolSelector
from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.get_agent_use_case import GetAgentUseCase
from src.application.agent_builder.interview_use_case import InterviewUseCase
from src.application.agent_builder.interviewer import Interviewer
from src.application.agent_builder.interview_session_store import InMemoryInterviewSessionStore
from src.infrastructure.agent_builder.agent_definition_repository import AgentDefinitionRepository
from src.infrastructure.agent_builder.tool_factory import ToolFactory
from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
from src.infrastructure.elasticsearch.es_repository import ElasticsearchRepository
from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig
from src.infrastructure.keyword.simple_keyword_extractor import SimpleKeywordExtractor
from src.infrastructure.morph.kiwi_morph_analyzer import KiwiMorphAnalyzer
from src.infrastructure.parser.parser_factory import ParserFactory
from src.infrastructure.embeddings.openai_embedding import OpenAIEmbedding
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore
from src.infrastructure.compressor.providers.openai_provider import OpenAIProvider
from src.infrastructure.compressor.llm_document_compressor import LLMDocumentCompressor
from src.domain.compressor.value_objects.compressor_config import CompressorConfig
from src.infrastructure.retriever.parent_child_retriever import ParentChildRetriever
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory
from src.domain.compressor.value_objects.llm_config import LLMConfig
from src.infrastructure.conversation.langchain_llm import LangChainConversationLLM
from src.infrastructure.conversation.langchain_summarizer import LangChainSummarizer
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.logging.middleware import (
    RequestLoggingMiddleware,
    ExceptionHandlerMiddleware,
)
from src.infrastructure.config.analysis_config import AnalysisConfig
from src.infrastructure.excel.pandas_excel_parser import PandasExcelParser
from src.infrastructure.llm.claude_client import ClaudeClient
from src.infrastructure.web_search.tavily_tool import TavilySearchTool
from src.application.hallucination.use_case import HallucinationEvaluatorUseCase
from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from src.infrastructure.tools.sandbox_executor import SandboxExecutor
from src.infrastructure.persistence.database import get_session_factory
from src.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationMessageRepository,
)
from src.infrastructure.persistence.repositories.conversation_summary_repository import (
    SQLAlchemyConversationSummaryRepository,
)
from src.domain.conversation.policies import SummarizationPolicy
from src.application.workflows.excel_analysis_workflow import ExcelAnalysisWorkflow
from src.application.use_cases.analyze_excel_use_case import AnalyzeExcelUseCase
from src.application.auto_agent_builder.agent_spec_inference_service import AgentSpecInferenceService
from src.application.auto_agent_builder.auto_build_use_case import AutoBuildUseCase
from src.application.auto_agent_builder.auto_build_reply_use_case import AutoBuildReplyUseCase
from src.application.middleware_agent.create_middleware_agent_use_case import CreateMiddlewareAgentUseCase
from src.infrastructure.auto_agent_builder.auto_build_session_repository import AutoBuildSessionRepository
from src.infrastructure.middleware_agent.middleware_agent_repository import MiddlewareAgentRepository
from src.infrastructure.redis.redis_client import RedisClient
from src.infrastructure.redis.redis_repository import RedisRepository

# Auth
from src.api.routes.auth_router import (
    router as auth_router,
    get_register_use_case,
    get_login_use_case,
    get_refresh_use_case,
    get_logout_use_case,
)
from src.api.routes.admin_router import (
    router as admin_router,
    get_pending_users_use_case,
    get_approve_use_case,
    get_reject_use_case,
)
from src.interfaces.dependencies.auth import get_jwt_adapter, get_user_repository
from src.application.auth.register_use_case import RegisterUseCase
from src.application.auth.login_use_case import LoginUseCase
from src.application.auth.refresh_token_use_case import RefreshTokenUseCase
from src.application.auth.logout_use_case import LogoutUseCase
from src.application.auth.get_pending_users_use_case import GetPendingUsersUseCase
from src.application.auth.approve_user_use_case import ApproveUserUseCase
from src.application.auth.reject_user_use_case import RejectUserUseCase
from src.infrastructure.auth.jwt_adapter import JWTAdapter
from src.infrastructure.auth.password_hasher import BcryptPasswordHasher
from src.infrastructure.auth.user_repository import UserRepository
from src.infrastructure.auth.refresh_token_repository import RefreshTokenRepository
from src.infrastructure.config.auth_config import AuthConfig


# Global processor instance (initialized on startup)
_document_processor: Optional[GraphDocumentProcessor] = None

# Global analysis use case instance (initialized on startup)
_analyze_excel_use_case: Optional[AnalyzeExcelUseCase] = None

# Global excel upload use case instance (initialized on startup)
_excel_upload_use_case: Optional[ExcelUploadUseCase] = None

# Global retrieval use case instance (initialized on startup)
_retrieval_use_case: Optional[RetrievalUseCase] = None

# Global hybrid search use case instance (initialized on startup)
_hybrid_search_use_case: Optional[HybridSearchUseCase] = None

# Global chunk-and-index use case instance (initialized on startup)
_chunk_index_use_case: Optional[ChunkAndIndexUseCase] = None

# Global morph-and-dual-index use case instance (initialized on startup)
_morph_index_use_case: Optional[MorphAndDualIndexUseCase] = None

# Global RAG agent use case instance (initialized on startup)
_rag_agent_use_case: Optional[RAGAgentUseCase] = None

# Global ingest use case instance (initialized on startup)
_ingest_use_case: Optional[IngestDocumentUseCase] = None

# Global doc-chunk use case instance (initialized on startup)
_doc_chunk_use_case: Optional[DocChunkUseCase] = None

# Global auto-agent-builder use case instances (initialized on startup)
_auto_build_use_case: Optional[AutoBuildUseCase] = None
_auto_build_reply_use_case: Optional[AutoBuildReplyUseCase] = None
_auto_build_session_repository: Optional[AutoBuildSessionRepository] = None

# Global logger instance
_app_logger: Optional[StructuredLogger] = None


def get_app_logger() -> StructuredLogger:
    """Get the application logger instance.

    Returns:
        StructuredLogger instance.
    """
    global _app_logger
    if _app_logger is None:
        log_level = logging.DEBUG if settings.debug else logging.INFO
        _app_logger = StructuredLogger(name="idt_api", level=log_level)
    return _app_logger


def get_configured_analyze_excel_use_case() -> AnalyzeExcelUseCase:
    """Get the configured excel analysis use case.

    Returns:
        Configured AnalyzeExcelUseCase instance.

    Raises:
        RuntimeError: If use case not initialized.
    """
    if _analyze_excel_use_case is None:
        raise RuntimeError("Excel analysis use case not initialized")
    return _analyze_excel_use_case


def get_configured_excel_upload_use_case() -> ExcelUploadUseCase:
    """Get the configured excel upload use case.

    Returns:
        Configured ExcelUploadUseCase instance.

    Raises:
        RuntimeError: If use case not initialized.
    """
    if _excel_upload_use_case is None:
        raise RuntimeError("Excel upload use case not initialized")
    return _excel_upload_use_case


def get_configured_processor() -> DocumentProcessor:
    """Get the configured document processor.

    Returns:
        Configured GraphDocumentProcessor instance.

    Raises:
        RuntimeError: If processor not initialized.
    """
    if _document_processor is None:
        raise RuntimeError("Document processor not initialized")
    return _document_processor


async def create_processor() -> GraphDocumentProcessor:
    """Create and configure the document processor with all dependencies.

    Returns:
        Configured GraphDocumentProcessor instance.
    """
    # Create parser
    parser = ParserFactory.create_from_string(settings.parser_type)

    # Create LLM provider for classification
    llm_config = LLMConfig(
        provider="openai",
        model_name=settings.openai_llm_model,
        temperature=0.0,
        max_tokens=500,
        api_key=settings.openai_api_key,
    )
    llm_provider = OpenAIProvider(llm_config)

    # Create embedding
    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)

    # Create Qdrant client and vectorstore
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )

    # Create processor
    return GraphDocumentProcessor(
        parser=parser,
        llm_provider=llm_provider,
        vectorstore=vectorstore,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )


def create_analyze_excel_use_case() -> AnalyzeExcelUseCase:
    """Create and configure the excel analysis use case.

    Returns:
        Configured AnalyzeExcelUseCase instance.
    """
    app_logger = get_app_logger()
    analysis_config = AnalysisConfig()
    retry_policy = analysis_config.get_retry_policy()
    quality_threshold = analysis_config.get_quality_threshold()

    excel_parser = PandasExcelParser()

    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_client = ClaudeClient(api_key=anthropic_api_key, logger=app_logger)

    tavily_search = TavilySearchTool()

    hallucination_adapter = HallucinationEvaluatorAdapter()
    hallucination_evaluator = HallucinationEvaluatorUseCase(
        evaluator_adapter=hallucination_adapter,
    )

    code_executor = SandboxExecutor(logger=app_logger)

    workflow = ExcelAnalysisWorkflow(
        excel_parser=excel_parser,
        claude_client=claude_client,
        tavily_search=tavily_search,
        hallucination_evaluator=hallucination_evaluator,
        code_executor=code_executor,
        logger=app_logger,
        retry_policy=retry_policy,
        quality_threshold=quality_threshold,
    )

    return AnalyzeExcelUseCase(
        workflow=workflow,
        logger=app_logger,
        retry_policy=retry_policy,
        quality_threshold=quality_threshold,
    )


def get_configured_chunk_index_use_case() -> ChunkAndIndexUseCase:
    """Get the configured chunk-and-index use case."""
    if _chunk_index_use_case is None:
        raise RuntimeError("ChunkAndIndexUseCase not initialized")
    return _chunk_index_use_case


def get_configured_morph_index_use_case() -> MorphAndDualIndexUseCase:
    """Get the configured morph-and-dual-index use case."""
    if _morph_index_use_case is None:
        raise RuntimeError("MorphAndDualIndexUseCase not initialized")
    return _morph_index_use_case


def get_configured_rag_agent_use_case() -> RAGAgentUseCase:
    """Get the configured RAG agent use case."""
    if _rag_agent_use_case is None:
        raise RuntimeError("RAGAgentUseCase not initialized")
    return _rag_agent_use_case


def create_conversation_use_case_factory():
    """Return a per-request factory for ConversationUseCase."""
    app_logger = get_app_logger()

    async def _factory() -> ConversationUseCase:
        factory = get_session_factory()
        session = factory()
        message_repo = SQLAlchemyConversationMessageRepository(session)
        summary_repo = SQLAlchemyConversationSummaryRepository(session)
        summarizer = LangChainSummarizer(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
        )
        llm = LangChainConversationLLM(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
        )
        policy = SummarizationPolicy()
        return ConversationUseCase(
            message_repo=message_repo,
            summary_repo=summary_repo,
            summarizer=summarizer,
            llm=llm,
            policy=policy,
            logger=app_logger,
        )

    return _factory


def get_configured_hybrid_search_use_case() -> HybridSearchUseCase:
    """Get the configured hybrid search use case."""
    if _hybrid_search_use_case is None:
        raise RuntimeError("HybridSearchUseCase not initialized")
    return _hybrid_search_use_case


def get_configured_retrieval_use_case() -> RetrievalUseCase:
    """Get the configured retrieval use case.

    Returns:
        Configured RetrievalUseCase instance.

    Raises:
        RuntimeError: If use case not initialized.
    """
    if _retrieval_use_case is None:
        raise RuntimeError("Retrieval use case not initialized")
    return _retrieval_use_case


def create_chunk_index_use_case() -> ChunkAndIndexUseCase:
    """Create and configure the chunk-and-index use case."""
    app_logger = get_app_logger()
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)
    chunking_strategy = ChunkingStrategyFactory.create_strategy(
        "parent_child",
        child_chunk_size=settings.default_chunk_size,
        child_chunk_overlap=settings.default_chunk_overlap,
    )
    keyword_extractor = SimpleKeywordExtractor()
    return ChunkAndIndexUseCase(
        chunking_strategy=chunking_strategy,
        keyword_extractor=keyword_extractor,
        es_repo=es_repo,
        es_index=settings.es_index,
        logger=app_logger,
    )


def create_morph_index_use_case() -> MorphAndDualIndexUseCase:
    """Create and configure the morph-and-dual-index use case."""
    app_logger = get_app_logger()
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)
    chunking_strategy = ChunkingStrategyFactory.create_strategy(
        "parent_child",
        child_chunk_size=settings.default_chunk_size,
        child_chunk_overlap=settings.default_chunk_overlap,
    )
    morph_analyzer = KiwiMorphAnalyzer()
    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )
    return MorphAndDualIndexUseCase(
        chunking_strategy=chunking_strategy,
        morph_analyzer=morph_analyzer,
        embedding=embedding,
        vector_store=vector_store,
        es_repo=es_repo,
        es_index=settings.es_index,
        logger=app_logger,
    )


def create_rag_agent_use_case() -> RAGAgentUseCase:
    """Create and configure the RAG agent use case."""
    app_logger = get_app_logger()

    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )
    hybrid_search_uc = HybridSearchUseCase(
        es_repo=es_repo,
        embedding=embedding,
        vector_store=vector_store,
        es_index=settings.es_index,
        logger=app_logger,
    )

    return RAGAgentUseCase(
        hybrid_search_use_case=hybrid_search_uc,
        openai_api_key=settings.openai_api_key,
        model_name=settings.openai_llm_model,
        logger=app_logger,
    )


def create_hybrid_search_use_case() -> HybridSearchUseCase:
    """Create and configure the hybrid search use case."""
    app_logger = get_app_logger()

    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )

    return HybridSearchUseCase(
        es_repo=es_repo,
        embedding=embedding,
        vector_store=vector_store,
        es_index=settings.es_index,
        logger=app_logger,
    )


def create_retrieval_use_case() -> RetrievalUseCase:
    """Create and configure the retrieval use case.

    Returns:
        Configured RetrievalUseCase instance.
    """
    app_logger = get_app_logger()

    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )

    retriever = ParentChildRetriever(
        client=qdrant_client,
        collection_name=settings.qdrant_collection_name,
        embedding=embedding,
    )

    llm_config = LLMConfig(
        provider="openai",
        model_name=settings.openai_llm_model,
        temperature=0.0,
        max_tokens=500,
        api_key=settings.openai_api_key,
    )
    llm_provider = OpenAIProvider(llm_config)
    compressor_config = CompressorConfig()
    compressor = LLMDocumentCompressor(
        llm_provider=llm_provider,
        config=compressor_config,
    )

    return RetrievalUseCase(
        retriever=retriever,
        compressor=compressor,
        query_rewriter=None,
        logger=app_logger,
    )


def create_excel_upload_use_case() -> ExcelUploadUseCase:
    """Create and configure the excel upload use case.

    Returns:
        Configured ExcelUploadUseCase instance.
    """
    app_logger = get_app_logger()
    excel_parser = PandasExcelParser()
    chunking_strategy = ChunkingStrategyFactory.create_strategy(
        "full_token",
        chunk_size=settings.default_chunk_size,
        chunk_overlap=settings.default_chunk_overlap,
    )

    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )

    return ExcelUploadUseCase(
        excel_parser=excel_parser,
        chunking_strategy=chunking_strategy,
        vectorstore=vectorstore,
        embedding=embedding,
        logger=app_logger,
    )


def create_ingest_use_case() -> IngestDocumentUseCase:
    """Create and configure the PDF ingest use case.

    Returns:
        Configured IngestDocumentUseCase with pymupdf and llamaparser parsers.
    """
    app_logger = get_app_logger()
    embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        embedding=embedding,
        collection_name=settings.qdrant_collection_name,
    )
    parsers = {
        "pymupdf": ParserFactory.create_from_string("pymupdf"),
        "llamaparser": ParserFactory.create_from_string(
            "llamaparser", api_key=settings.llama_parse_api_key
        ),
    }
    return IngestDocumentUseCase(
        parsers=parsers,
        embedding=embedding,
        vectorstore=vectorstore,
        logger=app_logger,
    )


def get_configured_ingest_use_case() -> IngestDocumentUseCase:
    """Get the configured ingest use case instance."""
    if _ingest_use_case is None:
        raise RuntimeError("Ingest use case not initialized")
    return _ingest_use_case


def create_doc_chunk_use_case() -> DocChunkUseCase:
    """Create and configure the doc-chunk use case."""
    from src.infrastructure.excel.pandas_excel_parser import PandasExcelParser

    app_logger = get_app_logger()
    pdf_parser = ParserFactory.create_from_string("pymupdf")
    excel_parser = PandasExcelParser()
    return DocChunkUseCase(
        pdf_parser=pdf_parser,
        excel_parser=excel_parser,
        logger=app_logger,
    )


def get_configured_doc_chunk_use_case() -> DocChunkUseCase:
    """Get the configured doc-chunk use case instance."""
    if _doc_chunk_use_case is None:
        raise RuntimeError("DocChunkUseCase not initialized")
    return _doc_chunk_use_case


def create_auto_build_components():
    """Create AutoBuildUseCase, AutoBuildReplyUseCase, AutoBuildSessionRepository."""
    import redis
    app_logger = get_app_logger()

    # Redis 클라이언트 생성
    pool = redis.ConnectionPool(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=settings.redis_db,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )
    redis_client = RedisClient(pool=pool)
    redis_repo = RedisRepository(client=redis_client)
    session_repo = AutoBuildSessionRepository(redis=redis_repo)

    # CreateMiddlewareAgentUseCase (AGENT-005 재사용, per-request MySQL session)
    def _make_create_middleware_agent_uc():
        session = get_session_factory()()
        middleware_agent_repo = MiddlewareAgentRepository(session=session)
        return CreateMiddlewareAgentUseCase(
            repository=middleware_agent_repo,
            logger=app_logger,
        )

    inference_service = AgentSpecInferenceService(
        model_name=settings.openai_llm_model,
        logger=app_logger,
    )

    auto_build_uc = AutoBuildUseCase(
        inference_service=inference_service,
        session_repository=session_repo,
        create_agent_use_case=_make_create_middleware_agent_uc(),
        logger=app_logger,
    )
    auto_build_reply_uc = AutoBuildReplyUseCase(
        inference_service=inference_service,
        session_repository=session_repo,
        create_agent_use_case=_make_create_middleware_agent_uc(),
        logger=app_logger,
    )

    return auto_build_uc, auto_build_reply_uc, session_repo


def get_configured_auto_build_use_case() -> AutoBuildUseCase:
    if _auto_build_use_case is None:
        raise RuntimeError("AutoBuildUseCase not initialized")
    return _auto_build_use_case


def get_configured_auto_build_reply_use_case() -> AutoBuildReplyUseCase:
    if _auto_build_reply_use_case is None:
        raise RuntimeError("AutoBuildReplyUseCase not initialized")
    return _auto_build_reply_use_case


def get_configured_auto_build_session_repository() -> AutoBuildSessionRepository:
    if _auto_build_session_repository is None:
        raise RuntimeError("AutoBuildSessionRepository not initialized")
    return _auto_build_session_repository


def create_auth_factories():
    """Auth use case per-request DI factories.

    JWTAdapter / BcryptPasswordHasher: 상태 없음 → 앱 전체 공유
    UserRepository / RefreshTokenRepository: MySQL session → 요청마다 생성

    Note: AuthConfig는 JWT_SECRET_KEY 환경변수가 없으면 RuntimeError 발생.
    개발 환경에서는 .env에 JWT_SECRET_KEY를 반드시 설정할 것.
    """
    app_logger = get_app_logger()
    try:
        auth_config = AuthConfig()
    except Exception as e:
        app_logger.warning(
            "AuthConfig init failed — auth endpoints disabled",
            error=str(e),
        )
        # JWT_SECRET_KEY 미설정 시 auth 기능 비활성화 (서버는 기동)
        _noop = lambda: (_ for _ in ()).throw(RuntimeError("JWT_SECRET_KEY not configured"))  # noqa: E731
        return (_noop,) * 9

    jwt_adapter = JWTAdapter(config=auth_config)
    password_hasher = BcryptPasswordHasher()

    def _make_user_repo():
        session = get_session_factory()()
        return UserRepository(session=session, logger=app_logger)

    def _make_rt_repo():
        session = get_session_factory()()
        return RefreshTokenRepository(session=session, logger=app_logger)

    def register_factory():
        return RegisterUseCase(
            user_repo=_make_user_repo(),
            password_hasher=password_hasher,
            logger=app_logger,
        )

    def login_factory():
        return LoginUseCase(
            user_repo=_make_user_repo(),
            refresh_token_repo=_make_rt_repo(),
            password_hasher=password_hasher,
            jwt_adapter=jwt_adapter,
            logger=app_logger,
        )

    def refresh_factory():
        return RefreshTokenUseCase(
            rt_repo=_make_rt_repo(),
            jwt_adapter=jwt_adapter,
            logger=app_logger,
        )

    def logout_factory():
        return LogoutUseCase(
            rt_repo=_make_rt_repo(),
            jwt_adapter=jwt_adapter,
            logger=app_logger,
        )

    def pending_users_factory():
        return GetPendingUsersUseCase(
            user_repo=_make_user_repo(),
            logger=app_logger,
        )

    def approve_factory():
        return ApproveUserUseCase(
            user_repo=_make_user_repo(),
            logger=app_logger,
        )

    def reject_factory():
        return RejectUserUseCase(
            user_repo=_make_user_repo(),
            logger=app_logger,
        )

    def jwt_adapter_factory():
        return jwt_adapter

    def user_repo_factory():
        return _make_user_repo()

    return (
        register_factory,
        login_factory,
        refresh_factory,
        logout_factory,
        pending_users_factory,
        approve_factory,
        reject_factory,
        jwt_adapter_factory,
        user_repo_factory,
    )


def create_agent_builder_factories():
    """Return per-request DI factories for Agent Builder use cases."""
    from langchain_openai import ChatOpenAI

    app_logger = get_app_logger()

    llm = ChatOpenAI(
        model=settings.openai_llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    tool_selector = ToolSelector(llm=llm, logger=app_logger)
    prompt_generator = PromptGenerator(llm=llm, logger=app_logger)
    interviewer = Interviewer(llm=llm, logger=app_logger)

    tool_factory = ToolFactory(
        logger=app_logger,
        tavily_api_key=os.environ.get("TAVILY_API_KEY"),
    )
    workflow_compiler = WorkflowCompiler(tool_factory=tool_factory, logger=app_logger)

    # 인터뷰 세션 스토어는 앱 전체에서 공유 (싱글턴)
    interview_session_store = InMemoryInterviewSessionStore()

    def _make_repo():
        session = get_session_factory()()
        return AgentDefinitionRepository(session=session, logger=app_logger)

    def create_uc_factory():
        return CreateAgentUseCase(
            tool_selector=tool_selector,
            prompt_generator=prompt_generator,
            repository=_make_repo(),
            logger=app_logger,
        )

    def update_uc_factory():
        return UpdateAgentUseCase(repository=_make_repo(), logger=app_logger)

    def run_uc_factory():
        return RunAgentUseCase(
            repository=_make_repo(),
            compiler=workflow_compiler,
            openai_api_key=settings.openai_api_key,
            logger=app_logger,
        )

    def get_uc_factory():
        return GetAgentUseCase(repository=_make_repo(), logger=app_logger)

    def interview_uc_factory():
        return InterviewUseCase(
            interviewer=interviewer,
            tool_selector=tool_selector,
            prompt_generator=prompt_generator,
            repository=_make_repo(),
            session_store=interview_session_store,
            logger=app_logger,
        )

    return create_uc_factory, update_uc_factory, run_uc_factory, get_uc_factory, interview_uc_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global _document_processor, _analyze_excel_use_case, _excel_upload_use_case
    global _retrieval_use_case, _hybrid_search_use_case, _chunk_index_use_case
    global _morph_index_use_case, _rag_agent_use_case, _ingest_use_case
    global _doc_chunk_use_case
    global _auto_build_use_case, _auto_build_reply_use_case, _auto_build_session_repository

    # Startup: Initialize processor
    _document_processor = await create_processor()
    _analyze_excel_use_case = create_analyze_excel_use_case()
    _excel_upload_use_case = create_excel_upload_use_case()
    _retrieval_use_case = create_retrieval_use_case()
    _hybrid_search_use_case = create_hybrid_search_use_case()
    _chunk_index_use_case = create_chunk_index_use_case()
    _morph_index_use_case = create_morph_index_use_case()
    _rag_agent_use_case = create_rag_agent_use_case()
    _ingest_use_case = create_ingest_use_case()
    _doc_chunk_use_case = create_doc_chunk_use_case()
    _auto_build_use_case, _auto_build_reply_use_case, _auto_build_session_repository = (
        create_auto_build_components()
    )

    yield

    # Shutdown: Cleanup (if needed)
    _document_processor = None
    _analyze_excel_use_case = None
    _excel_upload_use_case = None
    _retrieval_use_case = None
    _hybrid_search_use_case = None
    _chunk_index_use_case = None
    _morph_index_use_case = None
    _rag_agent_use_case = None
    _ingest_use_case = None
    _doc_chunk_use_case = None
    _auto_build_use_case = None
    _auto_build_reply_use_case = None
    _auto_build_session_repository = None


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="IDT Document Processing API",
        description="PDF document upload, classification, and vector storage API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Get logger
    logger = get_app_logger()

    # Register middleware (order matters: last added = first executed)
    # 1. CORSMiddleware - must be outermost to handle preflight OPTIONS
    # 2. RequestLoggingMiddleware - generates request_id and logs requests
    # 3. ExceptionHandlerMiddleware - handles unhandled exceptions
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware, logger=logger)
    app.add_middleware(ExceptionHandlerMiddleware, logger=logger, debug=settings.debug)

    # Override dependencies
    app.dependency_overrides[get_document_processor] = get_configured_processor
    app.dependency_overrides[get_analyze_excel_use_case] = get_configured_analyze_excel_use_case
    app.dependency_overrides[get_excel_upload_use_case] = get_configured_excel_upload_use_case
    app.dependency_overrides[get_retrieval_use_case] = get_configured_retrieval_use_case
    app.dependency_overrides[get_hybrid_search_use_case] = get_configured_hybrid_search_use_case
    app.dependency_overrides[get_chunk_index_use_case] = get_configured_chunk_index_use_case
    app.dependency_overrides[get_morph_index_use_case] = get_configured_morph_index_use_case
    app.dependency_overrides[get_rag_agent_use_case] = get_configured_rag_agent_use_case
    app.dependency_overrides[get_conversation_use_case] = create_conversation_use_case_factory()
    app.dependency_overrides[get_ingest_use_case] = get_configured_ingest_use_case
    app.dependency_overrides[get_doc_chunk_use_case] = get_configured_doc_chunk_use_case

    # Agent Builder DI
    _create_uc, _update_uc, _run_uc, _get_uc, _interview_uc = create_agent_builder_factories()
    app.dependency_overrides[get_create_agent_use_case] = _create_uc
    app.dependency_overrides[get_update_agent_use_case] = _update_uc
    app.dependency_overrides[get_run_agent_use_case] = _run_uc
    app.dependency_overrides[get_get_agent_use_case] = _get_uc
    app.dependency_overrides[get_interview_use_case] = _interview_uc

    # Auto Agent Builder DI
    app.dependency_overrides[get_auto_build_use_case] = get_configured_auto_build_use_case
    app.dependency_overrides[get_auto_build_reply_use_case] = get_configured_auto_build_reply_use_case
    app.dependency_overrides[get_auto_build_session_repository] = get_configured_auto_build_session_repository

    # Auth DI
    (
        _register_f, _login_f, _refresh_f, _logout_f,
        _pending_f, _approve_f, _reject_f,
        _jwt_f, _user_repo_f,
    ) = create_auth_factories()
    app.dependency_overrides[get_register_use_case] = _register_f
    app.dependency_overrides[get_login_use_case] = _login_f
    app.dependency_overrides[get_refresh_use_case] = _refresh_f
    app.dependency_overrides[get_logout_use_case] = _logout_f
    app.dependency_overrides[get_pending_users_use_case] = _pending_f
    app.dependency_overrides[get_approve_use_case] = _approve_f
    app.dependency_overrides[get_reject_use_case] = _reject_f
    app.dependency_overrides[get_jwt_adapter] = _jwt_f
    app.dependency_overrides[get_user_repository] = _user_repo_f

    # Include routers
    app.include_router(document_router)
    app.include_router(analysis_router)
    app.include_router(excel_upload_router)
    app.include_router(retrieval_router)
    app.include_router(hybrid_search_router)
    app.include_router(chunk_index_router)
    app.include_router(morph_index_router)
    app.include_router(rag_agent_router)
    app.include_router(conversation_router)
    app.include_router(ingest_router)
    app.include_router(doc_chunk_router)
    app.include_router(agent_builder_router)
    app.include_router(auto_agent_builder_router)
    app.include_router(auth_router)
    app.include_router(admin_router)

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    return app


# Create app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
