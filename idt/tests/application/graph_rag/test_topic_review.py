"""주제 판정 검토 (Design §11.9 검토, FR-27) — ReviewUseCase 가 주제 판정을 나눠 처리."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.application.graph_rag.admin.review_use_case import (
    GraphReviewTargetInvalidError,
    ReviewUseCase,
)
from src.application.graph_rag.topic.review import TopicReviewer
from src.domain.graph_rag.resolution import (
    DecidedBy,
    ResolutionBand,
    ResolutionDecision,
    ReviewStatus,
)
from src.domain.graph_rag.topic import (
    DOCUMENT_CHUNK_ID,
    DocumentTopic,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicStatus,
)

from tests.application.graph_rag.fakes import (
    FakeDecisions,
    FakeDocumentTopics,
    FakeStore,
    FakeTopics,
)


def _topic(id_, name, status=TopicStatus.ACTIVE, origin=TopicOrigin.ADMIN,
           level=TopicLevel.MAJOR, parent=None):
    return Topic(id_, name, name, level, parent, "", status, origin)


def _decision(entity_id, *, created_new, candidates=("t-loan",), id_="d1",
              mention="여신", mention_type="주제:대분류"):
    return ResolutionDecision(
        id=id_, job_id="j", document_id="doc-1", chunk_id=DOCUMENT_CHUNK_ID,
        mention_text=mention, mention_type=mention_type,
        candidates=tuple({"label": f"C{i}", "entity_id": c, "name": c}
                         for i, c in enumerate(candidates, 1)),
        probabilities=None, chosen_label="NEW" if created_new else "C1",
        entity_id=entity_id, created_new=created_new,
        decided_by=DecidedBy.LLM_FALLBACK, band=ResolutionBand.FALLBACK,
        probability=None, review_status=ReviewStatus.PENDING,
    )


def _make(topics, decision, links=()):
    decisions, repo, doc_links, store = (
        FakeDecisions(), FakeTopics(topics), FakeDocumentTopics(), FakeStore()
    )
    decisions.rows[decision.id] = decision
    doc_links.links["doc-1"] = list(links)
    uc = ReviewUseCase(
        decisions=decisions, store=store, logger=MagicMock(),
        topics=TopicReviewer(topics=repo, document_topics=doc_links, store=store,
                             logger=MagicMock()),
    )
    return uc, repo, doc_links, store, decisions


def _link(topic_id, decision_id="d1", primary=True):
    return DocumentTopic("doc-1", topic_id, primary, None, decision_id)


@pytest.mark.asyncio
async def test_approve_new_auto_topic_activates_it():
    uc, repo, *_ = _make(
        [_topic("t-new", "여신", TopicStatus.PENDING, TopicOrigin.AUTO)],
        _decision("t-new", created_new=True, candidates=()),
    )
    await uc.approve("d1", reviewer="admin", note=None, request_id="r")
    assert repo.rows["t-new"].status is TopicStatus.ACTIVE


@pytest.mark.asyncio
async def test_reject_new_topic_moves_document_and_retires_empty_auto_topic():
    uc, repo, links, store, decisions = _make(
        [_topic("t-loan", "대출"),
         _topic("t-new", "여신", TopicStatus.PENDING, TopicOrigin.AUTO)],
        _decision("t-new", created_new=True, candidates=("t-loan",)),
        links=[_link("t-new")],
    )
    to = await uc.reject("d1", reviewer="admin", note="같은 주제",
                         target_entity_id="t-loan", request_id="r")
    assert to == "t-loan"
    assert links.links["doc-1"][0].topic_id == "t-loan"
    assert repo.rows["t-new"].status is TopicStatus.RETIRED
    assert store.doc_topics["doc-1"] == ["t-loan"]
    assert decisions.rows["d1"].review_status is ReviewStatus.REJECTED
    assert decisions.rows["d1"].entity_id == "t-loan"


@pytest.mark.asyncio
async def test_reject_new_topic_without_target_is_invalid():
    uc, *_ = _make(
        [_topic("t-new", "여신", TopicStatus.PENDING, TopicOrigin.AUTO)],
        _decision("t-new", created_new=True, candidates=()),
    )
    with pytest.raises(GraphReviewTargetInvalidError):
        await uc.reject("d1", reviewer="admin", note=None, target_entity_id=None,
                        request_id="r")


@pytest.mark.asyncio
async def test_reject_link_without_target_splits_into_new_active_topic():
    uc, repo, links, store, _ = _make(
        [_topic("t-loan", "대출")],
        _decision("t-loan", created_new=False, mention="여신"),
        links=[_link("t-loan")],
    )
    to = await uc.reject("d1", reviewer="admin", note=None, target_entity_id=None,
                         request_id="r")
    new = repo.rows[to]
    assert (new.name, new.status, new.origin, new.created_by) == (
        "여신", TopicStatus.ACTIVE, TopicOrigin.ADMIN, "admin")
    assert links.links["doc-1"][0].topic_id == to
    assert repo.rows["t-loan"].status is TopicStatus.ACTIVE  # 관리자 주제는 유지


@pytest.mark.asyncio
async def test_reject_minor_split_keeps_parent_of_original():
    uc, repo, *_ = _make(
        [_topic("t-loan", "여신"),
         _topic("t-corp", "법인대출", level=TopicLevel.MINOR, parent="t-loan")],
        _decision("t-corp", created_new=False, mention="기업여신",
                  candidates=("t-corp",), mention_type="주제:소분류"),
        links=[_link("t-loan", "d0"), _link("t-corp")],
    )
    to = await uc.reject("d1", reviewer="admin", note=None, target_entity_id=None,
                         request_id="r")
    assert (repo.rows[to].level, repo.rows[to].parent_id) == (
        TopicLevel.MINOR, "t-loan")


@pytest.mark.asyncio
async def test_auto_topic_still_used_elsewhere_is_not_retired():
    uc, repo, links, *_ = _make(
        [_topic("t-loan", "대출"),
         _topic("t-new", "여신", TopicStatus.PENDING, TopicOrigin.AUTO)],
        _decision("t-new", created_new=True, candidates=("t-loan",)),
        links=[_link("t-new")],
    )
    links.links["doc-2"] = [DocumentTopic("doc-2", "t-new", True, None, "dx")]
    await uc.reject("d1", reviewer="admin", note=None, target_entity_id="t-loan",
                    request_id="r")
    assert repo.rows["t-new"].status is TopicStatus.PENDING


@pytest.mark.asyncio
async def test_entity_decisions_still_use_graph_reassign():
    """주제가 아닌 판정은 기존 경로(Neo4j 언급 이동)를 그대로 탄다."""
    uc, _, _, store, _ = _make(
        [], _decision("e-old", created_new=True, candidates=("e-a",),
                      mention_type="상품"),
    )
    store.reassign_decision = MagicMock(side_effect=lambda *a: _done())
    store.delete_entity_if_orphan = MagicMock(side_effect=lambda *a: _done(True))
    await uc.reject("d1", reviewer="admin", note=None, target_entity_id="e-a",
                    request_id="r")
    store.reassign_decision.assert_called_once_with("d1", "e-a")


async def _done(value=None):
    return value
