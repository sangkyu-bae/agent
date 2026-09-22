"""McpActionExecutor 단위 테스트.

Design Ref: approval-gate-phase2-mcp-executor §2.2, §6.1, §8.2 (E1~E17).

가짜 client 를 client_factory 로 주입한다 — 실제 MCP 연결 없이 "몇 번
호출했는가" 를 센다. 비가역 작업이라 호출 횟수 자체가 검증 대상이다.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.domain.mcp.value_objects import MCPToolDescriptor, MCPToolResult
from src.infrastructure.approval.mcp_executor import McpActionExecutor

SERVER_ID = "11111111-2222-3333-4444-555555555555"
TOOL_ID = f"mcp:{SERVER_ID}:send_email"
WRAPPED_ARGS = {"arguments": {"to": "a@b.c", "body": "비밀 본문"}}


def _registration(is_active: bool = True):
    return SimpleNamespace(id=SERVER_ID, is_active=is_active, name="my-mail")


def _descriptor(name: str = "send_email", with_key: bool = False):
    properties = {"to": {}, "body": {}}
    if with_key:
        properties["idempotency_key"] = {}
    return MCPToolDescriptor(
        name=name, input_schema={"type": "object", "properties": properties}
    )


def _result(content: str = "sent", is_error: bool = False):
    return MCPToolResult(
        tool_name="send_email", server_name="s", content=content, is_error=is_error
    )


def _build(
    *,
    registration=None,
    descriptors=None,
    call_result=None,
    list_error: Exception | None = None,
    call_error: Exception | None = None,
    max_output_chars: int = 1000,
):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=registration)
    client = MagicMock()
    client.list_tools = AsyncMock(
        return_value=descriptors if descriptors is not None else [_descriptor()],
        side_effect=list_error,
    )
    client.call_tool = AsyncMock(
        return_value=call_result or _result(), side_effect=call_error
    )
    factory = MagicMock(return_value=client)
    logger = MagicMock()
    executor = McpActionExecutor(
        server_repo=repo,
        client_factory=factory,
        max_output_chars=max_output_chars,
        logger=logger,
    )
    return executor, SimpleNamespace(
        repo=repo, client=client, factory=factory, logger=logger
    )


async def _run(executor, *, tool_id=TOOL_ID, tool_args=None, key=None):
    return await executor.execute(
        tool_id=tool_id,
        tool_args=WRAPPED_ARGS if tool_args is None else tool_args,
        request_id="req1",
        idempotency_key=key,
    )


class TestSupports:
    def test_mcp_형식만_받는다(self):
        executor, _ = _build()
        assert executor.supports(TOOL_ID) is True
        assert executor.supports(f"mcp_{SERVER_ID}") is True
        assert executor.supports("excel_export") is False
        assert executor.supports("internal:send_email") is False


class TestSuccess:
    async def test_검증_후_1회_호출하고_출력을_돌려준다(self):
        """Plan SC-1."""
        executor, m = _build(registration=_registration())
        result = await _run(executor)
        assert result.ok is True
        assert result.output == "sent"
        assert result.error_message is None
        assert m.client.list_tools.await_count == 1
        assert m.client.call_tool.await_count == 1

    async def test_서버_등록을_server_id로_조회한다(self):
        executor, m = _build(registration=_registration())
        await _run(executor)
        m.repo.find_by_id.assert_awaited_once_with(SERVER_ID, "req1")

    async def test_래퍼를_해제한_인자로_호출한다(self):
        executor, m = _build(registration=_registration())
        await _run(executor)
        kwargs = m.client.call_tool.await_args.kwargs
        assert kwargs["name"] == "send_email"
        assert kwargs["arguments"] == {"to": "a@b.c", "body": "비밀 본문"}

    async def test_출력이_상한을_넘으면_절단한다(self):
        executor, _ = _build(
            registration=_registration(),
            call_result=_result("x" * 500),
            max_output_chars=50,
        )
        result = await _run(executor)
        assert result.ok is True
        assert len(result.output) < 500
        assert "절단" in result.output


class TestIdempotencyKey:
    async def test_스키마에_있으면_주입한다(self):
        executor, m = _build(
            registration=_registration(), descriptors=[_descriptor(with_key=True)]
        )
        await _run(executor, key="idem-1")
        arguments = m.client.call_tool.await_args.kwargs["arguments"]
        assert arguments["idempotency_key"] == "idem-1"

    async def test_스키마에_없으면_주입하지_않는다(self):
        executor, m = _build(registration=_registration())
        await _run(executor, key="idem-1")
        arguments = m.client.call_tool.await_args.kwargs["arguments"]
        assert "idempotency_key" not in arguments


class TestBlocked:
    """Plan SC-3 — 어느 경우든 call_tool 은 0회."""

    async def _assert_blocked(self, executor, m, *, list_calls: int, **run_kwargs):
        result = await _run(executor, **run_kwargs)
        assert result.ok is False
        assert result.error_message.startswith("[집행 불가]")
        assert m.client.list_tools.await_count == list_calls
        assert m.client.call_tool.await_count == 0
        return result

    async def test_mcp_형식이_아닌_id(self):
        executor, m = _build(registration=_registration())
        await self._assert_blocked(executor, m, list_calls=0, tool_id="excel_export")
        m.repo.find_by_id.assert_not_awaited()

    async def test_도구_이름이_없는_레거시_id(self):
        """D-09 — 추측 호출하지 않는다."""
        executor, m = _build(registration=_registration())
        result = await self._assert_blocked(
            executor, m, list_calls=0, tool_id=f"mcp_{SERVER_ID}"
        )
        assert "다시 선택" in result.error_message
        m.repo.find_by_id.assert_not_awaited()

    async def test_서버_등록이_없다(self):
        executor, m = _build(registration=None)
        result = await self._assert_blocked(executor, m, list_calls=0)
        assert "찾을 수 없음" in result.error_message
        m.factory.assert_not_called()

    async def test_서버가_비활성이다(self):
        executor, m = _build(registration=_registration(is_active=False))
        result = await self._assert_blocked(executor, m, list_calls=0)
        assert "비활성" in result.error_message
        m.factory.assert_not_called()

    async def test_등록_조회가_예외를_던진다(self):
        executor, m = _build()
        m.repo.find_by_id = AsyncMock(side_effect=RuntimeError("db down"))
        await self._assert_blocked(executor, m, list_calls=0)

    async def test_client_조립이_실패한다(self):
        """Check G1 — Design §6.2. 네트워크 호출 전이므로 '불명' 이 아니라 '불가'."""
        executor, m = _build(registration=_registration())
        m.factory.side_effect = ValueError("https://h/mcp?api_key=SECRET123")
        result = await self._assert_blocked(executor, m, list_calls=0)
        assert "ValueError" in result.error_message
        assert "SECRET123" not in result.error_message

    async def test_list_tools가_실패한다(self):
        executor, m = _build(
            registration=_registration(), list_error=ConnectionError("refused")
        )
        result = await self._assert_blocked(executor, m, list_calls=1)
        assert "ConnectionError" in result.error_message

    async def test_예외_그룹은_안쪽_예외_타입으로_알린다(self):
        """anyio TaskGroup 이 실제 원인을 ExceptionGroup 으로 감싼다."""
        group = ExceptionGroup("tg", [ExceptionGroup("inner", [KeyError("x")])])
        executor, m = _build(registration=_registration(), list_error=group)
        result = await self._assert_blocked(executor, m, list_calls=1)
        assert "KeyError" in result.error_message
        assert "ExceptionGroup" not in result.error_message

    async def test_서버에_그_도구가_없다(self):
        executor, m = _build(
            registration=_registration(), descriptors=[_descriptor("other_tool")]
        )
        result = await self._assert_blocked(executor, m, list_calls=1)
        assert "send_email" in result.error_message


class TestUnknown:
    async def test_타임아웃은_불명이고_재호출하지_않는다(self):
        """Plan SC-7 / FR-04 — 비가역 작업의 재시도는 이중 집행이다."""
        executor, m = _build(registration=_registration(), call_error=TimeoutError())
        result = await _run(executor)
        assert result.ok is False
        assert result.error_message.startswith("[집행 여부 불명]")
        assert "TimeoutError" in result.error_message
        assert m.client.call_tool.await_count == 1

    async def test_임의_예외도_전파하지_않는다(self):
        """FR-05 — decide_use_case._execute_now 는 예외를 가두지 않는다."""
        executor, m = _build(
            registration=_registration(), call_error=RuntimeError("boom")
        )
        result = await _run(executor)
        assert result.ok is False
        assert result.error_message.startswith("[집행 여부 불명]")
        assert m.client.call_tool.await_count == 1


class TestToolError:
    async def test_is_error는_실패로_기록한다(self):
        """D-01 — 어댑터 경로는 이것을 성공 문자열로 돌려줬다."""
        executor, m = _build(
            registration=_registration(),
            call_result=_result("quota exceeded", is_error=True),
        )
        result = await _run(executor)
        assert result.ok is False
        assert result.error_message.startswith("[도구 실패]")
        assert "quota exceeded" in result.error_message
        assert m.client.call_tool.await_count == 1

    async def test_도구_메시지도_상한으로_절단한다(self):
        executor, _ = _build(
            registration=_registration(),
            call_result=_result("e" * 500, is_error=True),
            max_output_chars=50,
        )
        result = await _run(executor)
        assert len(result.error_message) < 200


class TestSecretsAndPii:
    async def test_예외_문자열의_시크릿이_문구에_들어가지_않는다(self):
        """D-11 — streamable_http 는 api_key 가 URL 쿼리에 실린다."""
        leak = "GET https://host/mcp?api_key=SECRET123 failed"
        for kwargs in ({"list_error": ConnectionError(leak)},
                       {"call_error": RuntimeError(leak)}):
            executor, _ = _build(registration=_registration(), **kwargs)
            result = await _run(executor)
            assert "SECRET123" not in result.error_message
            assert "api_key" not in result.error_message

    async def test_인자_값은_로그에_남기지_않는다(self):
        """Design §7 — 메일 본문 등 PII. 키 목록만 남긴다."""
        executor, m = _build(registration=_registration())
        await _run(executor)
        logged = repr(m.logger.mock_calls)
        assert "비밀 본문" not in logged
        assert "a@b.c" not in logged
        assert "arg_keys" in logged

    async def test_성공_로그에_소요시간이_있다(self):
        """Check G2 — §10.4 / §6.3 잠금 유지 시간 관찰 지표."""
        executor, m = _build(registration=_registration())
        await _run(executor)
        done = [c for c in m.logger.info.call_args_list
                if c.args and c.args[0] == "McpActionExecutor call done"]
        assert done and "elapsed_ms" in done[0].kwargs

    async def test_실패는_예외와_함께_error로_로깅한다(self):
        error = RuntimeError("boom")
        executor, m = _build(registration=_registration(), call_error=error)
        await _run(executor)
        assert m.logger.error.call_args.kwargs["exception"] is error


class TestBuildExecutionClient:
    def test_재시도는_0으로_고정된다(self):
        """D-10 — 켜면 안 되는 값이라 설정으로 열어두지 않는다."""
        from src.domain.mcp_registry.schemas import (
            MCPServerRegistration,
            MCPTransportType,
        )
        from src.domain.mcp.value_objects import MCPTimeoutConfig
        from src.infrastructure.approval.mcp_executor import build_execution_client
        from datetime import datetime

        now = datetime(2026, 9, 21)
        registration = MCPServerRegistration(
            id=SERVER_ID, user_id="7", name="my-mail", description="d",
            endpoint="http://localhost:9/sse", transport=MCPTransportType.SSE,
            input_schema=None, is_active=True, created_at=now, updated_at=now,
        )
        timeout = MCPTimeoutConfig(connect=1, read=2, total=2)
        client = build_execution_client(
            registration, timeout=timeout, logger=MagicMock()
        )
        assert client._retry.max_retries == 0
        assert client._retry.retry_tool_execution is False
        assert client._timeout.total == 2
