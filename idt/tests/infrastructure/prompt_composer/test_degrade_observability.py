"""degraded 로그 관측성 — prompt-fallback-visibility FR-00d.

**왜 필요한가** (Design §1-1):
2026-09-04 이후 프롬프트 생성이 100% 타임아웃으로 폴백했지만, 로그에는
`"prompt generation timeout, fallback=degraded"` 와 `latency_ms` 뿐이었다.
**어떤 모델로 몇 초 예산에서 실패했는지**가 없어 원인 규명에 DB 포렌식이
필요했다 (prompt_version 테이블의 elapsed_ms 분포로 역추적).

실측: gpt-5.1 은 21.06~22.52s, gpt-4o-mini 는 4.48~6.37s.
타임아웃 20s 는 전자에서 **최소값조차 초과**한다. 이 한 줄이 있었다면
DB 를 뒤질 필요가 없었다.
"""
from typing import Any

import pytest

from src.domain.prompt_composer.schemas import ToolMeta
from src.infrastructure.config.prompt_composer_config import PromptComposerConfig
from src.infrastructure.prompt_composer.adapter import LLMPromptGeneratorAdapter

METAS = (ToolMeta(tool_id="internal:a", name="검색", description="문서를 찾는다"),)


class RecordingLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def debug(self, message: str, **kw: Any) -> None:
        self.records.append(("debug", message, kw))

    def info(self, message: str, **kw: Any) -> None:
        self.records.append(("info", message, kw))

    def warning(self, message: str, **kw: Any) -> None:
        self.records.append(("warning", message, kw))

    def error(self, message: str, exception: Any = None, **kw: Any) -> None:
        self.records.append(("error", message, kw))

    def critical(self, message: str, exception: Any = None, **kw: Any) -> None:
        self.records.append(("critical", message, kw))

    def degrade_kwargs(self) -> dict:
        for _lvl, msg, kw in self.records:
            if "fallback=degraded" in msg:
                return kw
        raise AssertionError(f"degrade 로그 없음: {[m for _, m, _ in self.records]}")


class SlowChain:
    """타임아웃을 유발하는 체인 대역."""

    async def ainvoke(self, payload: dict, config: dict | None = None) -> object:
        import asyncio

        await asyncio.sleep(10)
        raise AssertionError("unreachable")


class BoomChain:
    async def ainvoke(self, payload: dict, config: dict | None = None) -> object:
        raise RuntimeError("upstream 500")


def _adapter(chain: Any, logger: RecordingLogger, model: str = "gpt-5.1"):
    cfg = PromptComposerConfig(
        PROMPT_COMPOSER_MODEL=model,
        PROMPT_COMPOSER_TIMEOUT_SEC=0.05,
    )
    return LLMPromptGeneratorAdapter(logger=logger, config=cfg, chain=chain)


async def _generate(adapter) -> tuple:
    return await adapter.generate(
        user_request="엑셀 변환 에이전트", metas=METAS, intent=None,
        history=[], request_id="req-1",
    )


class TestTimeoutLogCarriesDiagnosis:
    """FR-00d — 타임아웃 로그만 보고 '모델 × 예산' 을 판단할 수 있어야 한다."""

    @pytest.fixture
    def logger(self) -> RecordingLogger:
        return RecordingLogger()

    async def test_degrades_on_timeout(self, logger: RecordingLogger) -> None:
        _, degraded, reason, _ = await _generate(_adapter(SlowChain(), logger))
        assert degraded is True
        assert reason == "timeout"

    async def test_logs_timeout_budget(self, logger: RecordingLogger) -> None:
        await _generate(_adapter(SlowChain(), logger))
        kw = logger.degrade_kwargs()
        assert kw.get("timeout_sec") == 0.05, (
            "예산이 없으면 '느린 것'과 '예산이 짧은 것'을 구분할 수 없다"
        )

    async def test_logs_model_name(self, logger: RecordingLogger) -> None:
        await _generate(_adapter(SlowChain(), logger, model="gpt-5.1"))
        kw = logger.degrade_kwargs()
        assert kw.get("model") == "gpt-5.1", (
            "모델명이 없으면 관리자가 기본 모델을 바꾼 사실이 드러나지 않는다"
        )

    async def test_keeps_latency(self, logger: RecordingLogger) -> None:
        """기존 latency_ms 는 유지한다 — 회귀 방지."""
        await _generate(_adapter(SlowChain(), logger))
        assert "latency_ms" in logger.degrade_kwargs()


