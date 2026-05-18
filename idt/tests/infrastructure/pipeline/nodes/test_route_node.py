from unittest.mock import MagicMock

import pytest

from src.domain.pdf_routing.schemas import RoutingDecision, RoutingReason
from src.infrastructure.pipeline.nodes.route_node import route_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state_after_analyze(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
    )
    state["document_type"] = "text_heavy"
    state["analysis_confidence"] = 0.95
    state["total_pages"] = 10
    state["analysis_metrics"] = {
        "sampled_pages": 3,
        "avg_text_chars": 500.0,
        "avg_image_count": 0.0,
        "avg_image_area_ratio": 0.0,
        "avg_table_count": 0.0,
        "extractable_text_ratio": 1.0,
    }
    state.update(overrides)
    return state


class TestRouteNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = _make_state_after_analyze()
        router = MagicMock()
        router.route.return_value = RoutingDecision(
            parser_type="pymupdf",
            document_type="text_heavy",
            confidence=0.95,
            reason=RoutingReason.DOCUMENT_TYPE_MATCH,
            is_fallback=False,
        )

        result = await route_node(state, router)

        assert result["routed_parser_type"] == "pymupdf"
        assert result["is_fallback"] is False
        assert result["status"] == "routing"

    @pytest.mark.asyncio
    async def test_route_exception_falls_back_to_pymupdf(self):
        state = _make_state_after_analyze()
        router = MagicMock()
        router.route.side_effect = RuntimeError("routing error")

        result = await route_node(state, router)

        assert result["routed_parser_type"] == "pymupdf"
        assert result["is_fallback"] is True
        assert result["status"] == "routing"
        assert any("Route failed" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_document_type_none_passes_none_analysis(self):
        state = _make_state_after_analyze(document_type=None)
        router = MagicMock()
        router.route.return_value = RoutingDecision(
            parser_type="pymupdf",
            confidence=0.0,
            reason=RoutingReason.NO_ANALYSIS_FALLBACK,
            is_fallback=True,
        )

        result = await route_node(state, router)

        call_args = router.route.call_args
        assert call_args.kwargs.get("analysis_result") is None or call_args[1].get("analysis_result") is None or call_args[0][0] is None
