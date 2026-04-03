# Task: LangChain MCP 공통 클라이언트 모듈 (MCP Common Client)

> Task ID: MCP-001
> 의존성: LOG-001
> 최종 수정: 2026-03-14

---

## 1. 목적

- LangChain Agent에서 MCP(Model Context Protocol) 서버를 Tool로 호출하는 공통 레이어 구현
- stdio / SSE / WebSocket 세 가지 Transport 방식 모두 지원
- 특정 MCP 서버에 종속되지 않는 범용 어댑터 설계
- MCP 서버의 Tool 목록을 자동 발견하여 LangChain BaseTool로 래핑

---

## 2. 설계 원칙

### 2.1 아키텍처 레이어 배치

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `MCPConnectionPolicy`, `MCPToolResult`, `MCPServerConfig` | 연결 규칙, 결과 VO, 서버 설정 정의 |
| infrastructure | `MCPClientFactory`, `MCPToolAdapter`, `MCPToolRegistry` | MCP 클라이언트 연결, LangChain Tool 래핑, 서버 관리 |
| application | `MCPToolUseCase` | MCP Tool 실행 오케스트레이션 |

### 2.2 의존성

- LOG-001 (로깅 필수)
- `mcp>=1.0.0` (Python MCP SDK - Anthropic 공식)
- `langchain-mcp-adapters>=0.1.0` (LangChain MCP 어댑터)
- `langchain-core>=0.3.0` (BaseTool)

---

## 3. 도메인 설계

### 3.1 MCPServerConfig (Value Object)

```python
# domain/mcp/value_objects.py
from enum import Enum
from pydantic import BaseModel, Field


class MCPTransport(str, Enum):
    """MCP 연결 Transport 방식"""
    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"


class StdioServerConfig(BaseModel):
    """stdio Transport 서버 설정"""
    command: str = Field(description="실행할 명령어 (e.g. 'npx', 'python')")
    args: list[str] = Field(default_factory=list, description="명령어 인수")
    env: dict[str, str] | None = Field(default=None, description="환경변수")


class SSEServerConfig(BaseModel):
    """SSE Transport 서버 설정"""
    url: str = Field(description="MCP 서버 SSE 엔드포인트 URL")
    headers: dict[str, str] | None = Field(default=None, description="HTTP 헤더")
    timeout: float = Field(default=30.0, description="연결 타임아웃 (초)")


class WebSocketServerConfig(BaseModel):
    """WebSocket Transport 서버 설정"""
    url: str = Field(description="MCP 서버 WebSocket URL (ws:// 또는 wss://)")
    headers: dict[str, str] | None = Field(default=None, description="연결 헤더")
    timeout: float = Field(default=30.0, description="연결 타임아웃 (초)")


class MCPServerConfig(BaseModel):
    """MCP 서버 설정 (transport-agnostic)"""
    name: str = Field(description="서버 식별 이름")
    transport: MCPTransport = Field(description="연결 방식")
    stdio: StdioServerConfig | None = Field(default=None)
    sse: SSEServerConfig | None = Field(default=None)
    websocket: WebSocketServerConfig | None = Field(default=None)

    def get_transport_config(self) -> StdioServerConfig | SSEServerConfig | WebSocketServerConfig:
        """Transport 방식에 맞는 설정 반환"""
        if self.transport == MCPTransport.STDIO:
            if self.stdio is None:
                raise ValueError(f"stdio config is required for STDIO transport")
            return self.stdio
        elif self.transport == MCPTransport.SSE:
            if self.sse is None:
                raise ValueError(f"sse config is required for SSE transport")
            return self.sse
        else:
            if self.websocket is None:
                raise ValueError(f"websocket config is required for WEBSOCKET transport")
            return self.websocket


class MCPToolResult(BaseModel):
    """MCP Tool 실행 결과 VO"""
    tool_name: str = Field(description="실행된 Tool 이름")
    server_name: str = Field(description="Tool을 제공한 MCP 서버 이름")
    content: str = Field(description="실행 결과 텍스트")
    is_error: bool = Field(default=False, description="에러 여부")
    raw_result: dict | None = Field(default=None, description="원본 결과")
```

