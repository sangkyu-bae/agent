"""JudgmentSearchDecisionAdapter — Design §8.3 #8~11 (임계값·폴백·로그)."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from src.domain.judgment.exceptions import (
    JudgmentProtocolError,
    JudgmentTimeoutError,
    JudgmentUnavailableError,
)
from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import (
    JudgmentBackendKind,
    JudgmentRequest,
    JudgmentResponse,
    NoulAnswer,
)
from src.domain.search_decision.schemas import WebSearchDecision
from src.infrastructure.search_decision.judgment_adapter import (
    JudgmentSearchDecisionAdapter,
)
from src.infrastructure.search_decision.questions import QID, SEARCH_DECISION_NOUL

SECRET = "비밀-분석-본문"


class FakeBackend(JudgmentPort):
    kind = JudgmentBackendKind.ANYJEV

    def __init__(self, probability=None, error=None, delay: float = 0.0):
        self._p = probability
        self._error = error
        self._delay = delay
        self.requests: list[JudgmentRequest] = []

    async def judge(self, request):
        self.requests.append(request)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        return JudgmentResponse(
            answers={QID: NoulAnswer(self._p)},
            model="Tacit-9B",
            backend=self.kind,
            latency_ms=7,
        )


def _fallback(result=None) -> Mock:
    fb = Mock()
    fb.decide = AsyncMock(
        return_value=result or WebSearchDecision(needs_web_search=False, reason="llm")
    )
    return fb


def _adapter(backend, fallback=None, threshold=0.5, timeout=3.0, logger=None):
    return JudgmentSearchDecisionAdapter(
        backend=backend,
        fallback=fallback or _fallback(),
        threshold=threshold,
        timeout_seconds=timeout,
        logger=logger or Mock(),
    )


class TestThreshold:
    @pytest.mark.parametrize("p,expected", [(0.49, False), (0.50, True), (0.51, True)])
    async def test_boundary(self, p, expected):
        fb = _fallback()
        result = await _adapter(FakeBackend(p), fb).decide("q", "a", "req")
        assert result.needs_web_search is expected
        assert result.reason == f"judgment:anyjev p={p:.2f} thr=0.50"
        fb.decide.assert_not_awaited()

    async def test_request_shape(self):
        backend = FakeBackend(0.9)
        await _adapter(backend).decide("질문", "분석", "req")
        req = backend.requests[0]
        assert dict(req.state) == {"question": "질문", "analysis_text": "분석"}
        assert req.questions[QID].instructions == SEARCH_DECISION_NOUL

    def test_invalid_threshold_rejected(self):
        with pytest.raises(ValueError):
            _adapter(FakeBackend(0.5), threshold=1.5)


class TestFallback:
    @pytest.mark.parametrize(
        "error",
        [
            JudgmentTimeoutError(JudgmentBackendKind.ANYJEV, 3.0),
            JudgmentUnavailableError(JudgmentBackendKind.ANYJEV, "down", status=502),
            JudgmentProtocolError(JudgmentBackendKind.ANYJEV, "no Yes"),
        ],
    )
    async def test_backend_errors_fall_back(self, error):
        expected = WebSearchDecision(needs_web_search=True, reason="llm said so")
        fb = _fallback(expected)
        logger = Mock()
        result = await _adapter(FakeBackend(error=error), fb, logger=logger).decide(
            "q", "a", "req-9"
        )
        assert result is expected
        fb.decide.assert_awaited_once_with("q", "a", "req-9")
        logger.warning.assert_called_once()
        kw = logger.warning.call_args.kwargs
        assert kw["exception"] is error and kw["backend"] == "anyjev"
        assert kw["request_id"] == "req-9"

    async def test_outer_timeout_falls_back(self, monkeypatch):
        import src.infrastructure.search_decision.judgment_adapter as mod

        # 어댑터 내부 타임아웃 미작동 가정(가짜 백엔드) → 외부 wait_for 가 잡는다
        monkeypatch.setattr(mod, "_OUTER_TIMEOUT_MARGIN", 0.0)
        fb = _fallback()
        logger = Mock()
        adapter = _adapter(FakeBackend(0.9, delay=0.3), fb, timeout=0.01, logger=logger)
        await adapter.decide("q", "a", "req")
        fb.decide.assert_awaited_once()
        assert isinstance(logger.warning.call_args.kwargs["exception"], TimeoutError)

    async def test_fallback_result_passthrough_even_if_degraded(self):
        fb = _fallback(WebSearchDecision(needs_web_search=False))
        result = await _adapter(
            FakeBackend(error=JudgmentUnavailableError(JudgmentBackendKind.JEV, "x")),
            fb,
        ).decide("q", "a", "req")
        assert result.needs_web_search is False


class TestLogging:
    async def test_success_log_has_no_state_text(self):
        logger = Mock()
        await _adapter(FakeBackend(0.8), logger=logger).decide("q", SECRET, "req")
        logger.debug.assert_called_once()
        kw = logger.debug.call_args.kwargs
        assert SECRET not in str(kw) and SECRET not in logger.debug.call_args.args[0]
        assert kw["probability"] == 0.8 and kw["model"] == "Tacit-9B"
        assert len(kw["state_hash"]) == 12
