"""도구 ID 정규화 — 권한 규칙 키(카탈로그 표기)로 변환.

Design Ref: tool-access-control §3.2 — 규칙 키는 항상 카탈로그 표기다.
agent_tool 은 내부 도구를 `{id}`로, 카탈로그는 `internal:{id}`로 저장한다
(이중 네임스페이스, 위키 router-map). 판정 전에 이 함수 하나만 거친다.

레거시 서버 단위 참조(`mcp_{server}`)는 개별 도구를 특정하지 못하므로
None 을 돌려준다 — 서버 단위 판정은 ToolAccessSet.allowed_mcp_tool_names 가 맡는다.
"""
from src.domain.tool_catalog.mcp_tool_id import parse_mcp_tool_id

INTERNAL_PREFIX = "internal:"


def to_catalog_tool_id(raw_tool_id: str | None) -> str | None:
    """저장/요청 표기 → 카탈로그 표기. 해석할 수 없으면 None."""
    if not raw_tool_id:
        return None
    tool_id = raw_tool_id.strip()
    if not tool_id:
        return None

    ref = parse_mcp_tool_id(tool_id)
    if ref is not None:
        return None if ref.is_server_level else tool_id
    if tool_id.startswith("mcp:") or tool_id.startswith("mcp_"):
        # MCP 접두사지만 형식이 깨진 값 — 내부 도구로 오인하지 않는다.
        return None

    if tool_id.startswith(INTERNAL_PREFIX):
        name = tool_id[len(INTERNAL_PREFIX):]
        return tool_id if name else None
    if ":" in tool_id:
        return None
    return f"{INTERNAL_PREFIX}{tool_id}"
