"""UpdateAgentRequest/Response 도구 편집 필드 — agent-update-tool-editing D §4.2.

None = 도구 변경 안 함 / [] = 전부 해제 / [...] = 목표 상태 전체 교체.
응답은 도구 변경으로 발생한 visibility clamp 를 사용자에게 알린다.
"""
from src.application.agent_builder.schemas import (
    RagToolConfigRequest,
    UpdateAgentRequest,
    UpdateAgentResponse,
)


def test_tool_fields_default_to_none_meaning_unchanged():
    req = UpdateAgentRequest()

    assert req.tool_ids is None
    assert req.tool_configs is None


def test_empty_tool_ids_is_distinct_from_none():
    req = UpdateAgentRequest(tool_ids=[])

    assert req.tool_ids == []


def test_accepts_catalog_notation_tool_ids_and_configs():
    req = UpdateAgentRequest(
        tool_ids=["internal:tavily_search", "internal:internal_document_search"],
        tool_configs={
            "internal:internal_document_search": RagToolConfigRequest(top_k=7)
        },
    )

    assert req.tool_ids[0] == "internal:tavily_search"
    assert req.tool_configs["internal:internal_document_search"].top_k == 7


def test_response_carries_clamp_result():
    res = UpdateAgentResponse(
        agent_id="a1",
        name="n",
        system_prompt="p",
        updated_at="2026-09-06T00:00:00+00:00",
        visibility="department",
        visibility_clamped=True,
        max_visibility="department",
    )

    assert res.visibility_clamped is True
    assert res.max_visibility == "department"


def test_response_clamp_fields_are_optional_for_existing_callers():
    res = UpdateAgentResponse(
        agent_id="a1",
        name="n",
        system_prompt="p",
        updated_at="2026-09-06T00:00:00+00:00",
    )

    assert res.visibility_clamped is False
    assert res.max_visibility is None
