"""UnifiedUploadUseCase._build_strategy 분기 검증 (clause-aware-chunking Design §10).

chunking_config 미지정 시 기존 parent_child 동작 완전 불변(회귀 가드).
"""
from unittest.mock import MagicMock

from src.application.unified_upload.schemas import (
    UnifiedUploadRequest,
    UploadChunkingConfig,
)
from src.application.unified_upload.use_case import UnifiedUploadUseCase


def _use_case() -> UnifiedUploadUseCase:
    return UnifiedUploadUseCase(
        parser=MagicMock(),
        collection_repo=MagicMock(),
        activity_log_repo=MagicMock(),
        embedding_model_repo=MagicMock(),
        embedding_factory=MagicMock(),
        qdrant_client=MagicMock(),
        es_repo=MagicMock(),
        es_index="idx",
        morph_analyzer=MagicMock(),
        document_metadata_repo=MagicMock(),
        activity_log_service=MagicMock(),
        logger=MagicMock(),
    )


def _req(**kw) -> UnifiedUploadRequest:
    defaults = dict(
        file_bytes=b"x", filename="f.pdf", user_id="1",
        collection_name="col",
    )
    defaults.update(kw)
    return UnifiedUploadRequest(**defaults)


class TestBuildStrategyLegacy:
    def test_none_uses_parent_child(self):
        strategy, name, config = _use_case()._build_strategy(_req())
        assert name == "parent_child"
        assert config["strategy"] == "parent_child"
        assert config["child_chunk_size"] == 500
        assert config["child_chunk_overlap"] == 50

    def test_none_respects_query_params(self):
        _, _, config = _use_case()._build_strategy(
            _req(child_chunk_size=800, child_chunk_overlap=80)
        )
        assert config["child_chunk_size"] == 800
        assert config["child_chunk_overlap"] == 80


class TestBuildStrategyClause:
    def test_clause_config_delegated(self):
        cfg = UploadChunkingConfig(
            strategy="clause_aware",
            params={
                "parent_patterns": ["^제[0-9]+조"],
                "child_patterns": ["^[ ]*[0-9]+[.]"],
                "parent_chunk_size": 2000,
                "chunk_size": 500,
                "chunk_overlap": 50,
            },
            display={"strategy": "clause_aware", "profile_id": "p1"},
        )
        strategy, name, config = _use_case()._build_strategy(
            _req(chunking_config=cfg)
        )
        assert name == "clause_aware"
        assert strategy.get_strategy_name() == "clause_aware"
        assert config["profile_id"] == "p1"
