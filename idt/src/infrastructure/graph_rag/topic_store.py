"""주제 목록(V090)·문서↔주제(V091) 저장소 — 앱 수명 싱글턴, 호출마다 짧은 세션.

Design Ref: graph-rag-foundation §11.9 (module-4b). MySQL 이 원본이고 Neo4j 청크의
topic_ids 는 복사본이다.
이름 유일성은 DB 유일 키(parent_key, normalized_name)로 보장한다.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from src.domain.graph_rag.exceptions import GraphTopicDuplicateError
from src.domain.graph_rag.interfaces import (
    DocumentTopicStorePort,
    TopicRepositoryPort,
)
from src.domain.graph_rag.topic import (
    DocumentTopic,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicStatus,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.models import GraphDocumentTopicModel as LinkRow
from src.infrastructure.graph_rag.models import GraphTopicModel as TopicRow


def _topic(r: TopicRow) -> Topic:
    return Topic(
        id=r.id,
        name=r.name,
        normalized_name=r.normalized_name,
        level=TopicLevel(int(r.level)),
        parent_id=r.parent_id,
        description=r.description or "",
        status=TopicStatus(r.status),
        origin=TopicOrigin(r.origin),
        created_by=r.created_by,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _apply(row: TopicRow, t: Topic) -> None:
    row.name, row.normalized_name = t.name, t.normalized_name
    row.level, row.parent_id, row.parent_key = int(t.level), t.parent_id, t.parent_key
    row.description = t.description or None
    row.status, row.origin = t.status.value, t.origin.value
    row.created_by = t.created_by


def _link(r: LinkRow) -> DocumentTopic:
    return DocumentTopic(
        document_id=r.document_id,
        topic_id=r.topic_id,
        is_primary=bool(r.is_primary),
        probability=float(r.probability) if r.probability is not None else None,
        decision_id=r.decision_id,
    )


class SessionScopedTopicRepository(TopicRepositoryPort):
    def __init__(self, session_factory: Callable[[], Any], logger: LoggerInterface):
        self._session_factory = session_factory
        self._logger = logger

    async def list(
        self,
        request_id: str,
        *,
        level: TopicLevel | None = None,
        parent_id: str | None = None,
        include_retired: bool = False,
    ) -> list[Topic]:
        stmt = select(TopicRow)
        if level is not None:
            stmt = stmt.where(
                TopicRow.level == int(level), TopicRow.parent_key == (parent_id or "")
            )
        if not include_retired:
            stmt = stmt.where(TopicRow.status != TopicStatus.RETIRED.value)
        async with self._session_factory() as session:
            rows = (await session.execute(stmt.order_by(TopicRow.name))).scalars()
            return [_topic(r) for r in rows]

    async def get(self, topic_id: str, request_id: str) -> Topic | None:
        async with self._session_factory() as session:
            row = await session.get(TopicRow, topic_id)
            return _topic(row) if row else None

    async def find_by_name(
        self, parent_key: str, normalized_name: str, request_id: str
    ) -> Topic | None:
        stmt = select(TopicRow).where(
            TopicRow.parent_key == parent_key,
            TopicRow.normalized_name == normalized_name,
        )
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).scalars().first()
            return _topic(row) if row else None

    async def create(self, topic: Topic, request_id: str) -> Topic:
        try:
            async with self._session_factory() as session, session.begin():
                row = TopicRow(id=topic.id)
                _apply(row, topic)
                session.add(row)
        except IntegrityError as e:
            raise GraphTopicDuplicateError(f"topic already exists: {topic.name}") from e
        return await self.get(topic.id, request_id) or topic

    async def update(self, topic: Topic, request_id: str) -> Topic:
        try:
            async with self._session_factory() as session, session.begin():
                row = await session.get(TopicRow, topic.id)
                if row is None:
                    raise GraphTopicDuplicateError(f"topic vanished: {topic.id}")
                _apply(row, topic)
        except IntegrityError as e:
            raise GraphTopicDuplicateError(f"topic already exists: {topic.name}") from e
        return await self.get(topic.id, request_id) or topic


class SessionScopedDocumentTopicStore(DocumentTopicStorePort):
    def __init__(self, session_factory: Callable[[], Any], logger: LoggerInterface):
        self._session_factory = session_factory
        self._logger = logger

    async def list_for_document(
        self, document_id: str, request_id: str
    ) -> list[DocumentTopic]:
        stmt = (
            select(LinkRow)
            .where(LinkRow.document_id == document_id)
            .order_by(LinkRow.is_primary.desc(), LinkRow.created_at, LinkRow.topic_id)
        )
        async with self._session_factory() as session:
            return [_link(r) for r in (await session.execute(stmt)).scalars()]

    async def replace(
        self, document_id: str, links: list[DocumentTopic], request_id: str
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                delete(LinkRow).where(LinkRow.document_id == document_id)
            )
            seen: set[str] = set()
            for lk in links:
                if lk.topic_id in seen:
                    continue
                seen.add(lk.topic_id)
                session.add(_row(document_id, lk))

    async def move(
        self, decision_id: str, to_topic_id: str, request_id: str
    ) -> str | None:
        async with self._session_factory() as session, session.begin():
            row = (
                (
                    await session.execute(
                        select(LinkRow).where(LinkRow.decision_id == decision_id)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            document_id = row.document_id
            existing = await session.get(LinkRow, (document_id, to_topic_id))
            moved = DocumentTopic(
                document_id,
                to_topic_id,
                row.is_primary or bool(existing and existing.is_primary),
                None,
                decision_id if existing is None else existing.decision_id,
            )
            await session.delete(row)
            if existing is not None:
                await session.delete(existing)
            await session.flush()
            session.add(_row(document_id, moved))
            return document_id

    async def count_documents(
        self, topic_ids: list[str], request_id: str
    ) -> dict[str, int]:
        counts = dict.fromkeys(topic_ids, 0)
        if not topic_ids:
            return counts
        stmt = (
            select(LinkRow.topic_id, func.count())
            .where(LinkRow.topic_id.in_(topic_ids))
            .group_by(LinkRow.topic_id)
        )
        async with self._session_factory() as session:
            for topic_id, n in (await session.execute(stmt)).all():
                counts[topic_id] = int(n)
        return counts


def _row(document_id: str, lk: DocumentTopic) -> LinkRow:
    return LinkRow(
        document_id=document_id,
        topic_id=lk.topic_id,
        is_primary=lk.is_primary,
        probability=(
            Decimal(str(round(lk.probability, 4)))
            if lk.probability is not None
            else None
        ),
        decision_id=lk.decision_id,
    )
