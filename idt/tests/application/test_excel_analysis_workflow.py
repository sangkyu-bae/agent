"""Tests for ExcelAnalysisWorkflow."""

import pytest
from unittest.mock import AsyncMock, Mock

from src.application.workflows.excel_analysis_workflow import (
    ExcelAnalysisWorkflow,
    ExcelAnalysisState,
)
from src.domain.policies.analysis_policy import (
    AnalysisRetryPolicy,
    AnalysisQualityThreshold,
)
from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.domain.search_decision.schemas import WebSearchDecision
from tests.support.fake_utility_llm import FakeUtilityLLM


def _make_search_decision(needs: bool = False) -> Mock:
    decision = Mock()
    decision.decide = AsyncMock(
        return_value=WebSearchDecision(needs_web_search=needs)
    )
    return decision


def _base_state(**overrides) -> ExcelAnalysisState:
    state: ExcelAnalysisState = {
        "request_id": "test-123",
        "user_query": "분석해줘",
        "excel_data": {"file_path": "/tmp/test.xlsx", "user_id": "user-1"},
        "current_attempt": 0,
        "max_attempts": 3,
        "analysis_text": "",
        "confidence_score": 0.0,
        "hallucination_score": 0.0,
        "needs_web_search": False,
        "web_search_results": "",
        "attempts_history": [],
        "is_complete": False,
        "final_status": "pending",
        "error_message": "",
        "viz_decision": "",
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state




class TestExcelAnalysisWorkflowNodes:
    """각 노드의 단위 테스트."""

    def _create_workflow(self, **overrides) -> ExcelAnalysisWorkflow:
        defaults = {
            "excel_parser": Mock(),
            "llm_provider": FakeUtilityLLM("분석"),
            "tavily_search": Mock(),
            "hallucination_evaluator": Mock(),
            "search_decision": _make_search_decision(),
            "logger": Mock(),
            "retry_policy": AnalysisRetryPolicy(max_retries=3),
            "quality_threshold": AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        }
        defaults.update(overrides)
        return ExcelAnalysisWorkflow(**defaults)

    @pytest.mark.asyncio
    async def test_parse_excel_node(self):
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {"sheets": {"Sheet1": {"data": []}}}
        mock_parser.parse.return_value = mock_excel_data

        workflow = self._create_workflow(excel_parser=mock_parser)

        state = _base_state()
        result = await workflow._parse_excel_node(state)

        mock_parser.parse.assert_called_once_with("/tmp/test.xlsx", "user-1")
        assert "excel_data" in result
        assert result["current_attempt"] == 0

    @pytest.mark.asyncio
    async def test_analyze_node(self):
        fake_llm = FakeUtilityLLM("분석 결과입니다.")

        workflow = self._create_workflow(llm_provider=fake_llm)

        state = _base_state(user_query="데이터 요약")
        result = await workflow._analyze_node(state)

        assert result["analysis_text"] == "분석 결과입니다."
        assert result["current_attempt"] == 1
        fake_llm.llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_node_sanitizes_leaked_chart_json(self):
        """LLM이 분석+차트 JSON을 함께 내보내도 analysis_text는 자연어만 남는다."""
        leaked = '사용자별 남은 휴가 — 배상규 5일.\n```json\n{"type": "bar"}\n```'
        fake_llm = FakeUtilityLLM(leaked)

        workflow = self._create_workflow(llm_provider=fake_llm)

        result = await workflow._analyze_node(_base_state(user_query="휴가 그래프"))

        assert result["analysis_text"] == "사용자별 남은 휴가 — 배상규 5일."
        assert "```" not in result["analysis_text"]
        assert "type" not in result["analysis_text"]

    def test_build_analysis_prompt_includes_output_guide(self):
        """분석 프롬프트가 공용 출력 가이드 제약을 포함한다(약화 회귀 방지)."""
        from src.application.visualization.analysis_prompt import (
            ANALYSIS_OUTPUT_GUIDE,
        )

        workflow = self._create_workflow()
        prompt = workflow._build_analysis_prompt("휴가 그래프", {"a": 1}, "")

        assert ANALYSIS_OUTPUT_GUIDE in prompt
        assert "차트를 직접 만들지 않는다" in prompt

    @pytest.mark.asyncio
    async def test_analyze_node_sets_needs_web_search(self):
        """검색 결정이 True면 needs_web_search 반영."""
        fake_llm = FakeUtilityLLM("분석")
        search_decision = _make_search_decision(needs=True)

        workflow = self._create_workflow(
            llm_provider=fake_llm, search_decision=search_decision
        )

        state = _base_state(web_search_results="")
        result = await workflow._analyze_node(state)

        assert result["needs_web_search"] is True
        search_decision.decide.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_analyze_node_skips_decision_after_search(self):
        """이미 웹 검색을 했으면(web_search_results 존재) 결정 호출을 건너뛴다."""
        fake_llm = FakeUtilityLLM("분석")
        search_decision = _make_search_decision(needs=True)

        workflow = self._create_workflow(
            llm_provider=fake_llm, search_decision=search_decision
        )

        state = _base_state(web_search_results="이전 검색 결과")
        result = await workflow._analyze_node(state)

        assert result["needs_web_search"] is False
        search_decision.decide.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_web_search_node(self):
        mock_search = Mock()
        mock_search.get_search_context.return_value = "검색 결과 컨텍스트"

        workflow = self._create_workflow(tavily_search=mock_search)

        state = _base_state(
            user_query="2024년 매출",
            current_attempt=1,
            analysis_text="분석 텍스트",
            needs_web_search=True,
        )
        result = await workflow._web_search_node(state)

        assert result["web_search_results"] == "검색 결과 컨텍스트"
        assert result["needs_web_search"] is False
        mock_search.get_search_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_node_no_hallucination(self):
        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=False)
        )

        workflow = self._create_workflow(hallucination_evaluator=mock_evaluator)

        state = _base_state(current_attempt=1, analysis_text="분석 결과")
        result = await workflow._evaluate_node(state)

        assert result["confidence_score"] == 1.0
        assert result["hallucination_score"] == 0.0
        assert len(result["attempts_history"]) == 1
        assert result["attempts_history"][0]["attempt_number"] == 1

    @pytest.mark.asyncio
    async def test_evaluate_node_with_hallucination(self):
        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=True)
        )

        workflow = self._create_workflow(hallucination_evaluator=mock_evaluator)

        state = _base_state(current_attempt=1, analysis_text="할루시네이션 결과")
        result = await workflow._evaluate_node(state)

        assert result["confidence_score"] == 0.0
        assert result["hallucination_score"] == 1.0


