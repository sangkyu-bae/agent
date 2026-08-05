"""builtin-middleware D4: SetMiddlewareFlagsUseCase — 토글·config 검증."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.middleware.set_middleware_flags_use_case import (
    SetMiddlewareFlagsUseCase,
)
from src.domain.middleware.entities import MiddlewareCatalogEntry, MiddlewareType


def _entry(mw_type: MiddlewareType = MiddlewareType.MODEL_RETRY):
    return MiddlewareCatalogEntry(
        id="mc-1",
        middleware_type=mw_type,
        name="n",
        description="d",
        default_config={"max_retries": 3},
    )


def _uc(existing=None, active_models=None):
    repo = AsyncMock()
    repo.find_by_type.return_value = existing
    repo.update_flags.return_value = existing
    llm_model_repo = AsyncMock()
    models = []
    for name in active_models or []:
        m = MagicMock()
        m.model_name = name
        models.append(m)
    llm_model_repo.list_active.return_value = models
    uc = SetMiddlewareFlagsUseCase(
        repository=repo, llm_model_repository=llm_model_repo, logger=MagicMock()
    )
    return uc, repo


@pytest.mark.asyncio
async def test_토글_갱신():
    uc, repo = _uc(existing=_entry())
    result = await uc.execute(
        "model_retry", is_builtin=True, is_enforced=None,
        default_config=None, request_id="req-1",
    )
    repo.update_flags.assert_awaited_once()
    assert result is not None


@pytest.mark.asyncio
async def test_미존재_타입은_LookupError():
    uc, _ = _uc(existing=None)
    with pytest.raises(LookupError):
        await uc.execute(
            "없는것", is_builtin=True, is_enforced=None,
            default_config=None, request_id="req-1",
        )


@pytest.mark.asyncio
async def test_retry_config_범위_위반은_ValueError():
    uc, _ = _uc(existing=_entry())
    with pytest.raises(ValueError):
        await uc.execute(
            "model_retry", is_builtin=None, is_enforced=None,
            default_config={"max_retries": 99}, request_id="req-1",
        )


@pytest.mark.asyncio
async def test_call_limit_exit_behavior_검증():
    uc, _ = _uc(existing=_entry(MiddlewareType.MODEL_CALL_LIMIT))
    with pytest.raises(ValueError):
        await uc.execute(
            "model_call_limit", is_builtin=None, is_enforced=None,
            default_config={"run_limit": 5, "exit_behavior": "폭발"},
            request_id="req-1",
        )


@pytest.mark.asyncio
async def test_fallback_미등록_모델은_ValueError():
    uc, _ = _uc(
        existing=_entry(MiddlewareType.MODEL_FALLBACK),
        active_models=["gpt-4o-mini"],
    )
    with pytest.raises(ValueError):
        await uc.execute(
            "model_fallback", is_builtin=None, is_enforced=None,
            default_config={"fallback_models": ["미등록모델"]},
            request_id="req-1",
        )


@pytest.mark.asyncio
async def test_fallback_등록_모델은_통과():
    uc, repo = _uc(
        existing=_entry(MiddlewareType.MODEL_FALLBACK),
        active_models=["gpt-4o-mini"],
    )
    await uc.execute(
        "model_fallback", is_builtin=None, is_enforced=None,
        default_config={"fallback_models": ["gpt-4o-mini"]},
        request_id="req-1",
    )
    repo.update_flags.assert_awaited_once()


@pytest.mark.asyncio
async def test_미지_config_키는_ValueError():
    uc, _ = _uc(existing=_entry())
    with pytest.raises(ValueError):
        await uc.execute(
            "model_retry", is_builtin=None, is_enforced=None,
            default_config={"이상한키": 1}, request_id="req-1",
        )
