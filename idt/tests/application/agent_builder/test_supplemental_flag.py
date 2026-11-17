"""에이전트 저장 시 use_graph 정리 (graph-rag-foundation §7, Design 결정: 조용히 False).

- 노출 판단이 False 면 RAG 워커의 use_graph 를 False 로 바꾼 사본을 돌려준다
- 원본 WorkerDefinition·tool_config 는 바꾸지 않는다(포크 원본 보호)
- 다른 도구·use_graph 미지정 워커는 그대로
"""
from unittest.mock import MagicMock

import pytest
from src.application.agent_builder.supplemental_flag import strip_unexposed_graph_flag
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.extension_hooks import ExtensionHooks, FeatureExposurePort


class _Exposure(FeatureExposurePort):
    async def is_visible(self, feature, caller_is_admin):
        return caller_is_admin


def _rag(use_graph=True) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="internal_document_search", worker_id="rag_worker",
        description="rag", tool_config={"kb_id": "kb-1", "use_graph": use_graph},
    )


def _hooks() -> ExtensionHooks:
    h = ExtensionHooks()
    h.register(exposure=_Exposure())
    return h


@pytest.mark.asyncio
async def test_non_admin_flag_is_cleared_on_copy():
    original = _rag()
    out = await strip_unexposed_graph_flag(
        [original], _hooks(), caller_is_admin=False, logger=MagicMock(), request_id="r"
    )
    assert out[0].tool_config["use_graph"] is False
    assert out[0].tool_config["kb_id"] == "kb-1"
    assert original.tool_config["use_graph"] is True  # 원본 불변


@pytest.mark.asyncio
async def test_admin_flag_kept():
    out = await strip_unexposed_graph_flag(
        [_rag()], _hooks(), caller_is_admin=True, logger=MagicMock(), request_id="r"
    )
    assert out[0].tool_config["use_graph"] is True


@pytest.mark.asyncio
async def test_no_hooks_means_not_visible():
    out = await strip_unexposed_graph_flag(
        [_rag()], None, caller_is_admin=True, logger=MagicMock(), request_id="r"
    )
    assert out[0].tool_config["use_graph"] is False


@pytest.mark.asyncio
async def test_other_workers_untouched():
    other = WorkerDefinition(
        tool_id="tavily_search", worker_id="web", description="w",
        tool_config={"use_graph": True},
    )
    plain = WorkerDefinition(
        tool_id="internal_document_search", worker_id="r2", description="r",
        tool_config={"kb_id": "kb-2"},
    )
    none_cfg = WorkerDefinition(
        tool_id="internal_document_search", worker_id="r3", description="r",
    )
    out = await strip_unexposed_graph_flag(
        [other, plain, none_cfg], _hooks(), caller_is_admin=False,
        logger=MagicMock(), request_id="r",
    )
    assert out[0] is other
    assert out[1] is plain
    assert out[2] is none_cfg
