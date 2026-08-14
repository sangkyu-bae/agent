"""LLMIntentAnalyzerAdapter 단위 테스트.

Design §8.2 시나리오 10~15. 실제 LLM 을 호출하지 않고 fake chain 을 주입한다.
핵심 계약: **어떤 실패도 예외로 새어 나가지 않는다** (Plan D6 / Design E4~E6).
"""
import asyncio
from typing import Any

import pytest
from src.domain.intent.schemas import IntentLabel, IntentResult, IntentSpec, Turn
from src.infrastructure.config.intent_config import IntentConfig
from src.infrastructure.intent.adapter import LLMIntentAnalyzerAdapter


class RecordingLogger:
    """LoggerInterface 호환 스텁 — 호출 내역을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def debug(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("debug", message, kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("info", message, kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("warning", message, kwargs))

    def error(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        self.calls.append(("error", message, {"exception": exception, **kwargs}))

    def critical(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        self.calls.append(("critical", message, {"exception": exception, **kwargs}))

    def levels(self) -> list[str]:
        return [level for level, _, _ in self.calls]

    def kwargs_for(self, level: str) -> dict[str, Any]:
        for lvl, _, kwargs in self.calls:
            if lvl == level:
                return kwargs
        return {}


class FakeChain:
    """ainvoke 페이로드를 기록하고 정해진 반응을 돌려주는 fake."""

    def __init__(self, result: Any = None, raises: Exception | None = None,
                 delay: float = 0.0) -> None:
        self._result = result
        self._raises = raises
        self._delay = delay
        self.payloads: list[dict[str, Any]] = []

    async def ainvoke(self, payload: dict[str, Any]) -> Any:
        self.payloads.append(payload)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._result


def _spec(slots: list[str] | None = None) -> IntentSpec:
    return IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ],
        slots=slots or [],
    )


def _adapter(chain: FakeChain, timeout: float = 10.0) -> tuple[
    LLMIntentAnalyzerAdapter, RecordingLogger
]:
    logger = RecordingLogger()
    config = IntentConfig(INTENT_ANALYZER_TIMEOUT_SEC=timeout)
    adapter = LLMIntentAnalyzerAdapter(logger=logger, config=config, chain=chain)
    return adapter, logger


# --- 시나리오 13: 정상 경로 ------------------------------------------------


async def test_successful_analysis_returns_normalized_result() -> None:
    chain = FakeChain(result=IntentResult(label="search", confidence=0.82))
    adapter, logger = _adapter(chain)

    result = await adapter.analyze("여신 규정 알려줘", _spec())

    assert result.label == "search"
    assert result.confidence == pytest.approx(0.82)
    assert result.degraded is False
    assert "info" in logger.levels()


async def test_out_of_spec_label_is_demoted_not_degraded() -> None:
    """어댑터가 normalize 를 통과시키는지 확인 (Design E7)."""
    chain = FakeChain(result=IntentResult(label="weather", confidence=0.9))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("내일 날씨", _spec())

    assert result.label is None
    assert result.ambiguous is True
    assert result.degraded is False


async def test_llm_supplied_degraded_is_overridden() -> None:
    """LLM 이 degraded=True 를 반환해도 성공 경로면 False (Design §2.4 / E9)."""
    chain = FakeChain(
        result=IntentResult(label="search", confidence=0.5, degraded=True)
    )
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec())

    assert result.degraded is False


# --- 시나리오 10: LLM 예외 (E4) --------------------------------------------


async def test_chain_exception_returns_degraded_without_raising() -> None:
    chain = FakeChain(raises=RuntimeError("rate limit"))
    adapter, logger = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec(), request_id="req-1")

    assert result.degraded is True
    assert result.label is None
    assert result.confidence == pytest.approx(0.0)
    assert "error" in logger.levels()


async def test_chain_exception_logs_stack_trace_via_exception_kwarg() -> None:
    """error=str(e) 가 아니라 exception=e 로 기록해야 한다 (로깅 규약)."""
    boom = RuntimeError("boom")
    chain = FakeChain(raises=boom)
    adapter, logger = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    assert logger.kwargs_for("error").get("exception") is boom


# --- 시나리오 11: 타임아웃 (E5) ---------------------------------------------


async def test_timeout_returns_degraded() -> None:
    chain = FakeChain(result=IntentResult(label="search"), delay=0.2)
    adapter, logger = _adapter(chain, timeout=0.01)

    result = await adapter.analyze("여신 규정", _spec())

    assert result.degraded is True
    assert "warning" in logger.levels()


# --- 시나리오 12: 스키마 위반 (E6) ------------------------------------------


async def test_schema_violation_returns_degraded() -> None:
    chain = FakeChain(result={"label": "search", "confidence": "높음"})
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec())

    assert result.degraded is True


async def test_dict_payload_matching_schema_is_accepted() -> None:
    """구조화 출력이 dict 로 와도 스키마를 만족하면 정상 처리한다."""
    chain = FakeChain(result={"label": "analysis", "confidence": 0.4})
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("합계 계산해줘", _spec())

    assert result.label == "analysis"
    assert result.degraded is False


# --- 시나리오 14~15: history 처리 -------------------------------------------


async def test_history_none_renders_placeholder() -> None:
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(), history=None)

    assert chain.payloads[0]["history_block"] == "(없음)"


async def test_history_is_truncated_to_configured_limit() -> None:
    chain = FakeChain(result=IntentResult(label="search"))
    logger = RecordingLogger()
    config = IntentConfig(INTENT_ANALYZER_HISTORY_LIMIT=6)
    adapter = LLMIntentAnalyzerAdapter(logger=logger, config=config, chain=chain)
    history = [
        Turn(role="user" if i % 2 == 0 else "assistant", content=f"턴{i}")
        for i in range(20)
    ]

    await adapter.analyze("여신 규정", _spec(), history=history)

    block = chain.payloads[0]["history_block"]
    assert "턴19" in block
    assert "턴13" not in block, "최근 6턴(턴14~19)만 포함해야 한다"
    assert block.count("\n") == 5


# --- 프롬프트 조립 (Design §4.3) --------------------------------------------


async def test_labels_block_contains_every_label_with_description() -> None:
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    block = chain.payloads[0]["labels_block"]
    assert "- search: 근거 문서를 찾아야 하는 질문" in block
    assert "- analysis: 데이터를 계산·비교하는 질문" in block


async def test_slots_block_is_empty_when_no_slots_requested() -> None:
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    assert chain.payloads[0]["slots_block"] == ""


async def test_slots_block_lists_requested_slots() -> None:
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=["기간", "대상"]))

    block = chain.payloads[0]["slots_block"]
    assert "기간" in block and "대상" in block


async def test_unknown_block_is_empty_when_unknown_allowed() -> None:
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    assert chain.payloads[0]["unknown_block"] == ""


async def test_unknown_block_nudges_but_does_not_forbid_empty_label() -> None:
    """allow_unknown=False 는 힌트일 뿐 빈 label 을 금지하지 않는다 (Design §4.3).

    억지 선택을 강제하면 위키 계약 2(목록 프레이밍 과차단)를 재현하기 때문이다.
    """
    spec = IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ],
        allow_unknown=False,
    )
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", spec)

    block = chain.payloads[0]["unknown_block"]
    assert block != "", "힌트 문구가 들어가야 한다"
    assert "비워 두어도" in block, "빈 label 을 금지하는 문구여선 안 된다"


async def test_braces_in_message_do_not_break_prompt_assembly() -> None:
    """사용자 메시지의 중괄호가 템플릿 포매팅을 깨뜨리지 않아야 한다."""
    chain = FakeChain(result=IntentResult(label="search"))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("{여신} {{한도}} 규정", _spec())

    assert result.degraded is False
    assert chain.payloads[0]["message"] == "{여신} {{한도}} 규정"
