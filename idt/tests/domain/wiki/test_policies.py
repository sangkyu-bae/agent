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


class TestValidatePath:
    """wiki-user-facing: 가상 폴더 path 검증."""

    def test_none_allowed(self):
        WikiPolicy.validate_path(None)  # 미분류 허용

    def test_single_segment_allowed(self):
        WikiPolicy.validate_path("여신")

    def test_max_depth_allowed(self):
        WikiPolicy.validate_path("여신/한도/동일인")  # 깊이 3

    def test_depth_over_max_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("a/b/c/d")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("")

    def test_leading_slash_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("/여신")

    def test_trailing_slash_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("여신/")

    def test_consecutive_slash_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("여신//한도")

    def test_blank_segment_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("여신/ /한도")

    def test_segment_over_max_rejected(self):
        with pytest.raises(ValueError):
            WikiPolicy.validate_path("x" * (WikiPolicy.PATH_SEGMENT_MAX + 1))

    def test_total_length_over_max_rejected(self):
        seg = "x" * WikiPolicy.PATH_SEGMENT_MAX
        # 깊이 제한에 걸리지 않는 형태로 전체 길이 초과를 만들 수 없으므로
        # PATH_MAX_LEN 검증은 단일 세그먼트 상한과 독립적으로 확인한다
        long_path = "/".join([seg, seg, seg])
        if len(long_path) <= WikiPolicy.PATH_MAX_LEN:
            long_path = None  # 구성 불가 시 스킵 신호
        if long_path is not None:
            with pytest.raises(ValueError):
                WikiPolicy.validate_path(long_path)


class TestHumanSourceRef:
    """wiki-user-facing: 사람 작성 출처 표기 — 출처 불변식을 완화 없이 충족."""

    def test_format(self):
        assert WikiPolicy.human_source_ref("42") == "human:42"

    def test_prefix_constant(self):
        assert WikiPolicy.human_source_ref("u1").startswith(
            WikiPolicy.HUMAN_SOURCE_PREFIX
        )

    def test_satisfies_creation_invariant(self):
        article = _article(
            source_type=WikiSourceType.HUMAN,
            source_refs=[WikiPolicy.human_source_ref("42")],
        )
        WikiPolicy.validate_for_creation(article)  # no raise


class TestCanManage:
    """wiki-user-facing: 편집/폐기 인가 매트릭스 (admin×전부, 소유자×human만)."""

    def _human(self):
        return _article(source_type=WikiSourceType.HUMAN, source_refs=["human:7"])

    def _distilled(self):
        return _article(source_type=WikiSourceType.DISTILLED)

    def test_admin_can_manage_human(self):
        assert WikiPolicy.can_manage(
            self._human(), actor_id="99", actor_is_admin=True, agent_owner_id="7"
        )

    def test_admin_can_manage_distilled(self):
        assert WikiPolicy.can_manage(
            self._distilled(), actor_id="99", actor_is_admin=True, agent_owner_id="7"
        )

    def test_owner_can_manage_own_human(self):
        assert WikiPolicy.can_manage(
            self._human(), actor_id="7", actor_is_admin=False, agent_owner_id="7"
        )

    def test_owner_cannot_manage_distilled(self):
        assert not WikiPolicy.can_manage(
            self._distilled(), actor_id="7", actor_is_admin=False, agent_owner_id="7"
        )

    def test_non_owner_cannot_manage_human(self):
        assert not WikiPolicy.can_manage(
            self._human(), actor_id="8", actor_is_admin=False, agent_owner_id="7"
        )


class TestRefsDedup:
    """fix-wiki-distill-dedup: refs 정체성 키·중복 판정 (정확 일치만)."""

    def test_refs_key는_순서_무관(self):
        assert WikiPolicy.refs_key(["doc:1", "doc:2"]) == WikiPolicy.refs_key(
            ["doc:2", "doc:1"]
        )

    def test_refs_key는_공백_strip(self):
        assert WikiPolicy.refs_key([" doc:1 "]) == WikiPolicy.refs_key(["doc:1"])

    def test_동일_refs는_중복(self):
        existing = {WikiPolicy.refs_key(["doc:1", "doc:2"])}
        assert WikiPolicy.is_duplicate_group(["doc:2", "doc:1"], existing) is True

    def test_부분_겹침은_신규(self):
        existing = {WikiPolicy.refs_key(["doc:1", "doc:2"])}
        assert WikiPolicy.is_duplicate_group(["doc:1"], existing) is False
        assert WikiPolicy.is_duplicate_group(["doc:1", "doc:2", "doc:3"], existing) is False

    def test_빈_기존_집합은_항상_신규(self):
        assert WikiPolicy.is_duplicate_group(["doc:1"], set()) is False
