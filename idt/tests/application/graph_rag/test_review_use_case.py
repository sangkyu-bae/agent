"""검토 큐 — 승인·거절(분리·재연결) (Design §4.2 review reject, Plan FR-11)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.application.graph_rag.admin.review_use_case import (
    GraphReviewAlreadyDoneError,
    GraphReviewNotFoundError,
    GraphReviewTargetInvalidError,
    ReviewUseCase,
)
from src.domain.graph_rag.extraction import EntityWrite
from src.domain.graph_rag.resolution import (
    DecidedBy,
    ResolutionBand,
    ResolutionDecision,
    ReviewStatus,
)

from tests.application.graph_rag.fakes import FakeDecisions, FakeStore


def _decision(did="d1", entity_id="e1", created_new=False, status=ReviewStatus.PENDING,
              candidates=({"label": "C1", "entity_id": "e1", "type": "상품"},
                          {"label": "C2", "entity_id": "e2", "type": "상품"})):
    return ResolutionDecision(
        id=did, job_id="j", document_id="doc", chunk_id="p1", mention_text="A 상품",
        mention_type="상품", candidates=tuple(candidates), probabilities=None,
        chosen_label="C1", entity_id=entity_id, created_new=created_new,
        decided_by=DecidedBy.LLM_REJUDGE, band=ResolutionBand.REJUDGE,
        probability=0.6, review_status=status,
    )


def _setup(decision):
    store, decisions = FakeStore(), FakeDecisions()
    store._ensure4()
    for eid in ("e1", "e2"):
        store.entities[eid] = EntityWrite(eid, "global", eid, eid, "상품", "")
    store.mentions.append((decision.entity_id, "p1", decision.id, "doc"))
    decisions.rows[decision.id] = decision
    return ReviewUseCase(decisions=decisions, store=store, logger=MagicMock()), store, decisions


@pytest.mark.asyncio
async def test_list_pending():
    uc, _, _ = _setup(_decision())
    items, total = await uc.list(ReviewStatus.PENDING, 20, 0, "r")
    assert total == 1 and items[0].id == "d1"


@pytest.mark.asyncio
async def test_approve_keeps_graph_and_marks_approved():
    uc, store, decisions = _setup(_decision())
    await uc.approve("d1", reviewer="99", note="맞음", request_id="r")
    assert decisions.rows["d1"].review_status is ReviewStatus.APPROVED
    assert store.mentions[0][0] == "e1"


@pytest.mark.asyncio
async def test_reject_linked_without_target_splits_into_new_entity():
    uc, store, decisions = _setup(_decision())
    new_id = await uc.reject("d1", reviewer="99", note="다른 상품", target_entity_id=None,
                             request_id="r")
    assert new_id not in ("e1", "e2") and store.entities[new_id].name == "A 상품"
    assert store.mentions[0][0] == new_id
    assert "e1" not in store.entities          # 언급이 없어진 엔티티는 정리
    row = decisions.rows["d1"]
    assert row.review_status is ReviewStatus.REJECTED and row.entity_id == new_id


@pytest.mark.asyncio
async def test_reject_with_candidate_target_reassigns():
    uc, store, _ = _setup(_decision())
    out = await uc.reject("d1", reviewer="99", note=None, target_entity_id="e2",
                          request_id="r")
    assert out == "e2" and store.mentions[0][0] == "e2"


@pytest.mark.asyncio
async def test_reject_new_decision_requires_candidate_target():
    uc, _, _ = _setup(_decision(entity_id="e1", created_new=True))
    with pytest.raises(GraphReviewTargetInvalidError):
        await uc.reject("d1", reviewer="99", note=None, target_entity_id=None,
                        request_id="r")
    with pytest.raises(GraphReviewTargetInvalidError):
        await uc.reject("d1", reviewer="99", note=None, target_entity_id="zz",
                        request_id="r")


@pytest.mark.asyncio
async def test_already_reviewed_and_missing():
    uc, _, _ = _setup(_decision(status=ReviewStatus.APPROVED))
    with pytest.raises(GraphReviewAlreadyDoneError):
        await uc.approve("d1", reviewer="99", note=None, request_id="r")
    with pytest.raises(GraphReviewNotFoundError):
        await uc.approve("nope", reviewer="99", note=None, request_id="r")


@pytest.mark.asyncio
async def test_stage_off_blocks_review_actions():
    """Check G-2: 노출 단계 off 이면 검토 목록·승인·거절 모두 409."""
    import dataclasses

    from src.domain.graph_rag.exceptions import GraphStageOffError
    from src.domain.graph_rag.value_objects import GraphRagSettings, RolloutStage

    from tests.application.graph_rag.fakes import FakeReader

    _, store, decisions = _setup(_decision())
    off = FakeReader(dataclasses.replace(GraphRagSettings.defaults(),
                                         rollout_stage=RolloutStage.OFF))
    uc = ReviewUseCase(decisions=decisions, store=store, logger=MagicMock(), reader=off)
    with pytest.raises(GraphStageOffError):
        await uc.list(ReviewStatus.PENDING, 20, 0, "r")
    with pytest.raises(GraphStageOffError):
        await uc.approve("d1", reviewer="1", note=None, request_id="r")
    with pytest.raises(GraphStageOffError):
        await uc.reject("d1", reviewer="1", note=None, target_entity_id=None,
                        request_id="r")
    assert decisions.reviews == []
