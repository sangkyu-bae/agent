"""DocumentConversionAdapter: MCP pdf/doc↔html 변환 호출 래퍼 (Design §3-3).

MCP 서버는 보통 여러 변환 도구를 한 서버에 멀티플렉싱한다(pdf_to_html/docx_to_html/
html_to_pdf/html_to_docx). tool_id(mcp_{서버id})는 서버를 가리키므로, 이 어댑터가
방향(source/output 포맷)에 맞는 도구를 **이름으로 선택**하고 입출력을 정규화한다.

실측 계약(Doc Convert MCP, G3 PoC):
- 호출: tool.ainvoke({"arguments": {"source": {"kind":"base64","value":<b64>,
        "filename":<opt>}, "output": {"mode":"base64"}}})
- 결과: JSON 문자열 → {"format","output_mode","content"(=base64),"output_path","metadata"}
"""
import base64
import binascii
import json
from typing import Any

from src.domain.document_extractor.exceptions import McpConversionError
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# CC 메모리(mcp-session-terminated-means-404) 진단 힌트 재사용
_SESSION_TERMINATED_HINT = (
    "MCP 'Session terminated' 오류는 대부분 HTTP 404입니다 — "
    "서버 URL/api_key(빈 값 여부)를 확인하세요."
)

_HTML_DICT_KEYS = ("content", "html", "text", "result", "data")
_FILE_DICT_KEYS = ("content", "file_base64", "data", "result")


