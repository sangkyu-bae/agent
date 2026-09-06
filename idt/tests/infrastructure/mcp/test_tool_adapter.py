"""MCPToolAdapter 테스트 — Mock 사용."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def stdio_server_config():
    from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
    return MCPServerConfig(
        name="test_server",
        transport=MCPTransport.STDIO,
        stdio=StdioServerConfig(command="python", args=["server.py"]),
    )


@pytest.fixture
def adapter(stdio_server_config):
    from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
    return MCPToolAdapter(
        name="test_server_read_file",
        description="Read a file from the filesystem",
        server_config=stdio_server_config,
        mcp_tool_name="read_file",
    )


class TestMCPToolAdapter:

    def test_adapter_is_langchain_base_tool(self, adapter):
        from langchain_core.tools import BaseTool
        assert isinstance(adapter, BaseTool)

    def test_adapter_name_set_correctly(self, adapter):
        assert adapter.name == "test_server_read_file"

    def test_adapter_description_set_correctly(self, adapter):
        assert "file" in adapter.description.lower()

    @pytest.mark.asyncio
    async def test_arun_returns_text_content_on_success(self, adapter):
        # Given
        mock_content_item = MagicMock()
        mock_content_item.text = "file content here"
        mock_result = MagicMock()
        mock_result.content = [mock_content_item]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            # When
            result = await adapter._arun(arguments={"path": "/tmp/test.txt"})

        # Then
        assert result == "file content here"
        mock_session.call_tool.assert_called_once_with(
            name="read_file",
            arguments={"path": "/tmp/test.txt"},
        )

    @pytest.mark.asyncio
    async def test_arun_with_no_arguments_passes_empty_dict(self, adapter):
        # Given
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="ok")]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun()

        mock_session.call_tool.assert_called_once_with(name="read_file", arguments={})

    @pytest.mark.asyncio
    async def test_arun_concatenates_multiple_content_items(self, adapter):
        # Given
        mock_result = MagicMock()
        mock_result.content = [
            MagicMock(text="line1"),
            MagicMock(text="line2"),
        ]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun()

        assert result == "line1\nline2"

    @pytest.mark.asyncio
    async def test_arun_raises_on_connection_error(self, adapter):
        # Given
        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            # When & Then
            with pytest.raises(ConnectionError):
                await adapter._arun()

    def test_extract_content_from_text_items(self):
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
        mock_item = MagicMock()
        mock_item.text = "hello"
        mock_result = MagicMock()
        mock_result.content = [mock_item]
        assert MCPToolAdapter._extract_content(mock_result) == "hello"

    def test_extract_content_returns_empty_string_when_no_content(self):
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
        mock_result = MagicMock()
        mock_result.content = []
        assert MCPToolAdapter._extract_content(mock_result) == ""


class TestMCPToolAdapterDiagnostics:
    """U15 — 실행 로그 계측 (Design Ref: fix-mcp-tool-call-not-reaching-server §4)."""

    def test_request_id_and_tool_id_default_to_empty(self, adapter):
        """미주입 시에도 어댑터 생성이 깨지지 않는다 (기존 호출부 하위호환)."""
        assert adapter.request_id == ""
        assert adapter.tool_id == ""

    @pytest.mark.asyncio
    async def test_arun_logs_carry_request_id_and_tool_id(self, stdio_server_config):
        """③ 실행 구간 로그에 request_id/tool_id가 실린다 (FR-01)."""
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(
            name="test_server_read_file",
            description="Read a file",
            server_config=stdio_server_config,
            mcp_tool_name="read_file",
            request_id="req-diag-001",
            tool_id="mcp:srv-uuid:read_file",
        )

        mock_item = MagicMock()
        mock_item.text = "ok"
        mock_result = MagicMock()
        mock_result.content = [mock_item]
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx, patch(
            "src.infrastructure.mcp.tool_adapter.logger"
        ) as mock_logger:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            await adapter._arun(arguments={})

        started = [c for c in mock_logger.info.call_args_list
                   if "execution started" in c.args[0]]
        assert started, "실행 시작 로그가 없다"
        kwargs = started[0].kwargs
        assert kwargs["request_id"] == "req-diag-001"
        assert kwargs["tool_id"] == "mcp:srv-uuid:read_file"
        assert kwargs["tool"] == "read_file"

    @pytest.mark.asyncio
    async def test_arun_failure_log_carries_request_id_and_tool_id(
        self, stdio_server_config
    ):
        """실패 경로에서도 추적 필드가 유지된다 (LOG-001: 스택 트레이스 동반)."""
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(
            name="test_server_read_file",
            description="Read a file",
            server_config=stdio_server_config,
            mcp_tool_name="read_file",
            request_id="req-diag-002",
            tool_id="mcp_srv-uuid",
        )

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx, patch(
            "src.infrastructure.mcp.tool_adapter.logger"
        ) as mock_logger:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=ConnectionError("boom")
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(ConnectionError):
                await adapter._arun()

        assert mock_logger.error.called
        kwargs = mock_logger.error.call_args.kwargs
        assert kwargs["request_id"] == "req-diag-002"
        assert kwargs["tool_id"] == "mcp_srv-uuid"
        assert "exception" in kwargs

    @pytest.mark.asyncio
    async def test_arun_passes_request_id_to_session_factory(self, stdio_server_config):
        """G-03: ③ 실행 경로의 세션 로그도 같은 request_id로 이어져야 한다."""
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(
            name="t", description="d",
            server_config=stdio_server_config, mcp_tool_name="read_file",
            request_id="req-chain-001", tool_id="mcp:srv:read_file",
        )
        mock_result = MagicMock()
        mock_result.content = []
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            await adapter._arun(arguments={})

        assert "req-chain-001" in mock_ctx.call_args.args, (
            "create_session에 request_id가 전달되지 않아 로그 체인이 끊긴다"
        )


class TestMCPToolAdapterInputSchemaPropagation:
    """Design Ref: mcp-tool-category-routing module-2 —

    어댑터의 args_schema는 모든 MCP 도구가 공유하는 제네릭 래퍼(MCPToolInput)라
    도구별 실제 입력 스키마를 담지 못한다. collect 노드가 올바른 인자를
    만들려면 서버가 준 inputSchema가 필요하므로 별도 필드로 보존한다.
    """

    def test_defaults_to_empty_schema(self, stdio_server_config):
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

        adapter = MCPToolAdapter(
            name="srv_scrape",
            description="d",
            server_config=stdio_server_config,
            mcp_tool_name="scrape",
        )
        assert adapter.mcp_input_schema == {}

    def test_carries_provided_schema(self, stdio_server_config):
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

        schema = {"type": "object", "properties": {"url": {"type": "string"}}}
        adapter = MCPToolAdapter(
            name="srv_scrape",
            description="d",
            server_config=stdio_server_config,
            mcp_tool_name="scrape",
            mcp_input_schema=schema,
        )
        assert adapter.mcp_input_schema == schema

    def test_generic_args_schema_is_unchanged(self):
        """react 경로 호환: args_schema 계약은 그대로 유지한다."""
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter, MCPToolInput

        assert MCPToolAdapter.model_fields["args_schema"].default is MCPToolInput
