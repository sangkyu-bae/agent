"""tool-recommender Design §8.3 #8-#10 — LangChainToolFilter 통합 테스트.

핵심 검증축: **입력 도구를 절대 잃지 않는가** (§6.1 #8 최후 방어선).
"""
from src.domain.tool_selection.schemas import SelectionResult, ToolSource
from src.infrastructure.tool_selection.adapters.langchain_filter import (
    DefaultToolIdResolver,
    LangChainToolFilter,
)

# ── 테스트 더블 ──────────────────────────────────────────────────────────────


class _Tool:
    """BaseTool 흉내 — name/description만 있으면 충분하다."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class _ServerConfig:
    def __init__(self, name: str) -> None:
        self.name = name


class _MCPTool(_Tool):
    """MCPToolAdapter 흉내 — server_config + mcp_tool_name 보유."""

    def __init__(self, server: str, mcp_tool_name: str, description: str = "") -> None:
        super().__init__(f"{server}_{mcp_tool_name}", description)
        self.server_config = _ServerConfig(server)
        self.mcp_tool_name = mcp_tool_name


# 실측값 (Doc Convert MCP, 2026-08-13):
#   registration.name   = "Doc Convert MCP"        ← DB에만 있고 런타임엔 안 옴
#   server_config.name  = "mcp_6dd5c675-dae8-454d-9cc0-7e8c71f46977"
#   adapter.name        = "mcp_6dd5c675_dae8_454d_9cc0_7e8c71f46977_docx_to_html"
#   mcp_tool_name       = "docx_to_html"
_REAL_SERVER_ID = "6dd5c675-dae8-454d-9cc0-7e8c71f46977"
_REAL_RUNTIME_NAME = f"mcp_{_REAL_SERVER_ID}"


class _RealMCPTool(_Tool):
    """런타임 실제 형태 — server_config.name이 `mcp_{uuid}`(mcp_tool_loader.py:42)."""

    def __init__(self, mcp_tool_name: str, description: str = "") -> None:
        sanitized = f"{_REAL_RUNTIME_NAME}_{mcp_tool_name}".replace("-", "_")
        super().__init__(sanitized, description)
        self.server_config = _ServerConfig(_REAL_RUNTIME_NAME)
        self.mcp_tool_name = mcp_tool_name


class _SpyLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _rec(self, level, message, **kw):
        self.records.append((level, message, kw))

    def debug(self, message, **kw):
        self._rec("debug", message, **kw)

    def info(self, message, **kw):
        self._rec("info", message, **kw)

    def warning(self, message, **kw):
        self._rec("warning", message, **kw)

    def error(self, message, exception=None, **kw):
        self._rec("error", message, exception=exception, **kw)

    def critical(self, message, exception=None, **kw):
        self._rec("critical", message, exception=exception, **kw)

    def levels(self):
        return [lvl for lvl, _, _ in self.records]


class _StubSelector:
    """final_ids를 고정 반환하는 셀렉터."""

    def __init__(self, final_ids=(), exc: Exception | None = None) -> None:
        self._final_ids = tuple(final_ids)
        self._exc = exc
        self.seen_candidates = None
        self.seen_query = None

    async def select(self, query, candidates, *, required_ids=(), request_id=""):
        self.seen_query = query
        self.seen_candidates = list(candidates)
        if self._exc is not None:
            raise self._exc
        return SelectionResult(
            selected_ids=self._final_ids,
            required_ids=tuple(required_ids),
            final_ids=self._final_ids,
            candidate_count=len(candidates),
        )


def _build(selector):
    logger = _SpyLogger()
    return LangChainToolFilter(selector, logger), logger


# ── #8 정상 경로 ─────────────────────────────────────────────────────────────


async def test_filter_returns_selected_subset():
    tools = [_Tool("a"), _Tool("b"), _Tool("c")]
    selector = _StubSelector(("internal:a", "internal:c"))
    filt, _ = _build(selector)

    result = await filt.filter(tools, "질의")

    assert [t.name for t in result] == ["a", "c"]


async def test_filter_preserves_input_order():
    tools = [_Tool("a"), _Tool("b"), _Tool("c")]
    # 셀렉터가 역순으로 줘도 by_id 순회는 final_ids 순서를 따른다
    selector = _StubSelector(("internal:c", "internal:a"))
    filt, _ = _build(selector)

    result = await filt.filter(tools, "질의")

    assert [t.name for t in result] == ["c", "a"]


async def test_filter_returns_same_objects_not_copies():
    tools = [_Tool("a"), _Tool("b")]
    filt, _ = _build(_StubSelector(("internal:a",)))

    result = await filt.filter(tools, "질의")

    assert result[0] is tools[0]


async def test_filter_passes_query_and_required_through():
    tools = [_Tool("a"), _Tool("b")]
    selector = _StubSelector(("internal:a",))
    filt, _ = _build(selector)

    await filt.filter(tools, "엑셀로 뽑아줘", required_ids=("internal:b",))

    assert selector.seen_query == "엑셀로 뽑아줘"


async def test_empty_tool_list_returns_empty():
    filt, _ = _build(_StubSelector(()))
    assert await filt.filter([], "질의") == []


# ── #9 식별 실패 → 입력 그대로 (§6.1 #8) ────────────────────────────────────


async def test_unresolvable_tool_returns_input_unchanged():
    class _NullResolver:
        def resolve(self, tool):
            return None

    tools = [_Tool("a"), _Tool("b")]
    logger = _SpyLogger()
    filt = LangChainToolFilter(_StubSelector(()), logger, _NullResolver())

    result = await filt.filter(tools, "질의")

    assert result == tools
    assert "warning" in logger.levels()


async def test_partially_unresolvable_returns_input_unchanged():
    """일부만 식별되면 선별을 포기한다 — 조용한 도구 소실 방지."""

    class _PartialResolver:
        def resolve(self, tool):
            return None if tool.name == "b" else f"internal:{tool.name}"

    tools = [_Tool("a"), _Tool("b"), _Tool("c")]
    logger = _SpyLogger()
    filt = LangChainToolFilter(
        _StubSelector(("internal:a",)), logger, _PartialResolver()
    )

    result = await filt.filter(tools, "질의")

    assert result == tools


async def test_duplicate_tool_ids_returns_input_unchanged():
    tools = [_Tool("dup"), _Tool("dup")]
    filt, logger = _build(_StubSelector(("internal:dup",)))

    result = await filt.filter(tools, "질의")

    assert result == tools
    assert "warning" in logger.levels()


async def test_resolver_exception_returns_input_unchanged():
    class _BrokenResolver:
        def resolve(self, tool):
            raise RuntimeError("resolver down")

    tools = [_Tool("a")]
    logger = _SpyLogger()
    filt = LangChainToolFilter(_StubSelector(()), logger, _BrokenResolver())

    assert await filt.filter(tools, "질의") == tools


# ── #10 셀렉터 예외 / 빈 결과 → 입력 그대로 ─────────────────────────────────


async def test_selector_exception_returns_input_unchanged():
    """Port 계약이 깨져도 도구를 잃지 않는다."""
    tools = [_Tool("a"), _Tool("b")]
    filt, logger = _build(_StubSelector(exc=RuntimeError("contract violated")))

    result = await filt.filter(tools, "질의")

    assert result == tools
    assert "warning" in logger.levels()


async def test_empty_selection_returns_input_unchanged():
    tools = [_Tool("a"), _Tool("b")]
    filt, logger = _build(_StubSelector(()))

    result = await filt.filter(tools, "질의")

    assert result == tools
    assert "warning" in logger.levels()


async def test_final_ids_not_in_input_are_ignored():
    tools = [_Tool("a")]
    filt, _ = _build(_StubSelector(("internal:a", "internal:ghost")))

    result = await filt.filter(tools, "질의")

    assert [t.name for t in result] == ["a"]


# ── 후보 변환 (§3.3 저신호 보강 연동) ────────────────────────────────────────


async def test_mcp_tool_becomes_mcp_candidate_with_server_name():
    tools = [
        _Tool("internal_a"),
        _MCPTool("naver_mcp", "search_blog", "MCP tool: search_blog"),
    ]
    selector = _StubSelector(("internal:internal_a",))
    filt, _ = _build(selector)

    await filt.filter(tools, "질의")

    mcp = [c for c in selector.seen_candidates if c.source is ToolSource.MCP]
    assert len(mcp) == 1
    assert mcp[0].tool_id == "mcp:naver_mcp:search_blog"
    assert mcp[0].server_name == "naver_mcp"
    assert mcp[0].name == "search_blog"  # 서버 접두어 제거 — 모델에 보이는 이름


# ── 런타임 실제 형태: UUID 노이즈 제거 (Act-2) ───────────────────────────────


async def test_real_mcp_tool_id_uses_bare_server_id():
    """`mcp:mcp_{uuid}:...` 중복 접두어를 만들지 않는다."""
    selector = _StubSelector(())
    filt, _ = _build(selector)

    await filt.filter([_RealMCPTool("docx_to_html", "DOCX를 HTML로 변환")], "변환해줘")

    c = selector.seen_candidates[0]
    assert c.tool_id == f"mcp:{_REAL_SERVER_ID}:docx_to_html"
    assert "mcp:mcp_" not in c.tool_id


async def test_real_mcp_tool_name_drops_uuid_noise():
    """모델에 보이는 이름은 `docx_to_html` — UUID 40자를 넘기지 않는다."""
    selector = _StubSelector(())
    filt, _ = _build(selector)

    await filt.filter([_RealMCPTool("docx_to_html", "DOCX를 HTML로 변환")], "질의")

    c = selector.seen_candidates[0]
    assert c.name == "docx_to_html"
    assert _REAL_SERVER_ID not in c.name


async def test_real_mcp_server_name_is_none_when_runtime_id():
    """`mcp_{uuid}`는 사람이 읽는 이름이 아니므로 설명 보강에 쓰지 않는다.

    쓰면 저신호 도구의 설명이 오히려 UUID 노이즈로 오염된다.
    """
    selector = _StubSelector(())
    filt, _ = _build(selector)

    await filt.filter([_RealMCPTool("docx_to_html")], "질의")

    assert selector.seen_candidates[0].server_name is None


async def test_stub_description_enrichment_stays_clean_for_real_mcp_tool():
    """보강 결과에 UUID가 섞이지 않는지 end-to-end 확인."""
    from src.domain.tool_selection.policies import effective_description

    selector = _StubSelector(())
    filt, _ = _build(selector)

    await filt.filter(
        [_RealMCPTool("docx_to_html", "MCP tool: docx_to_html")], "질의"
    )

    enriched = effective_description(selector.seen_candidates[0])
    assert enriched == "'docx to html' 기능"
    assert _REAL_SERVER_ID not in enriched


def test_resolver_strips_mcp_prefix_from_runtime_server_name():
    resolver = DefaultToolIdResolver()
    assert resolver.resolve(_RealMCPTool("pdf_to_html")) == (
        f"mcp:{_REAL_SERVER_ID}:pdf_to_html"
    )


async def test_internal_tool_becomes_internal_candidate():
    tools = [_Tool("excel_export", "엑셀로 저장합니다.")]
    selector = _StubSelector(("internal:excel_export",))
    filt, _ = _build(selector)

    await filt.filter(tools, "질의")

    c = selector.seen_candidates[0]
    assert c.tool_id == "internal:excel_export"
    assert c.source is ToolSource.INTERNAL
    assert c.description == "엑셀로 저장합니다."
    assert c.server_name is None


async def test_missing_description_becomes_empty_string_not_none():
    class _NoDesc:
        name = "x"
        description = None

    selector = _StubSelector(("internal:x",))
    filt, _ = _build(selector)

    await filt.filter([_NoDesc()], "질의")

    assert selector.seen_candidates[0].description == ""


# ── DefaultToolIdResolver ────────────────────────────────────────────────────


def test_resolver_identifies_mcp_tool():
    resolver = DefaultToolIdResolver()
    tool = _MCPTool("naver_mcp", "search_blog")
    assert resolver.resolve(tool) == "mcp:naver_mcp:search_blog"


def test_resolver_identifies_plain_tool():
    assert DefaultToolIdResolver().resolve(_Tool("tavily_search")) == (
        "internal:tavily_search"
    )


def test_resolver_returns_none_for_nameless_object():
    assert DefaultToolIdResolver().resolve(object()) is None


def test_resolver_returns_none_for_dict_tool():
    """request.tools는 list[BaseTool | dict] — provider 네이티브 dict가 섞일 수 있다."""
    assert DefaultToolIdResolver().resolve({"type": "web_search"}) is None


def test_resolver_falls_back_to_name_when_server_config_lacks_name():
    tool = _Tool("x")
    tool.server_config = object()
    tool.mcp_tool_name = "y"
    assert DefaultToolIdResolver().resolve(tool) == "internal:x"
