"""builtin-middleware D6: MiddlewareProvider — 조회·병합·폴백 해석·플랜."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.middleware.middleware_provider import MiddlewareProvider
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    MiddlewareCatalogEntry,
    MiddlewareType,
)


def _entry(
    mw_type: MiddlewareType,
    *,
    is_builtin: bool = False,
    is_enforced: bool = False,
    is_active: bool = True,
    sort_order: int = 0,
    config: dict | None = None,
) -> MiddlewareCatalogEntry:
    return MiddlewareCatalogEntry(
        id=f"id-{mw_type.value}",
        middleware_type=mw_type,
        name=mw_type.value,
        description="",
        is_builtin=is_builtin,
        is_enforced=is_enforced,
        default_config=config or {},
        is_active=is_active,
        sort_order=sort_order,
    )


def _provider(catalog: list, snapshot: list, active_models: list | None = None):
    catalog_repo = AsyncMock()
    catalog_repo.list_all.return_value = catalog
    agent_mw_repo = AsyncMock()
    agent_mw_repo.list_by_agent.return_value = snapshot
    llm_model_repo = AsyncMock()
    llm_model_repo.list_active.return_value = active_models or []
    llm_factory = MagicMock()
    llm_factory.create.return_value = MagicMock(name="chat_model")
    provider = MiddlewareProvider(
        catalog_repo=catalog_repo,
        agent_middleware_repo=agent_mw_repo,
        llm_model_repo=llm_model_repo,
        llm_factory=llm_factory,
        logger=MagicMock(),
    )
    return provider, agent_mw_repo, llm_factory


@pytest.mark.asyncio
async def test_스냅샷과_enforced_병합_플랜():
    catalog = [
        _entry(MiddlewareType.MODEL_RETRY, is_builtin=True, sort_order=10),
        _entry(MiddlewareType.MODEL_CALL_LIMIT, is_enforced=True, sort_order=40),
    ]
    snapshot = [
        AgentMiddlewareRecord(agent_id="a-1", middleware_type="model_retry"),
    ]
    provider, _, _ = _provider(catalog, snapshot)
    plan = await provider.prepare("a-1", "req-1")
    assert [a.middleware_type for a in plan.applied] == [
        MiddlewareType.MODEL_RETRY,
        MiddlewareType.MODEL_CALL_LIMIT,
    ]


@pytest.mark.asyncio
async def test_agent_id_None이면_스냅샷_없이_builtin과_enforced():
    """General Chat 경로: 빌트인 ∪ enforced 전부 적용."""
    catalog = [
        _entry(MiddlewareType.MODEL_RETRY, is_builtin=True, sort_order=10),
        _entry(MiddlewareType.TOOL_RETRY, sort_order=20),
        _entry(MiddlewareType.MODEL_CALL_LIMIT, is_enforced=True, sort_order=40),
    ]
    provider, agent_mw_repo, _ = _provider(catalog, [])
    plan = await provider.prepare(None, "req-1")
    agent_mw_repo.list_by_agent.assert_not_awaited()
    assert [a.middleware_type for a in plan.applied] == [
        MiddlewareType.MODEL_RETRY,
        MiddlewareType.MODEL_CALL_LIMIT,
    ]


@pytest.mark.asyncio
async def test_플랜은_호출마다_새_인스턴스_목록():
    catalog = [_entry(MiddlewareType.MODEL_RETRY, is_builtin=True)]
    provider, _, _ = _provider(catalog, [])
    plan = await provider.prepare(None, "req-1")
    first = plan.instantiate()
    second = plan.instantiate()
    assert len(first) == 1
    assert first[0] is not second[0]


@pytest.mark.asyncio
async def test_폴백_모델은_등록_active_모델만_해석():
    reg = MagicMock()
    reg.model_name = "gpt-4o-mini"
    catalog = [
        _entry(
            MiddlewareType.MODEL_FALLBACK,
            is_builtin=True,
            config={"fallback_models": ["gpt-4o-mini", "미등록모델"]},
        )
    ]
    provider, _, llm_factory = _provider(catalog, [], active_models=[reg])
    plan = await provider.prepare(None, "req-1")
    instances = plan.instantiate()
    assert len(instances) == 1  # 해석 성공분 1개로 폴백 구성
    llm_factory.create.assert_called_once()


@pytest.mark.asyncio
async def test_폴백_전부_미해석이면_격하되고_실행_계속():
    catalog = [
        _entry(
            MiddlewareType.MODEL_FALLBACK,
            is_builtin=True,
            config={"fallback_models": ["미등록모델"]},
        ),
        _entry(MiddlewareType.MODEL_RETRY, is_builtin=True),
    ]
    provider, _, _ = _provider(catalog, [], active_models=[])
    plan = await provider.prepare(None, "req-1")
    instances = plan.instantiate()
    assert len(instances) == 1
