"""대시보드 집계 리포지토리 — MySQL 메타 기준 COUNT/SUM/GROUP BY (Design D4).

읽기 전용 — commit/rollback 없음 (DB-001). 세션은 요청 스코프 주입.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.admin_dashboard.interfaces import (
    DashboardAggregationRepositoryInterface,
)
from src.domain.admin_dashboard.schemas import (
    ChunkStats,
    DashboardStats,
    DocumentStats,
    KbBreakdownRow,
    KbStats,
    RecentDocumentRow,
    UserStats,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.auth.models import UserModel
from src.infrastructure.doc_browse.models import DocumentMetadataModel
from src.infrastructure.persistence.models.knowledge_base import KnowledgeBaseModel


class SqlAlchemyDashboardAggregationRepository(
    DashboardAggregationRepositoryInterface
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def get_stats(self) -> DashboardStats:
        return DashboardStats(
            kb=await self._kb_stats(),
            documents=await self._document_stats(),
            chunks=await self._chunk_stats(),
            users=await self._user_stats(),
        )

    async def _kb_stats(self) -> KbStats:
        scope_rows = (
            await self._session.execute(
                select(KnowledgeBaseModel.scope, func.count()).group_by(
                    KnowledgeBaseModel.scope
                )
            )
        ).all()
        by_scope = {str(scope): count for scope, count in scope_rows}
        active = await self._session.scalar(
            select(func.count())
            .select_from(KnowledgeBaseModel)
            .where(KnowledgeBaseModel.status == "active")
        )
        return KbStats(
            total=sum(by_scope.values()), active=active or 0, by_scope=by_scope
        )

    async def _document_stats(self) -> DocumentStats:
        total = await self._session.scalar(
            select(func.count()).select_from(DocumentMetadataModel)
        )
        with_kb = await self._session.scalar(
            select(func.count())
            .select_from(DocumentMetadataModel)
            .where(DocumentMetadataModel.kb_id.is_not(None))
        )
        total = total or 0
        with_kb = with_kb or 0
        return DocumentStats(
            total=total, with_kb=with_kb, without_kb=total - with_kb
        )

    async def _chunk_stats(self) -> ChunkStats:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(DocumentMetadataModel.chunk_count), 0))
        )
        return ChunkStats(total=int(total or 0))

    async def _user_stats(self) -> UserStats:
        status_rows = (
            await self._session.execute(
                select(UserModel.status, func.count()).group_by(UserModel.status)
            )
        ).all()
        by_status = {str(s): count for s, count in status_rows}
        admins = await self._session.scalar(
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.role == "admin")
        )
        return UserStats(
            total=sum(by_status.values()),
            approved=by_status.get("approved", 0),
            pending=by_status.get("pending", 0),
            admins=admins or 0,
        )

    async def get_kb_breakdown(self) -> list[KbBreakdownRow]:
        doc_agg = (
            select(
                DocumentMetadataModel.kb_id.label("kb_id"),
                func.count().label("document_count"),
                func.coalesce(
                    func.sum(DocumentMetadataModel.chunk_count), 0
                ).label("chunk_count"),
                func.max(DocumentMetadataModel.created_at).label(
                    "last_uploaded_at"
                ),
            )
            .where(DocumentMetadataModel.kb_id.is_not(None))
            .group_by(DocumentMetadataModel.kb_id)
            .subquery()
        )
        document_count = func.coalesce(doc_agg.c.document_count, 0)
        stmt = (
            select(
                KnowledgeBaseModel.id,
                KnowledgeBaseModel.name,
                KnowledgeBaseModel.scope,
                KnowledgeBaseModel.status,
                document_count.label("document_count"),
                func.coalesce(doc_agg.c.chunk_count, 0).label("chunk_count"),
                doc_agg.c.last_uploaded_at,
            )
            .outerjoin(doc_agg, KnowledgeBaseModel.id == doc_agg.c.kb_id)
            .order_by(document_count.desc(), KnowledgeBaseModel.name.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            KbBreakdownRow(
                kb_id=row.id,
                name=row.name,
                scope=str(row.scope),
                status=row.status,
                document_count=int(row.document_count),
                chunk_count=int(row.chunk_count),
                last_uploaded_at=row.last_uploaded_at,
            )
            for row in rows
        ]

    async def get_recent_documents(self, limit: int) -> list[RecentDocumentRow]:
        stmt = (
            select(DocumentMetadataModel, KnowledgeBaseModel.name)
            .outerjoin(
                KnowledgeBaseModel,
                DocumentMetadataModel.kb_id == KnowledgeBaseModel.id,
            )
            .order_by(DocumentMetadataModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            RecentDocumentRow(
                document_id=model.document_id,
                filename=model.filename,
                kb_id=model.kb_id,
                kb_name=kb_name,
                collection_name=model.collection_name,
                chunk_count=model.chunk_count,
                chunk_strategy=model.chunk_strategy,
                created_at=model.created_at,
            )
            for model, kb_name in rows
        ]