### 3.2 MCPConnectionPolicy (Domain Policy)

```python
# domain/mcp/policy.py

class MCPConnectionPolicy:
    """MCP 연결 정책"""

    MAX_SERVERS = 20
    MAX_TOOL_NAME_LENGTH = 100
    ALLOWED_TRANSPORTS = {"stdio", "sse", "websocket"}

    @staticmethod
    def validate_server_config(config: "MCPServerConfig") -> bool:
        """서버 설정 유효성 검증"""
        if not config.name or not config.name.strip():
            return False
        if config.transport.value not in MCPConnectionPolicy.ALLOWED_TRANSPORTS:
            return False
        return True

    @staticmethod
    def validate_server_count(count: int) -> bool:
        """등록된 서버 수 제한 검증"""
        return count <= MCPConnectionPolicy.MAX_SERVERS

    @staticmethod
    def sanitize_tool_name(name: str) -> str:
        """Tool 이름 정규화 (서버명 접두사 포함)"""
        sanitized = name.replace("-", "_").replace(" ", "_").lower()
        if len(sanitized) > MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH:
            sanitized = sanitized[:MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH]
        return sanitized
```

---

## 4. 인프라스트럭처 설계

### 4.1 MCPClientFactory

```python
# infrastructure/mcp/client_factory.py
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.sse import sse_client

from domain.mcp.value_objects import MCPServerConfig, MCPTransport
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MCPClientFactory:
    """
    MCP 서버 연결 팩토리

    Transport 방식에 따라 적절한 클라이언트 컨텍스트 매니저 반환
    """

    @staticmethod
    @asynccontextmanager
    async def create_session(
        config: MCPServerConfig,
        request_id: str | None = None,
    ) -> AsyncIterator[ClientSession]:
        """
        MCP 서버 세션 생성 (컨텍스트 매니저)

        Args:
            config: MCP 서버 설정
            request_id: 요청 추적 ID

        Yields:
            초기화된 ClientSession

        Raises:
            MCPConnectionError: 연결 실패 시
        """
        log_extra = {"request_id": request_id, "server": config.name, "transport": config.transport}

        logger.info("MCP session connecting", extra=log_extra)

        try:
            if config.transport == MCPTransport.STDIO:
                async with MCPClientFactory._stdio_session(config) as session:
                    logger.info("MCP session connected", extra=log_extra)
                    yield session

            elif config.transport == MCPTransport.SSE:
                async with MCPClientFactory._sse_session(config) as session:
                    logger.info("MCP session connected", extra=log_extra)
                    yield session

            elif config.transport == MCPTransport.WEBSOCKET:
                async with MCPClientFactory._websocket_session(config) as session:
                    logger.info("MCP session connected", extra=log_extra)
                    yield session

        except Exception as e:
            logger.error(
                "MCP session connection failed",
                extra=log_extra,
                exc_info=True,
            )
            raise

        finally:
            logger.info("MCP session closed", extra=log_extra)

    @staticmethod
    @asynccontextmanager
    async def _stdio_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
        stdio_config = config.stdio
        params = StdioServerParameters(
            command=stdio_config.command,
            args=stdio_config.args,
            env=stdio_config.env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    @asynccontextmanager
    async def _sse_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
        sse_config = config.sse
        headers = sse_config.headers or {}
        async with sse_client(
            url=sse_config.url,
            headers=headers,
            timeout=sse_config.timeout,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    @asynccontextmanager
    async def _websocket_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
        # websocket transport: mcp SDK websocket_client 또는 httpx websocket 사용
        from mcp.client.websocket import websocket_client

        ws_config = config.websocket
        async with websocket_client(url=ws_config.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
```

### 4.2 MCPToolAdapter (LangChain BaseTool Wrapper)

