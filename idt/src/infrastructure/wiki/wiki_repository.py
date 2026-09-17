"""WikiArticleRepository: MySQL(SoT) + Qdrant(벡터) 합성 저장소 (LLM-WIKI-001).

- MySQL: 메타데이터/라이프사이클의 Source of Truth (MySQLBaseRepository 재사용)
- Qdrant: 본문 임베딩 색인. search_similar는 벡터 검색 후 MySQL로 하이드레이션하고
  도메인 is_searchable(승인+미만료)로 최종 필터한다(상태는 MySQL이 권위).
ES(BM25) 색인은 현재 검색 경로(벡터)에서 미사용 → 후속 도입.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.repositories.wiki_repository import WikiArticleRepository as _Interface
from src.application.wiki.schemas import WikiTreeItem
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLQueryCondition
from src.domain.vector.entities import Document
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.vector.value_objects import DocumentId, SearchFilter
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository
from src.infrastructure.wiki.models import WikiArticleModel


def _to_model(entity: WikiArticle) -> WikiArticleModel:
    return WikiArticleModel(
        id=entity.id,
        agent_id=entity.agent_id,
        title=entity.title,
        content=entity.content,
        source_type=entity.source_type.value,
        source_refs=entity.source_refs,
        status=entity.status.value,
        confidence=entity.confidence,
        valid_until=entity.valid_until,
        version=entity.version,
        editor_id=entity.editor_id,
        reviewer_id=entity.reviewer_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        path=entity.path,
    )


def _apply_fields(row: WikiArticleModel, article: WikiArticle) -> None:
    """기존 ORM 행에 엔티티 값을 반영한다(id/created_at은 불변)."""
    row.agent_id = article.agent_id
    row.title = article.title
    row.content = article.content
    row.source_type = article.source_type.value
    row.source_refs = article.source_refs
    row.status = article.status.value
    row.confidence = article.confidence
    row.valid_until = article.valid_until
    row.version = article.version
    row.editor_id = article.editor_id
    row.reviewer_id = article.reviewer_id
    row.updated_at = article.updated_at
    row.path = article.path


def _to_entity(model: WikiArticleModel) -> WikiArticle:
    return WikiArticle(
        id=model.id,
        agent_id=model.agent_id,
        title=model.title,
        content=model.content,
        source_type=WikiSourceType(model.source_type),
        source_refs=list(model.source_refs or []),
        status=WikiStatus(model.status),
        confidence=float(model.confidence),
        valid_until=model.valid_until,
        version=model.version,
        editor_id=model.editor_id,
        reviewer_id=model.reviewer_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        path=model.path,
    )


def _toc_columns(excerpt_chars: int) -> list:
    """프롬프트 목차용 경량 컬럼 목록 (wiki-guided-routing D1).

    excerpt_chars > 0이면 본문 앞부분을 SQL SUBSTRING으로만 잘라 `excerpt`로 싣는다.
    content 컬럼 자체는 SELECT하지 않는다 (경량 계약 유지).
    """
    columns = [
        WikiArticleModel.id,
        WikiArticleModel.title,
        WikiArticleModel.status,
        WikiArticleModel.source_type,
        WikiArticleModel.path,
        WikiArticleModel.updated_at,
    ]
    if excerpt_chars > 0:
        columns.append(
            func.substring(WikiArticleModel.content, 1, excerpt_chars).label("excerpt")
        )
    return columns


class WikiArticleRepository(MySQLBaseRepository[WikiArticleModel], _Interface):
    """위키 항목 영속화 + 벡터 색인/검색 구현체."""

    def __init__(
        self,
        session: AsyncSession,
        logger: LoggerInterface,
        embedding: EmbeddingInterface,
        vector_store: VectorStoreInterface,
        collection_name: str,
    ) -> None:
        super().__init__(session, WikiArticleModel, logger)
        self._embedding = embedding
        self._vector_store = vector_store
        self._collection = collection_name

    # ── base 위임 (테스트 패치 포인트) ─────────────────────────────

    async def _base_save(self, model: WikiArticleModel, request_id: str) -> WikiArticleModel:
        return await MySQLBaseRepository.save(self, model, request_id)

    async def _base_find_by_id(self, id: str, request_id: str) -> WikiArticleModel | None:
        return await MySQLBaseRepository.find_by_id(self, id, request_id)

    async def _base_find_by_conditions(
        self, conditions: list[MySQLQueryCondition], request_id: str
    ) -> list[WikiArticleModel]:
        return await MySQLBaseRepository.find_by_conditions(self, conditions, request_id)

    async def _base_delete(self, id: str, request_id: str) -> bool:
        return await MySQLBaseRepository.delete(self, id, request_id)

    # ── 인터페이스 구현 ────────────────────────────────────────────

    async def save(self, article: WikiArticle, request_id: str) -> WikiArticle:
        saved = await self._base_save(_to_model(article), request_id)
        await self._index_vector(article, request_id)
        return _to_entity(saved)

    async def update(self, article: WikiArticle, request_id: str) -> WikiArticle:
        # load-then-mutate: 기존 행을 조회해 필드를 갱신한다(새 객체 add 시 PK 중복 INSERT).
        row = await self._base_find_by_id(article.id, request_id)
        if row is None:
            raise ValueError(f"위키 항목을 찾을 수 없습니다: {article.id}")
        _apply_fields(row, article)
        await self._session.flush()
        await self._index_vector(article, request_id)
        return _to_entity(row)

    async def find_by_id(self, id: str, request_id: str) -> WikiArticle | None:
        model = await self._base_find_by_id(id, request_id)
        return _to_entity(model) if model else None

    async def find_by_agent(
        self, agent_id: str, request_id: str, status: WikiStatus | None = None
    ) -> list[WikiArticle]:
        conditions = [MySQLQueryCondition(field="agent_id", operator="eq", value=agent_id)]
        if status is not None:
            conditions.append(
                MySQLQueryCondition(field="status", operator="eq", value=status.value)
            )
        models = await self._base_find_by_conditions(conditions, request_id)
        return [_to_entity(m) for m in models]

    async def delete(self, id: str, request_id: str) -> bool:
        await self._vector_store.delete_by_ids([DocumentId(id)])
        return await self._base_delete(id, request_id)

    async def search_similar(
        self, agent_id: str, query: str, top_k: int, now: datetime, request_id: str
    ) -> list[WikiArticle]:
        vector = await self._embedding.embed_text(query)
        docs = await self._vector_store.search_by_vector(
            vector=vector,
            top_k=top_k,
            filter=SearchFilter(metadata={"agent_id": agent_id}),
            collection_name=self._collection,
        )
        ids = [d.id.value for d in docs if d.id is not None]
        if not ids:
            return []
        return await self._hydrate_searchable(ids, now, request_id)

    async def list_searchable_tree_items(
        self, agent_id: str, now: datetime, request_id: str,
        excerpt_chars: int = 0,
    ) -> list[WikiTreeItem]:
        """프롬프트 목차용: 승인+미만료만, 갱신 내림차순, 본문 미조회.

        wiki-agentic-navigation D7 — WHERE 절은 entity.is_searchable(now)의
        SQL 미러. 의미 변경 시 양쪽 동기 수정
        (test_wiki_repository_toc가 쿼리 문자열로 고정).

        Design Ref: wiki-guided-routing D1 — excerpt_chars > 0이면 본문 앞부분을
        SQL SUBSTRING으로만 잘라 온다. content 컬럼 자체는 여전히 SELECT하지 않는다
        (경량 계약 유지).
        """
        stmt = (
            select(*_toc_columns(excerpt_chars))
            .where(
                WikiArticleModel.agent_id == agent_id,
                WikiArticleModel.status == WikiStatus.APPROVED.value,
                (
                    WikiArticleModel.valid_until.is_(None)
                    | (WikiArticleModel.valid_until > now)
                ),
            )
            .order_by(WikiArticleModel.updated_at.desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            WikiTreeItem(
                id=r.id, title=r.title, status=r.status,
                source_type=r.source_type, path=r.path, updated_at=r.updated_at,
                excerpt=getattr(r, "excerpt", None),
            )
            for r in rows
        ]

    async def list_tree_items(
        self, agent_id: str, request_id: str
    ) -> list[WikiTreeItem]:
        """지식 트리용 경량 목록 — 본문(content) 미조회, path·최신순 정렬.

        knowledge-deprecate-visibility — 폐기(deprecated) 문서는 트리에서
        제외한다(복원은 관리자 WikiPage의 list API 소관). draft는 노출 유지.
        의미 변경 시 test_wiki_repository_tree가 쿼리 문자열로 고정.
        """
        stmt = (
            select(
                WikiArticleModel.id,
                WikiArticleModel.title,
                WikiArticleModel.status,
                WikiArticleModel.source_type,
                WikiArticleModel.path,
                WikiArticleModel.updated_at,
            )
            .where(
                WikiArticleModel.agent_id == agent_id,
                WikiArticleModel.status != WikiStatus.DEPRECATED.value,
            )
            .order_by(
                WikiArticleModel.path.is_(None),
                WikiArticleModel.path,
                WikiArticleModel.updated_at.desc(),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            WikiTreeItem(
                id=r.id, title=r.title, status=r.status,
                source_type=r.source_type, path=r.path, updated_at=r.updated_at,
            )
            for r in rows
        ]

    # ── 내부 헬퍼 ──────────────────────────────────────────────────

    async def _index_vector(self, article: WikiArticle, request_id: str) -> None:
        """본문 임베딩을 wiki 컬렉션에 색인(상태/agent 메타 포함)."""
        vector = await self._embedding.embed_text(article.content)
        doc = Document(
            id=DocumentId(article.id),
            content=article.content,
            vector=vector,
            metadata={
                "agent_id": article.agent_id,
                "status": article.status.value,
                "source_type": article.source_type.value,
                "title": article.title,
            },
        )
        await self._vector_store.add_documents([doc])

    async def _hydrate_searchable(
        self, ids: list[str], now: datetime, request_id: str
    ) -> list[WikiArticle]:
        """벡터 hit id를 MySQL로 하이드레이션 후 검색가능 항목만 벡터 순서로 반환."""
        conditions = [MySQLQueryCondition(field="id", operator="in", value=ids)]
        models = await self._base_find_by_conditions(conditions, request_id)
        by_id = {m.id: _to_entity(m) for m in models}
        ordered = [by_id[i] for i in ids if i in by_id]
        return [a for a in ordered if a.is_searchable(now)]
