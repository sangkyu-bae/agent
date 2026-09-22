"""McpActionExecutor — 승인된 MCP 도구의 실제 집행기.

Design Ref: approval-gate-phase2-mcp-executor §2.2, §6.

호출 코어로 MCPToolAdapter(워커 런타임 경로)가 아니라 MCPCallClient 를 쓴다
(D-01). 어댑터는 도구의 isError 를 무시하고 에러 텍스트를 정상 문자열로
돌려주기 때문에, 그 경로로 집행하면 "발송 실패" 가 executed 로 기록된다.

집행은 두 단계다 (D-02):
  list_tools — 읽기 전용. 여기서 실패하면 아무것도 보내지 않은 것이 확실하다.
  call_tool  — 1회. 여기서 예외가 나면 집행됐는지 알 수 없다.
이 경계 덕에 "미집행 확실" 과 "불명" 을 예외 타입 분류 없이 가른다.

예외를 밖으로 던지지 않는다 — DecideApprovalUseCase._execute_now 는 집행기
예외를 가두지 않는다 (Plan FR-05).
"""
import time
from collections.abc import Callable

from src.domain.approval.execution_policy import (
    ExecutionFailureKind,
    ExecutionFailurePolicy,
    McpArgumentPolicy,
)
from src.domain.approval.interfaces import ActionExecutorInterface, ExecutionResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.policy import MCPRetryPolicy
from src.domain.mcp.value_objects import MCPTimeoutConfig, MCPToolDescriptor
from src.domain.mcp_registry.schemas import MCPServerRegistration
from src.domain.tool_catalog.mcp_tool_id import McpToolRef, parse_mcp_tool_id
from src.infrastructure.mcp.call_client import MCPCallClient
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader

ClientFactory = Callable[[MCPServerRegistration], MCPCallClient]


def build_execution_client(
    registration: MCPServerRegistration,
    *,
    timeout: MCPTimeoutConfig,
    logger: LoggerInterface,
) -> MCPCallClient:
    """집행 전용 MCP client. 재시도는 0 으로 고정한다 (D-10, Plan FR-04).

    비가역 작업의 자동 재시도는 이중 집행이다. MCPCallClient 는 연결 단계
    실패를 항상 재시도 후보로 보므로 max_retries 자체를 0 으로 둔다.
    """
    return MCPCallClient(
        config=MCPToolLoader._build_config(registration),
        timeout=timeout,
        retry=MCPRetryPolicy(max_retries=0, retry_tool_execution=False),
        logger=logger,
    )


def _exception_name(exc: BaseException) -> str:
    """문구에 쓸 예외 타입명. 값(str(e))은 쓰지 않는다 (D-11).

    MCP SDK 는 anyio TaskGroup 안에서 돌아 실제 원인이 ExceptionGroup 으로
    감싸여 올라온다 — 그대로 쓰면 사람이 원인을 짐작할 수 없다. 첫 번째
    안쪽 예외까지 내려간다.
    """
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return type(exc).__name__


