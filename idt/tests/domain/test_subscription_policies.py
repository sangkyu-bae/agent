"""ForkPolicy, SubscriptionPolicy 단위 테스트."""
import pytest

from src.domain.agent_builder.policies import AccessCheckInput, ForkPolicy, VisibilityPolicy
from src.domain.agent_builder.subscription import SubscriptionPolicy


def _ctx(
    owner_id: str = "owner-1",
    visibility: str = "public",
    department_id: str | None = None,
    viewer_id: str = "viewer-1",
    viewer_depts: list[str] | None = None,
    viewer_role: str = "user",
) -> AccessCheckInput:
    return AccessCheckInput(
        agent_owner_id=owner_id,
        agent_visibility=visibility,
        agent_department_id=department_id,
        viewer_user_id=viewer_id,
        viewer_department_ids=viewer_depts or [],
        viewer_role=viewer_role,
    )


class TestForkPolicy:
    def test_can_fork_public_agent(self):
        ctx = _ctx(owner_id="other", viewer_id="me", visibility="public")
        assert ForkPolicy.can_fork(ctx) is True

    def test_cannot_fork_own_agent(self):
        ctx = _ctx(owner_id="me", viewer_id="me", visibility="public")
        assert ForkPolicy.can_fork(ctx) is False

    def test_cannot_fork_private_agent(self):
        ctx = _ctx(owner_id="other", viewer_id="me", visibility="private")
        assert ForkPolicy.can_fork(ctx) is False

    def test_can_fork_department_agent_same_dept(self):
        ctx = _ctx(
            owner_id="other",
            viewer_id="me",
            visibility="department",
            department_id="dept-1",
            viewer_depts=["dept-1"],
        )
        assert ForkPolicy.can_fork(ctx) is True

    def test_cannot_fork_department_agent_diff_dept(self):
        ctx = _ctx(
            owner_id="other",
            viewer_id="me",
            visibility="department",
            department_id="dept-1",
            viewer_depts=["dept-2"],
        )
        assert ForkPolicy.can_fork(ctx) is False

    def test_validate_source_status_active(self):
        ForkPolicy.validate_source_status("active")

    def test_validate_source_status_deleted_raises(self):
        with pytest.raises(ValueError, match="삭제된 에이전트"):
            ForkPolicy.validate_source_status("deleted")


class TestSubscriptionPolicy:
    def test_can_subscribe_public_agent(self):
        ctx = _ctx(owner_id="other", viewer_id="me", visibility="public")
        assert SubscriptionPolicy.can_subscribe(ctx) is True

    def test_cannot_subscribe_own_agent(self):
        ctx = _ctx(owner_id="me", viewer_id="me", visibility="public")
        assert SubscriptionPolicy.can_subscribe(ctx) is False

    def test_cannot_subscribe_private_agent(self):
        ctx = _ctx(owner_id="other", viewer_id="me", visibility="private")
        assert SubscriptionPolicy.can_subscribe(ctx) is False

    def test_can_subscribe_department_agent_same_dept(self):
        ctx = _ctx(
            owner_id="other",
            viewer_id="me",
            visibility="department",
            department_id="dept-1",
            viewer_depts=["dept-1"],
        )
        assert SubscriptionPolicy.can_subscribe(ctx) is True