```python
# infrastructure/mcp/tool_adapter.py
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from domain.mcp.value_objects import MCPServerConfig, MCPToolResult
from infrastructure.mcp.client_factory import MCPClientFactory
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MCPToolInput(BaseModel):
    """MCP Tool 공통 입력 스키마"""
    arguments: dict = Field(default_factory=dict, description="Tool 실행 인수")


class MCPToolAdapter(BaseTool):
    """
    MCP Tool을 LangChain BaseTool로 래핑하는 어댑터

    하나의 MCP Tool을 하나의 LangChain Tool로 표현
    """

    name: str
    description: str
    args_schema: type[BaseModel] = MCPToolInput

    # MCP 관련 설정 (Pydantic v2 model_config arbitrary_types_allowed)
    server_config: MCPServerConfig
    mcp_tool_name: str  # 실제 MCP Tool 이름

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, arguments: dict | None = None) -> str:
        """동기 실행 (async 위임)"""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._arun(arguments=arguments or {})
        )

    async def _arun(self, arguments: dict | None = None) -> str:
        """
        MCP Tool 비동기 실행

        Args:
            arguments: Tool 실행 인수

        Returns:
            실행 결과 텍스트
        """
        args = arguments or {}
        log_extra = {
            "server": self.server_config.name,
            "tool": self.mcp_tool_name,
        }

        logger.info("MCP tool execution started", extra=log_extra)

        try:
            async with MCPClientFactory.create_session(self.server_config) as session:
                result = await session.call_tool(
                    name=self.mcp_tool_name,
                    arguments=args,
                )

            content = MCPToolAdapter._extract_content(result)

            logger.info("MCP tool execution completed", extra=log_extra)

            return content

        except Exception as e:
            logger.error(
                "MCP tool execution failed",
                extra=log_extra,
                exc_info=True,
            )
            raise

    @staticmethod
    def _extract_content(result) -> str:
        """MCP 결과에서 텍스트 콘텐츠 추출"""
        if hasattr(result, "content") and result.content:
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif hasattr(item, "data"):
                    parts.append(str(item.data))
            return "\n".join(parts) if parts else ""
        return str(result)
```

### 4.3 MCPToolRegistry (서버별 Tool 자동 발견 및 관리)

```python
# infrastructure/mcp/tool_registry.py
from langchain_core.tools import BaseTool

from domain.mcp.policy import MCPConnectionPolicy
from domain.mcp.value_objects import MCPServerConfig
from infrastructure.mcp.client_factory import MCPClientFactory
from infrastructure.mcp.tool_adapter import MCPToolAdapter
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MCPToolRegistry:
    """
    MCP 서버 Tool 레지스트리

    여러 MCP 서버에 연결하여 Tool 목록을 자동 발견하고
    LangChain BaseTool 목록으로 반환
    """

    def __init__(self, configs: list[MCPServerConfig]):
        """
        Args:
            configs: MCP 서버 설정 목록
        """
        if not MCPConnectionPolicy.validate_server_count(len(configs)):
            raise ValueError(
                f"Too many MCP servers: {len(configs)} > {MCPConnectionPolicy.MAX_SERVERS}"
            )
        self._configs = configs

    async def get_tools(self, request_id: str | None = None) -> list[BaseTool]:
        """
        모든 등록된 MCP 서버의 Tool 목록을 LangChain Tool로 반환

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
            extra={
                "request_id": request_id,
                "server_count": len(self._configs),
                "total_tools": len(all_tools),
            },
        )

        return all_tools

    async def _load_server_tools(
        self,
        config: MCPServerConfig,
        request_id: str | None,
    ) -> list[BaseTool]:
        """단일 MCP 서버의 Tool 목록 로드"""
        log_extra = {"request_id": request_id, "server": config.name}

        try:
            async with MCPClientFactory.create_session(config, request_id) as session:
                tools_response = await session.list_tools()

            tools = []
            for mcp_tool in tools_response.tools:
                tool_name = MCPConnectionPolicy.sanitize_tool_name(
                    f"{config.name}_{mcp_tool.name}"
                )
                adapter = MCPToolAdapter(
                    name=tool_name,
                    description=mcp_tool.description or f"MCP tool: {mcp_tool.name}",
                    server_config=config,
                    mcp_tool_name=mcp_tool.name,
                )
                tools.append(adapter)

            logger.info(
                "MCP server tools loaded",
                extra={**log_extra, "tool_count": len(tools)},
            )
            return tools

        except Exception as e:
            logger.error(
                "Failed to load MCP server tools",
                extra=log_extra,
                exc_info=True,
            )
            return []
```

