"""관리자 주제 목록 — 기본 목록 만들기·고치기·폐기 (Design §11.9, FR-27).

관리자가 만든 주제는 바로 active. 자동 주제(pending)는 검토 큐 또는 여기서 active 로.
상태는 active·retired 로만 바꿀 수 있다(pending 은 자동 생성 전용).
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from src.domain.graph_rag.exceptions import (
    GraphTopicInvalidError,
    GraphTopicNotFoundError,
)
from src.application.graph_rag.admin.inspect_use_case import ensure_stage_on
from src.domain.graph_rag.interfaces import (
    DocumentTopicStorePort,
    GraphSettingsReaderPort,
    TopicRepositoryPort,
)
from src.domain.graph_rag.topic import (
    MAX_TOPIC_DESCRIPTION,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicPolicy,
    TopicStatus,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_EDITABLE_STATUSES = {TopicStatus.ACTIVE, TopicStatus.RETIRED}


class TopicsUseCase:
    def __init__(
        self,
        *,
        topics: TopicRepositoryPort,
        document_topics: DocumentTopicStorePort,
        logger: LoggerInterface,
        reader: GraphSettingsReaderPort | None = None,
    ) -> None:
        self._topics = topics
        self._links = document_topics
        self._logger = logger
        self._reader = reader

    async def _ensure_on(self) -> None:
        """Design §4: 노출 단계 off 이면 409 (Check G-2)."""
        if self._reader is not None:
            await ensure_stage_on(self._reader)

    async def list(
        self, *, include_retired: bool, request_id: str
    ) -> list[tuple[Topic, int]]:
        """대분류 다음에 그 소분류 순서(트리 순서) + 문서 수."""
        await self._ensure_on()
        rows = await self._topics.list(request_id, include_retired=include_retired)
        counts = await self._links.count_documents([t.id for t in rows], request_id)
        majors = sorted(
            (t for t in rows if t.level is TopicLevel.MAJOR), key=lambda t: t.name
        )
        ordered: list[Topic] = []
        for major in majors:
            ordered.append(major)
            ordered += sorted(
                (t for t in rows if t.parent_id == major.id), key=lambda t: t.name
            )
        ordered += [t for t in rows if t not in ordered]  # 부모가 목록 밖인 소분류
        return [(t, counts.get(t.id, 0)) for t in ordered]

    async def create(
        self,
        *,
        name: str,
        level: int,
        parent_id: str | None,
        description: str | None,
        actor: str,
        request_id: str,
    ) -> Topic:
        await self._ensure_on()
        lvl = _level(level)
        TopicPolicy.check_parent(lvl, parent_id)
        if parent_id:
            parent = await self._topics.get(parent_id, request_id)
            if parent is None:
                raise GraphTopicNotFoundError(f"parent topic not found: {parent_id}")
            if parent.level is not TopicLevel.MAJOR or not parent.usable:
                raise GraphTopicInvalidError("parent must be an active major topic")
        clean = TopicPolicy.clean_name(name)
        topic = Topic(
            id=str(uuid.uuid4()),
            name=clean,
            normalized_name=TopicPolicy.normalize(clean),
            level=lvl,
            parent_id=parent_id,
            description=(description or "")[:MAX_TOPIC_DESCRIPTION],
            status=TopicStatus.ACTIVE,
            origin=TopicOrigin.ADMIN,
            created_by=actor,
        )
        created = await self._topics.create(topic, request_id)
        self._logger.info(
            "graph topic created",
            request_id=request_id,
            topic_id=created.id,
            level=int(lvl),
        )
        return created

    async def update(
        self,
        topic_id: str,
        *,
        name: str | None,
        description: str | None,
        status: str | None,
        request_id: str,
    ) -> Topic:
        await self._ensure_on()
        topic = await self._topics.get(topic_id, request_id)
        if topic is None:
            raise GraphTopicNotFoundError(f"topic not found: {topic_id}")
        if name is not None:
            clean = TopicPolicy.clean_name(name)
            topic = replace(
                topic, name=clean, normalized_name=TopicPolicy.normalize(clean)
            )
        if description is not None:
            topic = replace(topic, description=description[:MAX_TOPIC_DESCRIPTION])
        if status is not None:
            try:
                new_status = TopicStatus(status)
            except ValueError as e:
                raise GraphTopicInvalidError(f"unknown status: {status}") from e
            if new_status not in _EDITABLE_STATUSES:
                raise GraphTopicInvalidError("status can be active or retired")
            topic = replace(topic, status=new_status)
        return await self._topics.update(topic, request_id)


def _level(value: int) -> TopicLevel:
    try:
        return TopicLevel(value)
    except ValueError as e:
        raise GraphTopicInvalidError("level must be 1 or 2") from e
