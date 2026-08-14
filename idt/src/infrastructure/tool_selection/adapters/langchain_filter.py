"""LangChainToolFilter — Design Ref: §4.3.

``list[BaseTool] → list[BaseTool]``. 호출부는 이 한 줄만 추가하면 된다.

§6.1 #8 최후 방어선: 도구를 식별하지 못하거나 선별이 어떤 이유로든 실패하면
**입력을 그대로 돌려준다** — 즉 이 모듈이 없던 상태로 되돌아간다.
"""
import re
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_selection.interfaces.tool_selector_port import ToolSelectorPort
from src.domain.tool_selection.schemas import ToolCandidate, ToolSource

_MCP_RUNTIME_PREFIX = "mcp_"
"""`MCPServerConfig.name`은 사람이 읽는 이름이 아니라 저장 tool_id다.

`mcp_tool_loader.py:42`가 `name=registration.tool_id`(= ``mcp_{uuid}``)로 채운다.
DB의 `registration.name`("Doc Convert MCP")은 런타임 도구 객체까지 오지 않는다.
"""

_UUIDISH = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def _server_id(server_config: Any) -> str | None:
    """`MCPServerConfig` → 카탈로그 표기의 server_id.

    ``mcp_{uuid}``에서 접두어만 벗기면 되므로 저장소 조회가 필요 없다
    (Design §3.2 D-4 — 구현 중 실측으로 해소).
    """
    name = getattr(server_config, "name", None)
    if not isinstance(name, str) or not name:
        return None
    return name[len(_MCP_RUNTIME_PREFIX):] if name.startswith(
        _MCP_RUNTIME_PREFIX
    ) else name


def _server_label(server_config: Any) -> str | None:
    """설명 보강에 쓸 **사람이 읽는** 서버명. 런타임 UUID면 None.

    UUID를 그대로 쓰면 저신호 도구의 보강 문장이
    ``"6dd5c675-... 서버의 '...' 기능"``이 되어 노이즈만 늘어난다.
    """
    server_id = _server_id(server_config)
    if server_id is None or _UUIDISH.match(server_id):
        return None
    return server_id


@runtime_checkable
class ToolIdResolver(Protocol):
    """BaseTool → 도구 ID. 식별 불가 시 None.

    경로마다 ID 체계가 다를 수 있으므로 구현을 주입받는다 (§3.2).
    """

    def resolve(self, tool: Any) -> str | None: ...


class DefaultToolIdResolver:
    """MCP 어댑터는 duck typing으로, 나머지는 이름으로 식별한다.

    MCPToolAdapter를 import 하지 않는 이유: import 하는 순간 tool_selection이
    mcp 인프라에 묶여 탈부착 계약이 약해진다. ``server_config``/``mcp_tool_name``
    속성 유무만 본다.

    MCP id는 카탈로그와 같은 ``mcp:{server_id}:{mcp_tool_name}`` 형태다.
    server_id는 ``MCPServerConfig.name``(= ``mcp_{uuid}``)에서 접두어를 벗겨
    얻는다 — 저장소 조회가 필요 없다.
    """

    def resolve(self, tool: Any) -> str | None:
        server_config = getattr(tool, "server_config", None)
        mcp_tool_name = getattr(tool, "mcp_tool_name", None)
        if server_config is not None and mcp_tool_name:
            server_id = _server_id(server_config)
            if server_id:
                return f"mcp:{server_id}:{mcp_tool_name}"
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            return f"internal:{name}"
        return None


class LangChainToolFilter:
    """선별 결과로 BaseTool 목록을 좁힌다."""

    def __init__(
        self,
        selector: ToolSelectorPort,
        logger: LoggerInterface,
        resolver: ToolIdResolver | None = None,
    ) -> None:
        self._selector = selector
        self._logger = logger
        self._resolver = resolver or DefaultToolIdResolver()

    async def filter(
        self,
        tools: Sequence[Any],
        query: str,
        *,
        required_ids: Sequence[str] = (),
        request_id: str = "",
    ) -> list[Any]:
        """선별 후 도구 목록 반환. 어떤 실패에도 입력을 잃지 않는다."""
        if not tools:
            return list(tools)

        by_id = self._index(tools, request_id)
        if by_id is None:
            return list(tools)

        candidates = [self._to_candidate(tid, tool) for tid, tool in by_id.items()]
        try:
            result = await self._selector.select(
                query, candidates,
                required_ids=required_ids, request_id=request_id,
            )
        except Exception as exc:
            # Port 계약상 도달 불가. 계약이 깨져도 도구를 잃지 않는다.
            self._logger.warning(
                "Tool selector raised — falling back to full tool list",
                request_id=request_id, exception=exc,
            )
            return list(tools)

        selected = [by_id[tid] for tid in result.final_ids if tid in by_id]
        if not selected:
            self._logger.warning(
                "Tool selection produced nothing — falling back to full tool list",
                request_id=request_id, reason=result.reason,
            )
            return list(tools)
        return selected

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _index(
        self, tools: Sequence[Any], request_id: str
    ) -> dict[str, Any] | None:
        """``{tool_id: tool}``. 하나라도 식별 실패하면 None (§6.1 #8).

        일부만 식별되는 상태로 선별하면 식별 실패한 도구가 조용히 사라진다.
        회귀를 만드느니 선별을 포기하는 쪽이 안전하다.
        """
        by_id: dict[str, Any] = {}
        for tool in tools:
            tool_id = self._resolve_safely(tool, request_id)
            if tool_id is None or tool_id in by_id:
                self._logger.warning(
                    "Tool id unresolvable or duplicated — skipping tool selection",
                    request_id=request_id, tool_id=tool_id,
                    tool_type=type(tool).__name__,
                )
                return None
            by_id[tool_id] = tool
        return by_id

    def _resolve_safely(self, tool: Any, request_id: str) -> str | None:
        try:
            return self._resolver.resolve(tool)
        except Exception as exc:
            self._logger.warning(
                "Tool id resolver raised",
                request_id=request_id, exception=exc,
            )
            return None

    @staticmethod
    def _to_candidate(tool_id: str, tool: Any) -> ToolCandidate:
        """모델에 보일 형태로 정규화한다.

        MCP 도구의 ``tool.name``은 ``sanitize(f"{mcp_{uuid}}_{tool}")``라
        UUID 40자가 앞에 붙는다(`mcp/tool_registry.py:83-85`). 그대로 넘기면
        후보 목록이 UUID로 도배되어 선별 신호가 묻히므로 원본 도구명을 쓴다.
        """
        is_mcp = tool_id.startswith("mcp:")
        server_config = getattr(tool, "server_config", None)
        mcp_tool_name = getattr(tool, "mcp_tool_name", None)
        display_name = (
            mcp_tool_name
            if is_mcp and isinstance(mcp_tool_name, str) and mcp_tool_name
            else getattr(tool, "name", tool_id)
        )
        return ToolCandidate(
            tool_id=tool_id,
            name=str(display_name),
            description=str(getattr(tool, "description", "") or ""),
            source=ToolSource.MCP if is_mcp else ToolSource.INTERNAL,
            server_name=_server_label(server_config) if is_mcp else None,
        )
