"""MultimodalSettingsUseCase — Design §4.2 GET/PUT/test, FR-13/14."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.multimodal.registries import VisionAdapterRegistry
from src.application.multimodal.settings_use_case import (
    MultimodalSettingsUseCase,
    SettingsUpdate,
    VisionModelNotCapableError,
    VisionModelNotFoundError,
)
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.errors import MultimodalNotConfiguredError
from src.domain.multimodal.interfaces import DescribeOutcome
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import ElementType, MultimodalSettings


def _settings(**over) -> MultimodalSettings:
    base = dict(
        id="s",
        enabled=False,
        vision_model_id=None,
        max_images_per_doc=50,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=4,
        timeout_sec=60,
        output_language="ko",
        detail_level="detailed",
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    base.update(over)
    return MultimodalSettings(**base)


def _llm(**over) -> LlmModel:
    now = datetime.now(UTC)
    base = dict(
        id="m1",
        provider="fake",
        model_name="fake-v",
        display_name="Fake",
        description=None,
        api_key_env="FAKE_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        supports_vision=True,
    )
    base.update(over)
    return LlmModel(**base)


def _update(**over) -> SettingsUpdate:
    base = dict(
        enabled=True,
        vision_model_id="m1",
        max_images_per_doc=20,
        min_image_px=80,
        min_area_ratio=0.01,
        concurrency=3,
        timeout_sec=30,
        output_language="en",
        detail_level="brief",
    )
    base.update(over)
    return SettingsUpdate(**base)


class FakeAdapter:
    provider = "fake"
    behavior = "ok"

    def __init__(self, llm_factory, llm_model, logger, callbacks=None):
        pass

    async def describe(self, image, element_type, options):
        if FakeAdapter.behavior == "raise":
            raise RuntimeError("provider down")
        return DescribeOutcome(
            draft=DescriptionDraft(
                detected_type="chart",
                description="막대 차트",
                keywords=["차트"],
                markdown_table=None,
                chart=None,
                page_text=None,
            ),
            degraded_output_mode=False,
            output_mode="strict",
            usage={"total_tokens": 5},
        )


def _uc(settings=None, llm=_llm(), monkeypatch=None):
    repo = MagicMock()
    current = settings or _settings()
    repo.get = AsyncMock(return_value=current)
    repo.update = AsyncMock(side_effect=lambda s, rid: s)
    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(return_value=llm)
    vreg = VisionAdapterRegistry()
    vreg.register(FakeAdapter)
    if monkeypatch is not None:
        monkeypatch.setenv("FAKE_KEY", "x")
    uc = MultimodalSettingsUseCase(
        settings_repo=repo,
        llm_model_repo=llm_repo,
        adapters=vreg,
        llm_factory=MagicMock(),
        logger=MagicMock(),
    )
    return uc, repo, llm_repo


@pytest.mark.asyncio
async def test_get_resolves_soft_reference_and_warns_when_inactive():
    uc, _, _ = _uc(settings=_settings(vision_model_id="m1"), llm=_llm(is_active=False))
    view = await uc.get("req")
    assert view.settings.vision_model_id == "m1"
    assert view.vision_model is not None and view.vision_model.is_active is False
    assert any("inactive" in w for w in view.warnings)


@pytest.mark.asyncio
async def test_get_with_no_model_has_no_warning():
    uc, _, _ = _uc()
    view = await uc.get("req")
    assert view.vision_model is None and view.warnings == ()


@pytest.mark.asyncio
async def test_get_warns_when_model_deleted():
    uc, _, _ = _uc(settings=_settings(vision_model_id="gone"), llm=None)
    view = await uc.get("req")
    assert view.vision_model is None and any("not found" in w for w in view.warnings)


@pytest.mark.asyncio
async def test_update_replaces_all_fields_and_validates_model():
    uc, repo, _ = _uc()
    view = await uc.update(_update(), "req")
    saved: MultimodalSettings = repo.update.call_args.args[0]
    assert saved.id == "s" and saved.enabled is True and saved.vision_model_id == "m1"
    assert (saved.max_images_per_doc, saved.concurrency, saved.output_language) == (
        20,
        3,
        "en",
    )
    assert view.vision_model is not None and view.warnings == ()


@pytest.mark.asyncio
async def test_update_allows_clearing_model_when_disabled():
    uc, repo, llm_repo = _uc()
    await uc.update(_update(enabled=False, vision_model_id=None), "req")
    llm_repo.find_by_id.assert_not_called()
    assert repo.update.call_args.args[0].vision_model_id is None


@pytest.mark.asyncio
async def test_update_rejects_unknown_model():
    uc, _, _ = _uc(llm=None)
    with pytest.raises(VisionModelNotFoundError):
        await uc.update(_update(), "req")


@pytest.mark.asyncio
@pytest.mark.parametrize("llm", [_llm(is_active=False), _llm(supports_vision=False)])
async def test_update_rejects_inactive_or_non_vision_model(llm):
    uc, _, _ = _uc(llm=llm)
    with pytest.raises(VisionModelNotCapableError):
        await uc.update(_update(), "req")


@pytest.mark.asyncio
async def test_update_out_of_range_raises_value_error():
    uc, _, _ = _uc()
    with pytest.raises(ValueError):
        await uc.update(_update(concurrency=0), "req")


@pytest.mark.asyncio
async def test_test_connection_uses_selected_model_and_sample_image(monkeypatch):
    FakeAdapter.behavior = "ok"
    uc, _, _ = _uc(settings=_settings(vision_model_id="m1"), monkeypatch=monkeypatch)
    out = await uc.test_connection(None, "image/png", "req")
    assert out.ok is True and out.provider == "fake" and out.model_name == "fake-v"
    assert out.draft is not None and out.draft.detected_type == "chart"
    assert out.elapsed_ms >= 0 and out.degraded_output_mode is False


@pytest.mark.asyncio
async def test_test_connection_with_uploaded_image(monkeypatch):
    FakeAdapter.behavior = "ok"
    uc, _, _ = _uc(settings=_settings(vision_model_id="m1"), monkeypatch=monkeypatch)
    out = await uc.test_connection(b"\x89PNGxxxx", "image/png", "req")
    assert out.ok is True


@pytest.mark.asyncio
async def test_test_connection_not_configured_raises(monkeypatch):
    uc, _, _ = _uc(monkeypatch=monkeypatch)  # vision_model_id None
    with pytest.raises(MultimodalNotConfiguredError):
        await uc.test_connection(None, "image/png", "req")


@pytest.mark.asyncio
async def test_test_connection_provider_failure_returns_ok_false(monkeypatch):
    FakeAdapter.behavior = "raise"
    try:
        uc, _, _ = _uc(
            settings=_settings(vision_model_id="m1"), monkeypatch=monkeypatch
        )
        out = await uc.test_connection(None, "image/png", "req")
        assert out.ok is False and "provider down" in (out.error or "")
    finally:
        FakeAdapter.behavior = "ok"


def test_sample_image_is_a_png():
    from src.application.multimodal.settings_use_case import sample_chart_png

    data = sample_chart_png()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 500


def test_element_type_used_for_test_is_chart():
    assert MultimodalSettingsUseCase.TEST_ELEMENT_TYPE is ElementType.CHART
