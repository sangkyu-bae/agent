"""builtin-middleware D8: MiddlewareBuilder — 인스턴스화 + 개별 실패 격하."""
import pytest

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


class TestApprovalGateFailClosed:
    """approval-gate Design §6.2 — 안전 기능은 조용히 빠지지 않는다.

    기존 4종은 '조립 실패 = warning 후 스킵' 이 맞다(편의 기능이 없다고
    실행을 막을 이유가 없다). 승인 게이트에 같은 정책을 적용하면 게이트
    버그 하나로 승인 없이 이메일이 나간다.
    """

    def test_build_approval_gate_는_워커별_새_인스턴스를_만든다(self):
        from src.application.middleware.middleware_builder import MiddlewareBuilder

        a = MiddlewareBuilder.build_approval_gate(tool_id="email_send", worker_id="w1")
        b = MiddlewareBuilder.build_approval_gate(tool_id="email_send", worker_id="w1")
        assert a is not b  # builtin-middleware D6: 상태 공유 금지

    def test_build_approval_gate_산출물이_게이트_미들웨어다(self):
        from src.application.approval.gate_middleware import ApprovalGateMiddleware
        from src.application.middleware.middleware_builder import MiddlewareBuilder

        gate = MiddlewareBuilder.build_approval_gate(
            tool_id="email_send", worker_id="w1"
        )
        assert isinstance(gate, ApprovalGateMiddleware)

    def test_build_one_에_APPROVAL_GATE가_오면_예외(self):
        """게이트는 워커별로 조립된다 — 공통 경로로 새면 도구를 모른 채
        모든 워커에 붙어 무해한 워커까지 막는다."""
        from src.domain.middleware.entities import AppliedMiddleware, MiddlewareType
        from src.application.middleware.middleware_builder import MiddlewareBuilder

        applied = AppliedMiddleware(
            middleware_type=MiddlewareType.APPROVAL_GATE, config={}, sort_order=100
        )
        with pytest.raises(ValueError):
            MiddlewareBuilder._build_one(applied, [])

    def test_build_는_APPROVAL_GATE_실패를_재전파한다(self):
        """fail-closed — 다른 타입과 달리 warning 후 스킵하지 않는다."""
        from unittest.mock import MagicMock

        from src.domain.middleware.entities import AppliedMiddleware, MiddlewareType
        from src.application.middleware.middleware_builder import MiddlewareBuilder

        builder = MiddlewareBuilder(logger=MagicMock())
        applied = [
            AppliedMiddleware(
                middleware_type=MiddlewareType.APPROVAL_GATE,
                config={}, sort_order=100,
            )
        ]
        with pytest.raises(ValueError):
            builder.build(applied, "req-1")

    def test_build_는_기존_타입_실패는_여전히_스킵한다(self):
        """무회귀 — 편의 미들웨어 정책은 그대로."""
        from unittest.mock import MagicMock

        from src.domain.middleware.entities import AppliedMiddleware, MiddlewareType
        from src.application.middleware.middleware_builder import MiddlewareBuilder

        logger = MagicMock()
        builder = MiddlewareBuilder(logger=logger)
        applied = [
            AppliedMiddleware(
                middleware_type=MiddlewareType.MODEL_FALLBACK,
                config={"fallback_models": ["x"]}, sort_order=30,
            )
        ]
        # 해석된 폴백 모델이 없으면 _build_one 이 ValueError 를 낸다
        assert builder.build(applied, "req-1") == []
        assert logger.warning.called
