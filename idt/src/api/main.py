"""FastAPI application entry point."""
# import sys
# import asyncio
# if sys.platform == "win32":
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.api.routes.routed_retrieval_router import (
    router as routed_retrieval_router,
    get_routed_retrieval_use_case,
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
from src.api.routes.conversation_history_router import (
    router as conversation_history_router,
    get_history_use_case,
)
from src.application.conversation.history_use_case import ConversationHistoryUseCase
from src.api.routes.ingest_router import (
    router as ingest_router,
    get_ingest_use_case,
)
from src.api.routes.advanced_ingest_router import (
    router as advanced_ingest_router,
    get_advanced_ingest_use_case,
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
    get_list_agents_use_case,
    get_delete_agent_use_case,
    get_load_mcp_tools_use_case,
    get_subscribe_use_case,
    get_fork_agent_use_case,
    get_list_my_agents_use_case,
    get_list_available_sub_agents_use_case,
    get_attach_skill_use_case,
    get_detach_skill_use_case,
    get_list_attached_skills_use_case,
)
from src.api.routes.approval_router import (
    router as approval_router,
    internal_router as approval_internal_router,
    agent_gate_router as approval_agent_gate_router,
    get_gate_settings_use_case,
    get_decide_approval_use_case,
    get_list_approvals_use_case,
    get_execute_due_approvals_use_case,
    verify_scheduler_token as approval_verify_scheduler_token,
)
from src.api.routes.agent_schedule_router import (
    router as agent_schedule_router,
    trigger_router as agent_schedule_trigger_router,
    verify_scheduler_token as schedule_verify_scheduler_token,
    get_create_schedule_use_case,
    get_list_schedules_use_case,
    get_get_schedule_use_case,
    get_update_schedule_use_case,
    get_delete_schedule_use_case,
    get_toggle_schedule_use_case,
    get_list_schedule_runs_use_case,
    get_trigger_due_schedules_use_case,
)
from src.api.routes.background_job_router import (
    router as background_job_router,
    get_enqueue_job_use_case,
    get_list_jobs_use_case,
    get_get_job_use_case,
    get_count_unseen_use_case,
    get_mark_seen_use_case,
    get_mark_all_seen_use_case,
    get_list_my_schedule_runs_use_case,
    get_delete_job_use_case,
    get_cleanup_jobs_use_case,
    get_list_my_schedules_use_case,
)
from src.api.routes.agent_webhook_router import (
    router as agent_webhook_router,
    get_enable_webhook_use_case,
    get_get_webhook_use_case,
    get_rotate_webhook_use_case,
    get_update_webhook_use_case,
    get_disable_webhook_use_case,
    get_list_webhook_deliveries_use_case,
)
from src.api.routes.webhook_public_router import (
    router as webhook_public_router,
    get_invoke_webhook_use_case,
)
from src.api.routes.rag_tool_router import (
    router as rag_tool_router,
    get_qdrant_client as rag_tool_get_qdrant_client,
    get_collection_aliases as rag_tool_get_aliases,
    get_collection_permission_service as rag_tool_get_perm_service,
)
from src.api.routes.ws_router import (
    router as ws_router,
    get_connection_manager,
    get_ws_jwt_adapter,
    get_ws_user_repository,
    get_ws_run_agent_use_case,
    get_ws_general_chat_use_case,
    get_chat_stream_cache,
    get_ws_auth_context_resolver,
    get_ws_attachment_resolver,
    get_ws_logger,
)
from src.api.routes.agent_attachment_router import (
    router as agent_attachment_router,
    get_upload_attachment_use_case,
)
from src.api.routes.intent_router import (
    router as intent_router,
    get_analyze_intent_use_case,
)
from src.api.routes.document_extractor_router import (
    router as document_extractor_router,
    get_extract_document_use_case,
    get_refine_slots_use_case,
    get_document_attachment_store,
)
from src.application.document_extractor.extract_use_case import (
    ExtractDocumentUseCase,
)
from src.application.document_extractor.refine_use_case import RefineSlotsUseCase
from src.infrastructure.document_extractor.composer import DocumentComposer
from src.infrastructure.document_extractor.document_conversion_adapter import (
    DocumentConversionAdapter,
)
from src.infrastructure.document_font.factory import create_html_font_embedder
from src.infrastructure.document_extractor.document_template_repository import (
    DocumentTemplateRepository,
)
from src.infrastructure.document_extractor.session_scoped_repository import (
    SessionScopedDocumentTemplateRepository,
)
from src.infrastructure.document_extractor.slot_extractor import SlotExtractor
from src.infrastructure.document_extractor.source_file_archiver import (
    SourceFileArchiver,
)
from src.infrastructure.mcp_registry.session_scoped_repository import (
    SessionScopedMcpServerRepository,
)
from src.application.agent_attachment.resolver import AttachmentResolver
from src.application.agent_attachment.upload_use_case import UploadAttachmentUseCase
from src.application.intent.use_case import AnalyzeIntentUseCase
from src.infrastructure.agent_attachment.store import AgentAttachmentStore
from src.application.agent_run.ws_auth_context import WsAuthContextResolver
from src.infrastructure.general_chat.stream_cache import InMemoryChatStreamCache
from src.infrastructure.websocket.connection_manager import ConnectionManager
from src.api.routes.department_router import (
    router as department_router,
    get_list_departments_use_case,
    get_create_department_use_case,
    get_update_department_use_case,
    get_delete_department_use_case,
    get_assign_user_department_use_case,
    get_remove_user_department_use_case,
)
from src.api.routes.tool_catalog_router import (
    router as tool_catalog_router,
    get_list_tool_catalog_use_case,
    get_set_builtin_use_case,
    get_update_tool_metadata_use_case,
    get_sync_mcp_tools_use_case,
)
from src.api.routes.middleware_catalog_router import (
    router as middleware_catalog_router,
    get_list_middleware_catalog_use_case,
    get_set_middleware_flags_use_case,
)
from src.api.routes.auto_agent_builder_router import (
    router as auto_agent_builder_router,
    get_auto_build_use_case,
    get_auto_build_reply_use_case,
    get_session_repository as get_auto_build_session_repository,
    get_create_middleware_agent_use_case as get_auto_build_create_agent_uc,
)
from src.api.routes.mcp_registry_router import (
    router as mcp_registry_router,
    get_register_use_case as get_mcp_register_use_case,
    get_list_use_case as get_mcp_list_use_case,
    get_update_use_case as get_mcp_update_use_case,
    get_delete_use_case as get_mcp_delete_use_case,
    get_test_use_case as get_mcp_test_use_case,
)
from src.api.routes.agent_composer_router import (
    router as agent_composer_router,
    get_compose_agent_use_case,
)
from src.api.routes.prompt_composer_router import (
    router as prompt_composer_router,
    get_append_human_version_use_case,
    get_prompt_composer_use_case,
)
from src.api.routes.agent_pipeline_router import (
    router as agent_pipeline_router,
    get_agent_pipeline_use_case,
)
from src.api.routes.wiki_router import (
    router as wiki_router,
    get_distill_use_case as get_wiki_distill_use_case,
    get_human_write_use_case as get_wiki_human_write_use_case,
    get_query_use_case as get_wiki_query_use_case,
    get_review_use_case as get_wiki_review_use_case,
)
from src.api.routes.memory_router import (
    router as memory_router,
    get_memory_crud_use_case,
)
from src.api.routes.eval_router import (
    router as eval_router,
    get_submit_feedback_use_case,
    get_get_feedback_use_case,
    get_delete_feedback_use_case,
    get_agent_eval_stats_use_case,
)
from src.application.eval.use_cases import (
    SubmitFeedbackUseCase,
    GetFeedbackUseCase,
    DeleteFeedbackUseCase,
    AgentEvalStatsUseCase,
)
from src.infrastructure.eval.repository import MessageFeedbackRepository
from src.application.memory.crud_use_case import MemoryCrudUseCase
from src.application.memory.context_assembler import MemoryContextAssembler
from src.application.memory.extraction_service import MemoryExtractionService
from src.infrastructure.memory.extractor import MemoryCandidateExtractor
from src.infrastructure.memory.repository import MemoryRepository
from src.application.wiki.distill_use_case import DistillToWikiUseCase
from src.application.wiki.feedback_service import FeedbackWikiService
from src.application.wiki.human_write_use_case import HumanWikiWriteUseCase
from src.application.wiki.query_use_case import WikiQueryUseCase
from src.application.wiki.review_use_case import WikiReviewUseCase
from src.infrastructure.wiki.wiki_repository import WikiArticleRepository
from src.infrastructure.wiki.wiki_distiller import WikiDistiller
from src.infrastructure.wiki.feedback_distiller import FeedbackWikiDistiller
from src.infrastructure.wiki.wiki_source_provider import ElasticsearchWikiSourceProvider
from src.api.routes.skill_builder_router import (
    router as skill_builder_router,
    get_create_skill_use_case,
    get_get_skill_use_case,
    get_list_skills_use_case,
    get_update_skill_use_case,
    get_delete_skill_use_case,
    get_fork_skill_use_case,
)
from src.api.routes.middleware_agent_router import (
    router as middleware_agent_router,
    get_create_use_case as get_mw_create_use_case,
    get_get_use_case as get_mw_get_use_case,
    get_run_use_case as get_mw_run_use_case,
    get_update_use_case as get_mw_update_use_case,
)
from src.api.routes.collection_router import (
    router as collection_router,
    get_collection_use_case,
    get_activity_log_service as get_collection_activity_log_service,
)
from src.api.routes.unified_upload_router import (
    router as unified_upload_router,
    get_unified_upload_use_case,
)
from src.api.routes.knowledge_base_router import (
    router as knowledge_base_router,
    get_knowledge_base_use_case,
    get_kb_upload_use_case,
    get_kb_document_chunks_use_case,
    get_kb_document_summary_use_case,
    get_kb_section_summaries_use_case,
    get_list_kb_documents_use_case,
    get_section_summary_query_use_case,
    get_kb_search_use_case,
    get_kb_search_history_use_case,
)
from src.api.routes.admin_collection_router import (
    router as admin_collection_router,
)
from src.api.routes.admin_chunking_router import (
    router as admin_chunking_router,
    get_chunking_profile_use_case,
)
from src.api.routes.chunking_profile_router import (
    router as chunking_profile_router,
)
from src.api.routes.collection_search_router import (
    router as collection_search_router,
    get_collection_search_use_case,
    get_search_history_use_case,
)
from src.api.routes.doc_browse_router import (
    router as doc_browse_router,
    get_list_documents_use_case,
    get_chunks_use_case,
    get_delete_document_use_case,
)
from src.application.doc_browse.list_documents_use_case import ListDocumentsUseCase
from src.application.doc_browse.get_chunks_use_case import GetChunksUseCase
from src.application.doc_browse.delete_document_use_case import DeleteDocumentUseCase
from src.api.routes.excel_export_router import (
    router as excel_export_router,
    get_excel_export_use_case as get_excel_export_uc,
)
from src.api.routes.pdf_export_router import (
    router as pdf_export_router,
    get_html_to_pdf_use_case as get_html_to_pdf_uc,
)
from src.api.routes.preview_router import (
    router as preview_router,
    get_preview_parser,
    get_preview_upload_use_case,
)
from src.application.doc_chunk.use_case import DocChunkUseCase
from src.application.advanced_ingest.use_case import AdvancedIngestUseCase
from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.application.ingest.ingest_use_case import IngestDocumentUseCase
from src.application.chunk_and_index.use_case import ChunkAndIndexUseCase
from src.application.morph_index.use_case import MorphAndDualIndexUseCase
from src.application.conversation.use_case import ConversationUseCase
from src.application.rag_agent.use_case import RAGAgentUseCase
from src.application.retrieval.retrieval_use_case import RetrievalUseCase
from src.application.use_cases.excel_upload_use_case import ExcelUploadUseCase
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_run.aggregator import UsageAggregator
from src.application.agent_run.cost_calculator import CostCalculator
from src.application.agent_run.model_name_resolver import ModelNameResolver
from src.application.agent_run.schemas import RunObservabilityConfig
from src.application.agent_run.tracker import RunTracker
from src.application.agent_builder.get_agent_use_case import GetAgentUseCase
from src.application.agent_builder.list_agents_use_case import ListAgentsUseCase
from src.application.agent_builder.delete_agent_use_case import DeleteAgentUseCase
from src.application.agent_builder.subscribe_use_case import SubscribeUseCase
from src.application.agent_builder.fork_agent_use_case import ForkAgentUseCase
from src.application.agent_builder.list_my_agents_use_case import ListMyAgentsUseCase
from src.application.agent_builder.auto_fork_service import AutoForkService
from src.application.department.create_department_use_case import CreateDepartmentUseCase
from src.application.department.list_departments_use_case import ListDepartmentsUseCase
from src.application.department.update_department_use_case import UpdateDepartmentUseCase
from src.application.department.delete_department_use_case import DeleteDepartmentUseCase
from src.application.department.assign_user_department_use_case import AssignUserDepartmentUseCase
from src.application.department.remove_user_department_use_case import RemoveUserDepartmentUseCase
from src.application.tool_catalog.list_tool_catalog_use_case import ListToolCatalogUseCase
from src.application.tool_catalog.sync_mcp_tools_use_case import SyncMcpToolsUseCase
from src.infrastructure.agent_builder.agent_definition_repository import AgentDefinitionRepository
from src.infrastructure.agent_skill.agent_skill_repository import AgentSkillRepository
from src.infrastructure.agent_builder.subscription_repository import SubscriptionRepository
from src.infrastructure.department.department_repository import DepartmentRepository
from src.infrastructure.tool_catalog.tool_catalog_repository import ToolCatalogRepository
from src.infrastructure.agent_builder.tool_factory import ToolFactory
from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
from src.infrastructure.elasticsearch.es_repository import ElasticsearchRepository
from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig
from src.infrastructure.keyword.simple_keyword_extractor import SimpleKeywordExtractor
from src.infrastructure.morph.kiwi_morph_analyzer import KiwiMorphAnalyzer
from src.infrastructure.parser.parser_factory import ParserFactory
from src.infrastructure.parser.extension_routing_parser import (
    ExtensionRoutingParser,
)
from src.infrastructure.excel.excel_document_parser_adapter import (
    ExcelDocumentParserAdapter,
)
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
from src.infrastructure.llm.llm_factory import LLMFactory
from src.infrastructure.tool_selection.adapters.langchain_filter import (
    LangChainToolFilter,
)
from src.infrastructure.tool_selection.llm_tool_selector import (
    LLMToolSelector,
)
from src.infrastructure.web_search.tavily_tool import TavilySearchTool
from src.application.hallucination.use_case import HallucinationEvaluatorUseCase
from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from src.infrastructure.intent.adapter import LLMIntentAnalyzerAdapter
from src.infrastructure.search_decision.adapter import LLMSearchDecisionAdapter
from src.infrastructure.persistence.database import (
    get_engine,
    get_session,
    get_session_factory,
)
from src.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationMessageRepository,
)
from src.infrastructure.persistence.repositories.conversation_summary_repository import (
    SQLAlchemyConversationSummaryRepository,
)
from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy
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
from src.application.mcp_registry.register_mcp_server_use_case import RegisterMCPServerUseCase
from src.application.mcp_registry.list_mcp_servers_use_case import ListMCPServersUseCase
from src.application.mcp_registry.update_mcp_server_use_case import UpdateMCPServerUseCase
from src.application.mcp_registry.delete_mcp_server_use_case import DeleteMCPServerUseCase
from src.application.mcp_registry.mcp_connection_test_use_case import MCPConnectionTestUseCase
from src.application.middleware_agent.get_middleware_agent_use_case import GetMiddlewareAgentUseCase
from src.application.middleware_agent.run_middleware_agent_use_case import RunMiddlewareAgentUseCase
from src.application.middleware_agent.update_middleware_agent_use_case import UpdateMiddlewareAgentUseCase
from src.application.middleware_agent.middleware_builder import MiddlewareBuilder
from src.application.use_cases.excel_export_use_case import ExcelExportUseCase
from src.infrastructure.excel_export.pandas_excel_exporter import PandasExcelExporter
from src.application.use_cases.html_to_pdf_use_case import HtmlToPdfUseCase
from src.infrastructure.pdf_export.weasyprint_converter import WeasyprintConverter
from src.api.routes.ragas_router import (
    router as ragas_router,
    get_batch_eval_use_case,
    get_realtime_eval_use_case,
    get_eval_result_use_case,
    get_testset_use_case,
    get_testset_generate_use_case,
    # agent-model-benchmark module-5
    get_create_sweep_use_case,
    get_estimate_sweep_use_case,
    get_sweep_detail_use_case,
    get_list_sweeps_use_case,
    get_delete_sweep_use_case,
)
from src.application.ragas.batch_eval_use_case import BatchEvaluationUseCase
from src.application.ragas.realtime_eval_use_case import RealtimeEvaluationUseCase
from src.application.ragas.eval_result_use_case import EvalResultUseCase
from src.application.ragas.testset_use_case import TestsetUseCase
from src.infrastructure.ragas.repository import EvaluationRepository
from src.infrastructure.ragas.ragas_adapter import RagasEvaluatorAdapter

# Auth
from src.api.routes.general_chat_router import (
    router as general_chat_router,
    get_general_chat_use_case,
)
from src.application.general_chat.tools import ChatToolBuilder, MCPToolCache
from src.application.general_chat.use_case import GeneralChatUseCase
from src.application.mcp_registry.load_mcp_tools_use_case import LoadMCPToolsUseCase
from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.visualization.chart_policy import ChartStylePolicy
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.infrastructure.visualization.llm_chart_builder import LangChainChartBuilder
from src.infrastructure.visualization.llm_chart_transformer import (
    LangChainChartTransformer,
)
from src.infrastructure.visualization.llm_classifier import (
    LangChainVisualizationClassifier,
)
from src.infrastructure.mcp_registry.mcp_server_repository import MCPServerRepository
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader
from src.infrastructure.security.secret_cipher import SecretCipher


def _mcp_cipher() -> SecretCipher | None:
    """settings.mcp_secret_key가 설정돼 있으면 SecretCipher를, 없으면 None을 반환한다.

    빈 키면 암호화 비활성(SSE 등 시크릿 없는 서버는 그대로 동작).
    """
    key = settings.mcp_secret_key
    return SecretCipher(key) if key else None
