import pytest

from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.domain.chunking_profile.policy import ChunkingProfilePolicy


def _rules() -> list[BoundaryRule]:
    return [
        BoundaryRule(pattern="^제[0-9]+조", priority=1, level="parent"),
        BoundaryRule(pattern="^[ ]*[0-9]+[.]", priority=1, level="child"),
    ]


class TestValidateName:
    def test_korean_allowed(self):
        assert ChunkingProfilePolicy.validate_name("법령 기본") == "법령 기본"

    def test_strips(self):
        assert ChunkingProfilePolicy.validate_name("  이름 ") == "이름"

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_name("  ")

    def test_over_100_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_name("가" * 101)

    def test_control_char_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_name("이름\x00")


class TestValidateRules:
    def test_valid_rules_pass(self):
        ChunkingProfilePolicy.validate_rules(_rules())

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_rules([])

    def test_over_50_rejected(self):
        rules = [
            BoundaryRule(pattern="^제[0-9]+조", priority=i, level="parent")
            for i in range(51)
        ]
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_rules(rules)

    def test_invalid_regex_rejected(self):
        rules = [BoundaryRule(pattern="^제(조", priority=1, level="parent")]
        with pytest.raises(ValueError, match="invalid regex"):
            ChunkingProfilePolicy.validate_rules(rules)

    def test_pattern_over_200_rejected(self):
        rules = [
            BoundaryRule(pattern="a" * 201, priority=1, level="parent")
        ]
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_rules(rules)

    def test_bad_level_rejected(self):
        rules = [BoundaryRule(pattern="^x", priority=1, level="grandparent")]
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_rules(rules)

    def test_no_parent_rule_rejected(self):
        rules = [BoundaryRule(pattern="^[0-9]+[.]", priority=1, level="child")]
        with pytest.raises(ValueError, match="parent"):
            ChunkingProfilePolicy.validate_rules(rules)


class TestValidateSizes:
    def test_valid_pass(self):
        ChunkingProfilePolicy.validate_sizes(2000, 500, 50)

    def test_overlap_ge_size_rejected(self):
        with pytest.raises(ValueError, match="overlap"):
            ChunkingProfilePolicy.validate_sizes(2000, 500, 500)

    def test_child_gt_parent_rejected(self):
        with pytest.raises(ValueError, match="exceed"):
            ChunkingProfilePolicy.validate_sizes(400, 500, 50)

    def test_parent_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_sizes(50, 40, 0)

    def test_overlap_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_sizes(2000, 500, 999)


class TestValidateKbOverride:
    def test_both_none_ok(self):
        ChunkingProfilePolicy.validate_kb_override(None, None)

    def test_size_only_ok(self):
        ChunkingProfilePolicy.validate_kb_override(800, None)

    def test_overlap_without_size_rejected(self):
        with pytest.raises(ValueError, match="chunk_size is required"):
            ChunkingProfilePolicy.validate_kb_override(None, 50)

    def test_overlap_ge_size_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_kb_override(500, 500)

    def test_zero_overlap_ok(self):
        ChunkingProfilePolicy.validate_kb_override(500, 0)

    def test_size_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.validate_kb_override(99, None)


class TestCanDelete:
    def test_default_rejected(self):
        p = ChunkingProfile(name="d", is_default=True)
        with pytest.raises(ValueError):
            ChunkingProfilePolicy.can_delete(p)

    def test_non_default_ok(self):
        p = ChunkingProfile(name="d", is_default=False)
        ChunkingProfilePolicy.can_delete(p)
