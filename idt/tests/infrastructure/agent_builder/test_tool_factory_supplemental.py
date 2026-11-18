"""ToolFactory → InternalDocumentSearchTool 보조 검색 배선 (graph-rag-foundation module-1).

- tool_config.use_graph → tool.use_supplemental
- create(..., supplemental_grant=) → tool.supplemental_grant
- ExtensionHooks.supplemental 은 create 시점에 읽는다(기동 후 등록 허용)
"""
from unittest.mock import MagicMock

from src.domain.extension_hooks import (
    ExtensionHooks,
    SupplementalGrant,
    SupplementalResult,
    SupplementalRetrievalSource,
)
from src.infrastructure.agent_builder.tool_factory import ToolFactory


class _Source(SupplementalRetrievalSource):
    async def retrieve(self, query):
        return SupplementalResult(label="graph")


def _factory(hooks=None) -> ToolFactory:
    return ToolFactory(
        logger=MagicMock(),
        hybrid_search_use_case=MagicMock(),
        extension_hooks=hooks,
    )


def test_defaults_are_closed():
    tool = _factory().create("internal_document_search", "req")
    assert tool.use_supplemental is False
    assert tool.supplemental_grant is None
    assert tool.supplemental_source is None


def test_use_graph_and_grant_and_source_are_wired():
    hooks = ExtensionHooks()
    factory = _factory(hooks)
    source = _Source()
    hooks.register(supplemental=source)  # 팩토리 생성 이후 등록
    grant = SupplementalGrant(caller_is_admin=True)
    tool = factory.create(
        "internal_document_search", "req",
        tool_config={"use_graph": True}, supplemental_grant=grant,
    )
    assert tool.use_supplemental is True
    assert tool.supplemental_grant is grant
    assert tool.supplemental_source is source


def test_grant_ignored_for_other_tools():
    factory = ToolFactory(
        logger=MagicMock(), hybrid_search_use_case=MagicMock(),
        tavily_api_key="test-key", extension_hooks=ExtensionHooks(),
    )
    tool = factory.create(
        "tavily_search", "req", supplemental_grant=SupplementalGrant(True)
    )
    assert not hasattr(tool, "supplemental_grant")
