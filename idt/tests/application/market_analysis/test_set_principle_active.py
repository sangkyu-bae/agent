"""원칙 켜고 끄기 유스케이스 (DD9 — 활성화는 운영자가)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.application.market_analysis.principles import (
    InvalidPriorityError,
    PrincipleNotFoundError,
    SetPrincipleActiveUseCase,
)

from .fakes import FakePrincipleStore


def _uc():
    store = FakePrincipleStore()
    return SetPrincipleActiveUseCase(principles=store, logger=MagicMock()), store


async def test_activates_with_priority():
    uc, store = _uc()
    await uc.execute(
        principle_id=1, is_active=True, priority="high", updated_by="3", request_id="r"
    )
    assert store.toggles == [
        {"id": 1, "is_active": True, "priority": "high", "by": "3"}
    ]


async def test_unknown_principle_and_bad_priority():
    uc, store = _uc()
    with pytest.raises(PrincipleNotFoundError):
        await uc.execute(
            principle_id=99,
            is_active=False,
            priority=None,
            updated_by="3",
            request_id="r",
        )
    with pytest.raises(InvalidPriorityError):
        await uc.execute(
            principle_id=1,
            is_active=True,
            priority="urgent",
            updated_by="3",
            request_id="r",
        )
    assert store.toggles == []
