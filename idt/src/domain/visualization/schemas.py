"""시각화 라우팅 도메인 스키마."""
from enum import Enum


class VizDecision(str, Enum):
    """라우팅 판단 결과 (2분기).

    - VISUALIZE: 차트/그래프로 보여주는 것이 적절
    - TEXT: 텍스트 답변으로 충분
    """

    VISUALIZE = "visualize"
    TEXT = "text"
