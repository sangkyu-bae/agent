"""TopicReviewer — 주제 판정(검토 대기)의 승인·거절.

Design Ref: graph-rag-foundation §11.9 검토, Plan FR-27.
- 승인: 자동으로 만든 주제(pending)를 active 로 확정한다.
- 거절: 대상 지정 시 그 후보 주제로 옮기고, 연결 판정을 대상 없이 거절하면 언급 이름으로
  새 주제(active, 관리자 생성)를 만든다. 새로 만든 판정은 대상이 필요하다.
- 옮긴 뒤 문서가 0개인 자동 주제는 retired. Neo4j 청크의 topic_ids 를 다시 복사한다.
대상 검증(후보 안·자기 자신 아님)은 ReviewUseCase 가 엔티티 판정과 같은 규칙으로 한다.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from src.domain.graph_rag.exceptions import GraphTopicDuplicateError
from src.domain.graph_rag.interfaces import (
    DocumentTopicStorePort,
    GraphStorePort,
    TopicRepositoryPort,
)
from src.domain.graph_rag.resolution import ResolutionDecision
from src.domain.graph_rag.topic import (
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicPolicy,
    TopicStatus,
    level_of_mention_type,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class TopicReviewer:
    def __init__(
        self,
        *,
        topics: TopicRepositoryPort,
        document_topics: DocumentTopicStorePort,
        store: GraphStorePort | None,
        logger: LoggerInterface,
    ) -> None:
        self._topics = topics
        self._links = document_topics
        self._store = store
        self._logger = logger

    async def approve(self, d: ResolutionDecision, request_id: str) -> None:
        if not d.created_new:
            return
        topic = await self._topics.get(d.entity_id, request_id)
        if topic is not None and topic.status is TopicStatus.PENDING:
            await self._topics.update(
                replace(topic, status=TopicStatus.ACTIVE), request_id
            )

    async def split(self, d: ResolutionDecision, reviewer: str, request_id: str) -> str:
        """연결 판정 거절(대상 없음) → 언급 이름으로 새 주제."""
        level = level_of_mention_type(d.mention_type)
        parent_id = None
        if level is TopicLevel.MINOR:
            original = await self._topics.get(d.entity_id, request_id)
            parent_id = original.parent_id if original else None
        name = TopicPolicy.clean_name(d.mention_text)
        topic = Topic(
            id=str(uuid.uuid4()),
            name=name,
            normalized_name=TopicPolicy.normalize(name),
            level=level,
            parent_id=parent_id,
            description="",
            status=TopicStatus.ACTIVE,
            origin=TopicOrigin.ADMIN,
            created_by=reviewer,
        )
        try:
            return (await self._topics.create(topic, request_id)).id
        except GraphTopicDuplicateError:
            found = await self._topics.find_by_name(
                topic.parent_key, topic.normalized_name, request_id
            )
            if found is None or found.status is not TopicStatus.RETIRED:
                raise
            revived = await self._topics.update(
                replace(found, status=TopicStatus.ACTIVE), request_id
            )
            return revived.id

    async def move(
        self, d: ResolutionDecision, to_topic_id: str, request_id: str
    ) -> None:
        document_id = await self._links.move(d.id, to_topic_id, request_id)
        if d.entity_id != to_topic_id:
            await self._retire_if_empty(d.entity_id, request_id)
        if document_id is not None:
            await self._copy_to_graph(document_id, request_id)

    async def _retire_if_empty(self, topic_id: str, request_id: str) -> None:
        topic = await self._topics.get(topic_id, request_id)
        if topic is None or topic.origin is not TopicOrigin.AUTO:
            return
        counts = await self._links.count_documents([topic_id], request_id)
        if counts.get(topic_id, 0) == 0:
            await self._topics.update(
                replace(topic, status=TopicStatus.RETIRED), request_id
            )

    async def _copy_to_graph(self, document_id: str, request_id: str) -> None:
        if self._store is None:
            return
        links = await self._links.list_for_document(document_id, request_id)
        ids = [lk.topic_id for lk in sorted(links, key=lambda lk: not lk.is_primary)]
        try:
            await self._store.set_document_topics(document_id, ids)
        except Exception as e:  # noqa: BLE001 — 원본은 MySQL, 다음 잡이 다시 복사
            self._logger.warning(
                "copy topic ids after review failed",
                exception=e,
                request_id=request_id,
                document_id=document_id,
            )