from src.api.routes.auth_router import (
    router as auth_router,
    get_register_use_case,
    get_login_use_case,
    get_refresh_use_case,
    get_logout_use_case,
    get_user_departments_use_case,
)
from src.application.department.get_user_departments_use_case import (
    GetUserDepartmentsUseCase,
)
from src.api.routes.admin_router import (
    router as admin_router,
    get_pending_users_use_case,
    get_approve_use_case,
    get_reject_use_case,
)
from src.api.routes.admin_ragas_router import (
    router as admin_ragas_router,
    get_admin_eval_use_case,
)
from src.application.ragas.admin_eval_use_case import AdminEvalUseCase
from src.api.routes.embedding_model_router import (
    router as embedding_model_router,
    get_list_embedding_models_use_case,
)
from src.application.embedding_model.list_embedding_models_use_case import (
    ListEmbeddingModelsUseCase,
)
from src.infrastructure.embedding_model.repository import (
    EmbeddingModelRepository,
)
from src.infrastructure.embedding_model.seed import (
    seed_default_embedding_models,
)
from src.api.routes.llm_model_router import (
    router as llm_model_router,
    get_create_llm_model_use_case,
    get_update_llm_model_use_case,
    get_deactivate_llm_model_use_case,
    get_get_llm_model_use_case,
    get_list_llm_models_use_case,
    get_update_llm_model_pricing_use_case,
)
from src.api.routes.admin_dashboard_router import (
    router as admin_dashboard_router,
    get_dashboard_stats_use_case,
    get_kb_breakdown_use_case,
    get_recent_documents_use_case,
    get_storage_health_use_case,
)
from src.application.admin_dashboard.use_cases import (
    GetDashboardStatsUseCase,
    GetKbBreakdownUseCase,
    GetRecentDocumentsUseCase,
    StorageHealthCheckUseCase,
)
from src.infrastructure.admin_dashboard.aggregation_repository import (
    SqlAlchemyDashboardAggregationRepository,
)
from src.infrastructure.admin_dashboard.health_adapter import (
    StorageHealthAdapter,
    build_es_check,
    build_mysql_check,
    build_qdrant_check,
)
from src.api.routes.agent_run_router import (
    router as agent_run_router,
    get_run_detail_use_case,
    get_usage_by_user_use_case,
    get_usage_by_llm_use_case,
    get_usage_by_node_use_case,
    get_usage_me_use_case,
    get_list_runs_use_case,
    get_list_my_runs_use_case,
    get_usage_summary_use_case,
    get_usage_timeseries_use_case,
    get_my_usage_timeseries_use_case,
    get_message_retrievals_use_case,
)
from src.application.llm_model.create_llm_model_use_case import CreateLlmModelUseCase
from src.application.llm_model.update_llm_model_use_case import UpdateLlmModelUseCase
from src.application.llm_model.deactivate_llm_model_use_case import DeactivateLlmModelUseCase
from src.application.llm_model.get_llm_model_use_case import GetLlmModelUseCase
from src.application.llm_model.list_llm_models_use_case import ListLlmModelsUseCase
from src.application.llm_model.update_llm_model_pricing_use_case import (
    UpdateLlmModelPricingUseCase,
)
from src.application.llm_model.utility_llm_provider import UtilityLLMProvider
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.infrastructure.cache.in_memory_cache import InMemoryCache
from src.application.agent_run.use_cases.get_run_detail_use_case import (
    GetRunDetailUseCase,
)
from src.application.agent_run.use_cases.get_message_retrievals_use_case import (
    GetMessageRetrievalsUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_user_use_case import (
    GetUsageByUserUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_llm_use_case import (
    GetUsageByLlmUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_node_use_case import (
    GetUsageByNodeUseCase,
)
from src.application.agent_run.use_cases.get_usage_me_use_case import (
    GetUsageMeUseCase,
)
from src.application.agent_run.use_cases.list_runs_use_case import (
    ListRunsUseCase,
)
from src.application.agent_run.use_cases.list_my_runs_use_case import (
    ListMyRunsUseCase,
)
from src.application.agent_run.use_cases.get_usage_summary_use_case import (
    GetUsageSummaryUseCase,
)
from src.application.agent_run.use_cases.get_usage_timeseries_use_case import (
    GetUsageTimeseriesUseCase,
)
from src.application.agent_run.use_cases.get_my_usage_timeseries_use_case import (
    GetMyUsageTimeseriesUseCase,
)
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
)
from src.infrastructure.persistence.repositories.llm_call_repository import (
    SqlAlchemyLlmCallRepository,
)
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm_model.llm_model_repository import LlmModelRepository
from src.infrastructure.llm_model.seed import seed_default_models
from src.interfaces.dependencies.auth import (
    get_jwt_adapter,
    get_user_repository,
    get_assemble_auth_context_use_case,
)
from src.application.auth.register_use_case import RegisterUseCase
from src.application.permission.assemble_auth_context import AssembleAuthContextUseCase
from src.application.permission.grant_revoke import (
    GrantPermissionUseCase,
    RevokePermissionUseCase,
)
from src.infrastructure.user_profile.repository import UserProfileRepository
from src.infrastructure.permission.repository import PermissionRepository
from src.api.routes.admin_user_router import (
    router as admin_user_router,
    get_grant_permission_use_case,
    get_revoke_permission_use_case,
    get_permission_repository,
    get_admin_create_user_use_case,
    get_list_users_use_case,
)
from src.application.auth.admin_create_user_use_case import AdminCreateUserUseCase
from src.application.auth.list_users_use_case import ListUsersUseCase
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

# excel-chart-routing-dedup: Supervisor 재사용용 차트 OFF 워크플로우.
# 시각화는 상위 Supervisor chart_router가 전담하므로 내부 차트 서브그래프 미등록(중복 제거).
_supervisor_excel_workflow: Optional[ExcelAnalysisWorkflow] = None

# Global excel upload use case instance (initialized on startup)
_excel_upload_use_case: Optional[ExcelUploadUseCase] = None

# ws-agent-excel-attachment: Global attachment store (initialized on startup)
_attachment_store: Optional[AgentAttachmentStore] = None

# background-jobs: 워커 루프 싱글턴 (create_app 에서 조립, lifespan 에서 start/stop)
_background_job_worker = None

# Global retrieval use case instance (initialized on startup)
_retrieval_use_case: Optional[RetrievalUseCase] = None

# Global hybrid search use case instance (initialized on startup)
_hybrid_search_use_case: Optional[HybridSearchUseCase] = None
_routed_retrieval_use_case = None  # RoutedRetrievalUseCase (summary-routed-retrieval)

# Global chunk-and-index use case instance (initialized on startup)
_chunk_index_use_case: Optional[ChunkAndIndexUseCase] = None

# Global morph-and-dual-index use case instance (initialized on startup)
_morph_index_use_case: Optional[MorphAndDualIndexUseCase] = None

# Global RAG agent use case instance (initialized on startup)
_rag_agent_use_case: Optional[RAGAgentUseCase] = None

# Global ingest use case instance (initialized on startup)
_ingest_use_case: Optional[IngestDocumentUseCase] = None

# Global advanced ingest use case instance (initialized on startup)
_advanced_ingest_use_case: Optional[AdvancedIngestUseCase] = None

# Global doc-chunk use case instance (initialized on startup)
_doc_chunk_use_case: Optional[DocChunkUseCase] = None

# Global auto-agent-builder use case instances (initialized on startup)
_auto_build_use_case: Optional[AutoBuildUseCase] = None
_auto_build_reply_use_case: Optional[AutoBuildReplyUseCase] = None
_auto_build_session_repository: Optional[AutoBuildSessionRepository] = None

# Global LLM factory and default model (initialized on startup)
_llm_factory: LLMFactory = LLMFactory()
_default_llm_model: Optional[LlmModel] = None

# admin-default-llm-routing: 보조 LLM 공급자 (앱 수명 싱글톤, lazy).
# 관리자가 지정한 기본/보조 모델을 요청 시점마다 해석해 어댑터에 공급한다.
# _default_llm_model 과 달리 부팅 시 고정되지 않는다 — 재시작 없는 교체가 목적.
_utility_llm_provider: Optional[UtilityLLMProvider] = None


def get_utility_llm_provider() -> UtilityLLMProvider:
    """보조 LLM 공급자 lazy 싱글톤 (admin-default-llm-routing §2.1).

    세션은 보유하지 않는다 — 캐시 미스 시에만 session_factory 로 단기 읽기
    세션을 연다 (Design §9.4).
    """
    global _utility_llm_provider
    if _utility_llm_provider is None:
        app_logger = get_app_logger()
        cache = InMemoryCache(
            default_ttl_seconds=settings.llm_model_cache_ttl_seconds,
            max_entries=64,
        )
        _utility_llm_provider = UtilityLLMProvider(
            cache=cache,
            llm_factory=_llm_factory,
            session_factory=get_session_factory(),
            repo_builder=lambda session: LlmModelRepository(
                session=session, logger=app_logger
            ),
            logger=app_logger,
            utility_model_name=settings.utility_llm_model_name,
            ttl_seconds=settings.llm_model_cache_ttl_seconds,
            max_instances=settings.llm_instance_cache_max_entries,
        )
    return _utility_llm_provider

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


def get_configured_excel_analysis_workflow():
    """analysis-node-agent: 분석 노드의 엑셀 분기용 ExcelAnalysisWorkflow.

    excel-chart-routing-dedup: 차트 OFF 인스턴스(`_supervisor_excel_workflow`)를 반환한다.
    시각화는 상위 Supervisor chart_router/chart_builder가 전담하므로 내부 차트 노드를
    태우지 않아 중복(폐기되는 chart_builder LLM 호출)을 제거한다.
    미초기화 시 None 반환 → 분석 노드가 문맥 분석으로 graceful fallback.
    """
    return _supervisor_excel_workflow


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


# ── ws-agent-excel-attachment: 첨부 저장소/유스케이스 와이어링 ──────────────

def create_attachment_store() -> AgentAttachmentStore:
    """첨부 임시 저장소 생성. config 경로가 비면 시스템 tmp 하위로 해석."""
    import os
    import tempfile

    upload_dir = settings.agent_attachment_upload_dir or os.path.join(
        tempfile.gettempdir(), "agent_attachments"
    )
    return AgentAttachmentStore(
        upload_dir, ttl_seconds=settings.agent_attachment_ttl_seconds
    )


def _document_template_archive_dir() -> str:
    """원본 영구 보관 디렉토리 (document-template-extractor D3). 빈 값이면 기본 경로."""
    import os

    return settings.document_template_dir or os.path.join(
        "uploads", "document_templates"
    )


def create_document_extractor_factories():
    """document-template-extractor Design §6: extract/refine per-request DI 팩토리."""
    from src.infrastructure.llm_model.session_scoped_llm_model_repository import (
        SessionScopedLlmModelRepository,
    )

    app_logger = get_app_logger()
    slot_extractor = SlotExtractor(
        llm_factory=_llm_factory,
        llm_model_repository=SessionScopedLlmModelRepository(
            session_factory=get_session_factory(), logger=app_logger
        ),
        logger=app_logger,
        llm_html_max_chars=settings.document_extractor_llm_html_max_chars,
    )
    # fix-doc-generator-korean-font GAP-03 — 임베더는 폰트 파일·cmap 캐시를
    # 인스턴스에 들고 있다. 요청마다 새로 만들면 캐시가 항상 cold 라 변환 1건당
    # 2.7MB 폰트를 4회 읽는다(~240ms). 팩토리 밖에서 1회만 만들어 공유한다.
    font_embedder = create_html_font_embedder(settings, app_logger)

    def extract_factory(session: AsyncSession = Depends(get_session)):
        adapter = DocumentConversionAdapter(
            mcp_tool_loader=MCPToolLoader(logger=app_logger),
            mcp_repository=MCPServerRepository(
                session=session, logger=app_logger, cipher=_mcp_cipher()
            ),
            logger=app_logger,
            # fix-doc-generator-korean-font §11.1 — html→doc 변환 시 한글 폰트 보장
            font_embedder=font_embedder,
        )
        return ExtractDocumentUseCase(
            attachment_store=_attachment_store,
            conversion_adapter=adapter,
            slot_extractor=slot_extractor,
            logger=app_logger,
            max_file_mb=settings.document_extractor_max_file_mb,
            default_pdf_to_html_tool_id=(
                settings.document_extractor_pdf_to_html_tool_id
            ),
            default_html_to_doc_tool_id=(
                settings.document_extractor_html_to_doc_tool_id
            ),
            preview_mode=settings.document_extractor_preview_mode,
            preview_dpi=settings.document_extractor_preview_dpi,
        )

    def refine_factory():
        return RefineSlotsUseCase(
            slot_extractor=slot_extractor,
            logger=app_logger,
            max_regen=settings.document_extractor_max_regen,
        )

    return extract_factory, refine_factory


def get_configured_upload_attachment_use_case() -> UploadAttachmentUseCase:
    if _attachment_store is None:
        raise RuntimeError("Attachment store not initialized")
    return UploadAttachmentUseCase(
        store=_attachment_store,
        max_bytes=settings.agent_attachment_max_bytes,
        logger=get_app_logger(),
    )


def get_configured_ws_attachment_resolver() -> AttachmentResolver:
    if _attachment_store is None:
        raise RuntimeError("Attachment store not initialized")
    return AttachmentResolver(store=_attachment_store, logger=get_app_logger())


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
    global _supervisor_excel_workflow
    app_logger = get_app_logger()
    analysis_config = AnalysisConfig()
    retry_policy = analysis_config.get_retry_policy()
    quality_threshold = analysis_config.get_quality_threshold()

    excel_parser = PandasExcelParser()

    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_client = ClaudeClient(api_key=anthropic_api_key, logger=app_logger)

    tavily_search = TavilySearchTool()

    # admin-default-llm-routing AD-2: 관리자 설정 모델을 런타임에 따라간다.
    hallucination_adapter = HallucinationEvaluatorAdapter(
        llm_provider=get_utility_llm_provider()
    )
    hallucination_evaluator = HallucinationEvaluatorUseCase(
        evaluator_adapter=hallucination_adapter,
    )

    search_decision = LLMSearchDecisionAdapter(
        logger=app_logger, llm_provider=get_utility_llm_provider()
    )

    # supervisor-chart-builder-node: 엑셀 분석 결과 시각화용 chart_builder.
    # _default_llm_model 미로드(None) 시 빌더 비활성 → chart_router→END 하위호환.
    excel_chart_builder = None
    if _default_llm_model is not None:
        excel_viz_llm = _llm_factory.create(_default_llm_model, temperature=0)
        excel_chart_builder = LangChainChartBuilder(
            llm=excel_viz_llm,
            logger=app_logger,
            style_policy=ChartStylePolicy(),
            max_count=settings.chart_max_count,
        )

    # Standalone(analysis_router) 경로 — 차트 ON. 최종 답변+차트를 화면에 렌더.
    workflow = ExcelAnalysisWorkflow(
        excel_parser=excel_parser,
        claude_client=claude_client,
        tavily_search=tavily_search,
        hallucination_evaluator=hallucination_evaluator,
        search_decision=search_decision,
        logger=app_logger,
        retry_policy=retry_policy,
        quality_threshold=quality_threshold,
        chart_builder=excel_chart_builder,
        enable_visualization=True,
        # ★ runtime-datetime-context D3: [현재 날짜] 블록 기준 타임존
        agent_timezone=settings.agent_timezone,
    )

    # excel-chart-routing-dedup: Supervisor 재사용 경로 — 차트 OFF.
    # 의존성은 공유(stateless)하되 차트 서브그래프를 등록하지 않아 상위 노드와의 중복 제거.
    _supervisor_excel_workflow = ExcelAnalysisWorkflow(
        excel_parser=excel_parser,
        claude_client=claude_client,
        tavily_search=tavily_search,
        hallucination_evaluator=hallucination_evaluator,
        search_decision=search_decision,
        logger=app_logger,
        retry_policy=retry_policy,
        quality_threshold=quality_threshold,
        chart_builder=None,
        enable_visualization=False,
        agent_timezone=settings.agent_timezone,
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
    """Return a per-request factory for ConversationUseCase.

    DB-001 §10.2: 세션은 `get_session` dependency 로 주입받아 repository 가 공유한다.
    """
    app_logger = get_app_logger()

    async def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> ConversationUseCase:
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


def get_configured_routed_retrieval_use_case():
    """Get the configured routed retrieval use case (summary-routed-retrieval)."""
    if _routed_retrieval_use_case is None:
        raise RuntimeError("RoutedRetrievalUseCase not initialized")
    return _routed_retrieval_use_case


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
        llm_factory=_llm_factory,
        llm_model=_default_llm_model,
        logger=app_logger,
        # ★ runtime-datetime-context D3: [현재 날짜] 블록 기준 타임존
        agent_timezone=settings.agent_timezone,
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


def create_routed_retrieval_use_case():
    """Create the routed retrieval use case (summary-routed-retrieval Design D10).

    싱글턴 — 폴백은 getter 주입으로 lifespan 생성 순서와 무관.
    """
    from src.application.routed_retrieval.use_case import RoutedRetrievalUseCase
    from src.domain.routed_retrieval.policy import RoutedRetrievalPolicy
    from src.domain.hybrid_search.policies import RRFFusionPolicy
    from src.infrastructure.routed_retrieval.es_chunk_expander import (
        EsChunkExpander,
    )
    from src.infrastructure.routed_retrieval.hybrid_section_router import (
        HybridSectionRouter,
    )
    from src.infrastructure.routed_retrieval.qdrant_document_router import (
        QdrantDocumentRouter,
    )

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

    return RoutedRetrievalUseCase(
        embedding=embedding,
        document_router=QdrantDocumentRouter(vector_store, app_logger),
        section_router=HybridSectionRouter(
            vector_store=vector_store,
            es_repo=es_repo,
            es_index=settings.es_index,
            rrf_policy=RRFFusionPolicy(),
            logger=app_logger,
        ),
        chunk_expander=EsChunkExpander(es_repo, settings.es_index, app_logger),
        policy=RoutedRetrievalPolicy(),
        hybrid_search_getter=get_configured_hybrid_search_use_case,
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

    from src.application.collection.fire_and_forget_activity_logger import FireAndForgetActivityLogger

    activity_logger = FireAndForgetActivityLogger(
        session_factory=get_session_factory(),
        logger=app_logger,
    )

    return RetrievalUseCase(
        retriever=retriever,
        compressor=compressor,
        query_rewriter=None,
        logger=app_logger,
        activity_log_factory=lambda: activity_logger,
        collection_name=settings.qdrant_collection_name,
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
        "pymupdf4llm": ParserFactory.create_from_string("pymupdf4llm"),
        "llamaparser": ParserFactory.create_from_string(
            "llamaparser", api_key=settings.llama_parse_api_key
        ),
    }
    from src.application.collection.fire_and_forget_activity_logger import FireAndForgetActivityLogger

    activity_logger = FireAndForgetActivityLogger(
        session_factory=get_session_factory(),
        logger=app_logger,
    )

    from src.infrastructure.doc_browse.session_scoped_metadata_repository import SessionScopedDocumentMetadataRepository
    doc_metadata_repo = SessionScopedDocumentMetadataRepository(
        session_factory=get_session_factory(),
        logger=app_logger,
    )

    return IngestDocumentUseCase(
        parsers=parsers,
        embedding=embedding,
        vectorstore=vectorstore,
        logger=app_logger,
        activity_log_factory=lambda: activity_logger,
        collection_name=settings.qdrant_collection_name,
        document_metadata_repo=doc_metadata_repo,
    )


def get_configured_ingest_use_case() -> IngestDocumentUseCase:
    """Get the configured ingest use case instance."""
    if _ingest_use_case is None:
        raise RuntimeError("Ingest use case not initialized")
    return _ingest_use_case


def create_advanced_ingest_use_case() -> AdvancedIngestUseCase:
    """Create and configure the advanced PDF ingest use case."""
    from src.infrastructure.pdf_analyzer.pymupdf_analyzer import PyMuPDFAnalyzer
    from src.infrastructure.pdf_routing.default_parser_router import DefaultParserRouter
    from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
    from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
    from src.infrastructure.chunking.table_flattening.rule_based_generator import RuleBasedTableContentGenerator

    app_logger = get_app_logger()
    analyzer = PyMuPDFAnalyzer()
    parser_router = DefaultParserRouter()
    parsers = {
        "pymupdf": ParserFactory.create_from_string("pymupdf"),
        "pymupdf4llm": ParserFactory.create_from_string("pymupdf4llm"),
        "llamaparser": ParserFactory.create_from_string(
            "llamaparser", api_key=settings.llama_parse_api_key
        ),
    }
    layout_analyzer = LayoutAnalyzer()
    table_preprocessor = TableFlatteningPreprocessor(RuleBasedTableContentGenerator())
    morph_analyzer = KiwiMorphAnalyzer()
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
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    return AdvancedIngestUseCase(
        analyzer=analyzer,
        router=parser_router,
        parsers=parsers,
        layout_analyzer=layout_analyzer,
        table_preprocessor=table_preprocessor,
        morph_analyzer=morph_analyzer,
        embedding=embedding,
        vectorstore=vectorstore,
        es_repo=es_repo,
        logger=app_logger,
    )


def get_configured_advanced_ingest_use_case() -> AdvancedIngestUseCase:
    """Get the configured advanced ingest use case instance."""
    if _advanced_ingest_use_case is None:
        raise RuntimeError("AdvancedIngestUseCase not initialized")
    return _advanced_ingest_use_case


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
    """Create AutoBuildUseCase, AutoBuildReplyUseCase, AutoBuildSessionRepository.

    DB-001 §10.4: AutoBuild*UseCase 는 lifespan singleton 으로 유지하되,
    DB session 을 가진 CreateMiddlewareAgentUseCase 는 execute() 호출 시점에 주입받는다.
    """
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

    inference_service = AgentSpecInferenceService(
        llm_factory=_llm_factory,
        llm_model=_default_llm_model,
        logger=app_logger,
    )

    auto_build_uc = AutoBuildUseCase(
        inference_service=inference_service,
        session_repository=session_repo,
        logger=app_logger,
    )
    auto_build_reply_uc = AutoBuildReplyUseCase(
        inference_service=inference_service,
        session_repository=session_repo,
        logger=app_logger,
    )

    return auto_build_uc, auto_build_reply_uc, session_repo


def create_middleware_agent_use_case_factory():
    """요청 스코프 CreateMiddlewareAgentUseCase 팩토리 (DB-001 §10.4).

    AutoBuild*UseCase.execute() 에서 kwarg 로 주입된다.
    """
    app_logger = get_app_logger()

    def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> CreateMiddlewareAgentUseCase:
        middleware_agent_repo = MiddlewareAgentRepository(session=session)
        return CreateMiddlewareAgentUseCase(
            repository=middleware_agent_repo,
            logger=app_logger,
        )

    return _factory


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

    # DB-001 §10.2: session 은 Depends(get_session) 으로 주입, repo 간 공유.
    def _make_user_repo(session: AsyncSession):
        return UserRepository(session=session, logger=app_logger)

    def _make_rt_repo(session: AsyncSession):
        return RefreshTokenRepository(session=session, logger=app_logger)

    def _make_user_profile_repo(session: AsyncSession):
        return UserProfileRepository(session=session, logger=app_logger)

    def register_factory(session: AsyncSession = Depends(get_session)):
        return RegisterUseCase(
            user_repo=_make_user_repo(session),
            password_hasher=password_hasher,
            logger=app_logger,
            user_profile_repo=_make_user_profile_repo(session),
        )

    def login_factory(session: AsyncSession = Depends(get_session)):
        return LoginUseCase(
            user_repo=_make_user_repo(session),
            refresh_token_repo=_make_rt_repo(session),
            password_hasher=password_hasher,
            jwt_adapter=jwt_adapter,
            logger=app_logger,
        )

    def refresh_factory(session: AsyncSession = Depends(get_session)):
        return RefreshTokenUseCase(
            rt_repo=_make_rt_repo(session),
            jwt_adapter=jwt_adapter,
            logger=app_logger,
        )

    def logout_factory(session: AsyncSession = Depends(get_session)):
        return LogoutUseCase(
            rt_repo=_make_rt_repo(session),
            jwt_adapter=jwt_adapter,
            logger=app_logger,
        )

    def pending_users_factory(session: AsyncSession = Depends(get_session)):
        return GetPendingUsersUseCase(
            user_repo=_make_user_repo(session),
            logger=app_logger,
        )

    def approve_factory(session: AsyncSession = Depends(get_session)):
        return ApproveUserUseCase(
            user_repo=_make_user_repo(session),
            logger=app_logger,
        )

    def reject_factory(session: AsyncSession = Depends(get_session)):
        return RejectUserUseCase(
            user_repo=_make_user_repo(session),
            logger=app_logger,
        )

    def jwt_adapter_factory():
        return jwt_adapter

    def user_repo_factory(session: AsyncSession = Depends(get_session)):
        return _make_user_repo(session)

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


def create_auth_context_factories():
    """Auth context use case per-request DI factories.

    agent-user-context Design §6.1:
    AssembleAuthContextUseCase, GrantPermissionUseCase, RevokePermissionUseCase,
    PermissionRepository — 모두 session-scoped (요청마다 생성).

    Note: DepartmentRepository는 기존 infra에서 재사용.
    """
    app_logger = get_app_logger()

    def _make_user_profile_repo(session: AsyncSession) -> UserProfileRepository:
        return UserProfileRepository(session=session, logger=app_logger)

    def _make_permission_repo(session: AsyncSession) -> PermissionRepository:
        return PermissionRepository(session=session, logger=app_logger)

    def _make_department_repo(session: AsyncSession):
        return DepartmentRepository(session=session, logger=app_logger)

    def assemble_auth_context_factory(
        session: AsyncSession = Depends(get_session),
    ) -> AssembleAuthContextUseCase:
        return AssembleAuthContextUseCase(
            profile_repo=_make_user_profile_repo(session),
            department_repo=_make_department_repo(session),
            permission_repo=_make_permission_repo(session),
            logger=app_logger,
        )

    def grant_permission_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GrantPermissionUseCase:
        return GrantPermissionUseCase(
            permission_repo=_make_permission_repo(session),
            logger=app_logger,
        )

    def revoke_permission_factory(
        session: AsyncSession = Depends(get_session),
    ) -> RevokePermissionUseCase:
        return RevokePermissionUseCase(
            permission_repo=_make_permission_repo(session),
            logger=app_logger,
        )

    def permission_repo_factory(
        session: AsyncSession = Depends(get_session),
    ) -> PermissionRepository:
        return _make_permission_repo(session)

    return (
        assemble_auth_context_factory,
        grant_permission_factory,
        revoke_permission_factory,
        permission_repo_factory,
    )


def create_ws_auth_context_resolver() -> WsAuthContextResolver:
    """WS 전용 AuthContext 조립기 (단기 세션 기반).

    fix-ws-auth-context-missing Design §3.3.1:
    - WS 연결은 스트리밍 동안 장시간 유지되므로 request-scoped 세션을 점유하지 않도록
      resolver.execute() 내부에서 session_factory로 단기 세션을 연다.
    - CLAUDE.md §6: get_session_factory()를 주입, async with로 단기 사용.
    """
    app_logger = get_app_logger()

    def _assemble_uc_builder(session: AsyncSession) -> AssembleAuthContextUseCase:
        return AssembleAuthContextUseCase(
            profile_repo=UserProfileRepository(session=session, logger=app_logger),
            department_repo=DepartmentRepository(session=session, logger=app_logger),
            permission_repo=PermissionRepository(session=session, logger=app_logger),
            logger=app_logger,
        )

    return WsAuthContextResolver(
        session_factory=get_session_factory(),
        assemble_uc_builder=_assemble_uc_builder,
    )


def create_admin_user_mgmt_factories():
    """admin-user-registration Design §5.2: 사용자 생성/목록 per-request DI factories.

    DB-001 §10.2: session 은 Depends(get_session) 으로 주입, User/Profile/Department
    repo 가 동일 세션을 공유 → User+Profile+부서 배정이 단일 트랜잭션으로 commit/rollback.
    """
    app_logger = get_app_logger()
    password_hasher = BcryptPasswordHasher()

    def _user(session: AsyncSession) -> UserRepository:
        return UserRepository(session=session, logger=app_logger)

    def _profile(session: AsyncSession) -> UserProfileRepository:
        return UserProfileRepository(session=session, logger=app_logger)

    def _dept(session: AsyncSession) -> DepartmentRepository:
        return DepartmentRepository(session=session, logger=app_logger)

    def admin_create_user_factory(
        session: AsyncSession = Depends(get_session),
    ) -> AdminCreateUserUseCase:
        return AdminCreateUserUseCase(
            user_repo=_user(session),
            user_profile_repo=_profile(session),
            department_repo=_dept(session),
            password_hasher=password_hasher,
            logger=app_logger,
        )

    def list_users_factory(
        session: AsyncSession = Depends(get_session),
    ) -> ListUsersUseCase:
        return ListUsersUseCase(
            user_repo=_user(session),
            user_profile_repo=_profile(session),
            department_repo=_dept(session),
            logger=app_logger,
        )

    return admin_create_user_factory, list_users_factory


def create_llm_model_factories(
    cost_calculator: CostCalculator | None = None,
    llm_provider: UtilityLLMProviderPort | None = None,
):
    """Return per-request DI factories for LLM Model registry (LLM-MODEL-REG-001 + M4).

    DB-001 §10.2: session 은 Depends(get_session) 으로 주입. repo 는 동일 세션 공유.
    M4: cost_calculator 주입 시 update_pricing_factory도 함께 반환 (★ M1 G1).
    admin-default-llm-routing AD-3: llm_provider 주입 시 모델 변경 4경로가
    보조 LLM 해석 캐시를 무효화한다 (미주입이면 기존 동작 — FR-9).
    """
    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession) -> LlmModelRepository:
        return LlmModelRepository(session=session, logger=app_logger)

    def create_factory(session: AsyncSession = Depends(get_session)) -> CreateLlmModelUseCase:
        return CreateLlmModelUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            llm_provider=llm_provider,
        )

    def update_factory(session: AsyncSession = Depends(get_session)) -> UpdateLlmModelUseCase:
        return UpdateLlmModelUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            llm_provider=llm_provider,
        )

    def deactivate_factory(session: AsyncSession = Depends(get_session)) -> DeactivateLlmModelUseCase:
        return DeactivateLlmModelUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            llm_provider=llm_provider,
        )

    def get_factory(session: AsyncSession = Depends(get_session)) -> GetLlmModelUseCase:
        return GetLlmModelUseCase(repository=_make_repo(session), logger=app_logger)

    def list_factory(session: AsyncSession = Depends(get_session)) -> ListLlmModelsUseCase:
        return ListLlmModelsUseCase(repository=_make_repo(session), logger=app_logger)

    # M4: UpdateLlmModelPricingUseCase — cost_calculator 의무 invalidate
    def update_pricing_factory(
        session: AsyncSession = Depends(get_session),
    ) -> UpdateLlmModelPricingUseCase:
        if cost_calculator is None:
            raise RuntimeError(
                "CostCalculator must be wired into create_llm_model_factories for pricing PATCH"
            )
        return UpdateLlmModelPricingUseCase(
            repository=_make_repo(session),
            cost_calculator=cost_calculator,
            logger=app_logger,
            llm_provider=llm_provider,
        )

    return (
        create_factory,
        update_factory,
        deactivate_factory,
        get_factory,
        list_factory,
        update_pricing_factory,
    )


def create_admin_dashboard_factories():
    """admin-dashboard DI factories (Design D2/D5).

    집계 유스케이스는 request-scope 세션, 헬스 어댑터는 app-scope 클라이언트 1회 생성.
    """
    app_logger = get_app_logger()

    def stats_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetDashboardStatsUseCase:
        return GetDashboardStatsUseCase(
            repo=SqlAlchemyDashboardAggregationRepository(session, app_logger),
            logger=app_logger,
        )

    def kb_breakdown_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetKbBreakdownUseCase:
        return GetKbBreakdownUseCase(
            repo=SqlAlchemyDashboardAggregationRepository(session, app_logger),
            logger=app_logger,
        )

    def recent_documents_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetRecentDocumentsUseCase:
        return GetRecentDocumentsUseCase(
            repo=SqlAlchemyDashboardAggregationRepository(session, app_logger),
            logger=app_logger,
        )

    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    es_client = ElasticsearchClient.from_config(
        ElasticsearchConfig(
            ES_HOST=settings.es_host,
            ES_PORT=settings.es_port,
            ES_SCHEME=settings.es_scheme,
        )
    )
    health_adapter = StorageHealthAdapter(
        checks={
            "mysql": build_mysql_check(get_engine()),
            "qdrant": build_qdrant_check(qdrant_client),
            "elasticsearch": build_es_check(es_client),
        },
        logger=app_logger,
    )

    def health_factory() -> StorageHealthCheckUseCase:
        return StorageHealthCheckUseCase(port=health_adapter, logger=app_logger)

    return (
        stats_factory,
        kb_breakdown_factory,
        recent_documents_factory,
        health_factory,
    )


