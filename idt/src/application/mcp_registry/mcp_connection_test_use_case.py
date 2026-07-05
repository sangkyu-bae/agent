"""MCPConnectionTestUseCase: 등록된 MCP 서버 연결 테스트 (list_tools)."""
import time

from src.application.mcp_registry.schemas import MCPConnectionTestResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.infrastructure.mcp.call_client import MCPCallClient
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader

_SESSION_TERMINATED = "Session terminated"
_SESSION_TERMINATED_HINT = (
    "엔드포인트가 404를 반환했습니다(MCP 'Session terminated'). "
    "api_key 누락/오타 또는 URL 경로(/mcp)를 확인하세요."
)


def _walk_exceptions(exc: BaseException):
    """ExceptionGroup·__cause__·__context__를 모두 순회하며 예외를 yield한다."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        yield cur
        subs = getattr(cur, "exceptions", None)  # ExceptionGroup
        if subs:
            stack.extend(subs)
        if cur.__cause__ is not None:
            stack.append(cur.__cause__)
        if cur.__context__ is not None:
            stack.append(cur.__context__)


def _friendly_error(exc: BaseException) -> str:
    """transport 예외를 운영자 친화적 메시지로 변환한다.

    SDK가 404를 ExceptionGroup으로 감싼 McpError('Session terminated')로 올리므로
    중첩 예외를 순회해 탐지하고, 발견 시 원인 진단 힌트를 덧붙인다.
    """
    raw = str(exc)
    for inner in _walk_exceptions(exc):
        if _SESSION_TERMINATED in str(inner):
            return f"{_SESSION_TERMINATED_HINT} (원본: {raw})"
    return raw


class MCPConnectionTestUseCase:
    """저장된 MCP 서버에 실제 연결해 도구 목록을 조회한다.

    - 연결/조회 실패는 예외 대신 ok=False 응답으로 반환 (운영자 친화적).
    - 서버 미존재 시 None 반환 (라우터에서 404 매핑).
    - 런타임 도구 로드와 동일하게 transport별 config만으로 연결한다
      (auth는 streamable_http는 URL/headers, sse는 endpoint에 내장).
    """

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        logger: LoggerInterface,
    ):
        self._repo = repository
        self._logger = logger

    async def execute(
        self, id: str, request_id: str
    ) -> MCPConnectionTestResponse | None:
        registration = await self._repo.find_by_id(id, request_id)
        if registration is None:
            return None

        self._logger.info(
            "MCPConnectionTestUseCase start",
            request_id=request_id,
            server_id=id,
            transport=registration.transport.value,
        )

        config = MCPToolLoader._build_config(registration)
        client = MCPCallClient(config=config, logger=self._logger)

        started = time.perf_counter()
        try:
            descriptors = await client.list_tools(request_id)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._logger.info(
                "MCPConnectionTestUseCase done",
                request_id=request_id,
                server_id=id,
                tool_count=len(descriptors),
                elapsed_ms=elapsed_ms,
            )
            return MCPConnectionTestResponse(
                ok=True,
                tools=[
                    {"name": d.name, "description": d.description}
                    for d in descriptors
                ],
                elapsed_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._logger.error(
                "MCP connection test failed",
                request_id=request_id,
                server_id=id,
                exception=e,
            )
            return MCPConnectionTestResponse(
                ok=False, error=_friendly_error(e), elapsed_ms=elapsed_ms
            )
