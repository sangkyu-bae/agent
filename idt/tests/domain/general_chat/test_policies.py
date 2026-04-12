"""Domain policy tests for general_chat — mock 금지."""
import os

import pytest

from src.domain.general_chat.policies import ChatAgentPolicy


def test_max_iterations_default():
    """TC-1: ChatAgentPolicy.MAX_ITERATIONS 기본값 = 10."""
    policy = ChatAgentPolicy()
    assert policy.MAX_ITERATIONS == 10


def test_max_iterations_env_override(monkeypatch):
    """TC-2: 환경변수 CHAT_MAX_ITERATIONS 오버라이드 — int 변환 정상."""
    monkeypatch.setenv("CHAT_MAX_ITERATIONS", "20")
    policy = ChatAgentPolicy()
    assert policy.MAX_ITERATIONS == 20


def test_mcp_cache_ttl_default():
    """TC-3: ChatAgentPolicy.MCP_CACHE_TTL_SECONDS 기본값 = 600."""
    policy = ChatAgentPolicy()
    assert policy.MCP_CACHE_TTL_SECONDS == 600


def test_summarization_threshold():
    """TC-4: SUMMARIZATION_THRESHOLD = 6."""
    policy = ChatAgentPolicy()
    assert policy.SUMMARIZATION_THRESHOLD == 6