def create_agent_run_factories():
    """Return per-request DI factories for Agent Run Observability (M4).

    Repository session은 request scope이므로 UsageAggregator도 request scope로 생성.
    Aggregator는 trivial wrapper이므로 새 인스턴스 비용 0.
    """
    app_logger = get_app_logger()

    def _aggregator(session: AsyncSession) -> UsageAggregator:
        return UsageAggregator(llm_call_repo=SqlAlchemyLlmCallRepository(session))

    def run_detail_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetRunDetailUseCase:
        return GetRunDetailUseCase(
            agent_run_repo=SqlAlchemyAgentRunRepository(session),
            llm_call_repo=SqlAlchemyLlmCallRepository(session),
            logger=app_logger,
        )

    def by_user_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetUsageByUserUseCase:
        return GetUsageByUserUseCase(aggregator=_aggregator(session))

    def by_llm_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetUsageByLlmUseCase:
        return GetUsageByLlmUseCase(aggregator=_aggregator(session))

    def by_node_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetUsageByNodeUseCase:
        return GetUsageByNodeUseCase(aggregator=_aggregator(session))

    def me_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetUsageMeUseCase:
        return GetUsageMeUseCase(aggregator=_aggregator(session))

    # ── M5: admin run list ──
    def list_runs_factory(
        session: AsyncSession = Depends(get_session),
    ) -> ListRunsUseCase:
        return ListRunsUseCase(
            agent_run_repo=SqlAlchemyAgentRunRepository(session),
            logger=app_logger,
        )

    # ── M5 dashboard: 4 new factories ──
    def list_my_runs_factory(
        session: AsyncSession = Depends(get_session),
    ) -> ListMyRunsUseCase:
        list_runs_uc = ListRunsUseCase(
            agent_run_repo=SqlAlchemyAgentRunRepository(session),
            logger=app_logger,
        )
        return ListMyRunsUseCase(list_runs_use_case=list_runs_uc)

    def usage_summary_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetUsageSummaryUseCase:
        return GetUsageSummaryUseCase(aggregator=_aggregator(session))

    def usage_timeseries_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetUsageTimeseriesUseCase:
        return GetUsageTimeseriesUseCase(aggregator=_aggregator(session))

    def my_usage_timeseries_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetMyUsageTimeseriesUseCase:
        return GetMyUsageTimeseriesUseCase(aggregator=_aggregator(session))

    # ── retrieval-observability §4.6: 메시지 기준 검색 근거 조회 ──
    def message_retrievals_factory(
        session: AsyncSession = Depends(get_session),
    ) -> GetMessageRetrievalsUseCase:
        return GetMessageRetrievalsUseCase(
            agent_run_repo=SqlAlchemyAgentRunRepository(session),
            message_repo=SQLAlchemyConversationMessageRepository(session),
            logger=app_logger,
        )

    return (
        run_detail_factory,
        by_user_factory,
        by_llm_factory,
        by_node_factory,
        me_factory,
        list_runs_factory,            # ★ M5
        list_my_runs_factory,         # ★ M5 dashboard
        usage_summary_factory,        # ★ M5 dashboard
        usage_timeseries_factory,     # ★ M5 dashboard
        my_usage_timeseries_factory,  # ★ M5 dashboard
        message_retrievals_factory,   # ★ retrieval-observability
    )


def create_embedding_model_factories():
    """Return per-request DI factories for Embedding Model Registry."""
    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession):
        return EmbeddingModelRepository(session=session, logger=app_logger)

    def list_factory(
        session: AsyncSession = Depends(get_session),
    ) -> ListEmbeddingModelsUseCase:
        return ListEmbeddingModelsUseCase(
            repository=_make_repo(session), logger=app_logger
        )

    return (list_factory,)


async def seed_embedding_models_on_startup() -> None:
    app_logger = get_app_logger()
    request_id = str(uuid.uuid4())
    factory = get_session_factory()
    try:
        async with factory() as session:
            async with session.begin():
                repo = EmbeddingModelRepository(
                    session=session, logger=app_logger
                )
                await seed_default_embedding_models(
                    repo, app_logger, request_id
                )
    except Exception as e:
        app_logger.warning(
            "Embedding model seeding skipped",
            request_id=request_id,
            error=str(e),
        )


async def seed_llm_models_on_startup() -> None:
    """서비스 기동 시 기본 LLM 모델 3개 등록 (중복 스킵).

    DB-001 §10.2: get_session_factory()로 단발성 세션 획득 (lifespan 1회만 실행).
    """
    app_logger = get_app_logger()
    request_id = str(uuid.uuid4())
    factory = get_session_factory()
    try:
        async with factory() as session:
            async with session.begin():
                repo = LlmModelRepository(session=session, logger=app_logger)
                await seed_default_models(repo, app_logger, request_id)
    except Exception as e:
        app_logger.warning(
            "LLM model seeding skipped",
            request_id=request_id,
            error=str(e),
        )


async def _load_default_llm_model() -> LlmModel:
    """DB에서 is_default=True 모델을 조회한다."""
    app_logger = get_app_logger()
    request_id = str(uuid.uuid4())
    factory = get_session_factory()
    async with factory() as session:
        repo = LlmModelRepository(session=session, logger=app_logger)
        default = await repo.find_default(request_id)
        if default is None:
            app_logger.warning(
                "기본 LLM 모델 미설정, 환경변수 폴백 사용",
                request_id=request_id,
            )
            return LlmModel(
                id="fallback",
                provider="openai",
                model_name=settings.openai_llm_model,
                display_name="Fallback",
                description=None,
                api_key_env="OPENAI_API_KEY",
                max_tokens=128000,
                is_active=True,
                is_default=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        return default


def create_history_use_case_factory():
    """Return a per-request factory for ConversationHistoryUseCase.

    DB-001 §10.2: 세션은 Depends(get_session) 주입.
    """
    app_logger = get_app_logger()

    def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> ConversationHistoryUseCase:
        repo = SQLAlchemyConversationMessageRepository(session)
        agent_repo = MiddlewareAgentRepository(session=session)
        return ConversationHistoryUseCase(
            repo=repo, logger=app_logger, agent_repo=agent_repo
        )

    return _factory


def _make_analysis_snapshot_policy() -> AnalysisSnapshotPolicy:
    """analysis-data-continuity D8: settings 기반 스냅샷 정책 (하드코딩 금지)."""
    return AnalysisSnapshotPolicy(
        item_max_chars=settings.analysis_snapshot_item_max_chars,
        total_max_chars=settings.analysis_snapshot_total_max_chars,
        retention=settings.analysis_snapshot_retention,
        raw_source_max_chars=settings.analysis_snapshot_raw_source_max_chars,
        raw_source_total_max_chars=settings.analysis_snapshot_raw_source_total_max_chars,
        raw_source_max_rows=settings.analysis_snapshot_raw_source_max_rows,
    )


def _analysis_snapshot_excluded_tools() -> frozenset[str]:
    """analysis-data-continuity D8: General Chat 수집 제외 도구 (콤마 구분 설정)."""
    return frozenset(
        t.strip()
        for t in settings.analysis_snapshot_excluded_tools.split(",")
        if t.strip()
    )


def _empty_result_patterns() -> tuple[str, ...]:
    """supervisor-early-finish-fix D-07: 빈 결과 판정 보조 문구 (콤마 구분 설정).

    application/domain은 config를 직접 import하지 않는다 — 여기서 정규화해
    WorkflowCompiler 생성자로 주입한다 (agent_timezone과 동일 규약).
    """
    return tuple(
        p.strip()
        for p in settings.empty_result_patterns.split(",")
        if p.strip()
    )


# retrieval-observability §4.5: RunTracker lazy singleton.
# agent_run(create_agent_builder_factories)과 general_chat factory가 동일 인스턴스를
# 공유한다 — 상태 없는 파사드(session_factory만 보유)라 공유 안전.
_run_tracker_singleton: RunTracker | None = None
_tracker_cost_calculator: CostCalculator | None = None


def get_run_tracker() -> RunTracker:
    global _run_tracker_singleton, _tracker_cost_calculator
    if _run_tracker_singleton is None:
        app_logger = get_app_logger()
        from src.infrastructure.llm_model.session_scoped_llm_model_repository import (
            SessionScopedLlmModelRepository,
        )

        scoped_llm_model_repo = SessionScopedLlmModelRepository(
            session_factory=get_session_factory(),
            logger=app_logger,
        )
        _tracker_cost_calculator = CostCalculator(
            llm_model_repo=scoped_llm_model_repo,
            config=RunObservabilityConfig(),
        )
        _run_tracker_singleton = RunTracker(
            session_factory=get_session_factory(),
            cost_calculator=_tracker_cost_calculator,
            model_name_resolver=ModelNameResolver(
                llm_model_repo=scoped_llm_model_repo,
                logger=app_logger,
            ),
            logger=app_logger,
        )
    return _run_tracker_singleton


def get_tracker_cost_calculator() -> CostCalculator:
    """M4 가격 PATCH invalidate 공유용 — tracker와 동일 CostCalculator."""
    get_run_tracker()
    return _tracker_cost_calculator


# agent-memory §3-4: 주입용 assembler lazy singleton.
# 상태 없는 파사드(session_factory만 보유)라 앱 전역 공유 안전 — RunTracker 선례.
_memory_assembler_singleton: MemoryContextAssembler | None = None


def get_memory_assembler() -> MemoryContextAssembler:
    global _memory_assembler_singleton
    if _memory_assembler_singleton is None:
        _memory_assembler_singleton = MemoryContextAssembler(
            session_factory=get_session_factory(),
            logger=get_app_logger(),
            token_cap=settings.memory_inject_token_cap,
        )
    return _memory_assembler_singleton


def create_memory_factories():
    """Return per-request DI factory for Memory CRUD use case (agent-memory)."""
    app_logger = get_app_logger()

    def crud_factory(session: AsyncSession = Depends(get_session)):
        return MemoryCrudUseCase(
            memory_repo=MemoryRepository(session=session, logger=app_logger),
            logger=app_logger,
            max_active_per_user=settings.memory_max_active_per_user,
            max_pending_per_user=settings.memory_max_pending_per_user,
            max_active_per_department=settings.memory_max_active_per_department,
        )

    return crud_factory


# agent-memory-extraction §3-4: 추출 서비스 lazy singleton.
# enabled 판정은 서비스 내부(kickoff no-op) — off여도 주입은 항상(코드 경로 단일화).
_memory_extraction_singleton: MemoryExtractionService | None = None


def get_memory_extraction_service() -> MemoryExtractionService:
    global _memory_extraction_singleton
    if _memory_extraction_singleton is None:
        app_logger = get_app_logger()
        extractor = MemoryCandidateExtractor.from_openai(
            model_name=settings.memory_extraction_model_name,
            api_key=settings.openai_api_key,
            logger=app_logger,
            llm_provider=get_utility_llm_provider(),
        )
        _memory_extraction_singleton = MemoryExtractionService(
            session_factory=get_session_factory(),
            extractor=extractor,
            logger=app_logger,
            enabled=settings.memory_extraction_enabled,
            max_per_turn=settings.memory_extraction_max_per_turn,
            pending_cap=settings.memory_max_pending_per_user,
            feedback_enabled=settings.eval_feedback_extraction_enabled,
        )
    return _memory_extraction_singleton


# wiki-feedback-loop §3-6: 위키 환류 서비스 lazy singleton.
# enabled 판정은 서비스 내부(kickoff no-op) — off여도 주입은 항상(코드 경로 단일화).
_feedback_wiki_singleton: FeedbackWikiService | None = None


def get_feedback_wiki_service() -> FeedbackWikiService:
    global _feedback_wiki_singleton
    if _feedback_wiki_singleton is None:
        app_logger = get_app_logger()
        distiller = FeedbackWikiDistiller.from_openai(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
            llm_provider=get_utility_llm_provider(),
        )
        _feedback_wiki_singleton = FeedbackWikiService(
            session_factory=get_session_factory(),
            distiller=distiller,
            logger=app_logger,
            enabled=settings.wiki_feedback_draft_enabled,
            reinforce_enabled=settings.wiki_feedback_reinforce_enabled,
        )
    return _feedback_wiki_singleton


# builtin-middleware D6/D7: MiddlewareProvider lazy singleton.
# 컴파일러/General Chat(앱 싱글톤)이 공유 — 세션은 session-scoped 어댑터가
# 매 호출 새로 연다 (SessionScopedDocumentTemplateRepository 패턴).
_middleware_provider_singleton = None


def get_middleware_provider():
    global _middleware_provider_singleton
    if _middleware_provider_singleton is None:
        from src.application.middleware.middleware_provider import (
            MiddlewareProvider,
        )
        from src.infrastructure.llm_model.session_scoped_llm_model_repository import (
            SessionScopedLlmModelRepository,
        )
        from src.infrastructure.middleware.session_scoped import (
            SessionScopedAgentMiddlewareRepository,
            SessionScopedMiddlewareCatalogRepository,
        )

        app_logger = get_app_logger()
        _middleware_provider_singleton = MiddlewareProvider(
            catalog_repo=SessionScopedMiddlewareCatalogRepository(
                session_factory=get_session_factory(), logger=app_logger
            ),
            agent_middleware_repo=SessionScopedAgentMiddlewareRepository(
                session_factory=get_session_factory(), logger=app_logger
            ),
            llm_model_repo=SessionScopedLlmModelRepository(
                session_factory=get_session_factory(), logger=app_logger
            ),
            llm_factory=_llm_factory,
            logger=app_logger,
        )
    return _middleware_provider_singleton


def create_general_chat_use_case_factory():
    """Return a per-request factory for GeneralChatUseCase.

    DB-001 §10.1/§10.2: message/summary/mcp 는 동일 세션 공유, Depends(get_session) 주입.
    """
    app_logger = get_app_logger()

    async def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> GeneralChatUseCase:
        message_repo = SQLAlchemyConversationMessageRepository(session)
        summary_repo = SQLAlchemyConversationSummaryRepository(session)
        summarizer = LangChainSummarizer(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
        )
        policy = SummarizationPolicy()

        # 도구: TavilySearchTool
        tavily_tool = TavilySearchTool()

        # 도구: InternalDocumentSearchTool (HybridSearch 재사용)
        # retrieval-observability §4.5: tracker 주입 → general_chat 검색도
        # ai_retrieval_source에 영속화 (RunContext는 UseCase가 세팅).
        hybrid_search_uc = get_configured_hybrid_search_use_case()
        internal_doc_tool = InternalDocumentSearchTool(
            hybrid_search_use_case=hybrid_search_uc,
            top_k=5,
            request_id="",
            tracker=get_run_tracker(),
            logger=app_logger,
            config=RunObservabilityConfig(),
        )

        # 도구: MCP Tools (LoadMCPToolsUseCase via DB) — 동일 세션 공유
        mcp_repo = MCPServerRepository(
            session=session, logger=app_logger, cipher=_mcp_cipher()
        )
        mcp_loader = MCPToolLoader(logger=app_logger)
        load_mcp_uc = LoadMCPToolsUseCase(
            repository=mcp_repo,
            mcp_tool_loader=mcp_loader,
            logger=app_logger,
        )

        tool_builder = ChatToolBuilder(
            tavily_tool=tavily_tool,
            internal_doc_tool=internal_doc_tool,
            mcp_cache=MCPToolCache,
            load_mcp_use_case=load_mcp_uc,
            logger=app_logger,
        )

        # chart-builder DI (Design §6): 추출용 LLM 1개를 분류기/빌더가 공유.
        viz_llm = _llm_factory.create(_default_llm_model, temperature=0)
        chart_builder = LangChainChartBuilder(
            llm=viz_llm,
            logger=app_logger,
            style_policy=ChartStylePolicy(),
            max_count=settings.chart_max_count,
        )
        viz_classifier = LangChainVisualizationClassifier(viz_llm)
        # chart-context-continuity §3.8: 차트 편집 변환기 — viz_llm 공유.
        chart_transformer = LangChainChartTransformer(
            llm=viz_llm,
            logger=app_logger,
            style_policy=ChartStylePolicy(),
        )

        return GeneralChatUseCase(
            chat_tool_builder=tool_builder,
            message_repo=message_repo,
            summary_repo=summary_repo,
            summarizer=summarizer,
            summarization_policy=policy,
            logger=app_logger,
            llm_factory=_llm_factory,
            llm_model=_default_llm_model,
            # AGENT-OBS-001 fix 미러링: 메시지 별도 세션 즉시 commit —
            # tracker attach의 FK 검사가 요청 세션 미커밋 row에 1205로 막히지 않게.
            session_factory=get_session_factory(),
            viz_policy=VisualizationRoutingPolicy(),
            viz_classifier=viz_classifier,
            chart_builder=chart_builder,
            chart_transformer=chart_transformer,
            snapshot_policy=_make_analysis_snapshot_policy(),
            snapshot_excluded_tools=_analysis_snapshot_excluded_tools(),
            tracker=get_run_tracker(),
            memory_assembler=get_memory_assembler(),
            memory_extractor=get_memory_extraction_service(),
            # builtin-middleware D7: 카탈로그 빌트인 ∪ enforced 적용
            middleware_provider=get_middleware_provider(),
            # tool-recommender module-4: 킬스위치 off면 None → 선별 비활성
            tool_filter=_build_tool_filter(),
            # ★ runtime-datetime-context D3: [현재 날짜] 블록 기준 타임존
            agent_timezone=settings.agent_timezone,
        )

    return _factory


# search-node-query-pipeline: provider별 API 키 환경변수 매핑.
# LLMFactory는 provider/model_name/api_key_env만 사용한다 (llm_factory.py).
_SEARCH_PIPELINE_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "",  # ollama는 API 키 불필요
}


