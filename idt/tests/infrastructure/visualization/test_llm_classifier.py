"""LangChainVisualizationClassifier 테스트 (LLM은 AsyncMock)."""
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.visualization.llm_classifier import (
    LangChainVisualizationClassifier,
    _VizLabel,
)


def _llm_returning(label: str) -> MagicMock:
    """with_structured_output(...).ainvoke가 _VizLabel(label)을 반환하는 fake LLM."""
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=_VizLabel(decision=label))
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


class TestLangChainVisualizationClassifier:
    async def test_returns_visualize(self) -> None:
        llm = _llm_returning("visualize")
        clf = LangChainVisualizationClassifier(llm)
        result = await clf.classify("추세 알려줘", "2023 100, 2024 130")
        assert result == "visualize"

    async def test_returns_text(self) -> None:
        llm = _llm_returning("text")
        clf = LangChainVisualizationClassifier(llm)
        result = await clf.classify("요약해줘", "내용")
        assert result == "text"

    async def test_uses_structured_output(self) -> None:
        llm = _llm_returning("text")
        clf = LangChainVisualizationClassifier(llm)
        await clf.classify("q", "a")
        llm.with_structured_output.assert_called_once_with(_VizLabel)
