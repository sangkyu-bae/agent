"""analyze-user-context: 분석 노드 사용자·부서 컨텍스트 주입 테스트.

Design §5 (테스트 설계) 4개 그룹:
- 5-1 프롬프트 회귀 (_build_analysis_prompt)
- 5-2 블록 소스 우선순위 (_analyze_node: state 우선 / ContextVar 폴백)
- 5-3 경로 ① use case (AnalyzeExcelUseCase.execute auth_ctx)
- 5-4 경로 ② supervisor (_run_excel_analysis / _analyze_context)
"""
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.agent_run.auth_context import (
    reset_current_auth_context,
    set_current_auth_context,
)
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.use_cases.analyze_excel_use_case import AnalyzeExcelUseCase
from src.application.workflows.excel_analysis_workflow import ExcelAnalysisWorkflow
from src.domain.agent_run.auth_context import AuthContext
from src.domain.policies.analysis_policy import (
    AnalysisQualityThreshold,
    AnalysisRetryPolicy,
)
from src.domain.search_decision.schemas import WebSearchDecision
from src.infrastructure.llm.schemas import ClaudeResponse


def _auth(name: str = "배상규", dept: str = "여신관리부", role: str = "user") -> AuthContext:
    return AuthContext(
        user_id=1,
        display_name=name,
        role=role,
        primary_department_id="D1",
        primary_department_name=dept,
        department_ids=("D1",),
        department_names=(dept,),
        permissions=frozenset(),
    )


def _claude_response(content: str) -> ClaudeResponse:
    return ClaudeResponse(
        content=content,
        model="claude-sonnet-4-5-20250929",
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=5,
        request_id="t",
        latency_ms=1,
    )


def _make_workflow(mock_claude: Mock) -> ExcelAnalysisWorkflow:
    search_decision = Mock()
    search_decision.decide = AsyncMock(
        return_value=WebSearchDecision(needs_web_search=False)
    )
    return ExcelAnalysisWorkflow(
        excel_parser=Mock(),
        claude_client=mock_claude,
        tavily_search=Mock(),
        hallucination_evaluator=Mock(),
        search_decision=search_decision,
        logger=Mock(),
        retry_policy=AnalysisRetryPolicy(max_retries=3),
        quality_threshold=AnalysisQualityThreshold(
            min_confidence_score=0.7, max_hallucination_score=0.3
        ),
    )


def _base_state(**overrides) -> dict:
    state = {
        "request_id": "t",
        "user_query": "나의 휴가는 며칠 남았어?",
        "excel_data": {"rows": [{"name": "배상규", "leave": 5}]},
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
        "charts": [],
    }
    state.update(overrides)
    return state


def _captured_prompt(mock_claude: Mock) -> str:
    """_analyze_node가 claude.complete에 넘긴 프롬프트 본문 추출."""
    request = mock_claude.complete.call_args.args[0]
    return request.messages[0]["content"]


# ── 5-1 프롬프트 회귀 ────────────────────────────────────────────────


class TestBuildAnalysisPromptUserBlock:
    def test_prepends_user_block_when_present(self):
        wf = _make_workflow(Mock())
        block = "[현재 사용자 정보]\n- 이름: 배상규\n---\n\n"

        prompt = wf._build_analysis_prompt("질문", {"a": 1}, "", user_block=block)

        assert prompt.startswith(block)
        assert "배상규" in prompt
        assert "## 사용자 질문" in prompt

    def test_no_block_by_default_keeps_original(self):
        wf = _make_workflow(Mock())

        prompt = wf._build_analysis_prompt("질문", {"a": 1}, "")

        assert prompt.startswith("당신은 데이터 분석 결과를")
        assert "[현재 사용자 정보]" not in prompt


# ── 5-2 블록 소스 우선순위 ──────────────────────────────────────────