def _build_tool_selector_llm_model() -> LlmModel | None:
    """settings → 도구 선별용 경량 LlmModel (DB 미등록 인라인 엔티티).

    tool-recommender Design §10.3. provider/model 미설정 시 None.
    """
    provider = settings.tool_selector_provider
    model_name = settings.tool_selector_model_name
    if not provider or not model_name:
        return None
    now = datetime.now()
    return LlmModel(
        id="tool-selector-llm",
        provider=provider,
        model_name=model_name,
        display_name=f"Tool Selector ({model_name})",
        description=None,
        api_key_env=_SEARCH_PIPELINE_API_KEY_ENV.get(provider, "OPENAI_API_KEY"),
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


def _build_tool_filter():
    """도구 선별 어댑터. 킬스위치가 꺼져 있거나 조립 실패 시 None.

    tool-recommender module-4 결선. None이면 GeneralChatUseCase가 선별을
    건너뛰어 기존과 동일하게 전량 바인딩한다 (하위호환).
    """
    if not settings.tool_selector_enabled:
        return None
    logger = get_app_logger()
    llm_model = _build_tool_selector_llm_model()
    if llm_model is None:
        logger.warning(
            "Tool selector enabled but provider/model unset — disabling"
        )
        return None
    try:
        selector = LLMToolSelector(
            llm_factory=_llm_factory,
            llm_model=llm_model,
            logger=logger,
            top_k=settings.tool_selector_top_k,
            timeout_sec=settings.tool_selector_timeout_sec,
        )
        return LangChainToolFilter(selector=selector, logger=logger)
    except Exception as e:
        # 선별은 부가 기능이다 — 조립 실패가 채팅을 막아선 안 된다.
        logger.warning("Tool filter build failed — disabling", exception=e)
        return None


def _build_pipeline_tool_selector(cfg):
    """에이전트 생성 파이프라인용 셀렉터 (agent-create-pipeline D2/§9.3).

    General Chat 의 tool_selector_enabled 킬스위치와 **독립**이다 (Plan O6) —
    빌더 문맥 파라미터(top_k·timeout)만 파이프라인 config 에서 받는다.
    LLM 미구성·조립 실패 시 NullToolSelector 로 강하 — 파이프라인은
    steps.tools=degraded 로 진행한다 (라우터 미등록 낙하가 아니다: 추천이
    없어도 지정 도구만으로 "쓸 수 있는 결과"가 존재하기 때문).
    """
    from src.infrastructure.agent_create_pipeline.adapters import NullToolSelector

    logger = get_app_logger()
    llm_model = _build_tool_selector_llm_model()
    if llm_model is None:
        logger.warning(
            "Pipeline tool selector provider/model unset — null selector"
        )
        return NullToolSelector()
    try:
        return LLMToolSelector(
            llm_factory=_llm_factory,
            llm_model=llm_model,
            logger=logger,
            top_k=cfg.AGENT_PIPELINE_SELECTOR_TOP_K,
            timeout_sec=cfg.AGENT_PIPELINE_SELECTOR_TIMEOUT_SEC,
        )
    except Exception as e:
        logger.warning(
            "Pipeline tool selector build failed — null selector", exception=e
        )
        return NullToolSelector()


def _build_search_pipeline_llm_model() -> LlmModel | None:
    """settings → search 파이프라인용 경량 LlmModel (DB 미등록 인라인 엔티티).

    provider/model 미설정 시 None → WorkflowCompiler가 per-run LLM 사용 (D3).
    API 키 부재 등 생성 실패는 compile 시점 fallback이 흡수한다.
    """
    provider = settings.search_pipeline_provider
    model_name = settings.search_pipeline_model_name
    if not provider or not model_name:
        return None
    now = datetime.now()
    return LlmModel(
        id="search-pipeline-llm",
        provider=provider,
        model_name=model_name,
        display_name=f"Search Pipeline ({model_name})",
        description=None,
        api_key_env=_SEARCH_PIPELINE_API_KEY_ENV.get(provider, "OPENAI_API_KEY"),
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


def create_agent_builder_factories():
    """Return per-request DI factories for Agent Builder use cases."""
    app_logger = get_app_logger()

    # AGENT-OBS-001 (M1·M4): RunTracker 등 관측성 싱글톤은 ToolFactory보다 먼저 생성
    # M4: ToolFactory에 tracker 주입 → InternalDocumentSearchTool이 record_retrieval 호출
    # retrieval-observability §4.5: general_chat factory와 공유하는 lazy singleton 사용
    _obs_config = RunObservabilityConfig()
    run_tracker = get_run_tracker()
    _cost_calculator = get_tracker_cost_calculator()

    # LLM-WIKI-001 Step6: 승인 위키 우선 검색 어댑터(run-scoped 세션). use_wiki_first=True 도구에만 적용.
    from src.application.wiki.run_scoped_wiki_search import RunScopedWikiSearch

    _wiki_collection = getattr(settings, "wiki_collection_name", "wiki_knowledge")
    _wiki_embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
    _wiki_qdrant = AsyncQdrantClient(
        host=settings.qdrant_host, port=settings.qdrant_port
    )
    _wiki_vector_store = QdrantVectorStore(
        client=_wiki_qdrant,
        embedding=_wiki_embedding,
        collection_name=_wiki_collection,
    )

    def _wiki_repo_builder(session: AsyncSession):
        return WikiArticleRepository(
            session=session,
            logger=app_logger,
            embedding=_wiki_embedding,
            vector_store=_wiki_vector_store,
            collection_name=_wiki_collection,
        )

    _wiki_search = RunScopedWikiSearch(
        session_factory=get_session_factory(),
        repo_builder=_wiki_repo_builder,
        inner_search_getter=get_configured_hybrid_search_use_case,
        logger=app_logger,
    )

    # wiki-agentic-navigation: wiki_read 도구·목차 블록 배선 (기존 repo_builder 재사용)
    from src.application.wiki.toc_provider import WikiTocProvider
    from src.infrastructure.wiki.folder_summary_repository import (
        MySQLWikiFolderSummaryRepository,
    )

    # wiki-folder-summaries: 폴더 요약 저장소 빌더 (wiki_list 도구·폴더 지도 공용)
    def _wiki_folder_repo_builder(session: AsyncSession):
        return MySQLWikiFolderSummaryRepository(session=session, logger=app_logger)

    _wiki_toc_provider = WikiTocProvider(
        session_factory=get_session_factory(),
        repo_builder=_wiki_repo_builder,
        max_items=settings.wiki_toc_max_items,
        max_bytes=settings.wiki_toc_max_bytes,
        logger=app_logger,
        folder_repo_builder=_wiki_folder_repo_builder,
        folder_enabled=settings.wiki_folder_summaries_enabled,
        folder_threshold=settings.wiki_folder_mode_threshold,
        excerpt_chars=settings.wiki_toc_excerpt_chars,
    )

    # MCP 워커(tool_id="mcp_{uuid}") 실행 의존.
    # ToolFactory/DocumentConversionAdapter는 앱 싱글톤이라 per-request 세션을
    # 들 수 없다 — 매 호출마다 세션을 여는 세션 스코프 저장소를 공유한다.
    _mcp_tool_loader = MCPToolLoader(logger=app_logger)
    _mcp_runtime_repo = SessionScopedMcpServerRepository(
        session_factory=get_session_factory(),
        logger=app_logger,
        cipher=_mcp_cipher(),
    )

    tool_factory = ToolFactory(
        logger=app_logger,
        hybrid_search_use_case_getter=get_configured_hybrid_search_use_case,
        # MCP 서버를 워커로 붙인 에이전트 실행 경로.
        mcp_tool_loader=_mcp_tool_loader,
        mcp_repository=_mcp_runtime_repo,
        tavily_api_key=os.environ.get("TAVILY_API_KEY"),
        tracker=run_tracker,                # ★ M4: RAG retrieval 영속화
        run_observability_config=_obs_config,
        wiki_search=_wiki_search,           # ★ LLM-WIKI-001 Step6
        # ★ rag-routed-integration D2: use_routed_search 에이전트용 라우팅 검색
        routed_retrieval_getter=get_configured_routed_retrieval_use_case,
        # ★ wiki-agentic-navigation: wiki_read 도구 per-call 세션 의존
        wiki_session_factory=get_session_factory(),
        wiki_repo_builder=_wiki_repo_builder,
        # ★ wiki-folder-summaries: wiki_list 도구용 폴더 요약 저장소
        wiki_folder_repo_builder=_wiki_folder_repo_builder,
    )
    # document-template-extractor Design §6: 합성 노드 의존(싱글톤).
    # 컴파일러/컴포저는 앱 싱글톤이라 per-request 세션 대신 session-scoped 어댑터 사용.
    _dt_runtime_template_repo = SessionScopedDocumentTemplateRepository(
        session_factory=get_session_factory(), logger=app_logger,
    )
    # doc-generator §4-6: 생성 노드 의존(싱글톤) — 추출기와 동일 패턴.
    from src.infrastructure.document_generator.generation_type_repository import (
        DocumentGenerationTypeRepository,
        SessionScopedDocumentGenerationTypeRepository,
    )
    from src.infrastructure.document_generator.generator import DocumentGenerator
    _dg_runtime_type_repo = SessionScopedDocumentGenerationTypeRepository(
        session_factory=get_session_factory(), logger=app_logger,
    )
    _dt_conversion_adapter = DocumentConversionAdapter(
        mcp_tool_loader=_mcp_tool_loader,
        mcp_repository=_mcp_runtime_repo,
        logger=app_logger,
        # fix-doc-generator-korean-font §11.1 — generator·composer 가 이 인스턴스를
        # 공유하므로, 여기 한 번의 주입으로 두 경로가 모두 커버된다.
        font_embedder=create_html_font_embedder(settings, app_logger),
    )
    _dt_composer = DocumentComposer(
        conversion_adapter=_dt_conversion_adapter,
        attachment_store=_attachment_store or create_attachment_store(),
        logger=app_logger,
    )
    _dt_archiver = SourceFileArchiver(
        attachment_store=_attachment_store or create_attachment_store(),
        archive_dir=_document_template_archive_dir(),
        logger=app_logger,
    )
    # doc-generator §4-6: 변환 어댑터·첨부 저장소는 기존 인스턴스 공유 (신규 생성 금지).
    _dg_generator = DocumentGenerator(
        conversion_adapter=_dt_conversion_adapter,
        attachment_store=_attachment_store or create_attachment_store(),
        logger=app_logger,
        default_html_to_doc_tool_id=settings.document_generator_html_to_doc_tool_id,
        fallback_html_to_doc_tool_id=settings.document_extractor_html_to_doc_tool_id,
        llm_input_max_chars=settings.document_generator_llm_input_max_chars,
    )

    # excel-generator-node §2.1: 엑셀 생성 노드 의존 (문서생성기와 저장소 공유).
    from src.infrastructure.excel.pandas_excel_parser import PandasExcelParser
    from src.infrastructure.excel_export.pandas_excel_exporter import (
        PandasExcelExporter as _EgExporter,
    )
    from src.infrastructure.excel_generator.generator import ExcelGenerator

    _eg_generator = ExcelGenerator(
        exporter=_EgExporter(),
        attachment_store=_attachment_store or create_attachment_store(),
        logger=app_logger,
        excel_parser=PandasExcelParser(),
        # excel-generator-node Act-1 (D-5): 문서생성기와 동일 상한 설정 공유
        llm_input_max_chars=settings.document_generator_llm_input_max_chars,
    )

    # golden-sample-blueprint §2.1: 발표자료 생성 노드 의존 (문서생성기와 어댑터·저장소 공유)
    from src.api.blueprint_di import build_presentation_generation_use_case
    from src.infrastructure.blueprint.repository import (
        SessionScopedBlueprintRepository,
    )

    _bp_runtime_repo = SessionScopedBlueprintRepository(
        session_factory=get_session_factory(), logger=app_logger,
    )
    _bp_presentation_generator = build_presentation_generation_use_case(
        conversion_adapter=_dt_conversion_adapter,
        attachment_store=_attachment_store or create_attachment_store(),
        logger=app_logger,
        input_max_chars=settings.document_generator_llm_input_max_chars,
    )

    # ★ mcp-tool-category-routing §5 D-08: 도구 카테고리·호출 상한 조회.
    # 컴파일러는 앱 싱글톤이라 per-request 세션이 없다 — 세션 스코프 어댑터 주입.
    from src.infrastructure.tool_catalog.session_scoped import (
        SessionScopedToolCatalogRepository,
    )

    _tool_catalog_runtime_repo = SessionScopedToolCatalogRepository(
        session_factory=get_session_factory(), logger=app_logger,
    )

    workflow_compiler = WorkflowCompiler(
        tool_factory=tool_factory, llm_factory=_llm_factory, logger=app_logger,
        hooks=DefaultHooks(),
        # ★ mcp-tool-category-routing §5 D-01/D-09: 카테고리 해석 + 호출 상한
        tool_catalog_repository=_tool_catalog_runtime_repo,
        excel_analysis_workflow_getter=get_configured_excel_analysis_workflow,
        chart_max_count=settings.chart_max_count,
        pipeline_llm_model=_build_search_pipeline_llm_model(),
        search_compress_threshold=settings.search_compress_threshold,
        # deep-search-pipeline FR-13: 기본 legacy — 배포 시 동작 무변화.
        search_pipeline_mode=settings.search_pipeline_mode,
        document_template_repository=_dt_runtime_template_repo,
        document_composer=_dt_composer,
        # ★ doc-generator §4-4: 생성 노드 의존
        document_generation_type_repository=_dg_runtime_type_repo,
        document_generator=_dg_generator,
        # ★ golden-sample-blueprint: 발표자료 생성 노드 의존
        presentation_generator=_bp_presentation_generator,
        blueprint_repository=_bp_runtime_repo,
        # ★ excel-generator-node §2.1: 엑셀 생성 노드 의존
        excel_generator=_eg_generator,
        # ★ wiki-agentic-navigation D1: wiki_read 에이전트 목차 블록 주입
        wiki_toc_provider=_wiki_toc_provider,
        # ★ builtin-middleware D6: 스냅샷 ∪ enforced 미들웨어 조립
        middleware_provider=get_middleware_provider(),
        # ★ runtime-datetime-context D3: [현재 날짜] 블록 기준 타임존
        agent_timezone=settings.agent_timezone,
        # ★ supervisor-early-finish-fix D-07: 빈 결과 판정 보조 문구
        empty_result_patterns=_empty_result_patterns(),
    )

    # DB-001 §10.2: session 은 Depends(get_session) 으로 주입.
    def _make_repo(session: AsyncSession):
        return AgentDefinitionRepository(session=session, logger=app_logger)

    def _make_agent_skill_repo(session: AsyncSession):
        return AgentSkillRepository(session=session, logger=app_logger)

    def _make_skill_sync(session: AsyncSession):
        from src.application.agent_skill.sync_agent_skills_use_case import (
            SyncAgentSkillsUseCase,
        )
        from src.infrastructure.skill_builder.skill_repository import SkillRepository
        return SyncAgentSkillsUseCase(
            agent_skill_repo=_make_agent_skill_repo(session),
            skill_repo=SkillRepository(session=session, logger=app_logger),
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            logger=app_logger,
        )

    def _make_llm_model_repo(session: AsyncSession):
        return LlmModelRepository(session=session, logger=app_logger)

    def _make_perm_repo(session: AsyncSession):
        from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
        return CollectionPermissionRepository(session, app_logger)

    def _make_document_template_repo(session: AsyncSession):
        return DocumentTemplateRepository(session=session, logger=app_logger)

    def _make_document_generation_type_repo(session: AsyncSession):
        return DocumentGenerationTypeRepository(session=session, logger=app_logger)

    def _make_kb_repo(session: AsyncSession):
        from src.infrastructure.knowledge_base.repository import (
            KnowledgeBaseRepository,
        )
        return KnowledgeBaseRepository(session, app_logger)

    def _make_middleware_catalog_repo(session: AsyncSession):
        from src.infrastructure.middleware.repository import (
            MiddlewareCatalogRepository,
        )
        return MiddlewareCatalogRepository(session=session, logger=app_logger)

    def _make_agent_middleware_repo(session: AsyncSession):
        from src.infrastructure.middleware.repository import (
            AgentMiddlewareRepository,
        )
        return AgentMiddlewareRepository(session=session, logger=app_logger)

    def _make_prompt_version_reader(session: AsyncSession):
        from src.infrastructure.prompt_composer.repository import PromptRepository

        return PromptRepository(session)

    def create_uc_factory(session: AsyncSession = Depends(get_session)):
        return CreateAgentUseCase(
            repository=_make_repo(session),
            llm_model_repository=_make_llm_model_repo(session),
            perm_repo=_make_perm_repo(session),
            logger=app_logger,
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            skill_sync=_make_skill_sync(session),
            document_template_repo=_make_document_template_repo(session),
            source_archiver=_dt_archiver,
            max_template_slots=settings.document_extractor_max_slots,
            # doc-generator §4-3: 문서 유형 저장 (동일 세션 편승)
            document_generation_type_repo=_make_document_generation_type_repo(
                session
            ),
            max_generation_sections=settings.document_generator_max_sections,
            # nl-agent-composer FR-08: mcp_* tool_id 메타 해석
            mcp_server_repo=MCPServerRepository(
                session=session, logger=app_logger, cipher=_mcp_cipher()
            ),
            # kb-rag-filter D7: kb_id 검증·scope clamp·컬렉션 고정
            kb_repo=_make_kb_repo(session),
            # builtin-tools D5: 빌트인 주입 (동일 세션 — 세션 분리 금지 규칙)
            tool_catalog_repo=ToolCatalogRepository(
                session=session, logger=app_logger
            ),
            # builtin-middleware D5: 빌트인 미들웨어 스냅샷 (동일 세션)
            middleware_catalog_repo=_make_middleware_catalog_repo(session),
            # prompt-fallback-visibility module-1: degraded 프롬프트 저장 게이트.
            # 동일 세션 편승 — DB-001 "한 UseCase 안에서 repository 별 서로 다른
            # 세션 사용 금지". 조회 전용이라 트랜잭션에 쓰기를 더하지 않는다.
            prompt_version_reader=_make_prompt_version_reader(session),
        )

    def update_uc_factory(session: AsyncSession = Depends(get_session)):
        return UpdateAgentUseCase(
            repository=_make_repo(session),
            perm_repo=_make_perm_repo(session),
            logger=app_logger,
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            skill_sync=_make_skill_sync(session),
            document_template_repo=_make_document_template_repo(session),
            source_archiver=_dt_archiver,
            max_template_slots=settings.document_extractor_max_slots,
            # doc-generator §4-3: 문서 유형 교체 (동일 세션 편승)
            document_generation_type_repo=_make_document_generation_type_repo(
                session
            ),
            max_generation_sections=settings.document_generator_max_sections,
            # kb-rag-filter D7: kb_id 워커 scope 검증
            kb_repo=_make_kb_repo(session),
            # agent-builder-edit-mapping FR-5: 모델 변경 검증
            llm_model_repo=_make_llm_model_repo(session),
            # builtin-middleware D5: middleware_types 수정 검증
            middleware_catalog_repo=_make_middleware_catalog_repo(session),
            # agent-update-tool-editing D §2.3: 도구 재구성 — 빌트인 재주입 +
            # mcp_* 메타 해석 (create 와 동일 세션 — 세션 분리 금지 규칙)
            tool_catalog_repo=ToolCatalogRepository(
                session=session, logger=app_logger
            ),
            mcp_server_repo=MCPServerRepository(
                session=session, logger=app_logger, cipher=_mcp_cipher()
            ),
        )

    # agent-schedule Design §6.2: RunAgentUseCase 조립 본문을 함수로 추출해
    # 기존 run 엔드포인트와 스케줄 트리거(TriggerDueSchedulesUseCase)가 공유.
    def _build_run_agent_uc(session: AsyncSession):
        message_repo = SQLAlchemyConversationMessageRepository(session)
        summary_repo = SQLAlchemyConversationSummaryRepository(session)
        summarizer = LangChainSummarizer(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
        )
        policy = SummarizationPolicy()
        return RunAgentUseCase(
            repository=_make_repo(session),
            llm_model_repository=_make_llm_model_repo(session),
            compiler=workflow_compiler,
            logger=app_logger,
            message_repo=message_repo,
            summary_repo=summary_repo,
            summarizer=summarizer,
            policy=policy,
            tracker=run_tracker,
            # AGENT-OBS-001 fix: user_message를 별도 세션 commit해 ai_run FK 락 회피
            session_factory=get_session_factory(),
            # skill-agent-integration Phase A: 부착 Skill instruction 주입
            agent_skill_repo=_make_agent_skill_repo(session),
            # analysis-data-continuity D8: 분석 데이터 스냅샷 영속·재주입
            snapshot_policy=_make_analysis_snapshot_policy(),
            # approval-gate Design §2.1 ④: 게이트 발동 시 승인 요청 적재.
            approval_repo_factory=_make_approval_repo,
            # Check G4: 만료·타임존을 에이전트별 게이트 설정에서 해석
            approval_gate_config_resolver=_resolve_approval_gate_config,
        )

    def run_uc_factory(session: AsyncSession = Depends(get_session)):
        return _build_run_agent_uc(session)

    def get_uc_factory(session: AsyncSession = Depends(get_session)):
        from src.infrastructure.department.department_repository import DepartmentRepository as DeptRepo
        dept_repo = DeptRepo(session=session, logger=app_logger)
        return GetAgentUseCase(
            repository=_make_repo(session),
            dept_repository=dept_repo,
            logger=app_logger,
            agent_skill_repo=_make_agent_skill_repo(session),
            # builtin-middleware D5: edit 폼 프라임용 스냅샷 노출
            agent_middleware_repo=_make_agent_middleware_repo(session),
            # doc-generator FR-12: edit 폼 프리필용 활성 유형 노출
            document_generation_type_repo=_make_document_generation_type_repo(
                session
            ),
        )

    def list_uc_factory(session: AsyncSession = Depends(get_session)):
        dept_repo = DepartmentRepository(session=session, logger=app_logger)
        return ListAgentsUseCase(
            agent_repo=_make_repo(session),
            dept_repo=dept_repo,
            logger=app_logger,
        )

    def _make_sub_repo(session: AsyncSession):
        return SubscriptionRepository(session=session, logger=app_logger)

    def delete_uc_factory(session: AsyncSession = Depends(get_session)):
        return DeleteAgentUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            auto_fork_service=AutoForkService(
                agent_repo=_make_repo(session),
                subscription_repo=_make_sub_repo(session),
                logger=app_logger,
            ),
            document_template_repo=_make_document_template_repo(session),
            # doc-generator: 종속 문서 유형 soft-delete 캐스케이드
            document_generation_type_repo=_make_document_generation_type_repo(
                session
            ),
        )

    def subscribe_uc_factory(session: AsyncSession = Depends(get_session)):
        return SubscribeUseCase(
            agent_repo=_make_repo(session),
            subscription_repo=_make_sub_repo(session),
            logger=app_logger,
        )

    def fork_uc_factory(session: AsyncSession = Depends(get_session)):
        return ForkAgentUseCase(
            agent_repo=_make_repo(session),
            logger=app_logger,
        )

    def list_my_uc_factory(session: AsyncSession = Depends(get_session)):
        return ListMyAgentsUseCase(
            agent_repo=_make_repo(session),
            subscription_repo=_make_sub_repo(session),
            logger=app_logger,
        )

    def list_available_sub_agents_uc_factory(session: AsyncSession = Depends(get_session)):
        from src.application.agent_builder.list_available_sub_agents_use_case import (
            ListAvailableSubAgentsUseCase,
        )
        return ListAvailableSubAgentsUseCase(
            agent_repo=_make_repo(session),
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            logger=app_logger,
        )

    return (
        create_uc_factory, update_uc_factory, run_uc_factory,
        get_uc_factory,
        list_uc_factory, delete_uc_factory,
        subscribe_uc_factory, fork_uc_factory, list_my_uc_factory,
        list_available_sub_agents_uc_factory,
        _cost_calculator,  # M4 — share singleton for pricing PATCH invalidate
        _build_run_agent_uc,  # agent-schedule: 트리거 UC 와 공유
    )


async def _resolve_approval_gate_config(
    session: AsyncSession, agent_id: str, request_id: str
) -> dict:
    """approval-gate 게이트 config 해석 — 적재(RunAgentUseCase)와 승인
    (DecideApprovalUseCase)이 공유하는 **단일 출처** (Check G4).

    카탈로그 default_config ∪ 에이전트 override 를 MergePolicy 로 병합한다.
    게이트가 적용 목록에 없으면 빈 dict (도메인 기본값이 쓰인다).
    """
    from src.domain.middleware.entities import MiddlewareType
    from src.domain.middleware.policies import MiddlewareMergePolicy
    from src.infrastructure.middleware.repository import (
        AgentMiddlewareRepository,
        MiddlewareCatalogRepository,
    )

    logger = get_app_logger()
    catalog = await MiddlewareCatalogRepository(session, logger).list_all(request_id)
    records = await AgentMiddlewareRepository(session, logger).list_by_agent(
        agent_id, request_id
    )
    applied = MiddlewareMergePolicy.merge(records, catalog)
    gate = next(
        (a for a in applied if a.middleware_type is MiddlewareType.APPROVAL_GATE),
        None,
    )
    return dict(gate.config) if gate is not None else {}


def _make_approval_repo(session: AsyncSession):
    """approval_request 리포지토리 팩토리 — RunAgentUseCase 적재용."""
    from src.infrastructure.approval.repository import ApprovalRepository

    return ApprovalRepository(session=session, logger=get_app_logger())


def _build_approval_executor(app_logger):
    """승인된 도구의 실제 집행기 (approval-gate-phase2 Design §2.1, §11.4).

    폴백 집행기를 두지 않는다 — 받을 집행기가 없는 도구는 failed 로 끝나야
    한다 (Plan SC-2). 새 부작용 도구는 ActionExecutorInterface 구현체를
    목록에 더한다.

    서버 등록은 세션 스코프 저장소로 조회한다: 예약 집행 tick 에는 요청
    세션이 없다 (tool-and-mcp §3). cipher 는 런타임 MCP 저장소와 같은 값.
    """
    from src.infrastructure.approval.composite_executor import (
        CompositeActionExecutor,
    )
    from src.infrastructure.approval.mcp_executor import (
        McpActionExecutor,
        build_execution_client,
    )
    from src.infrastructure.config.approval_execution_config import (
        ApprovalExecutionConfig,
    )

    config = ApprovalExecutionConfig()
    timeout = config.get_timeout()
    mcp_executor = McpActionExecutor(
        server_repo=SessionScopedMcpServerRepository(
            session_factory=get_session_factory(),
            logger=app_logger,
            cipher=_mcp_cipher(),
        ),
        client_factory=lambda registration: build_execution_client(
            registration, timeout=timeout, logger=app_logger
        ),
        max_output_chars=config.APPROVAL_EXEC_OUTPUT_MAX_CHARS,
        logger=app_logger,
    )
    return CompositeActionExecutor(executors=[mcp_executor], logger=app_logger)


def create_approval_factories(build_run_agent_uc):
    """approval-gate DI (Design §2.1 / §4).

    승인·거절·목록은 요청 스코프(세션 보유), tick 은 싱글턴(session_factory 만)
    — agent_schedule 트리거와 동형이다 (DB-001).

    resumer 로 RunAgentUseCase 를 넘긴다: 재개 실행은 compile 지식을 가진
    쪽에 두고 approval 은 RunResumerInterface 로만 의존한다 (Design §7.3 v0.2).
    """
    from src.application.approval.decide_use_case import DecideApprovalUseCase
    from src.application.approval.execute_scheduler import (
        ExecuteDueApprovalsUseCase,
    )
    from src.application.approval.list_use_case import ListApprovalsUseCase
    from src.infrastructure.approval.repository import ApprovalRepository
    from src.infrastructure.middleware.repository import (
        AgentMiddlewareRepository,
        MiddlewareCatalogRepository,
    )

    app_logger = get_app_logger()
    executor = _build_approval_executor(app_logger)

    def _approval_repo(session: AsyncSession):
        return ApprovalRepository(session=session, logger=app_logger)

    def _agent_repo(session: AsyncSession):
        return AgentDefinitionRepository(session=session, logger=app_logger)

    class _GateConfigReader:
        """승인 시 execute_after·timezone 을 읽는다.

        적재 쪽과 같은 _resolve_approval_gate_config 에 위임한다 (Check G4) —
        두 곳이 다르게 해석하면 적재 때와 승인 때의 만료·시각이 어긋난다.
        """

        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        async def resolve_gate_config(self, agent_id: str, request_id: str) -> dict:
            return await _resolve_approval_gate_config(
                self._session, agent_id, request_id
            )

    def decide_f(session: AsyncSession = Depends(get_session)):
        return DecideApprovalUseCase(
            approval_repo=_approval_repo(session),
            agent_repo=_agent_repo(session),
            executor=executor,
            gate_config_reader=_GateConfigReader(session),
            logger=app_logger,
            resumer=build_run_agent_uc(session),
        )

    def list_f(session: AsyncSession = Depends(get_session)):
        return ListApprovalsUseCase(
            approval_repo=_approval_repo(session),
            agent_repo=_agent_repo(session),
            logger=app_logger,
        )

    class _TickRunner:
        """tick 싱글턴 — 요청마다 새 세션을 열어 한 트랜잭션으로 처리한다.

        claim_due 의 FOR UPDATE SKIP LOCKED 잠금이 이 트랜잭션 동안 유지돼야
        다중 워커 중복 집행이 막힌다 (Design §2.1 3차 저지선).
        """

        async def run(self, request_id: str):
            session_factory = get_session_factory()
            async with session_factory() as session:
                async with session.begin():
                    uc = ExecuteDueApprovalsUseCase(
                        approval_repo=_approval_repo(session),
                        executor=executor,
                        logger=app_logger,
                        resumer=build_run_agent_uc(session),
                    )
                    return await uc.run(request_id)

    tick_runner = _TickRunner()

    def tick_f():
        return tick_runner

    def approval_repo_factory(session):
        """RunAgentUseCase 적재용 — 세션을 받아 리포지토리를 만든다."""
        return ApprovalRepository(session=session, logger=app_logger)

    def gate_settings_f(session: AsyncSession = Depends(get_session)):
        """approval-gate Check G3 — 에이전트별 게이트 설정 입구."""
        from src.application.approval.gate_settings_use_case import (
            ApprovalGateSettingsUseCase,
        )

        return ApprovalGateSettingsUseCase(
            agent_repo=_agent_repo(session),
            catalog_repo=MiddlewareCatalogRepository(
                session=session, logger=app_logger
            ),
            agent_middleware_repo=AgentMiddlewareRepository(
                session=session, logger=app_logger
            ),
            logger=app_logger,
        )

    return decide_f, list_f, tick_f, approval_repo_factory, gate_settings_f


def create_agent_schedule_factories(build_run_agent_uc, outbound_dispatcher=None):
    """agent-schedule DI: CRUD 요청-스코프 팩토리 + 트리거 싱글턴.

    트리거 싱글턴은 AsyncSession 을 보유하지 않는다(session_factory 만) — DB-001.
    outbound_dispatcher는 agent-webhook-outbound 훅 ① (optional — 미주입 무동작).
    """
    from src.application.agent_schedule.create_schedule_use_case import (
        CreateScheduleUseCase,
    )
    from src.application.agent_schedule.delete_schedule_use_case import (
        DeleteScheduleUseCase,
    )
    from src.application.agent_schedule.get_schedule_use_case import (
        GetScheduleUseCase,
    )
    from src.application.agent_schedule.list_schedule_runs_use_case import (
        ListScheduleRunsUseCase,
    )
    from src.application.agent_schedule.list_schedules_use_case import (
        ListSchedulesUseCase,
    )
    from src.application.agent_schedule.toggle_schedule_use_case import (
        ToggleScheduleUseCase,
    )
    from src.application.agent_schedule.trigger_due_schedules_use_case import (
        TriggerDueSchedulesUseCase,
    )
    from src.application.agent_schedule.update_schedule_use_case import (
        UpdateScheduleUseCase,
    )
    from src.infrastructure.agent_schedule.run_sink import DbScheduleRunSink
    from src.infrastructure.agent_schedule.schedule_repository import (
        ScheduleRepository,
    )
    from src.infrastructure.agent_schedule.schedule_repository import (
        ScheduleRepository,
    )
    from src.infrastructure.agent_schedule.schedule_run_repository import (
        ScheduleRunRepository,
    )

    app_logger = get_app_logger()

    def _make_schedule_repo(session: AsyncSession):
        return ScheduleRepository(session=session, logger=app_logger)

    def _make_agent_repo(session: AsyncSession):
        return AgentDefinitionRepository(session=session, logger=app_logger)

    def create_f(session: AsyncSession = Depends(get_session)):
        return CreateScheduleUseCase(
            _make_schedule_repo(session), _make_agent_repo(session), app_logger
        )

    def list_f(session: AsyncSession = Depends(get_session)):
        return ListSchedulesUseCase(
            _make_schedule_repo(session), _make_agent_repo(session), app_logger
        )

    def get_f(session: AsyncSession = Depends(get_session)):
        return GetScheduleUseCase(_make_schedule_repo(session), app_logger)

    def update_f(session: AsyncSession = Depends(get_session)):
        return UpdateScheduleUseCase(_make_schedule_repo(session), app_logger)

    def delete_f(session: AsyncSession = Depends(get_session)):
        return DeleteScheduleUseCase(_make_schedule_repo(session), app_logger)

    def toggle_f(session: AsyncSession = Depends(get_session)):
        return ToggleScheduleUseCase(_make_schedule_repo(session), app_logger)

    def list_runs_f(session: AsyncSession = Depends(get_session)):
        return ListScheduleRunsUseCase(
            _make_schedule_repo(session),
            ScheduleRunRepository(session=session, logger=app_logger),
            app_logger,
        )

    trigger_uc = TriggerDueSchedulesUseCase(
        session_factory=get_session_factory(),
        schedule_repo_builder=_make_schedule_repo,
        run_agent_uc_builder=build_run_agent_uc,
        sink=DbScheduleRunSink(get_session_factory(), app_logger),
        logger=app_logger,
        outbound_dispatcher=outbound_dispatcher,
    )

    def trigger_f():
        return trigger_uc

    return (
        create_f, list_f, get_f, update_f, delete_f,
        toggle_f, list_runs_f, trigger_f,
    )


def create_agent_webhook_factories(build_run_agent_uc):
    """agent-webhook DI: 관리 5종 + 공개 invoke 요청-스코프 팩토리 (Design §4-5).

    invoke는 스케줄과 공유하는 build_run_agent_uc로 실행 파이프라인을 재사용하고,
    소유자 AuthContext는 요청 세션 스코프의 AssembleAuthContextUseCase로 조립한다 (D3).

    M2(outbound): 디스패처는 앱 수명 싱글턴(D11) — 요청 세션 비의존(session_factory만).
    반환된 dispatcher를 create_agent_schedule_factories에 전달해 훅 ①을 배선한다.
    """
    from src.application.agent_webhook.dispatch_outbound_use_case import (
        DispatchOutboundWebhookUseCase,
    )
    from src.application.agent_webhook.invoke_webhook_agent_use_case import (
        InvokeWebhookAgentUseCase,
    )
    from src.application.agent_webhook.manage_webhook_use_cases import (
        DisableWebhookUseCase,
        EnableWebhookUseCase,
        GetWebhookUseCase,
        ListWebhookDeliveriesUseCase,
        RotateWebhookSecretUseCase,
        UpdateWebhookUseCase,
    )
    from src.infrastructure.agent_webhook.delivery_repository import (
        AgentWebhookDeliveryRepository,
    )
    from src.infrastructure.agent_webhook.repository import (
        AgentWebhookRepository,
    )
    from src.infrastructure.webhook.outbound_sender import HttpxOutboundSender

    app_logger = get_app_logger()

    def _make_webhook_repo(session: AsyncSession):
        return AgentWebhookRepository(session=session, logger=app_logger)

    def _make_delivery_repo(session: AsyncSession):
        return AgentWebhookDeliveryRepository(session=session, logger=app_logger)

    outbound_dispatcher = DispatchOutboundWebhookUseCase(
        session_factory=get_session_factory(),
        webhook_repo_builder=_make_webhook_repo,
        delivery_repo_builder=_make_delivery_repo,
        sender=HttpxOutboundSender(app_logger),
        logger=app_logger,
    )

    def _make_agent_repo(session: AsyncSession):
        return AgentDefinitionRepository(session=session, logger=app_logger)

    def _make_assemble_uc(session: AsyncSession):
        return AssembleAuthContextUseCase(
            profile_repo=UserProfileRepository(session=session, logger=app_logger),
            department_repo=DepartmentRepository(session=session, logger=app_logger),
            permission_repo=PermissionRepository(session=session, logger=app_logger),
            logger=app_logger,
        )

    def enable_f(session: AsyncSession = Depends(get_session)):
        return EnableWebhookUseCase(
            _make_webhook_repo(session), _make_agent_repo(session), app_logger
        )

    def get_f(session: AsyncSession = Depends(get_session)):
        return GetWebhookUseCase(
            _make_webhook_repo(session), _make_agent_repo(session), app_logger
        )

    def rotate_f(session: AsyncSession = Depends(get_session)):
        return RotateWebhookSecretUseCase(
            _make_webhook_repo(session), _make_agent_repo(session), app_logger
        )

    def update_f(session: AsyncSession = Depends(get_session)):
        return UpdateWebhookUseCase(
            _make_webhook_repo(session), _make_agent_repo(session), app_logger
        )

    def disable_f(session: AsyncSession = Depends(get_session)):
        return DisableWebhookUseCase(
            _make_webhook_repo(session), _make_agent_repo(session), app_logger
        )

    def invoke_f(session: AsyncSession = Depends(get_session)):
        return InvokeWebhookAgentUseCase(
            webhook_repo=_make_webhook_repo(session),
            agent_repo=_make_agent_repo(session),
            user_repo=UserRepository(session=session, logger=app_logger),
            assemble_auth_context_uc=_make_assemble_uc(session),
            run_agent_uc=build_run_agent_uc(session),
            logger=app_logger,
            outbound_dispatcher=outbound_dispatcher,  # M2 훅 ② (비차단 spawn)
        )

    def deliveries_f(session: AsyncSession = Depends(get_session)):
        return ListWebhookDeliveriesUseCase(
            _make_delivery_repo(session), _make_agent_repo(session), app_logger
        )

    return (
        enable_f, get_f, rotate_f, update_f, disable_f, invoke_f,
        deliveries_f, outbound_dispatcher,
    )


def create_background_job_factories(
    build_run_agent_uc, outbound_dispatcher=None, schedule_trigger_uc=None,
    approval_tick_runner=None,
):
    """background-jobs DI (Design §4-5): 요청-스코프 팩토리 + 워커 싱글턴.

    워커는 AsyncSession 을 보유하지 않는다 (session_factory 만, DB-001).
    AuthContext 는 실행 시점에 등록자 기준으로 재조립한다 (D3 — webhook 동형).
    """
    from src.application.background_job.enqueue_job_use_case import (
        EnqueueJobUseCase,
    )
    from src.application.background_job.list_my_schedule_runs_use_case import (
        ListMyScheduleRunsUseCase,
    )
    from src.application.background_job.list_my_schedules_use_case import (
        ListMySchedulesUseCase,
    )
    from src.application.background_job.delete_use_cases import (
        CleanupJobsUseCase,
        DeleteJobUseCase,
    )
    from src.application.background_job.query_use_cases import (
        CountUnseenUseCase,
        GetJobUseCase,
        ListJobHistoryUseCase,
        MarkAllSeenUseCase,
        MarkSeenUseCase,
    )
    from src.application.background_job.worker import BackgroundJobWorker
    from src.infrastructure.agent_schedule.schedule_run_repository import (
        ScheduleRunRepository,
    )
    from src.infrastructure.background_job.job_repository import (
        BackgroundJobRepository,
    )

    app_logger = get_app_logger()
    session_factory = get_session_factory()

    def _make_job_repo(session: AsyncSession):
        return BackgroundJobRepository(session=session, logger=app_logger)

    def _make_agent_repo(session: AsyncSession):
        return AgentDefinitionRepository(session=session, logger=app_logger)

    async def _assemble_job_auth_context(user_id: str, request_id: str):
        """등록자 AuthContext 재조립 (D3) — 사용자 미존재/비활성 시 None."""
        from src.domain.auth.entities import UserStatus

        async with session_factory() as session:
            user_repo = UserRepository(session=session, logger=app_logger)
            try:
                user = await user_repo.find_by_id(int(user_id))
            except (TypeError, ValueError):
                return None
            if user is None or user.status != UserStatus.APPROVED:
                return None
            assemble_uc = AssembleAuthContextUseCase(
                profile_repo=UserProfileRepository(
                    session=session, logger=app_logger
                ),
                department_repo=DepartmentRepository(
                    session=session, logger=app_logger
                ),
                permission_repo=PermissionRepository(
                    session=session, logger=app_logger
                ),
                logger=app_logger,
            )
            return await assemble_uc.execute(user, request_id)

    def enqueue_f(session: AsyncSession = Depends(get_session)):
        return EnqueueJobUseCase(
            _make_job_repo(session), _make_agent_repo(session), app_logger
        )

    def list_f(session: AsyncSession = Depends(get_session)):
        return ListJobHistoryUseCase(_make_job_repo(session), app_logger)

    def delete_f(session: AsyncSession = Depends(get_session)):
        return DeleteJobUseCase(_make_job_repo(session), app_logger)

    def cleanup_f(session: AsyncSession = Depends(get_session)):
        return CleanupJobsUseCase(_make_job_repo(session), app_logger)

    def get_f(session: AsyncSession = Depends(get_session)):
        return GetJobUseCase(_make_job_repo(session), app_logger)

    def unseen_f(session: AsyncSession = Depends(get_session)):
        # approval-gate Design §5.5: 벨 배지에 승인 대기 건수 합산.
        from src.application.approval.list_use_case import ListApprovalsUseCase
        from src.infrastructure.approval.repository import ApprovalRepository

        approval_counter = ListApprovalsUseCase(
            approval_repo=ApprovalRepository(session=session, logger=app_logger),
            agent_repo=AgentDefinitionRepository(session=session, logger=app_logger),
            logger=app_logger,
        )
        return CountUnseenUseCase(
            _make_job_repo(session), app_logger,
            approval_counter=approval_counter,
        )

    def seen_f(session: AsyncSession = Depends(get_session)):
        return MarkSeenUseCase(_make_job_repo(session), app_logger)

    def seen_all_f(session: AsyncSession = Depends(get_session)):
        return MarkAllSeenUseCase(_make_job_repo(session), app_logger)

    def schedule_runs_f(session: AsyncSession = Depends(get_session)):
        return ListMyScheduleRunsUseCase(
            ScheduleRunRepository(session=session, logger=app_logger),
            app_logger,
        )

    def my_schedules_f(session: AsyncSession = Depends(get_session)):
        return ListMySchedulesUseCase(
            ScheduleRepository(session=session, logger=app_logger), app_logger
        )

    worker = BackgroundJobWorker(
        session_factory=session_factory,
        job_repo_builder=_make_job_repo,
        run_agent_uc_builder=build_run_agent_uc,
        assemble_auth_context=_assemble_job_auth_context,
        logger=app_logger,
        schedule_trigger_uc=schedule_trigger_uc,
        outbound_dispatcher=outbound_dispatcher,
        poll_interval_sec=settings.background_job_poll_interval_sec,
        schedule_tick_interval_sec=settings.background_schedule_tick_interval_sec,
        max_concurrency=settings.background_job_max_concurrency,
        enabled=settings.background_worker_enabled,
        # approval-gate Check G5: 외부 cron 없이도 예약 집행이 돌도록 합류
        approval_tick_runner=approval_tick_runner,
        approval_tick_interval_sec=settings.approval_executor_tick_seconds,
    )

    return (
        enqueue_f, list_f, get_f, unseen_f, seen_f, seen_all_f,
        schedule_runs_f, delete_f, cleanup_f, my_schedules_f, worker,
    )


def create_department_factories():
    """Return per-request DI factories for Department use cases."""
    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession):
        return DepartmentRepository(session=session, logger=app_logger)

    def list_factory(session: AsyncSession = Depends(get_session)):
        return ListDepartmentsUseCase(repository=_make_repo(session), logger=app_logger)

    def create_factory(session: AsyncSession = Depends(get_session)):
        return CreateDepartmentUseCase(repository=_make_repo(session), logger=app_logger)

    def update_factory(session: AsyncSession = Depends(get_session)):
        return UpdateDepartmentUseCase(repository=_make_repo(session), logger=app_logger)

    def delete_factory(session: AsyncSession = Depends(get_session)):
        return DeleteDepartmentUseCase(repository=_make_repo(session), logger=app_logger)

    def assign_factory(session: AsyncSession = Depends(get_session)):
        return AssignUserDepartmentUseCase(repository=_make_repo(session), logger=app_logger)

    def remove_factory(session: AsyncSession = Depends(get_session)):
        return RemoveUserDepartmentUseCase(repository=_make_repo(session), logger=app_logger)

    return list_factory, create_factory, update_factory, delete_factory, assign_factory, remove_factory


