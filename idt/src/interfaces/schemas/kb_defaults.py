"""kb-defaults 요청/응답 스키마 (agent-kb-quick-setup Design §4.2)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.application.kb_default_setting.use_case import KbDefaultsView
from src.domain.embedding_model.entity import EmbeddingModel


class KbDefaultsUpdateRequest(BaseModel):
    """PUT 전체 교체 — 해제(null)는 지원하지 않는다 (Design §4.2)."""

    model_config = ConfigDict(extra="forbid")

    default_embedding_model_id: int = Field(ge=1)


class EmbeddingModelSummary(BaseModel):
    id: int
    provider: str
    model_name: str
    display_name: str
    vector_dimension: int
    is_active: bool

    @classmethod
    def from_domain(cls, m: EmbeddingModel) -> "EmbeddingModelSummary":
        return cls(
            id=m.id,
            provider=m.provider,
            model_name=m.model_name,
            display_name=m.display_name,
            vector_dimension=m.vector_dimension,
            is_active=m.is_active,
        )


class KbDefaultsResponse(BaseModel):
    configured: bool
    default_embedding_model_id: int | None
    model: EmbeddingModelSummary | None
    warnings: list[str]
    updated_at: datetime | None

    @classmethod
    def from_view(cls, v: KbDefaultsView) -> "KbDefaultsResponse":
        return cls(
            configured=v.configured,
            default_embedding_model_id=v.setting.default_embedding_model_id,
            model=EmbeddingModelSummary.from_domain(v.model) if v.model else None,
            warnings=list(v.warnings),
            updated_at=v.setting.updated_at,
        )


class KbDefaultsPublicResponse(BaseModel):
    """사용자용 축약 — 빌더 블록이 업로드 전 미설정 안내를 띄우기 위한 읽기 전용."""

    configured: bool
    default_embedding_model_id: int | None
    model_display_name: str | None

    @classmethod
    def from_view(cls, v: KbDefaultsView) -> "KbDefaultsPublicResponse":
        return cls(
            configured=v.configured,
            default_embedding_model_id=(
                v.setting.default_embedding_model_id if v.configured else None
            ),
            model_display_name=(
                v.model.display_name if v.configured and v.model else None
            ),
        )