class McpActionExecutor(ActionExecutorInterface):
    """`mcp:{server_id}:{tool}` 도구를 서버 등록의 자격증명으로 1회 호출한다.

    발신 계정은 tool_id 가 가리키는 등록(= 에이전트 소유자의 것)이다 (D-08).
    등록은 집행 시점에 조회한다 — 자격증명을 approval 행에 복제하지 않는다.
    """

    def __init__(
        self,
        *,
        server_repo,
        client_factory: ClientFactory,
        max_output_chars: int,
        logger: LoggerInterface,
    ) -> None:
        # server_repo: find_by_id(server_id, request_id) 만 쓴다. 스케줄러
        # tick 에는 요청 세션이 없으므로 SessionScopedMcpServerRepository 를
        # 주입한다 (tool-and-mcp §3).
        self._server_repo = server_repo
        self._client_factory = client_factory
        self._max_output_chars = max_output_chars
        self._logger = logger

    def supports(self, tool_id: str) -> bool:
        return parse_mcp_tool_id(tool_id) is not None

    async def execute(
        self,
        *,
        tool_id: str,
        tool_args: dict,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> ExecutionResult:
        ref = parse_mcp_tool_id(tool_id)
        if ref is None:
            return self._fail("blocked", "MCP 도구 id 형식이 아님", tool_id, request_id)
        if ref.tool_name is None:
            # D-09: 서버만 가리키는 구형 id. 어떤 도구인지 추측하지 않는다.
            return self._fail(
                "blocked",
                "도구 이름이 없는 구형 id — 에이전트에서 도구를 다시 선택하세요",
                tool_id, request_id,
            )
        client, failure = await self._connect(ref, tool_id, request_id)
        if client is None:
            return failure
        descriptor, failure = await self._verify(client, ref, tool_id, request_id)
        if descriptor is None:
            return failure
        arguments = McpArgumentPolicy.with_idempotency_key(
            McpArgumentPolicy.unwrap(tool_args),
            descriptor.input_schema,
            idempotency_key,
        )
        return await self._call(client, ref, arguments, tool_id, request_id)

    async def _connect(
        self, ref: McpToolRef, tool_id: str, request_id: str
    ) -> tuple[MCPCallClient | None, ExecutionResult | None]:
        """①② 서버 등록 조회 → client 조립. 네트워크 호출 없음."""
        try:
            registration = await self._server_repo.find_by_id(
                ref.server_id, request_id
            )
        except Exception as e:
            return None, self._fail(
                "blocked", f"MCP 서버 등록 조회 실패 ({_exception_name(e)})",
                tool_id, request_id, exception=e,
            )
        if registration is None:
            return None, self._fail(
                "blocked", "MCP 서버 등록을 찾을 수 없음", tool_id, request_id
            )
        if not registration.is_active:
            return None, self._fail(
                "blocked", "MCP 서버가 비활성 상태", tool_id, request_id
            )
        # Check G1 (Design §6.2): config 조립(URL·헤더)도 네트워크 전 단계다.
        # 여기서 새면 Composite 가 '불명' 으로 기록해 경계가 역전된다.
        try:
            return self._client_factory(registration), None
        except Exception as e:
            return None, self._fail(
                "blocked", f"MCP 접속 설정 조립 실패 ({_exception_name(e)})",
                tool_id, request_id, exception=e,
            )

    async def _verify(
        self, client: MCPCallClient, ref: McpToolRef, tool_id: str, request_id: str
    ) -> tuple[MCPToolDescriptor | None, ExecutionResult | None]:
        """③ 읽기 전용 검증 — 연결·인증 확인 + 도구 존재 + input_schema 확보."""
        try:
            descriptors = await client.list_tools(request_id)
        except Exception as e:
            return None, self._fail(
                "blocked", f"MCP 서버 연결 실패 ({_exception_name(e)})",
                tool_id, request_id, exception=e,
            )
        for descriptor in descriptors:
            if descriptor.name == ref.tool_name:
                return descriptor, None
        return None, self._fail(
            "blocked", f"서버에 '{ref.tool_name}' 도구가 없음", tool_id, request_id
        )

    async def _call(
        self,
        client: MCPCallClient,
        ref: McpToolRef,
        arguments: dict,
        tool_id: str,
        request_id: str,
    ) -> ExecutionResult:
        """④ 실제 집행 — 정확히 1회."""
        # Design §7: 인자 값(메일 본문 등)은 남기지 않는다. 키 목록만.
        self._logger.info(
            "McpActionExecutor call start", request_id=request_id,
            tool_id=tool_id, server_id=ref.server_id, arg_keys=sorted(arguments),
        )
        started = time.perf_counter()
        try:
            result = await client.call_tool(
                name=ref.tool_name, arguments=arguments, request_id=request_id
            )
        except Exception as e:
            # Plan SC-7: 보냈을 수도 있다. 재호출하지 않고 사람에게 넘긴다.
            return self._fail(
                "unknown", f"호출 중 오류 ({_exception_name(e)})",
                tool_id, request_id, exception=e,
            )
        content = McpArgumentPolicy.truncate(result.content, self._max_output_chars)
        if result.is_error:
            return self._fail("tool_error", content, tool_id, request_id)
        self._logger.info(
            "McpActionExecutor call done", request_id=request_id,
            tool_id=tool_id, server_id=ref.server_id,
            output_chars=len(result.content),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return ExecutionResult(ok=True, output=content)

    def _fail(
        self,
        kind: ExecutionFailureKind,
        reason: str,
        tool_id: str,
        request_id: str,
        *,
        exception: Exception | None = None,
    ) -> ExecutionResult:
        """실패를 값으로 만든다.

        D-11: reason 에 str(e) 를 넣지 않는다 — streamable_http 는 api_key 가
        URL 쿼리에 실려 예외 문자열로 새어 나온다. 전체 예외는 로그로만 간다.
        tool_error 의 reason(도구 응답 본문)도 로그에는 남기지 않는다.
        """
        if exception is not None:
            self._logger.error(
                "McpActionExecutor failed", exception=exception,
                request_id=request_id, tool_id=tool_id, kind=kind,
            )
        else:
            self._logger.warning(
                "McpActionExecutor failed",
                request_id=request_id, tool_id=tool_id, kind=kind,
            )
        return ExecutionResult(
            ok=False, output="",
            error_message=ExecutionFailurePolicy.render(kind, reason),
        )
