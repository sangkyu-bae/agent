"""LangSmith infra 헬퍼 단위 테스트.

Design agent-run-langsmith-per-agent-project §3.1 / §4.1.
- normalize_agent_project_name: 정규화/fallback/절단
- make_agent_run_tracer: 키 없으면 None, 있으면 per-run LangChainTracer(project_name)
"""
import importlib

import pytest

from src.infrastructure.langsmith.langsmith import (
    normalize_agent_project_name,
    make_agent_run_tracer,
)


class TestNormalize:
    def test_basic(self) -> None:
        assert normalize_agent_project_name("여신심사봇") == "agent-여신심사봇"

    def test_collapses_whitespace(self) -> None:
        assert normalize_agent_project_name("  정책   FAQ  봇 ") == "agent-정책 FAQ 봇"

    def test_empty_and_none_fallback(self) -> None:
        assert normalize_agent_project_name("") == "agent-run"
        assert normalize_agent_project_name("   ") == "agent-run"
        assert normalize_agent_project_name(None) == "agent-run"

    def test_truncates_long(self) -> None:
        out = normalize_agent_project_name("가" * 300)
        assert len(out) <= 128
        assert out.startswith("agent-")


class TestMakeTracer:
    def test_none_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        assert make_agent_run_tracer("여신심사봇") is None

    def test_returns_tracer_with_project(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_dummy_key_for_test")
        tracer = make_agent_run_tracer("여신심사봇", tags=["agent-platform", "a-1"])
        assert tracer is not None
        assert tracer.project_name == "agent-여신심사봇"
