"""MiddlewareBuilder: AppliedMiddleware → langchain v1 미들웨어 인스턴스 (D8).

langchain v1 클래스 참조는 본 모듈에만 존재한다 (A→B 전환 격리 지점).
개별 인스턴스화 실패는 해당 미들웨어만 제외 + warning — 실행을 차단하지 않는다.
"""
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.middleware.entities import AppliedMiddleware, MiddlewareType


class MiddlewareBuilder:
    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def build(
        self,
        applied: list[AppliedMiddleware],
        request_id: str,
        fallback_models: list | None = None,
    ) -> list:
        """호출마다 새 인스턴스 목록 반환 — 워커 간 상태 공유 금지(D6).

        fallback_models: model_fallback용 사전 해석된 BaseChatModel 목록
        (해석은 async 경계인 MiddlewareProvider가 수행).
        """
        instances = []
        for a in applied:
            try:
                instances.append(self._build_one(a, fallback_models or []))
                self._logger.info(
                    "Middleware applied",
                    request_id=request_id,
                    middleware_type=a.middleware_type.value,
                )
            except Exception as e:
                self._logger.warning(
                    "Middleware build skipped",
                    request_id=request_id,
                    middleware_type=a.middleware_type.value,
                    exception=e,
                )
        return instances

    @staticmethod
    def _build_one(a: AppliedMiddleware, fallback_models: list):
        cfg = a.config
        match a.middleware_type:
            case MiddlewareType.MODEL_RETRY:
                return ModelRetryMiddleware(
                    max_retries=cfg.get("max_retries", 3),
                    backoff_factor=cfg.get("backoff_factor", 2.0),
                    initial_delay=cfg.get("initial_delay", 1.0),
                )
            case MiddlewareType.TOOL_RETRY:
                return ToolRetryMiddleware(
                    max_retries=cfg.get("max_retries", 2),
                    backoff_factor=cfg.get("backoff_factor", 2.0),
                    initial_delay=cfg.get("initial_delay", 1.0),
                )
            case MiddlewareType.MODEL_CALL_LIMIT:
                exit_behavior = cfg.get("exit_behavior", "end")
                if exit_behavior not in ("end", "error"):
                    raise ValueError(
                        f"invalid exit_behavior: {exit_behavior!r}"
                    )
                return ModelCallLimitMiddleware(
                    run_limit=cfg.get("run_limit", 10),
                    exit_behavior=exit_behavior,
                )
            case MiddlewareType.MODEL_FALLBACK:
                if not fallback_models:
                    raise ValueError("no resolvable fallback models")
                return ModelFallbackMiddleware(
                    fallback_models[0], *fallback_models[1:]
                )
            case _:
                raise ValueError(
                    f"unsupported middleware type: {a.middleware_type!r}"
                )
