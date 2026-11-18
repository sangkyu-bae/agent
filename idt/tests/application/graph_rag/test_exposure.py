"""GraphExposure·capabilities (Plan FR-24, Design §4.2 capabilities)."""
import pytest
from src.application.graph_rag.hooks import GraphExposure, capabilities_for
from src.domain.extension_hooks import GRAPH_RAG_FEATURE
from src.domain.graph_rag.value_objects import RolloutStage

from tests.application.graph_rag.fakes import FakeReader


@pytest.mark.asyncio
@pytest.mark.parametrize("stage, is_admin, visible", [
    (RolloutStage.OFF, True, False),
    (RolloutStage.ADMIN_ONLY, True, True),
    (RolloutStage.ADMIN_ONLY, False, False),
    (RolloutStage.GENERAL, False, True),
])
async def test_exposure_follows_stage(stage, is_admin, visible):
    exposure = GraphExposure(FakeReader().with_stage(stage))
    assert await exposure.is_visible(GRAPH_RAG_FEATURE, is_admin) is visible


@pytest.mark.asyncio
async def test_exposure_other_feature_is_false():
    exposure = GraphExposure(FakeReader().with_stage(RolloutStage.GENERAL))
    assert await exposure.is_visible("something_else", True) is False


@pytest.mark.asyncio
async def test_capabilities_hide_stage_from_non_admin():
    reader = FakeReader().with_stage(RolloutStage.ADMIN_ONLY)
    assert await capabilities_for(reader, caller_is_admin=False) == {"visible": False}
    assert await capabilities_for(reader, caller_is_admin=True) == {
        "visible": True, "stage": "admin_only",
    }


@pytest.mark.asyncio
async def test_reader_failure_is_closed():
    reader = FakeReader(fail=True)
    assert await GraphExposure(reader).is_visible(GRAPH_RAG_FEATURE, True) is False
    assert await capabilities_for(reader, caller_is_admin=True) == {"visible": False}
