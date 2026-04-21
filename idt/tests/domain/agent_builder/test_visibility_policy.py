"""VisibilityPolicy 단위 테스트 — mock 금지."""
import pytest

from src.domain.agent_builder.policies import (
    AccessCheckInput,
    Visibility,
    VisibilityPolicy,
)


def _ctx(
    owner_id: str = "owner-1",
    visibility: str = "private",
    agent_dept_id: str | None = None,
    viewer_id: str = "viewer-1",
    viewer_dept_ids: list[str] | None = None,
    viewer_role: str = "user",
) -> AccessCheckInput:
    return AccessCheckInput(
        agent_owner_id=owner_id,
        agent_visibility=visibility,
        agent_department_id=agent_dept_id,
        viewer_user_id=viewer_id,
        viewer_department_ids=viewer_dept_ids or [],
        viewer_role=viewer_role,
    )


class TestCanAccess:
    def test_private_owner_can_access(self):
        ctx = _ctx(owner_id="user-1", visibility="private", viewer_id="user-1")
        assert VisibilityPolicy.can_access(ctx) is True

    def test_private_other_user_denied(self):
        ctx = _ctx(owner_id="user-1", visibility="private", viewer_id="user-2")
        assert VisibilityPolicy.can_access(ctx) is False

    def test_department_same_dept_can_access(self):
        ctx = _ctx(
            visibility="department",
            agent_dept_id="dept-a",
            viewer_id="user-2",
            viewer_dept_ids=["dept-a", "dept-b"],
        )
        assert VisibilityPolicy.can_access(ctx) is True

    def test_department_other_dept_denied(self):
        ctx = _ctx(
            visibility="department",
            agent_dept_id="dept-a",
            viewer_id="user-2",
            viewer_dept_ids=["dept-c"],
        )
        assert VisibilityPolicy.can_access(ctx) is False

    def test_department_no_dept_id_denied(self):
        ctx = _ctx(
            visibility="department",
            agent_dept_id=None,
            viewer_id="user-2",
            viewer_dept_ids=["dept-a"],
        )
        assert VisibilityPolicy.can_access(ctx) is False

    def test_public_any_authenticated_can_access(self):
        ctx = _ctx(visibility="public", viewer_id="anyone")
        assert VisibilityPolicy.can_access(ctx) is True


class TestCanEdit:
    def test_owner_can_edit(self):
        ctx = _ctx(owner_id="user-1", viewer_id="user-1")
        assert VisibilityPolicy.can_edit(ctx) is True

    def test_non_owner_cannot_edit(self):
        ctx = _ctx(owner_id="user-1", viewer_id="user-2")
        assert VisibilityPolicy.can_edit(ctx) is False


class TestCanDelete:
    def test_owner_can_delete(self):
        ctx = _ctx(owner_id="user-1", viewer_id="user-1")
        assert VisibilityPolicy.can_delete(ctx) is True

    def test_admin_can_delete(self):
        ctx = _ctx(owner_id="user-1", viewer_id="user-2", viewer_role="admin")
        assert VisibilityPolicy.can_delete(ctx) is True

    def test_non_owner_non_admin_cannot_delete(self):
        ctx = _ctx(owner_id="user-1", viewer_id="user-2", viewer_role="user")
        assert VisibilityPolicy.can_delete(ctx) is False
