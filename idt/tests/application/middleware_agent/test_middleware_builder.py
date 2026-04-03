"""application/middleware_agent/middleware_builder 단위 테스트."""
from unittest.mock import MagicMock, patch
import pytest

from src.application.middleware_agent.middleware_builder import MiddlewareBuilder
from src.domain.middleware_agent.schemas import MiddlewareConfig, MiddlewareType


def _make_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


def _cfg(t: MiddlewareType, config: dict = None, order: int = 0) -> MiddlewareConfig:
    return MiddlewareConfig(middleware_type=t, config=config or {}, sort_order=order)


class TestMiddlewareBuilder:

    def test_build_empty_configs_returns_empty_list(self):
        builder = MiddlewareBuilder(logger=_make_logger())
        result = builder.build([], request_id="req-1")
        assert result == []

    @patch("src.application.middleware_agent.middleware_builder.SummarizationMiddleware")
    def test_build_summarization_middleware(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        builder = MiddlewareBuilder(logger=_make_logger())
        cfg = _cfg(
            MiddlewareType.SUMMARIZATION,
            {"model": "gpt-4o-mini", "trigger": ["tokens", 4000], "keep": ["messages", 20]},
        )
        result = builder.build([cfg], request_id="req-1")

        assert len(result) == 1
        assert result[0] is mock_instance
        mock_cls.assert_called_once()

    @patch("src.application.middleware_agent.middleware_builder.PIIMiddleware")
    def test_build_pii_middleware(self, mock_cls):
        mock_cls.return_value = MagicMock()
        builder = MiddlewareBuilder(logger=_make_logger())
        cfg = _cfg(MiddlewareType.PII, {"pii_type": "email", "strategy": "redact", "apply_to_input": True})
        result = builder.build([cfg], request_id="req-1")

        assert len(result) == 1
        mock_cls.assert_called_once_with("email", strategy="redact", apply_to_input=True)

    @patch("src.application.middleware_agent.middleware_builder.ToolRetryMiddleware")
    def test_build_tool_retry_middleware(self, mock_cls):
        mock_cls.return_value = MagicMock()
        builder = MiddlewareBuilder(logger=_make_logger())
        cfg = _cfg(MiddlewareType.TOOL_RETRY, {"max_retries": 3, "backoff_factor": 2.0, "initial_delay": 1.0})
        builder.build([cfg], request_id="req-1")
        mock_cls.assert_called_once_with(max_retries=3, backoff_factor=2.0, initial_delay=1.0)

    @patch("src.application.middleware_agent.middleware_builder.ModelCallLimitMiddleware")
    def test_build_model_call_limit_middleware(self, mock_cls):
        mock_cls.return_value = MagicMock()
        builder = MiddlewareBuilder(logger=_make_logger())
        cfg = _cfg(MiddlewareType.MODEL_CALL_LIMIT, {"run_limit": 5, "exit_behavior": "end"})
        builder.build([cfg], request_id="req-1")
        mock_cls.assert_called_once_with(run_limit=5, exit_behavior="end")

    @patch("src.application.middleware_agent.middleware_builder.ModelFallbackMiddleware")
    def test_build_model_fallback_middleware(self, mock_cls):
        mock_cls.return_value = MagicMock()
        builder = MiddlewareBuilder(logger=_make_logger())
        cfg = _cfg(MiddlewareType.MODEL_FALLBACK, {"fallback_models": ["gpt-4o-mini", "claude-3-5-sonnet-20241022"]})
        builder.build([cfg], request_id="req-1")
        mock_cls.assert_called_once_with("gpt-4o-mini", "claude-3-5-sonnet-20241022")

    @patch("src.application.middleware_agent.middleware_builder.PIIMiddleware")
    @patch("src.application.middleware_agent.middleware_builder.SummarizationMiddleware")
    def test_build_respects_sort_order(self, mock_summ, mock_pii):
        mock_summ.return_value = MagicMock(name="summ")
        mock_pii.return_value = MagicMock(name="pii")

        builder = MiddlewareBuilder(logger=_make_logger())
        # PII sort_order=0, SUMMARIZATION sort_order=1 → PII 먼저
        cfgs = [
            _cfg(MiddlewareType.SUMMARIZATION, {}, order=1),
            _cfg(MiddlewareType.PII, {"pii_type": "email"}, order=0),
        ]
        result = builder.build(cfgs, request_id="req-1")

        assert result[0] is mock_pii.return_value
        assert result[1] is mock_summ.return_value

    def test_unsupported_type_raises(self):
        builder = MiddlewareBuilder(logger=_make_logger())

        class FakeConfig:
            middleware_type = "not_a_real_type"
            config = {}
            sort_order = 0

        with pytest.raises((ValueError, AttributeError)):
            builder._build_one(FakeConfig(), "req-1")  # type: ignore
