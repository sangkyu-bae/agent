"""knowledge_base.revision_mode 매핑 — document-revision Design §3.3 V096 / FR-15."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.infrastructure.knowledge_base.repository import KnowledgeBaseRepository
from src.infrastructure.persistence.models.knowledge_base import KnowledgeBaseModel


def test_entity_default_is_suggest() -> None:
    kb = KnowledgeBase(
        name="kb", owner_id=1, scope=CollectionScope.PERSONAL, collection_name="c"
    )
    assert kb.revision_mode == "suggest"


def test_model_column_default_is_suggest() -> None:
    col = KnowledgeBaseModel.__table__.columns["revision_mode"]
    assert col.default.arg == "suggest"
    assert col.nullable is False


def test_to_domain_maps_revision_mode() -> None:
    repo = KnowledgeBaseRepository(AsyncMock(), MagicMock())
    model = KnowledgeBaseModel(
        id="kb-1",
        name="kb",
        description=None,
        owner_id=1,
        scope="PERSONAL",
        department_id=None,
        collection_name="c",
        status="active",
        use_clause_chunking=0,
        chunking_profile_id=None,
        chunk_size=None,
        chunk_overlap=None,
        use_custom_chunking=0,
        custom_chunking_config=None,
        revision_mode="suggest",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    assert repo._to_domain(model).revision_mode == "suggest"
