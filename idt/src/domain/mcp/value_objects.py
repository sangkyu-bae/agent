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
    STREAMABLE_HTTP = "streamable_http"


class MCPTimeoutConfig(BaseModel):
    """세분화 타임아웃 설정 (초). 모두 양수여야 한다.

    connect: 연결/HTTP 요청 타임아웃
    read: SSE/스트림 읽기 타임아웃
    total: 단일 호출 전체 상한 (호출 코어에서 wait_for로 강제)
    """

    connect: float = Field(default=30.0, gt=0, description="연결/HTTP 요청 타임아웃")
    read: float = Field(default=300.0, gt=0, description="SSE/스트림 읽기 타임아웃")
    total: float = Field(default=300.0, gt=0, description="단일 호출 전체 상한")

    @classmethod
    def from_legacy(cls, timeout: float) -> "MCPTimeoutConfig":
        """SSEServerConfig.timeout 단일값을 connect로 매핑한다 (호환 규칙)."""
        return cls(connect=timeout)


class MCPAuthConfig(BaseModel):
    """인증 헤더 주입 설정 (Bearer 등)."""

    scheme: str = Field(default="Bearer", description="Authorization 스킴")
    token: str | None = Field(default=None, description="토큰 값")
    extra_headers: dict[str, str] = Field(
        default_factory=dict, description="추가 인증 헤더"
    )

    def to_headers(self) -> dict[str, str]:
        """주입할 헤더 dict를 생성한다. token이 있으면 Authorization을 구성한다."""
        headers = dict(self.extra_headers)
        if self.token:
            headers["Authorization"] = f"{self.scheme} {self.token}".strip()
        return headers


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


class StreamableHTTPServerConfig(BaseModel):
    """Streamable HTTP Transport 서버 설정."""

    url: str = Field(description="MCP 서버 Streamable HTTP 엔드포인트 URL")
    headers: dict[str, str] | None = Field(default=None, description="정적 HTTP 헤더")
    timeout: MCPTimeoutConfig | None = Field(
        default=None, description="세분화 타임아웃. None이면 기본값 사용"
    )


class MCPServerConfig(BaseModel):
    """MCP 서버 설정 (transport-agnostic).

    stdio / SSE / WebSocket / Streamable HTTP 모두 지원하는 단일 설정 객체.
    transport 필드에 따라 해당하는 설정 필드를 사용한다.
    """

    name: str = Field(description="서버 식별 이름")
    transport: MCPTransport = Field(description="연결 방식")
    stdio: StdioServerConfig | None = Field(default=None)
    sse: SSEServerConfig | None = Field(default=None)
    websocket: WebSocketServerConfig | None = Field(default=None)
    streamable_http: StreamableHTTPServerConfig | None = Field(default=None)

    def get_transport_config(
        self,
    ) -> (
        StdioServerConfig
        | SSEServerConfig
        | WebSocketServerConfig
        | StreamableHTTPServerConfig
    ):
        """Transport 방식에 맞는 설정을 반환한다.

        Returns:
            해당 transport의 설정 객체

        Raises:
            ValueError: 해당 transport 설정이 없을 때
        """
        config_map = {
            MCPTransport.STDIO: (self.stdio, "stdio"),
            MCPTransport.SSE: (self.sse, "sse"),
            MCPTransport.WEBSOCKET: (self.websocket, "websocket"),
            MCPTransport.STREAMABLE_HTTP: (self.streamable_http, "streamable_http"),
        }
        cfg, label = config_map[self.transport]
        if cfg is None:
            raise ValueError(
                f"{label} config is required for {self.transport.name} transport"
            )
        return cfg


class MCPToolDescriptor(BaseModel):
    """list_tools 결과 1건 (transport-agnostic, SDK 비노출 경량 VO)."""

    name: str = Field(description="Tool 이름 (원본)")
    description: str = Field(default="", description="Tool 설명")
    input_schema: dict = Field(
        default_factory=dict, description="JSON Schema (inputSchema)"
    )


class MCPToolResult(BaseModel):
    """MCP Tool 실행 결과 Value Object."""

    tool_name: str = Field(description="실행된 Tool 이름")
    server_name: str = Field(description="Tool을 제공한 MCP 서버 이름")
    content: str = Field(description="실행 결과 텍스트")
    is_error: bool = Field(default=False, description="에러 여부")
    raw_result: dict | None = Field(default=None, description="원본 결과")
