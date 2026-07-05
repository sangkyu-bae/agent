"""Domain 테스트: WikiPolicy (LLM-WIKI-001).

생성 불변식(출처 필수 등)과 상태 전이 규칙, confidence 클램핑을 검증한다.
"""
import pytest

from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.domain.wiki.policies import WikiPolicy


def _article(**kw) -> WikiArticle:
    base = dict(
        id="w1",
        agent_id="agent_1",
        title="제목",
        content="본문",
        source_type=WikiSourceType.DISTILLED,
        source_refs=["doc:1"],
    )
    base.update(kw)
    return WikiArticle(**base)


class TestValidateForCreation:

    def test_valid_article_passes(self):
        WikiPolicy.validate_for_creation(_article())  # no raise

    def test_empty_title_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(_article(title="  "))

    def test_too_long_title_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(
                _article(title="x" * (WikiPolicy.TITLE_MAX + 1))
            )

    def test_empty_content_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(_article(content=""))

    def test_too_long_content_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(
                _article(content="x" * (WikiPolicy.CONTENT_MAX + 1))
            )

    def test_empty_source_refs_rejected_invariant(self):
        """출처 불변식: source_refs 비면 KB 진입 불가."""
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(_article(source_refs=[]))

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(_article(confidence=1.5))
        with pytest.raises(ValueError):
            WikiPolicy.validate_for_creation(_article(confidence=-0.1))


class TestValidateTransition:

    def test_draft_to_approved_allowed(self):
        WikiPolicy.validate_transition(WikiStatus.DRAFT, WikiStatus.APPROVED)

    def test_draft_to_deprecated_allowed(self):
        WikiPolicy.validate_transition(WikiStatus.DRAFT, WikiStatus.DEPRECATED)

    def test_approved_to_deprecated_allowed(self):
        WikiPolicy.validate_transition(WikiStatus.APPROVED, WikiStatus.DEPRECATED)

    def test_deprecated_to_approved_allowed(self):
        WikiPolicy.validate_transition(WikiStatus.DEPRECATED, WikiStatus.APPROVED)

    def test_approved_to_draft_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_transition(WikiStatus.APPROVED, WikiStatus.DRAFT)

    def test_same_status_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_transition(WikiStatus.DRAFT, WikiStatus.DRAFT)


class TestClampConfidence:

    def test_within_range_unchanged(self):
        assert WikiPolicy.clamp_confidence(0.7) == 0.7

    def test_above_max_clamped(self):
        assert WikiPolicy.clamp_confidence(1.5) == WikiPolicy.CONFIDENCE_MAX

    def test_below_min_clamped(self):
        assert WikiPolicy.clamp_confidence(-1.0) == WikiPolicy.CONFIDENCE_MIN
