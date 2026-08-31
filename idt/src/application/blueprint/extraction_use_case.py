"""BlueprintExtractionUseCase — Golden Sample → DocumentBlueprint 초안.

Design Ref: golden-sample-blueprint §2.2 (추출 흐름) / §6.3 (degraded 경계)
- 흐름: 추출기 → 정책(에셋·팔레트·크기) → 페이지 분류(비전, 동시·타임아웃은
  multimodal_setting 재사용 D3) → 서사 종합 → Draft 조립(서버 필드·폰트 매핑·경고).
- 건별 분류 실패 → kind=unknown + warning, 종합 실패 → 패턴 순서 기본 서사 + warning.
  확장자 미지원·비전 미설정은 예외 (Plan FR-01/FR-04).
- PPTX(렌더 없음, D4)는 도형 통계 휴리스틱으로 분류하고 비전을 호출하지 않는다.
- blueprint-style-fidelity §3.3: 폰트 패스스루·본문 로고 좌표·푸터·장식·6단 크기를
  정책으로 조립해 schema v2 로 낸다 (서버 계산 — LLM Draft 아님, DR-1/DR-2).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Protocol

from src.application.blueprint.registries import SampleExtractorRegistry
from src.domain.blueprint.interfaces import (
    FontCatalogPort,
    NarrativeSynthesizerPort,
    PageClassifierPort,
    PageHints,
)
from src.domain.blueprint.policies import (
    DecorationPolicy,
    FooterPolicy,
    PaletteClusterPolicy,
    RepeatAssetPolicy,
    SizeHierarchyPolicy,
    SlotBoxPolicy,
    SlotSplitPolicy,
)
from src.domain.blueprint.schemas import NarrativeDraft, PagePatternDraft
from src.domain.blueprint.value_objects import (
    CURRENT_SCHEMA_VERSION,
    BlueprintAsset,
    Decoration,
    DocumentBlueprint,
    HeaderFooter,
    Narrative,
    NarrativeSection,
    PagePattern,
    PageStats,
    PatternKind,
    RelBox,
    SampleStats,
    Slot,
    SlotKind,
    StyleTokens,
    TableStyle,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multimodal.value_objects import MultimodalSettings

# blueprint-render-style-fidelity DR-10(v2) — 골든 샘플 실측 기본값.
# 값 출처: 줄간격 18.8pt/13pt=1.45, 문단 간 33.2pt, 표 외곽선·zebra 존재.
_DEFAULT_ZEBRA = True
_DEFAULT_BORDER_WIDTH_PT = 0.75
_DEFAULT_LINE_SPACING = 1.45
_DEFAULT_SPACE_AFTER_PT = 33.2

_TITLE_BAND = RelBox(0.05, 0.05, 0.9, 0.12)
_BODY_BAND = RelBox(0.05, 0.22, 0.9, 0.7)
_CONTENT_IMAGE_MIN_AREA = 0.15


@dataclass(frozen=True)
class VisionSession:
    settings: MultimodalSettings
    classifier: PageClassifierPort
    synthesizer: NarrativeSynthesizerPort


class VisionProviderPort(Protocol):
    """multimodal_setting 을 검증해 비전 분류기·종합기를 만든다 (DI 에서 구현)."""

    async def resolve(self, request_id: str) -> VisionSession: ...


@dataclass(frozen=True)
class ExtractionOutcome:
    blueprint: DocumentBlueprint
    assets: dict[str, bytes]
    page_thumbnails: tuple[bytes | None, ...]
    classification: tuple[int, int]  # (succeeded, failed)
    timings_ms: dict[str, int]


@dataclass(frozen=True)
class _Classified:
    patterns: list[PagePattern]
    failed: int
    warnings: list[str]


class BlueprintExtractionUseCase:
    def __init__(
        self,
        extractors: SampleExtractorRegistry,
        vision: VisionProviderPort,
        fonts: FontCatalogPort,
        logger: LoggerInterface,
    ) -> None:
        self._extractors = extractors
        self._vision = vision
        self._fonts = fonts
        self._logger = logger

    # ── public ────────────────────────────────────────────────────────────────

    async def run(
        self, data: bytes, filename: str, max_pages: int, request_id: str
    ) -> ExtractionOutcome:
        extractor = self._extractors.resolve(filename)  # 415 우선
        session = await self._vision.resolve(request_id)  # 409 (설정 오류)
        t0 = time.perf_counter()
        stats = extractor.extract(data, filename, max_pages)
        extract_ms = _ms(t0)

        t1 = time.perf_counter()
        classified = await self._classify_all(stats, session)
        classify_ms = _ms(t1)

        t2 = time.perf_counter()
        narrative, nwarn = await self._narrative(classified.patterns, stats, session)
        synth_ms = _ms(t2)

        blueprint, asset_bytes = self._assemble(
            stats, filename, classified, narrative, nwarn
        )
        timings = {
            "extract": extract_ms,
            "classify": classify_ms,
            "synthesize": synth_ms,
        }
        self._log_done(request_id, filename, stats, classified, blueprint, timings)
        return ExtractionOutcome(
            blueprint=blueprint,
            assets=asset_bytes,
            page_thumbnails=tuple(p.render_png for p in stats.pages),
            classification=(len(stats.pages) - classified.failed, classified.failed),
            timings_ms=timings,
        )

    def _log_done(
        self, request_id, filename, stats, classified, blueprint, timings
    ) -> None:
        self._logger.info(
            "blueprint.extract done",
            request_id=request_id,
            filename=filename,
            pages=len(stats.pages),
            classified_failed=classified.failed,
            assets=len(blueprint.assets),
            warnings=len(blueprint.warnings),
            **{f"{k}_ms": v for k, v in timings.items()},
        )

    # ── 분류 ──────────────────────────────────────────────────────────────────

    async def _classify_all(
        self, stats: SampleStats, session: VisionSession
    ) -> _Classified:
        settings = session.settings
        sem = asyncio.Semaphore(settings.concurrency)
        count = len(stats.pages)

        async def one(page: PageStats) -> tuple[PagePattern, str | None]:
            if page.render_png is None:
                return _heuristic_pattern(page, count), None
            async with sem:
                return await self._classify_vision(page, count, session)

        results = await asyncio.gather(*(one(p) for p in stats.pages))
        warnings = [w for _, w in results if w]
        return _Classified(
            patterns=[p for p, _ in results], failed=len(warnings), warnings=warnings
        )

    async def _classify_vision(
        self, page: PageStats, count: int, session: VisionSession
    ) -> tuple[PagePattern, str | None]:
        hints = _hints(page, count)
        try:
            draft = await asyncio.wait_for(
                session.classifier.classify(
                    page.render_png or b"", hints, session.settings.output_language
                ),
                timeout=float(session.settings.timeout_sec),
            )
        except Exception as e:  # noqa: BLE001 — 건별 degraded (§6.3)
            self._logger.warning(
                "blueprint.classify page failed — unknown pattern",
                page=page.number,
                exception=e,
            )
            return _unknown_pattern(
                page.number
            ), f"page {page.number}: 패턴 분류 실패 ({e})"
        return _pattern_from_draft(draft, page.number), None

    # ── 서사 ──────────────────────────────────────────────────────────────────

    async def _narrative(
        self,
        patterns: Sequence[PagePattern],
        stats: SampleStats,
        session: VisionSession,
    ) -> tuple[Narrative, list[str]]:
        titles = [_title_of(p) for p in stats.pages]
        language = session.settings.output_language
        try:
            draft = await asyncio.wait_for(
                session.synthesizer.synthesize(patterns, titles, language),
                timeout=float(session.settings.timeout_sec),
            )
            narrative = _narrative_from_draft(draft, patterns)
            if narrative is not None:
                return narrative, []
            reason = "no valid sections"
        except Exception as e:  # noqa: BLE001
            self._logger.warning("blueprint.narrative failed — fallback", exception=e)
            reason = str(e)
        return _fallback_narrative(patterns, language), [
            f"narrative 종합 실패 — 패턴 순서 기본 서사 사용 ({reason})"
        ]

    # ── 조립 ──────────────────────────────────────────────────────────────────

    def _assemble(
        self,
        stats: SampleStats,
        filename: str,
        classified: _Classified,
        narrative: Narrative,
        narrative_warnings: list[str],
    ) -> tuple[DocumentBlueprint, dict[str, bytes]]:
        assets = RepeatAssetPolicy.apply(stats)
        font_mapping, font_warnings = self._fonts.propose_mapping(_fonts_used(stats))
        style, patterns, deco_warnings = _style_and_patterns(
            stats, assets, classified.patterns
        )
        now = datetime.now(UTC)
        blueprint = DocumentBlueprint(
            id=uuid.uuid4().hex,
            name=PurePath(filename).stem or "blueprint",
            description="",
            schema_version=CURRENT_SCHEMA_VERSION,
            source_kind=stats.source_kind,
            page_count=len(stats.pages),
            style=style,
            patterns=patterns,
            narrative=narrative,
            assets=assets,
            font_mapping=font_mapping,
            warnings=tuple(
                classified.warnings
                + narrative_warnings
                + list(font_warnings)
                + deco_warnings
            ),
            status="active",
            created_at=now,
            updated_at=now,
        )
        return blueprint, _asset_bytes(stats, assets)


def _style_and_patterns(
    stats: SampleStats,
    assets: Sequence[BlueprintAsset],
    patterns: Sequence[PagePattern],
) -> tuple[StyleTokens, tuple[PagePattern, ...], list[str]]:
    """팔레트·크기·푸터·장식 정책을 묶어 StyleTokens 와 장식이 붙은 패턴을 만든다."""
    palette = PaletteClusterPolicy.apply(stats)
    hierarchy = SizeHierarchyPolicy.apply(stats)
    common, per_pattern, warnings = DecorationPolicy.apply(stats, patterns, palette)
    style = StyleTokens(
        slide_size=stats.page_size,
        fonts=hierarchy.fonts,
        sizes=hierarchy.sizes,
        palette=palette,
        table_style=TableStyle(
            header_bg=palette["primary"],
            header_text="#FFFFFF",
            border="#CCCCCC",
            # blueprint-render-style-fidelity DR-10(v2): 추출이 스타일을 **켠다**.
            # VO 기본값(꺼짐)은 하위호환용이고, 신규 추출은 골든 실측값을 쓴다.
            zebra=_DEFAULT_ZEBRA,
            border_width_pt=_DEFAULT_BORDER_WIDTH_PT,
        ),
        header_footer=_header_footer(stats, assets, hierarchy.sizes["caption"]),
        common_decorations=common,
        body_line_spacing=_DEFAULT_LINE_SPACING,
        body_space_after_pt=_DEFAULT_SPACE_AFTER_PT,
        chart_label_size_pt=hierarchy.sizes["caption"],
    )
    decorated = tuple(
        replace(p, decorations=per_pattern.get(p.id, ())) for p in patterns
    )
    # Design Ref: blueprint-slot-box-snap DR-7 — 장식 확정 후 슬롯 좌표를 실측 스냅.
    # 장식 판정은 텍스트 슬롯을 보지 않으므로(_CONTENT_SLOT_KINDS) 순환이 없다.
    snapped, snap_warnings = _split_and_snap_slots(
        stats, decorated, common, hierarchy.sizes["caption"]
    )
    return style, snapped, warnings + snap_warnings


def _split_and_snap_slots(
    stats: SampleStats,
    patterns: Sequence[PagePattern],
    common: Sequence[Decoration],
    caption: float,
) -> tuple[tuple[PagePattern, ...], list[str]]:
    """페이지별로 텍스트 슬롯을 장식 경계로 쪼개고(C-1) 실측 좌표로 스냅한다."""
    by_page = {p.number: p for p in stats.pages}
    out: list[PagePattern] = []
    warnings: list[str] = []
    for pattern in patterns:
        page = by_page.get(pattern.sample_page)
        if page is None:
            out.append(pattern)
            continue
        decorations = (*common, *pattern.decorations)
        # Design Ref: blueprint-slot-content-fill DR-5 — 분할이 스냅보다 먼저다.
        # 분할은 원본 비전 박스로 span 을 배정해야 하고, 스냅은 쪼갠 슬롯별로 맞춘다.
        split, split_warnings = SlotSplitPolicy.apply(
            page, pattern, decorations, caption
        )
        snapped, page_warnings = SlotBoxPolicy.apply(page, split, decorations, caption)
        out.append(snapped)
        warnings.extend((*split_warnings, *page_warnings))
    return tuple(out), warnings


def _header_footer(
    stats: SampleStats, assets: Sequence[BlueprintAsset], caption: float
) -> HeaderFooter:
    logo = next((a for a in assets if a.kind == "logo"), None)
    detected = FooterPolicy.apply(stats, caption_size=caption)
    return replace(detected, logo_asset_id=logo.id if logo else None)


# ── helpers (순수) ───────────────────────────────────────────────────────────


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _title_of(page: PageStats) -> str:
    if not page.spans:
        return ""
    return max(page.spans, key=lambda s: (s.size, s.bold)).text.strip()


def _hints(page: PageStats, count: int) -> PageHints:
    ranked = sorted(page.spans, key=lambda s: (-s.size, s.box.y))
    titles = tuple(dict.fromkeys(s.text.strip() for s in ranked[:3] if s.text.strip()))
    largest = max((i.box.area for i in page.images), default=0.0)
    return PageHints(
        page_number=page.number,
        page_count=count,
        has_tables=bool(page.tables),
        image_count=len(page.images),
        largest_image_area=largest,
        title_candidates=titles,
    )


def _fonts_used(stats: SampleStats) -> tuple[str, ...]:
    names = {s.font for p in stats.pages for s in p.spans if s.font}
    names |= {v for v in stats.theme_fonts.values() if v}
    return tuple(sorted(names))


def _asset_bytes(
    stats: SampleStats, assets: Sequence[BlueprintAsset]
) -> dict[str, bytes]:
    by_sha = {img.sha256: img.data for p in stats.pages for img in p.images}
    return {a.id: by_sha[a.sha256] for a in assets if a.sha256 in by_sha}


def _clamped_box(x: float, y: float, w: float, h: float) -> RelBox:
    x, y = min(max(x, 0.0), 0.99), min(max(y, 0.0), 0.99)
    return RelBox(x=x, y=y, w=max(min(w, 1.0 - x), 0.01), h=max(min(h, 1.0 - y), 0.01))


def _pattern_from_draft(draft: PagePatternDraft, page_number: int) -> PagePattern:
    slots: list[Slot] = []
    counts: dict[str, int] = {}
    trust_align = draft.kind == "cover"  # Plan §5: 표지 title 만 LLM align 신뢰
    for s in draft.slots:
        counts[s.kind] = counts.get(s.kind, 0) + 1
        suffix = "" if counts[s.kind] == 1 else str(counts[s.kind])
        slots.append(
            Slot(
                id=f"{s.kind}{suffix}",
                kind=SlotKind(s.kind),
                box=_clamped_box(s.x, s.y, s.w, s.h),
                role=s.role,
                max_chars=s.max_chars,
                max_rows=None,
                asset_id=None,
                align=s.align if trust_align and s.kind == "title" else "left",
            )
        )
    if not slots:
        slots = list(_default_slots())
    return PagePattern(
        id=f"p{page_number}",
        kind=PatternKind(draft.kind),
        slots=tuple(slots),
        background=None,
        sample_page=page_number,
        notes=draft.layout_notes,
    )


def _default_slots() -> tuple[Slot, ...]:
    return (
        Slot("title", SlotKind.TITLE, _TITLE_BAND, "제목", 60, None, None),
        Slot("text", SlotKind.TEXT, _BODY_BAND, "본문", 600, None, None),
    )


def _unknown_pattern(page_number: int) -> PagePattern:
    return PagePattern(
        id=f"p{page_number}",
        kind=PatternKind.UNKNOWN,
        slots=_default_slots(),
        background=None,
        sample_page=page_number,
        notes="vision classification failed",
    )


def _heuristic_pattern(page: PageStats, count: int) -> PagePattern:
    """PPTX(렌더 없음, D4): 도형 통계로 패턴 종류·슬롯을 정한다."""
    kind, body = _heuristic_kind(page, count)
    slots = [Slot("title", SlotKind.TITLE, _TITLE_BAND, "제목", 60, None, None)]
    if body is not None:
        slots.append(body)
    return PagePattern(
        id=f"p{page.number}",
        kind=kind,
        slots=tuple(slots),
        background=None,
        sample_page=page.number,
        notes="heuristic (pptx shapes)",
    )


def _heuristic_kind(page: PageStats, count: int) -> tuple[PatternKind, Slot | None]:
    big = max(page.images, key=lambda i: i.box.area, default=None)
    if page.number == 1 and big is not None and big.box.area >= 0.8:
        return PatternKind.COVER, None
    if page.tables:
        return PatternKind.TABLE, Slot(
            "table", SlotKind.TABLE, page.tables[0], "표", None, 12, None
        )
    if page.charts:
        return PatternKind.CHART_WITH_NOTES, Slot(
            "chart", SlotKind.CHART, page.charts[0], "차트", None, None, None
        )
    if big is not None and big.box.area >= _CONTENT_IMAGE_MIN_AREA:
        return PatternKind.IMAGE_WITH_NOTES, Slot(
            "image", SlotKind.IMAGE, big.box, "이미지", None, None, None
        )
    if page.number == count and count > 1:
        return PatternKind.CLOSING, Slot(
            "text", SlotKind.TEXT, _BODY_BAND, "맺음말", 400, None, None
        )
    return PatternKind.TEXT, Slot(
        "bullets", SlotKind.BULLETS, _BODY_BAND, "본문", 600, None, None
    )


def _narrative_from_draft(
    draft: NarrativeDraft, patterns: Sequence[PagePattern]
) -> Narrative | None:
    known = {p.id for p in patterns}
    sections = []
    for s in draft.sections:
        ids = tuple(pid for pid in s.pattern_ids if pid in known)
        if ids:
            sections.append(
                NarrativeSection(role=s.role, pattern_ids=ids, guidance=s.guidance)
            )
    if not sections:
        return None
    return Narrative(sections=tuple(sections), tone=draft.tone, language=draft.language)


def _fallback_narrative(patterns: Sequence[PagePattern], language: str) -> Narrative:
    return Narrative(
        sections=tuple(
            NarrativeSection(role=p.kind.value, pattern_ids=(p.id,), guidance="")
            for p in patterns
        ),
        tone="",
        language=language,
    )
