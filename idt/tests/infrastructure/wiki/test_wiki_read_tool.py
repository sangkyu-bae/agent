"""Infrastructure 테스트: WikiReadTool (wiki-agentic-navigation FR-02/FR-05).

- RunContext agent_id 격리: 컨텍스트 없으면 세션조차 열지 않고 실패 텍스트
- 가드 실패(UseCase None)와 성공 렌더링
- BaseTool 규약: name/args_schema(article_id) — UsageCallback on_tool_start
  자동 기록(FR-05)의 전제
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.infrastructure.wiki.wiki_read_tool import FAIL_TEXT, WikiReadTool

NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _article(id="w1", agent_id="agent_1", path="여신/한도") -> WikiArticle:
    return WikiArticle(
        id=id, agent_id=agent_id, title="한도 산정 기준", content="본문 텍스트입니다.",
        source_type=WikiSourceType.HUMAN, source_refs=["human:1"],
        status=WikiStatus.APPROVED, confidence=0.9, path=path,
        updated_at=NOW,
    )


class _SessionCtx:
    def __init__(self, counter):
        self._counter = counter

    async def __aenter__(self):
        self._counter["opened"] += 1
        return MagicMock()

    async def __aexit__(self, *a):
        self._counter["closed"] += 1
        return False


def _make_tool(found: WikiArticle | None):
    counter = {"opened": 0, "closed": 0}

    def session_factory():
        return _SessionCtx(counter)

    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=found)

    def repo_builder(session):
        return repo

    tool = WikiReadTool(
        session_factory=session_factory,
        repo_builder=repo_builder,
        request_id="r",
        logger=MagicMock(),
    )
    return tool, repo, counter


def _set_ctx(agent_id="agent_1"):
    return set_current_run_context(RunContext(
        run_id=MagicMock(), user_id="u", agent_id=agent_id, callback=MagicMock(),
    ))


class TestToolContract:

    def test_is_base_tool_named_wiki_read(self):
        tool, _, _ = _make_tool(found=None)
        assert isinstance(tool, BaseTool)
        assert tool.name == "wiki_read"

    def test_args_schema_has_article_id(self):
        tool, _, _ = _make_tool(found=None)
        assert "article_id" in tool.args_schema.model_fields


class TestNoContext:

    @pytest.mark.asyncio
    async def test_no_run_context_fails_without_session(self):
        tool, repo, counter = _make_tool(found=_article())
        result = await tool._arun("w1")
        assert result == FAIL_TEXT
        assert counter["opened"] == 0
        repo.find_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_agent_id_fails(self):
        tool, _, counter = _make_tool(found=_article())
        token = _set_ctx("")
        try:
            result = await tool._arun("w1")
        finally:
            reset_run_context(token)
        assert result == FAIL_TEXT
        assert counter["opened"] == 0


class TestGuardedRead:

    @pytest.mark.asyncio
    async def test_guard_failure_returns_uniform_fail_text(self):
        # 타 에이전트 소유 문서 → UseCase가 None → 동일 실패 텍스트
        tool, _, counter = _make_tool(found=_article(agent_id="agent_other"))
        token = _set_ctx("agent_1")
        try:
            result = await tool._arun("w1")
        finally:
            reset_run_context(token)
        assert result == FAIL_TEXT
        assert counter["opened"] == 1 and counter["closed"] == 1

    @pytest.mark.asyncio
    async def test_success_renders_title_path_and_content(self):
        tool, repo, counter = _make_tool(found=_article())
        token = _set_ctx("agent_1")
        try:
            result = await tool._arun("w1")
        finally:
            reset_run_context(token)
        assert "한도 산정 기준" in result
        assert "여신/한도" in result
        assert "본문 텍스트입니다." in result
        assert result != FAIL_TEXT
        repo.find_by_id.assert_awaited_once_with("w1", "r")
        assert counter["opened"] == 1 and counter["closed"] == 1

    @pytest.mark.asyncio
    async def test_none_path_renders_dash(self):
        tool, _, _ = _make_tool(found=_article(path=None))
        token = _set_ctx("agent_1")
        try:
            result = await tool._arun("w1")
        finally:
            reset_run_context(token)
        assert "경로: -" in result
