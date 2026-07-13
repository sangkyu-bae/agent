"""GetMessageRetrievalsUseCase: 대화 메시지 기준 검색 근거 조회.

retrieval-observability Design §4.6 (D8):
conversation_message → ai_run(user_message_id FK) → ai_retrieval_source 경로로
"이 질문에서 어떤 재작성 쿼리로 어떤 문서가 뽑혔는지"를 조회한다.
그룹핑: run별 → search_query별 (그룹 내 rank_index 순서 유지).
"""
from dataclasses import dataclass, field
from typing import List, Optional

from src.application.agent_run.exceptions import (
    MessageAccessDeniedError,
    MessageNotFoundError,
)
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.agent_run.entities import AgentRun, RetrievalSource
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.conversation.entities import MessageId
from src.domain.logging.interfaces.logger_interface import LoggerInterface


# ── DTO (application 레이어 — Pydantic 변환은 router에서) ──────────────


@dataclass(frozen=True)
class QueryRetrievalGroup:
    """재작성 쿼리 1개 단위의 근거 그룹."""

    search_query: Optional[str]
    query_source: Optional[str]
    search_mode: Optional[str]
    sources: List[RetrievalSource] = field(default_factory=list)


@dataclass(frozen=True)
class MessageRunRetrievals:
    """run 1개의 검색 근거 (보통 메시지당 1 run, 재시도 시 복수)."""

    run: AgentRun
    groups: List[QueryRetrievalGroup] = field(default_factory=list)


@dataclass(frozen=True)
class MessageRetrievalsDto:
    message_id: int
    runs: List[MessageRunRetrievals] = field(default_factory=list)


class GetMessageRetrievalsUseCase:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        message_repo: ConversationMessageRepository,
        logger: LoggerInterface,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._message_repo = message_repo
        self._logger = logger

    async def execute(
        self,
        message_id: int,
        requesting_user_id: str,
        is_admin: bool,
    ) -> MessageRetrievalsDto:
        """메시지 소유 검증 → run 조회 → run별 retrieval 그룹핑.

        Raises:
            MessageNotFoundError: 메시지 미존재 → router 404
            MessageAccessDeniedError: 본인 아님 + non-admin → router 403
        """
        message = await self._message_repo.find_by_id(MessageId(message_id))
        if message is None:
            raise MessageNotFoundError(message_id)
        if message.user_id.value != requesting_user_id and not is_admin:
            raise MessageAccessDeniedError(message_id)

        runs = await self._agent_run_repo.find_runs_by_user_message(message_id)
        run_nodes: List[MessageRunRetrievals] = []
        for run in runs:
            retrievals = await self._agent_run_repo.find_retrievals(run.id)
            run_nodes.append(
                MessageRunRetrievals(run=run, groups=_group_by_query(retrievals))
            )

        self._logger.info(
            "Message retrievals fetched",
            message_id=message_id,
            run_count=len(run_nodes),
        )
        return MessageRetrievalsDto(message_id=message_id, runs=run_nodes)


def _group_by_query(
    retrievals: List[RetrievalSource],
) -> List[QueryRetrievalGroup]:
    """search_query 기준 그룹핑 — 등장 순서 보존, 그룹 내 rank_index 순서 유지.

    find_retrievals가 rank_index ORDER BY로 반환하므로 append 순서가 곧 rank 순서.
    """
    grouped: dict[tuple, list[RetrievalSource]] = {}
    for r in retrievals:
        key = (r.search_query, r.query_source, r.search_mode)
        grouped.setdefault(key, []).append(r)
    return [
        QueryRetrievalGroup(
            search_query=key[0],
            query_source=key[1],
            search_mode=key[2],
            sources=sources,
        )
        for key, sources in grouped.items()
    ]
