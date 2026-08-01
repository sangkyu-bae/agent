"""MySQLWikiFolderSummaryRepository: 폴더 요약 MySQL 저장소 (wiki-folder-summaries D1).

파생 캐시라 벡터 색인 없음. upsert는 (agent_id, path) 유니크 기준
INSERT ... ON DUPLICATE KEY UPDATE — 동시 재증류 경합은 마지막 쓰기 승리로 충분.
commit()은 호출 측 세션 관리가 담당한다(Repository 내부 commit 금지).
"""
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.repositories.wiki_folder_repository import (
    WikiFolderSummaryRepository,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiFolderSummary
from src.infrastructure.wiki.models import WikiFolderSummaryModel


class MySQLWikiFolderSummaryRepository(WikiFolderSummaryRepository):
    """폴더 요약 영속화 구현체."""

    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def upsert(self, summary: WikiFolderSummary, request_id: str) -> None:
        stmt = mysql_insert(WikiFolderSummaryModel).values(
            id=summary.id,
            agent_id=summary.agent_id,
            path=summary.path,
            summary=summary.summary,
            article_count=summary.article_count,
            updated_at=summary.updated_at,
        )
        # id는 갱신하지 않는다 — uq(agent_id, path)가 기존 행을 식별
        stmt = stmt.on_duplicate_key_update(
            summary=stmt.inserted.summary,
            article_count=stmt.inserted.article_count,
            updated_at=stmt.inserted.updated_at,
        )
        await self._session.execute(stmt)
        self._logger.info(
            "WikiFolderSummaryRepository upsert",
            request_id=request_id, agent_id=summary.agent_id, path=summary.path,
        )

    async def delete(self, agent_id: str, path: str, request_id: str) -> None:
        stmt = sa_delete(WikiFolderSummaryModel).where(
            WikiFolderSummaryModel.agent_id == agent_id,
            WikiFolderSummaryModel.path == path,
        )
        await self._session.execute(stmt)
        self._logger.info(
            "WikiFolderSummaryRepository delete",
            request_id=request_id, agent_id=agent_id, path=path,
        )

    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[WikiFolderSummary]:
        stmt = (
            select(
                WikiFolderSummaryModel.id,
                WikiFolderSummaryModel.agent_id,
                WikiFolderSummaryModel.path,
                WikiFolderSummaryModel.summary,
                WikiFolderSummaryModel.article_count,
                WikiFolderSummaryModel.updated_at,
            )
            .where(WikiFolderSummaryModel.agent_id == agent_id)
            .order_by(WikiFolderSummaryModel.path)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            WikiFolderSummary(
                id=r.id, agent_id=r.agent_id, path=r.path, summary=r.summary,
                article_count=r.article_count, updated_at=r.updated_at,
            )
            for r in rows
        ]
