"""Wiki API 스키마: Request/Response Pydantic 모델 + 매핑 (LLM-WIKI-001)."""
from datetime import datetime

from pydantic import BaseModel, Field

from src.domain.wiki.entity import WikiArticle


class DistillRequest(BaseModel):
    agent_id: str
    collection_name: str
    max_articles: int = Field(default=50, ge=1, le=500)


class WikiArticleResponse(BaseModel):
    id: str
    agent_id: str
    title: str
    content: str
    source_type: str
    source_refs: list[str]
    status: str
    confidence: float
    valid_until: datetime | None
    version: int
    editor_id: str | None
    reviewer_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
    path: str | None = None


class DistillResponse(BaseModel):
    agent_id: str
    created_count: int
    items: list[WikiArticleResponse]


class ListWikiResponse(BaseModel):
    items: list[WikiArticleResponse]
    total: int


class ReviewActionRequest(BaseModel):
    reviewer_id: str


class EditWikiRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    editor_id: str | None = None  # 하위호환 수용 — 서버는 인증 사용자를 기록한다
    path: str | None = None


class CreateWikiRequest(BaseModel):
    """소유자 직접 작성 (wiki-user-facing) — source_type=human, 즉시 approved."""

    agent_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    path: str | None = None
    valid_until: datetime | None = None


class WikiTreeItemResponse(BaseModel):
    id: str
    title: str
    status: str
    source_type: str
    updated_at: datetime | None


class WikiTreeGroupResponse(BaseModel):
    path: str | None  # None = 미분류
    items: list[WikiTreeItemResponse]


class WikiTreeResponse(BaseModel):
    agent_id: str
    groups: list[WikiTreeGroupResponse]
    total: int


def to_response(article: WikiArticle) -> WikiArticleResponse:
    """도메인 엔티티 → API 응답 DTO."""
    return WikiArticleResponse(
        id=article.id,
        agent_id=article.agent_id,
        title=article.title,
        content=article.content,
        source_type=article.source_type.value,
        source_refs=article.source_refs,
        status=article.status.value,
        confidence=article.confidence,
        valid_until=article.valid_until,
        version=article.version,
        editor_id=article.editor_id,
        reviewer_id=article.reviewer_id,
        created_at=article.created_at,
        updated_at=article.updated_at,
        path=article.path,
    )