class TestExcelAnalysisWorkflowRouting:
    """조건부 엣지 라우팅 테스트."""

    def _create_workflow(self, **overrides) -> ExcelAnalysisWorkflow:
        defaults = {
            "excel_parser": Mock(),
            "llm_provider": FakeUtilityLLM("분석"),
            "tavily_search": Mock(),
            "hallucination_evaluator": Mock(),
            "search_decision": _make_search_decision(),
            "logger": Mock(),
            "retry_policy": AnalysisRetryPolicy(max_retries=3),
            "quality_threshold": AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        }
        defaults.update(overrides)
        return ExcelAnalysisWorkflow(**defaults)

    def test_should_search_true(self):
        workflow = self._create_workflow()
        assert workflow._should_search({"needs_web_search": True}) == "search"

    def test_should_search_false(self):
        workflow = self._create_workflow()
        assert workflow._should_search({"needs_web_search": False}) == "evaluate"

    def test_should_retry_or_complete_quality_ok(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.9,
            "hallucination_score": 0.1,
            "current_attempt": 1,
        }
        assert workflow._should_retry_or_complete(state) == "complete"

    def test_should_retry_or_complete_quality_bad_retry(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.0,
            "hallucination_score": 1.0,
            "current_attempt": 1,
        }
        assert workflow._should_retry_or_complete(state) == "retry"

    def test_should_retry_or_complete_quality_bad_max_retries(self):
        workflow = self._create_workflow()
        state = {
            "confidence_score": 0.0,
            "hallucination_score": 1.0,
            "current_attempt": 3,
        }
        assert workflow._should_retry_or_complete(state) == "complete"


