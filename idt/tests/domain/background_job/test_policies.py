"""Domain 테스트: JobTransitionPolicy / JobQueuePolicy."""
import pytest

from src.domain.background_job.policies import (
    ERROR_MESSAGE_MAX,
    JobQueuePolicy,
    JobTransitionPolicy,
)


class TestJobTransitionPolicy:
    @pytest.mark.parametrize(
        "current,new",
        [
            ("queued", "running"),
            ("queued", "failed"),
            ("running", "success"),
            ("running", "failed"),
        ],
    )
    def test_allowed_transitions(self, current, new):
        assert JobTransitionPolicy.can_transition(current, new) is True

    @pytest.mark.parametrize(
        "current,new",
        [
            ("queued", "success"),  # 실행 없이 성공 불가
            ("running", "queued"),  # 역행 불가
            ("success", "failed"),  # 종결 후 재전이 불가
            ("success", "running"),
            ("failed", "running"),
            ("failed", "success"),
            ("queued", "queued"),
            ("unknown", "running"),
        ],
    )
    def test_denied_transitions(self, current, new):
        assert JobTransitionPolicy.can_transition(current, new) is False


class TestJobQueuePolicy:
    def test_truncate_error_none_passthrough(self):
        assert JobQueuePolicy.truncate_error(None) is None

    def test_truncate_error_short_unchanged(self):
        assert JobQueuePolicy.truncate_error("boom") == "boom"

    def test_truncate_error_caps_at_max(self):
        long = "x" * (ERROR_MESSAGE_MAX + 100)
        assert len(JobQueuePolicy.truncate_error(long)) == ERROR_MESSAGE_MAX

    def test_validate_concurrency_rejects_zero(self):
        with pytest.raises(ValueError):
            JobQueuePolicy.validate_concurrency(0)

    def test_validate_concurrency_accepts_one(self):
        JobQueuePolicy.validate_concurrency(1)  # no raise
