"""graph_rag 가 코어 확장 지점에 등록하는 구현.

Design Ref: graph-rag-foundation §2.1 — module-2 노출 판단, module-3 업로드 후 추출.
module-5: 문서 삭제 정리(GraphDeletionHook). 검색 공급자는 retrieval/source.py.
설정을 읽지 못하면 닫힘(노출·추출 안 함).
"""

from __future__ import annotations

from typing import Any

from src.domain.extension_hooks import (
    GRAPH_RAG_FEATURE,
    DocumentDeletedEvent,
    DocumentDeletionHook,
    DocumentIngestedEvent,
    FeatureExposurePort,
    PostIngestHook,
)
from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.extraction import (
    DocumentEligibilityPolicy,
    JobMode,
    TriggerSource,
)
from src.domain.graph_rag.interfaces import (
    DecisionStorePort,
    DocumentTopicStorePort,
    GraphSettingsReaderPort,
    GraphStorePort,
)
from src.domain.graph_rag.policies import RolloutPolicy
from src.domain.graph_rag.value_objects import RolloutStage
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_FAILED = "failed"


class GraphIngestHook(PostIngestHook):
    """업로드 완료 → 조건이 맞으면 추출 잡을 띄운다 (Plan FR-04).

    예외는 코어 호출 지점이 로그만 남기고 삼킨다(업로드 결과 불변).
    """

    def __init__(self, launcher: Any, reader: GraphSettingsReaderPort) -> None:
        self._launcher = launcher
        self._reader = reader

    async def on_document_ingested(
        self, event: DocumentIngestedEvent, request_id: str
    ) -> None:
        settings = await self._reader.get()
        if (
            settings.rollout_stage is RolloutStage.OFF
            or not settings.extraction_enabled
            or not settings.extraction_llm_model_id
            or event.status == _FAILED
            or event.chunk_count <= 0
            or not DocumentEligibilityPolicy.is_extractable(event.filename)
        ):
            return
        await self._launcher.launch(
            document_id=event.document_id,
            kb_id=event.kb_id,
            collection_name=event.collection_name,
            mode=JobMode.RESUME,
            trigger=TriggerSource.UPLOAD,
            requested_by=event.user_id,
            request_id=request_id,
        )


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


class GraphDeletionHook(DocumentDeletionHook):
    """문서 삭제 → 그래프 근거·주제 연결 정리 (Plan FR-15, module-5).

    노출 단계와 상관없이 정리한다(이전에 추출한 그래프가 남지 않게).
    그래프 저장소가 없으면 MySQL 주제 연결만 지운다. 예외는 코어가 삼킨다.
    """

    def __init__(
        self,
        store: GraphStorePort | None,
        document_topics: DocumentTopicStorePort,
        logger: LoggerInterface,
        *,
        decisions: DecisionStorePort | None = None,
    ) -> None:
        self._store = store
        self._links = document_topics
        self._logger = logger
        self._decisions = decisions

    async def on_document_deleted(
        self, event: DocumentDeletedEvent, request_id: str
    ) -> None:
        await self._links.replace(event.document_id, [], request_id)
        if self._decisions is not None:  # Check M-1: 검토 큐에 남지 않게
            await self._decisions.delete_for_document(event.document_id, request_id)
        if self._store is None:
            return
        try:
            await self._store.delete_document(event.document_id)
        except GraphBackendUnavailableError as e:
            self._logger.warning(
                "graph cleanup skipped — backend unavailable",
                exception=e,
                request_id=request_id,
                document_id=event.document_id,
            )
            return
        self._logger.info(
            "graph document cleaned",
            request_id=request_id,
            document_id=event.document_id,
        )
