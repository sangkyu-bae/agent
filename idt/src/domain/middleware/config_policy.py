"""builtin-middleware D4: 미들웨어 default_config 검증 정책.

관리자 config 편집의 유일한 검증 지점 — 위반 시 ValueError(라우터 400 매핑).
폴백 모델의 등록 여부 확인은 I/O가 필요하므로 호출자(UseCase)가
active_model_names를 조회해 전달한다 (도메인 순수성 유지).
"""
from src.domain.middleware.entities import MiddlewareType

_RETRY_KEYS = {"max_retries", "backoff_factor", "initial_delay"}


class MiddlewareConfigPolicy:
    @staticmethod
    def validate(
        middleware_type: MiddlewareType,
        config: dict,
        active_model_names: set[str] | None = None,
    ) -> None:
        match middleware_type:
            case MiddlewareType.MODEL_RETRY | MiddlewareType.TOOL_RETRY:
                MiddlewareConfigPolicy._validate_retry(config)
            case MiddlewareType.MODEL_CALL_LIMIT:
                MiddlewareConfigPolicy._validate_call_limit(config)
            case MiddlewareType.MODEL_FALLBACK:
                MiddlewareConfigPolicy._validate_fallback(
                    config, active_model_names or set()
                )

    @staticmethod
    def _validate_retry(config: dict) -> None:
        _reject_unknown_keys(config, _RETRY_KEYS)
        max_retries = config.get("max_retries", 3)
        if not isinstance(max_retries, int) or not (0 <= max_retries <= 10):
            raise ValueError(f"max_retries must be 0~10, got {max_retries!r}")
        backoff = config.get("backoff_factor", 2.0)
        if not isinstance(backoff, (int, float)) or backoff < 1.0:
            raise ValueError(f"backoff_factor must be >= 1.0, got {backoff!r}")
        delay = config.get("initial_delay", 1.0)
        if not isinstance(delay, (int, float)) or delay < 0:
            raise ValueError(f"initial_delay must be >= 0, got {delay!r}")

    @staticmethod
    def _validate_call_limit(config: dict) -> None:
        _reject_unknown_keys(config, {"run_limit", "exit_behavior"})
        run_limit = config.get("run_limit", 10)
        if not isinstance(run_limit, int) or not (1 <= run_limit <= 50):
            raise ValueError(f"run_limit must be 1~50, got {run_limit!r}")
        exit_behavior = config.get("exit_behavior", "end")
        if exit_behavior not in ("end", "error"):
            raise ValueError(
                f"exit_behavior must be 'end' or 'error', got {exit_behavior!r}"
            )

    @staticmethod
    def _validate_fallback(config: dict, active_model_names: set[str]) -> None:
        _reject_unknown_keys(config, {"fallback_models"})
        models = config.get("fallback_models", [])
        if not isinstance(models, list) or any(
            not isinstance(m, str) for m in models
        ):
            raise ValueError("fallback_models must be a list of model names")
        unknown = [m for m in models if m not in active_model_names]
        if unknown:
            raise ValueError(
                f"fallback_models contains unregistered/inactive models: {unknown}"
            )


def _reject_unknown_keys(config: dict, allowed: set[str]) -> None:
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
