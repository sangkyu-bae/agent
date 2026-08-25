"""BlueprintAdminUseCase — blueprint 라이브러리 CRUD·에셋·폰트.

Design Ref: golden-sample-blueprint §4.1 / §7 (에셋 MIME·크기·개수 가드) / §6.1
- 저장은 추출 결과를 관리자가 편집한 DocumentBlueprint + 에셋 바이트를 받는다.
- PUT 은 편집 가능한 필드만 반영하고 id/source_kind/page_count/created_at 은 유지.
- 검증 실패 → BlueprintValidationError(400), 없음 → BlueprintNotFoundError(404).
- blueprint-style-fidelity §4.3: update 는 schema_version 을 CURRENT 로 승격(DR-5),
  reextract 는 같은 id 에 추출 결과를 덮어쓴다(에셋 교체, 이름·설명·생성일 보존).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.domain.blueprint.errors import (
    BlueprintNotFoundError,
    BlueprintValidationError,
)
from src.domain.blueprint.interfaces import (
    BlueprintRepository,
    FontCatalogPort,
    StoredAsset,
)
from src.domain.blueprint.value_objects import (
    CURRENT_SCHEMA_VERSION,
    DocumentBlueprint,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

if TYPE_CHECKING:
    from src.application.blueprint.extraction_use_case import (
        BlueprintExtractionUseCase,
    )

MAX_ASSETS = 20
MAX_ASSET_BYTES = 2 * 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


@dataclass(frozen=True)
class FontsView:
    installed: tuple[str, ...]
    default: str


class BlueprintAdminUseCase:
    def __init__(
        self,
        repo: BlueprintRepository,
        fonts: FontCatalogPort,
        logger: LoggerInterface,
        extraction: BlueprintExtractionUseCase | None = None,
    ) -> None:
        self._repo = repo
        self._fonts = fonts
        self._logger = logger
        self._extraction = extraction

    async def create(
        self,
        blueprint: DocumentBlueprint,
        asset_bytes: Mapping[str, bytes],
        created_by: str,
    ) -> DocumentBlueprint:
        stored = _validate_assets(blueprint, asset_bytes)
        now = datetime.now(UTC)
        bp = replace(blueprint, created_at=now, updated_at=now)
        await self._repo.save(bp, stored, created_by)
        self._logger.info(
            "blueprint.create", blueprint_id=bp.id, name=bp.name, created_by=created_by
        )
        return bp

    async def get(self, blueprint_id: str) -> DocumentBlueprint:
        bp = await self._repo.find_by_id(blueprint_id)
        if bp is None:
            raise BlueprintNotFoundError(f"blueprint '{blueprint_id}' not found")
        return bp

    async def list(self, include_inactive: bool = True) -> list[DocumentBlueprint]:
        return await self._repo.list_all(include_inactive=include_inactive)

    async def options(self) -> list[tuple[str, str]]:
        """에이전트 빌더 드롭다운용 (active 만)."""
        return [
            (b.id, b.name) for b in await self._repo.list_all(include_inactive=False)
        ]

    async def update(
        self, blueprint_id: str, edited: DocumentBlueprint
    ) -> DocumentBlueprint:
        current = await self.get(blueprint_id)
        known = {a.id for a in current.assets}
        unknown = {a.id for a in edited.assets} - known
        if unknown:
            raise BlueprintValidationError(
                f"assets cannot be added via update: {sorted(unknown)}"
            )
        merged = replace(
            edited,
            id=current.id,
            source_kind=current.source_kind,
            page_count=current.page_count,
            schema_version=CURRENT_SCHEMA_VERSION,  # DR-5: 쓰기 경계에서 승격
            created_at=current.created_at,
            updated_at=datetime.now(UTC),
        )
        await self._repo.update(merged)
        return merged

    async def reextract(
        self,
        blueprint_id: str,
        data: bytes,
        filename: str,
        max_pages: int,
        request_id: str,
    ) -> DocumentBlueprint:
        """같은 id 로 재추출 — 에셋 교체, 이름·설명·상태·생성일 보존 (§4.3)."""
        if self._extraction is None:
            raise RuntimeError("reextract requires an extraction use case")
        current = await self.get(blueprint_id)
        outcome = await self._extraction.run(data, filename, max_pages, request_id)
        merged = replace(
            outcome.blueprint,
            id=current.id,
            name=current.name,
            description=current.description,
            status=current.status,
            created_at=current.created_at,
            updated_at=datetime.now(UTC),
        )
        await self._repo.replace(merged, outcome.assets)
        self._logger.info(
            "blueprint.reextract",
            blueprint_id=merged.id,
            schema_version=merged.schema_version,
            assets=len(merged.assets),
            warnings=len(merged.warnings),
        )
        return merged

    async def deactivate(self, blueprint_id: str) -> DocumentBlueprint:
        current = await self.get(blueprint_id)
        updated = replace(current, status="inactive", updated_at=datetime.now(UTC))
        await self._repo.update(updated)
        self._logger.info("blueprint.deactivate", blueprint_id=blueprint_id)
        return updated

    async def asset(self, blueprint_id: str, asset_id: str) -> StoredAsset:
        stored = await self._repo.load_asset(blueprint_id, asset_id)
        if stored is None:
            raise BlueprintNotFoundError(f"asset '{asset_id}' not found")
        return stored

    def fonts(self) -> FontsView:
        return FontsView(
            installed=self._fonts.installed(), default=self._fonts.default_font()
        )


def _validate_assets(
    blueprint: DocumentBlueprint, asset_bytes: Mapping[str, bytes]
) -> list[StoredAsset]:
    if len(blueprint.assets) > MAX_ASSETS:
        raise BlueprintValidationError(f"too many assets (> {MAX_ASSETS})")
    stored: list[StoredAsset] = []
    for asset in blueprint.assets:
        data = asset_bytes.get(asset.id)
        if data is None:
            raise BlueprintValidationError(f"asset '{asset.id}' has no data")
        if len(data) > MAX_ASSET_BYTES:
            raise BlueprintValidationError(f"asset '{asset.id}' exceeds 2MB")
        if not (data.startswith(_PNG) or data.startswith(_JPEG)):
            raise BlueprintValidationError(f"asset '{asset.id}' must be PNG or JPEG")
        stored.append(StoredAsset(asset=asset, data=data))
    return stored
