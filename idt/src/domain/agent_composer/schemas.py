"""agent_composer 도메인 VO — 외부 의존 없음(순수 dataclass)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CandidateTool:
    """LLM 조합 후보 도구 메타.

    tool_id 형태:
    - 내부 도구: "excel_export" (TOOL_REGISTRY 키)
    - MCP 개별 도구(tool_catalog): "mcp:{server_id}:{tool_name}"
    - MCP 서버 단위 폴백(D2): "mcp_{server_id}"
    """

    tool_id: str
    name: str
    description: str
    source: str  # "internal" | "mcp"
    mcp_server_id: str | None = None
    server_level: bool = False


@dataclass(frozen=True)
class MissingCapability:
    """요청 역량 중 현재 도구로 커버할 수 없는 항목."""

    capability: str
    reason: str
    suggestion: str = ""


@dataclass(frozen=True)
class ComposedDraft:
    """초안 조립 결과 — 응답 조립의 입력."""

    coverage: str  # "full" | "partial" | "none"
    name_suggestion: str
    system_prompt: str
    workers: list  # list[WorkerDefinition]
    flow_hint: str
    missing_capabilities: list[MissingCapability] = field(default_factory=list)
    notes: str = ""
