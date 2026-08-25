"""DocumentBlueprint ⇄ dict — blueprint_json 컬럼·API 응답 공용.

Design §3.3 / §8.2 schema_version. 순수 변환(표준 라이브러리만).
blueprint-style-fidelity §3.4: SCHEMA_VERSION=2. v1 은 읽기만 허용 — 새 키는
기본값으로 채우고 버전은 보존한다(DR-5, 승격은 쓰기 경계인 UseCase 책임).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from src.domain.blueprint.value_objects import (
    CURRENT_SCHEMA_VERSION,
    BlueprintAsset,
    Decoration,
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

SCHEMA_VERSION = CURRENT_SCHEMA_VERSION
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1, SCHEMA_VERSION})


def _listify(value: Any) -> Any:
    if isinstance(value, tuple | list):
        return [_listify(v) for v in value]
    if isinstance(value, dict):
        return {k: _listify(v) for k, v in value.items()}
    return value


def blueprint_to_dict(bp: DocumentBlueprint) -> dict[str, Any]:
    data = _listify(asdict(bp))
    data["created_at"] = bp.created_at.isoformat()
    data["updated_at"] = bp.updated_at.isoformat()
    data["style"]["slide_size"] = list(bp.style.slide_size)
    for p in data["patterns"]:
        p["kind"] = PatternKind(p["kind"]).value
        for s in p["slots"]:
            s["kind"] = SlotKind(s["kind"]).value
    return data


def blueprint_from_dict(data: dict[str, Any]) -> DocumentBlueprint:
    version = int(data.get("schema_version", 0))
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported blueprint schema_version {version}")
    return DocumentBlueprint(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        schema_version=version,
        source_kind=data["source_kind"],
        page_count=int(data["page_count"]),
        style=_style(data["style"]),
        patterns=tuple(_pattern(p) for p in data["patterns"]),
        narrative=_narrative(data["narrative"]),
        assets=tuple(_asset(a) for a in data.get("assets", [])),
        font_mapping=dict(data.get("font_mapping", {})),
        warnings=tuple(data.get("warnings", [])),
        status=data.get("status", "active"),
        created_at=_dt(data["created_at"]),
        updated_at=_dt(data["updated_at"]),
    )


def _dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _box(d: dict[str, Any]) -> RelBox:
    return RelBox(x=float(d["x"]), y=float(d["y"]), w=float(d["w"]), h=float(d["h"]))


def _opt_box(d: dict[str, Any] | None) -> RelBox | None:
    return None if d is None else _box(d)


def _decoration(d: dict[str, Any]) -> Decoration:
    return Decoration(
        id=d["id"],
        shape=d.get("shape", "rect"),
        box=_box(d["box"]),
        fill=d["fill"],
        line=d.get("line"),
    )


def _decorations(items: list[dict[str, Any]] | None) -> tuple[Decoration, ...]:
    return tuple(_decoration(d) for d in items or [])


def _style(d: dict[str, Any]) -> StyleTokens:
    ts, hf = d["table_style"], d["header_footer"]
    return StyleTokens(
        slide_size=(float(d["slide_size"][0]), float(d["slide_size"][1])),
        fonts=dict(d["fonts"]),
        sizes={k: float(v) for k, v in d["sizes"].items()},
        palette=dict(d["palette"]),
        table_style=TableStyle(
            ts["header_bg"], ts["header_text"], ts["border"], bool(ts["zebra"])
        ),
        header_footer=HeaderFooter(
            hf.get("logo_asset_id"),
            hf.get("page_number_format", ""),
            hf.get("footer_text", ""),
            footer_box=_opt_box(hf.get("footer_box")),
            page_number_box=_opt_box(hf.get("page_number_box")),
            footer_color=hf.get("footer_color"),
        ),
        common_decorations=_decorations(d.get("common_decorations")),
    )


def _slot(d: dict[str, Any]) -> Slot:
    return Slot(
        id=d["id"],
        kind=SlotKind(d["kind"]),
        box=_box(d["box"]),
        role=d.get("role", ""),
        max_chars=d.get("max_chars"),
        max_rows=d.get("max_rows"),
        asset_id=d.get("asset_id"),
        align=d.get("align", "left"),
    )


def _pattern(d: dict[str, Any]) -> PagePattern:
    return PagePattern(
        id=d["id"],
        kind=PatternKind(d["kind"]),
        slots=tuple(_slot(s) for s in d["slots"]),
        background=d.get("background"),
        sample_page=int(d.get("sample_page", 0)),
        notes=d.get("notes", ""),
        decorations=_decorations(d.get("decorations")),
    )


def _narrative(d: dict[str, Any]) -> Narrative:
    return Narrative(
        sections=tuple(
            NarrativeSection(s["role"], tuple(s["pattern_ids"]), s.get("guidance", ""))
            for s in d.get("sections", [])
        ),
        tone=d.get("tone", ""),
        language=d.get("language", "ko"),
    )


def _asset(d: dict[str, Any]) -> BlueprintAsset:
    return BlueprintAsset(
        id=d["id"],
        kind=d["kind"],
        mime=d["mime"],
        width=int(d["width"]),
        height=int(d["height"]),
        sha256=d["sha256"],
        box=_box(d["box"]),
        adopted=bool(d.get("adopted", True)),
        cover_box=_opt_box(d.get("cover_box")),
    )