def create_ragas_factories(build_run_agent_uc=None):
    """RAGAS 평가 DI (eval-hub Design §2.4).

    배치 실행기·생성 UC는 애플리케이션 싱글턴 — DB 접근은 session_factory 기반
    독립 짧은 세션(SessionScopedEvalRunStore, D11 패턴). CRUD UC만 per-request 세션.
    build_run_agent_uc: agent 대상 헤드리스 실행용 (agent-schedule §6.2와 공유).
    """
    from src.application.agent_builder.schemas import RunAgentRequest
    from src.application.ragas.batch_executor import BatchEvalExecutor
    from src.application.ragas.testset_generate_use_case import (
        TestsetGenerateUseCase,
    )
    from src.infrastructure.eval_testset.document_text_extractor import (
        extract_document_text,
    )
    from src.infrastructure.eval_testset.qa_generator import OpenAIQAGenerator
    from src.infrastructure.eval_testset.testset_file_parser import (
        parse_testset_file,
    )
    from src.infrastructure.ragas.run_store import SessionScopedEvalRunStore
    from src.infrastructure.ragas.target_executor import (
        AgentRunOutcome,
        DefaultTargetExecutor,
    )

    app_logger = get_app_logger()
    evaluator = RagasEvaluatorAdapter()
    session_factory = get_session_factory()

    eval_qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    eval_embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)

    async def _run_agent_headless(
        agent_id: str,
        question: str,
        user_id: str,
        request_id: str,
        *,
        llm_model_id_override: str | None = None,
        temperature_override: float | None = None,
        persist_conversation: bool = True,
    ) -> AgentRunOutcome:
        """agent-model-benchmark module-4: 오버라이드를 실행 경로로 전달하고,
        도구 호출·관측 run_id를 함께 회수한다 (D1/D2/D6/D10)."""
        if build_run_agent_uc is None:
            raise ValueError("agent 대상 평가 실행기가 구성되지 않았습니다")
        async with session_factory() as session:
            async with session.begin():
                run_uc = build_run_agent_uc(session)
                resp = await run_uc.execute(
                    agent_id,
                    RunAgentRequest(
                        query=question,
                        user_id=user_id,
                        llm_model_id_override=llm_model_id_override,
                        temperature_override=temperature_override,
                        persist_conversation=persist_conversation,
                    ),
                    request_id,
                    viewer_user_id=user_id,
                )
                return AgentRunOutcome(
                    answer=resp.answer,
                    tools_used=list(resp.tools_used),
                    ai_run_id=resp.run_id,
                )

    batch_executor = BatchEvalExecutor(
        store=SessionScopedEvalRunStore(session_factory, app_logger),
        evaluator=evaluator,
        target_executor=DefaultTargetExecutor(
            qdrant_client=eval_qdrant_client,
            embedding=eval_embedding,
            agent_runner=_run_agent_headless,
            logger=app_logger,
        ),
        logger=app_logger,
    )

    generate_uc = TestsetGenerateUseCase(
        text_extractor=extract_document_text,
        qa_generator=OpenAIQAGenerator(
            model_name=settings.eval_qa_gen_model,
            llm_provider=get_utility_llm_provider(),
        ),
        logger=app_logger,
        max_input_chars=settings.eval_qa_gen_max_input_chars,
        max_pairs=settings.eval_qa_gen_max_pairs,
        max_file_bytes=settings.eval_qa_gen_max_file_mb * 1024 * 1024,
    )

    def _make_repo(session: AsyncSession):
        return EvaluationRepository(session=session, logger=app_logger)

    def batch_factory(session: AsyncSession = Depends(get_session)):
        return BatchEvaluationUseCase(
            repository=_make_repo(session),
            evaluator=evaluator,
            logger=app_logger,
            executor=batch_executor,
        )

    def realtime_factory(session: AsyncSession = Depends(get_session)):
        return RealtimeEvaluationUseCase(
            repository=_make_repo(session),
            evaluator=evaluator,
            logger=app_logger,
        )

    def result_factory(session: AsyncSession = Depends(get_session)):
        return EvalResultUseCase(repository=_make_repo(session), logger=app_logger)

    def testset_factory(session: AsyncSession = Depends(get_session)):
        return TestsetUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            file_parser=parse_testset_file,
        )

    def admin_eval_factory(session: AsyncSession = Depends(get_session)):
        return AdminEvalUseCase(repository=_make_repo(session), logger=app_logger)

    def generate_factory():
        return generate_uc

    # ── agent-model-benchmark module-5: 모델 스윕 배선 ────────────────
    from src.application.eval_sweep.sweep_executor import SweepExecutor
    from src.application.eval_sweep.use_cases import (
        CreateSweepUseCase,
        DeleteSweepUseCase,
        EstimateSweepCostUseCase,
        GetSweepDetailUseCase,
        ListSweepsUseCase,
    )
    from src.infrastructure.eval_sweep.repository import SweepRepository

    def _make_sweep_repo(session: AsyncSession):
        return SweepRepository(session=session, logger=app_logger)

    def _make_llm_model_repo(session: AsyncSession):
        return LlmModelRepository(session=session, logger=app_logger)

    async def _agent_token_stats(agent_id: str, request_id: str) -> dict:
        """비용 추정용 실측 평균 토큰 (§4.2 basis).

        해당 에이전트의 최근 성공 실행에서 평균을 낸다. 이력이 없으면 빈 dict를
        돌려 UseCase가 상수 fallback을 쓰게 한다 — 추정 실패로 막지 않는다.
        """
        from sqlalchemy import func as sa_func
        from src.infrastructure.persistence.models.agent_run import AgentRunModel

        try:
            async with session_factory() as session:
                stmt = (
                    select(
                        sa_func.avg(AgentRunModel.prompt_tokens),
                        sa_func.avg(AgentRunModel.completion_tokens),
                        sa_func.count(AgentRunModel.id),
                    )
                    .where(
                        AgentRunModel.agent_id == agent_id,
                        AgentRunModel.status == "SUCCESS",
                    )
                )
                row = (await session.execute(stmt)).one_or_none()
        except Exception as e:
            app_logger.warning(
                "토큰 실측 조회 실패 — 상수 fallback 사용",
                request_id=request_id,
                agent_id=agent_id,
                exception=e,
            )
            return {}

        if row is None or not row[2]:
            return {}
        return {
            "avg_prompt_tokens": int(row[0] or 0),
            "avg_completion_tokens": int(row[1] or 0),
            "sample_size": int(row[2]),
            "source": "ai_run_recent_avg",
        }

    sweep_executor = SweepExecutor(
        batch_executor=batch_executor,
        sweep_repo_builder=_make_sweep_repo,
        session_factory=session_factory,
        logger=app_logger,
    )

    def _estimator(session: AsyncSession):
        return EstimateSweepCostUseCase(
            eval_repo=_make_repo(session),
            llm_model_repo=_make_llm_model_repo(session),
            token_stats_provider=_agent_token_stats,
            logger=app_logger,
        )

    def estimate_sweep_factory(session: AsyncSession = Depends(get_session)):
        return _estimator(session)

    def create_sweep_factory(session: AsyncSession = Depends(get_session)):
        return CreateSweepUseCase(
            sweep_repo=_make_sweep_repo(session),
            eval_repo=_make_repo(session),
            llm_model_repo=_make_llm_model_repo(session),
            executor=sweep_executor,
            estimator=_estimator(session),
            logger=app_logger,
        )

    def sweep_detail_factory(session: AsyncSession = Depends(get_session)):
        return GetSweepDetailUseCase(
            sweep_repo=_make_sweep_repo(session),
            llm_model_repo=_make_llm_model_repo(session),
            logger=app_logger,
            # G-2: 실험 조건(에이전트명·테스트셋명·케이스 수) 표시용
            agent_repo=AgentDefinitionRepository(session=session, logger=app_logger),
            eval_repo=_make_repo(session),
        )

    def list_sweeps_factory(session: AsyncSession = Depends(get_session)):
        return ListSweepsUseCase(
            sweep_repo=_make_sweep_repo(session), logger=app_logger
        )

    def delete_sweep_factory(session: AsyncSession = Depends(get_session)):
        return DeleteSweepUseCase(
            sweep_repo=_make_sweep_repo(session), logger=app_logger
        )

    return (
        batch_factory, realtime_factory, result_factory,
        testset_factory, admin_eval_factory, generate_factory,
        create_sweep_factory, estimate_sweep_factory,
        sweep_detail_factory, list_sweeps_factory, delete_sweep_factory,
    )


def create_collection_factories():
    """Return per-request DI factories for Collection Management."""
    app_logger = get_app_logger()

    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    from src.infrastructure.collection.qdrant_collection_repository import QdrantCollectionRepository
    from src.infrastructure.collection.activity_log_repository import ActivityLogRepository
    from src.application.collection.activity_log_service import ActivityLogService
    from src.application.collection.use_case import CollectionManagementUseCase
    from src.domain.collection.policy import CollectionPolicy
    from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
    from src.application.collection.permission_service import CollectionPermissionService
    from src.domain.collection.permission_policy import CollectionPermissionPolicy
    from src.infrastructure.department.department_repository import DepartmentRepository

    collection_repo = QdrantCollectionRepository(qdrant_client)

    def use_case_factory(session: AsyncSession = Depends(get_session)):
        log_repo = ActivityLogRepository(session, app_logger)
        log_service = ActivityLogService(log_repo, app_logger)
        embedding_model_repo = EmbeddingModelRepository(
            session=session, logger=app_logger
        )
        perm_repo = CollectionPermissionRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        perm_service = CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=app_logger,
        )
        return CollectionManagementUseCase(
            repository=collection_repo,
            policy=CollectionPolicy(),
            activity_log=log_service,
            default_collection=settings.qdrant_collection_name,
            permission_service=perm_service,
            embedding_model_repo=embedding_model_repo,
        )

    def activity_log_factory(session: AsyncSession = Depends(get_session)):
        log_repo = ActivityLogRepository(session, app_logger)
        return ActivityLogService(log_repo, app_logger)

    return use_case_factory, activity_log_factory


def create_unified_upload_factories():
    """Return per-request DI factory for UnifiedUploadUseCase."""
    from src.infrastructure.collection.qdrant_collection_repository import QdrantCollectionRepository
    from src.infrastructure.collection.activity_log_repository import ActivityLogRepository
    from src.application.collection.activity_log_service import ActivityLogService
    from src.application.unified_upload.use_case import UnifiedUploadUseCase
    from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
    from src.infrastructure.morph.kiwi_morph_analyzer import KiwiMorphAnalyzer
    from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository

    app_logger = get_app_logger()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    collection_repo = QdrantCollectionRepository(qdrant_client)
    embedding_factory = EmbeddingFactory()
    # kb-excel-upload D9: 확장자 라우팅 — pdf는 기존 파서, xlsx/xls는 어댑터
    parser = ExtensionRoutingParser(
        pdf_parser=ParserFactory.create_from_string(settings.parser_type),
        excel_parser=ExcelDocumentParserAdapter(
            excel_parser=PandasExcelParser(),
            max_rows_per_sheet=settings.kb_excel_max_rows_per_sheet,
        ),
    )
    morph_analyzer = KiwiMorphAnalyzer()

    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    def use_case_factory(session: AsyncSession = Depends(get_session)):
        log_repo = ActivityLogRepository(session, app_logger)
        log_service = ActivityLogService(log_repo, app_logger)
        embedding_model_repo = EmbeddingModelRepository(
            session=session, logger=app_logger
        )
        document_metadata_repo = DocumentMetadataRepository(
            session=session, logger=app_logger
        )
        return UnifiedUploadUseCase(
            parser=parser,
            collection_repo=collection_repo,
            activity_log_repo=log_repo,
            embedding_model_repo=embedding_model_repo,
            embedding_factory=embedding_factory,
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            morph_analyzer=morph_analyzer,
            document_metadata_repo=document_metadata_repo,
            activity_log_service=log_service,
            logger=app_logger,
        )

    return use_case_factory


