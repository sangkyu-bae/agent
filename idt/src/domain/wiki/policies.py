"""WikiPolicy: LLM Wiki 도메인 규칙.

LLM-WIKI-001 §Policy. 외부 호출 없이 순수 검증 함수만 보관한다.
핵심 불변식:
  - 출처 불변식: source_refs 가 비어 있으면 위키 항목을 생성할 수 없다(환각 누적 방지).
  - 상태 전이: ALLOWED_TRANSITIONS 에 정의된 전이만 허용한다.
"""
from src.domain.wiki.entity import WikiArticle, WikiStatus


class WikiPolicy:
    """위키 생성/전이/신뢰도 검증 규칙."""

    TITLE_MAX = 200
    CONTENT_MAX = 8000
    SOURCE_REFS_MIN = 1
    CONFIDENCE_MIN = 0.0
    CONFIDENCE_MAX = 1.0

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
