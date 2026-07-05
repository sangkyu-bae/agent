"""DocumentConversionAdapter 테스트 — MCP 도구 모의 (Design §3-3).

실측 계약(Doc Convert MCP, G3 PoC) 반영:
- 한 서버가 4개 도구 멀티플렉싱 → 방향별 이름(pdf_to_html/html_to_pdf 등)으로 선택.
- 호출: {"arguments": {"source": {kind,value,filename}, "output": {mode}}}
- 결과: JSON 문자열 {"format","output_mode":"base64","content":<base64>} 또는 dict/str.
"""
import base64
import json
from unittest.mock import MagicMock

import pytest

from src.domain.document_extractor.exceptions import McpConversionError
from src.infrastructure.document_extractor.document_conversion_adapter import (
    DocumentConversionAdapter,
)

SRV = "mcp_6dd5c675-dae8-454d-9cc0-7e8c71f46977"


class FakeTool:
    def __init__(self, name, result=None, error: Exception | None = None):
        self.name = name
        self._result = result
        self._error = error
        self.last_payload = None

    async def ainvoke(self, payload):
        self.last_payload = payload
        if self._error:
            raise self._error
        return self._result


class FakeLoader:
    def __init__(self, tools):
        self._tools = tools
        self.last_tool_id = None

    async def load_by_tool_id(self, tool_id, repository, request_id):
        self.last_tool_id = tool_id
        return self._tools


def _adapter(tools):
    loader = FakeLoader(tools)
    return (
        DocumentConversionAdapter(
            mcp_tool_loader=loader, mcp_repository=object(), logger=MagicMock()
        ),
        loader,
    )


def _multiplex_tools(html_result=None, file_result=None):
    """실서버처럼 4개 도구를 노출하는 목."""
    return [
        FakeTool(f"{SRV}_docx_to_html", result=html_result),
        FakeTool(f"{SRV}_pdf_to_html", result=html_result),
        FakeTool(f"{SRV}_html_to_pdf", result=file_result),
        FakeTool(f"{SRV}_html_to_docx", result=file_result),
    ]


def _json_content(fmt, content_bytes_or_text):
    if isinstance(content_bytes_or_text, bytes):
        content = base64.b64encode(content_bytes_or_text).decode("ascii")
    else:
        content = base64.b64encode(
            content_bytes_or_text.encode("utf-8")
        ).decode("ascii")
    return json.dumps(
        {"format": fmt, "output_mode": "base64", "content": content}
    )


