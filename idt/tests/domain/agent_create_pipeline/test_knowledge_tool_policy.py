"""PipelinePolicy.with_knowledge_tool — agent-kb-quick-setup Design §9.4 / FR-12."""
from src.domain.agent_create_pipeline.policies import (
    KNOWLEDGE_TOOL_ID,
    PipelinePolicy,
)


def test_no_kb_id_returns_inputs_unchanged() -> None:
    ids, cfgs = PipelinePolicy.with_knowledge_tool(("internal:a",), None)
    assert ids == ("internal:a",)
    assert cfgs == {}


def test_kb_id_appends_knowledge_tool_and_config() -> None:
    ids, cfgs = PipelinePolicy.with_knowledge_tool(("internal:a",), "kb-1")
    assert ids == ("internal:a", KNOWLEDGE_TOOL_ID)
    assert cfgs == {KNOWLEDGE_TOOL_ID: {"kb_id": "kb-1"}}


def test_existing_knowledge_tool_is_not_duplicated() -> None:
    ids, cfgs = PipelinePolicy.with_knowledge_tool(
        ("internal:a", KNOWLEDGE_TOOL_ID), "kb-1"
    )
    assert ids == ("internal:a", KNOWLEDGE_TOOL_ID)
    assert cfgs[KNOWLEDGE_TOOL_ID]["kb_id"] == "kb-1"


def test_blank_kb_id_is_treated_as_none() -> None:
    ids, cfgs = PipelinePolicy.with_knowledge_tool((), "  ")
    assert ids == ()
    assert cfgs == {}


def test_knowledge_tool_id_is_catalog_form() -> None:
    assert KNOWLEDGE_TOOL_ID == "internal:internal_document_search"
