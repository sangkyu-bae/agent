"""MCP Tool Registry.

여러 MCP 서버에 연결하여 Tool 목록을 자동 발견하고
LangChain BaseTool 목록으로 반환한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from langchain_core.tools import BaseTool

from src.domain.mcp.policy import MCPConnectionPolicy
from src.domain.mcp.value_objects import MCPServerConfig
from src.infrastructure.logging import get_logger
from src.infrastructure.mcp.client_factory import HeaderProvider, MCPClientFactory
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

logger = get_logger(__name__)


def _as_schema_dict(raw) -> dict:
    """Design Ref: mcp-tool-category-routing module-2 —
    list_tools 응답의 inputSchema를 안전하게 dict로 정규화한다.

    MCP 서버는 스키마를 아예 주지 않을 수도, 규격 밖 형태로 줄 수도 있다.
    그대로 어댑터에 넘기면 pydantic 검증 실패로 해당 서버의 도구 로딩
    전체가 무너지므로, 알 수 없는 형태는 '스키마 미상'(빈 dict)으로 낮춘다.
    """
    return raw if isinstance(raw, dict) else {}


class MCPToolRegistry:
    """MCP 서버 Tool 레지스트리.

    등록된 MCP 서버들에서 Tool 목록을 자동 발견하고
    LangChain BaseTool 리스트로 반환한다.
    단일 서버 연결 실패 시 해당 서버를 건너뛰고 나머지를 계속 처리한다.
    """

    def __init__(
        self,
        configs: list[MCPServerConfig],
        header_providers: dict[str, HeaderProvider | None] | None = None,
    ) -> None:
        """초기화.

        Args:
            configs: MCP 서버 설정 목록
            header_providers: 서버 이름(config.name) → 호출 시점 헤더 공급자.
                도구 실행에만 쓰이고 list_tools 에는 쓰지 않는다
                (mcp-identity-header — 목록 조회는 신원 불필요).

        Raises:
            ValueError: 서버 수가 정책 상한을 초과하는 경우
        """
        if not MCPConnectionPolicy.validate_server_count(len(configs)):
            raise ValueError(
                f"Too many MCP servers: {len(configs)} > {MCPConnectionPolicy.MAX_SERVERS}"
            )
        self._configs = configs
        self._header_providers = header_providers or {}

    async def get_tools(self, request_id: str | None = None) -> list[BaseTool]:
        """모든 등록된 MCP 서버의 Tool 목록을 LangChain Tool로 반환한다.

        단일 서버 연결 실패는 경고 로그를 남기고 빈 리스트로 처리한다
        (전체 실패 방지).

        Args:
            request_id: 요청 추적 ID

        Returns:
            LangChain BaseTool 목록
        """
        all_tools: list[BaseTool] = []

        for config in self._configs:
            tools = await self._load_server_tools(config, request_id)
            all_tools.extend(tools)

        logger.info(
            "MCP tools loaded",
            request_id=request_id,
            server_count=len(self._configs),
            total_tools=len(all_tools),
        )

        return all_tools

    async def _load_server_tools(
        self,
        config: MCPServerConfig,
        request_id: str | None,
    ) -> list[BaseTool]:
        """단일 MCP 서버에서 Tool 목록을 로드한다."""
        log_extra = {"request_id": request_id, "server": config.name}

        try:
            async with MCPClientFactory.create_session(config, request_id) as session:
                tools_response = await session.list_tools()

            tools: list[BaseTool] = []
            for mcp_tool in tools_response.tools:
                # Design Ref: §3.2 — 단순 절단은 같은 서버 내 도구 이름 충돌을 만든다.
                tool_name = MCPConnectionPolicy.build_tool_name(
                    f"{config.name}_{mcp_tool.name}"
                )
                adapter = MCPToolAdapter(
                    name=tool_name,
                    description=mcp_tool.description or f"MCP tool: {mcp_tool.name}",
                    server_config=config,
                    mcp_tool_name=mcp_tool.name,
                    # Design Ref: mcp-tool-category-routing module-2 —
                    # 지금까지 버려지던 도구별 입력 스키마. collect 노드가
                    # 실제 인자 키를 알아야 추측 없이 호출할 수 있다.
                    # 스키마 미제공·비정형 응답은 빈 dict로 degrade한다.
                    # dict가 아닌 값을 그대로 넘기면 pydantic 검증에서 터져
                    # 그 서버의 도구 로딩 '전체'가 실패한다(§6.2 격리 철학 위배).
                    mcp_input_schema=_as_schema_dict(
                        getattr(mcp_tool, "inputSchema", None)
                    ),
                    # Design Ref: §4 — ③ 실행 로그가 요청/도구를 되짚을 수 있도록 전달.
                    request_id=request_id or "",
                    tool_id=config.name,
                    header_provider=self._header_providers.get(config.name),
                )
                tools.append(adapter)

            # Design Ref: §2.2 — tool_count=0 / 의도한 도구가 목록에 없음을
            # 여기서 바로 판별할 수 있어야 한다.
            logger.info(
                "MCP server tools loaded",
                tool_count=len(tools),
                tool_names=[t.mcp_tool_name for t in tools],
                **log_extra,
            )
            return tools

        except Exception as e:
            logger.error(
                "Failed to load MCP server tools",
                exception=e,
                **log_extra,
            )
            return []
