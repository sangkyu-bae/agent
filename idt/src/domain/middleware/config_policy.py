"""builtin-middleware D4: 미들웨어 default_config 검증 정책.

관리자 config 편집의 유일한 검증 지점 — 위반 시 ValueError(라우터 400 매핑).
폴백 모델의 등록 여부 확인은 I/O가 필요하므로 호출자(UseCase)가
active_model_names를 조회해 전달한다 (도메인 순수성 유지).
"""
from src.domain.middleware.entities import MiddlewareType

_RETRY_KEYS = {"max_retries", "backoff_factor", "initial_delay"}
# approval-gate Design §3.4
_GATE_KEYS = {"mode", "execute_after", "expires_hours", "on_expire", "timezone"}
_GATE_MODES = ("always", "off")
_GATE_MIN_HOURS = 1
_GATE_MAX_HOURS = 720


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
            case MiddlewareType.APPROVAL_GATE:
                MiddlewareConfigPolicy._validate_approval_gate(config)

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


    @staticmethod
    def _validate_approval_gate(config: dict) -> None:
        """approval-gate Design §3.4 — 저장 시점 방어.

        cron 을 여기서 막지 않으면 승인 시각 계산(집행 예약)에서 터진다.
        승인 버튼을 누른 사람이 원인을 알 수 없는 오류를 보게 되므로
        설정 저장 시점에 되돌려준다.
        """
        _reject_unknown_keys(config, _GATE_KEYS)
        mode = config.get("mode", "always")
        if mode not in _GATE_MODES:
            raise ValueError(f"mode must be one of {_GATE_MODES}, got {mode!r}")
        hours = config.get("expires_hours", 168)
        if (
            not isinstance(hours, int)
            or isinstance(hours, bool)
            or not (_GATE_MIN_HOURS <= hours <= _GATE_MAX_HOURS)
        ):
            raise ValueError(
                f"expires_hours must be {_GATE_MIN_HOURS}~{_GATE_MAX_HOURS}, "
                f"got {hours!r}"
            )
        on_expire = config.get("on_expire", "expire")
        if on_expire != "expire":
            raise ValueError(f"on_expire must be 'expire', got {on_expire!r}")
        MiddlewareConfigPolicy._validate_cron(config.get("execute_after"))
        MiddlewareConfigPolicy._validate_timezone(config.get("timezone"))

    @staticmethod
    def _validate_cron(expr: object) -> None:
        """None(즉시 집행) 또는 유효한 5필드 cron 만 허용.

        croniter 는 외부 I/O 없는 순수 계산 라이브러리로 domain 사용이
        허용된다 (agent_schedule/policies.py 선례).
        """
        if expr is None:
            return
        if not isinstance(expr, str):
            raise ValueError(f"execute_after must be a cron string, got {expr!r}")
        from croniter import croniter

        if len(expr.split()) != 5 or not croniter.is_valid(expr):
            raise ValueError(f"invalid cron expression: {expr!r}")


    @staticmethod
    def _validate_timezone(tz: object) -> None:
        """Check G13 — IANA 타임존만 허용. 잘못되면 승인 시각 계산에서 터진다."""
        if tz is None:
            return
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        if not isinstance(tz, str):
            raise ValueError(f"timezone must be a string, got {tz!r}")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown timezone: {tz!r}") from e


def _reject_unknown_keys(config: dict, allowed: set[str]) -> None:
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
