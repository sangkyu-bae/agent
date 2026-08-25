"""BlueprintAdminUseCase (Design §4.1 / §7 에셋 가드 / §6.1 오류)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.application.blueprint.admin_use_case import BlueprintAdminUseCase
from src.domain.blueprint.errors import (
    BlueprintNotFoundError,
    BlueprintValidationError,
)
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

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class MemRepo:
    def __init__(self):
        self.rows: dict[str, DocumentBlueprint] = {}
        self.assets: dict[tuple[str, str], StoredAsset] = {}

    async def save(self, bp, assets, created_by):
        self.rows[bp.id] = bp
        for s in assets:
            self.assets[(bp.id, s.asset.id)] = s

    async def update(self, bp):
        if bp.id not in self.rows:
            raise BlueprintNotFoundError(bp.id)
        self.rows[bp.id] = bp

    async def find_by_id(self, bid):
        return self.rows.get(bid)

    async def list_all(self, include_inactive):
        return [
            b for b in self.rows.values() if include_inactive or b.status == "active"
        ]

    async def load_asset(self, bid, aid):
        return self.assets.get((bid, aid))

    async def load_assets(self, bid):
        return {k[1]: v.data for k, v in self.assets.items() if k[0] == bid}


class Fonts:
    def installed(self):
        return ("NanumGothic",)

    def default_font(self):
        return "NanumGothic"

    def suggest(self, f):
        return None


def _bp(bid="b1", assets=()) -> DocumentBlueprint:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    slot = Slot(
        "title", SlotKind.TITLE, RelBox(0.1, 0.1, 0.8, 0.2), "t", 40, None, None
    )
    return DocumentBlueprint(
        id=bid,
        name="n",
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
            HeaderFooter(None, "{n}", ""),
        ),
        patterns=(PagePattern("p1", PatternKind.COVER, (slot,), None, 1, ""),),
        narrative=Narrative((NarrativeSection("표지", ("p1",), ""),), "", "ko"),
        assets=tuple(assets),
        font_mapping={},
        warnings=(),
        status="active",
        created_at=now,
        updated_at=now,
    )


def _asset(aid="a1") -> BlueprintAsset:
    return BlueprintAsset(
        aid, "logo", "image/png", 10, 5, "f" * 64, RelBox(0.8, 0.02, 0.1, 0.05), True
    )


def _uc(repo=None) -> tuple[BlueprintAdminUseCase, MemRepo]:
    repo = repo or MemRepo()
    return BlueprintAdminUseCase(repo, Fonts(), MagicMock()), repo


@pytest.mark.asyncio
async def test_create_stores_blueprint_and_assets_and_stamps_time():
    uc, repo = _uc()
    bp = _bp(assets=[_asset()])
    saved = await uc.create(bp, {"a1": PNG}, created_by="admin")
    assert saved.id == "b1" and saved.created_at > bp.created_at
    assert repo.assets[("b1", "a1")].data == PNG


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,msg",
    [
        ({}, "no data"),
        ({"a1": b"GIF89a"}, "PNG or JPEG"),
        ({"a1": PNG + b"0" * (2 * 1024 * 1024)}, "2MB"),
    ],
)
async def test_create_rejects_bad_assets(payload, msg):
    uc, _ = _uc()
    with pytest.raises(BlueprintValidationError, match=msg):
        await uc.create(_bp(assets=[_asset()]), payload, "admin")


@pytest.mark.asyncio
async def test_create_rejects_too_many_assets():
    uc, _ = _uc()
    assets = [_asset(f"a{i}") for i in range(21)]
    with pytest.raises(BlueprintValidationError, match="too many"):
        await uc.create(_bp(assets=assets), {a.id: PNG for a in assets}, "admin")


@pytest.mark.asyncio
async def test_get_list_options_and_not_found():
    uc, repo = _uc()
    await uc.create(_bp("b1"), {}, "u")
    await uc.create(replace(_bp("b2"), status="inactive"), {}, "u")
    assert (await uc.get("b1")).id == "b1"
    assert sorted(b.id for b in await uc.list()) == ["b1", "b2"]
    assert [b.id for b in await uc.list(include_inactive=False)] == ["b1"]
    assert await uc.options() == [("b1", "n")]
    with pytest.raises(BlueprintNotFoundError):
        await uc.get("zzz")


@pytest.mark.asyncio
async def test_update_keeps_immutable_fields_and_rejects_new_assets():
    uc, repo = _uc()
    await uc.create(_bp(assets=[_asset()]), {"a1": PNG}, "u")
    edited = replace(
        _bp(assets=[replace(_asset(), adopted=False)]),
        id="other",
        name="수정",
        source_kind="pptx",
        page_count=99,
        font_mapping={"H": "Z"},
    )
    out = await uc.update("b1", edited)
    assert out.id == "b1" and out.source_kind == "pdf" and out.page_count == 1
    assert (
        out.name == "수정"
        and out.font_mapping == {"H": "Z"}
        and out.assets[0].adopted is False
    )
    with pytest.raises(BlueprintValidationError, match="cannot be added"):
        await uc.update("b1", _bp(assets=[_asset("new")]))


@pytest.mark.asyncio
async def test_deactivate_and_asset_lookup():
    uc, repo = _uc()
    await uc.create(_bp(assets=[_asset()]), {"a1": PNG}, "u")
    assert (await uc.deactivate("b1")).status == "inactive"
    assert (await uc.asset("b1", "a1")).data == PNG
    with pytest.raises(BlueprintNotFoundError):
        await uc.asset("b1", "nope")
    assert uc.fonts().default == "NanumGothic"


# ── blueprint-style-fidelity §4.3 — update 승격 / reextract ─────────────────

from src.domain.blueprint.value_objects import CURRENT_SCHEMA_VERSION  # noqa: E402


async def _replace(self, bp, assets):
    if bp.id not in self.rows:
        raise BlueprintNotFoundError(bp.id)
    self.rows[bp.id] = bp
    for k in [k for k in self.assets if k[0] == bp.id]:
        del self.assets[k]
    for a in bp.assets:
        self.assets[(bp.id, a.id)] = StoredAsset(a, assets[a.id])


MemRepo.replace = _replace


@pytest.mark.asyncio
async def test_update_promotes_schema_version_to_current():
    uc, repo = _uc()
    await uc.create(_bp(), {}, "u")
    assert repo.rows["b1"].schema_version == 1
    out = await uc.update("b1", _bp())
    assert out.schema_version == CURRENT_SCHEMA_VERSION


class FakeExtraction:
    def __init__(self, blueprint, assets):
        self.blueprint, self.assets, self.calls = blueprint, assets, []

    async def run(self, data, filename, max_pages, request_id):
        from src.application.blueprint.extraction_use_case import ExtractionOutcome

        self.calls.append((filename, max_pages, request_id))
        return ExtractionOutcome(self.blueprint, self.assets, (None,), (1, 0), {})


@pytest.mark.asyncio
async def test_reextract_keeps_identity_and_swaps_assets():
    uc, repo = _uc()
    original = replace(_bp(assets=[_asset()]), name="원본", description="설명")
    await uc.create(original, {"a1": PNG}, "u")
    created_at = repo.rows["b1"].created_at

    fresh = replace(
        _bp(bid="tmp", assets=[_asset("a9")]),
        schema_version=CURRENT_SCHEMA_VERSION,
        name="golden_sample_report",
        warnings=("w",),
    )
    extraction = FakeExtraction(fresh, {"a9": PNG})
    uc2 = BlueprintAdminUseCase(repo, Fonts(), MagicMock(), extraction=extraction)
    out = await uc2.reextract("b1", b"%PDF", "g.pdf", 20, "req")

    assert out.id == "b1" and out.name == "원본" and out.description == "설명"
    assert out.created_at == created_at and out.updated_at >= created_at
    assert out.schema_version == CURRENT_SCHEMA_VERSION
    assert [a.id for a in out.assets] == ["a9"] and out.warnings == ("w",)
    assert await repo.load_assets("b1") == {"a9": PNG}
    assert extraction.calls == [("g.pdf", 20, "req")]


@pytest.mark.asyncio
async def test_reextract_requires_extraction_dependency_and_existing_id():
    uc, _ = _uc()
    with pytest.raises(BlueprintNotFoundError):
        await BlueprintAdminUseCase(
            MemRepo(), Fonts(), MagicMock(), extraction=FakeExtraction(_bp(), {})
        ).reextract("nope", b"", "g.pdf", 20, "r")
    with pytest.raises(RuntimeError, match="extraction"):
        await uc.reextract("b1", b"", "g.pdf", 20, "r")
