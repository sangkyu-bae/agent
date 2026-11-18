"""관리자 설정·단계·상태 유스케이스 (Design §4.1·§4.2, Plan FR-03·FR-23)."""
import dataclasses
from unittest.mock import MagicMock

import pytest
from src.application.graph_rag.admin.health_use_case import GraphHealthUseCase
from src.application.graph_rag.admin.settings_use_case import (
    GraphRagSettingsUpdate,
    GraphRagSettingsUseCase,
)
from src.application.graph_rag.admin.stage_use_case import ChangeStageUseCase
from src.domain.graph_rag.exceptions import GraphStageEvalRequiredError
from src.domain.graph_rag.value_objects import GraphRagSettings, RolloutStage

from tests.application.graph_rag.fakes import (
    FakeReader,
    FakeSettingsRepo,
    FakeStageRepo,
    FakeStore,
    FakeVerifier,
)


def _update(**over) -> GraphRagSettingsUpdate:
    base = GraphRagSettings.defaults()
    fields = {
        f.name: getattr(base, f.name)
        for f in dataclasses.fields(GraphRagSettingsUpdate)
    }
    fields.update(over)
    return GraphRagSettingsUpdate(**fields)


# ── settings ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_keeps_stage_and_invalidates_cache():
    repo = FakeSettingsRepo(dataclasses.replace(
        GraphRagSettings.defaults(), rollout_stage=RolloutStage.ADMIN_ONLY
    ))
    reader = FakeReader()
    uc = GraphRagSettingsUseCase(repo, reader, MagicMock())
    saved = await uc.update(_update(jev_enabled=True, max_hops=3), "r")
    assert saved.rollout_stage is RolloutStage.ADMIN_ONLY  # PUT 은 단계를 바꾸지 않는다
    assert saved.jev_enabled is True and saved.max_hops == 3
    assert reader.invalidations == 1


@pytest.mark.asyncio
async def test_update_invalid_values_raise_value_error_and_do_not_save():
    repo = FakeSettingsRepo()
    uc = GraphRagSettingsUseCase(repo, FakeReader(), MagicMock())
    with pytest.raises(ValueError):
        await uc.update(_update(new_threshold=0.9, link_threshold=0.8), "r")
    assert repo.updates == []


# ── stage ───────────────────────────────────────────────────────────────────

def _stage_uc(current=RolloutStage.OFF, evidence_ok=False):
    repo = FakeSettingsRepo(dataclasses.replace(
        GraphRagSettings.defaults(), rollout_stage=current
    ))
    changes, reader, verifier = FakeStageRepo(), FakeReader(), FakeVerifier(evidence_ok)
    uc = ChangeStageUseCase(repo, changes, verifier, reader, MagicMock())
    return uc, repo, changes, reader, verifier


@pytest.mark.asyncio
async def test_change_to_admin_only_records_history():
    uc, repo, changes, reader, _ = _stage_uc()
    out = await uc.change(
        RolloutStage.ADMIN_ONLY, actor_id="99", request_id="r",
    )
    assert out.rollout_stage is RolloutStage.ADMIN_ONLY
    assert repo.settings.rollout_stage is RolloutStage.ADMIN_ONLY
    assert len(changes.added) == 1
    c = changes.added[0]
    assert (c.from_stage, c.to_stage, c.changed_by) == (
        RolloutStage.OFF, RolloutStage.ADMIN_ONLY, "99"
    )
    assert reader.invalidations == 1


@pytest.mark.asyncio
async def test_same_stage_is_noop_without_history():
    uc, repo, changes, reader, _ = _stage_uc(RolloutStage.ADMIN_ONLY)
    await uc.change(RolloutStage.ADMIN_ONLY, actor_id="99", request_id="r")
    assert changes.added == [] and repo.updates == []


@pytest.mark.asyncio
async def test_general_without_evidence_or_reason_blocked():
    uc, repo, changes, _, verifier = _stage_uc(RolloutStage.ADMIN_ONLY)
    with pytest.raises(GraphStageEvalRequiredError):
        await uc.change(
            RolloutStage.GENERAL, actor_id="99", request_id="r",
            eval_baseline_run_id="b", eval_graph_run_id="g",
        )
    assert verifier.calls == [("b", "g")]
    assert changes.added == [] and repo.updates == []


@pytest.mark.asyncio
async def test_general_with_verified_evidence_passes():
    uc, repo, changes, _, _ = _stage_uc(RolloutStage.ADMIN_ONLY, evidence_ok=True)
    await uc.change(
        RolloutStage.GENERAL, actor_id="99", request_id="r",
        eval_baseline_run_id="b", eval_graph_run_id="g",
    )
    assert repo.settings.rollout_stage is RolloutStage.GENERAL
    assert changes.added[0].eval_graph_run_id == "g"


@pytest.mark.asyncio
async def test_general_forced_with_reason_records_reason():
    uc, _, changes, _, verifier = _stage_uc(RolloutStage.ADMIN_ONLY)
    await uc.change(
        RolloutStage.GENERAL, actor_id="99", request_id="r",
        force_reason="시연 일정상 먼저 공개하고 다음 주 평가",
    )
    assert verifier.calls == []  # 근거 id 없으면 검증 호출도 없다
    assert changes.added[0].force_reason.startswith("시연")


# ── health ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_backend_off():
    h = await GraphHealthUseCase(
        store=None, backend="off", uri=None, node_limit=200000, rel_limit=400000
    ).execute()
    assert (h.backend, h.connected, h.external) == ("off", False, False)


@pytest.mark.asyncio
async def test_health_connected_aura_marks_external():
    h = await GraphHealthUseCase(
        store=FakeStore(counts=(12, 34)), backend="neo4j",
        uri="neo4j+s://abcd1234.databases.neo4j.io",
        node_limit=200000, rel_limit=400000,
    ).execute()
    assert h.connected and h.external
    assert (h.node_count, h.relationship_count) == (12, 34)
    assert (h.node_limit, h.relationship_limit) == (200000, 400000)


@pytest.mark.asyncio
async def test_health_down_reports_error_not_raise():
    h = await GraphHealthUseCase(
        store=FakeStore(down=True), backend="neo4j", uri="bolt://localhost:7687",
        node_limit=200000, rel_limit=400000,
    ).execute()
    assert h.connected is False and h.external is False
    assert h.error
