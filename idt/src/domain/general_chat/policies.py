"""General Chat API 에이전트 동작 정책 상수.

환경변수 우선, 기본값 fallback (하드코딩 금지).
"""
from __future__ import annotations

import os


class ChatAgentPolicy:
    """ReAct 에이전트 동작 정책."""

    def __init__(self) -> None:
        self.MAX_ITERATIONS: int = int(os.getenv("CHAT_MAX_ITERATIONS", "10"))
        self.TOOL_TIMEOUT_SECONDS: int = 30
        self.MCP_CACHE_TTL_SECONDS: int = int(os.getenv("CHAT_MCP_CACHE_TTL", "600"))
        self.SUMMARIZATION_THRESHOLD: int = 6
        self.RECENT_TURNS_CONTEXT: int = 3
