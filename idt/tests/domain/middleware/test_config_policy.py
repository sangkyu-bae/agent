"""MiddlewareConfigPolicy 단위 테스트.

approval-gate Design §8.3 — APPROVAL_GATE case 를 추가하면서 기존 4종
검증도 함께 고정한다. 이 파일 이전에는 config_policy 테스트가 0건이라
신규 case 추가가 기존 검증을 깨뜨려도 알 길이 없었다.
"""
import pytest

from src.domain.middleware.config_policy import MiddlewareConfigPolicy
from src.domain.middleware.entities import MiddlewareType


class TestRetryConfig:
    @pytest.mark.parametrize(
        "mw_type", [MiddlewareType.MODEL_RETRY, MiddlewareType.TOOL_RETRY]
    )
    def test_기본값_통과(self, mw_type):
        MiddlewareConfigPolicy.validate(mw_type, {})

    def test_유효_범위_통과(self):
        MiddlewareConfigPolicy.validate(
            MiddlewareType.MODEL_RETRY,
            {"max_retries": 5, "backoff_factor": 2.0, "initial_delay": 1.0},
        )

    @pytest.mark.parametrize("bad", [-1, 11, "3", None])
    def test_max_retries_범위_위반(self, bad):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_RETRY, {"max_retries": bad}
            )

    def test_backoff_하한_위반(self):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_RETRY, {"backoff_factor": 0.5}
            )

    def test_미지_키_거부(self):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_RETRY, {"오타키": 1}
            )


class TestCallLimitConfig:
    def test_기본값_통과(self):
        MiddlewareConfigPolicy.validate(MiddlewareType.MODEL_CALL_LIMIT, {})

    @pytest.mark.parametrize("bad", [0, 51, "10"])
    def test_run_limit_범위_위반(self, bad):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_CALL_LIMIT, {"run_limit": bad}
            )

    def test_exit_behavior_허용값(self):
        for v in ("end", "error"):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_CALL_LIMIT, {"exit_behavior": v}
            )

    def test_exit_behavior_위반(self):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_CALL_LIMIT, {"exit_behavior": "continue"}
            )


class TestFallbackConfig:
    def test_등록된_모델만_통과(self):
        MiddlewareConfigPolicy.validate(
            MiddlewareType.MODEL_FALLBACK,
            {"fallback_models": ["gpt-4o"]},
            active_model_names={"gpt-4o"},
        )

    def test_미등록_모델_거부(self):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.MODEL_FALLBACK,
                {"fallback_models": ["없는모델"]},
                active_model_names={"gpt-4o"},
            )


class TestApprovalGateConfig:
    """approval-gate Design §3.4 — 허용 키 4종."""

    def test_기본값_통과(self):
        MiddlewareConfigPolicy.validate(MiddlewareType.APPROVAL_GATE, {})

    def test_금리_시나리오_설정_통과(self):
        MiddlewareConfigPolicy.validate(
            MiddlewareType.APPROVAL_GATE,
            {"mode": "always", "execute_after": "0 0 * * *",
             "expires_hours": 24, "on_expire": "expire"},
        )

    def test_미지_키_거부(self):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"auto_approve": True}
            )

    @pytest.mark.parametrize("bad", ["auto", "on", "", 1])
    def test_mode_허용값_위반(self, bad):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"mode": bad}
            )

    def test_mode_허용값(self):
        for v in ("always", "off"):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"mode": v}
            )

    @pytest.mark.parametrize("bad", [0, 721, "24", True])
    def test_expires_hours_범위_위반(self, bad):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"expires_hours": bad}
            )

    def test_execute_after_null_허용(self):
        """즉시 집행 — 기존 동작."""
        MiddlewareConfigPolicy.validate(
            MiddlewareType.APPROVAL_GATE, {"execute_after": None}
        )

    @pytest.mark.parametrize("bad", ["매일 자정", "0 0 * *", "* * * * * *", 5])
    def test_잘못된_cron_거부(self, bad):
        """저장 시점에 막지 않으면 승인 시각 계산에서 터진다."""
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"execute_after": bad}
            )

    def test_on_expire_허용값_위반(self):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"on_expire": "approve"}
            )


class TestApprovalGateTimezone:
    """Check G13 — cron 해석 기준 타임존."""

    def test_유효한_타임존_통과(self):
        for tz in ("Asia/Seoul", "UTC", "America/New_York"):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"timezone": tz}
            )

    @pytest.mark.parametrize("bad", ["KST", "Seoul", "", 9])
    def test_잘못된_타임존_거부(self, bad):
        with pytest.raises(ValueError):
            MiddlewareConfigPolicy.validate(
                MiddlewareType.APPROVAL_GATE, {"timezone": bad}
            )
