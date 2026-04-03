"""MiddlewareBuilder: MiddlewareConfig 목록 → LangChain 미들웨어 인스턴스 목록."""
try:
    from langchain.agents.middleware import (
        ModelCallLimitMiddleware,
        ModelFallbackMiddleware,
        PIIMiddleware,
        SummarizationMiddleware,
        ToolRetryMiddleware,
    )
except ImportError:  # pragma: no cover — langchain v1.0 alpha 미설치 환경 대비
    SummarizationMiddleware = None  # type: ignore
    PIIMiddleware = None  # type: ignore
    ToolRetryMiddleware = None  # type: ignore
    ModelCallLimitMiddleware = None  # type: ignore
    ModelFallbackMiddleware = None  # type: ignore

from src.domain.middleware_agent.schemas import MiddlewareConfig, MiddlewareType
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class MiddlewareBuilder:
    """MiddlewareConfig → 미들웨어 인스턴스 변환 (application 레이어)."""

    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def build(self, configs: list[MiddlewareConfig], request_id: str) -> list:
        """sort_order 정렬된 미들웨어 인스턴스 목록 반환."""
        sorted_configs = sorted(configs, key=lambda c: c.sort_order)
        instances = []
        for cfg in sorted_configs:
            instance = self._build_one(cfg, request_id)
            instances.append(instance)
            self._logger.info(
                "Middleware built",
                request_id=request_id,
                middleware_type=cfg.middleware_type.value,
            )
        return instances

    def _build_one(self, cfg: MiddlewareConfig, request_id: str):
        match cfg.middleware_type:
            case MiddlewareType.SUMMARIZATION:
                return SummarizationMiddleware(
                    model=cfg.config.get("model", "gpt-4o-mini"),
                    trigger=tuple(cfg.config.get("trigger", ("tokens", 4000))),
                    keep=tuple(cfg.config.get("keep", ("messages", 20))),
                )
            case MiddlewareType.PII:
                return PIIMiddleware(
                    cfg.config["pii_type"],
                    strategy=cfg.config.get("strategy", "redact"),
                    apply_to_input=cfg.config.get("apply_to_input", True),
                )
            case MiddlewareType.TOOL_RETRY:
                return ToolRetryMiddleware(
                    max_retries=cfg.config.get("max_retries", 3),
                    backoff_factor=cfg.config.get("backoff_factor", 2.0),
                    initial_delay=cfg.config.get("initial_delay", 1.0),
                )
            case MiddlewareType.MODEL_CALL_LIMIT:
                return ModelCallLimitMiddleware(
                    run_limit=cfg.config.get("run_limit", 10),
                    exit_behavior=cfg.config.get("exit_behavior", "end"),
                )
            case MiddlewareType.MODEL_FALLBACK:
                fallback_models = cfg.config.get("fallback_models", [])
                return ModelFallbackMiddleware(*fallback_models)
            case _:
                raise ValueError(f"Unsupported middleware type: {cfg.middleware_type!r}")
