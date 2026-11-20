"""AdminConfiguredJudgeLlmProvider — Design D-15·D-16 (answer-citation §2.2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.application.grounding_judge_setting.provider import (
    AdminConfiguredJudgeLlmProvider,
)
from src.domain.grounding_judge_setting.models import GroundingJudgeSetting

from tests.application.grounding_judge_setting.fakes import (
    FakeModelRepo,
    FakeSettingRepo,
    fallback_provider,
    make_model,
    session_factory,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _provider(setting_repo, model_repo, *, fallback=None, factory=None, clock=None):
    if factory is None:
        factory = MagicMock()
        factory.create.side_effect = lambda model, temperature=0.0: (
            f"llm:{model.id}:{temperature}"
        )
    provider = AdminConfiguredJudgeLlmProvider(
        session_factory=session_factory(),
        setting_repo_factory=lambda s: setting_repo,
        model_repo_factory=lambda s: model_repo,
        llm_factory=factory,
        fallback=fallback or fallback_provider(),
        logger=MagicMock(),
        ttl_seconds=60,
        clock=clock or _Clock(),
    )
    return provider, factory


@pytest.mark.asyncio
async def test_uses_admin_model_when_set_and_active():
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    fb = fallback_provider()
    p, _ = _provider(repo, FakeModelRepo(make_model("m-1")), fallback=fb)
    assert await p.get(0.0) == "llm:m-1:0.0"
    fb.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "models",
    [
        (),  # 삭제됨
        (make_model("m-1", active=False),),  # 비활성
        (make_model("m-1", kind="image"),),  # 채팅 모델 아님
    ],
)
async def test_falls_back_when_admin_model_unusable(models):
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    fb = fallback_provider()
    p, _ = _provider(repo, FakeModelRepo(*models), fallback=fb)
    assert await p.get(0.0) is fb.get.return_value


@pytest.mark.asyncio
async def test_falls_back_when_setting_empty():
    fb = fallback_provider()
    p, _ = _provider(FakeSettingRepo(), FakeModelRepo(make_model("m-1")), fallback=fb)
    assert await p.get(0.0) is fb.get.return_value


@pytest.mark.asyncio
async def test_setting_read_failure_falls_back_and_is_not_cached():
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    repo.fail = True
    fb = fallback_provider()
    p, _ = _provider(repo, FakeModelRepo(make_model("m-1")), fallback=fb)
    assert await p.get(0.0) is fb.get.return_value
    repo.fail = False
    assert await p.get(0.0) == "llm:m-1:0.0"  # 다음 호출에서 재시도


@pytest.mark.asyncio
async def test_resolution_is_cached_within_ttl_and_refreshed_after():
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    clock = _Clock()
    p, _ = _provider(repo, FakeModelRepo(make_model("m-1")), clock=clock)
    await p.get(0.0)
    await p.get(0.0)
    assert repo.get_calls == 1
    clock.now = 61
    await p.get(0.0)
    assert repo.get_calls == 2


@pytest.mark.asyncio
async def test_invalidate_drops_cache_and_invalidates_fallback():
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    fb = fallback_provider()
    models = FakeModelRepo(make_model("m-1"), make_model("m-2"))
    p, _ = _provider(repo, models, fallback=fb)
    await p.get(0.0)
    repo.setting = GroundingJudgeSetting(judge_llm_model_id="m-2")
    await p.invalidate()
    assert await p.get(0.0) == "llm:m-2:0.0"
    fb.invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_instances_are_reused_per_model_and_temperature():
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    p, factory = _provider(repo, FakeModelRepo(make_model("m-1")))
    await p.get(0.0)
    await p.get(0.0)
    await p.get(0.3)
    assert factory.create.call_count == 2


@pytest.mark.asyncio
async def test_instance_creation_failure_falls_back():
    repo = FakeSettingRepo(GroundingJudgeSetting(judge_llm_model_id="m-1"))
    fb = fallback_provider()
    factory = MagicMock()
    factory.create.side_effect = RuntimeError("no api key")
    p, _ = _provider(
        repo, FakeModelRepo(make_model("m-1")), fallback=fb, factory=factory
    )
    assert await p.get(0.0) is fb.get.return_value
