"""General Chat 도구 권한 필터 (tool-access-control Check G-01).

일반 채팅은 RunAgentUseCase 를 거치지 않고 Tavily·내부 문서·등록 MCP 전부를 바인딩했다.
실행자 ToolAccessSet 으로 바인딩 전에 거른다. 판정 id 는 tool-recommender 와 같은
DefaultToolIdResolver 규칙(internal:{name} / mcp:{srv}:{tool}).
"""
from unittest.mock import AsyncMock, MagicMock

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.agent_run.auth_context import AuthContext
from src.domain.tool_access.value_objects import ToolAccessSet
from src.infrastructure.tool_selection.adapters.langchain_filter import DefaultToolIdResolver

SRV = "7f3c0000-0000-0000-0000-000000000001"


def _tool(name: str, mcp: str | None = None):
    t = MagicMock()
    t.name = name
    if mcp:
        t.mcp_tool_name = mcp
        t.server_config = MagicMock()
        t.server_config.name = f"mcp_{SRV}"
    else:
        t.mcp_tool_name = None
        t.server_config = None
    return t


TOOLS = [
    _tool("tavily_search"),
    _tool("internal_document_search"),
    _tool("srv_send_mail", mcp="send_mail"),
    _tool("srv_list_mail", mcp="list_mail"),
]


def _uc(resolver):
    return GeneralChatUseCase(
        chat_tool_builder=MagicMock(), message_repo=MagicMock(), summary_repo=MagicMock(),
        summarizer=MagicMock(), summarization_policy=MagicMock(), logger=MagicMock(),
        llm_factory=MagicMock(), llm_model=MagicMock(),
        tool_access_resolver=resolver, tool_id_resolver=DefaultToolIdResolver(),
    )


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=7, display_name="u", role="user", primary_department_id=None,
        primary_department_name=None, department_ids=("d1",), department_names=(),
        permissions=frozenset(),
    )


def _resolver(access=None, error=None):
    r = MagicMock()
    r.for_auth_ctx = AsyncMock(return_value=access, side_effect=error)
    r.for_user_id = AsyncMock(return_value=access, side_effect=error)
    return r


async def test_keeps_only_allowed_tools():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({
        "internal:internal_document_search", f"mcp:{SRV}:list_mail",
    }))
    r = _resolver(access)
    got = await _uc(r)._permitted_tools(TOOLS, _ctx(), "7", "rid")
    assert [t.name for t in got] == ["internal_document_search", "srv_list_mail"]
    r.for_auth_ctx.assert_awaited_once()


async def test_without_auth_ctx_uses_user_id():
    r = _resolver(ToolAccessSet.admin())
    got = await _uc(r)._permitted_tools(TOOLS, None, "7", "rid")
    assert len(got) == 4
    r.for_user_id.assert_awaited_once_with("7", "rid")


async def test_resolver_failure_binds_no_tools():
    got = await _uc(_resolver(error=RuntimeError("db")))._permitted_tools(TOOLS, _ctx(), "7", "rid")
    assert got == []


async def test_without_resolver_unfiltered():
    assert len(await _uc(None)._permitted_tools(TOOLS, _ctx(), "7", "rid")) == 4
