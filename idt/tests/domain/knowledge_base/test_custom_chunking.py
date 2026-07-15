"""CustomChunkingConfig/Policy 검증 테스트 (kb-custom-chunking Design §4, V-01~V-07)."""
import pytest

from src.domain.knowledge_base.custom_chunking import (
    CustomBoundaryRule,
    CustomChunkingConfig,
    CustomChunkingPolicy,
    parse_custom_chunking_config,
)


def _config(**kw) -> CustomChunkingConfig:
    defaults = dict(strategy="full_token", chunk_size=500, chunk_overlap=50)
    defaults.update(kw)
    return CustomChunkingConfig(**defaults)


def _boundary_config(**kw) -> CustomChunkingConfig:
    defaults = dict(
        strategy="boundary_pattern",
        chunk_size=600,
        chunk_overlap=80,
        parent_chunk_size=3000,
        boundary_rules=[
            CustomBoundaryRule(pattern=r"^제\d+장", priority=1, level="parent"),
            CustomBoundaryRule(pattern=r"^\d+\.\s", priority=1, level="child"),
        ],
    )
    defaults.update(kw)
    return CustomChunkingConfig(**defaults)


class TestParse:
    def test_valid_dict_roundtrip(self):
        raw = {
            "version": 1,
            "strategy": "parent_child",
            "chunk_size": 800,
            "chunk_overlap": 100,
            "parent_chunk_size": 2500,
        }
        config = parse_custom_chunking_config(raw)
        assert config.strategy == "parent_child"
        assert config.chunk_size == 800
        assert config.parent_chunk_size == 2500

    def test_unknown_strategy_rejected(self):
        with pytest.raises(ValueError, match="custom_chunking_config"):
            parse_custom_chunking_config(
                {"strategy": "magic", "chunk_size": 500}
            )

    def test_missing_chunk_size_rejected(self):
        with pytest.raises(ValueError, match="custom_chunking_config"):
            parse_custom_chunking_config({"strategy": "full_token"})

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError, match="custom_chunking_config"):
            parse_custom_chunking_config("not-a-dict")


