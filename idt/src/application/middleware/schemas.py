"""builtin-middleware D4: 미들웨어 카탈로그 API 스키마."""
from pydantic import BaseModel

from src.domain.middleware.entities import MiddlewareCatalogEntry


class MiddlewareCatalogItemResponse(BaseModel):
    middleware_type: str
    name: str
    description: str
    is_builtin: bool
    is_enforced: bool
    default_config: dict
    is_active: bool
    sort_order: int

    @classmethod
    def from_entity(
        cls, entry: MiddlewareCatalogEntry
    ) -> "MiddlewareCatalogItemResponse":
        return cls(
            middleware_type=entry.middleware_type.value,
            name=entry.name,
            description=entry.description,
            is_builtin=entry.is_builtin,
            is_enforced=entry.is_enforced,
            default_config=entry.default_config,
            is_active=entry.is_active,
            sort_order=entry.sort_order,
        )


class MiddlewareCatalogListResponse(BaseModel):
    middlewares: list[MiddlewareCatalogItemResponse]


class SetMiddlewareFlagsRequest(BaseModel):
    """부분 갱신 — None = 미변경."""

    is_builtin: bool | None = None
    is_enforced: bool | None = None
    default_config: dict | None = None
