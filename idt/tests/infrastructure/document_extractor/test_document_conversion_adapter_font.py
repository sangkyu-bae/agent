"""to_document 폰트 임베드 연동 테스트 (Design §8.2 U-10~U-12).

Option C(어댑터 일괄 주입): 폰트는 html→doc 변환 경로 한 곳에서 보장된다.
generator·composer 는 물론 미래 호출자까지 자동으로 커버되는지 확인한다.
"""
import base64
import json

import pytest

from src.infrastructure.document_extractor.document_conversion_adapter import (
    DocumentConversionAdapter,
)


class _NullLogger:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.payloads: list[dict] = []

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return json.dumps(
            {
                "format": "pdf",
                "output_mode": "base64",
                "content": base64.b64encode(b"%PDF-fake").decode("ascii"),
            }
        )


class _FakeLoader:
    def __init__(self, tools) -> None:
        self._tools = tools

    async def load_by_tool_id(self, tool_id, repository, request_id):
        return self._tools


class _StubEmbedder:
    """폰트 셸을 씌운 것처럼 흉내낸다 (실제 서브셋은 별도 테스트에서 검증)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def wrap(self, html: str, request_id: str):
        self.calls.append(html)
        from src.domain.document_font.schemas import FontEmbedResult

        return FontEmbedResult(
            html=f"<html><head><style>@font-face{{}}</style></head>"
            f"<body>{html}</body></html>",
            applied=True,
        )


def _adapter(tools, embedder=None):
    return DocumentConversionAdapter(
        mcp_tool_loader=_FakeLoader(tools),
        mcp_repository=object(),
        logger=_NullLogger(),
        font_embedder=embedder,
    )


def _sent_html(tool: _FakeTool) -> str:
    source = tool.payloads[0]["arguments"]["source"]
    return base64.b64decode(source["value"]).decode("utf-8")


@pytest.mark.asyncio
async def test_to_document_sends_font_embedded_html():
    """U-10: MCP 로 전달된 base64 를 되돌리면 @font-face 가 들어 있다."""
    tool = _FakeTool("html_to_pdf")
    embedder = _StubEmbedder()

    await _adapter([tool], embedder).to_document(
        "<h1>위기 레포트</h1>", "pdf", "mcp_x", "r-1"
    )

    sent = _sent_html(tool)
    assert "@font-face" in sent
    assert "<h1>위기 레포트</h1>" in sent
    assert embedder.calls == ["<h1>위기 레포트</h1>"]


@pytest.mark.asyncio
async def test_to_document_without_embedder_keeps_legacy_behaviour():
    """U-11: 미주입(None)이면 기존 동작 그대로 — 하위 호환."""
    tool = _FakeTool("html_to_pdf")

    await _adapter([tool]).to_document("<h1>본문</h1>", "pdf", "mcp_x", "r-1")

    assert _sent_html(tool) == "<h1>본문</h1>"


@pytest.mark.asyncio
async def test_docx_output_is_not_font_embedded():
    """GAP-04: Word 는 CSS @font-face 로 폰트를 싣지 못한다.

    docx 에 base64 폰트를 붙여봐야 렌더링에 쓰이지 않고 페이로드만 커진다.
    """
    tool = _FakeTool("html_to_docx")
    embedder = _StubEmbedder()

    await _adapter([tool], embedder).to_document(
        "<h1>본문</h1>", "docx", "mcp_x", "r-1"
    )

    assert embedder.calls == []
    assert _sent_html(tool) == "<h1>본문</h1>"


@pytest.mark.asyncio
async def test_to_html_is_not_font_embedded():
    """U-12: 역방향 변환에는 폰트를 심지 않는다."""
    tool = _FakeTool("pdf_to_html")
    tool.ainvoke = _echo_html(tool)
    embedder = _StubEmbedder()

    await _adapter([tool], embedder).to_html(b"%PDF", "pdf", "mcp_x", "r-1")

    assert embedder.calls == []


@pytest.mark.asyncio
async def test_pptx_to_pdf_is_not_font_embedded():
    """U-12: PPTX 경로는 HTML 이 아니므로 대상이 아니다 (Plan §2.2)."""
    tool = _FakeTool("pptx_to_pdf")
    embedder = _StubEmbedder()

    await _adapter([tool], embedder).to_pdf_from_pptx(b"PK", "mcp_x", "r-1")

    assert embedder.calls == []


@pytest.mark.asyncio
async def test_embedder_failure_does_not_block_conversion():
    """FR-09: 임베더가 터져도 변환은 계속된다."""

    class _Boom:
        def wrap(self, html, request_id):
            raise RuntimeError("boom")

    tool = _FakeTool("html_to_pdf")

    result = await _adapter([tool], _Boom()).to_document(
        "<h1>본문</h1>", "pdf", "mcp_x", "r-1"
    )

    assert result == b"%PDF-fake"
    assert _sent_html(tool) == "<h1>본문</h1>"


def _echo_html(tool):
    async def ainvoke(payload):
        tool.payloads.append(payload)
        return json.dumps({"content": "<p>추출된 본문</p>"})

    return ainvoke
