"""BlueprintRepository — aiosqlite (Design §9.1 / db-session 규칙: commit 금지)."""

from __future__ import annotations

import inspect
import os
import tempfile
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.domain.blueprint.errors import BlueprintNotFoundError
from src.domain.blueprint.interfaces import StoredAsset
from src.domain.blueprint.value_objects import (
    BlueprintAsset,
    DocumentBlueprint,
    HeaderFooter,
    Narrative,
    NarrativeSection,
    PagePattern,
    PatternKind,
    RelBox,
    Slot,
    SlotKind,
    StyleTokens,
    TableStyle,
)
from src.infrastructure.blueprint.models import (  # noqa: F401 — metadata 등록
    DocumentBlueprintAssetModel,
    DocumentBlueprintModel,
)
from src.infrastructure.blueprint.repository import BlueprintRepository
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            async with s.begin():
                yield s
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _bp(bid="b1", name="샘플", status="active") -> DocumentBlueprint:
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    asset = BlueprintAsset(
        "a1", "logo", "image/png", 10, 5, "f" * 64, RelBox(0.8, 0.02, 0.1, 0.05), True
    )
    slot = Slot(
        "title", SlotKind.TITLE, RelBox(0.1, 0.1, 0.8, 0.2), "t", 40, None, None
    )
    return DocumentBlueprint(
        id=bid,
        name=name,
        description="",
        schema_version=1,
        source_kind="pdf",
        page_count=1,
        style=StyleTokens(
            (13.333, 7.5),
            {"heading": "H", "body": "B"},
            {"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0},
            {
                "primary": "#1F3A5F",
                "accent1": "#E07A1F",
                "text": "#222222",
                "bg": "#FFFFFF",
            },
            TableStyle("#1F3A5F", "#FFFFFF", "#CCCCCC", False),
            HeaderFooter("a1", "{n}", ""),
        ),
        patterns=(PagePattern("p1", PatternKind.COVER, (slot,), None, 1, ""),),
        narrative=Narrative((NarrativeSection("표지", ("p1",), ""),), "", "ko"),
        assets=(asset,),
        font_mapping={"H": "X"},
        warnings=(),
        status=status,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_save_and_find_roundtrip_with_assets(session):
    repo = BlueprintRepository(session, MagicMock())
    bp = _bp()
    await repo.save(bp, [StoredAsset(bp.assets[0], b"\x89PNGlogo")], created_by="u1")
    loaded = await repo.find_by_id("b1")
    assert loaded == bp
    stored = await repo.load_asset("b1", "a1")
    assert stored is not None and stored.data == b"\x89PNGlogo"
    assert stored.asset == bp.assets[0]
    assert await repo.load_assets("b1") == {"a1": b"\x89PNGlogo"}
    assert await repo.load_asset("b1", "nope") is None


@pytest.mark.asyncio
async def test_list_and_inactive_filter(session):
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_bp("b1", "A"), [], "u")
    await repo.save(_bp("b2", "B", status="inactive"), [], "u")
    active = await repo.list_all(include_inactive=False)
    assert [b.id for b in active] == ["b1"]
    both = await repo.list_all(include_inactive=True)
    assert sorted(b.id for b in both) == ["b1", "b2"]


@pytest.mark.asyncio
async def test_update_changes_json_status_and_adopted(session):
    repo = BlueprintRepository(session, MagicMock())
    bp = _bp()
    await repo.save(bp, [StoredAsset(bp.assets[0], b"x")], "u")
    edited = replace(
        bp,
        name="수정",
        status="inactive",
        font_mapping={"H": "Y"},
        assets=(replace(bp.assets[0], adopted=False),),
    )
    await repo.update(edited)
    loaded = await repo.find_by_id("b1")
    assert loaded.name == "수정" and loaded.status == "inactive"
    assert loaded.font_mapping == {"H": "Y"} and loaded.assets[0].adopted is False
    assert (await repo.load_asset("b1", "a1")).asset.adopted is False


@pytest.mark.asyncio
async def test_find_missing_returns_none_and_update_missing_raises(session):
    repo = BlueprintRepository(session, MagicMock())
    assert await repo.find_by_id("zzz") is None
    with pytest.raises(BlueprintNotFoundError):
        await repo.update(_bp("zzz"))


def test_repository_never_commits():
    src = inspect.getsource(BlueprintRepository)
    assert "commit(" not in src and "rollback(" not in src


# ── blueprint-style-fidelity §4.3 — replace (재추출: 에셋 교체) ──────────────


@pytest.mark.asyncio
async def test_replace_swaps_assets_and_rewrites_json_and_version(session):
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_bp(), [StoredAsset(_bp().assets[0], b"\x89PNG-old")], "u")

    new_asset = BlueprintAsset(
        "a2", "logo", "image/png", 20, 8, "e" * 64, RelBox(0.83, 0.04, 0.12, 0.07), True
    )
    updated = replace(
        _bp(),
        schema_version=2,
        assets=(new_asset,),
        style=replace(
            _bp().style, header_footer=HeaderFooter("a2", "{n} / {total}", "푸터")
        ),
        updated_at=datetime(2026, 8, 23, tzinfo=UTC),
    )
    await repo.replace(updated, {"a2": b"\x89PNG-new"})

    found = await repo.find_by_id("b1")
    assert found is not None and found.schema_version == 2
    assert [a.id for a in found.assets] == ["a2"]
    assert found.style.header_footer.footer_text == "푸터"
    assert await repo.load_assets("b1") == {"a2": b"\x89PNG-new"}
    assert await repo.load_asset("b1", "a1") is None


