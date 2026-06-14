"""시각화 라우팅 도메인 정책 (휴리스틱, LLM 의존 없음)."""
import re

from src.domain.visualization.schemas import VizDecision


class VisualizationRoutingPolicy:
    """분석 결과를 시각화할지 텍스트로 답할지 1차 판단하는 규칙.

    하이브리드 라우팅의 휴리스틱 단계를 담당한다.
    - 명시 키워드가 있으면 즉시 visualize (LLM 불필요)
    - 시각화 신호가 전혀 없으면 즉시 text (LLM 불필요)
    - 데이터 신호는 있으나 명시 없으면 None 반환 → 상위에서 LLM 위임
    """

    VISUALIZE_KEYWORDS: tuple[str, ...] = (
        "그래프", "차트", "시각화", "그려", "도표", "추이",
        "plot", "chart", "graph", "visualize",
    )

    # 분석 텍스트의 숫자 토큰이 이 개수 이상이면 차트 후보로 간주
    NUMERIC_TOKEN_THRESHOLD: int = 4

    _NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?%?")

    def explicit_request(self, question: str) -> bool:
        """질문에 시각화 명시 키워드가 포함되어 있는가."""
        q = (question or "").lower()
        return any(kw.lower() in q for kw in self.VISUALIZE_KEYWORDS)

    def data_suggests_chart(self, analysis_text: str) -> bool:
        """분석 텍스트에 수치 신호가 충분한가 (간단 휴리스틱)."""
        if not analysis_text:
            return False
        numeric_count = len(self._NUMERIC_RE.findall(analysis_text))
        return numeric_count >= self.NUMERIC_TOKEN_THRESHOLD

    def decide(self, question: str, analysis_text: str) -> str | None:
        """1차 판단.

        Returns:
            "visualize": 명시 요청 → 즉시 시각화
            "text": 시각화 신호 없음 → 즉시 텍스트
            None: 데이터 신호는 있으나 명시 없음 → LLM 위임(애매구간)
        """
        if self.explicit_request(question):
            return VizDecision.VISUALIZE.value
        if self.data_suggests_chart(analysis_text):
            return None
        return VizDecision.TEXT.value
