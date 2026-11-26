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


class TestDatedSnapshotFallback:
    """공급사 응답은 날짜 붙은 스냅샷명(gpt-5.1-2025-11-13)을 돌려준다. 등록명은
    gpt-5.1 이라 정확 일치만 보면 매핑이 안 돼 비용이 0 으로 남았다
    (stock-analysis-agents module-10 실측)."""

    @staticmethod
    def _repo(known: dict[str, str]) -> MagicMock:
        repo = MagicMock()

        async def find(provider: str, name: str, request_id: str):
            return _make_model(known[name]) if name in known else None

        repo.find_by_provider_and_name = AsyncMock(side_effect=find)
        return repo

    @pytest.mark.asyncio
    async def test_dash_date_suffix_falls_back_to_base_name(self) -> None:
        logger = MagicMock()
        resolver = ModelNameResolver(self._repo({"gpt-5.1": "m-51"}), logger)

        assert await resolver.resolve("openai", "gpt-5.1-2025-11-13") == "m-51"
        logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_compact_date_suffix_falls_back_to_base_name(self) -> None:
        resolver = ModelNameResolver(
            self._repo({"claude-3-5-sonnet": "m-c"}), MagicMock()
        )

        assert (
            await resolver.resolve("anthropic", "claude-3-5-sonnet-20241022") == "m-c"
        )

    @pytest.mark.asyncio
    async def test_exact_name_wins_over_base(self) -> None:
        resolver = ModelNameResolver(
            self._repo({"gpt-5.1": "m-base", "gpt-5.1-2025-11-13": "m-pinned"}),
            MagicMock(),
        )

        assert await resolver.resolve("openai", "gpt-5.1-2025-11-13") == "m-pinned"

    @pytest.mark.asyncio
    async def test_both_missing_returns_none_and_warns_once(self) -> None:
        logger = MagicMock()
        resolver = ModelNameResolver(self._repo({}), logger)

        assert await resolver.resolve("openai", "ghost-2025-11-13") is None
        logger.warning.assert_called_once()
