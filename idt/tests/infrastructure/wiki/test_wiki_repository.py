"""Infrastructure 테스트: WikiArticleRepository (Mock Session/Embedding/VectorStore).

MySQL(SoT) CRUD + Qdrant 벡터 색인/검색의 합성 동작을 모킹으로 검증한다.
search_similar는 벡터 검색 결과를 MySQL로 하이드레이션 후 is_searchable로 필터한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.infrastructure.wiki.models import WikiArticleModel
from src.infrastructure.wiki.wiki_repository import WikiArticleRepository

NOW = datetime(2026, 6, 28)


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def mock_embedding():
    emb = MagicMock()
    emb.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return emb


@pytest.fixture
def mock_vector_store():
    vs = MagicMock()
    vs.add_documents = AsyncMock(return_value=[DocumentId("w1")])
    vs.delete_by_ids = AsyncMock(return_value=1)
    vs.search_by_vector = AsyncMock(return_value=[])
    return vs


def _repo(session, logger, embedding, vector_store):
    return WikiArticleRepository(
        session=session, logger=logger, embedding=embedding,
        vector_store=vector_store, collection_name="wiki_knowledge",
    )


def _entity(id="w1", status=WikiStatus.DRAFT, valid_until=None) -> WikiArticle:
    return WikiArticle(
        id=id, agent_id="agent_1", title=f"제목-{id}", content=f"본문-{id}",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=status, confidence=0.7, valid_until=valid_until,
        created_at=NOW, updated_at=NOW,
    )


def _model(id="w1", status="approved", valid_until=None) -> MagicMock:
    m = MagicMock(spec=WikiArticleModel)
    m.id = id
    m.agent_id = "agent_1"
    m.title = f"제목-{id}"
    m.content = f"본문-{id}"
    m.source_type = "distilled"
    m.source_refs = ["doc:1"]
    m.status = status
    m.confidence = 0.7
    m.valid_until = valid_until
    m.version = 1
    m.editor_id = None
    m.reviewer_id = None
    m.created_at = NOW
    m.updated_at = NOW
    return m


def _doc(id) -> Document:
    return Document(
        id=DocumentId(id), content=f"본문-{id}", vector=[0.1, 0.2, 0.3],
        metadata={"agent_id": "agent_1"}, score=0.9,
    )


class TestSave:

    @pytest.mark.asyncio
    async def test_save_persists_and_indexes(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_save", new_callable=AsyncMock) as base:
            base.return_value = _model(status="draft")
            result = await repo.save(_entity(), "r")
        assert result.id == "w1"
        base.assert_awaited_once()
        mock_embedding.embed_text.assert_awaited_once()
        mock_vector_store.add_documents.assert_awaited_once()


class TestFind:

    @pytest.mark.asyncio
    async def test_find_by_id_maps_entity(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as base:
            base.return_value = _model(status="approved")
            result = await repo.find_by_id("w1", "r")
        assert result is not None
        assert result.status == WikiStatus.APPROVED
        assert result.source_type == WikiSourceType.DISTILLED
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_find_by_id_none(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as base:
            base.return_value = None
            assert await repo.find_by_id("x", "r") is None

    @pytest.mark.asyncio
    async def test_find_by_agent_with_status_filter(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_find_by_conditions", new_callable=AsyncMock) as base:
            base.return_value = [_model(status="approved")]
            result = await repo.find_by_agent("agent_1", "r", status=WikiStatus.APPROVED)
            conds = base.await_args.args[0]
        fields = {c.field for c in conds}
        assert fields == {"agent_id", "status"}
        assert len(result) == 1


class TestUpdateDelete:

    @pytest.mark.asyncio
    async def test_update_loads_then_mutates_and_reindexes(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as base:
            base.return_value = _model(status="draft")
            await repo.update(_entity(status=WikiStatus.APPROVED), "r")
        base.assert_awaited_once()  # load-then-mutate (no transient add)
        mock_session.flush.assert_awaited()
        mock_vector_store.add_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_missing_raises(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_find_by_id", new_callable=AsyncMock) as base:
            base.return_value = None
            with pytest.raises(ValueError):
                await repo.update(_entity(), "r")

    @pytest.mark.asyncio
    async def test_delete_removes_vector_and_row(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        with patch.object(repo, "_base_delete", new_callable=AsyncMock) as base:
            base.return_value = True
            result = await repo.delete("w1", "r")
        assert result is True
        mock_vector_store.delete_by_ids.assert_awaited_once()


class TestSearchSimilar:

    @pytest.mark.asyncio
    async def test_returns_only_searchable_in_vector_order(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        # 벡터 결과: w2(approved), w1(draft), w3(approved-expired)
        mock_vector_store.search_by_vector = AsyncMock(
            return_value=[_doc("w2"), _doc("w1"), _doc("w3")]
        )
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        models = {
            "w1": _model("w1", status="draft"),
            "w2": _model("w2", status="approved"),
            "w3": _model("w3", status="approved", valid_until=datetime(2026, 6, 1)),
        }
        with patch.object(repo, "_base_find_by_conditions", new_callable=AsyncMock) as base:
            base.return_value = list(models.values())
            result = await repo.search_similar("agent_1", "쿼리", top_k=5, now=NOW, request_id="r")
        ids = [a.id for a in result]
        assert ids == ["w2"]  # draft·expired 제외, 벡터 순서 유지

    @pytest.mark.asyncio
    async def test_empty_vector_returns_empty(self, mock_session, mock_logger, mock_embedding, mock_vector_store):
        repo = _repo(mock_session, mock_logger, mock_embedding, mock_vector_store)
        result = await repo.search_similar("agent_1", "q", top_k=5, now=NOW, request_id="r")
        assert result == []
