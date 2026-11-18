"""검토 큐 — 애매하게 판정된 건을 관리자가 승인·거절한다.

Design Ref: graph-rag-foundation §4.2 review reject, Plan FR-11, D4.
- 승인: 그래프는 그대로, 판정 행만 approved.
- 거절(원래 연결했던 판정): 대상 미지정이면 새 엔티티로 분리, 후보 지정이면 재연결.
- 거절(원래 새로 만든 판정): 후보 중 대상을 지정해야 한다(합칠 곳이 필요).
- 옮긴 뒤 언급이 0개가 된 엔티티는 지운다. 대상은 판정 당시 후보로 제한한다
  — 임의 엔티티로의 병합은 엔티티 검색 화면(module-5)이 생긴 뒤 검토한다.
"""

from __future__ import annotations

import uuid

from src.application.graph_rag.admin.inspect_use_case import ensure_stage_on
from src.application.graph_rag.topic.review import TopicReviewer
from src.domain.graph_rag.exceptions import GraphRagError
from src.domain.graph_rag.extraction import GLOBAL_SCOPE, EntityWrite, NameNormalizer
from src.domain.graph_rag.interfaces import (
    DecisionStorePort,
    GraphSettingsReaderPort,
    GraphStorePort,
)
from src.domain.graph_rag.resolution import ResolutionDecision, ReviewStatus
from src.domain.graph_rag.topic import is_topic_decision
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GraphReviewNotFoundError(GraphRagError):
    code = "GRAPH_REVIEW_NOT_FOUND"


class GraphReviewAlreadyDoneError(GraphRagError):
    code = "GRAPH_REVIEW_ALREADY_DONE"


class GraphReviewTargetInvalidError(GraphRagError):
    code = "GRAPH_REVIEW_TARGET_INVALID"


class ReviewUseCase:
    def __init__(
        self,
        *,
        decisions: DecisionStorePort,
        store: GraphStorePort,
        logger: LoggerInterface,
        topics: TopicReviewer | None = None,
        reader: GraphSettingsReaderPort | None = None,
    ) -> None:
        self._decisions = decisions
        self._store = store
        self._logger = logger
        self._topics = topics
        self._reader = reader

    async def _ensure_on(self) -> None:
        """Design §4: 단계 off 이면 설정·health 외 관리자 API 는 409 (Check G-2)."""
        if self._reader is not None:
            await ensure_stage_on(self._reader)

    def _topic_reviewer(self, d: ResolutionDecision) -> TopicReviewer | None:
        if not is_topic_decision(d.mention_type):
            return None
        if self._topics is None:
            raise GraphReviewTargetInvalidError("topic review is not available")
        return self._topics

    async def list(
        self, status: ReviewStatus, limit: int, offset: int, request_id: str
    ) -> tuple[list[ResolutionDecision], int]:
        await self._ensure_on()
        return await self._decisions.list_by_review_status(
            status, limit, offset, request_id
        )

    async def _pending(self, decision_id: str, request_id: str) -> ResolutionDecision:
        await self._ensure_on()
        d = await self._decisions.get(decision_id, request_id)
        if d is None:
            raise GraphReviewNotFoundError(f"decision not found: {decision_id}")
        if d.review_status is not ReviewStatus.PENDING:
            raise GraphReviewAlreadyDoneError(f"already {d.review_status.value}")
        return d

    async def approve(
        self, decision_id: str, *, reviewer: str, note: str | None, request_id: str
    ) -> None:
        d = await self._pending(decision_id, request_id)
        topics = self._topic_reviewer(d)
        if topics is not None:
            await topics.approve(d, request_id)
        await self._decisions.mark_reviewed(
            d.id, ReviewStatus.APPROVED, reviewer, note, d.entity_id, request_id
        )

    async def reject(
        self,
        decision_id: str,
        *,
        reviewer: str,
        note: str | None,
        target_entity_id: str | None,
        request_id: str,
    ) -> str:
        """거절 처리 후 언급이 연결된 엔티티 id 를 돌려준다."""
        d = await self._pending(decision_id, request_id)
        topics = self._topic_reviewer(d)
        if topics is not None:
            to_id = self._checked_target(d, target_entity_id) or await topics.split(
                d, reviewer, request_id
            )
            await topics.move(d, to_id, request_id)
        else:
            to_id = await self._target(d, target_entity_id)
            await self._store.reassign_decision(d.id, to_id)
            if d.entity_id != to_id:
                await self._store.delete_entity_if_orphan(d.entity_id)
        await self._decisions.mark_reviewed(
            d.id, ReviewStatus.REJECTED, reviewer, note, to_id, request_id
        )
        self._logger.info(
            "graph review rejected",
            request_id=request_id,
            decision_id=d.id,
            from_entity=d.entity_id,
            to_entity=to_id,
        )
        return to_id

    @staticmethod
    def _checked_target(d: ResolutionDecision, target: str | None) -> str | None:
        """대상 검증 — 판정 당시 후보만. 대상 없음은 연결 판정일 때만 허용(분리)."""
        candidate_ids = {c.get("entity_id") for c in d.candidates}
        if target is not None:
            if target not in candidate_ids or target == d.entity_id:
                raise GraphReviewTargetInvalidError(
                    "target must be one of the decision candidates"
                )
            return target
        if d.created_new:
            raise GraphReviewTargetInvalidError(
                "a newly created entity needs a candidate to merge into"
            )
        return None

    async def _target(self, d: ResolutionDecision, target: str | None) -> str:
        checked = self._checked_target(d, target)
        if checked is not None:
            return checked
        entity = EntityWrite(
            id=str(uuid.uuid4()),
            scope_key=GLOBAL_SCOPE,
            name=d.mention_text,
            normalized_name=NameNormalizer.normalize(d.mention_text),
            type=d.mention_type,
            description="",
        )
        await self._store.create_entity(entity)
        return entity.id
