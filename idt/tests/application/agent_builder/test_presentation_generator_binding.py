"""presentation_generator 워커 tool_config 바인딩 (golden-sample-blueprint D7)."""

import pytest
from src.application.agent_builder.presentation_generator_binding import (
    PRESENTATION_GENERATOR_TOOL_ID,
    apply_presentation_generator_config,
)
from src.application.agent_builder.schemas import PresentationGeneratorConfigRequest
from src.domain.agent_builder.schemas import WorkerDefinition


def _worker(tool_id: str, worker_type: str = "tool") -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"w-{tool_id}",
        description="",
        worker_type=worker_type,
    )


def test_injects_validated_config_into_generator_worker():
    workers = [_worker("tavily_search"), _worker(PRESENTATION_GENERATOR_TOOL_ID)]
    req = PresentationGeneratorConfigRequest(
        blueprint_id="bp1",
        output_format="pdf",
        mcp_pptx_to_pdf_tool_id="mcp_x",
        max_slides=12,
    )
    apply_presentation_generator_config(req, workers)
    assert workers[1].tool_config == {
        "blueprint_id": "bp1",
        "output_format": "pdf",
        "mcp_pptx_to_pdf_tool_id": "mcp_x",
        "max_slides": 12,
    }
    assert workers[0].tool_config is None


def test_missing_worker_raises_value_error():
    with pytest.raises(ValueError, match="presentation_generator"):
        apply_presentation_generator_config(
            PresentationGeneratorConfigRequest(blueprint_id="bp1"),
            [_worker("tavily_search")],
        )


def test_invalid_config_raises_value_error():
    with pytest.raises(ValueError):
        apply_presentation_generator_config(
            PresentationGeneratorConfigRequest(blueprint_id="", max_slides=5),
            [_worker(PRESENTATION_GENERATOR_TOOL_ID)],
        )
    with pytest.raises(ValueError):
        apply_presentation_generator_config(
            PresentationGeneratorConfigRequest(blueprint_id="b", output_format="docx"),
            [_worker(PRESENTATION_GENERATOR_TOOL_ID)],
        )
