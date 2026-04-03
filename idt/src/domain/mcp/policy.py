"""MCP Connection Policy.

MCP 서버 연결에 관한 도메인 규칙을 정의합니다.
domain 레이어 — 외부 의존성 없음.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.mcp.value_objects import MCPServerConfig


class MCPConnectionPolicy:
    """MCP 연결 정책."""

    MAX_SERVERS = 20
    MAX_TOOL_NAME_LENGTH = 100

    @staticmethod
    def validate_server_config(config: MCPServerConfig) -> bool:
        """서버 설정 유효성 검증.

        Args:
            config: MCP 서버 설정 객체

        Returns:
            유효하면 True, 그렇지 않으면 False
        """
        if not config.name or not config.name.strip():
            return False
        return True

    @staticmethod
    def validate_server_count(count: int) -> bool:
        """등록된 서버 수 제한 검증.

        Args:
            count: 등록하려는 서버 수

        Returns:
            허용 범위 내면 True
        """
        return count <= MCPConnectionPolicy.MAX_SERVERS

    @staticmethod
    def sanitize_tool_name(name: str) -> str:
        """Tool 이름을 LangChain 호환 형식으로 정규화한다.

        - 하이픈/공백 → 언더스코어
        - 소문자로 변환
        - MAX_TOOL_NAME_LENGTH 초과 시 잘라냄

        Args:
            name: 원본 Tool 이름

        Returns:
            정규화된 Tool 이름
        """
        sanitized = name.replace("-", "_").replace(" ", "_").lower()
        if len(sanitized) > MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH:
            sanitized = sanitized[: MCPConnectionPolicy.MAX_TOOL_NAME_LENGTH]
        return sanitized
