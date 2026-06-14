"""시각화 라우팅 애매구간 LLM 분류 어댑터."""
from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from src.domain.visualization.interfaces import VisualizationClassifierInterface


class _VizLabel(BaseModel):
    """LLM structured output 라벨."""

    decision: Literal["visualize", "text"] = Field(
        description="차트/그래프로 보여주는 게 적절하면 visualize, 텍스트로 충분하면 text"
    )


_PROMPT = (
    "다음 분석 결과를 사용자에게 보여줄 때 차트/그래프가 더 적절한지, "
    "텍스트로 충분한지 판단하세요.\n"
    "수치를 비교/추세로 보여주는 게 이해에 도움이 되면 visualize, "
    "단순 설명/요약이면 text입니다.\n\n"
    "[질문]\n{question}\n\n[분석 결과]\n{analysis}"
)


class LangChainVisualizationClassifier(VisualizationClassifierInterface):
    """LangChain BaseChatModel 기반 시각화 분류기."""

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def classify(self, question: str, analysis_text: str) -> str:
        prompt = _PROMPT.format(question=question, analysis=analysis_text[:2000])
        structured = self._llm.with_structured_output(_VizLabel)
        result = await structured.ainvoke(prompt)
        return result.decision
