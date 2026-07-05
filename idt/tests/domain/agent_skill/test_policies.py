"""Domain 테스트: SkillAttachPolicy / SkillInjectionPolicy."""
import pytest

from src.domain.agent_skill.policies import (
    InjectableSkill,
    SkillAttachPolicy,
    SkillInjectionPolicy,
)


class TestSkillAttachPolicy:
    def test_attach_ok_when_new_and_under_limit(self):
        SkillAttachPolicy.validate_attach(["a", "b"], "c")  # no raise

    def test_reject_duplicate(self):
        with pytest.raises(ValueError, match="이미 부착"):
            SkillAttachPolicy.validate_attach(["a", "b"], "a")

    def test_reject_when_at_max(self):
        existing = ["a", "b", "c"]  # MAX_ATTACHED == 3
        with pytest.raises(ValueError, match="최대"):
            SkillAttachPolicy.validate_attach(existing, "d")

    def test_validate_count_ok_at_max(self):
        SkillAttachPolicy.validate_count(["a", "b", "c"])  # no raise

    def test_validate_count_ok_empty(self):
        SkillAttachPolicy.validate_count([])  # no raise

    def test_validate_count_reject_over_max(self):
        with pytest.raises(ValueError, match="최대"):
            SkillAttachPolicy.validate_count(["a", "b", "c", "d"])


def _skill(name: str, instruction: str, order: int) -> InjectableSkill:
    return InjectableSkill(name=name, instruction=instruction, sort_order=order)


class TestSkillInjectionPolicy:
    def test_empty_returns_base_unchanged(self):
        base = "원본 시스템 프롬프트"
        assert SkillInjectionPolicy.merge(base, []) == base

    def test_blank_instructions_return_base_unchanged(self):
        base = "원본"
        assert SkillInjectionPolicy.merge(base, [_skill("s", "   ", 0)]) == base

    def test_prepends_in_sort_order(self):
        base = "BASE"
        skills = [
            _skill("둘째", "B내용", 1),
            _skill("첫째", "A내용", 0),
        ]
        merged = SkillInjectionPolicy.merge(base, skills)
        # base는 맨 끝, 첫째(order 0)가 둘째보다 앞
        assert merged.endswith("BASE")
        assert merged.index("첫째") < merged.index("둘째")
        assert "[부착된 스킬: 첫째]" in merged
        assert "A내용" in merged and "B내용" in merged

    def test_length_guard_excludes_overflow(self):
        base = "BASE"
        big = "x" * 30_000
        skills = [
            _skill("first", big, 0),
            _skill("second", big, 1),  # 누적 60k > 40k → 제외
        ]
        merged = SkillInjectionPolicy.merge(base, skills)
        assert "[부착된 스킬: first]" in merged
        assert "[부착된 스킬: second]" not in merged
