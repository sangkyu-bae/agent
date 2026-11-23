"""GroundingJudgeSettingUseCase — Design §4.2 (answer-citation-verification)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.grounding_judge_setting.use_cases import (
    GroundingJudgeSettingUseCase,
)
from src.domain.grounding_judge_setting.exceptions import (
    JudgeModelKindInvalidError,
    JudgeModelNotFoundError,
)
from src.domain.grounding_judge_setting.models import GroundingJudgeSetting

from tests.application.grounding_judge_setting.fakes import (
    FakeModelRepo,
    FakeSettingRepo,
    make_model,
)


def _uc(setting=None, *models, env="gpt-4o", provider=None):
    repo = FakeSettingRepo(setting)
    uc = GroundingJudgeSettingUseCase(
        setting_repo=repo,
        model_repo=FakeModelRepo(*models),
        provider=provider or AsyncMock(),
        env_model_name=env,
        logger=MagicMock(),
    )
    return uc, repo


@pytest.mark.asyncio
async def test_get_reports_admin_source_when_set_model_is_usable():
    uc, _ = _uc(
        GroundingJudgeSetting("m-2"),
        make_model("m-1"),
        make_model("m-2", name="claude"),
    )
    setting, effective = await uc.get("r")
    assert setting.judge_llm_model_id == "m-2"
    assert (effective.model_id, effective.source) == ("m-2", "admin")


@pytest.mark.asyncio
async def test_get_reports_env_source_when_unset():
    uc, _ = _uc(
        None,
        make_model("m-1", name="gpt-4o"),
        make_model("m-9", default=True, name="x"),
    )
    _, effective = await uc.get("r")
    assert (effective.model_id, effective.source) == ("m-1", "env")


@pytest.mark.asyncio
async def test_get_reports_env_when_admin_model_was_deactivated():
    uc, _ = _uc(
        GroundingJudgeSetting("m-2"), make_model("m-1"), make_model("m-2", active=False)
    )
    _, effective = await uc.get("r")
    assert effective.source == "env"


@pytest.mark.asyncio
async def test_get_reports_default_when_env_name_not_registered():
    uc, _ = _uc(None, make_model("m-9", default=True, name="other"), env="gpt-4o")
    _, effective = await uc.get("r")
    assert (effective.model_id, effective.source) == ("m-9", "default")


@pytest.mark.asyncio
async def test_get_effective_none_when_nothing_resolves():
    uc, _ = _uc(None, env="gpt-4o")
    _, effective = await uc.get("r")
    assert effective is None


@pytest.mark.asyncio
async def test_update_saves_and_invalidates_provider():
    provider = AsyncMock()
    uc, repo = _uc(None, make_model("m-1"), provider=provider)
    _, effective = await uc.update("m-1", actor_id="7", request_id="r")
    assert repo.setting == GroundingJudgeSetting("m-1", updated_by="7")
    assert effective.source == "admin"
    provider.invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_to_none_clears_setting():
    uc, repo = _uc(GroundingJudgeSetting("m-1"), make_model("m-1"))
    await uc.update(None, actor_id="7", request_id="r")
    assert repo.setting.judge_llm_model_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("models", [(), (make_model("m-1", active=False),)])
async def test_update_rejects_missing_or_inactive_model(models):
    uc, repo = _uc(None, *models)
    with pytest.raises(JudgeModelNotFoundError):
        await uc.update("m-1", actor_id="7", request_id="r")
    assert repo.setting.judge_llm_model_id is None


@pytest.mark.asyncio
async def test_update_rejects_non_chat_model():
    uc, _ = _uc(None, make_model("m-1", kind="image"))
    with pytest.raises(JudgeModelKindInvalidError):
        await uc.update("m-1", actor_id="7", request_id="r")


@pytest.mark.asyncio
async def test_update_succeeds_even_if_invalidation_fails():
    provider = AsyncMock()
    provider.invalidate.side_effect = RuntimeError("cache down")
    uc, repo = _uc(None, make_model("m-1"), provider=provider)
    await uc.update("m-1", actor_id="7", request_id="r")
    assert repo.setting.judge_llm_model_id == "m-1"
