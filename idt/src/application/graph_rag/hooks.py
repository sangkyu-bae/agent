"""graph_rag 가 코어 확장 지점에 등록하는 구현 (module-2: 노출 판단).

Design Ref: graph-rag-foundation §2.1 — GraphIngestHook·GraphDeletionHook·
GraphRetrievalSource 는 module-3·5 에서 이 모듈에 추가된다.
설정을 읽지 못하면 닫힘(노출 안 함).
"""

from __future__ import annotations

from src.domain.extension_hooks import GRAPH_RAG_FEATURE, FeatureExposurePort
from src.domain.graph_rag.interfaces import GraphSettingsReaderPort
from src.domain.graph_rag.policies import RolloutPolicy
from src.domain.graph_rag.value_objects import RolloutStage


async def _stage_or_none(reader: GraphSettingsReaderPort) -> RolloutStage | None:
    try:
        return (await reader.get()).rollout_stage
    except Exception:  # noqa: BLE001 — 노출 판단 실패는 닫힘
        return None


class GraphExposure(FeatureExposurePort):
    def __init__(self, reader: GraphSettingsReaderPort) -> None:
        self._reader = reader

    async def is_visible(self, feature: str, caller_is_admin: bool) -> bool:
        if feature != GRAPH_RAG_FEATURE:
            return False
        stage = await _stage_or_none(self._reader)
        if stage is None:
            return False
        return RolloutPolicy.allows(stage, caller_is_admin=caller_is_admin)


async def capabilities_for(
    reader: GraphSettingsReaderPort, *, caller_is_admin: bool
) -> dict:
    """Plan FR-24 — 일반 사용자 응답에는 stage 를 넣지 않는다."""
    stage = await _stage_or_none(reader)
    if stage is None or not RolloutPolicy.allows(
        stage, caller_is_admin=caller_is_admin
    ):
        return {"visible": False}
    if not caller_is_admin:
        return {"visible": True}
    return {"visible": True, "stage": stage.value}