class TestRangeValidation:
    """V-01/V-02 — 수치 범위·관계."""

    def test_chunk_size_below_min(self):
        with pytest.raises(ValueError, match="chunk_size"):
            CustomChunkingPolicy.validate(_config(chunk_size=99))

    def test_chunk_size_above_max(self):
        with pytest.raises(ValueError, match="chunk_size"):
            CustomChunkingPolicy.validate(_config(chunk_size=4001))

    def test_overlap_above_max(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            CustomChunkingPolicy.validate(
                _config(chunk_size=4000, chunk_overlap=501)
            )

    def test_overlap_not_less_than_size(self):
        with pytest.raises(ValueError, match="less than chunk_size"):
            CustomChunkingPolicy.validate(
                _config(chunk_size=100, chunk_overlap=100)
            )

    def test_parent_size_out_of_range(self):
        with pytest.raises(ValueError, match="parent_chunk_size"):
            CustomChunkingPolicy.validate(
                _config(strategy="parent_child", parent_chunk_size=8001)
            )

    def test_chunk_size_exceeds_parent(self):
        with pytest.raises(ValueError, match="parent_chunk_size"):
            CustomChunkingPolicy.validate(
                _config(strategy="parent_child", chunk_size=3000,
                        parent_chunk_size=2000)
            )

    def test_min_chunk_size_out_of_range(self):
        with pytest.raises(ValueError, match="min_chunk_size"):
            CustomChunkingPolicy.validate(
                _config(strategy="semantic", chunk_overlap=0,
                        min_chunk_size=49)
            )

    def test_min_chunk_size_not_less_than_size(self):
        with pytest.raises(ValueError, match="min_chunk_size"):
            CustomChunkingPolicy.validate(
                _config(strategy="semantic", chunk_size=500,
                        chunk_overlap=0, min_chunk_size=500)
            )

    def test_valid_full_token_passes(self):
        CustomChunkingPolicy.validate(_config())


class TestStrategyParamMatrix:
    """V-03/V-05 — 전략별 금지 파라미터."""

    def test_full_token_rejects_parent_size(self):
        with pytest.raises(ValueError, match="full_token.*parent_chunk_size"):
            CustomChunkingPolicy.validate(_config(parent_chunk_size=2000))

    def test_full_token_rejects_boundary_rules(self):
        rules = [CustomBoundaryRule(pattern="^a", priority=1, level="parent")]
        with pytest.raises(ValueError, match="full_token.*boundary_rules"):
            CustomChunkingPolicy.validate(_config(boundary_rules=rules))

    def test_parent_child_rejects_min_chunk_size(self):
        with pytest.raises(ValueError, match="parent_child.*min_chunk_size"):
            CustomChunkingPolicy.validate(
                _config(strategy="parent_child", min_chunk_size=100)
            )

    def test_semantic_rejects_overlap(self):
        with pytest.raises(ValueError, match="semantic.*chunk_overlap"):
            CustomChunkingPolicy.validate(
                _config(strategy="semantic", chunk_overlap=50)
            )

    def test_semantic_zero_overlap_passes(self):
        CustomChunkingPolicy.validate(
            _config(strategy="semantic", chunk_overlap=0, min_chunk_size=200)
        )

    def test_section_aware_rejects_parent_size(self):
        with pytest.raises(ValueError, match="section_aware.*parent_chunk_size"):
            CustomChunkingPolicy.validate(
                _config(strategy="section_aware", parent_chunk_size=2000)
            )

    def test_boundary_pattern_rejects_min_chunk_size(self):
        with pytest.raises(ValueError, match="boundary_pattern.*min_chunk_size"):
            CustomChunkingPolicy.validate(
                _boundary_config(min_chunk_size=100)
            )


class TestBoundaryRules:
    """V-04 — 경계 규칙 검증."""

    def test_valid_rules_pass(self):
        CustomChunkingPolicy.validate(_boundary_config())

    def test_no_rules_rejected(self):
        with pytest.raises(ValueError, match="boundary rule"):
            CustomChunkingPolicy.validate(_boundary_config(boundary_rules=[]))

    def test_no_parent_level_rejected(self):
        rules = [CustomBoundaryRule(pattern="^a", priority=1, level="child")]
        with pytest.raises(ValueError, match="parent"):
            CustomChunkingPolicy.validate(
                _boundary_config(boundary_rules=rules)
            )

    def test_too_many_rules_rejected(self):
        rules = [
            CustomBoundaryRule(pattern=f"^{i}", priority=i, level="parent")
            for i in range(51)
        ]
        with pytest.raises(ValueError, match="max 50"):
            CustomChunkingPolicy.validate(
                _boundary_config(boundary_rules=rules)
            )

    def test_empty_pattern_rejected(self):
        rules = [CustomBoundaryRule(pattern="  ", priority=1, level="parent")]
        with pytest.raises(ValueError, match="empty"):
            CustomChunkingPolicy.validate(
                _boundary_config(boundary_rules=rules)
            )

    def test_too_long_pattern_rejected(self):
        rules = [
            CustomBoundaryRule(pattern="a" * 201, priority=1, level="parent")
        ]
        with pytest.raises(ValueError, match="max 200"):
            CustomChunkingPolicy.validate(
                _boundary_config(boundary_rules=rules)
            )

    def test_invalid_regex_error_contains_pattern(self):
        rules = [
            CustomBoundaryRule(pattern="[unclosed", priority=1, level="parent")
        ]
        with pytest.raises(ValueError, match=r"\[unclosed"):
            CustomChunkingPolicy.validate(
                _boundary_config(boundary_rules=rules)
            )


class TestKbSettingsValidation:
    """V-06/V-07 — KB 플래그·config 조합."""

    def test_both_toggles_rejected(self):
        with pytest.raises(ValueError, match="cannot both"):
            CustomChunkingPolicy.validate_kb_settings(
                use_clause_chunking=True,
                use_custom_chunking=True,
                custom_chunking_config=None,
            )

    def test_custom_without_config_rejected(self):
        with pytest.raises(ValueError, match="required"):
            CustomChunkingPolicy.validate_kb_settings(
                use_clause_chunking=False,
                use_custom_chunking=True,
                custom_chunking_config=None,
            )

    def test_config_without_toggle_rejected(self):
        with pytest.raises(ValueError, match="use_custom_chunking"):
            CustomChunkingPolicy.validate_kb_settings(
                use_clause_chunking=False,
                use_custom_chunking=False,
                custom_chunking_config={"strategy": "full_token",
                                        "chunk_size": 500},
            )

    def test_valid_custom_passes(self):
        CustomChunkingPolicy.validate_kb_settings(
            use_clause_chunking=False,
            use_custom_chunking=True,
            custom_chunking_config={"strategy": "full_token",
                                    "chunk_size": 500},
        )

    def test_all_off_passes(self):
        CustomChunkingPolicy.validate_kb_settings(
            use_clause_chunking=False,
            use_custom_chunking=False,
            custom_chunking_config=None,
        )


class TestFactoryMapping:
    """Design §3.2 — 전략별 factory 파라미터 매핑."""

    def test_full_token(self):
        config = _config(chunk_size=1500, chunk_overlap=150)
        assert config.factory_strategy() == "full_token"
        assert config.factory_params() == {
            "chunk_size": 1500, "chunk_overlap": 150,
        }

    def test_parent_child_maps_child_keys(self):
        config = _config(
            strategy="parent_child", chunk_size=400, chunk_overlap=40,
            parent_chunk_size=2500,
        )
        assert config.factory_strategy() == "parent_child"
        assert config.factory_params() == {
            "child_chunk_size": 400,
            "child_chunk_overlap": 40,
            "parent_chunk_size": 2500,
        }

    def test_parent_child_omits_unset_parent_size(self):
        config = _config(strategy="parent_child")
        assert "parent_chunk_size" not in config.factory_params()

    def test_semantic(self):
        config = _config(
            strategy="semantic", chunk_size=1000, chunk_overlap=0,
            min_chunk_size=200,
        )
        assert config.factory_params() == {
            "chunk_size": 1000, "min_chunk_size": 200,
        }

    def test_section_aware(self):
        config = _config(
            strategy="section_aware", chunk_size=2000, chunk_overlap=200,
            min_chunk_size=100,
        )
        assert config.factory_params() == {
            "chunk_size": 2000, "chunk_overlap": 200, "min_chunk_size": 100,
        }

    def test_boundary_pattern_maps_to_clause_aware(self):
        config = _boundary_config()
        assert config.factory_strategy() == "clause_aware"
        params = config.factory_params()
        assert params["parent_patterns"] == [r"^제\d+장"]
        assert params["child_patterns"] == [r"^\d+\.\s"]
        assert params["parent_chunk_size"] == 3000
        assert params["chunk_size"] == 600
        assert params["chunk_overlap"] == 80

    def test_boundary_patterns_sorted_by_priority(self):
        config = _boundary_config(boundary_rules=[
            CustomBoundaryRule(pattern="^B", priority=2, level="parent"),
            CustomBoundaryRule(pattern="^A", priority=1, level="parent"),
        ])
        assert config.factory_params()["parent_patterns"] == ["^A", "^B"]

    def test_display_marks_custom(self):
        display = _boundary_config().display()
        assert display["custom"] is True
        assert display["strategy"] == "boundary_pattern"
        assert display["boundary_rule_count"] == 2
