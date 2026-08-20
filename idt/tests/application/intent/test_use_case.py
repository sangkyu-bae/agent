"""AnalyzeIntentUseCase 단위 테스트.

Design §8.2 시나리오 20~22.

주의: 시나리오 20~21(labels 1개 / description 빈 문자열)은 IntentSpec·IntentLabel
생성 시점에 pydantic 이 거부하므로(module-1 test_policies.py 에서 검증) UseCase 에
도달하는 spec 은 정의상 항상 유효하다. 해당 검증은 라우터 422 테스트로 옮겼다.
"""
from typing import Any

import pytest
from src.application.intent.use_case import AnalyzeIntentUseCase
from src.domain.intent.interfaces import IntentAnalyzerInterface
from src.domain.intent.schemas import (
    IntentLabel,
    IntentResult,
    IntentSpec,
    SlotAnswer,
    SlotSpec,
    Turn,
)


class SpyAnalyzer(IntentAnalyzerInterface):
    """호출 인자를 기록하는 포트 대역."""

    def __init__(self, result: IntentResult | None = None) -> None:
        self.result = result or IntentResult(label="search", confidence=0.7)
        self.calls: list[dict[str, Any]] = []

    async def analyze(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        answers: list[SlotAnswer] | None = None,
        round_: int = 0,
        request_id: str = "",
    ) -> IntentResult:
        self.calls.append(
            {
                "message": message,
                "spec": spec,
                "history": history,
                "answers": answers,
                "round_": round_,
                "request_id": request_id,
            }
        )
        return self.result


def _spec() -> IntentSpec:
    return IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ]
    )


# --- 시나리오 22: 위임 + 로깅 ------------------------------------------------


async def test_delegates_to_analyzer_exactly_once() -> None:
    analyzer = SpyAnalyzer()
    use_case = AnalyzeIntentUseCase(analyzer=analyzer)

    await use_case.execute("여신 규정 알려줘", _spec())

    assert len(analyzer.calls) == 1
    assert analyzer.calls[0]["message"] == "여신 규정 알려줘"


async def test_returns_analyzer_result_unchanged() -> None:
    expected = IntentResult(label="analysis", confidence=0.61, reason="계산 요청")
    use_case = AnalyzeIntentUseCase(analyzer=SpyAnalyzer(result=expected))

    result = await use_case.execute("합계 내줘", _spec())

    assert result == expected


async def test_history_and_request_id_are_forwarded() -> None:
    analyzer = SpyAnalyzer()
    use_case = AnalyzeIntentUseCase(analyzer=analyzer)
    history = [Turn(role="user", content="여신 규정")]

    await use_case.execute("그거 말고", _spec(), history=history, request_id="req-9")

    assert analyzer.calls[0]["history"] == history
    assert analyzer.calls[0]["request_id"] == "req-9"


async def test_history_defaults_to_none() -> None:
    analyzer = SpyAnalyzer()
    use_case = AnalyzeIntentUseCase(analyzer=analyzer)

    await use_case.execute("여신 규정", _spec())

    assert analyzer.calls[0]["history"] is None


# --- 되묻기 왕복 인자 전달 (Plan D4 — stateless) -----------------------------


async def test_answers_and_round_are_forwarded() -> None:
    analyzer = SpyAnalyzer()
    use_case = AnalyzeIntentUseCase(analyzer=analyzer)
    spec = IntentSpec(slots=[SlotSpec(key="tone", description="답변 어조")])
    answers = [SlotAnswer(slot_key="tone", value="친근")]

    await use_case.execute("에이전트 만들어줘", spec, answers=answers, round_=1)

    assert analyzer.calls[0]["answers"] == answers
    assert analyzer.calls[0]["round_"] == 1


async def test_answers_and_round_default_to_empty() -> None:
    analyzer = SpyAnalyzer()
    use_case = AnalyzeIntentUseCase(analyzer=analyzer)

    await use_case.execute("여신 규정", _spec())

    assert analyzer.calls[0]["answers"] is None
    assert analyzer.calls[0]["round_"] == 0


async def test_use_case_holds_no_round_state_between_calls() -> None:
    """모듈은 라운드 사이에 아무것도 기억하지 않는다 — 상태는 전부 인자에 있다."""
    analyzer = SpyAnalyzer()
    use_case = AnalyzeIntentUseCase(analyzer=analyzer)
    spec = IntentSpec(slots=[SlotSpec(key="tone", description="답변 어조")])

    await use_case.execute(
        "만들어줘", spec, answers=[SlotAnswer(slot_key="tone", value="친근")], round_=1
    )
    await use_case.execute("만들어줘", spec)

    assert analyzer.calls[1]["answers"] is None
    assert analyzer.calls[1]["round_"] == 0


# --- degraded 는 UseCase 를 그대로 통과한다 (Plan D6) ------------------------


async def test_degraded_result_passes_through_without_raising() -> None:
    degraded = IntentResult(degraded=True)
    use_case = AnalyzeIntentUseCase(analyzer=SpyAnalyzer(result=degraded))

    result = await use_case.execute("여신 규정", _spec())

    assert result.degraded is True
    assert result.label is None


async def test_use_case_has_no_try_except_around_analyzer() -> None:
    """어댑터가 모든 예외를 흡수하는 것이 계약이므로 UseCase 는 감싸지 않는다.

    포트 계약을 어긴 구현이 있다면 조용히 삼키지 말고 드러나야 한다 (Design §6.1).
    """

    class BrokenAnalyzer(IntentAnalyzerInterface):
        async def analyze(
            self,
            message: str,
            spec: IntentSpec,
            history: list[Turn] | None = None,
            answers: list[SlotAnswer] | None = None,
            round_: int = 0,
            request_id: str = "",
        ) -> IntentResult:
            raise RuntimeError("포트 계약 위반")

    use_case = AnalyzeIntentUseCase(analyzer=BrokenAnalyzer())

    with pytest.raises(RuntimeError):
        await use_case.execute("여신 규정", _spec())
