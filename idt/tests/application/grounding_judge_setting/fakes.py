"""grounding_judge_setting 테스트 공용 더블."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.domain.grounding_judge_setting.models import GroundingJudgeSetting
from src.domain.llm_model.entity import LlmModel


def make_model(
    model_id: str = "m-1",
    *,
    name: str = "gpt-4o",
    active: bool = True,
    kind: str = "chat",
    default: bool = False,
) -> LlmModel:
    now = datetime(2026, 11, 20, 12, 0, 0)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name=name,
        display_name=name.upper(),
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=active,
        is_default=default,
        created_at=now,
        updated_at=now,
        model_kind=kind,
    )


class FakeSettingRepo:
    def __init__(self, setting: GroundingJudgeSetting | None = None) -> None:
        self.setting = setting or GroundingJudgeSetting()
        self.get_calls = 0
        self.fail = False

    async def get(self, request_id: str) -> GroundingJudgeSetting:
        self.get_calls += 1
        if self.fail:
            raise RuntimeError("db down")
        return self.setting

    async def update(
        self, setting: GroundingJudgeSetting, request_id: str
    ) -> GroundingJudgeSetting:
        self.setting = setting
        return setting


class FakeModelRepo:
    def __init__(self, *models: LlmModel) -> None:
        self.models = {m.id: m for m in models}

    async def find_by_id(self, model_id: str, request_id: str):
        return self.models.get(model_id)

    async def list_active(self, request_id: str):
        return [m for m in self.models.values() if m.is_active]

    async def find_default(self, request_id: str):
        return next((m for m in self.models.values() if m.is_default), None)


def session_factory():
    @asynccontextmanager
    async def _scope():
        yield MagicMock(name="session")

    return _scope


def fallback_provider(llm=None) -> AsyncMock:
    fb = AsyncMock()
    fb.get.return_value = llm or MagicMock(name="fallback-llm")
    return fb