class TestExcelAnalysisWorkflowIntegration:
    """그래프 전체 흐름 테스트."""

    @pytest.mark.asyncio
    async def test_full_flow_success_first_attempt(self):
        """첫 시도에 성공 → complete → chart_router → END."""
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {
            "sheets": {"Sheet1": {"data": [{"a": 1}]}}
        }
        mock_parser.parse.return_value = mock_excel_data

        fake_llm = FakeUtilityLLM("분석 결과입니다.")

        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            return_value=HallucinationEvaluationResult(is_hallucinated=False)
        )

        workflow = ExcelAnalysisWorkflow(
            excel_parser=mock_parser,
            llm_provider=fake_llm,
            tavily_search=Mock(),
            hallucination_evaluator=mock_evaluator,
            search_decision=_make_search_decision(),
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(max_retries=3),
            quality_threshold=AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        )

        result = await workflow.run(_base_state(user_query="데이터 요약"))

        assert result["analysis_text"] == "분석 결과입니다."
        assert result["confidence_score"] == 1.0
        assert result["hallucination_score"] == 0.0
        assert len(result["attempts_history"]) == 1
        # complete 경로가 chart_router를 거쳐 viz_decision을 기록했는지
        assert result["viz_decision"] in ("visualize", "text")
        mock_parser.parse.assert_called_once()
        fake_llm.llm.ainvoke.assert_called_once()
        mock_evaluator.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_flow_retry_then_success(self):
        """할루시네이션으로 재시도 후 성공."""
        mock_parser = Mock()
        mock_excel_data = Mock()
        mock_excel_data.to_dict.return_value = {"sheets": {}}
        mock_parser.parse.return_value = mock_excel_data

        fake_llm = FakeUtilityLLM("할루시네이션 결과", "개선된 분석")

        mock_search = Mock()
        mock_search.get_search_context.return_value = "웹 검색 결과"

        mock_evaluator = Mock()
        mock_evaluator.evaluate = AsyncMock(
            side_effect=[
                HallucinationEvaluationResult(is_hallucinated=True),
                HallucinationEvaluationResult(is_hallucinated=False),
            ]
        )

        workflow = ExcelAnalysisWorkflow(
            excel_parser=mock_parser,
            llm_provider=fake_llm,
            tavily_search=mock_search,
            hallucination_evaluator=mock_evaluator,
            search_decision=_make_search_decision(needs=False),
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(
                max_retries=3,
                require_web_search_on_retry=True,
            ),
            quality_threshold=AnalysisQualityThreshold(
                min_confidence_score=0.7,
                max_hallucination_score=0.3,
            ),
        )

        result = await workflow.run(_base_state(user_query="분석"))

        assert result["analysis_text"] == "개선된 분석"
        assert len(result["attempts_history"]) == 2
        assert result["confidence_score"] == 1.0
        assert fake_llm.llm.ainvoke.call_count == 2
        assert mock_search.get_search_context.call_count == 1
        assert result["viz_decision"] in ("visualize", "text")


