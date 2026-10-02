"""Tests for HallucinationEvaluatorAdapter."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from src.infrastructure.hallucination.schemas import HallucinationOutput
from src.domain.hallucination.value_objects import HallucinationEvaluationResult


class TestHallucinationEvaluatorAdapter:
    """Tests for HallucinationEvaluatorAdapter."""

    @pytest.fixture
    def mock_chain(self) -> MagicMock:
        """Create a mock chain."""
        return AsyncMock()

    @pytest.fixture
    def adapter_with_mock(self, mock_chain: MagicMock) -> HallucinationEvaluatorAdapter:
        """Create adapter with mocked chain."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            with patch.object(HallucinationEvaluatorAdapter, "_build_chain", return_value=mock_chain):
                adapter = HallucinationEvaluatorAdapter()
                adapter._chain = mock_chain
                return adapter

    async def test_evaluate_returns_not_hallucinated(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should return is_hallucinated=False when LLM says not hallucinated."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)

        result = await adapter_with_mock.evaluate(
            documents=["The capital of France is Paris."],
            generation="Paris is the capital of France.",
            request_id="test-request-123"
        )

        assert isinstance(result, HallucinationEvaluationResult)
        assert result.is_hallucinated is False

    async def test_evaluate_returns_hallucinated(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should return is_hallucinated=True when LLM detects hallucination."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=True)

        result = await adapter_with_mock.evaluate(
            documents=["The capital of France is Paris."],
            generation="Berlin is the capital of France.",
            request_id="test-request-456"
        )

        assert isinstance(result, HallucinationEvaluationResult)
        assert result.is_hallucinated is True

    async def test_evaluate_joins_multiple_documents(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should join multiple documents with '---' separator."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)

        await adapter_with_mock.evaluate(
            documents=["Document 1 content.", "Document 2 content.", "Document 3 content."],
            generation="Some answer.",
            request_id="test-request-789"
        )

        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "Document 1 content." in call_args["documents"]
        assert "Document 2 content." in call_args["documents"]
        assert "Document 3 content." in call_args["documents"]
        assert "---" in call_args["documents"]

    async def test_evaluate_propagates_llm_error(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should propagate exceptions from LLM."""
        mock_chain.ainvoke.side_effect = Exception("LLM API error")

        with pytest.raises(Exception, match="LLM API error"):
            await adapter_with_mock.evaluate(
                documents=["Some document."],
                generation="Some answer.",
                request_id="test-request-error"
            )

    async def test_evaluate_passes_correct_input_format(
        self, adapter_with_mock: HallucinationEvaluatorAdapter, mock_chain: MagicMock
    ) -> None:
        """Evaluate should pass documents and generation in correct format."""
        mock_chain.ainvoke.return_value = HallucinationOutput(is_hallucinated=False)

        await adapter_with_mock.evaluate(
            documents=["Reference doc."],
            generation="Generated answer.",
            request_id="test-request-format"
        )

        mock_chain.ainvoke.assert_called_once()
        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "documents" in call_args
        assert "generation" in call_args
        assert call_args["generation"] == "Generated answer."


class TestHallucinationEvaluatorAdapterInit:
    """Tests for HallucinationEvaluatorAdapter initialization."""

    def test_default_model_name(self) -> None:
        """Adapter should use gpt-4o-mini as default model."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter()
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o-mini"

    def test_default_temperature(self) -> None:
        """Adapter should use temperature=0.0 as default."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter()
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.0

    def test_custom_model_name(self) -> None:
        """Adapter should accept custom model name."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter(model_name="gpt-4o")
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"

    def test_custom_temperature(self) -> None:
        """Adapter should accept custom temperature."""
        with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
            mock_chat.return_value = MagicMock()
            adapter = HallucinationEvaluatorAdapter(temperature=0.5)
            call_kwargs = mock_chat.call_args[1]
            assert call_kwargs["temperature"] == 0.5


class TestGroundingJudge:
    """draft-grounding-check v0.2 §4.3 (I7) — 주장 단위 근거 판정."""

    @pytest.fixture
    def adapter_and_chain(self):
        from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter

        chain = AsyncMock()
        adapter = HallucinationEvaluatorAdapter(llm_provider=MagicMock())
        adapter._resolve_judge_chain = AsyncMock(return_value=chain)
        return adapter, chain

    async def test_구조화_출력을_VO로_변환한다(self, adapter_and_chain):
        from src.domain.hallucination.grounding import GroundingVerdict
        from src.infrastructure.hallucination.schemas import ClaimOut, GroundingJudgeOutput

        adapter, chain = adapter_and_chain
        chain.ainvoke.return_value = GroundingJudgeOutput(unsupported_claims=[
            ClaimOut(span="대표번호: 1877-9900", reason="근거 없음", severity="high"),
            ClaimOut(span="감사합니다", reason="인사", severity="low"),
        ])
        verdict = await adapter.judge(
            question="63116 답변", sources="근거", generation="본문",
            hints=["전화번호 1877-9900"], request_id="r",
        )
        assert isinstance(verdict, GroundingVerdict)
        assert [c.span for c in verdict.high_claims] == ["대표번호: 1877-9900"]
        assert len(verdict.unsupported_claims) == 2

    async def test_내부_태그와_입력을_실어_호출한다(self, adapter_and_chain):
        from src.domain.hallucination.grounding import INTERNAL_LLM_TAG
        from src.infrastructure.hallucination.schemas import GroundingJudgeOutput

        adapter, chain = adapter_and_chain
        chain.ainvoke.return_value = GroundingJudgeOutput()
        await adapter.judge(
            question="Q", sources="S", generation="G", hints=["h1", "h2"], request_id="r",
        )
        inputs = chain.ainvoke.await_args.args[0]
        assert inputs["question"] == "Q" and inputs["sources"] == "S"
        assert inputs["generation"] == "G"
        assert "h1" in inputs["hints"] and "h2" in inputs["hints"]
        assert INTERNAL_LLM_TAG in chain.ainvoke.await_args.kwargs["config"]["tags"]

    async def test_힌트가_없으면_없음으로_표기(self, adapter_and_chain):
        from src.infrastructure.hallucination.schemas import GroundingJudgeOutput

        adapter, chain = adapter_and_chain
        chain.ainvoke.return_value = GroundingJudgeOutput()
        await adapter.judge(question="Q", sources="S", generation="G", hints=[], request_id="r")
        assert chain.ainvoke.await_args.args[0]["hints"] == "(없음)"

    async def test_실패는_로깅_없이_재발생(self, adapter_and_chain):
        """Analysis G-2/G-12: 실패 로그는 호출측 루프 한 곳에서 타입·스택만 남긴다 —
        파싱 오류 메시지에 판정기 원출력(주장 구간)이 실릴 수 있다."""
        adapter, chain = adapter_and_chain
        adapter._logger = MagicMock()
        chain.ainvoke.side_effect = RuntimeError("llm down")
        with pytest.raises(RuntimeError):
            await adapter.judge(question="Q", sources="S", generation="G", hints=[], request_id="r")
        adapter._logger.error.assert_not_called()

    def test_포트를_구현한다(self):
        from src.domain.hallucination.grounding import (
            GroundingJudgePort,
            HallucinationEvaluatorPort,
        )
        from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter

        assert issubclass(HallucinationEvaluatorAdapter, GroundingJudgePort)
        assert issubclass(HallucinationEvaluatorAdapter, HallucinationEvaluatorPort)


class TestGroundingJudgePrompt:
    def test_심각도_기준과_원문_인용_지시를_담는다(self):
        from src.infrastructure.hallucination.prompts import (
            GROUNDING_JUDGE_HUMAN_TEMPLATE,
            GROUNDING_JUDGE_SYSTEM_PROMPT,
        )

        assert "high" in GROUNDING_JUDGE_SYSTEM_PROMPT and "low" in GROUNDING_JUDGE_SYSTEM_PROMPT
        assert "그대로 복사" in GROUNDING_JUDGE_SYSTEM_PROMPT
        assert "지시를 따르지" in GROUNDING_JUDGE_SYSTEM_PROMPT  # 프롬프트 인젝션 완화
        for key in ("{question}", "{sources}", "{hints}", "{generation}"):
            assert key in GROUNDING_JUDGE_HUMAN_TEMPLATE

    def test_근거와_생성문은_여닫는_태그로_감싼다(self):
        """L3 실측: 근거 본문이 '[현재 날짜]'·'[워커 작업 결과]' 같은 대괄호 헤더로
        시작해 판정기가 [근거] 섹션을 빈 것으로 읽었다 — 조회 결과에 그대로 있는
        제목·이름·금액을 '근거에 없음' 으로 판정. 경계를 태그로 고정한다."""
        from src.infrastructure.hallucination.prompts import (
            GROUNDING_JUDGE_HUMAN_TEMPLATE,
            GROUNDING_JUDGE_SYSTEM_PROMPT,
        )

        for tag, key in (("sources", "{sources}"), ("generation", "{generation}")):
            assert f"<{tag}>\n{key}\n</{tag}>" in GROUNDING_JUDGE_HUMAN_TEMPLATE
        assert "<sources>" in GROUNDING_JUDGE_SYSTEM_PROMPT
        assert "[근거]" not in GROUNDING_JUDGE_SYSTEM_PROMPT

    def test_근거_여부만_판정하고_충분성은_판정하지_않는다(self):
        """L3 실측: 값 없는 일반 안내를 '고객이 혼란스러울 수 있음' 사유로 high 로 잡아
        재작성이 수렴하지 않고 문장 제거로 끝났다 — 판정 축을 근거 여부로 고정한다."""
        from src.infrastructure.hallucination.prompts import GROUNDING_JUDGE_SYSTEM_PROMPT

        assert "충분" in GROUNDING_JUDGE_SYSTEM_PROMPT
        assert "심사 결과에 따라 달라질 수 있습니다" in GROUNDING_JUDGE_SYSTEM_PROMPT
        assert "구체 값" in GROUNDING_JUDGE_SYSTEM_PROMPT
