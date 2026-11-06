"""ListToolCatalogUseCase: 활성 도구 카탈로그 목록 조회."""
from typing import TYPE_CHECKING

from src.application.tool_catalog.schemas import ToolCatalogItemResponse, ToolCatalogListResponse
from src.domain.auth.entities import User
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface

if TYPE_CHECKING:
    from src.application.tool_access.resolver import ToolAccessResolver


class ListToolCatalogUseCase:
    def __init__(
        self,
        repository: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
        access_resolver: "ToolAccessResolver | None" = None,
    ) -> None:
        self._repository = repository
        self._logger = logger
        # Design Ref: tool-access-control §4.1 (Plan FR-05) — 비관리자는 허용 도구만.
        # 미주입 = 필터 없음(기존 동작). 프로덕션 주입은 배선 계약 테스트가 고정한다.
        self._access_resolver = access_resolver

    async def execute(
        self, request_id: str, viewer: User | None = None
    ) -> ToolCatalogListResponse:
        self._logger.info("ListToolCatalogUseCase start", request_id=request_id)
        try:
            entries = await self._repository.list_active(request_id)
            if self._access_resolver is not None:
                if viewer is None:
                    # Fail-Closed: 판정 배선이 있는데 조회자를 모르면 아무것도 보이지 않는다.
                    entries = []
                else:
                    access = await self._access_resolver.for_user(viewer, request_id)
                    entries = [e for e in entries if access.allows(e.tool_id)]
            self._logger.info(
                "ListToolCatalogUseCase done",
                request_id=request_id, count=len(entries),
            )
            return ToolCatalogListResponse(
                tools=[
                    ToolCatalogItemResponse(
                        tool_id=e.tool_id,
                        source=e.source,
                        name=e.name,
                        description=e.description,
                        mcp_server_id=e.mcp_server_id,
                        requires_env=e.requires_env,
                        is_builtin=e.is_builtin,
                        # mcp-tool-category-routing §4.1 (FR-13):
                        # 관리자 화면이 현재 분류·상한을 보고 고칠 수 있어야 한다.
                        category=e.category,
                        requires_approval=e.requires_approval,
                        max_tool_calls=e.max_tool_calls,
                    )
                    for e in entries
                ]
            )
        except Exception as e:
            self._logger.error(
                "ListToolCatalogUseCase failed", exception=e, request_id=request_id
            )
            raise
