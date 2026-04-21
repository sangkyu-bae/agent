"""LLM-MODEL-REG-001 Application Layer 공용 fixture."""
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface


class InMemoryLlmModelRepository(LlmModelRepositoryInterface):
    """테스트용 in-memory 구현 (mock 대신 동작 검증 용이)."""

    def __init__(self) -> None:
        self._by_id: dict[str, LlmModel] = {}

    async def save(self, model: LlmModel, request_id: str) -> LlmModel:
        self._by_id[model.id] = model
        return model

    async def find_by_id(
        self, model_id: str, request_id: str
    ) -> Optional[LlmModel]:
        return self._by_id.get(model_id)

    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> Optional[LlmModel]:
        for m in self._by_id.values():
            if m.provider == provider and m.model_name == model_name:
                return m
        return None

    async def find_default(self, request_id: str) -> Optional[LlmModel]:
        for m in self._by_id.values():
            if m.is_default:
                return m
        return None

    async def list_active(self, request_id: str) -> list[LlmModel]:
        return [m for m in self._by_id.values() if m.is_active]

    async def list_all(self, request_id: str) -> list[LlmModel]:
        return list(self._by_id.values())

    async def update(self, model: LlmModel, request_id: str) -> LlmModel:
        self._by_id[model.id] = model
        return model

    async def unset_all_defaults(self, request_id: str) -> None:
        for m in self._by_id.values():
            m.is_default = False


@pytest.fixture
def repo() -> InMemoryLlmModelRepository:
    return InMemoryLlmModelRepository()


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def seeded_model(repo: InMemoryLlmModelRepository) -> LlmModel:
    """사전 등록된 기본 모델 1건."""
    now = datetime.now(timezone.utc)
    model = LlmModel(
        id="seed-1",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )
    repo._by_id[model.id] = model
    return model
