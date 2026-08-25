"""BlueprintRepository — document_blueprint / _asset MySQL 영속화.

Design Ref: golden-sample-blueprint §3.3 / §9.3 BlueprintRepository
- 세션 주입, commit/rollback 금지(UseCase 단일 세션 규칙, docs/rules/db-session.md).
- blueprint_json 은 domain serialization 이 단일 출처. 에셋 메타(adopted 포함)는
  blueprint_json 의 assets 와 asset 행 양쪽에 있으며 asset 행이 바이트의 출처.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.blueprint.errors import BlueprintNotFoundError
from src.domain.blueprint.font_normalization import normalize_blueprint_fonts
from src.domain.blueprint.interfaces import StoredAsset
from src.domain.blueprint.serialization import (
    blueprint_from_dict,
    blueprint_to_dict,
)
from src.domain.blueprint.value_objects import BlueprintAsset, DocumentBlueprint, RelBox
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.blueprint.models import (
    DocumentBlueprintAssetModel,
    DocumentBlueprintModel,
)


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


class BlueprintRepository:
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self,
        blueprint: DocumentBlueprint,
        assets: Sequence[StoredAsset],
        created_by: str,
    ) -> None:
        row = DocumentBlueprintModel(
            id=blueprint.id,
            name=blueprint.name,
            description=blueprint.description,
            source_kind=blueprint.source_kind,
            page_count=blueprint.page_count,
            schema_version=blueprint.schema_version,
            blueprint_json=blueprint_to_dict(blueprint),
            status=blueprint.status,
            created_by=created_by,
            created_at=_naive(blueprint.created_at),
            updated_at=_naive(blueprint.updated_at),
        )
        self._session.add(row)
        for stored in assets:
            self._session.add(_asset_row(blueprint.id, stored))
        await self._session.flush()
        self._logger.info(
            "Blueprint saved",
            blueprint_id=blueprint.id,
            assets=len(assets),
            created_by=created_by,
        )

    async def update(self, blueprint: DocumentBlueprint) -> None:
        row = await self._session.get(DocumentBlueprintModel, blueprint.id)
        if row is None:
            raise BlueprintNotFoundError(f"blueprint '{blueprint.id}' not found")
        row.name = blueprint.name
        row.description = blueprint.description
        row.status = blueprint.status
        row.schema_version = blueprint.schema_version
        row.blueprint_json = blueprint_to_dict(blueprint)
        row.updated_at = _naive(blueprint.updated_at)
        adopted = {a.id: a.adopted for a in blueprint.assets}
        for asset_row in await self._asset_rows(blueprint.id):
            if asset_row.id in adopted:
                asset_row.adopted = adopted[asset_row.id]
        await self._session.flush()
        self._logger.info("Blueprint updated", blueprint_id=blueprint.id)

    async def replace(
        self, blueprint: DocumentBlueprint, assets: Mapping[str, bytes]
    ) -> None:
        """재추출 결과로 덮어쓰기 (style-fidelity §4.3): 에셋 행 delete+insert."""
        row = await self._session.get(DocumentBlueprintModel, blueprint.id)
        if row is None:
            raise BlueprintNotFoundError(f"blueprint '{blueprint.id}' not found")
        row.name = blueprint.name
        row.description = blueprint.description
        row.status = blueprint.status
        row.page_count = blueprint.page_count
        row.schema_version = blueprint.schema_version
        row.blueprint_json = blueprint_to_dict(blueprint)
        row.updated_at = _naive(blueprint.updated_at)
        await self._session.execute(
            delete(DocumentBlueprintAssetModel).where(
                DocumentBlueprintAssetModel.blueprint_id == blueprint.id
            )
        )
        for asset in blueprint.assets:
            if asset.id in assets:
                stored = StoredAsset(asset=asset, data=assets[asset.id])
                self._session.add(_asset_row(blueprint.id, stored))
        await self._session.flush()
        self._logger.info(
            "Blueprint replaced",
            blueprint_id=blueprint.id,
            assets=len(blueprint.assets),
            schema_version=blueprint.schema_version,
        )

    async def find_by_id(self, blueprint_id: str) -> DocumentBlueprint | None:
        row = await self._session.get(DocumentBlueprintModel, blueprint_id)
        return None if row is None else _to_domain(row)

    async def list_all(self, include_inactive: bool) -> list[DocumentBlueprint]:
        stmt = select(DocumentBlueprintModel).order_by(
            DocumentBlueprintModel.updated_at.desc()
        )
        if not include_inactive:
            stmt = stmt.where(DocumentBlueprintModel.status == "active")
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def load_asset(self, blueprint_id: str, asset_id: str) -> StoredAsset | None:
        row = await self._session.get(DocumentBlueprintAssetModel, asset_id)
        if row is None or row.blueprint_id != blueprint_id:
            return None
        return StoredAsset(asset=_asset_to_domain(row), data=bytes(row.data))

    async def load_assets(self, blueprint_id: str) -> dict[str, bytes]:
        return {r.id: bytes(r.data) for r in await self._asset_rows(blueprint_id)}

    async def _asset_rows(self, blueprint_id: str) -> list[DocumentBlueprintAssetModel]:
        stmt = select(DocumentBlueprintAssetModel).where(
            DocumentBlueprintAssetModel.blueprint_id == blueprint_id
        )
        return list((await self._session.execute(stmt)).scalars().all())


def _asset_row(blueprint_id: str, stored: StoredAsset) -> DocumentBlueprintAssetModel:
    a = stored.asset
    return DocumentBlueprintAssetModel(
        id=a.id,
        blueprint_id=blueprint_id,
        kind=a.kind,
        mime=a.mime,
        width=a.width,
        height=a.height,
        sha256=a.sha256,
        box_json={"x": a.box.x, "y": a.box.y, "w": a.box.w, "h": a.box.h},
        adopted=a.adopted,
        data=stored.data,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


def _asset_to_domain(row: DocumentBlueprintAssetModel) -> BlueprintAsset:
    b = row.box_json
    return BlueprintAsset(
        id=row.id,
        kind=row.kind,
        mime=row.mime,
        width=row.width,
        height=row.height,
        sha256=row.sha256,
        box=RelBox(float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])),
        adopted=bool(row.adopted),
    )


def _to_domain(row: DocumentBlueprintModel) -> DocumentBlueprint:
    data = dict(row.blueprint_json)
    # 컬럼이 진실인 필드는 컬럼 값으로 덮는다 (name/status 등은 PUT 으로 바뀜)
    data.update(
        id=row.id,
        name=row.name,
        description=row.description,
        status=row.status,
        schema_version=row.schema_version,
    )
    # Design Ref: blueprint-font-mapping-migration DR-1 — 읽기 경계 정규화.
    # blueprint_from_dict 는 순수 변환으로 두고, 정규화는 여기서 명시 호출한다.
    return normalize_blueprint_fonts(blueprint_from_dict(data))


class SessionScopedBlueprintRepository:
    """매 호출마다 새 세션을 열어 BlueprintRepository 에 위임 (에이전트 런타임용).

    SessionScopedDocumentGenerationTypeRepository 동형 — 그래프 노드는 요청 세션이 없다.
    읽기 전용(find_by_id / load_assets)만 노출한다.
    """

    def __init__(self, session_factory, logger: LoggerInterface) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def find_by_id(self, blueprint_id: str) -> DocumentBlueprint | None:
        async with self._session_factory() as session:
            return await BlueprintRepository(session, self._logger).find_by_id(
                blueprint_id
            )

    async def load_assets(self, blueprint_id: str) -> dict[str, bytes]:
        async with self._session_factory() as session:
            return await BlueprintRepository(session, self._logger).load_assets(
                blueprint_id
            )
