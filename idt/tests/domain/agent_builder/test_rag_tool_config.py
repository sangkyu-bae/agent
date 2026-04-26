"""Tests for RagToolConfig VO and RagToolConfigPolicy. Domain: mock 금지."""
import pytest

from src.domain.agent_builder.rag_tool_config import RagToolConfig, RagToolConfigPolicy


class TestRagToolConfig:
    def test_default_values(self):
        config = RagToolConfig()
        assert config.collection_name is None
        assert config.es_index is None
        assert config.metadata_filter == {}
        assert config.top_k == 5
        assert config.search_mode == "hybrid"
        assert config.rrf_k == 60
        assert config.tool_name == "내부 문서 검색"
        assert config.tool_description != ""

    def test_custom_values(self):
        config = RagToolConfig(
            collection_name="finance_docs",
            es_index="finance_idx",
            metadata_filter={"department": "finance"},
            top_k=10,
            search_mode="vector_only",
            rrf_k=30,
            tool_name="금융 정책 검색",
            tool_description="금융 관련 내부 정책 문서를 검색합니다.",
        )
        assert config.collection_name == "finance_docs"
        assert config.metadata_filter == {"department": "finance"}
        assert config.top_k == 10
        assert config.search_mode == "vector_only"

    def test_frozen_immutability(self):
        config = RagToolConfig()
        with pytest.raises(AttributeError):
            config.top_k = 10

    def test_top_k_below_min_raises(self):
        with pytest.raises(ValueError, match="top_k must be 1~20"):
            RagToolConfig(top_k=0)

    def test_top_k_above_max_raises(self):
        with pytest.raises(ValueError, match="top_k must be 1~20"):
            RagToolConfig(top_k=21)

    def test_top_k_boundary_min(self):
        config = RagToolConfig(top_k=1)
        assert config.top_k == 1

    def test_top_k_boundary_max(self):
        config = RagToolConfig(top_k=20)
        assert config.top_k == 20

    def test_invalid_search_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid search_mode"):
            RagToolConfig(search_mode="full_text")

    def test_valid_search_modes(self):
        for mode in ("hybrid", "vector_only", "bm25_only"):
            config = RagToolConfig(search_mode=mode)
            assert config.search_mode == mode

    def test_rrf_k_below_min_raises(self):
        with pytest.raises(ValueError, match="rrf_k must be >= 1"):
            RagToolConfig(rrf_k=0)

    def test_from_dict_full(self):
        data = {
            "collection_name": "tech",
            "metadata_filter": {"category": "manual"},
            "top_k": 3,
            "search_mode": "bm25_only",
            "rrf_k": 40,
            "tool_name": "기술 매뉴얼",
            "tool_description": "기술 지원 매뉴얼을 검색합니다.",
        }
        config = RagToolConfig(**data)
        assert config.collection_name == "tech"
        assert config.tool_name == "기술 매뉴얼"

    def test_from_dict_partial_uses_defaults(self):
        config = RagToolConfig(**{"top_k": 8})
        assert config.top_k == 8
        assert config.search_mode == "hybrid"
        assert config.collection_name is None

    def test_from_none_uses_all_defaults(self):
        config = RagToolConfig()
        assert config.top_k == 5


class TestRagToolConfigPolicy:
    def test_valid_config_passes(self):
        config = RagToolConfig(
            metadata_filter={"a": "1", "b": "2"},
            tool_name="테스트",
            tool_description="설명",
        )
        RagToolConfigPolicy.validate(config)

    def test_metadata_filter_exceeds_max_raises(self):
        filters = {f"key_{i}": f"val_{i}" for i in range(11)}
        config = RagToolConfig(metadata_filter=filters)
        with pytest.raises(ValueError, match="metadata_filter max 10"):
            RagToolConfigPolicy.validate(config)

    def test_tool_name_too_long_raises(self):
        config = RagToolConfig(tool_name="x" * 101)
        with pytest.raises(ValueError, match="tool_name max 100"):
            RagToolConfigPolicy.validate(config)

    def test_tool_description_too_long_raises(self):
        config = RagToolConfig(tool_description="x" * 501)
        with pytest.raises(ValueError, match="tool_description max 500"):
            RagToolConfigPolicy.validate(config)

    def test_boundary_metadata_filter_10_passes(self):
        filters = {f"key_{i}": f"val_{i}" for i in range(10)}
        config = RagToolConfig(metadata_filter=filters)
        RagToolConfigPolicy.validate(config)

    def test_boundary_tool_name_100_passes(self):
        config = RagToolConfig(tool_name="x" * 100)
        RagToolConfigPolicy.validate(config)