---

## 5. Application 설계

### 5.1 MCPToolUseCase

```python
# application/mcp/use_case.py
from langchain_core.tools import BaseTool

from domain.mcp.policy import MCPConnectionPolicy
from domain.mcp.value_objects import MCPServerConfig
from infrastructure.mcp.tool_registry import MCPToolRegistry
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class MCPToolUseCase:
    """MCP Tool 유스케이스 - Agent에 MCP Tool 목록 제공"""

    def __init__(self, configs: list[MCPServerConfig]):
        self._registry = MCPToolRegistry(configs)

    async def get_tools_for_agent(self, request_id: str) -> list[BaseTool]:
        """
        LangGraph Agent에서 사용할 MCP Tool 목록 반환

        Args:
            request_id: 요청 추적 ID

        Returns:
            LangChain BaseTool 목록
        """
        logger.info(
            "Loading MCP tools for agent",
            extra={"request_id": request_id},
        )
        return await self._registry.get_tools(request_id)
```

---

## 6. 파일 구조

```
src/
├── domain/
│   └── mcp/
│       ├── __init__.py
│       ├── policy.py              # MCPConnectionPolicy
│       └── value_objects.py       # MCPServerConfig, MCPToolResult, MCPTransport
├── application/
│   └── mcp/
│       ├── __init__.py
│       └── use_case.py            # MCPToolUseCase
└── infrastructure/
    └── mcp/
        ├── __init__.py
        ├── client_factory.py      # MCPClientFactory (stdio/sse/websocket)
        ├── tool_adapter.py        # MCPToolAdapter (LangChain BaseTool 래퍼)
        └── tool_registry.py       # MCPToolRegistry (서버별 Tool 자동 발견)

tests/
├── domain/
│   └── mcp/
│       ├── test_policy.py
│       └── test_value_objects.py
├── infrastructure/
│   └── mcp/
│       ├── test_client_factory.py
│       ├── test_tool_adapter.py
│       └── test_tool_registry.py
└── application/
    └── mcp/
        └── test_use_case.py
```

---

## 7. 테스트 요구사항

### 7.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/mcp/test_policy.py
import pytest
from domain.mcp.policy import MCPConnectionPolicy
from domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig


class TestMCPConnectionPolicy:

    class TestValidateServerConfig:

        def test_returns_true_with_valid_stdio_config(self):
            # Given
            config = MCPServerConfig(
                name="filesystem",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem"]),
            )
            # When
            result = MCPConnectionPolicy.validate_server_config(config)
            # Then
            assert result is True

        def test_returns_false_with_empty_name(self):
            # Given
            config = MCPServerConfig(
                name="",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            # When
            result = MCPConnectionPolicy.validate_server_config(config)
            # Then
            assert result is False

    class TestSanitizeToolName:

        def test_replaces_hyphens_with_underscores(self):
            assert MCPConnectionPolicy.sanitize_tool_name("read-file") == "read_file"

        def test_lowercases_name(self):
            assert MCPConnectionPolicy.sanitize_tool_name("ReadFile") == "readfile"

        def test_truncates_long_name(self):
            long_name = "a" * 200
            result = MCPConnectionPolicy.sanitize_tool_name(long_name)
            assert len(result) <= MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH

    class TestValidateServerCount:

        def test_returns_true_within_limit(self):
            assert MCPConnectionPolicy.validate_server_count(10) is True

        def test_returns_false_exceeding_limit(self):
            assert MCPConnectionPolicy.validate_server_count(21) is False


# tests/domain/mcp/test_value_objects.py
class TestMCPServerConfig:

    def test_get_transport_config_returns_stdio_config(self):
        # Given
        config = MCPServerConfig(
            name="test",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="python", args=["server.py"]),
        )
        # When
        result = config.get_transport_config()
        # Then
        assert isinstance(result, StdioServerConfig)

    def test_get_transport_config_raises_when_config_missing(self):
        # Given
        config = MCPServerConfig(name="test", transport=MCPTransport.STDIO)
        # When & Then
        with pytest.raises(ValueError, match="stdio config is required"):
            config.get_transport_config()
