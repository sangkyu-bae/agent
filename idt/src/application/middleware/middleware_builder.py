"""MiddlewareBuilder: AppliedMiddleware → langchain v1 미들웨어 인스턴스 (D8).

langchain v1 클래스 참조는 본 모듈에만 존재한다 (A→B 전환 격리 지점).
개별 인스턴스화 실패는 해당 미들웨어만 제외 + warning — 실행을 차단하지 않는다.
"""
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
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
    def build_tool_call_budget(run_limit: int):
        """Design Ref: mcp-tool-category-routing §5 D-05/D-11 (FR-10).

        미분류(react) 워커의 도구 호출 예산 미들웨어를 만든다.
        langchain v1 클래스 참조를 이 모듈 밖으로 새게 하지 않기 위한
        팩토리다(D8 격리 계약) — 컴파일러는 인스턴스만 받는다.

        exit_behavior="continue": 상한 초과분만 차단하고 모델은 그때까지
        수집한 내용으로 답변을 마무리한다. "end"는 즉시 중단이라 수집한
        내용의 종합이 유실된다.

        Args:
            run_limit: 워커 1회 실행당 허용 도구 호출 수

        Returns:
            ToolCallLimitMiddleware 인스턴스 (워커마다 새로 만들 것 — D6)
        """
        return ToolCallLimitMiddleware(
            run_limit=run_limit, exit_behavior="continue",
        )

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
