"""Domain 테스트: SkillBuilderPolicy / SkillVisibilityPolicy / SkillForkPolicy."""
import pytest

from src.domain.skill_builder.policies import (
    SkillAccessInput,
    SkillBuilderPolicy,
    SkillForkPolicy,
    SkillVisibilityPolicy,
)


class TestValidateName:
    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="비어"):
            SkillBuilderPolicy.validate_name("  ")

    def test_too_long_name_raises(self):
        with pytest.raises(ValueError, match="초과"):
            SkillBuilderPolicy.validate_name("a" * 256)

    def test_valid_name_ok(self):
        SkillBuilderPolicy.validate_name("환율 계산기")


class TestValidateInstruction:
    def test_empty_instruction_raises(self):
        with pytest.raises(ValueError, match="비어"):
            SkillBuilderPolicy.validate_instruction("")

    def test_valid_instruction_ok(self):
        SkillBuilderPolicy.validate_instruction("이렇게 동작하라")


class TestValidateScript:
    def test_unknown_script_type_raises(self):
        with pytest.raises(ValueError, match="script_type"):
            SkillBuilderPolicy.validate_script("ruby", "puts 1")

    def test_none_type_with_content_raises(self):
        with pytest.raises(ValueError, match="none"):
            SkillBuilderPolicy.validate_script("none", "print(1)")

    def test_python_type_with_content_ok(self):
        SkillBuilderPolicy.validate_script("python", "print(1)")

    def test_none_type_without_content_ok(self):
        SkillBuilderPolicy.validate_script("none", None)


class TestValidateVisibility:
    def test_unknown_visibility_raises(self):
        with pytest.raises(ValueError, match="visibility"):
            SkillBuilderPolicy.validate_visibility("secret", None)

    def test_department_without_dept_id_raises(self):
        with pytest.raises(ValueError, match="department"):
            SkillBuilderPolicy.validate_visibility("department", None)

    def test_department_with_dept_id_ok(self):
        SkillBuilderPolicy.validate_visibility("department", "dept-1")


def _ctx(**overrides) -> SkillAccessInput:
    base = dict(
        owner_id="owner",
        visibility="private",
        department_id=None,
        viewer_user_id="viewer",
        viewer_department_ids=[],
        viewer_role="user",
    )
    base.update(overrides)
    return SkillAccessInput(**base)


class TestVisibilityPolicy:
    def test_owner_can_access_private(self):
        assert SkillVisibilityPolicy.can_access(_ctx(viewer_user_id="owner")) is True

    def test_other_cannot_access_private(self):
        assert SkillVisibilityPolicy.can_access(_ctx()) is False

    def test_anyone_can_access_public(self):
        assert SkillVisibilityPolicy.can_access(_ctx(visibility="public")) is True

    def test_department_member_can_access(self):
        ctx = _ctx(
            visibility="department",
            department_id="d1",
            viewer_department_ids=["d1"],
        )
        assert SkillVisibilityPolicy.can_access(ctx) is True

    def test_non_member_cannot_access_department(self):
        ctx = _ctx(
            visibility="department",
            department_id="d1",
            viewer_department_ids=["d2"],
        )
        assert SkillVisibilityPolicy.can_access(ctx) is False

    def test_only_owner_can_edit(self):
        assert SkillVisibilityPolicy.can_edit(_ctx(viewer_user_id="owner")) is True
        assert SkillVisibilityPolicy.can_edit(_ctx()) is False

    def test_admin_can_delete(self):
        assert SkillVisibilityPolicy.can_delete(_ctx(viewer_role="admin")) is True


class TestForkPolicy:
    def test_owner_cannot_fork_own(self):
        assert SkillForkPolicy.can_fork(_ctx(viewer_user_id="owner")) is False

    def test_can_fork_accessible_public(self):
        assert SkillForkPolicy.can_fork(_ctx(visibility="public")) is True

    def test_deleted_source_raises(self):
        with pytest.raises(ValueError, match="삭제"):
            SkillForkPolicy.validate_source_status("deleted")