```

### 7.2 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/mcp/test_tool_adapter.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
from infrastructure.mcp.tool_adapter import MCPToolAdapter


class TestMCPToolAdapter:

    @pytest.fixture
    def server_config(self):
        return MCPServerConfig(
            name="test_server",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="python", args=["server.py"]),
        )

    @pytest.fixture
    def adapter(self, server_config):
        return MCPToolAdapter(
            name="test_server_read_file",
            description="Read a file",
            server_config=server_config,
            mcp_tool_name="read_file",
        )

    @pytest.mark.asyncio
    async def test_arun_returns_content_on_success(self, adapter):
        # Given
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="file content")]

        mock_session = AsyncMock()
        mock_session.call_tool.return_value = mock_result

        with patch(
            "infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            # When
            result = await adapter._arun(arguments={"path": "/tmp/test.txt"})

        # Then
        assert result == "file content"
        mock_session.call_tool.assert_called_once_with(
            name="read_file",
            arguments={"path": "/tmp/test.txt"},
        )

    @pytest.mark.asyncio
    async def test_arun_raises_on_connection_error(self, adapter):
        # Given
        with patch(
            "infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            # When & Then
            with pytest.raises(ConnectionError):
                await adapter._arun()


# tests/infrastructure/mcp/test_tool_registry.py
class TestMCPToolRegistry:

    @pytest.fixture
    def configs(self):
        return [
            MCPServerConfig(
                name="server1",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=["server1"]),
            )
        ]

    @pytest.mark.asyncio
    async def test_get_tools_returns_langchain_tools(self, configs):
        # Given
        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        mock_tool.description = "Read a file"

        mock_session = AsyncMock()
        mock_session.list_tools.return_value = MagicMock(tools=[mock_tool])

        with patch(
            "infrastructure.mcp.tool_registry.MCPClientFactory.create_session"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

            registry = MCPToolRegistry(configs)
            tools = await registry.get_tools(request_id="req-001")

        # Then
        assert len(tools) == 1
        assert tools[0].name == "server1_read_file"

    def test_init_raises_when_too_many_servers(self):
        # Given
        configs = [
            MCPServerConfig(
                name=f"server{i}",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            for i in range(21)  # MAX_SERVERS + 1
        ]
        # When & Then
        with pytest.raises(ValueError, match="Too many MCP servers"):
            MCPToolRegistry(configs)
```

### 7.3 Application 테스트

```python
# tests/application/mcp/test_use_case.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
from application.mcp.use_case import MCPToolUseCase


class TestMCPToolUseCase:

    @pytest.fixture
    def configs(self):
        return [
            MCPServerConfig(
                name="filesystem",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                ),
            )
        ]

    @pytest.mark.asyncio
    async def test_get_tools_for_agent_returns_tools(self, configs):
        # Given
        mock_tool = MagicMock()
        use_case = MCPToolUseCase(configs)

        with patch.object(use_case._registry, "get_tools", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [mock_tool]

            # When
            tools = await use_case.get_tools_for_agent("req-001")

        # Then
        assert len(tools) == 1
        mock_get.assert_called_once_with("req-001")
```

