"""ToolFactory 인용 라벨러 전달 S4 — answer-citation-verification §9.2."""

from unittest.mock import MagicMock

from src.infrastructure.agent_builder.tool_factory import ToolFactory


def test_labeler_is_passed_to_rag_tool():
    labeler = MagicMock()
    factory = ToolFactory(
        logger=MagicMock(), hybrid_search_use_case=MagicMock(), citation_labeler=labeler
    )
    tool = factory.create("internal_document_search", "req")
    assert tool.citation_labeler is labeler


def test_default_is_none():
    factory = ToolFactory(logger=MagicMock(), hybrid_search_use_case=MagicMock())
    assert factory.create("internal_document_search", "req").citation_labeler is None
