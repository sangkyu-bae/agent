"""에이전트 저장 시 노출되지 않은 보조 검색(그래프) 플래그 정리.

Design Ref: graph-rag-foundation §7 — 노출 단계가 허용하지 않는 사용자가
use_graph=True 를 보내면 에러 없이 False 로 바꿔 저장하고 로그만 남긴다.
실행 시점 3중 게이트(Plan FR-20)와 함께 이중 방어다.
"""

from __future__ import annotations

import dataclasses

from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.extension_hooks import GRAPH_RAG_FEATURE, ExtensionHooks
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_RAG_TOOL_ID = "internal_document_search"
_FLAG = "use_graph"


def _has_flag(worker: WorkerDefinition) -> bool:
    return (
        worker.tool_id == _RAG_TOOL_ID
        and bool(worker.tool_config)
        and bool(worker.tool_config.get(_FLAG))
    )


async def strip_unexposed_graph_flag(
    workers: list[WorkerDefinition],
    hooks: ExtensionHooks | None,
    *,
    caller_is_admin: bool,
    logger: LoggerInterface,
    request_id: str,
) -> list[WorkerDefinition]:
    """use_graph=True 워커가 있고 노출되지 않으면 False 로 바꾼 사본 목록을 돌려준다."""
    flagged = [w for w in workers if _has_flag(w)]
    if not flagged:
        return list(workers)
    visible = hooks is not None and await hooks.is_visible(
        GRAPH_RAG_FEATURE, caller_is_admin=caller_is_admin
    )
    if visible:
        return list(workers)
    logger.info(
        "use_graph cleared on save (feature not exposed)",
        request_id=request_id,
        worker_ids=[w.worker_id for w in flagged],
    )
    return [
        dataclasses.replace(w, tool_config={**w.tool_config, _FLAG: False})
        if _has_flag(w)
        else w
        for w in workers
    ]