@pytest.mark.asyncio
async def test_replace_missing_raises(session):
    repo = BlueprintRepository(session, MagicMock())
    with pytest.raises(BlueprintNotFoundError):
        await repo.replace(_bp(bid="nope"), {})


# ── blueprint-font-mapping-migration §8.3 — 읽기 경계 정규화 (FR-01/03) ─────

_POLLUTED_FONTS = {"heading": "Malgun Gothic Bold", "body": "Malgun Gothic Regular"}
_IDENTITY_MAPPING = {
    "Malgun Gothic Bold": "Malgun Gothic Bold",
    "Malgun Gothic Regular": "Malgun Gothic Regular",
}


def _polluted(bid="poll1") -> DocumentBlueprint:
    """FR-01 이전에 추출·저장된 형태 — 서브패밀리명 + 항등 매핑."""
    bp = _bp(bid=bid)
    return replace(
        bp,
        style=replace(bp.style, fonts=dict(_POLLUTED_FONTS)),
        font_mapping=dict(_IDENTITY_MAPPING),
    )


@pytest.mark.asyncio
async def test_find_by_id_normalizes_polluted_fonts(session):
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_polluted(), [], "u1")

    loaded = await repo.find_by_id("poll1")

    assert loaded is not None
    assert loaded.style.fonts == {"heading": "Malgun Gothic", "body": "Malgun Gothic"}
    assert loaded.font_mapping == {"Malgun Gothic": "Malgun Gothic"}


@pytest.mark.asyncio
async def test_list_all_normalizes_every_row(session):
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_polluted("poll1"), [], "u1")
    await repo.save(_polluted("poll2"), [], "u1")

    rows = await repo.list_all(include_inactive=True)

    assert len(rows) == 2
    for bp in rows:
        assert set(bp.style.fonts.values()) == {"Malgun Gothic"}


@pytest.mark.asyncio
async def test_update_persists_normalized_fonts(session):
    """FR-03 쓰기 승격 — 읽어서 저장하면 blueprint_json 이 정리된다."""
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_polluted(), [], "u1")

    loaded = await repo.find_by_id("poll1")
    assert loaded is not None
    await repo.update(loaded)

    row = await session.get(DocumentBlueprintModel, "poll1")
    assert row.blueprint_json["style"]["fonts"]["heading"] == "Malgun Gothic"
    assert row.blueprint_json["font_mapping"] == {"Malgun Gothic": "Malgun Gothic"}


@pytest.mark.asyncio
async def test_v1_schema_version_is_preserved_through_normalization(session):
    """정규화는 schema_version 을 승격하지 않는다 (DR-5 는 UseCase 책임)."""
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_polluted(), [], "u1")

    loaded = await repo.find_by_id("poll1")

    assert loaded is not None and loaded.schema_version == 1


@pytest.mark.asyncio
async def test_already_clean_blueprint_survives_load_unchanged(session):
    repo = BlueprintRepository(session, MagicMock())
    await repo.save(_bp(), [], "u1")

    loaded = await repo.find_by_id("b1")

    assert loaded is not None
    assert loaded.style.fonts == {"heading": "H", "body": "B"}
    assert loaded.font_mapping == {"H": "X"}
