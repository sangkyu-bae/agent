"""ToolCatalog 애플리케이션 레이어 스키마."""
from pydantic import BaseModel, Field


class ToolCatalogItemResponse(BaseModel):
    tool_id: str
    source: str
    name: str
    description: str
    mcp_server_id: str | None = None
    requires_env: list[str] = []
    # builtin-tools D4: 에이전트 생성 시 자동 주입되는 빌트인 여부
    is_builtin: bool = False
    # mcp-tool-category-routing §4.1 (FR-13): 워커 노드 분류·호출 상한.
    # None = 미분류 → 기존 react 경로 (FR-14). 필드 추가만이므로 기존 소비자 무영향.
    category: str | None = None
    max_tool_calls: int | None = None
    # approval-gate Check G2: 관리자 화면이 현재 상태를 그리려면 필요하다.
    requires_approval: bool = False


class ToolCatalogListResponse(BaseModel):
    tools: list[ToolCatalogItemResponse]


class SyncMcpToolsRequest(BaseModel):
    mcp_server_id: str | None = None


class SetBuiltinRequest(BaseModel):
    """builtin-tools D3: 빌트인 토글 요청 (tool_id는 카탈로그 형식)."""

    tool_id: str
    is_builtin: bool


class SetBuiltinResponse(BaseModel):
    tool_id: str
    is_builtin: bool


class ToolMetadataRequest(BaseModel):
    """mcp-tool-category-routing §4.2: 분류·호출 상한 부분 갱신 요청.

    tool_id를 body로 받는 이유는 SetBuiltinRequest와 같다 — 카탈로그 형식
    (mcp:{uuid}:{tool})이 콜론·임의 도구명을 포함해 path 세그먼트로 부적합하다.

    부분 갱신: 필드를 **생략**하면 그 컬럼을 건드리지 않고, 명시적 null은
    '미분류/기본값으로 되돌리기'다. 라우터가 model_fields_set으로 둘을 가른다.
    """

    tool_id: str
    category: str | None = Field(
        default=None,
        description="search/collect/analysis/action 또는 null(미분류)",
    )
    max_tool_calls: int | None = Field(
        default=None, description="워커 1회 실행당 도구 호출 상한. null이면 기본값",
    )
    # approval-gate Check G2: 생략하면 미변경. null 은 유스케이스가 400 으로 거부.
    requires_approval: bool | None = Field(
        default=None, description="true 면 이 도구 호출 전 사람 승인 필요",
    )


class ToolMetadataResponse(BaseModel):
    tool_id: str
    category: str | None = None
    max_tool_calls: int | None = None
    requires_approval: bool = False