class TestToolSelection:
    @pytest.mark.asyncio
    async def test_pdf_upload_selects_pdf_to_html(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<p>PDF본문</p>"))
        adapter, _ = _adapter(tools)
        html = await adapter.to_html(b"pdf", "pdf", SRV, "r")
        assert html == "<p>PDF본문</p>"
        # pdf_to_html이 호출됐는지(그 도구만 payload 수신)
        pdf_tool = next(t for t in tools if t.name.endswith("pdf_to_html"))
        assert pdf_tool.last_payload is not None
        docx_tool = next(t for t in tools if t.name.endswith("docx_to_html"))
        assert docx_tool.last_payload is None

    @pytest.mark.asyncio
    async def test_docx_upload_selects_docx_to_html(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<p>DOCX본문</p>"))
        adapter, _ = _adapter(tools)
        await adapter.to_html(b"docx", "docx", SRV, "r")
        docx_tool = next(t for t in tools if t.name.endswith("docx_to_html"))
        assert docx_tool.last_payload is not None

    @pytest.mark.asyncio
    async def test_output_pdf_selects_html_to_pdf(self):
        raw = b"%PDF-1.7 fake"
        tools = _multiplex_tools(file_result=_json_content("pdf", raw))
        adapter, _ = _adapter(tools)
        out = await adapter.to_document("<p>x</p>", "pdf", SRV, "r")
        assert out == raw
        pdf_tool = next(t for t in tools if t.name.endswith("html_to_pdf"))
        assert pdf_tool.last_payload is not None

    @pytest.mark.asyncio
    async def test_output_docx_selects_html_to_docx(self):
        raw = b"DOCXBYTES"
        tools = _multiplex_tools(file_result=_json_content("docx", raw))
        adapter, _ = _adapter(tools)
        out = await adapter.to_document("<p>x</p>", "docx", SRV, "r")
        assert out == raw

    @pytest.mark.asyncio
    async def test_direction_not_found_raises(self):
        # html_to_* 도구만 있고 pdf_to_html 없음
        tools = [
            FakeTool(f"{SRV}_html_to_pdf", result="x"),
            FakeTool(f"{SRV}_html_to_docx", result="x"),
        ]
        adapter, _ = _adapter(tools)
        with pytest.raises(McpConversionError, match="pdf_to_html"):
            await adapter.to_html(b"pdf", "pdf", SRV, "r")

    @pytest.mark.asyncio
    async def test_single_tool_server_used_directly(self):
        # 멀티플렉싱 아닌 단일 도구 서버는 이름 불일치여도 그대로 사용
        tools = [FakeTool("legacy_convert", result="<p>ok</p>")]
        adapter, _ = _adapter(tools)
        assert await adapter.to_html(b"x", "pdf", "mcp_single", "r") == "<p>ok</p>"


class TestPayloadContract:
    @pytest.mark.asyncio
    async def test_payload_is_arguments_wrapped_base64_source(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<p>ok</p>"))
        adapter, _ = _adapter(tools)
        await adapter.to_html(b"pdf-bytes", "pdf", SRV, "r")
        tool = next(t for t in tools if t.name.endswith("pdf_to_html"))
        args = tool.last_payload["arguments"]
        assert args["source"]["kind"] == "base64"
        assert base64.b64decode(args["source"]["value"]) == b"pdf-bytes"
        assert args["output"]["mode"] == "base64"


class TestOptionsAndWarnings:
    """D2: 변환 options 전달 + MCP metadata.warnings 로깅."""

    @pytest.mark.asyncio
    async def test_options_forwarded_in_arguments(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<p>ok</p>"))
        adapter, _ = _adapter(tools)
        await adapter.to_html(
            b"pdf", "pdf", SRV, "r", options={"mode": "layout", "dpi": 120}
        )
        tool = next(t for t in tools if t.name.endswith("pdf_to_html"))
        assert tool.last_payload["arguments"]["options"] == {
            "mode": "layout", "dpi": 120,
        }

    @pytest.mark.asyncio
    async def test_options_omitted_keeps_legacy_payload(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<p>ok</p>"))
        adapter, _ = _adapter(tools)
        await adapter.to_html(b"pdf", "pdf", SRV, "r")
        tool = next(t for t in tools if t.name.endswith("pdf_to_html"))
        assert "options" not in tool.last_payload["arguments"]

    @pytest.mark.asyncio
    async def test_flat_fallback_keeps_options(self):
        class WrapRejectingTool(FakeTool):
            """arguments 래퍼를 거부하고 평면 인자만 받는 서버 모의."""

            async def ainvoke(self, payload):
                if "arguments" in payload:
                    raise RuntimeError("unexpected key: arguments")
                return await super().ainvoke(payload)

        tools = [
            WrapRejectingTool(
                f"{SRV}_pdf_to_html", result=_json_content("html", "<p>ok</p>")
            )
        ]
        adapter, _ = _adapter(tools)
        await adapter.to_html(
            b"pdf", "pdf", SRV, "r", options={"mode": "layout", "dpi": 96}
        )
        assert tools[0].last_payload["options"] == {"mode": "layout", "dpi": 96}

    @pytest.mark.asyncio
    async def test_metadata_warnings_logged(self):
        result = json.dumps({
            "format": "html",
            "output_mode": "base64",
            "content": base64.b64encode("<p>ok</p>".encode()).decode("ascii"),
            "metadata": {"engine": "pymupdf-text", "warnings": ["lossy 변환"]},
        })
        tools = _multiplex_tools(html_result=result)
        adapter, _ = _adapter(tools)
        await adapter.to_html(b"pdf", "pdf", SRV, "r")
        logger = adapter._logger
        assert any(
            "lossy 변환" in str(c) for c in logger.warning.call_args_list
        )

    @pytest.mark.asyncio
    async def test_no_warnings_no_log(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<p>ok</p>"))
        adapter, _ = _adapter(tools)
        await adapter.to_html(b"pdf", "pdf", SRV, "r")
        adapter._logger.warning.assert_not_called()


class TestResultNormalization:
    @pytest.mark.asyncio
    async def test_json_string_base64_html_decoded(self):
        tools = _multiplex_tools(html_result=_json_content("html", "<h1>제목</h1>"))
        adapter, _ = _adapter(tools)
        assert await adapter.to_html(b"x", "pdf", SRV, "r") == "<h1>제목</h1>"

    @pytest.mark.asyncio
    async def test_plain_dict_html_key(self):
        tools = _multiplex_tools(html_result={"html": "<p>plain</p>"})
        adapter, _ = _adapter(tools)
        assert await adapter.to_html(b"x", "pdf", SRV, "r") == "<p>plain</p>"

    @pytest.mark.asyncio
    async def test_raw_string_html_passthrough(self):
        tools = _multiplex_tools(html_result="<p>raw</p>")
        adapter, _ = _adapter(tools)
        assert await adapter.to_html(b"x", "pdf", SRV, "r") == "<p>raw</p>"

    @pytest.mark.asyncio
    async def test_empty_result_rejected(self):
        tools = _multiplex_tools(html_result="   ")
        adapter, _ = _adapter(tools)
        with pytest.raises(McpConversionError):
            await adapter.to_html(b"x", "pdf", SRV, "r")


class TestErrors:
    @pytest.mark.asyncio
    async def test_tool_not_found_raises_with_hint(self):
        adapter, _ = _adapter([])
        with pytest.raises(McpConversionError, match="mcp_p2h"):
            await adapter.to_html(b"x", "pdf", "mcp_p2h", "r")

    @pytest.mark.asyncio
    async def test_invoke_failure_wrapped(self):
        # arguments-wrap + flat 폴백 모두 실패 → McpConversionError
        tools = _multiplex_tools()
        for t in tools:
            t._error = RuntimeError("Session terminated")
        adapter, _ = _adapter(tools)
        with pytest.raises(McpConversionError):
            await adapter.to_html(b"x", "pdf", SRV, "r")

    @pytest.mark.asyncio
    async def test_non_base64_file_result_rejected(self):
        tools = _multiplex_tools(
            file_result=json.dumps(
                {"format": "pdf", "output_mode": "base64", "content": "!!not b64!!"}
            )
        )
        adapter, _ = _adapter(tools)
        with pytest.raises(McpConversionError):
            await adapter.to_document("<p>x</p>", "pdf", SRV, "r")
