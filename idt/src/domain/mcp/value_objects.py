"""MCP Domain Value Objects.

MCP(Model Context Protocol) 연결 설정 및 결과 값 객체를 정의합니다.
domain 레이어 — 외부 의존성 없음.
"""

from enum import Enum

from pydantic import BaseModel, Field


class MCPTransport(str, Enum):
    """MCP 연결 Transport 방식."""

    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"


class StdioServerConfig(BaseModel):
    """stdio Transport 서버 설정."""

    command: str = Field(description="실행할 명령어 (e.g. 'npx', 'python')")
    args: list[str] = Field(default_factory=list, description="명령어 인수")
    env: dict[str, str] | None = Field(default=None, description="환경변수")


class SSEServerConfig(BaseModel):
    """SSE(Server-Sent Events) Transport 서버 설정."""

    url: str = Field(description="MCP 서버 SSE 엔드포인트 URL")
    headers: dict[str, str] | None = Field(default=None, description="HTTP 헤더")
    timeout: float = Field(default=30.0, description="연결 타임아웃 (초)")


class WebSocketServerConfig(BaseModel):
    """WebSocket Transport 서버 설정."""

    url: str = Field(description="MCP 서버 WebSocket URL (ws:// 또는 wss://)")
    headers: dict[str, str] | None = Field(default=None, description="연결 헤더")
    timeout: float = Field(default=30.0, description="연결 타임아웃 (초)")


class MCPServerConfig(BaseModel):
    """MCP 서버 설정 (transport-agnostic).

    stdio / SSE / WebSocket 모두 지원하는 단일 설정 객체.
    transport 필드에 따라 해당하는 설정 필드를 사용한다.
    """

    name: str = Field(description="서버 식별 이름")
    transport: MCPTransport = Field(description="연결 방식")
    stdio: StdioServerConfig | None = Field(default=None)
    sse: SSEServerConfig | None = Field(default=None)
    websocket: WebSocketServerConfig | None = Field(default=None)

    def get_transport_config(
        self,
    ) -> StdioServerConfig | SSEServerConfig | WebSocketServerConfig:
        """Transport 방식에 맞는 설정을 반환한다.

        Returns:
            해당 transport의 설정 객체

        Raises:
            ValueError: 해당 transport 설정이 없을 때
        """
        if self.transport == MCPTransport.STDIO:
            if self.stdio is None:
                raise ValueError("stdio config is required for STDIO transport")
            return self.stdio
        elif self.transport == MCPTransport.SSE:
            if self.sse is None:
                raise ValueError("sse config is required for SSE transport")
            return self.sse
        else:
            if self.websocket is None:
                raise ValueError("websocket config is required for WEBSOCKET transport")
            return self.websocket


class MCPToolResult(BaseModel):
    """MCP Tool 실행 결과 Value Object."""

    tool_name: str = Field(description="실행된 Tool 이름")
    server_name: str = Field(description="Tool을 제공한 MCP 서버 이름")
    content: str = Field(description="실행 결과 텍스트")
    is_error: bool = Field(default=False, description="에러 여부")
    raw_result: dict | None = Field(default=None, description="원본 결과")
