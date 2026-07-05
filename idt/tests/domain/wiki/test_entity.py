"""Domain 테스트: WikiArticle 엔티티 (LLM-WIKI-001).

순수 도메인 객체의 기본값/상태 전이 동작/검색 노출 판단을 검증한다.
"""
from datetime import datetime

from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


def _article(**kw) -> WikiArticle:
    base = dict(
        id="w1",
        agent_id="agent_1",
        title="여신 한도 산정 기준",
        content="여신 한도는 ...",
        source_type=WikiSourceType.DISTILLED,
        source_refs=["doc:policy#3"],
    )
    base.update(kw)
    return WikiArticle(**base)


class TestDefaults:

    def test_default_status_is_draft(self):
        assert _article().status == WikiStatus.DRAFT

    def test_default_confidence_and_version(self):
        a = _article()
        assert a.confidence == 0.5
        assert a.version == 1

    def test_optional_fields_default_none(self):
        a = _article()
        assert a.valid_until is None
        assert a.reviewer_id is None
        assert a.editor_id is None


class TestStatusTransitionsMutators:

    def test_mark_approved_sets_reviewer_and_status(self):
        a = _article()
        now = datetime(2026, 6, 28)
        a.mark_approved(reviewer_id="admin", now=now)
        assert a.status == WikiStatus.APPROVED
        assert a.reviewer_id == "admin"
        assert a.updated_at == now

    def test_mark_deprecated(self):
        a = _article(status=WikiStatus.APPROVED)
        now = datetime(2026, 6, 28)
        a.mark_deprecated(now=now)
        assert a.status == WikiStatus.DEPRECATED
        assert a.updated_at == now

    def test_restore_to_approved(self):
        a = _article(status=WikiStatus.DEPRECATED)
        a.restore(now=datetime(2026, 6, 28))
        assert a.status == WikiStatus.APPROVED

    def test_apply_edit_increments_version(self):
        a = _article()
        a.apply_edit(title="새 제목", content="새 본문", now=datetime(2026, 6, 28))
        assert a.title == "새 제목"
        assert a.content == "새 본문"
        assert a.version == 2


class TestSearchability:

    def test_approved_without_expiry_is_searchable(self):
        a = _article(status=WikiStatus.APPROVED)
        assert a.is_searchable(now=datetime(2026, 6, 28)) is True

    def test_draft_is_not_searchable(self):
        a = _article(status=WikiStatus.DRAFT)
        assert a.is_searchable(now=datetime(2026, 6, 28)) is False

    def test_deprecated_is_not_searchable(self):
        a = _article(status=WikiStatus.DEPRECATED)
        assert a.is_searchable(now=datetime(2026, 6, 28)) is False

    def test_expired_approved_is_not_searchable(self):
        a = _article(status=WikiStatus.APPROVED, valid_until=datetime(2026, 6, 1))
        assert a.is_searchable(now=datetime(2026, 6, 28)) is False

    def test_unexpired_approved_is_searchable(self):
        a = _article(status=WikiStatus.APPROVED, valid_until=datetime(2026, 7, 1))
        assert a.is_searchable(now=datetime(2026, 6, 28)) is True

    def test_is_expired(self):
        a = _article(valid_until=datetime(2026, 6, 1))
        assert a.is_expired(now=datetime(2026, 6, 28)) is True
        assert a.is_expired(now=datetime(2026, 5, 1)) is False

    def test_no_expiry_never_expired(self):
        a = _article(valid_until=None)
        assert a.is_expired(now=datetime(2026, 6, 28)) is False