def create_knowledge_base_factories(unified_upload_factory, summary_launcher=None):
    """Return per-request DI factories for Knowledge Base (knowledge-base-scoping Design §8).

    summary_launcher: 섹션 요약 잡 킥오프 싱글턴 (card-section-summary D14, 선택).
    """
    from src.infrastructure.collection.qdrant_collection_repository import QdrantCollectionRepository
    from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
    from src.application.collection.permission_service import CollectionPermissionService
    from src.domain.collection.permission_policy import CollectionPermissionPolicy
    from src.infrastructure.department.department_repository import DepartmentRepository
    from src.infrastructure.knowledge_base.repository import KnowledgeBaseRepository
    from src.domain.knowledge_base.policy import KnowledgeBasePolicy
    from src.application.knowledge_base.collection_assigner import UserSelectedCollectionAssigner
    from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
    from src.application.knowledge_base.upload_use_case import KnowledgeBaseUploadUseCase
    from src.application.knowledge_base.chunking_resolver import ChunkingSettingsResolver
    from src.infrastructure.chunking_profile.repository import ChunkingProfileRepository

    app_logger = get_app_logger()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    collection_repo = QdrantCollectionRepository(qdrant_client)

    def _build_assigner(session: AsyncSession):
        perm_repo = CollectionPermissionRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        perm_service = CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=app_logger,
        )
        return UserSelectedCollectionAssigner(
            collection_repo=collection_repo,
            perm_service=perm_service,
        )

    def kb_use_case_factory(session: AsyncSession = Depends(get_session)):
        kb_repo = KnowledgeBaseRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        profile_repo = ChunkingProfileRepository(session, app_logger)
        return KnowledgeBaseUseCase(
            kb_repo=kb_repo,
            policy=KnowledgeBasePolicy(),
            assigner=_build_assigner(session),
            dept_repo=dept_repo,
            logger=app_logger,
            profile_repo=profile_repo,
        )

    def kb_upload_factory(session: AsyncSession = Depends(get_session)):
        kb_repo = KnowledgeBaseRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        # 동일 요청 세션으로 UnifiedUploadUseCase 조립 (db-session 규칙: UseCase 단일 세션)
        unified = unified_upload_factory(session)
        profile_repo = ChunkingProfileRepository(session, app_logger)
        resolver = ChunkingSettingsResolver(profile_repo, app_logger)
        return KnowledgeBaseUploadUseCase(
            kb_repo=kb_repo,
            policy=KnowledgeBasePolicy(),
            dept_repo=dept_repo,
            unified_upload=unified,
            logger=app_logger,
            chunking_resolver=resolver,
            summary_launcher=summary_launcher,
        )

    def kb_documents_factory(session: AsyncSession = Depends(get_session)):
        # kb-management-ui D3: 권한/존재 검증은 동일 세션의 KnowledgeBaseUseCase에 위임
        from src.application.knowledge_base.list_documents_use_case import (
            ListKbDocumentsUseCase,
        )
        from src.infrastructure.doc_browse.document_metadata_repository import (
            DocumentMetadataRepository,
        )

        return ListKbDocumentsUseCase(
            kb_use_case=kb_use_case_factory(session),
            document_metadata_repo=DocumentMetadataRepository(
                session, app_logger
            ),
            logger=app_logger,
        )

    return kb_use_case_factory, kb_upload_factory, kb_documents_factory


def create_kb_browse_factories(kb_use_case_factory):
    """KB 저장 내용 조회 DI (kb-content-browser Design §4.4).

    Qdrant/ES 클라이언트는 싱글턴, 가드(kb_use_case + doc_meta repo)는
    per-request 세션으로 조립한다.
    """
    from src.application.knowledge_base.content_browse_guard import (
        KbDocumentGuard,
    )
    from src.application.knowledge_base.get_kb_document_chunks_use_case import (
        GetKbDocumentChunksUseCase,
    )
    from src.application.knowledge_base.get_kb_document_summary_use_case import (
        GetKbDocumentSummaryUseCase,
    )
    from src.application.knowledge_base.list_kb_section_summaries_use_case import (
        ListKbSectionSummariesUseCase,
    )
    from src.infrastructure.doc_browse.document_metadata_repository import (
        DocumentMetadataRepository,
    )

    app_logger = get_app_logger()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(
        client=es_client, logger=StructuredLogger("kb_browse.es")
    )

    def _guard(session: AsyncSession) -> KbDocumentGuard:
        return KbDocumentGuard(
            kb_use_case=kb_use_case_factory(session),
            document_metadata_repo=DocumentMetadataRepository(
                session, app_logger
            ),
            logger=StructuredLogger("kb_browse.guard"),
        )

    def summary_factory(session: AsyncSession = Depends(get_session)):
        return GetKbDocumentSummaryUseCase(
            guard=_guard(session),
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            logger=StructuredLogger("kb_browse.summary"),
        )

    def sections_factory(session: AsyncSession = Depends(get_session)):
        return ListKbSectionSummariesUseCase(
            guard=_guard(session),
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            logger=StructuredLogger("kb_browse.sections"),
        )

    def chunks_factory(session: AsyncSession = Depends(get_session)):
        return GetKbDocumentChunksUseCase(
            guard=_guard(session),
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            logger=StructuredLogger("kb_browse.chunks"),
        )

    return summary_factory, sections_factory, chunks_factory


def create_kb_search_factories(kb_use_case_factory):
    """KB 단위 검색/히스토리 DI (kb-retrieval-test §3.3).

    Qdrant/ES 클라이언트는 싱글턴, 나머지는 per-request 세션으로
    조립한다 — 한 UseCase 안에서 단일 세션 규칙 준수.
    """
    from src.application.knowledge_base.content_browse_guard import (
        KbDocumentGuard,
    )
    from src.application.knowledge_base.search_history_use_case import (
        KbSearchHistoryUseCase,
    )
    from src.application.knowledge_base.search_use_case import KbSearchUseCase
    from src.infrastructure.collection.activity_log_repository import (
        ActivityLogRepository,
    )
    from src.infrastructure.collection_search.search_history_repository import (
        SearchHistoryRepository,
    )
    from src.infrastructure.doc_browse.document_metadata_repository import (
        DocumentMetadataRepository,
    )
    from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory

    app_logger = get_app_logger()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    embedding_factory = EmbeddingFactory()
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(
        client=es_client, logger=StructuredLogger("kb_search.es")
    )

    def kb_search_factory(session: AsyncSession = Depends(get_session)):
        kb_use_case = kb_use_case_factory(session)
        guard = KbDocumentGuard(
            kb_use_case=kb_use_case,
            document_metadata_repo=DocumentMetadataRepository(
                session, app_logger
            ),
            logger=StructuredLogger("kb_search.guard"),
        )
        return KbSearchUseCase(
            kb_use_case=kb_use_case,
            document_guard=guard,
            activity_log_repo=ActivityLogRepository(session, app_logger),
            embedding_model_repo=EmbeddingModelRepository(
                session=session, logger=app_logger
            ),
            embedding_factory=embedding_factory,
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            search_history_repo=SearchHistoryRepository(session, app_logger),
            logger=StructuredLogger("kb_search"),
        )

    def kb_history_factory(session: AsyncSession = Depends(get_session)):
        return KbSearchHistoryUseCase(
            kb_use_case=kb_use_case_factory(session),
            search_history_repo=SearchHistoryRepository(session, app_logger),
            logger=StructuredLogger("kb_search.history"),
        )

    return kb_search_factory, kb_history_factory


def create_chunking_profile_factories():
    """Return per-request DI factory for Chunking Profile (clause-aware-chunking Design §9)."""
    from src.infrastructure.chunking_profile.repository import ChunkingProfileRepository
    from src.domain.chunking_profile.policy import ChunkingProfilePolicy
    from src.application.chunking_profile.use_case import ChunkingProfileUseCase
    from src.infrastructure.llm_model.llm_model_repository import LlmModelRepository

    app_logger = get_app_logger()

    def profile_use_case_factory(session: AsyncSession = Depends(get_session)):
        repo = ChunkingProfileRepository(session, app_logger)
        # card-section-summary D16: summary_llm_model_id 존재+활성 검증용
        llm_model_repo = LlmModelRepository(session, app_logger)
        return ChunkingProfileUseCase(
            repo, ChunkingProfilePolicy(), app_logger,
            llm_model_repo=llm_model_repo,
        )

    return profile_use_case_factory


def create_section_summary_components():
    """Section Summary 배선 (card-section-summary Design §3, D11).

    launcher/runner는 애플리케이션 싱글턴 — DB 접근은 전부 session_factory 기반
    독립 짧은 세션(JobStore)으로 수행한다. query use case만 per-request 세션.
    """
    from src.application.section_summary.launcher import SectionSummaryLauncher
    from src.application.section_summary.query_use_case import (
        SectionSummaryQueryUseCase,
    )
    from src.application.section_summary.use_case import SummarizeSectionsUseCase
    from src.domain.knowledge_base.policy import KnowledgeBasePolicy
    from src.domain.section_summary.policy import SectionSummaryJobPolicy
    from src.infrastructure.department.department_repository import (
        DepartmentRepository,
    )
    from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
    from src.infrastructure.knowledge_base.repository import (
        KnowledgeBaseRepository,
    )
    from src.infrastructure.llm.llm_factory import LLMFactory
    from src.infrastructure.llm_model.session_scoped_llm_model_repository import (
        SessionScopedLlmModelRepository,
    )
    from src.infrastructure.section_summary.document_summary_step import (
        DocumentSummaryStep,
    )
    from src.infrastructure.section_summary.job_repository import (
        SectionSummaryJobRepository,
        SessionScopedSectionSummaryJobStore,
    )
    from src.infrastructure.section_summary.qdrant_section_source import (
        QdrantSectionSource,
    )
    from src.infrastructure.section_summary.summary_writer import (
        DualStoreSummaryWriter,
    )

    app_logger = get_app_logger()
    session_factory = get_session_factory()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    job_store = SessionScopedSectionSummaryJobStore(session_factory, app_logger)
    policy = SectionSummaryJobPolicy()

    async def _resolve_embedding_provider(
        model_name: str, request_id: str
    ) -> str | None:
        async with session_factory() as session:
            repo = EmbeddingModelRepository(session=session, logger=app_logger)
            model = await repo.find_by_model_name(model_name, request_id)
            return model.provider if model else None

    section_source = QdrantSectionSource(qdrant_client, app_logger)
    llm_model_repo = SessionScopedLlmModelRepository(session_factory, app_logger)
    llm_factory = LLMFactory()
    embedding_factory = EmbeddingFactory()
    # document-summary-routing D1/D2: 섹션 요약 완료 직후 문서 요약 자동 체이닝
    document_summary_step = DocumentSummaryStep(
        section_source=section_source,
        qdrant_client=qdrant_client,
        es_repo=es_repo,
        es_index=settings.es_index,
        llm_model_repo=llm_model_repo,
        llm_factory=llm_factory,
        embedding_factory=embedding_factory,
        policy=policy,
        logger=app_logger,
        input_char_cap=settings.document_summary_input_char_cap,
        max_batches=settings.document_summary_max_batches,
    )
    runner = SummarizeSectionsUseCase(
        job_store=job_store,
        section_source=section_source,
        writer=DualStoreSummaryWriter(
            qdrant_client, es_repo, settings.es_index, app_logger
        ),
        llm_model_repo=llm_model_repo,
        llm_factory=llm_factory,
        embedding_factory=embedding_factory,
        policy=policy,
        logger=app_logger,
        concurrency=settings.section_summary_concurrency,
        input_char_cap=settings.section_summary_input_char_cap,
        max_sections=settings.section_summary_max_sections,
        document_summary_step=document_summary_step,
    )
    launcher = SectionSummaryLauncher(
        job_store=job_store,
        runner=runner,
        logger=app_logger,
        embedding_provider_resolver=_resolve_embedding_provider,
    )

    def query_use_case_factory(session: AsyncSession = Depends(get_session)):
        return SectionSummaryQueryUseCase(
            kb_repo=KnowledgeBaseRepository(session, app_logger),
            dept_repo=DepartmentRepository(session, app_logger),
            kb_policy=KnowledgeBasePolicy(),
            job_repo=SectionSummaryJobRepository(session, app_logger),
            policy=policy,
            launcher=launcher,
            logger=app_logger,
            stale_seconds=settings.section_summary_stale_seconds,
        )

    return launcher, query_use_case_factory


def create_collection_search_factories():
    """Return per-request DI factories for CollectionSearch + SearchHistory."""
    from src.infrastructure.collection.qdrant_collection_repository import QdrantCollectionRepository
    from src.infrastructure.collection.activity_log_repository import ActivityLogRepository
    from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
    from src.infrastructure.department.department_repository import DepartmentRepository
    from src.infrastructure.collection_search.search_history_repository import SearchHistoryRepository
    from src.application.collection.permission_service import CollectionPermissionService
    from src.domain.collection.permission_policy import CollectionPermissionPolicy
    from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
    from src.application.collection_search.use_case import CollectionSearchUseCase
    from src.application.collection_search.search_history_use_case import SearchHistoryUseCase

    app_logger = get_app_logger()
    qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    collection_repo = QdrantCollectionRepository(qdrant_client)
    embedding_factory = EmbeddingFactory()

    es_config = ElasticsearchConfig(
        ES_HOST=settings.es_host,
        ES_PORT=settings.es_port,
        ES_SCHEME=settings.es_scheme,
    )
    es_client = ElasticsearchClient.from_config(es_config)
    es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)

    def search_uc_factory(session: AsyncSession = Depends(get_session)):
        log_repo = ActivityLogRepository(session, app_logger)
        perm_repo = CollectionPermissionRepository(session, app_logger)
        dept_repo = DepartmentRepository(session, app_logger)
        perm_service = CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=app_logger,
        )
        embedding_model_repo = EmbeddingModelRepository(
            session=session, logger=app_logger
        )
        history_repo = SearchHistoryRepository(session, app_logger)
        return CollectionSearchUseCase(
            collection_repo=collection_repo,
            permission_service=perm_service,
            activity_log_repo=log_repo,
            embedding_model_repo=embedding_model_repo,
            embedding_factory=embedding_factory,
            qdrant_client=qdrant_client,
            es_repo=es_repo,
            es_index=settings.es_index,
            search_history_repo=history_repo,
            logger=app_logger,
        )

    def history_uc_factory(session: AsyncSession = Depends(get_session)):
        history_repo = SearchHistoryRepository(session, app_logger)
        return SearchHistoryUseCase(
            search_history_repo=history_repo,
            logger=app_logger,
        )

    return search_uc_factory, history_uc_factory


def create_tool_catalog_factories():
    """Return per-request DI factories for Tool Catalog use cases."""
    app_logger = get_app_logger()

    def list_factory(session: AsyncSession = Depends(get_session)):
        repo = ToolCatalogRepository(session=session, logger=app_logger)
        return ListToolCatalogUseCase(repository=repo, logger=app_logger)

    def sync_factory(session: AsyncSession = Depends(get_session)):
        tool_catalog_repo = ToolCatalogRepository(session=session, logger=app_logger)
        mcp_repo = MCPServerRepository(session=session, logger=app_logger, cipher=_mcp_cipher())
        mcp_loader = MCPToolLoader(logger=app_logger)
        return SyncMcpToolsUseCase(
            tool_catalog_repo=tool_catalog_repo,
            mcp_server_repo=mcp_repo,
            mcp_tool_loader=mcp_loader,
            logger=app_logger,
        )

    def set_builtin_factory(session: AsyncSession = Depends(get_session)):
        # builtin-tools D3: 관리자 빌트인 토글
        from src.application.tool_catalog.set_builtin_use_case import (
            SetBuiltinToolUseCase,
        )

        repo = ToolCatalogRepository(session=session, logger=app_logger)
        return SetBuiltinToolUseCase(repository=repo, logger=app_logger)

    def update_metadata_factory(session: AsyncSession = Depends(get_session)):
        # mcp-tool-category-routing §4.2 (FR-13): 관리자 분류·상한 지정
        from src.application.tool_catalog.update_metadata_use_case import (
            UpdateToolMetadataUseCase,
        )

        repo = ToolCatalogRepository(session=session, logger=app_logger)
        return UpdateToolMetadataUseCase(repository=repo, logger=app_logger)

    return list_factory, sync_factory, set_builtin_factory, update_metadata_factory


def create_middleware_catalog_factories():
    """Return per-request DI factories for Middleware Catalog (builtin-middleware D4)."""
    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession):
        from src.infrastructure.middleware.repository import (
            MiddlewareCatalogRepository,
        )
        return MiddlewareCatalogRepository(session=session, logger=app_logger)

    def list_factory(session: AsyncSession = Depends(get_session)):
        from src.application.middleware.list_middleware_catalog_use_case import (
            ListMiddlewareCatalogUseCase,
        )
        return ListMiddlewareCatalogUseCase(
            repository=_make_repo(session), logger=app_logger
        )

    def set_flags_factory(session: AsyncSession = Depends(get_session)):
        from src.application.middleware.set_middleware_flags_use_case import (
            SetMiddlewareFlagsUseCase,
        )
        return SetMiddlewareFlagsUseCase(
            repository=_make_repo(session),
            llm_model_repository=LlmModelRepository(
                session=session, logger=app_logger
            ),
            logger=app_logger,
        )

    return list_factory, set_flags_factory


def create_agent_composer_factories():
    """Return per-request DI factory for Agent Composer use case (nl-agent-composer)."""
    from langchain_openai import ChatOpenAI

    from src.application.agent_composer.composer import AgentComposer
    from src.application.agent_composer.compose_agent_use_case import (
        ComposeAgentUseCase,
    )
    from src.application.agent_composer.planner import AgentPlanner
    from src.infrastructure.llm_model.llm_model_repository import (
        LlmModelRepository,
    )

    app_logger = get_app_logger()

    llm = ChatOpenAI(
        model=settings.openai_llm_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    composer = AgentComposer(
        llm=llm,
        logger=app_logger,
        max_candidates=settings.composer_max_candidates,
    )
    # fix-agent-planner-hitl D6: Planner는 Composer와 동일 LLM 인스턴스 재사용
    planner = AgentPlanner(
        llm=llm,
        logger=app_logger,
        max_candidates=settings.composer_max_candidates,
    )

    def compose_factory(session: AsyncSession = Depends(get_session)):
        return ComposeAgentUseCase(
            composer=composer,
            planner=planner,
            tool_catalog_repo=ToolCatalogRepository(
                session=session, logger=app_logger
            ),
            mcp_server_repo=MCPServerRepository(
                session=session, logger=app_logger, cipher=_mcp_cipher()
            ),
            llm_model_repository=LlmModelRepository(
                session=session, logger=app_logger
            ),
            logger=app_logger,
        )

    return compose_factory


def create_prompt_composer_factory():
    """Return per-request DI factory for prompt-composer (Design §9.4).

    LLM 어댑터는 lifespan 1회 생성해 공유하고(세션 무관), 세션에 의존하는
    Repository 2종만 요청마다 조립한다 — 동일 `AsyncSession` 을 공유해야
    UseCase 안에서 원자성이 성립한다 (DB-001).

    킬스위치가 꺼져 있거나 조립이 실패하면 None 을 돌려주고, 호출부가 라우터를
    등록하지 않는다 (tool_selection 관례) — 프롬프트 생성은 부가 기능이며
    조립 실패가 앱 기동을 막아선 안 된다.
    """
    from src.application.prompt_composer.compose_prompt_use_case import (
        ComposePromptUseCase,
    )
    from src.infrastructure.config.prompt_composer_config import (
        PromptComposerConfig,
    )
    from src.infrastructure.prompt_composer.adapter import (
        LLMPromptGeneratorAdapter,
    )
    from src.infrastructure.prompt_composer.repository import (
        PromptRepository,
        ToolCatalogMetaReader,
    )

    app_logger = get_app_logger()
    config = PromptComposerConfig()
    if not config.PROMPT_COMPOSER_ENABLED:
        app_logger.info("Prompt composer disabled — router not registered")
        return None
    try:
        generator = LLMPromptGeneratorAdapter(
            logger=app_logger,
            config=config,
            llm_provider=get_utility_llm_provider(),
        )
    except Exception as e:
        app_logger.error("Prompt composer build failed — disabling", exception=e)
        return None

    def prompt_factory(session: AsyncSession = Depends(get_session)):
        return ComposePromptUseCase(
            generator=generator,
            tool_reader=ToolCatalogMetaReader(session),
            repository=PromptRepository(session),
            logger=app_logger,
        )

    return prompt_factory


def create_append_human_version_factory():
    """Return per-request DI factory for human prompt-version append.

    agent-create-wizard Design Ref: §4.5 — 위저드 4단계의 편집본 저장 경로.
    LLM 어댑터가 필요 없다(사람이 쓴 글을 그대로 저장할 뿐)므로 생성기 조립
    실패와 무관하게 항상 조립된다. 라우터 등록 여부는 호출부가
    `create_prompt_composer_factory()` 결과와 함께 판단한다 — 같은 라우터에
    속하므로 킬스위치를 공유한다.
    """
    from src.application.prompt_composer.append_human_version_use_case import (
        AppendHumanVersionUseCase,
    )
    from src.infrastructure.prompt_composer.repository import PromptRepository

    app_logger = get_app_logger()

    def append_factory(session: AsyncSession = Depends(get_session)):
        return AppendHumanVersionUseCase(
            repository=PromptRepository(session), logger=app_logger
        )

    return append_factory


def create_mcp_registry_factories():
    """Return per-request DI factories for MCP Registry use cases (MCP-REG-001)."""
    app_logger = get_app_logger()

    # 암호화 키 설정 여부 — streamable_http 시크릿 저장 가능 여부를 결정한다.
    secrets_enabled = _mcp_cipher() is not None

    def _make_repo(session: AsyncSession):
        return MCPServerRepository(session=session, logger=app_logger, cipher=_mcp_cipher())

    def _make_sync_uc(session: AsyncSession):
        """mcp-tool-auto-sync Design Ref: §11.4 — DB-001 준수.

        Depends(get_session)가 준 **동일 세션 인스턴스**를 등록/수정 UseCase와
        공유한다. repository 인스턴스가 2개인 것은 무방하고, 금지되는 것은
        세션이 2개인 경우다(요청 1건 = 세션 1개 = 트랜잭션 1건).
        """
        return SyncMcpToolsUseCase(
            tool_catalog_repo=ToolCatalogRepository(session=session, logger=app_logger),
            mcp_server_repo=_make_repo(session),
            mcp_tool_loader=MCPToolLoader(logger=app_logger),
            logger=app_logger,
        )

    def register_factory(session: AsyncSession = Depends(get_session)):
        return RegisterMCPServerUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            secrets_enabled=secrets_enabled,
            # mcp-tool-auto-sync FR-01: 등록 직후 도구 카탈로그 자동 반영
            sync_use_case=_make_sync_uc(session),
            sync_timeout_sec=settings.mcp_tool_sync_timeout_sec,
        )

    def list_factory(session: AsyncSession = Depends(get_session)):
        return ListMCPServersUseCase(repository=_make_repo(session), logger=app_logger)

    def update_factory(session: AsyncSession = Depends(get_session)):
        return UpdateMCPServerUseCase(
            repository=_make_repo(session),
            logger=app_logger,
            secrets_enabled=secrets_enabled,
            # mcp-tool-auto-sync FR-02/FR-08: 수정 직후 반영(비활성화 연동 포함)
            sync_use_case=_make_sync_uc(session),
            sync_timeout_sec=settings.mcp_tool_sync_timeout_sec,
        )

    def delete_factory(session: AsyncSession = Depends(get_session)):
        return DeleteMCPServerUseCase(repository=_make_repo(session), logger=app_logger)

    def test_factory(session: AsyncSession = Depends(get_session)):
        return MCPConnectionTestUseCase(repository=_make_repo(session), logger=app_logger)

    return register_factory, list_factory, update_factory, delete_factory, test_factory


_wiki_vector_stack: tuple | None = None


def get_wiki_vector_stack():
    """wiki-tree-performance D1: wiki API용 임베딩·Qdrant·벡터스토어 앱 전역 lazy 싱글턴.

    per-request 생성 시 요청마다 수 초의 클라이언트 초기화 비용 + 미해제 누수 발생
    (plan §1.2 실측). 클라이언트는 무상태(설정+커넥션 풀)이므로 동시 요청 공유 안전
    — create_agent_builder_factories가 동일 방식으로 이미 공유 운용 중.
    """
    global _wiki_vector_stack
    if _wiki_vector_stack is None:
        collection = getattr(settings, "wiki_collection_name", "wiki_knowledge")
        embedding = OpenAIEmbedding(model_name=settings.openai_embedding_model)
        qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host, port=settings.qdrant_port
        )
        vector_store = QdrantVectorStore(
            client=qdrant_client, embedding=embedding, collection_name=collection
        )
        _wiki_vector_stack = (embedding, vector_store, collection)
    return _wiki_vector_stack


_wiki_folder_summary_service = None


def get_wiki_folder_summary_service():
    """wiki-folder-summaries D2: 폴더 요약 팬아웃 서비스 (앱 전역 lazy 싱글톤).

    fire-and-forget 태스크가 자체 세션을 열므로 요청 세션과 분리된다.
    enabled=False(기본)면 kickoff가 no-op — 배선은 항상 하고 플래그로 제어.
    """
    global _wiki_folder_summary_service
    if _wiki_folder_summary_service is None:
        from src.application.wiki.folder_summary_service import (
            WikiFolderSummaryService,
        )
        from src.infrastructure.wiki.folder_summary_distiller import (
            FolderSummaryDistiller,
        )
        from src.infrastructure.wiki.folder_summary_repository import (
            MySQLWikiFolderSummaryRepository,
        )

        app_logger = get_app_logger()

        def _article_repo_builder(session: AsyncSession):
            # wiki-tree-performance D1: 무거운 클라이언트는 앱 전역 싱글턴 공유
            embedding, vector_store, wiki_collection = get_wiki_vector_stack()
            return WikiArticleRepository(
                session=session, logger=app_logger, embedding=embedding,
                vector_store=vector_store, collection_name=wiki_collection,
            )

        _wiki_folder_summary_service = WikiFolderSummaryService(
            session_factory=get_session_factory(),
            article_repo_builder=_article_repo_builder,
            folder_repo_builder=lambda s: MySQLWikiFolderSummaryRepository(
                session=s, logger=app_logger
            ),
            distiller=FolderSummaryDistiller.from_openai(
                model_name=settings.openai_llm_model,
                api_key=settings.openai_api_key,
                logger=app_logger,
                llm_provider=get_utility_llm_provider(),
            ),
            logger=app_logger,
            enabled=settings.wiki_folder_summaries_enabled,
        )
    return _wiki_folder_summary_service