class DocumentConversionAdapter:
    """MCP 변환 도구 호출 + 방향별 도구 선택 + 응답 정규화."""

    def __init__(
        self, mcp_tool_loader, mcp_repository, logger: LoggerInterface
    ) -> None:
        self._loader = mcp_tool_loader
        self._repository = mcp_repository
        self._logger = logger

    async def to_html(
        self,
        file_bytes: bytes,
        source_format: str,
        mcp_tool_id: str,
        request_id: str,
        options: dict | None = None,
    ) -> str:
        """원본 문서(PDF/Word) → HTML. `{source_format}_to_html` 도구 선택.

        options: 변환 도구 옵션 (예: pdf_to_html {"mode": "layout", "dpi": 120}).
        """
        tool = await self._select_tool(
            mcp_tool_id, f"{source_format}_to_html", request_id
        )
        payload = self._build_payload(
            base64.b64encode(file_bytes).decode("ascii"),
            filename=f"source.{source_format}",
            options=options,
        )
        result = await self._invoke(tool, payload, mcp_tool_id, request_id)
        self._log_warnings(result, mcp_tool_id, request_id)
        html = self._normalize_html(result)
        if not html or not html.strip():
            raise McpConversionError(
                f"MCP 변환 결과가 비어 있습니다 (tool={mcp_tool_id}, {source_format}→html)"
            )
        return html

    async def to_document(
        self,
        html: str,
        output_format: str,
        mcp_tool_id: str,
        request_id: str,
    ) -> bytes:
        """채워진 HTML → PDF/Word 바이트. `html_to_{output_format}` 도구 선택."""
        tool = await self._select_tool(
            mcp_tool_id, f"html_to_{output_format}", request_id
        )
        payload = self._build_payload(
            base64.b64encode(html.encode("utf-8")).decode("ascii"),
            filename=f"filled.html",
        )
        result = await self._invoke(tool, payload, mcp_tool_id, request_id)
        self._log_warnings(result, mcp_tool_id, request_id)
        return self._normalize_file(result, mcp_tool_id)

    # ── 도구 선택 ────────────────────────────────────────────────────────
    async def _select_tool(
        self, mcp_tool_id: str, direction_suffix: str, request_id: str
    ):
        tools = await self._load_tools(mcp_tool_id, request_id)
        matched = [t for t in tools if getattr(t, "name", "").endswith(direction_suffix)]
        if matched:
            return matched[0]
        # 단일 도구 서버(멀티플렉싱 아님)면 그대로 사용.
        if len(tools) == 1:
            return tools[0]
        available = ", ".join(getattr(t, "name", "?") for t in tools)
        raise McpConversionError(
            f"'{direction_suffix}' 변환 도구를 MCP 서버에서 찾지 못했습니다 "
            f"(tool={mcp_tool_id}). 사용 가능: {available}"
        )

    async def _load_tools(self, mcp_tool_id: str, request_id: str) -> list:
        try:
            tools = await self._loader.load_by_tool_id(
                tool_id=mcp_tool_id,
                repository=self._repository,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "DocumentConversionAdapter tool load failed",
                exception=e,
                request_id=request_id,
                mcp_tool_id=mcp_tool_id,
            )
            raise McpConversionError(
                f"MCP 변환 도구 연결 실패: {mcp_tool_id}. {_SESSION_TERMINATED_HINT}"
            ) from e
        if not tools:
            raise McpConversionError(
                f"MCP 변환 도구를 찾을 수 없습니다: {mcp_tool_id}. "
                f"MCP 레지스트리에 pdf/doc↔html 변환 서버가 등록되어 있는지 확인하세요."
            )
        return tools

    # ── 호출/페이로드 ────────────────────────────────────────────────────
    @staticmethod
    def _build_payload(
        b64: str, filename: str, options: dict | None = None
    ) -> dict:
        """실측 계약: arguments 래퍼 + source(base64)/output(base64)[/options]."""
        arguments: dict = {
            "source": {"kind": "base64", "value": b64, "filename": filename},
            "output": {"mode": "base64"},
        }
        if options:
            arguments["options"] = options
        return {"arguments": arguments}

    def _log_warnings(self, result, mcp_tool_id: str, request_id: str) -> None:
        """MCP ConvertResult.metadata.warnings 로깅 (D2 — lossy 변환 가시화)."""
        payload = self._coerce_dict(result)
        if payload is None:
            return
        metadata = payload.get("metadata")
        warnings = metadata.get("warnings") if isinstance(metadata, dict) else None
        for warning in warnings or []:
            self._logger.warning(
                "MCP conversion warning",
                request_id=request_id,
                mcp_tool_id=mcp_tool_id,
                warning=str(warning),
            )

    async def _invoke(
        self, tool, payload: dict, mcp_tool_id: str, request_id: str
    ) -> Any:
        self._logger.info(
            "DocumentConversionAdapter invoke",
            request_id=request_id,
            mcp_tool_id=mcp_tool_id,
            tool=getattr(tool, "name", "?"),
        )
        try:
            return await tool.ainvoke(payload)
        except Exception as e:
            # 일부 서버는 arguments 래퍼 없이 평평한 인자를 받는다 — 1회 폴백.
            inner = payload.get("arguments")
            if isinstance(inner, dict):
                try:
                    return await tool.ainvoke(inner)
                except Exception:
                    pass
            self._logger.error(
                "DocumentConversionAdapter invoke failed",
                exception=e,
                request_id=request_id,
                mcp_tool_id=mcp_tool_id,
            )
            raise McpConversionError(
                f"MCP 변환 호출 실패 (tool={mcp_tool_id}): {e}. "
                f"{_SESSION_TERMINATED_HINT}"
            ) from e

    # ── 응답 정규화 ──────────────────────────────────────────────────────
    @classmethod
    def _normalize_html(cls, result: Any) -> str:
        payload = cls._coerce_dict(result)
        if payload is not None:
            content = cls._pick(payload, _HTML_DICT_KEYS)
            if isinstance(content, str) and content.strip():
                # output_mode=base64면 content는 HTML의 base64.
                if str(payload.get("output_mode", "")).lower() == "base64":
                    return cls._maybe_b64_to_text(content)
                return content
        if isinstance(result, str) and result.strip():
            return result  # 서버가 HTML 원문을 그대로 반환하는 경우
        if isinstance(result, list):
            parts = [
                b.get("text", "")
                for b in result
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            return "\n".join(p for p in parts if p)
        return ""

    @classmethod
    def _normalize_file(cls, result: Any, mcp_tool_id: str) -> bytes:
        payload = cls._coerce_dict(result)
        if payload is not None:
            content = cls._pick(payload, _FILE_DICT_KEYS)
            if isinstance(content, str) and content.strip():
                return cls._decode_base64(content, mcp_tool_id)
            if isinstance(content, (bytes, bytearray)):
                return bytes(content)
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        if isinstance(result, str) and result.strip():
            return cls._decode_base64(result, mcp_tool_id)
        raise McpConversionError(
            f"지원하지 않는 MCP 변환 응답 형식입니다 (tool={mcp_tool_id}): "
            f"{type(result).__name__}"
        )

    @staticmethod
    def _coerce_dict(result: Any) -> dict | None:
        """결과가 dict거나 JSON 문자열이면 dict로, 아니면 None."""
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            text = result.strip()
            if text.startswith("{"):
                try:
                    parsed = json.loads(text)
                    return parsed if isinstance(parsed, dict) else None
                except ValueError:
                    return None
        return None

    @staticmethod
    def _pick(payload: dict, keys: tuple[str, ...]):
        for key in keys:
            if key in payload and payload[key]:
                return payload[key]
        return None

    @staticmethod
    def _maybe_b64_to_text(value: str) -> str:
        try:
            return base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return value  # 이미 평문 HTML이면 그대로

    @staticmethod
    def _decode_base64(value: str, mcp_tool_id: str) -> bytes:
        try:
            return base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as e:
            raise McpConversionError(
                f"MCP 변환 응답을 파일로 해석할 수 없습니다 (tool={mcp_tool_id})"
            ) from e
