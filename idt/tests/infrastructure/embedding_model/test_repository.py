from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.domain.embedding_model.entity import EmbeddingModel
from src.infrastructure.embedding_model.models import EmbeddingModelTable
from src.infrastructure.persistence.models.base import Base


def _make_model(
    *,
    provider: str = "openai",
    model_name: str = "text-embedding-3-small",
    display_name: str = "OpenAI Embedding 3 Small",
    vector_dimension: int = 1536,
    is_active: bool = True,
) -> EmbeddingModel:
    now = datetime.now(timezone.utc)
    return EmbeddingModel(
        id=0,
        provider=provider,
        model_name=model_name,
        display_name=display_name,
        vector_dimension=vector_dimension,
        is_active=is_active,
        description=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def sync_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestEmbeddingModelTable:
    def test_create_row(self, sync_session: Session):
        now = datetime.now(timezone.utc)
        row = EmbeddingModelTable(
            provider="openai",
            model_name="text-embedding-3-small",
            display_name="OpenAI Embedding 3 Small",
            vector_dimension=1536,
            is_active=True,
            description="test",
            created_at=now,
            updated_at=now,
        )
        sync_session.add(row)
        sync_session.flush()
        assert row.id is not None
        assert row.model_name == "text-embedding-3-small"

    def test_unique_model_name(self, sync_session: Session):
        now = datetime.now(timezone.utc)
        row1 = EmbeddingModelTable(
            provider="openai",
            model_name="text-embedding-3-small",
            display_name="A",
            vector_dimension=1536,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        row2 = EmbeddingModelTable(
            provider="openai",
            model_name="text-embedding-3-small",
            display_name="B",
            vector_dimension=1536,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        sync_session.add(row1)
        sync_session.flush()
        sync_session.add(row2)
        with pytest.raises(Exception):
            sync_session.flush()
