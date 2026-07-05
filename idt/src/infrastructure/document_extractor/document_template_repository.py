"""DocumentTemplateRepository: document_template MySQL CRUD (Design §2-5).

DB-001 §10.3 준수 — commit/rollback은 세션 관리자(get_session) 책임.
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.document_extractor.interfaces import (
    DocumentTemplateRepositoryInterface,
)
from src.domain.document_extractor.schemas import (
    TEMPLATE_STATUS_ACTIVE,
    TEMPLATE_STATUS_DELETED,
    DocumentTemplate,
    TemplateSlot,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.document_extractor.models import DocumentTemplateModel


class DocumentTemplateRepository(DocumentTemplateRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self, template: DocumentTemplate, request_id: str
    ) -> DocumentTemplate:
        self._logger.info(
            "DocumentTemplate save",
            request_id=request_id,
            template_id=template.id,
            agent_id=template.agent_id,
        )
        try:
            self._session.add(self._to_orm(template))
            await self._session.flush()
            return template
        except Exception as e:
            self._logger.error(
                "DocumentTemplate save failed", exception=e, request_id=request_id
            )
            raise

    async def find_by_id(
        self, template_id: str, request_id: str
    ) -> DocumentTemplate | None:
        try:
            stmt = select(DocumentTemplateModel).where(
                DocumentTemplateModel.id == template_id
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "DocumentTemplate find_by_id failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def find_active_by_agent_worker(
        self, agent_id: str, worker_id: str, request_id: str
    ) -> DocumentTemplate | None:
        try:
            stmt = select(DocumentTemplateModel).where(
                DocumentTemplateModel.agent_id == agent_id,
                DocumentTemplateModel.worker_id == worker_id,
                DocumentTemplateModel.status == TEMPLATE_STATUS_ACTIVE,
            )
            result = await self._session.execute(stmt)
            row = result.scalars().first()
            return self._to_domain(row) if row else None
        except Exception as e:
            self._logger.error(
                "DocumentTemplate find_active_by_agent_worker failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def soft_delete(self, template_id: str, request_id: str) -> None:
        self._logger.info(
            "DocumentTemplate soft_delete",
            request_id=request_id,
            template_id=template_id,
        )
        try:
            stmt = (
                update(DocumentTemplateModel)
                .where(DocumentTemplateModel.id == template_id)
                .values(
                    status=TEMPLATE_STATUS_DELETED,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
        except Exception as e:
            self._logger.error(
                "DocumentTemplate soft_delete failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def soft_delete_by_agent(self, agent_id: str, request_id: str) -> int:
        self._logger.info(
            "DocumentTemplate soft_delete_by_agent",
            request_id=request_id,
            agent_id=agent_id,
        )
        try:
            stmt = (
                update(DocumentTemplateModel)
                .where(
                    DocumentTemplateModel.agent_id == agent_id,
                    DocumentTemplateModel.status == TEMPLATE_STATUS_ACTIVE,
                )
                .values(
                    status=TEMPLATE_STATUS_DELETED,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            result = await self._session.execute(stmt)
            return result.rowcount or 0
        except Exception as e:
            self._logger.error(
                "DocumentTemplate soft_delete_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    @staticmethod
    def _to_orm(template: DocumentTemplate) -> DocumentTemplateModel:
        return DocumentTemplateModel(
            id=template.id,
            agent_id=template.agent_id,
            worker_id=template.worker_id,
            name=template.name,
            html_skeleton=template.html_skeleton,
            slots=[
                {
                    "key": s.key,
                    "label": s.label,
                    "slot_type": s.slot_type,
                    "description": s.description,
                    "fill_hint": s.fill_hint,
                    "sample_value": s.sample_value,
                }
                for s in template.slots
            ],
            source_file_ref=template.source_file_ref,
            source_format=template.source_format,
            status=template.status,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    @staticmethod
    def _to_domain(row: DocumentTemplateModel) -> DocumentTemplate:
        return DocumentTemplate(
            id=row.id,
            agent_id=row.agent_id,
            worker_id=row.worker_id,
            name=row.name,
            html_skeleton=row.html_skeleton,
            slots=[
                TemplateSlot(
                    key=item["key"],
                    label=item["label"],
                    slot_type=item["slot_type"],
                    description=item.get("description", ""),
                    fill_hint=item.get("fill_hint", ""),
                    sample_value=item.get("sample_value", ""),
                )
                for item in (row.slots or [])
            ],
            source_file_ref=row.source_file_ref,
            source_format=row.source_format,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
