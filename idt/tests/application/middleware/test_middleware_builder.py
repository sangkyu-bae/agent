"""builtin-middleware D8: MiddlewareBuilder — 인스턴스화 + 개별 실패 격하."""
from unittest.mock import MagicMock

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)

from src.application.middleware.middleware_builder import MiddlewareBuilder
from src.domain.middleware.entities import AppliedMiddleware, MiddlewareType


def _applied(mw_type: MiddlewareType, config: dict | None = None) -> AppliedMiddleware:
    return AppliedMiddleware(
        middleware_type=mw_type, config=config or {}, sort_order=0
    )


def _builder() -> tuple[MiddlewareBuilder, MagicMock]:
    logger = MagicMock()
    return MiddlewareBuilder(logger=logger), logger


class TestBuildEach:
    def test_model_retry(self):
        builder, _ = _builder()
        out = builder.build(
            [_applied(MiddlewareType.MODEL_RETRY, {"max_retries": 5})], "req-1"
        )
        assert len(out) == 1
        assert isinstance(out[0], ModelRetryMiddleware)

    def test_tool_retry(self):
        builder, _ = _builder()
        out = builder.build([_applied(MiddlewareType.TOOL_RETRY)], "req-1")
        assert isinstance(out[0], ToolRetryMiddleware)

    def test_model_call_limit(self):
        builder, _ = _builder()
        out = builder.build(
            [
                _applied(
                    MiddlewareType.MODEL_CALL_LIMIT,
                    {"run_limit": 3, "exit_behavior": "end"},
                )
            ],
            "req-1",
        )
        assert isinstance(out[0], ModelCallLimitMiddleware)

    def test_model_fallback_with_resolved_models(self):
        builder, _ = _builder()
        fake_model = MagicMock()
        out = builder.build(
            [_applied(MiddlewareType.MODEL_FALLBACK)],
            "req-1",
            fallback_models=[fake_model],
        )
        assert isinstance(out[0], ModelFallbackMiddleware)


class TestDegradation:
    def test_fallback_모델_미해석이면_제외_경고_계속(self):
        """D8: 폴백 모델 0개 → 해당 미들웨어만 제외, 나머지는 조립."""
        builder, logger = _builder()
        out = builder.build(
            [
                _applied(MiddlewareType.MODEL_FALLBACK),
                _applied(MiddlewareType.MODEL_RETRY),
            ],
            "req-1",
        )
        assert len(out) == 1
        assert isinstance(out[0], ModelRetryMiddleware)
        logger.warning.assert_called()

    def test_설정_오류는_해당_미들웨어만_제외(self):
        builder, logger = _builder()
        out = builder.build(
            [
                _applied(MiddlewareType.MODEL_CALL_LIMIT, {"exit_behavior": "폭발"}),
                _applied(MiddlewareType.TOOL_RETRY),
            ],
            "req-1",
        )
        assert len(out) == 1
        assert isinstance(out[0], ToolRetryMiddleware)
        logger.warning.assert_called()

    def test_빌드마다_새_인스턴스(self):
        """D6: 워커 간 미들웨어 상태 공유 금지 — 호출마다 신규 인스턴스."""
        builder, _ = _builder()
        applied = [_applied(MiddlewareType.MODEL_RETRY)]
        first = builder.build(applied, "req-1")
        second = builder.build(applied, "req-1")
        assert first[0] is not second[0]
