"""차트 후속 질문 의도 판정 휴리스틱 (LLM 의존 없음).

chart-context-continuity Design §3.3 (D2):
- 보수적 판정 — 애매하면 NONE(일반 경로). 오분류 안전망은 application 가드
  (세션에 charts 부속 메시지가 없으면 일반 경로)가 추가 담당한다.
- NEW_FROM_DATA 판정은 Phase 3에서 활성화 (enum 값만 선점).
"""
from enum import Enum


class ChartFollowupDecision(str, Enum):
    EDIT = "chart_edit"                    # 기존 차트 수정 (색/타입/시리즈)
    NEW_FROM_DATA = "chart_new_from_data"  # 저장된 분석 데이터로 신규 차트 (Phase 3)
    NONE = "none"                          # 일반 경로


class ChartFollowupPolicy:
    """질문 텍스트 → 차트 후속 의도 1차 판정 (VisualizationRoutingPolicy 동형)."""

    REFERENT_KEYWORDS: tuple[str, ...] = (
        "해당", "이 ", "그 ", "위 ", "방금", "아까", "그걸", "이걸",
    )
    CHART_NOUNS: tuple[str, ...] = ("그래프", "차트", "도표", "chart", "graph")
    EDIT_VERBS: tuple[str, ...] = (
        "바꿔", "변경", "수정", "넣어", "추가", "색", "나눠", "분리", "합쳐",
    )

    def decide(self, question: str | None) -> ChartFollowupDecision:
        """EDIT: (차트명사 + 지시어) 또는 (차트명사 + 편집동사). 그 외 NONE."""
        q = (question or "").lower()
        if not q or not any(noun in q for noun in self.CHART_NOUNS):
            return ChartFollowupDecision.NONE
        has_referent = any(kw in q for kw in self.REFERENT_KEYWORDS)
        has_edit_verb = any(verb in q for verb in self.EDIT_VERBS)
        if has_referent or has_edit_verb:
            return ChartFollowupDecision.EDIT
        return ChartFollowupDecision.NONE
