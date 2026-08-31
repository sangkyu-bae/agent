"""PresentationGeneratorToolConfig (Design §9.1 — DocumentGeneratorToolConfig 동형)."""

from dataclasses import asdict

import pytest
from src.domain.blueprint.tool_config import PresentationGeneratorToolConfig


def _cfg(**over):
    base = dict(
        blueprint_id="b1",
        output_format="pptx",
        mcp_pptx_to_pdf_tool_id="",
        max_slides=15,
    )
    base.update(over)
    return PresentationGeneratorToolConfig(**base)


def test_defaults_roundtrip_via_asdict():
    cfg = _cfg()
    assert PresentationGeneratorToolConfig(**asdict(cfg)) == cfg


def test_requires_blueprint_id():
    with pytest.raises(ValueError):
        _cfg(blueprint_id="")


@pytest.mark.parametrize("fmt", ["pdf", "pptx"])
def test_accepts_supported_output_formats(fmt):
    assert _cfg(output_format=fmt).output_format == fmt


def test_rejects_docx_and_bad_mcp_prefix_and_slide_range():
    with pytest.raises(ValueError):
        _cfg(output_format="docx")
    with pytest.raises(ValueError):
        _cfg(mcp_pptx_to_pdf_tool_id="not-mcp")
    _cfg(mcp_pptx_to_pdf_tool_id="mcp_abc")
    with pytest.raises(ValueError):
        _cfg(max_slides=0)
    with pytest.raises(ValueError):
        _cfg(max_slides=61)
