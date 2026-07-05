"""Domain 테스트: SkillDefinition 엔티티 (apply_update / soft_delete / fork_for)."""
from datetime import datetime

import pytest

from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)


def _make_skill(**overrides) -> SkillDefinition:
    base = dict(
        id="skill-1",
        user_id="user-1",
        name="환율 계산기",
        description="통화 환율 변환",
        instruction="환율 변환 요청 시 ...",
        trigger="환율, 통화 변환",
        script_type=SkillScriptType.PYTHON,
        script_content="def convert(): ...",
        status="active",
        visibility=SkillVisibility.PRIVATE,
        department_id=None,
        forked_from=None,
        forked_at=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    base.update(overrides)
    return SkillDefinition(**base)


class TestSkillInvariant:
    def test_department_visibility_requires_department_id(self):
        with pytest.raises(ValueError, match="department"):
            _make_skill(visibility=SkillVisibility.DEPARTMENT, department_id=None)

    def test_department_visibility_with_department_id_ok(self):
        skill = _make_skill(
            visibility=SkillVisibility.DEPARTMENT, department_id="dept-1"
        )
        assert skill.department_id == "dept-1"


class TestApplyUpdate:
    def test_partial_update_changes_only_given_fields(self):
        skill = _make_skill()
        skill.apply_update(name="새 이름")
        assert skill.name == "새 이름"
        assert skill.instruction == "환율 변환 요청 시 ..."

    def test_update_to_department_without_dept_raises(self):
        skill = _make_skill()
        with pytest.raises(ValueError, match="department"):
            skill.apply_update(visibility=SkillVisibility.DEPARTMENT)


class TestSoftDelete:
    def test_soft_delete_sets_status_deleted(self):
        skill = _make_skill()
        skill.soft_delete()
        assert skill.status == "deleted"


class TestForkFor:
    def test_fork_creates_private_copy_with_new_owner(self):
        src = _make_skill(visibility=SkillVisibility.PUBLIC)
        forked = src.fork_for("skill-2", "user-2", datetime(2026, 2, 2))
        assert forked.id == "skill-2"
        assert forked.user_id == "user-2"
        assert forked.visibility == SkillVisibility.PRIVATE
        assert forked.department_id is None
        assert forked.forked_from == "skill-1"
        assert forked.forked_at == datetime(2026, 2, 2)
        assert forked.status == "active"
        # 본문은 복제
        assert forked.instruction == src.instruction
        assert forked.script_content == src.script_content
