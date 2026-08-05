"""CreateAgentUseCase 빌트인 미들웨어 스냅샷 주입 — builtin-middleware D5.

빌트인(middleware_catalog.is_builtin AND is_active)은 생성 시
AgentDefinition.middleware_types 스냅샷에 실리고,
exclude_builtin_middleware_types(폼 전용)로만 제외된다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import CreateAgentRequest
from src.domain.llm_model.entity import LlmModel
from src.domain.middleware.entities import MiddlewareCatalogEntry, MiddlewareType

PROMPT = "테스트 지침"


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _builtin_mw(mw_type: MiddlewareType, sort_order: int = 0):
    return MiddlewareCatalogEntry(
        id=f"mc-{mw_type.value}", middleware_type=mw_type,
        name=mw_type.value, description="", is_builtin=True,
        sort_order=sort_order,
    )


def _make_use_case(builtin_middlewares=None, with_middleware_repo=True):
    repository = MagicMock()
    repository.save = AsyncMock(side_effect=lambda agent, rid: agent)
    llm_model_repository = MagicMock()
    model = _llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=model)
    llm_model_repository.find_default = AsyncMock(return_value=model)
    perm_repo = MagicMock()
    perm_repo.find_by_collection_name = AsyncMock(return_value=None)

    middleware_catalog_repo = None
    if with_middleware_repo:
        middleware_catalog_repo = MagicMock()
        middleware_catalog_repo.list_builtin = AsyncMock(
            return_value=builtin_middlewares or []
        )

    use_case = CreateAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=MagicMock(),
        middleware_catalog_repo=middleware_catalog_repo,
    )
    return use_case, repository


def _request(**kw) -> CreateAgentRequest:
    defaults = dict(
        user_request="요청", name="테스트", user_id="user-1",
        system_prompt=PROMPT,
    )
    defaults.update(kw)
    return CreateAgentRequest(**defaults)


def _saved_agent(repository):
    return repository.save.call_args.args[0]


class TestMiddlewareSnapshot:
    @pytest.mark.asyncio
    async def test_빌트인_미들웨어가_스냅샷으로_저장(self):
        use_case, repository = _make_use_case(
            [
                _builtin_mw(MiddlewareType.MODEL_RETRY, 10),
                _builtin_mw(MiddlewareType.TOOL_RETRY, 20),
            ]
        )
        await use_case.execute(_request(), "req")
        agent = _saved_agent(repository)
        assert agent.middleware_types == ["model_retry", "tool_retry"]

    @pytest.mark.asyncio
    async def test_exclude로_명시_해제분만_제외(self):
        use_case, repository = _make_use_case(
            [
                _builtin_mw(MiddlewareType.MODEL_RETRY, 10),
                _builtin_mw(MiddlewareType.TOOL_RETRY, 20),
            ]
        )
        await use_case.execute(
            _request(exclude_builtin_middleware_types=["tool_retry"]), "req"
        )
        agent = _saved_agent(repository)
        assert agent.middleware_types == ["model_retry"]

    @pytest.mark.asyncio
    async def test_repo_미주입이면_스냅샷_생략_무회귀(self):
        use_case, repository = _make_use_case(with_middleware_repo=False)
        await use_case.execute(_request(), "req")
        agent = _saved_agent(repository)
        assert agent.middleware_types == []

    @pytest.mark.asyncio
    async def test_미지_exclude_타입은_무해(self):
        use_case, repository = _make_use_case(
            [_builtin_mw(MiddlewareType.MODEL_RETRY, 10)]
        )
        await use_case.execute(
            _request(exclude_builtin_middleware_types=["없는타입"]), "req"
        )
        agent = _saved_agent(repository)
        assert agent.middleware_types == ["model_retry"]

    @pytest.mark.asyncio
    async def test_카탈로그_sort_order_순서_유지(self):
        use_case, repository = _make_use_case(
            [
                _builtin_mw(MiddlewareType.MODEL_CALL_LIMIT, 40),
                _builtin_mw(MiddlewareType.MODEL_RETRY, 10),
            ]
        )
        await use_case.execute(_request(), "req")
        agent = _saved_agent(repository)
        assert agent.middleware_types == ["model_retry", "model_call_limit"]