def create_wiki_factories():
    """Return per-request DI factories for Wiki use cases (LLM-WIKI-001)."""
    app_logger = get_app_logger()
    # wiki-tree-performance D1: 무거운 클라이언트는 기동 시 1회 생성해 전 요청이 공유.
    # per-request 생성 시 wiki 전 엔드포인트가 요청마다 수 초를 지불했다 (plan §1.2).
    embedding, vector_store, wiki_collection = get_wiki_vector_stack()

    def _make_repo(session: AsyncSession):
        return WikiArticleRepository(
            session=session,
            logger=app_logger,
            embedding=embedding,
            vector_store=vector_store,
            collection_name=wiki_collection,
        )

    def _make_source_provider():
        es_config = ElasticsearchConfig(
            ES_HOST=settings.es_host,
            ES_PORT=settings.es_port,
            ES_SCHEME=settings.es_scheme,
        )
        es_client = ElasticsearchClient.from_config(es_config)
        es_repo = ElasticsearchRepository(client=es_client, logger=app_logger)
        return ElasticsearchWikiSourceProvider(es_repo=es_repo, logger=app_logger)

    def _make_distiller():
        return WikiDistiller.from_openai(
            model_name=settings.openai_llm_model,
            api_key=settings.openai_api_key,
            logger=app_logger,
            llm_provider=get_utility_llm_provider(),
        )

    def distill_factory(session: AsyncSession = Depends(get_session)):
        return DistillToWikiUseCase(
            repository=_make_repo(session),
            source_provider=_make_source_provider(),
            distiller=_make_distiller(),
            logger=app_logger,
        )

    def query_factory(session: AsyncSession = Depends(get_session)):
        return WikiQueryUseCase(repository=_make_repo(session))

    def review_factory(session: AsyncSession = Depends(get_session)):
        # wiki-folder-summaries D2: 승인 이벤트 → 폴더 요약 재증류 팬아웃
        return WikiReviewUseCase(
            repository=_make_repo(session), logger=app_logger,
            folder_summary_service=get_wiki_folder_summary_service(),
        )

    def human_write_factory(session: AsyncSession = Depends(get_session)):
        # wiki-user-facing: wiki·agent 두 repo는 동일 세션 (한 UseCase 한 세션)
        return HumanWikiWriteUseCase(
            wiki_repo=_make_repo(session),
            agent_repo=AgentDefinitionRepository(session=session, logger=app_logger),
            logger=app_logger,
            folder_summary_service=get_wiki_folder_summary_service(),
        )

    return distill_factory, query_factory, review_factory, human_write_factory


def create_skill_builder_factories():
    """Return per-request DI factories for Skill Builder use cases (SKILL-001)."""
    from src.application.skill_builder.create_skill_use_case import CreateSkillUseCase
    from src.application.skill_builder.get_skill_use_case import GetSkillUseCase
    from src.application.skill_builder.list_skills_use_case import ListSkillsUseCase
    from src.application.skill_builder.update_skill_use_case import UpdateSkillUseCase
    from src.application.skill_builder.delete_skill_use_case import DeleteSkillUseCase
    from src.application.skill_builder.fork_skill_use_case import ForkSkillUseCase
    from src.infrastructure.skill_builder.skill_repository import SkillRepository

    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession):
        return SkillRepository(session=session, logger=app_logger)

    def _make_dept(session: AsyncSession):
        return DepartmentRepository(session=session, logger=app_logger)

    def create_factory(session: AsyncSession = Depends(get_session)):
        return CreateSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def get_factory(session: AsyncSession = Depends(get_session)):
        return GetSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def list_factory(session: AsyncSession = Depends(get_session)):
        return ListSkillsUseCase(
            repository=_make_repo(session),
            dept_repo=_make_dept(session),
            logger=app_logger,
        )

    def update_factory(session: AsyncSession = Depends(get_session)):
        return UpdateSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def delete_factory(session: AsyncSession = Depends(get_session)):
        return DeleteSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def fork_factory(session: AsyncSession = Depends(get_session)):
        return ForkSkillUseCase(
            repository=_make_repo(session),
            dept_repo=_make_dept(session),
            logger=app_logger,
        )

    return (
        create_factory, get_factory, list_factory,
        update_factory, delete_factory, fork_factory,
    )


def create_agent_skill_factories():
    """Return per-request DI factories for agent-skill attach use cases.

    skill-agent-integration Phase A: 부착/해제/목록 UseCase.
    """
    from src.application.agent_skill.attach_skill_use_case import AttachSkillUseCase
    from src.application.agent_skill.detach_skill_use_case import DetachSkillUseCase
    from src.application.agent_skill.list_attached_skills_use_case import (
        ListAttachedSkillsUseCase,
    )
    from src.infrastructure.skill_builder.skill_repository import SkillRepository

    app_logger = get_app_logger()

    def _links(session: AsyncSession):
        return AgentSkillRepository(session=session, logger=app_logger)

    def _agents(session: AsyncSession):
        return AgentDefinitionRepository(session=session, logger=app_logger)

    def _skills(session: AsyncSession):
        return SkillRepository(session=session, logger=app_logger)

    def _dept(session: AsyncSession):
        return DepartmentRepository(session=session, logger=app_logger)

    def attach_factory(session: AsyncSession = Depends(get_session)):
        return AttachSkillUseCase(
            agent_skill_repo=_links(session),
            agent_repo=_agents(session),
            skill_repo=_skills(session),
            dept_repo=_dept(session),
            logger=app_logger,
        )

    def detach_factory(session: AsyncSession = Depends(get_session)):
        return DetachSkillUseCase(
            agent_skill_repo=_links(session),
            agent_repo=_agents(session),
            logger=app_logger,
        )

    def list_factory(session: AsyncSession = Depends(get_session)):
        return ListAttachedSkillsUseCase(
            agent_skill_repo=_links(session),
            agent_repo=_agents(session),
            dept_repo=_dept(session),
            logger=app_logger,
        )

    return attach_factory, detach_factory, list_factory


def create_middleware_agent_factories():
    """Return per-request DI factories for Middleware Agent use cases (AGENT-005)."""
    app_logger = get_app_logger()
    tool_factory = ToolFactory(
        logger=app_logger,
        tavily_api_key=os.environ.get("TAVILY_API_KEY"),
        # RunMiddlewareAgentUseCase도 create_async를 저장소 없이 호출한다 —
        # 에이전트 빌더와 동일하게 세션 스코프 저장소를 주입한다.
        mcp_tool_loader=MCPToolLoader(logger=app_logger),
        mcp_repository=SessionScopedMcpServerRepository(
            session_factory=get_session_factory(),
            logger=app_logger,
            cipher=_mcp_cipher(),
        ),
    )
    middleware_builder = MiddlewareBuilder(logger=app_logger)

    def _make_repo(session: AsyncSession):
        return MiddlewareAgentRepository(session=session)

    def create_factory(session: AsyncSession = Depends(get_session)):
        return CreateMiddlewareAgentUseCase(repository=_make_repo(session), logger=app_logger)

    def get_factory(session: AsyncSession = Depends(get_session)):
        return GetMiddlewareAgentUseCase(repository=_make_repo(session), logger=app_logger)

    def run_factory(session: AsyncSession = Depends(get_session)):
        return RunMiddlewareAgentUseCase(
            repository=_make_repo(session),
            tool_factory=tool_factory,
            middleware_builder=middleware_builder,
            logger=app_logger,
        )

    def update_factory(session: AsyncSession = Depends(get_session)):
        return UpdateMiddlewareAgentUseCase(repository=_make_repo(session), logger=app_logger)

    return create_factory, get_factory, run_factory, update_factory


def create_excel_export_use_case() -> ExcelExportUseCase:
    """Create singleton ExcelExportUseCase (stateless)."""
    app_logger = get_app_logger()
    exporter = PandasExcelExporter()
    return ExcelExportUseCase(exporter=exporter, logger=app_logger)


def create_html_to_pdf_use_case() -> HtmlToPdfUseCase:
    """Create singleton HtmlToPdfUseCase (stateless)."""
    app_logger = get_app_logger()
    converter = WeasyprintConverter()
    return HtmlToPdfUseCase(converter=converter, logger=app_logger)


def create_load_mcp_tools_factory():
    """Return per-request factory for LoadMCPToolsUseCase (agent_builder /tools)."""
    app_logger = get_app_logger()

    def _factory(session: AsyncSession = Depends(get_session)):
        mcp_repo = MCPServerRepository(session=session, logger=app_logger, cipher=_mcp_cipher())
        mcp_loader = MCPToolLoader(logger=app_logger)
        return LoadMCPToolsUseCase(
            repository=mcp_repo,
            mcp_tool_loader=mcp_loader,
            logger=app_logger,
        )

    return _factory


async def seed_internal_tools_on_startup() -> None:
    """서비스 기동 시 TOOL_REGISTRY(코드) → tool_catalog 동기화.

    내부 도구의 단일 진실원은 코드다. 부팅마다 upsert하여 UI 도구 목록이
    항상 코드와 일치한다(손수 시드 마이그레이션 불필요·드리프트 해소).
    DB-001 §10.2: get_session_factory()로 단발성 세션 획득.
    """
    from src.application.tool_catalog.sync_internal_tools_use_case import (
        SyncInternalToolsUseCase,
    )
    from src.infrastructure.tool_catalog.tool_catalog_repository import (
        ToolCatalogRepository,
    )

    app_logger = get_app_logger()
    request_id = str(uuid.uuid4())
    factory = get_session_factory()
    try:
        async with factory() as session:
            async with session.begin():
                uc = SyncInternalToolsUseCase(
                    repository=ToolCatalogRepository(
                        session=session, logger=app_logger
                    ),
                    logger=app_logger,
                )
                await uc.execute(request_id)
    except Exception as e:
        app_logger.warning(
            "Internal tool catalog sync skipped",
            request_id=request_id,
            error=str(e),
        )


