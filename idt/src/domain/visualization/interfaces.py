"""시각화 라우팅 도메인 포트."""
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from src.domain.visualization.chart_schemas import ChartConfig


class VisualizationClassifierInterface(ABC):
    """애매구간 LLM 분류 포트.

    application 레이어는 이 인터페이스에만 의존하고,
    구체 구현(LLM 호출)은 infrastructure에서 제공한다.
    """

    @abstractmethod
    async def classify(self, question: str, analysis_text: str) -> str:
        """질문 + 분석 텍스트로 'visualize' 또는 'text'를 반환한다."""
        raise NotImplementedError


class ChartBuilderInterface(ABC):
    """분석 텍스트 → Chart.js config 생성 포트.

    구체 구현(LLM structured output)은 infrastructure에서 제공한다.
    실패 시 빈 리스트를 반환해 본 답변 흐름을 막지 않는다.
    """

    @abstractmethod
    async def build(
        self, question: str, analysis_text: str, context: str = "",
    ) -> list[ChartConfig]:
        """질문+분석텍스트(+보조 컨텍스트)로 Chart.js config 리스트 생성."""
        raise NotImplementedError


class ChartTransformResult(BaseModel):
    """차트 변환 결과. charts=[] 는 변환 실패/불가 → 호출측이 일반 경로로 폴백.

    chart-context-continuity Design §3.4.
    """

    charts: list[ChartConfig] = Field(default_factory=list)
    message: str = ""


class ChartTransformerInterface(ABC):
    """기존 차트 config + 사용자 지시 → 새 차트 변환 포트.

    ChartBuilderInterface(텍스트→차트)와 책임 분리 (D3).
    구체 구현(LLM structured output)은 infrastructure에서 제공한다.
    실패 시 charts=[] 결과를 반환해 본 답변 흐름을 막지 않는다.
    """

    @abstractmethod
    async def transform(
        self, instruction: str, charts: list[dict], context: str = "",
    ) -> ChartTransformResult:
        """사용자 지시 + 기존 차트(저장 JSON)(+분석 데이터 컨텍스트) → 새 차트."""
        raise NotImplementedError
