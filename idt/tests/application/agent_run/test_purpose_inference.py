"""Tool name → RunPurpose 매핑 단위 테스트.

AGENT-OBS-002 Design §4-3 매핑 표 검증.
"""
import pytest

from src.application.agent_run.purpose_inference import infer_tool_purpose
from src.domain.agent_run.value_objects import RunPurpose


class TestInferToolPurposeMappings:
    @pytest.mark.parametrize(
        "tool_name, expected",
        [
            # WORKER (사용자 의도 직접 처리 툴)
            ("internal_document_search", RunPurpose.WORKER),
            ("rag_search", RunPurpose.WORKER),
            ("rag_search_finance", RunPurpose.WORKER),
            ("hybrid_search", RunPurpose.WORKER),
            ("retrieval_v2", RunPurpose.WORKER),
            ("tavily_search", RunPurpose.WORKER),
            ("perplexity_search", RunPurpose.WORKER),
            ("web_search_engine", RunPurpose.WORKER),
            ("excel_export", RunPurpose.WORKER),
            ("python_code_executor", RunPurpose.WORKER),
            # QUERY_REWRITE
            ("query_rewriter_v2", RunPurpose.QUERY_REWRITE),
            ("query_rewrite_basic", RunPurpose.QUERY_REWRITE),
            # RERANK
            ("reranker_cohere", RunPurpose.RERANK),
            ("compressor_basic", RunPurpose.RERANK),
            # HALLUCINATION_CHECK
            ("hallucination_check_v1", RunPurpose.HALLUCINATION_CHECK),
            ("hallucination_validator", RunPurpose.HALLUCINATION_CHECK),
            # MCP → OTHER
            ("mcp_jira_create_issue", RunPurpose.OTHER),
            ("mcp_slack_send_message", RunPurpose.OTHER),
            # Unknown → OTHER
            ("totally_unknown_tool", RunPurpose.OTHER),
            ("", RunPurpose.OTHER),
        ],
    )
    def test_known_mappings(self, tool_name: str, expected: RunPurpose) -> None:
        assert infer_tool_purpose(tool_name) == expected

    def test_none_input_returns_other(self) -> None:
        # type: ignore[arg-type]
        assert infer_tool_purpose(None) == RunPurpose.OTHER  # type: ignore[arg-type]


class TestInferToolPurposeCaseInsensitive:
    @pytest.mark.parametrize(
        "tool_name, expected",
        [
            ("RAG_SEARCH", RunPurpose.WORKER),
            ("Query_Rewriter", RunPurpose.QUERY_REWRITE),
            ("RERANKER_COHERE", RunPurpose.RERANK),
            ("Hallucination_Check", RunPurpose.HALLUCINATION_CHECK),
            ("MCP_anything", RunPurpose.OTHER),
        ],
    )
    def test_case_insensitive_matching(
        self, tool_name: str, expected: RunPurpose
    ) -> None:
        assert infer_tool_purpose(tool_name) == expected


class TestInferToolPurposePriority:
    """우선순위 검증 — 첫 매칭 규칙이 적용되는지."""

    def test_query_rewrite_priority_over_worker(self) -> None:
        # 'query_rewrite'가 WORKER보다 먼저 매칭되어야 함
        assert infer_tool_purpose("query_rewriter_rag") == RunPurpose.QUERY_REWRITE

    def test_reranker_priority_over_worker(self) -> None:
        assert infer_tool_purpose("reranker_for_rag") == RunPurpose.RERANK