class TestAnalyzeNodeUtilityLLM:
    """excel-analysis-llm-provider: 분석 노드는 관리자 유틸리티 LLM을 런타임에 해석한다.

    고정 ClaudeClient(Sonnet 4.5)는 PII 마스킹(PiiGuardedLLMFactory)·관리자 모델 교체를
    우회했다. 이제 UtilityLLMProviderPort.get()으로 호출 시점마다 모델을 얻는다.
    """

    def _workflow(self, provider, **overrides) -> ExcelAnalysisWorkflow:
        search_decision = _make_search_decision()
        base = dict(
            excel_parser=Mock(),
            llm_provider=provider,
            tavily_search=Mock(),
            hallucination_evaluator=Mock(),
            search_decision=search_decision,
            logger=Mock(),
            retry_policy=AnalysisRetryPolicy(max_retries=3),
            quality_threshold=AnalysisQualityThreshold(
                min_confidence_score=0.7, max_hallucination_score=0.3,
            ),
        )
        base.update(overrides)
        return ExcelAnalysisWorkflow(**base)

    @pytest.mark.asyncio
    async def test_uses_configured_temperature(self):
        provider = FakeUtilityLLM("분석")
        wf = self._workflow(provider, analysis_temperature=0.42)
        await wf._analyze_node(_base_state())
        assert provider.temperatures == [0.42]

    @pytest.mark.asyncio
    async def test_passes_run_name_and_request_id(self):
        provider = FakeUtilityLLM("분석")
        await self._workflow(provider)._analyze_node(_base_state())
        config = provider.llm.ainvoke.call_args.kwargs["config"]
        assert config["run_name"] == "excel_analysis"
        assert config["metadata"]["request_id"] == _base_state()["request_id"]

    @pytest.mark.asyncio
    async def test_block_list_content_is_coerced(self):
        provider = FakeUtilityLLM([
            {"type": "thinking", "thinking": "", "signature": "s"},
            {"type": "text", "text": "블록 분석 결과"},
        ])
        result = await self._workflow(provider)._analyze_node(_base_state())
        assert result["analysis_text"] == "블록 분석 결과"

    @pytest.mark.asyncio
    async def test_unresolved_model_raises_clear_error(self):
        from src.domain.llm.exceptions import UtilityLLMUnavailableError

        provider = FakeUtilityLLM(available=False)
        with pytest.raises(UtilityLLMUnavailableError):
            await self._workflow(provider)._analyze_node(_base_state())


class TestEmptyAnalysisResponse:
    """claude-agent-e2e-fixes Check G-1: 분석 LLM 빈 답 처리.

    2026-11-19 실 E2E: Opus 5.5가 입력 58k에 출력 한도 16000을 전부 thinking으로 써
    text가 비었고, 빈 답이 환각 검사로 넘어가 "Generation and documents are required"
    로 실패했다. 빈 답이면 검색 판단·환각 검사 전에 원인을 담아 실패한다.
    """

    def _workflow(self, provider, decision=None) -> ExcelAnalysisWorkflow:
        return ExcelAnalysisWorkflow(
            excel_parser=Mock(), llm_provider=provider, tavily_search=Mock(),
            hallucination_evaluator=Mock(),
            search_decision=decision or _make_search_decision(),
            logger=Mock(), retry_policy=AnalysisRetryPolicy(max_retries=3),
            quality_threshold=AnalysisQualityThreshold(),
        )

    @staticmethod
    def _thinking_only(stop_reason: str | None):
        thinking = {"type": "thinking", "thinking": "...", "signature": "s"}
        provider = FakeUtilityLLM([thinking])
        meta = {"stop_reason": stop_reason} if stop_reason else {}
        provider.llm.ainvoke.return_value.response_metadata = meta
        return provider

    @pytest.mark.asyncio
    async def test_max_tokens_stop_names_output_limit(self):
        from src.domain.llm.exceptions import EmptyLLMResponseError

        decision = _make_search_decision()
        wf = self._workflow(self._thinking_only("max_tokens"), decision)
        with pytest.raises(EmptyLLMResponseError, match="최대 출력 토큰"):
            await wf._analyze_node(_base_state())
        decision.decide.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_without_stop_reason_still_fails_clearly(self):
        from src.domain.llm.exceptions import EmptyLLMResponseError

        with pytest.raises(EmptyLLMResponseError, match="빈 응답"):
            await self._workflow(self._thinking_only(None))._analyze_node(_base_state())

    @pytest.mark.asyncio
    async def test_full_run_skips_hallucination_check(self):
        from src.domain.llm.exceptions import EmptyLLMResponseError

        wf = self._workflow(self._thinking_only("max_tokens"))
        with pytest.raises(EmptyLLMResponseError):
            await wf._analyze_node(_base_state())
        wf._evaluator.evaluate.assert_not_called()