---

## 8. 사용 예시

### 8.1 stdio 연결 (로컬 MCP 서버)

```python
from domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
from application.mcp.use_case import MCPToolUseCase

# 파일시스템 MCP 서버 설정
configs = [
    MCPServerConfig(
        name="filesystem",
        transport=MCPTransport.STDIO,
        stdio=StdioServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
        ),
    )
]

use_case = MCPToolUseCase(configs)
tools = await use_case.get_tools_for_agent(request_id="req-abc-123")

# LangGraph Agent에 Tool 전달
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(llm, tools)
```

### 8.2 SSE 연결 (원격 MCP 서버)

```python
from domain.mcp.value_objects import MCPServerConfig, MCPTransport, SSEServerConfig

config = MCPServerConfig(
    name="remote_api",
    transport=MCPTransport.SSE,
    sse=SSEServerConfig(
        url="http://mcp-server.internal:8080/sse",
        headers={"Authorization": "Bearer token"},
        timeout=30.0,
    ),
)
```

### 8.3 WebSocket 연결

```python
from domain.mcp.value_objects import MCPServerConfig, MCPTransport, WebSocketServerConfig

config = MCPServerConfig(
    name="realtime_db",
    transport=MCPTransport.WEBSOCKET,
    websocket=WebSocketServerConfig(
        url="wss://mcp-server.internal:8081/ws",
        timeout=30.0,
    ),
)
```

### 8.4 LangGraph Agent에서 통합 사용

```python
# application/workflows/research_workflow.py
from langgraph.prebuilt import create_react_agent
from application.mcp.use_case import MCPToolUseCase

class ResearchWorkflow:
    def __init__(self, llm, mcp_use_case: MCPToolUseCase):
        self._llm = llm
        self._mcp = mcp_use_case

    async def build_agent(self, request_id: str):
        tools = await self._mcp.get_tools_for_agent(request_id)
        return create_react_agent(self._llm, tools)
```

---

## 9. 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `stdio.command` | 필수 | 실행 명령어 |
| `stdio.args` | `[]` | 명령어 인수 |
| `sse.timeout` | `30.0` | SSE 연결 타임아웃 (초) |
| `websocket.timeout` | `30.0` | WebSocket 연결 타임아웃 (초) |

### Policy 상수

| 상수 | 값 | 설명 |
|------|-----|------|
| `MAX_SERVERS` | `20` | 최대 등록 서버 수 |
| `MAX_TOOL_NAME_LENGTH` | `100` | Tool 이름 최대 길이 |

---

## 10. 로깅 체크리스트 (LOG-001 준수)

- [ ] `get_logger(__name__)` 사용
- [ ] 세션 연결/종료 시 INFO 로그 (`server`, `transport` 포함)
- [ ] Tool 실행 시작/완료 INFO 로그 (`server`, `tool` 포함)
- [ ] 예외 발생 시 ERROR 로그 + `exc_info=True` (스택 트레이스)
- [ ] `request_id` 컨텍스트 전파
- [ ] API 키/토큰 등 민감 정보 로깅 금지

---

## 11. 금지 사항

- ❌ `print()` 사용 금지 (logger 필수)
- ❌ 스택 트레이스 없는 에러 로그 금지
- ❌ `request_id` 없는 로그 금지 (API 컨텍스트 내)
- ❌ MCP 서버 URL/토큰 하드코딩 금지 (환경변수 또는 설정 주입)
- ❌ domain 레이어에서 MCP SDK 직접 사용 금지

---

## 12. 의존성 패키지

```toml
# pyproject.toml 추가
"mcp>=1.0.0",
"langchain-mcp-adapters>=0.1.0",
```

---

## 13. CLAUDE.md Task Files Reference 추가

```markdown
| MCP-001 | src/claude/task/task-mcp-client.md | LangChain MCP 공통 클라이언트 모듈 |
```
