"""ModelNameResolver 매핑 + 캐시 + warning log 검증."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.model_name_resolver import ModelNameResolver
from src.domain.llm_model.entity import LlmModel


def _make_model(model_id: str = "m-1") -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


class TestResolve:
    @pytest.mark.asyncio
    async def test_known_model_returns_id(self) -> None:
        repo = MagicMock()
        repo.find_by_provider_and_name = AsyncMock(return_value=_make_model("m-1"))
        logger = MagicMock()
        resolver = ModelNameResolver(repo, logger)

        result = await resolver.resolve("openai", "gpt-4o")

        assert result == "m-1"
        logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_model_returns_none_and_warns(self) -> None:
        repo = MagicMock()
        repo.find_by_provider_and_name = AsyncMock(return_value=None)
        logger = MagicMock()
        resolver = ModelNameResolver(repo, logger)

        result = await resolver.resolve("openai", "ghost-model")

        assert result is None
        logger.warning.assert_called_once()
        kwargs = logger.warning.call_args.kwargs
        assert kwargs["provider"] == "openai"
        assert kwargs["model_name"] == "ghost-model"

    @pytest.mark.asyncio
    async def test_cache_avoids_duplicate_db_calls(self) -> None:
        repo = MagicMock()
        repo.find_by_provider_and_name = AsyncMock(return_value=_make_model())
        resolver = ModelNameResolver(repo, MagicMock())

        await resolver.resolve("openai", "gpt-4o")
        await resolver.resolve("openai", "gpt-4o")

        assert repo.find_by_provider_and_name.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_misses_are_also_cached(self) -> None:
        repo = MagicMock()
        repo.find_by_provider_and_name = AsyncMock(return_value=None)
        resolver = ModelNameResolver(repo, MagicMock())

        await resolver.resolve("openai", "ghost")
        await resolver.resolve("openai", "ghost")

        # 반복되는 unmapped 모델로 DB 폭증 방지
        assert repo.find_by_provider_and_name.await_count == 1