class TestAnalyzeNodeBlockResolution:
    @pytest.mark.asyncio
    async def test_state_block_takes_precedence(self):
        mock_claude = Mock()
        mock_claude.complete = AsyncMock(return_value=_claude_response("분석"))
        wf = _make_workflow(mock_claude)

        # 가이드 예시 텍스트(배상규/김철수/이영희)와 겹치지 않는 고유 토큰 사용.
        token = set_current_auth_context(_auth(name="CTXVARONLY"))
        try:
            await wf._analyze_node(
                _base_state(user_context_block="[현재 사용자 정보]\nBLOCK_S\n---\n\n")
            )
        finally:
            reset_current_auth_context(token)

        prompt = _captured_prompt(mock_claude)
        assert "BLOCK_S" in prompt
        assert "CTXVARONLY" not in prompt  # ContextVar 블록은 무시됨

    @pytest.mark.asyncio
    async def test_contextvar_fallback_when_state_empty(self):
        mock_claude = Mock()
        mock_claude.complete = AsyncMock(return_value=_claude_response("분석"))
        wf = _make_workflow(mock_claude)

        token = set_current_auth_context(_auth(name="배상규", dept="여신관리부"))
        try:
            await wf._analyze_node(_base_state())  # user_context_block 미설정
        finally:
            reset_current_auth_context(token)

        prompt = _captured_prompt(mock_claude)
        assert "[현재 사용자 정보]" in prompt
        assert "배상규" in prompt
        assert "여신관리부" in prompt

    @pytest.mark.asyncio
    async def test_no_block_when_both_absent(self):
        mock_claude = Mock()
        mock_claude.complete = AsyncMock(return_value=_claude_response("분석"))
        wf = _make_workflow(mock_claude)

        await wf._analyze_node(_base_state())  # state 없음 + ContextVar 없음

        prompt = _captured_prompt(mock_claude)
        assert "[현재 사용자 정보]" not in prompt


# ── 5-3 경로 ① use case ─────────────────────────────────────────────


def _mock_workflow_capturing() -> Mock:
    mock_wf = Mock()
    mock_wf.run = AsyncMock(
        return_value={
            "request_id": "t",
            "user_query": "q",
            "excel_data": {},
            "analysis_text": "결과",
            "confidence_score": 1.0,
            "hallucination_score": 0.0,
            "attempts_history": [
                {
                    "attempt_number": 1,
                    "analysis_text": "결과",
                    "confidence_score": 1.0,
                    "hallucination_score": 0.0,
                    "used_web_search": False,
                    "timestamp": "2026-06-09T10:00:00",
                }
            ],
            "is_complete": True,
            "final_status": "completed",
            "charts": [],
        }
    )
    return mock_wf


class TestUseCaseAuthCtxInjection:
    @pytest.mark.asyncio
    async def test_auth_ctx_injects_user_block(self):
        mock_wf = _mock_workflow_capturing()
        use_case = AnalyzeExcelUseCase(workflow=mock_wf, logger=Mock())

        await use_case.execute(
            excel_file_path="/tmp/t.xlsx",
            user_query="나의 휴가",
            user_id="user-1",
            auth_ctx=_auth(name="배상규", dept="여신관리부"),
        )

        initial = mock_wf.run.call_args.args[0]
        assert "배상규" in initial["user_context_block"]
        assert "여신관리부" in initial["user_context_block"]

    @pytest.mark.asyncio
    async def test_no_auth_ctx_keeps_empty_block(self):
        mock_wf = _mock_workflow_capturing()
        use_case = AnalyzeExcelUseCase(workflow=mock_wf, logger=Mock())

        await use_case.execute(
            excel_file_path="/tmp/t.xlsx",
            user_query="요약",
            user_id="user-1",
        )

        initial = mock_wf.run.call_args.args[0]
        assert initial["user_context_block"] == ""


# ── 5-4 경로 ② supervisor ───────────────────────────────────────────


def _make_compiler() -> WorkflowCompiler:
    return WorkflowCompiler(
        tool_factory=Mock(),
        llm_factory=Mock(),
        logger=Mock(),
    )


class TestSupervisorAnalysisUserBlock:
    @pytest.mark.asyncio
    async def test_run_excel_analysis_injects_block_from_contextvar(self):
        compiler = _make_compiler()
        captured: dict = {}

        async def fake_run(initial):
            captured.update(initial)
            return {"analysis_text": "결과"}

        wf = Mock()
        wf.run = fake_run

        token = set_current_auth_context(_auth(name="배상규"))
        try:
            await compiler._run_excel_analysis(
                wf, "나의 휴가", {"file_path": "/t.xlsx", "user_id": "u"}, Mock()
            )
        finally:
            reset_current_auth_context(token)

        assert "배상규" in captured["user_context_block"]

    @pytest.mark.asyncio
    async def test_analyze_context_prepends_block_from_contextvar(self):
        compiler = _make_compiler()

        captured: dict = {}

        class FakeLLM:
            async def ainvoke(self, messages):
                captured["system"] = messages[0]["content"]
                return Mock(content="분석 결과")

        token = set_current_auth_context(_auth(name="배상규"))
        try:
            await compiler._analyze_context(
                FakeLLM(), "SYSTEM_PROMPT", "나의 휴가", []
            )
        finally:
            reset_current_auth_context(token)

        assert captured["system"].startswith("[현재 사용자 정보]")
        assert "배상규" in captured["system"]