async def _ensure_es_index() -> None:
    """앱 시작 시 ES 문서 인덱스 존재를 보장한다."""
    from src.infrastructure.elasticsearch.es_index_mappings import (
        DOCUMENTS_INDEX_MAPPINGS,
        DOCUMENTS_INDEX_SETTINGS,
    )

    try:
        es_config = ElasticsearchConfig(
            ES_HOST=settings.es_host,
            ES_PORT=settings.es_port,
            ES_SCHEME=settings.es_scheme,
        )
        es_client = ElasticsearchClient.from_config(es_config)
        es_repo = ElasticsearchRepository(client=es_client, logger=get_app_logger())
        try:
            created = await es_repo.ensure_index_exists(
                settings.es_index, DOCUMENTS_INDEX_MAPPINGS,
                settings=DOCUMENTS_INDEX_SETTINGS,
            )
        except Exception:
            get_app_logger().warning(
                "ES index creation with nori failed, falling back to standard analyzer",
            )
            created = await es_repo.ensure_index_exists(
                settings.es_index, DOCUMENTS_INDEX_MAPPINGS
            )
        if created:
            get_app_logger().info(
                "ES index ensured on startup", index=settings.es_index
            )
        else:
            # card-section-summary D7: 기존 인덱스에 신규 필드(summary_text 등)를
            # additive put_mapping으로 반영 (동일 매핑 재적용은 no-op — 멱등)
            try:
                await es_client.get_client().indices.put_mapping(
                    index=settings.es_index,
                    properties=DOCUMENTS_INDEX_MAPPINGS["properties"],
                )
            except Exception as e:
                get_app_logger().warning(
                    "ES put_mapping for summary fields failed", exception=e
                )
    except Exception as e:
        get_app_logger().warning(
            "ES index ensure failed on startup", exception=e
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global _document_processor, _analyze_excel_use_case, _excel_upload_use_case
    global _supervisor_excel_workflow
    global _retrieval_use_case, _hybrid_search_use_case, _chunk_index_use_case
    global _routed_retrieval_use_case
    global _morph_index_use_case, _rag_agent_use_case, _ingest_use_case
    global _doc_chunk_use_case
    global _advanced_ingest_use_case
    global _attachment_store
    global _auto_build_use_case, _auto_build_reply_use_case, _auto_build_session_repository

    # uvicorn access log 억제 (RequestLoggingMiddleware가 중복 로깅하므로)
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False

    # Startup: Initialize processor
    _document_processor = await create_processor()
    _excel_upload_use_case = create_excel_upload_use_case()
    _attachment_store = create_attachment_store()
    _retrieval_use_case = create_retrieval_use_case()
    _hybrid_search_use_case = create_hybrid_search_use_case()
    # summary-routed-retrieval: 3계층 하강 라우팅 검색 (폴백=위 하이브리드 getter)
    _routed_retrieval_use_case = create_routed_retrieval_use_case()
    _chunk_index_use_case = create_chunk_index_use_case()
    _morph_index_use_case = create_morph_index_use_case()
    _rag_agent_use_case = create_rag_agent_use_case()
    _ingest_use_case = create_ingest_use_case()
    _doc_chunk_use_case = create_doc_chunk_use_case()
    _auto_build_use_case, _auto_build_reply_use_case, _auto_build_session_repository = (
        create_auto_build_components()
    )
    _advanced_ingest_use_case = create_advanced_ingest_use_case()

    # ES 인덱스 보장 (없으면 자동 생성, 실패 시 warning만)
    await _ensure_es_index()

    # LLM Model Registry: 기본 모델 시드 등록 (중복 스킵, 실패 시 경고)
    await seed_llm_models_on_startup()
    await seed_embedding_models_on_startup()

    # 내부 도구 카탈로그 동기화 (TOOL_REGISTRY → tool_catalog, 코드가 진실원)
    await seed_internal_tools_on_startup()

    # LLM Factory: 기본 모델 조회 (시드 후 실행)
    global _default_llm_model
    _default_llm_model = await _load_default_llm_model()

    # supervisor-chart-builder-node: 엑셀 분석 워크플로우는 _default_llm_model 로드 후
    # 생성해야 chart_builder LLM 주입이 가능하다(시각화 분기 활성화).
    _analyze_excel_use_case = create_analyze_excel_use_case()

    # background-jobs D1·D13: 워커 루프 기동 (enabled=False 면 내부 no-op).
    # asyncio.create_task 는 실행 중인 이벤트 루프가 필요해 lifespan 에서 시작한다.
    if _background_job_worker is not None:
        _background_job_worker.start()

    yield

    # background-jobs D7: 루프·활성 job 취소 + failed 마킹 시도 (reconcile 이중 방어)
    if _background_job_worker is not None:
        await _background_job_worker.stop()

    # Shutdown: Cleanup (if needed)
    _document_processor = None
    _analyze_excel_use_case = None
    _supervisor_excel_workflow = None
    _excel_upload_use_case = None
    _attachment_store = None
    _retrieval_use_case = None
    _hybrid_search_use_case = None
    _routed_retrieval_use_case = None
    _chunk_index_use_case = None
    _morph_index_use_case = None
    _rag_agent_use_case = None
    _ingest_use_case = None
    _doc_chunk_use_case = None
    _auto_build_use_case = None
    _auto_build_reply_use_case = None
    _auto_build_session_repository = None
    _advanced_ingest_use_case = None


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
    app.dependency_overrides[get_routed_retrieval_use_case] = (
        get_configured_routed_retrieval_use_case
    )
    app.dependency_overrides[get_chunk_index_use_case] = get_configured_chunk_index_use_case
    app.dependency_overrides[get_morph_index_use_case] = get_configured_morph_index_use_case
    app.dependency_overrides[get_rag_agent_use_case] = get_configured_rag_agent_use_case
    app.dependency_overrides[get_conversation_use_case] = create_conversation_use_case_factory()
    app.dependency_overrides[get_history_use_case] = create_history_use_case_factory()
    app.dependency_overrides[get_general_chat_use_case] = create_general_chat_use_case_factory()
    app.dependency_overrides[get_ingest_use_case] = get_configured_ingest_use_case
    app.dependency_overrides[get_doc_chunk_use_case] = get_configured_doc_chunk_use_case
    app.dependency_overrides[get_advanced_ingest_use_case] = get_configured_advanced_ingest_use_case

    # Agent Builder DI
    (
        _create_uc, _update_uc, _run_uc, _get_uc,
        _list_agents_uc, _delete_agent_uc,
        _subscribe_uc, _fork_uc, _list_my_uc,
        _list_available_sub_agents_uc,
        _cost_calculator_singleton,  # M4 — share with pricing PATCH factory
        _build_run_agent_uc,  # agent-schedule: 트리거 UC 와 공유
    ) = create_agent_builder_factories()
    app.dependency_overrides[get_create_agent_use_case] = _create_uc
    app.dependency_overrides[get_update_agent_use_case] = _update_uc
    app.dependency_overrides[get_run_agent_use_case] = _run_uc
    app.dependency_overrides[get_get_agent_use_case] = _get_uc
    app.dependency_overrides[get_list_agents_use_case] = _list_agents_uc
    app.dependency_overrides[get_delete_agent_use_case] = _delete_agent_uc
    app.dependency_overrides[get_subscribe_use_case] = _subscribe_uc
    app.dependency_overrides[get_fork_agent_use_case] = _fork_uc
    app.dependency_overrides[get_list_my_agents_use_case] = _list_my_uc
    app.dependency_overrides[get_list_available_sub_agents_use_case] = _list_available_sub_agents_uc
    app.dependency_overrides[get_load_mcp_tools_use_case] = create_load_mcp_tools_factory()

    # Agent Webhook DI (agent-webhook Design §4-5 + M2 §4-6)
    # 스케줄 DI보다 먼저 — outbound 디스패처 싱글턴을 훅 ①에 전달해야 한다.
    (
        _wh_enable_f, _wh_get_f, _wh_rotate_f, _wh_update_f,
        _wh_disable_f, _wh_invoke_f, _wh_deliveries_f, _wh_dispatcher,
    ) = create_agent_webhook_factories(_build_run_agent_uc)
    app.dependency_overrides[get_enable_webhook_use_case] = _wh_enable_f
    app.dependency_overrides[get_get_webhook_use_case] = _wh_get_f
    app.dependency_overrides[get_rotate_webhook_use_case] = _wh_rotate_f
    app.dependency_overrides[get_update_webhook_use_case] = _wh_update_f
    app.dependency_overrides[get_disable_webhook_use_case] = _wh_disable_f
    app.dependency_overrides[get_invoke_webhook_use_case] = _wh_invoke_f
    app.dependency_overrides[get_list_webhook_deliveries_use_case] = (
        _wh_deliveries_f
    )

    # Agent Schedule DI (agent-schedule Design §6.2 + outbound 훅 ①)
    (
        _sch_create_f, _sch_list_f, _sch_get_f, _sch_update_f, _sch_delete_f,
        _sch_toggle_f, _sch_list_runs_f, _sch_trigger_f,
    ) = create_agent_schedule_factories(
        _build_run_agent_uc, outbound_dispatcher=_wh_dispatcher
    )
    app.dependency_overrides[get_create_schedule_use_case] = _sch_create_f
    app.dependency_overrides[get_list_schedules_use_case] = _sch_list_f
    app.dependency_overrides[get_get_schedule_use_case] = _sch_get_f
    app.dependency_overrides[get_update_schedule_use_case] = _sch_update_f
    app.dependency_overrides[get_delete_schedule_use_case] = _sch_delete_f
    app.dependency_overrides[get_toggle_schedule_use_case] = _sch_toggle_f
    app.dependency_overrides[get_list_schedule_runs_use_case] = _sch_list_runs_f
    app.dependency_overrides[get_trigger_due_schedules_use_case] = _sch_trigger_f

    # Approval Gate DI (approval-gate Design §2.1 / §4)
    (
        _ap_decide_f, _ap_list_f, _ap_tick_f, _ap_repo_factory,
        _ap_gate_settings_f,
    ) = create_approval_factories(_build_run_agent_uc)
    app.dependency_overrides[get_gate_settings_use_case] = _ap_gate_settings_f
    app.dependency_overrides[get_decide_approval_use_case] = _ap_decide_f
    app.dependency_overrides[get_list_approvals_use_case] = _ap_list_f
    app.dependency_overrides[get_execute_due_approvals_use_case] = _ap_tick_f
    # internal tick 은 스케줄 트리거와 같은 토큰 검증을 쓴다 — 인증 없이
    # 집행을 트리거할 수 있으면 게이트가 무의미해진다.
    app.dependency_overrides[approval_verify_scheduler_token] = (
        schedule_verify_scheduler_token
    )

    # Background Job DI (background-jobs Design §4-5)
    # 스케줄 DI 이후 — 워커의 내장 스케줄러 틱(D1)이 트리거 싱글턴을 공유한다.
    global _background_job_worker
    (
        _bj_enqueue_f, _bj_list_f, _bj_get_f, _bj_unseen_f,
        _bj_seen_f, _bj_seen_all_f, _bj_sch_runs_f,
        _bj_delete_f, _bj_cleanup_f, _bj_my_sch_f, _background_job_worker,
    ) = create_background_job_factories(
        _build_run_agent_uc,
        outbound_dispatcher=_wh_dispatcher,
        schedule_trigger_uc=_sch_trigger_f(),
        # approval-gate Check G5: 승인 팩토리의 tick 싱글턴을 워커가 공유
        approval_tick_runner=_ap_tick_f(),
    )
    app.dependency_overrides[get_enqueue_job_use_case] = _bj_enqueue_f
    app.dependency_overrides[get_list_jobs_use_case] = _bj_list_f
    app.dependency_overrides[get_get_job_use_case] = _bj_get_f
    app.dependency_overrides[get_count_unseen_use_case] = _bj_unseen_f
    app.dependency_overrides[get_mark_seen_use_case] = _bj_seen_f
    app.dependency_overrides[get_mark_all_seen_use_case] = _bj_seen_all_f
    app.dependency_overrides[get_list_my_schedule_runs_use_case] = _bj_sch_runs_f
    app.dependency_overrides[get_delete_job_use_case] = _bj_delete_f
    app.dependency_overrides[get_cleanup_jobs_use_case] = _bj_cleanup_f
    app.dependency_overrides[get_list_my_schedules_use_case] = _bj_my_sch_f

    # document-template-extractor Design §6: extract/refine/files DI
    _de_extract_f, _de_refine_f = create_document_extractor_factories()
    app.dependency_overrides[get_extract_document_use_case] = _de_extract_f
    app.dependency_overrides[get_refine_slots_use_case] = _de_refine_f
    app.dependency_overrides[get_document_attachment_store] = (
        lambda: _attachment_store
    )

    # Department DI
    (
        _dept_list_f, _dept_create_f, _dept_update_f,
        _dept_delete_f, _dept_assign_f, _dept_remove_f,
    ) = create_department_factories()
    app.dependency_overrides[get_list_departments_use_case] = _dept_list_f
    app.dependency_overrides[get_create_department_use_case] = _dept_create_f
    app.dependency_overrides[get_update_department_use_case] = _dept_update_f
    app.dependency_overrides[get_delete_department_use_case] = _dept_delete_f
    app.dependency_overrides[get_assign_user_department_use_case] = _dept_assign_f
    app.dependency_overrides[get_remove_user_department_use_case] = _dept_remove_f

    # Tool Catalog DI
    (
        _tc_list_f, _tc_sync_f, _tc_builtin_f, _tc_meta_f,
    ) = create_tool_catalog_factories()
    app.dependency_overrides[get_list_tool_catalog_use_case] = _tc_list_f
    app.dependency_overrides[get_sync_mcp_tools_use_case] = _tc_sync_f
    app.dependency_overrides[get_set_builtin_use_case] = _tc_builtin_f
    # mcp-tool-category-routing §4.2 (FR-13)
    app.dependency_overrides[get_update_tool_metadata_use_case] = _tc_meta_f

    # Middleware Catalog DI (builtin-middleware D4)
    _mw_list_f, _mw_flags_f = create_middleware_catalog_factories()
    app.dependency_overrides[get_list_middleware_catalog_use_case] = _mw_list_f
    app.dependency_overrides[get_set_middleware_flags_use_case] = _mw_flags_f

    # Agent Composer DI (nl-agent-composer)
    _compose_f = create_agent_composer_factories()
    app.dependency_overrides[get_compose_agent_use_case] = _compose_f

    # Prompt Composer DI (prompt-composer Design §9.4)
    # None이면 라우터를 등록하지 않는다 — 부가 기능이므로 조립 실패가 기동을 막지 않는다.
    _prompt_f = create_prompt_composer_factory()
    if _prompt_f is not None:
        app.dependency_overrides[get_prompt_composer_use_case] = _prompt_f
        # agent-create-wizard §4.5 — 같은 라우터의 사람 편집본 저장 경로
        app.dependency_overrides[get_append_human_version_use_case] = (
            create_append_human_version_factory()
        )
        app.include_router(prompt_composer_router)

    # Auto Agent Builder DI
    app.dependency_overrides[get_auto_build_use_case] = get_configured_auto_build_use_case
    app.dependency_overrides[get_auto_build_reply_use_case] = get_configured_auto_build_reply_use_case
    app.dependency_overrides[get_auto_build_session_repository] = get_configured_auto_build_session_repository
    app.dependency_overrides[get_auto_build_create_agent_uc] = create_middleware_agent_use_case_factory()

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

    # expose-user-department: /me 부서 노출 — DepartmentRepository per-request 재사용
    def _user_departments_f(session: AsyncSession = Depends(get_session)):
        return GetUserDepartmentsUseCase(
            repository=DepartmentRepository(session=session, logger=get_app_logger()),
            logger=get_app_logger(),
        )

    app.dependency_overrides[get_user_departments_use_case] = _user_departments_f

    # Auth Context DI (agent-user-context Design §6.1 + §6.4)
    (
        _assemble_f, _grant_f, _revoke_f, _perm_repo_f,
    ) = create_auth_context_factories()
    app.dependency_overrides[get_assemble_auth_context_use_case] = _assemble_f
    app.dependency_overrides[get_grant_permission_use_case] = _grant_f
    app.dependency_overrides[get_revoke_permission_use_case] = _revoke_f
    app.dependency_overrides[get_permission_repository] = _perm_repo_f

    # Admin User Management DI (admin-user-registration Design §5.2)
    _admin_create_user_f, _list_users_f = create_admin_user_mgmt_factories()
    app.dependency_overrides[get_admin_create_user_use_case] = _admin_create_user_f
    app.dependency_overrides[get_list_users_use_case] = _list_users_f

    # WebSocket DI
    _connection_manager = ConnectionManager(logger=logger, max_connections=100)
    app.dependency_overrides[get_connection_manager] = lambda: _connection_manager
    app.dependency_overrides[get_ws_jwt_adapter] = _jwt_f
    app.dependency_overrides[get_ws_user_repository] = _user_repo_f
    # Reuse the HTTP RunAgentUseCase factory for WS /ws/agent/{run_id}
    # (Design fe-websocket-integration-guide §4.2 — same factory, no new instance).
    app.dependency_overrides[get_ws_run_agent_use_case] = _run_uc

    # fix-ws-auth-context-missing Design §3.3.2: WS AuthContext 조립기 + logger
    # — system prompt에 [현재 사용자 정보] 블록이 들어가도록 auth_ctx를 stream에 전달.
    _ws_auth_resolver = create_ws_auth_context_resolver()
    app.dependency_overrides[get_ws_auth_context_resolver] = lambda: _ws_auth_resolver
    app.dependency_overrides[get_ws_logger] = lambda: logger

    # ws-agent-excel-attachment: 업로드 UC + WS 첨부 resolver DI
    app.dependency_overrides[get_upload_attachment_use_case] = (
        get_configured_upload_attachment_use_case
    )
    app.dependency_overrides[get_ws_attachment_resolver] = (
        get_configured_ws_attachment_resolver
    )

    # intent-analyzer Design §2.1 — 독립 모듈. 기존 그래프에는 배선하지 않는다(Plan D8).
    # 어댑터 1개를 앱 수명 동안 재사용한다 (위키 app-lifetime-client-singleton).
    _intent_use_case = AnalyzeIntentUseCase(
        analyzer=LLMIntentAnalyzerAdapter(
            logger=logger, llm_provider=get_utility_llm_provider()
        )
    )
    app.dependency_overrides[get_analyze_intent_use_case] = lambda: _intent_use_case

    # Agent Create Pipeline DI (agent-create-pipeline Design §9)
    # 킬스위치 off 또는 prompt-composer 미가동이면 등록하지 않는다 (탈착형 낙하).
    # 여기(DI 섹션)서의 include 가 곧 라우트 우선순위다 — agent_builder 의
    # /{agent_id} 계열(5100줄대 블록)보다 먼저 등록되어 /pipeline 이 삼켜지지
    # 않는다 (Design §4.1). 협력자 재사용: _intent_use_case(위 싱글턴),
    # _prompt_f(ComposePromptUseCase), _create_uc(CreateAgentUseCase).
    from src.application.agent_create_pipeline.use_case import (
        AgentCreatePipelineUseCase,
    )
    from src.infrastructure.agent_create_pipeline.adapters import (
        CatalogCandidateReader,
    )
    from src.infrastructure.config.agent_create_pipeline_config import (
        AgentPipelineConfig,
    )
    from src.infrastructure.config.intent_config import IntentConfig

    _pipeline_cfg = AgentPipelineConfig()
    if _pipeline_cfg.AGENT_PIPELINE_ENABLED and _prompt_f is not None:
        _pipeline_selector = _build_pipeline_tool_selector(_pipeline_cfg)
        # 되묻기 상한의 단일 출처는 INTENT_* config 다 (Analysis G-02/G-03) —
        # 어댑터 프롬프트의 "남은 라운드"와 파이프라인 재clamp 가 같은 값을 본다.
        _pipeline_limits = IntentConfig().slot_limits()

        def _pipeline_factory(
            session: AsyncSession = Depends(get_session),
            compose_uc=Depends(_prompt_f),
            create_uc=Depends(_create_uc),
        ):
            # Depends 체인이 요청당 단일 세션을 공유한다 (DB-001 §10.4).
            return AgentCreatePipelineUseCase(
                intent_use_case=_intent_use_case,
                candidate_reader=CatalogCandidateReader(
                    repository=ToolCatalogRepository(
                        session=session, logger=logger
                    ),
                    logger=logger,
                ),
                tool_selector=_pipeline_selector,
                compose_use_case=compose_uc,
                create_agent_use_case=create_uc,
                logger=logger,
                limits=_pipeline_limits,
            )

        app.dependency_overrides[get_agent_pipeline_use_case] = _pipeline_factory
        app.include_router(agent_pipeline_router)
    else:
        logger.info(
            "Agent pipeline disabled — router not registered",
            enabled=_pipeline_cfg.AGENT_PIPELINE_ENABLED,
            prompt_composer_ready=_prompt_f is not None,
        )

    # ws-chat-streaming Design §4.4: in-memory ChatStreamCache + reuse GeneralChat factory.
    _chat_stream_cache = InMemoryChatStreamCache(ttl_seconds=300, max_sessions=1000)
    app.dependency_overrides[get_chat_stream_cache] = lambda: _chat_stream_cache
    app.dependency_overrides[get_ws_general_chat_use_case] = (
        create_general_chat_use_case_factory()
    )

    # LLM Model Registry DI (★ M4: + pricing PATCH factory with cost_calculator)
    (
        _llm_create_f,
        _llm_update_f,
        _llm_deactivate_f,
        _llm_get_f,
        _llm_list_f,
        _llm_pricing_f,
    ) = create_llm_model_factories(
        cost_calculator=_cost_calculator_singleton,
        # admin-default-llm-routing AD-3: 관리자 모델 변경 4경로가 보조 LLM
        # 해석 캐시를 무효화한다 → 재시작 없이 다음 요청부터 반영된다.
        llm_provider=get_utility_llm_provider(),
    )
    app.dependency_overrides[get_create_llm_model_use_case] = _llm_create_f
    app.dependency_overrides[get_update_llm_model_use_case] = _llm_update_f
    app.dependency_overrides[get_deactivate_llm_model_use_case] = _llm_deactivate_f
    app.dependency_overrides[get_get_llm_model_use_case] = _llm_get_f
    app.dependency_overrides[get_list_llm_models_use_case] = _llm_list_f
    app.dependency_overrides[get_update_llm_model_pricing_use_case] = _llm_pricing_f

    # Agent Run Observability DI (M4 + M5 + M5-dashboard)
    (
        _run_detail_f,
        _usage_by_user_f,
        _usage_by_llm_f,
        _usage_by_node_f,
        _usage_me_f,
        _list_runs_f,                # ★ M5
        _list_my_runs_f,             # ★ M5 dashboard
        _usage_summary_f,            # ★ M5 dashboard
        _usage_timeseries_f,         # ★ M5 dashboard
        _my_usage_timeseries_f,      # ★ M5 dashboard
        _message_retrievals_f,       # ★ retrieval-observability
    ) = create_agent_run_factories()
    app.dependency_overrides[get_run_detail_use_case] = _run_detail_f
    app.dependency_overrides[get_usage_by_user_use_case] = _usage_by_user_f
    app.dependency_overrides[get_usage_by_llm_use_case] = _usage_by_llm_f
    app.dependency_overrides[get_usage_by_node_use_case] = _usage_by_node_f
    app.dependency_overrides[get_usage_me_use_case] = _usage_me_f
    app.dependency_overrides[get_list_runs_use_case] = _list_runs_f
    app.dependency_overrides[get_list_my_runs_use_case] = _list_my_runs_f
    app.dependency_overrides[get_usage_summary_use_case] = _usage_summary_f
    app.dependency_overrides[get_usage_timeseries_use_case] = _usage_timeseries_f
    app.dependency_overrides[get_my_usage_timeseries_use_case] = _my_usage_timeseries_f
    app.dependency_overrides[get_message_retrievals_use_case] = _message_retrievals_f

    # Admin Dashboard DI (admin-dashboard Design D2)
    (
        _dash_stats_f,
        _dash_kb_breakdown_f,
        _dash_recent_docs_f,
        _dash_health_f,
    ) = create_admin_dashboard_factories()
    app.dependency_overrides[get_dashboard_stats_use_case] = _dash_stats_f
    app.dependency_overrides[get_kb_breakdown_use_case] = _dash_kb_breakdown_f
    app.dependency_overrides[get_recent_documents_use_case] = _dash_recent_docs_f
    app.dependency_overrides[get_storage_health_use_case] = _dash_health_f

    # Embedding Model Registry DI
    (_emb_list_f,) = create_embedding_model_factories()
    app.dependency_overrides[get_list_embedding_models_use_case] = _emb_list_f

    # MCP Registry DI
    (
        _mcp_register_f, _mcp_list_f, _mcp_update_f, _mcp_delete_f, _mcp_test_f,
    ) = create_mcp_registry_factories()
    app.dependency_overrides[get_mcp_register_use_case] = _mcp_register_f
    app.dependency_overrides[get_mcp_list_use_case] = _mcp_list_f
    app.dependency_overrides[get_mcp_update_use_case] = _mcp_update_f
    app.dependency_overrides[get_mcp_delete_use_case] = _mcp_delete_f

    # Wiki DI (LLM-WIKI-001 + wiki-user-facing)
    (
        _wiki_distill_f, _wiki_query_f, _wiki_review_f, _wiki_human_write_f,
    ) = create_wiki_factories()
    app.dependency_overrides[get_wiki_distill_use_case] = _wiki_distill_f
    app.dependency_overrides[get_wiki_query_use_case] = _wiki_query_f
    app.dependency_overrides[get_wiki_review_use_case] = _wiki_review_f
    app.dependency_overrides[get_wiki_human_write_use_case] = _wiki_human_write_f
    app.dependency_overrides[get_mcp_test_use_case] = _mcp_test_f

    # Memory DI (agent-memory)
    _memory_crud_f = create_memory_factories()
    app.dependency_overrides[get_memory_crud_use_case] = _memory_crud_f

    # Eval Gate DI (agent-eval-gate)
    def _eval_submit_f(session: AsyncSession = Depends(get_session)):
        # eval/wiki-feedback-loop: off여도 주입은 항상(코드 경로 단일화)
        return SubmitFeedbackUseCase(
            feedback_repo=MessageFeedbackRepository(session, get_app_logger()),
            message_repo=SQLAlchemyConversationMessageRepository(session),
            logger=get_app_logger(),
            extraction=get_memory_extraction_service(),
            wiki_feedback=get_feedback_wiki_service(),
        )

    def _eval_get_f(session: AsyncSession = Depends(get_session)):
        return GetFeedbackUseCase(
            feedback_repo=MessageFeedbackRepository(session, get_app_logger())
        )

    def _eval_delete_f(session: AsyncSession = Depends(get_session)):
        return DeleteFeedbackUseCase(
            feedback_repo=MessageFeedbackRepository(session, get_app_logger())
        )

    def _eval_stats_f(session: AsyncSession = Depends(get_session)):
        return AgentEvalStatsUseCase(
            feedback_repo=MessageFeedbackRepository(session, get_app_logger()),
            recent_negative_limit=settings.eval_recent_negative_limit,
        )

    app.dependency_overrides[get_submit_feedback_use_case] = _eval_submit_f
    app.dependency_overrides[get_get_feedback_use_case] = _eval_get_f
    app.dependency_overrides[get_delete_feedback_use_case] = _eval_delete_f
    app.dependency_overrides[get_agent_eval_stats_use_case] = _eval_stats_f

    # Skill Builder DI
    (
        _skill_create_f, _skill_get_f, _skill_list_f,
        _skill_update_f, _skill_delete_f, _skill_fork_f,
    ) = create_skill_builder_factories()
    app.dependency_overrides[get_create_skill_use_case] = _skill_create_f
    app.dependency_overrides[get_get_skill_use_case] = _skill_get_f
    app.dependency_overrides[get_list_skills_use_case] = _skill_list_f
    app.dependency_overrides[get_update_skill_use_case] = _skill_update_f
    app.dependency_overrides[get_delete_skill_use_case] = _skill_delete_f
    app.dependency_overrides[get_fork_skill_use_case] = _skill_fork_f

    # Agent-Skill Attach DI (skill-agent-integration Phase A)
    (
        _agent_skill_attach_f, _agent_skill_detach_f, _agent_skill_list_f,
    ) = create_agent_skill_factories()
    app.dependency_overrides[get_attach_skill_use_case] = _agent_skill_attach_f
    app.dependency_overrides[get_detach_skill_use_case] = _agent_skill_detach_f
    app.dependency_overrides[get_list_attached_skills_use_case] = _agent_skill_list_f

    # Middleware Agent DI
    (
        _mw_create_f, _mw_get_f, _mw_run_f, _mw_update_f,
    ) = create_middleware_agent_factories()
    app.dependency_overrides[get_mw_create_use_case] = _mw_create_f
    app.dependency_overrides[get_mw_get_use_case] = _mw_get_f
    app.dependency_overrides[get_mw_run_use_case] = _mw_run_f
    app.dependency_overrides[get_mw_update_use_case] = _mw_update_f

    # Collection Management DI (per-request — session 필요)
    _collection_uc_factory, _activity_log_service_factory = create_collection_factories()
    app.dependency_overrides[get_collection_use_case] = _collection_uc_factory
    app.dependency_overrides[get_collection_activity_log_service] = _activity_log_service_factory

    # Unified Upload DI (per-request — session 필요)
    _unified_upload_uc_factory = create_unified_upload_factories()
    app.dependency_overrides[get_unified_upload_use_case] = _unified_upload_uc_factory
    # Section Summary DI (card-section-summary — launcher는 싱글턴, query는 per-request)
    _section_summary_launcher, _section_summary_query_factory = (
        create_section_summary_components()
    )
    _kb_uc_factory, _kb_upload_factory, _kb_documents_factory = (
        create_knowledge_base_factories(
            _unified_upload_uc_factory, _section_summary_launcher
        )
    )
    app.dependency_overrides[get_knowledge_base_use_case] = _kb_uc_factory
    app.dependency_overrides[get_kb_upload_use_case] = _kb_upload_factory
    app.dependency_overrides[get_list_kb_documents_use_case] = (
        _kb_documents_factory
    )
    app.dependency_overrides[get_section_summary_query_use_case] = (
        _section_summary_query_factory
    )
    # KB 저장 내용 조회 DI (kb-content-browser)
    _kb_summary_factory, _kb_sections_factory, _kb_chunks_factory = (
        create_kb_browse_factories(_kb_uc_factory)
    )
    app.dependency_overrides[get_kb_document_summary_use_case] = (
        _kb_summary_factory
    )
    app.dependency_overrides[get_kb_section_summaries_use_case] = (
        _kb_sections_factory
    )
    app.dependency_overrides[get_kb_document_chunks_use_case] = (
        _kb_chunks_factory
    )
    # KB 검색/히스토리 DI (kb-retrieval-test)
    _kb_search_factory, _kb_search_history_factory = (
        create_kb_search_factories(_kb_uc_factory)
    )
    app.dependency_overrides[get_kb_search_use_case] = _kb_search_factory
    app.dependency_overrides[get_kb_search_history_use_case] = (
        _kb_search_history_factory
    )

    # Chunking Profile DI (clause-aware-chunking)
    _chunking_profile_factory = create_chunking_profile_factories()
    app.dependency_overrides[get_chunking_profile_use_case] = _chunking_profile_factory

    # Preview Router DI
    _preview_parser = ParserFactory.create_from_string("pymupdf4llm")
    app.dependency_overrides[get_preview_parser] = lambda: _preview_parser
    _preview_upload_uc_factory = create_unified_upload_factories()
    app.dependency_overrides[get_preview_upload_use_case] = _preview_upload_uc_factory

    # Collection Search DI (per-request — session 필요)
    _search_uc_factory, _history_uc_factory = create_collection_search_factories()
    app.dependency_overrides[get_collection_search_use_case] = _search_uc_factory
    app.dependency_overrides[get_search_history_use_case] = _history_uc_factory

    # Excel Export DI (singleton)
    _excel_export_uc = create_excel_export_use_case()
    app.dependency_overrides[get_excel_export_uc] = lambda: _excel_export_uc

    # PDF Export DI (singleton)
    _html_to_pdf_uc = create_html_to_pdf_use_case()
    app.dependency_overrides[get_html_to_pdf_uc] = lambda: _html_to_pdf_uc

    # RAG Tool Router DI
    _rag_tool_qdrant = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )
    app.dependency_overrides[rag_tool_get_qdrant_client] = lambda: _rag_tool_qdrant
    app.dependency_overrides[rag_tool_get_aliases] = lambda: getattr(settings, "collection_aliases", {})

    def _rag_tool_perm_service_factory(
        session: AsyncSession = Depends(get_session),
    ):
        from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
        from src.application.collection.permission_service import CollectionPermissionService
        from src.domain.collection.permission_policy import CollectionPermissionPolicy
        from src.infrastructure.department.department_repository import DepartmentRepository
        perm_repo = CollectionPermissionRepository(session, logger)
        dept_repo = DepartmentRepository(session, logger)
        return CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=logger,
        )

    app.dependency_overrides[rag_tool_get_perm_service] = _rag_tool_perm_service_factory

    # Doc Browse DI (per-request, MySQL-based)
    def _list_documents_uc_factory(
        session: AsyncSession = Depends(get_session),
    ):
        from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository
        repo = DocumentMetadataRepository(
            session=session,
            logger=StructuredLogger("doc_browse.metadata_repo"),
        )
        return ListDocumentsUseCase(
            document_metadata_repo=repo,
            logger=StructuredLogger("doc_browse.list"),
        )

    def _get_chunks_uc_factory():
        return GetChunksUseCase(
            qdrant_client=AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            ),
            logger=StructuredLogger("doc_browse.chunks"),
        )

    def _delete_document_uc_factory(
        session: AsyncSession = Depends(get_session),
    ):
        from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository
        from src.infrastructure.collection.activity_log_repository import ActivityLogRepository
        from src.infrastructure.collection.permission_repository import CollectionPermissionRepository
        from src.infrastructure.department.department_repository import DepartmentRepository
        from src.application.collection.permission_service import CollectionPermissionService
        from src.application.collection.activity_log_service import ActivityLogService
        from src.domain.collection.permission_policy import CollectionPermissionPolicy
        from src.domain.doc_browse.policies import DocumentDeletePolicy

        metadata_repo = DocumentMetadataRepository(
            session=session,
            logger=StructuredLogger("doc_browse.metadata_repo"),
        )
        log_repo = ActivityLogRepository(session, StructuredLogger("doc_browse.activity_log"))
        log_service = ActivityLogService(log_repo, StructuredLogger("doc_browse.activity_log"))
        perm_repo = CollectionPermissionRepository(session, StructuredLogger("doc_browse.perm"))
        dept_repo = DepartmentRepository(session, StructuredLogger("doc_browse.dept"))
        perm_service = CollectionPermissionService(
            perm_repo=perm_repo,
            dept_repo=dept_repo,
            policy=CollectionPermissionPolicy(),
            logger=StructuredLogger("doc_browse.perm_service"),
        )

        es_config_local = ElasticsearchConfig(
            ES_HOST=settings.es_host,
            ES_PORT=settings.es_port,
            ES_SCHEME=settings.es_scheme,
        )
        es_client_local = ElasticsearchClient.from_config(es_config_local)
        es_repo_local = ElasticsearchRepository(client=es_client_local, logger=StructuredLogger("doc_browse.es"))

        return DeleteDocumentUseCase(
            document_metadata_repo=metadata_repo,
            qdrant_client=AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            ),
            es_repo=es_repo_local,
            es_index=settings.es_index,
            permission_service=perm_service,
            activity_log_service=log_service,
            policy=DocumentDeletePolicy(),
            logger=StructuredLogger("doc_browse.delete"),
        )

    app.dependency_overrides[get_list_documents_use_case] = _list_documents_uc_factory
    app.dependency_overrides[get_chunks_use_case] = _get_chunks_uc_factory
    app.dependency_overrides[get_delete_document_use_case] = _delete_document_uc_factory

    # RAGAS Evaluation DI (eval-hub: agent 헤드리스 실행기 공유)
    (
        _ragas_batch_f, _ragas_realtime_f,
        _ragas_result_f, _ragas_testset_f, _ragas_admin_f,
        _ragas_generate_f,
        _sweep_create_f, _sweep_estimate_f,
        _sweep_detail_f, _sweep_list_f, _sweep_delete_f,
    ) = create_ragas_factories(_build_run_agent_uc)
    app.dependency_overrides[get_batch_eval_use_case] = _ragas_batch_f
    app.dependency_overrides[get_realtime_eval_use_case] = _ragas_realtime_f
    app.dependency_overrides[get_eval_result_use_case] = _ragas_result_f
    app.dependency_overrides[get_testset_use_case] = _ragas_testset_f
    app.dependency_overrides[get_testset_generate_use_case] = _ragas_generate_f
    app.dependency_overrides[get_admin_eval_use_case] = _ragas_admin_f
    # agent-model-benchmark module-5: 모델 스윕
    app.dependency_overrides[get_create_sweep_use_case] = _sweep_create_f
    app.dependency_overrides[get_estimate_sweep_use_case] = _sweep_estimate_f
    app.dependency_overrides[get_sweep_detail_use_case] = _sweep_detail_f
    app.dependency_overrides[get_list_sweeps_use_case] = _sweep_list_f
    app.dependency_overrides[get_delete_sweep_use_case] = _sweep_delete_f

    # Include routers
    app.include_router(document_router)
    app.include_router(analysis_router)
    app.include_router(excel_upload_router)
    app.include_router(agent_attachment_router)
    app.include_router(intent_router)
    app.include_router(document_extractor_router)
    app.include_router(retrieval_router)
    app.include_router(routed_retrieval_router)
    app.include_router(hybrid_search_router)
    app.include_router(chunk_index_router)
    app.include_router(morph_index_router)
    app.include_router(rag_agent_router)
    app.include_router(conversation_router)
    app.include_router(conversation_history_router)
    app.include_router(ingest_router)
    app.include_router(doc_chunk_router)
    app.include_router(agent_builder_router)
    app.include_router(agent_schedule_router)
    app.include_router(agent_schedule_trigger_router)
    app.include_router(approval_router)
    app.include_router(approval_internal_router)
    app.include_router(approval_agent_gate_router)
    app.include_router(background_job_router)
    app.include_router(agent_webhook_router)
    app.include_router(webhook_public_router)
    app.include_router(rag_tool_router)
    app.include_router(department_router)
    app.include_router(tool_catalog_router)
    app.include_router(middleware_catalog_router)
    app.include_router(agent_composer_router)
    app.include_router(auto_agent_builder_router)
    app.include_router(general_chat_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(admin_ragas_router)
    app.include_router(llm_model_router)
    app.include_router(embedding_model_router)
    app.include_router(mcp_registry_router)
    app.include_router(wiki_router)
    app.include_router(memory_router)
    app.include_router(eval_router)
    app.include_router(skill_builder_router)
    app.include_router(middleware_agent_router)
    app.include_router(collection_router)
    app.include_router(doc_browse_router)
    app.include_router(excel_export_router)
    app.include_router(pdf_export_router)
    app.include_router(unified_upload_router)
    app.include_router(knowledge_base_router)
    app.include_router(admin_collection_router)
    app.include_router(admin_chunking_router)
    app.include_router(chunking_profile_router)
    app.include_router(collection_search_router)
    app.include_router(ragas_router)
    app.include_router(preview_router)
    # multimodal-extractor: DI + /api/v1/admin/multimodal 라우터 (preview 라우터 선등록 후)
    from src.api.multimodal_di import wire_multimodal

    wire_multimodal(
        app, get_session=get_session, llm_factory=_llm_factory, logger=get_app_logger()
    )
    # golden-sample-blueprint: DI + /api/v1/admin/blueprints 라우터 (multimodal 레지스트리 재사용)
    from src.api.blueprint_di import wire_blueprint

    wire_blueprint(
        app,
        get_session=get_session,
        llm_factory=_llm_factory,
        logger=get_app_logger(),
        settings=settings,
    )
    app.include_router(advanced_ingest_router)
    app.include_router(ws_router)
    app.include_router(agent_run_router)  # M4 — observability read APIs
    app.include_router(admin_user_router)  # agent-user-context: admin permission mgmt
    app.include_router(admin_dashboard_router)  # admin-dashboard: 운영 현황

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
