"""SyncInternalToolsUseCase: TOOL_REGISTRY(코드) → tool_catalog 동기화.

내부 도구의 단일 진실원은 코드(`TOOL_REGISTRY`)다. 부팅 시 이 UseCase가
레지스트리를 tool_catalog에 upsert하여 UI 도구 목록(GET /tool-catalog)이
코드와 항상 일치하도록 한다. (V008 손수 시드의 드리프트 문제 해소.)

- tool_id는 `internal:{id}` 규약(프론트 DOCUMENT_EXTRACTOR_TOOL_ID 등과 일치).
- 레지스트리에서 사라진 internal 항목은 비활성화(is_active=False)한다.
- mcp 소스 항목은 건드리지 않는다(SyncMcpToolsUseCase 책임).
"""
import uuid

from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface

INTERNAL_PREFIX = "internal:"


class SyncInternalToolsUseCase:
    def __init__(
        self,
        repository: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, request_id: str) -> int:
        self._logger.info("SyncInternalToolsUseCase start", request_id=request_id)
        try:
            desired: set[str] = set()
            for meta in get_all_tools():
                tool_id = f"{INTERNAL_PREFIX}{meta.tool_id}"
                desired.add(tool_id)
                await self._repository.upsert_by_tool_id(
                    ToolCatalogEntry(
                        id=str(uuid.uuid4()),
                        tool_id=tool_id,
                        source="internal",
                        name=meta.name,
                        description=meta.description,
                        requires_env=list(meta.requires_env),
                        is_active=True,
                    ),
                    request_id,
                )

            deactivated = await self._deactivate_stale(desired, request_id)

            self._logger.info(
                "SyncInternalToolsUseCase done",
                request_id=request_id,
                synced=len(desired),
                deactivated=deactivated,
            )
            return len(desired)
        except Exception as e:
            self._logger.error(
                "SyncInternalToolsUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def _deactivate_stale(
        self, desired: set[str], request_id: str
    ) -> int:
        """레지스트리에서 사라진 active internal 항목을 비활성화."""
        active = await self._repository.list_active(request_id)
        count = 0
        for entry in active:
            if entry.source != "internal" or entry.tool_id in desired:
                continue
            await self._repository.upsert_by_tool_id(
                ToolCatalogEntry(
                    id=entry.id,
                    tool_id=entry.tool_id,
                    source="internal",
                    name=entry.name,
                    description=entry.description,
                    requires_env=list(entry.requires_env),
                    is_active=False,
                ),
                request_id,
            )
            count += 1
        return count