class TestOtherReasonsAlsoDiagnosable:
    """타임아웃 외 사유에서도 동일 진단 정보가 실린다."""

    async def test_error_path_logs_model_and_budget(self) -> None:
        logger = RecordingLogger()
        _, degraded, reason, _ = await _generate(_adapter(BoomChain(), logger))
        assert (degraded, reason) == (True, "error")
        kw = logger.degrade_kwargs()
        assert kw.get("model") == "gpt-5.1"
        assert kw.get("timeout_sec") == 0.05


# ── provider 경로 (Check G1) ────────────────────────────────────────────────


class _ProviderLLM:
    """`UtilityLLMProvider` 가 돌려주는 LLM 스텁.

    `model_name` 속성을 갖는 것이 핵심이다 — `_active_model_name()` 이 읽는 값.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def with_structured_output(self, schema: Any, **kw: Any) -> Any:
        from langchain_core.runnables import RunnableLambda

        def _boom(_payload: Any) -> Any:
            raise RuntimeError("upstream 500")

        return RunnableLambda(_boom)


class _StubProvider:
    def __init__(self, llm: Any) -> None:
        self._llm = llm

    async def get(self, temperature: float = 0.0) -> Any:
        return self._llm

    async def invalidate(self) -> None: ...


def _provider_adapter(llm: Any, logger: RecordingLogger):
    """운영 배선과 동일하게 `llm_provider` 를 주입한다 (main.py:4379-4383)."""
    cfg = PromptComposerConfig(
        PROMPT_COMPOSER_MODEL="config-fallback-model",
        PROMPT_COMPOSER_TIMEOUT_SEC=5.0,
    )
    return LLMPromptGeneratorAdapter(
        logger=logger, config=cfg, llm_provider=_StubProvider(llm)
    )


class TestActiveModelNamePrefersProvider:
    """Check G1 — 운영 경로(provider 주입)에서 **해석된 모델명**이 찍혀야 한다.

    `chain=` 주입 테스트만으로는 `PROMPT_COMPOSER_MODEL` 폴백 분기밖에 못 친다.
    정작 진단에 필요한 값은 provider 가 해석해 준 모델명이다 — 기본 모델이
    gpt-5.1 로 바뀐 사실이 바로 이 값으로 드러난다.
    """

    async def test_logs_provider_resolved_model(self) -> None:
        logger = RecordingLogger()
        adapter = _provider_adapter(_ProviderLLM("gpt-5.1"), logger)

        _, degraded, reason, _ = await _generate(adapter)

        assert (degraded, reason) == (True, "error")
        kw = logger.degrade_kwargs()
        assert kw.get("model") == "gpt-5.1", (
            "provider 가 해석한 모델이 아니라 config 폴백값이 찍혔다 — "
            "어떤 모델이 실패했는지 알 수 없게 된다"
        )
        assert kw.get("model") != "config-fallback-model"

    async def test_falls_back_to_config_when_provider_returns_none(self) -> None:
        """provider 가 None 이면 ChatOpenAI 폴백이므로 config 값이 맞다 (DR-9)."""
        logger = RecordingLogger()
        cfg = PromptComposerConfig(
            PROMPT_COMPOSER_MODEL="config-fallback-model",
            PROMPT_COMPOSER_TIMEOUT_SEC=5.0,
        )
        adapter = LLMPromptGeneratorAdapter(
            logger=logger, config=cfg, llm_provider=_StubProvider(None)
        )
        adapter._chain = BoomChain()  # ChatOpenAI 실생성 회피

        _, degraded, _, _ = await _generate(adapter)

        assert degraded is True
        assert logger.degrade_kwargs().get("model") == "config-fallback-model"

    async def test_provider_fallback_is_warned(self) -> None:
        """provider 가 None 을 줬다는 사실도 로그에 남는다 (Do 부수 개선)."""
        logger = RecordingLogger()
        cfg = PromptComposerConfig(PROMPT_COMPOSER_TIMEOUT_SEC=5.0)
        adapter = LLMPromptGeneratorAdapter(
            logger=logger, config=cfg, llm_provider=_StubProvider(None)
        )
        adapter._chain = BoomChain()

        await _generate(adapter)

        assert any(
            "Utility LLM unavailable" in msg for _lvl, msg, _kw in logger.records
        )
