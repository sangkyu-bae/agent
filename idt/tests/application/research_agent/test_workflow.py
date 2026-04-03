"""Tests for SelfCorrectiveRAGWorkflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.research_agent.workflow import (
    SelfCorrectiveRAGWorkflow,
    create_initial_state,
)
from src.domain.research_agent.value_objects import (
    RouteDecision,
    RouteType,
    RelevanceResult,
)
from src.domain.research_agent.policy import RoutingPolicy
from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.domain.query_rewrite.value_objects import RewrittenQuery


class TestCreateInitialState:
    """Tests for create_initial_state function."""

    def test_creates_state_with_question_and_request_id(self) -> None:
        """Should create initial state with question and request_id."""
        state = create_initial_state(
            question="테스트 질문입니다",
            request_id="test-req-123"
        )

        assert state["question"] == "테스트 질문입니다"
        assert state["request_id"] == "test-req-123"

    def test_initializes_retry_count_to_zero(self) -> None:
        """Should initialize retry_count to 0."""
        state = create_initial_state(question="질문", request_id="req-1")
        assert state["retry_count"] == 0

    def test_initializes_optional_fields_to_none(self) -> None:
        """Should initialize optional fields to None."""
        state = create_initial_state(question="질문", request_id="req-1")

        assert state["route"] is None
        assert state["route_reason"] is None
        assert state["generation"] is None
        assert state["is_hallucinated"] is None
        assert state["is_relevant"] is None
        assert state["transformed_query"] is None
        assert state["web_search_results"] is None

    def test_initializes_lists_to_empty(self) -> None:
        """Should initialize list fields to empty lists."""
        state = create_initial_state(question="질문", request_id="req-1")

        assert state["documents"] == []
        assert state["errors"] == []

    def test_initializes_status_to_routing(self) -> None:
        """Should initialize status to 'routing'."""
        state = create_initial_state(question="질문", request_id="req-1")
        assert state["status"] == "routing"


class TestSelfCorrectiveRAGWorkflow:
    """Tests for SelfCorrectiveRAGWorkflow."""

    @pytest.fixture
    def mock_router(self) -> AsyncMock:
        """Create mock router adapter."""
        mock = AsyncMock()
        mock.route = AsyncMock()
        return mock

    @pytest.fixture
    def mock_generator(self) -> AsyncMock:
        """Create mock generator adapter."""
        mock = AsyncMock()
        mock.generate = AsyncMock()
        return mock

    @pytest.fixture
    def mock_relevance_evaluator(self) -> AsyncMock:
        """Create mock relevance evaluator adapter."""
        mock = AsyncMock()
        mock.evaluate = AsyncMock()
        return mock

    @pytest.fixture
    def mock_hallucination_use_case(self) -> AsyncMock:
        """Create mock hallucination use case."""
        mock = AsyncMock()
        mock.evaluate = AsyncMock()
        return mock

    @pytest.fixture
    def mock_query_rewriter_use_case(self) -> AsyncMock:
        """Create mock query rewriter use case."""
        mock = AsyncMock()
        mock.rewrite = AsyncMock()
        return mock

    @pytest.fixture
    def mock_web_search_use_case(self) -> MagicMock:
        """Create mock web search use case."""
        mock = MagicMock()
        mock.get_context = MagicMock()
        return mock

    @pytest.fixture
    def mock_retriever(self) -> MagicMock:
        """Create mock retriever."""
        mock = MagicMock()
        mock.return_value = ["Mock document content for testing."]
        return mock

    @pytest.fixture
    def workflow(
        self,
        mock_router: AsyncMock,
        mock_generator: AsyncMock,
        mock_relevance_evaluator: AsyncMock,
        mock_hallucination_use_case: AsyncMock,
        mock_query_rewriter_use_case: AsyncMock,
        mock_web_search_use_case: MagicMock,
        mock_retriever: MagicMock,
    ) -> SelfCorrectiveRAGWorkflow:
        """Create workflow with mocked dependencies."""
        return SelfCorrectiveRAGWorkflow(
            router_adapter=mock_router,
            generator_adapter=mock_generator,
            relevance_evaluator_adapter=mock_relevance_evaluator,
            hallucination_use_case=mock_hallucination_use_case,
            query_rewriter_use_case=mock_query_rewriter_use_case,
            web_search_use_case=mock_web_search_use_case,
            retriever=mock_retriever,
        )

    async def test_normal_rag_flow_completes_successfully(
        self,
        workflow: SelfCorrectiveRAGWorkflow,
        mock_router: AsyncMock,
        mock_generator: AsyncMock,
        mock_relevance_evaluator: AsyncMock,
        mock_hallucination_use_case: AsyncMock,
    ) -> None:
        """Normal RAG flow should complete with relevant non-hallucinated answer."""
        mock_router.route.return_value = RouteDecision(
            route=RouteType.RAG, reason="Document query"
        )
        mock_generator.generate.return_value = "정확한 답변입니다."
        mock_hallucination_use_case.evaluate.return_value = HallucinationEvaluationResult(
            is_hallucinated=False
        )
        mock_relevance_evaluator.evaluate.return_value = RelevanceResult(
            is_relevant=True
        )

        result = await workflow.run(
            question="회사 정책은 무엇인가요?",
            request_id="test-normal-001"
        )

        assert result["status"] == "completed"
        assert result["generation"] == "정확한 답변입니다."
        assert result["is_hallucinated"] is False
        assert result["is_relevant"] is True
        assert result["retry_count"] == 0

    async def test_web_search_route_when_keyword_detected(
        self,
        workflow: SelfCorrectiveRAGWorkflow,
        mock_router: AsyncMock,
        mock_generator: AsyncMock,
        mock_relevance_evaluator: AsyncMock,
        mock_hallucination_use_case: AsyncMock,
        mock_web_search_use_case: MagicMock,
    ) -> None:
        """Should route to web search when web search keywords detected."""
        mock_router.route.return_value = RouteDecision(
            route=RouteType.WEB_SEARCH, reason="Current events"
        )
        mock_web_search_use_case.get_context.return_value = "최신 AI 뉴스 내용"
        mock_generator.generate.return_value = "최신 AI 동향은..."
        mock_hallucination_use_case.evaluate.return_value = HallucinationEvaluationResult(
            is_hallucinated=False
        )
        mock_relevance_evaluator.evaluate.return_value = RelevanceResult(
            is_relevant=True
        )

        result = await workflow.run(
            question="최신 AI 뉴스가 뭐야?",
            request_id="test-websearch-001"
        )

        assert result["status"] == "completed"
        assert result["route"] == RouteType.WEB_SEARCH
        mock_web_search_use_case.get_context.assert_called_once()

    async def test_retry_on_hallucination_detected(
        self,
        workflow: SelfCorrectiveRAGWorkflow,
        mock_router: AsyncMock,
        mock_generator: AsyncMock,
        mock_relevance_evaluator: AsyncMock,
        mock_hallucination_use_case: AsyncMock,
        mock_query_rewriter_use_case: AsyncMock,
    ) -> None:
        """Should retry with rewritten query when hallucination detected."""
        mock_router.route.return_value = RouteDecision(
            route=RouteType.RAG, reason="Document query"
        )

        # First call returns hallucinated, second call returns not hallucinated
        mock_hallucination_use_case.evaluate.side_effect = [
            HallucinationEvaluationResult(is_hallucinated=True),
            HallucinationEvaluationResult(is_hallucinated=False),
        ]
        mock_relevance_evaluator.evaluate.side_effect = [
            RelevanceResult(is_relevant=True),
            RelevanceResult(is_relevant=True),
        ]
        mock_generator.generate.side_effect = [
            "할루시네이션 답변",
            "정확한 답변",
        ]
        mock_query_rewriter_use_case.rewrite.return_value = RewrittenQuery(
            original_query="원래 질문",
            rewritten_query="개선된 질문"
        )

        result = await workflow.run(
            question="테스트 질문",
            request_id="test-hallucination-001"
        )

        assert result["status"] == "completed"
        assert result["retry_count"] == 1
        mock_query_rewriter_use_case.rewrite.assert_called_once()

    async def test_retry_on_not_relevant_answer(
        self,
        workflow: SelfCorrectiveRAGWorkflow,
        mock_router: AsyncMock,
        mock_generator: AsyncMock,
        mock_relevance_evaluator: AsyncMock,
        mock_hallucination_use_case: AsyncMock,
        mock_query_rewriter_use_case: AsyncMock,
    ) -> None:
        """Should retry with rewritten query when answer not relevant."""
        mock_router.route.return_value = RouteDecision(
            route=RouteType.RAG, reason="Document query"
        )

        mock_hallucination_use_case.evaluate.return_value = HallucinationEvaluationResult(
            is_hallucinated=False
        )

        # First call returns not relevant, second call returns relevant
        mock_relevance_evaluator.evaluate.side_effect = [
            RelevanceResult(is_relevant=False),
            RelevanceResult(is_relevant=True),
        ]
        mock_generator.generate.side_effect = [
            "관련 없는 답변",
            "관련 있는 답변",
        ]
        mock_query_rewriter_use_case.rewrite.return_value = RewrittenQuery(
            original_query="원래 질문",
            rewritten_query="개선된 질문"
        )

        result = await workflow.run(
            question="테스트 질문",
            request_id="test-relevance-001"
        )

        assert result["status"] == "completed"
        assert result["retry_count"] == 1

    async def test_max_retry_exceeded_ends_workflow(
        self,
        workflow: SelfCorrectiveRAGWorkflow,
        mock_router: AsyncMock,
        mock_generator: AsyncMock,
        mock_relevance_evaluator: AsyncMock,
        mock_hallucination_use_case: AsyncMock,
        mock_query_rewriter_use_case: AsyncMock,
    ) -> None:
        """Should end workflow when max retry count exceeded."""
        mock_router.route.return_value = RouteDecision(
            route=RouteType.RAG, reason="Document query"
        )

        # Always return hallucinated
        mock_hallucination_use_case.evaluate.return_value = HallucinationEvaluationResult(
            is_hallucinated=True
        )
        mock_relevance_evaluator.evaluate.return_value = RelevanceResult(
            is_relevant=True
        )
        mock_generator.generate.return_value = "답변"
        mock_query_rewriter_use_case.rewrite.return_value = RewrittenQuery(
            original_query="질문",
            rewritten_query="개선된 질문"
        )

        result = await workflow.run(
            question="테스트 질문",
            request_id="test-maxretry-001"
        )

        # Should end after MAX_RETRY_COUNT retries
        assert result["retry_count"] == RoutingPolicy.MAX_RETRY_COUNT
        assert result["status"] == "completed"

    async def test_error_handling_sets_failed_status(
        self,
        workflow: SelfCorrectiveRAGWorkflow,
        mock_router: AsyncMock,
    ) -> None:
        """Should set failed status and record error on exception."""
        mock_router.route.side_effect = Exception("Router failed")

        result = await workflow.run(
            question="테스트 질문",
            request_id="test-error-001"
        )

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert "Router failed" in result["errors"][0]


class TestSelfCorrectiveRAGWorkflowInit:
    """Tests for SelfCorrectiveRAGWorkflow initialization."""

    def test_requires_all_dependencies(self) -> None:
        """Workflow should require all dependencies."""
        mock_router = AsyncMock()
        mock_generator = AsyncMock()
        mock_relevance = AsyncMock()
        mock_hallucination = AsyncMock()
        mock_query_rewriter = AsyncMock()
        mock_web_search = MagicMock()

        workflow = SelfCorrectiveRAGWorkflow(
            router_adapter=mock_router,
            generator_adapter=mock_generator,
            relevance_evaluator_adapter=mock_relevance,
            hallucination_use_case=mock_hallucination,
            query_rewriter_use_case=mock_query_rewriter,
            web_search_use_case=mock_web_search,
        )

        assert workflow is not None
