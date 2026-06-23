"""MCP Connection Policy.

MCP 서버 연결에 관한 도메인 규칙을 정의합니다.
domain 레이어 — 외부 의존성 없음.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

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


class MCPRetryPolicy(BaseModel):
    """재시도 + 지수 백오프 정책 (도메인 순수).

    기본은 연결 단계 한정 재시도. tool 실행 재시도는 비멱등 부작용 위험이 있어
    retry_tool_execution=False 기본 옵트인.
    """

    max_retries: int = Field(default=2, ge=0, description="추가 재시도 횟수")
    base_backoff: float = Field(default=0.5, gt=0, description="첫 재시도 대기(초)")
    factor: float = Field(default=2.0, ge=1.0, description="지수 증가 계수")
    max_backoff: float = Field(default=8.0, gt=0, description="대기 상한(초)")
    retry_tool_execution: bool = Field(
        default=False,
        description="True면 call_tool 실패도 재시도(멱등 도구 한정 옵트인)",
    )

    def compute_backoff(self, attempt: int) -> float:
        """attempt(0-base)에 대한 대기 시간을 계산한다. 단조 증가 + 상한 보장.

        Args:
            attempt: 재시도 시도 인덱스 (0부터)

        Returns:
            대기 시간(초), max_backoff 이하
        """
        delay = self.base_backoff * (self.factor**attempt)
        return min(delay, self.max_backoff)

    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        """예외의 재시도 가능 여부를 분류한다.

        연결/타임아웃/일시 네트워크 오류만 재시도 대상으로 본다.

        Args:
            exc: 발생한 예외

        Returns:
            재시도 가능하면 True
        """
        retryable = (ConnectionError, TimeoutError, asyncio.TimeoutError, OSError)
        return isinstance(exc, retryable)
