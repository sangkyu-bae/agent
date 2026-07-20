"""WikiPolicy: LLM Wiki 도메인 규칙.

LLM-WIKI-001 §Policy. 외부 호출 없이 순수 검증 함수만 보관한다.
핵심 불변식:
  - 출처 불변식: source_refs 가 비어 있으면 위키 항목을 생성할 수 없다(환각 누적 방지).
  - 상태 전이: ALLOWED_TRANSITIONS 에 정의된 전이만 허용한다.
"""
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


class WikiPolicy:
    """위키 생성/전이/신뢰도 검증 규칙."""

    TITLE_MAX = 200
    CONTENT_MAX = 8000
    SOURCE_REFS_MIN = 1
    CONFIDENCE_MIN = 0.0
    CONFIDENCE_MAX = 1.0

    # wiki-user-facing: 사람 작성 출처 표기 / 가상 폴더 path 제약
    HUMAN_SOURCE_PREFIX = "human:"
    PATH_MAX_LEN = 255
    PATH_MAX_DEPTH = 3
    PATH_SEGMENT_MAX = 30

    ALLOWED_TRANSITIONS: dict[WikiStatus, set[WikiStatus]] = {
        WikiStatus.DRAFT: {WikiStatus.APPROVED, WikiStatus.DEPRECATED},
        WikiStatus.APPROVED: {WikiStatus.DEPRECATED},
        WikiStatus.DEPRECATED: {WikiStatus.APPROVED},
    }

    @staticmethod
    def validate_for_creation(article: WikiArticle) -> None:
        """위키 항목 생성 시 불변식 검증. 위반 시 ValueError."""
        if not article.title or not article.title.strip():
            raise ValueError("title은 빈 문자열일 수 없습니다.")
        if len(article.title) > WikiPolicy.TITLE_MAX:
            raise ValueError(f"title은 {WikiPolicy.TITLE_MAX}자를 초과할 수 없습니다.")
        if not article.content or not article.content.strip():
            raise ValueError("content는 빈 문자열일 수 없습니다.")
        if len(article.content) > WikiPolicy.CONTENT_MAX:
            raise ValueError(
                f"content는 {WikiPolicy.CONTENT_MAX}자를 초과할 수 없습니다."
            )
        if len(article.source_refs) < WikiPolicy.SOURCE_REFS_MIN:
            raise ValueError("source_refs는 최소 1개 필요합니다(출처 불변식).")
        if not (
            WikiPolicy.CONFIDENCE_MIN <= article.confidence <= WikiPolicy.CONFIDENCE_MAX
        ):
            raise ValueError("confidence는 0.0~1.0 범위여야 합니다.")

    @staticmethod
    def validate_transition(current: WikiStatus, target: WikiStatus) -> None:
        """허용되지 않은 상태 전이면 ValueError."""
        allowed = WikiPolicy.ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"허용되지 않은 상태 전이입니다: {current.value} -> {target.value}"
            )

    @staticmethod
    def clamp_confidence(value: float) -> float:
        """confidence를 0.0~1.0 범위로 클램핑한다(환류 갱신용)."""
        return max(WikiPolicy.CONFIDENCE_MIN, min(WikiPolicy.CONFIDENCE_MAX, value))

    @staticmethod
    def validate_path(path: str | None) -> None:
        """가상 폴더 path 검증. None=미분류 허용, 위반 시 ValueError."""
        if path is None:
            return
        if len(path) > WikiPolicy.PATH_MAX_LEN:
            raise ValueError(
                f"path는 {WikiPolicy.PATH_MAX_LEN}자를 초과할 수 없습니다."
            )
        segments = path.split("/")
        if len(segments) > WikiPolicy.PATH_MAX_DEPTH:
            raise ValueError(
                f"path 깊이는 {WikiPolicy.PATH_MAX_DEPTH}단계를 초과할 수 없습니다."
            )
        for seg in segments:
            if not seg.strip():
                raise ValueError("path에 빈 세그먼트를 포함할 수 없습니다.")
            if len(seg) > WikiPolicy.PATH_SEGMENT_MAX:
                raise ValueError(
                    f"path 세그먼트는 {WikiPolicy.PATH_SEGMENT_MAX}자를 초과할 수 없습니다."
                )

    @staticmethod
    def human_source_ref(user_id: str) -> str:
        """사람 작성물의 출처 표기 — 출처 불변식을 완화 없이 충족한다."""
        return f"{WikiPolicy.HUMAN_SOURCE_PREFIX}{user_id}"

    @staticmethod
    def can_manage(
        article: WikiArticle,
        actor_id: str,
        actor_is_admin: bool,
        agent_owner_id: str,
    ) -> bool:
        """편집/폐기 인가: admin은 전부, 소유자는 자기 에이전트의 human 문서만.

        approve/reject/restore는 이 함수를 타지 않는다(admin 전용 유지).
        """
        if actor_is_admin:
            return True
        return (
            actor_id == agent_owner_id
            and article.source_type == WikiSourceType.HUMAN
        )
