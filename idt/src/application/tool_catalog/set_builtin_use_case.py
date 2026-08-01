"""SetBuiltinToolUseCase: 빌트인 도구 등록/해제 (관리자 전용, builtin-tools D3).

런타임 SoT인 tool_catalog.is_builtin을 토글한다. 비활성 도구도 플래그 지정을
허용한다 — 에이전트 생성 주입은 list_builtin(active 필터)이 방어한다(D5).
"""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class SetBuiltinToolUseCase:
    def __init__(
        self,
        repository: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, tool_id: str, is_builtin: bool, request_id: str
    ) -> ToolCatalogEntry:
        self._logger.info(
            "SetBuiltinToolUseCase start",
            request_id=request_id, tool_id=tool_id, is_builtin=is_builtin,
        )
        try:
            existing = await self._repository.find_by_tool_id(tool_id, request_id)
            if existing is None:
                raise ValueError(f"Unknown catalog tool_id: {tool_id!r}")
            updated = await self._repository.set_builtin(
                tool_id, is_builtin, request_id
            )
            if updated is None:
                raise ValueError(f"Unknown catalog tool_id: {tool_id!r}")
            self._logger.info(
                "SetBuiltinToolUseCase done",
                request_id=request_id, tool_id=tool_id, is_builtin=updated.is_builtin,
            )
            return updated
        except Exception as e:
            self._logger.error(
                "SetBuiltinToolUseCase failed", exception=e, request_id=request_id
            )
            raise
