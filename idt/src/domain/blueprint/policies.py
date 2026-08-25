"""domain/blueprint 정책 — 순수 함수.

Design Ref: golden-sample-blueprint §2.2 (추출 흐름) / §6.3 (degraded 경계)
- PaletteClusterPolicy / SizeHierarchyPolicy / RepeatAssetPolicy:
  SampleStats → 토큰 (수치 기반)
- FooterPolicy / DecorationPolicy (blueprint-style-fidelity §3.3):
  반복 푸터·장식 도형을 서버가 계산 — LLM 슬롯에 두지 않는다 (DR-1/DR-2)
- SlidePlanValidationPolicy / SlotContentPolicy:
  LLM 출력 검증 — 위반은 제외 + 경고(degraded)
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import sqrt

from src.domain.blueprint.value_objects import (
    MAX_CHART_SERIES,
    BlueprintAsset,
    Decoration,
    FillRect,
    HeaderFooter,
    ImageRef,
    PagePattern,
    PageStats,
    RelBox,
    SampleStats,
    SlidePlan,
    Slot,
    SlotContent,
    SlotKind,
    TextSpan,
)

_MERGE_DISTANCE = 30.0  # RGB 유클리드 — 이하이면 같은 색으로 병합
_MIN_ACCENT_SATURATION = 24  # max-min 채널 차 — 미만은 회색 계열
_FILL_WEIGHT = 40.0  # 면적 비율 1.0 = span 40개 무게
_FILL_BG_AREA = 0.9
_DEFAULT_BG = "#FFFFFF"
_DEFAULT_TEXT = "#222222"
_COVER_MIN_AREA = 0.8
_DECORATION_MIN_W = 0.6
_DECORATION_MIN_AREA = 0.3

# 폰트명 정규화 (FontFamilyPolicy / FR-01)
_BOLD_TOKENS = frozenset(
    {"bold", "semibold", "demibold", "extrabold", "black", "heavy"}
)
_SUBFAMILY_TOKENS = _BOLD_TOKENS | frozenset(
    {
        "regular",
        "normal",
        "book",
        "roman",
        "italic",
        "oblique",
        "light",
        "extralight",
        "ultralight",
        "semilight",
        "thin",
        "medium",
        "condensed",
        "expanded",
        "mt",
        "ms",
    }
)
_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
# 마지막 토큰이 서브패밀리 토큰과 겹치는 실존 패밀리 — 축약에서 제외 (FR-06, DR-3)
# 구분자를 제거한 소문자 키. 새 충돌이 발견되면 이 목록만 늘린다.
_PROTECTED_FAMILIES = frozenset({"timesnewroman", "arialblack"})
_FONT_TOKEN_SPLIT = re.compile(r"[\s\-_,]+")
_FONT_KEY_STRIP = re.compile(r"[\s\-_,]+")
_TRAILING_TOKEN_KEY = re.compile(
    r"(?:" + "|".join(sorted(_SUBFAMILY_TOKENS, key=len, reverse=True)) + r")$"
)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _distance(a: str, b: str) -> float:
    ra, rb = _rgb(a), _rgb(b)
    return sqrt(sum((x - y) ** 2 for x, y in zip(ra, rb, strict=True)))


def _saturation(hex_color: str) -> int:
    r, g, b = _rgb(hex_color)
    return max(r, g, b) - min(r, g, b)


def _cluster(weighted: dict[str, float]) -> list[tuple[str, float]]:
    """가중치 내림차순으로 근접색을 대표색에 병합해 (대표색, 합산 가중치) 목록 반환."""
    reps: list[tuple[str, float]] = []
    for color, weight in sorted(weighted.items(), key=lambda kv: -kv[1]):
        for i, (rep, acc) in enumerate(reps):
            if _distance(rep, color) <= _MERGE_DISTANCE:
                reps[i] = (rep, acc + weight)
                break
        else:
            reps.append((color, weight))
    return sorted(reps, key=lambda kv: -kv[1])


def _all_spans(stats: SampleStats) -> list[TextSpan]:
    return [s for p in stats.pages for s in p.spans]


# ── PaletteClusterPolicy ─────────────────────────────────────────────────────


class PaletteClusterPolicy:
    """본문색 = 비굵은 span 최빈색(동률이면 채도 낮은 것).

    primary/accent = 나머지 가중 빈도 (배경 근접색 제외).
    """

    @staticmethod
    def apply(stats: SampleStats) -> dict[str, str]:
        spans = _all_spans(stats)
        text = PaletteClusterPolicy._text_color(spans)
        body_size = _body_size(spans)
        weighted: dict[str, float] = defaultdict(float)
        for s in spans:
            emphasis = 2.0 if (s.bold or s.size > body_size) else 1.0
            weighted[s.color.upper()] += emphasis
        # 도형·차트 채움색: 면적 비율 가중 (전면 배경(≥ 0.9)은 제외)
        for page in stats.pages:
            for color, area in page.fills:
                if area < _FILL_BG_AREA:
                    weighted[color.upper()] += area * _FILL_WEIGHT
        others = [
            c
            for c, _ in _cluster(dict(weighted))
            if _distance(c, text) > _MERGE_DISTANCE
            and _distance(c, _DEFAULT_BG)
            > _MERGE_DISTANCE  # 배경색 근접(흰 글자)은 제외
        ]
        # 채도 있는 색이 하나라도 있으면 회색 계열(캡션·축 라벨)은 후보에서 제외
        saturated = [c for c in others if _saturation(c) >= _MIN_ACCENT_SATURATION]
        if saturated:
            others = saturated
        primary = others[0] if others else text
        accent1 = PaletteClusterPolicy._accent(stats, others, primary)
        palette = {
            "primary": primary,
            "accent1": accent1,
            "text": text,
            "bg": _DEFAULT_BG,
        }
        for i, extra in enumerate(others[2:4], start=2):
            palette[f"accent{i}"] = extra
        return palette

    @staticmethod
    def _accent(stats: SampleStats, others: list[str], primary: str) -> str:
        """accent1 = 채움 도형의 채도 있는 색 중 primary 가 아닌 최다 (FR-07).

        도형색이 없으면 텍스트 빈도 순위(others[1]) 로 폴백.
        """
        fill_weight: dict[str, float] = defaultdict(float)
        for page in stats.pages:
            for color, area in page.fills:
                if area < _FILL_BG_AREA:
                    fill_weight[color.upper()] += area
        candidates = [
            c
            for c, _ in _cluster(dict(fill_weight))
            if _saturation(c) >= _MIN_ACCENT_SATURATION
            and _distance(c, primary) > _MERGE_DISTANCE
            and _distance(c, _DEFAULT_BG) > _MERGE_DISTANCE
        ]
        if candidates:
            return candidates[0]
        return others[1] if len(others) > 1 else primary

    @staticmethod
    def _text_color(spans: list[TextSpan]) -> str:
        plain = [s for s in spans if not s.bold] or spans
        if not plain:
            return _DEFAULT_TEXT
        counts = Counter(s.color.upper() for s in plain)
        clustered = _cluster({c: float(n) for c, n in counts.items()})
        top = clustered[0][1]
        tied = [c for c, w in clustered if w == top]
        return min(tied, key=_saturation)


# ── SizeHierarchyPolicy ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SizeHierarchy:
    sizes: dict[str, float]
    fonts: dict[str, str]


def _body_size(spans: list[TextSpan]) -> float:
    """본문 크기 = 글자 수 가중 최빈 크기 (표 셀처럼 짧은 텍스트에 휘둘리지 않도록)."""
    if not spans:
        return 14.0
    weights: Counter[float] = Counter()
    for s in spans:
        weights[round(s.size * 2) / 2] += len(s.text.strip())
    return float(weights.most_common(1)[0][0])


class SizeHierarchyPolicy:
    @staticmethod
    def apply(stats: SampleStats) -> SizeHierarchy:
        spans = _all_spans(stats)
        body = _body_size(spans)
        distinct = sorted({round(s.size * 2) / 2 for s in spans}, reverse=True)
        larger = [v for v in distinct if v > body]
        smaller = [v for v in distinct if v < body]
        h1 = larger[0] if larger else round(body * 2, 1)
        h2 = (
            larger[1]
            if len(larger) > 1
            else (larger[0] if larger else round(body * 1.5, 1))
        )
        caption = (
            smaller[-1] if smaller else round(body * 0.75, 1)
        )  # 최소 크기 = 캡션/각주
        sizes = {
            "h1": float(h1),
            "h2": float(h2),
            "body": float(body),
            "caption": float(caption),
        }
        sizes.update(SizeHierarchyPolicy._optional(larger, h1, h2, body))
        return SizeHierarchy(
            sizes=sizes, fonts=SizeHierarchyPolicy._fonts(spans, body, h2)
        )

    @staticmethod
    def _optional(larger: list[float], h1, h2, body) -> dict[str, float]:
        """subtitle/h3 (FR-05).

        subtitle = h1~h2 사이 최대. 없으면 h2~body 구간이 2개 이상일 때 그 최대.
        h3 = h2~body 구간 중 subtitle 로 쓰이지 않은 최대.
        """
        out: dict[str, float] = {}
        upper = [v for v in larger if h2 < v < h1]
        lower = [v for v in larger if body < v < h2]
        if upper:
            out["subtitle"] = float(upper[0])
        elif len(lower) >= 2:
            out["subtitle"] = float(lower.pop(0))
        if lower:
            out["h3"] = float(lower[0])
        return out

    @staticmethod
    def _fonts(spans: list[TextSpan], body: float, h2: float) -> dict[str, str]:
        if not spans:
            return {"heading": "", "body": ""}
        body_font = Counter(
            s.font for s in spans if abs(s.size - body) < 0.26
        ) or Counter(s.font for s in spans)
        head_spans = [s for s in spans if s.size >= h2 and s.size > body]
        head_font = Counter(s.font for s in head_spans) or body_font
        return {
            "heading": head_font.most_common(1)[0][0],
            "body": body_font.most_common(1)[0][0],
        }


# ── RepeatAssetPolicy ────────────────────────────────────────────────────────


class RepeatAssetPolicy:
    """반복 이미지(≥2페이지 동일 sha) → logo/decoration, 1페이지 전면 → cover."""

    @staticmethod
    def apply(stats: SampleStats, max_assets: int = 20) -> tuple[BlueprintAsset, ...]:
        first_seen: dict[str, ImageRef] = {}
        pages_by_sha: dict[str, set[int]] = defaultdict(set)
        seen: dict[str, list[tuple[int, ImageRef]]] = defaultdict(list)
        for page in stats.pages:
            for img in page.images:
                first_seen.setdefault(img.sha256, img)
                pages_by_sha[img.sha256].add(page.number)
                seen[img.sha256].append((page.number, img))
        assets: list[BlueprintAsset] = []
        for sha, img in first_seen.items():
            kind = RepeatAssetPolicy._classify(img, pages_by_sha[sha])
            if kind is not None:
                assets.append(RepeatAssetPolicy._asset(img, kind, seen[sha]))
        order = {"cover": 0, "logo": 1, "decoration": 2}
        assets.sort(key=lambda a: (order[a.kind], a.id))
        return tuple(assets[:max_assets])

    @staticmethod
    def _asset(
        img: ImageRef, kind: str, seen: list[tuple[int, ImageRef]]
    ) -> BlueprintAsset:
        """logo/decoration 은 본문(2p+) 최빈 box, 표지 box 는 cover_box (FR-02)."""
        if kind == "cover":
            return _asset(img, kind)
        cover = next((i for n, i in seen if n == 1), None)
        body = [i for n, i in seen if n != 1] or [i for _, i in seen]
        box = _modal_box([i.box for i in body])
        return _asset(img, kind, box=box, cover_box=cover.box if cover else None)

    @staticmethod
    def _classify(img: ImageRef, pages: set[int]) -> str | None:
        if 1 in pages and img.box.area >= _COVER_MIN_AREA:
            return "cover"
        if len(pages) < 2:
            return None
        if img.box.w >= _DECORATION_MIN_W or img.box.area >= _DECORATION_MIN_AREA:
            return "decoration"
        return "logo"


def _asset(
    img: ImageRef,
    kind: str,
    box: RelBox | None = None,
    cover_box: RelBox | None = None,
) -> BlueprintAsset:
    return BlueprintAsset(
        id=f"asset-{img.sha256[:12]}",
        kind=kind,  # type: ignore[arg-type]
        mime=img.mime,
        width=img.width,
        height=img.height,
        sha256=img.sha256,
        box=box or img.box,
        adopted=True,
        cover_box=cover_box,
    )


def _round_box(box: RelBox, step: float = 0.02) -> tuple[float, ...]:
    return tuple(round(round(v / step) * step, 2) for v in (box.x, box.y, box.w, box.h))


def _modal_box(boxes: Sequence[RelBox]) -> RelBox:
    """0.02 격자로 반올림한 최빈 box 의 원본 첫 항목."""
    counts = Counter(_round_box(b) for b in boxes)
    key = counts.most_common(1)[0][0]
    return next(b for b in boxes if _round_box(b) == key)


# ── FooterPolicy ─────────────────────────────────────────────────────────────

_FOOTER_BAND_Y = 0.88
_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*(/\s*\d+)?\s*$")
_DEFAULT_PAGE_FORMAT = "{n} / {total}"


class FooterPolicy:
    """하단 밴드(y ≥ 0.88, 캡션 크기) 의 반복 텍스트·페이지번호 → HeaderFooter (FR-03).

    표지(1p) 제외, 2페이지 이상에서 반복될 때만 채택. 실패는 빈 값(degraded).
    """

    @staticmethod
    def apply(stats: SampleStats, caption_size: float) -> HeaderFooter:
        band = FooterPolicy._band_spans(stats, caption_size)
        numbers = [s for s in band if _PAGE_NUMBER_RE.match(s.text)]
        texts = [s for s in band if not _PAGE_NUMBER_RE.match(s.text)]
        fmt, number_box = FooterPolicy._page_number(numbers)
        text, text_box, color = FooterPolicy._repeated_text(texts)
        return HeaderFooter(
            logo_asset_id=None,
            page_number_format=fmt,
            footer_text=text,
            footer_box=text_box,
            page_number_box=number_box,
            footer_color=color,
        )

    @staticmethod
    def _band_spans(stats: SampleStats, caption_size: float) -> list[TextSpan]:
        if len(stats.pages) < 2:
            return []
        return [
            s
            for page in stats.pages
            if page.number != 1
            for s in page.spans
            if s.box.y >= _FOOTER_BAND_Y
            and s.size <= caption_size + 1
            and s.text.strip()
        ]

    @staticmethod
    def _page_number(spans: list[TextSpan]) -> tuple[str, RelBox | None]:
        if len(spans) < 2:
            return _DEFAULT_PAGE_FORMAT, None
        with_total = sum(1 for s in spans if "/" in s.text)
        fmt = _DEFAULT_PAGE_FORMAT if with_total * 2 >= len(spans) else "{n}"
        return fmt, _modal_box([s.box for s in spans])

    @staticmethod
    def _repeated_text(
        spans: list[TextSpan],
    ) -> tuple[str, RelBox | None, str | None]:
        counts = Counter(s.text.strip() for s in spans)
        if not counts:
            return "", None, None
        text, n = counts.most_common(1)[0]
        if n < 2:
            return "", None, None
        matched = [s for s in spans if s.text.strip() == text]
        color = Counter(s.color.upper() for s in matched).most_common(1)[0][0]
        return text, _modal_box([s.box for s in matched]), color


# ── DecorationPolicy ─────────────────────────────────────────────────────────

_DECO_MIN_AREA = 0.001
_DECO_MAX_AREA = 0.6
_DECO_THIN = 0.02
_DECO_BAR_ASPECT = 2.0  # h/w — 세로 막대(차트)
_DECO_CONTAIN_EXCLUDE = 0.8  # 교집합/도형면적 — 표·차트 내부 도형 제외
_DECO_BG_DISTANCE = 12.0
_MAX_COMMON_DECORATIONS = 4
_MAX_PATTERN_DECORATIONS = 8
_CONTENT_SLOT_KINDS = (SlotKind.CHART, SlotKind.IMAGE, SlotKind.TABLE)

DecorationMap = dict[str, tuple[Decoration, ...]]


def _containment(a: RelBox, b: RelBox) -> float:
    """a 가 b 안에 들어간 비율 (교집합 / a 면적)."""
    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return (ix * iy) / a.area if a.area > 0 else 0.0


class DecorationPolicy:
    """채움 사각형 → 장식 (FR-06, DR-8).

    제외: 면적 범위 밖 / 배경 근접색 / 표·차트·이미지 **슬롯** 내부(포함 ≥0.8) /
    차트 슬롯이 있는 페이지의 primary·accent 색 얇은 선·세로 막대.
    PyMuPDF find_tables 는 카드 박스를 표로 오탐하므로 쓰지 않는다 — 비전 슬롯이 기준.
    ≥2 비표지 페이지 반복 → common 승격.
    """

    @staticmethod
    def apply(
        stats: SampleStats,
        patterns: Sequence[PagePattern],
        palette: dict[str, str],
    ) -> tuple[tuple[Decoration, ...], DecorationMap, list[str]]:
        by_page = {p.sample_page: p for p in patterns}
        kept: dict[int, list[FillRect]] = {}
        for page in stats.pages:
            pattern = by_page.get(page.number)
            if pattern is None:
                continue
            kept[page.number] = [
                r for r in page.rects if DecorationPolicy._eligible(r, pattern, palette)
            ]
        keys = DecorationPolicy._repeated_keys(kept)
        common, common_warnings = DecorationPolicy._common(kept, keys)
        per_pattern, warnings = DecorationPolicy._per_pattern(kept, by_page, keys)
        return common, per_pattern, common_warnings + warnings

    @staticmethod
    def _eligible(r: FillRect, pattern: PagePattern, palette) -> bool:
        area = r.box.area
        if area < _DECO_MIN_AREA or area > _DECO_MAX_AREA:
            return False
        if _distance(r.color, palette.get("bg", _DEFAULT_BG)) < _DECO_BG_DISTANCE:
            return False
        has_chart = any(s.kind is SlotKind.CHART for s in pattern.slots)
        if has_chart and DecorationPolicy._is_chart_bar(r, palette):
            return False
        content = [s.box for s in pattern.slots if s.kind in _CONTENT_SLOT_KINDS]
        return all(_containment(r.box, b) < _DECO_CONTAIN_EXCLUDE for b in content)

    @staticmethod
    def _is_chart_bar(r: FillRect, palette: dict[str, str]) -> bool:
        thin = r.box.w < _DECO_THIN or r.box.h < _DECO_THIN
        tall = r.box.h >= r.box.w * _DECO_BAR_ASPECT
        if not (thin or tall):
            return False
        return any(
            _distance(r.color, palette[k]) <= _MERGE_DISTANCE
            for k in ("primary", "accent1")
        )

    @staticmethod
    def _key(r: FillRect) -> tuple:
        return (r.color.upper(), *_round_box(r.box))

    @staticmethod
    def _repeated_keys(kept: dict[int, list[FillRect]]) -> set[tuple]:
        pages_by_key: dict[tuple, set[int]] = defaultdict(set)
        for number, rects in kept.items():
            if number == 1:
                continue
            for r in rects:
                pages_by_key[DecorationPolicy._key(r)].add(number)
        return {k for k, pages in pages_by_key.items() if len(pages) >= 2}

    @staticmethod
    def _common(kept, keys: set[tuple]) -> tuple[tuple[Decoration, ...], list[str]]:
        seen: dict[tuple, FillRect] = {}
        for number in sorted(kept):
            for r in kept[number]:
                k = DecorationPolicy._key(r)
                if k in keys:
                    seen.setdefault(k, r)
        ordered = sorted(seen.values(), key=lambda r: -r.box.area)
        warnings: list[str] = []
        if len(ordered) > _MAX_COMMON_DECORATIONS:
            warnings.append(
                f"common: 장식 {len(ordered)}개 중 {_MAX_COMMON_DECORATIONS}개만 채택"
            )
        common = tuple(
            Decoration(f"common{i}", "rect", r.box, r.color.upper())
            for i, r in enumerate(ordered[:_MAX_COMMON_DECORATIONS], start=1)
        )
        return common, warnings

    @staticmethod
    def _per_pattern(kept, by_page, keys) -> tuple[DecorationMap, list[str]]:
        out: DecorationMap = {}
        warnings: list[str] = []
        for number, rects in kept.items():
            own = [r for r in rects if DecorationPolicy._key(r) not in keys]
            if not own:
                continue
            own.sort(key=lambda r: -r.box.area)
            pid = by_page[number].id
            if len(own) > _MAX_PATTERN_DECORATIONS:
                warnings.append(
                    f"{pid}: 장식 {len(own)}개 중 {_MAX_PATTERN_DECORATIONS}개만 채택"
                )
            out[pid] = tuple(
                Decoration(f"deco{i}", "rect", r.box, r.color.upper())
                for i, r in enumerate(own[:_MAX_PATTERN_DECORATIONS], start=1)
            )
        return out, warnings


# ── SlidePlanValidationPolicy ────────────────────────────────────────────────


@dataclass(frozen=True)
class PlanOutcome:
    kept: tuple[SlidePlan, ...]
    rejected: tuple[str, ...]


class SlidePlanValidationPolicy:
    @staticmethod
    def apply(
        plans: list[SlidePlan], patterns: tuple[PagePattern, ...], max_slides: int
    ) -> PlanOutcome:
        known = {p.id for p in patterns}
        kept: list[SlidePlan] = []
        rejected: list[str] = []
        for plan in plans:
            if plan.pattern_id not in known:
                rejected.append(
                    f"slide {plan.index}: unknown pattern_id '{plan.pattern_id}'"
                )
                continue
            if len(kept) >= max_slides:
                rejected.append(f"slide {plan.index}: exceeds max_slides={max_slides}")
                continue
            kept.append(
                SlidePlan(
                    index=len(kept) + 1,
                    pattern_id=plan.pattern_id,
                    title=plan.title,
                    intent=plan.intent,
                    data_hint=plan.data_hint,
                )
            )
        return PlanOutcome(kept=tuple(kept), rejected=tuple(rejected))


# ── SlotContentPolicy ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContentOutcome:
    kept: tuple[SlotContent, ...]
    warnings: tuple[str, ...]


_TEXT_KINDS = {SlotKind.TITLE, SlotKind.TEXT}


class SlotContentPolicy:
    @staticmethod
    def apply(contents: list[SlotContent], pattern: PagePattern) -> ContentOutcome:
        kept: list[SlotContent] = []
        warnings: list[str] = []
        for c in contents:
            slot = pattern.slot(c.slot_id)
            if slot is not None and slot.kind is SlotKind.FOOTER:
                continue  # DR-2: 푸터는 렌더러가 스타일로 그림 — LLM 내용 무시
            problem = (
                f"slot '{c.slot_id}' not in pattern '{pattern.id}'"
                if slot is None
                else SlotContentPolicy._violation(c, slot)
            )
            if problem:
                warnings.append(problem)
            else:
                kept.append(c)
        return ContentOutcome(kept=tuple(kept), warnings=tuple(warnings))

    @staticmethod
    def _violation(c: SlotContent, slot: Slot) -> str | None:
        if slot.kind in _TEXT_KINDS:
            return _check_text(c, slot)
        if slot.kind is SlotKind.BULLETS:
            return _check_bullets(c, slot)
        if slot.kind is SlotKind.TABLE:
            return _check_table(c, slot)
        if slot.kind is SlotKind.CHART:
            return _check_chart(c, slot)
        return None  # image: 콘텐츠 없음(에셋 고정)


def _check_text(c: SlotContent, slot: Slot) -> str | None:
    if c.text is None or c.bullets is not None:
        return f"slot '{slot.id}': expected text"
    if slot.max_chars and len(c.text) > slot.max_chars:
        return f"slot '{slot.id}': text {len(c.text)} > max_chars {slot.max_chars}"
    return None


def _check_bullets(c: SlotContent, slot: Slot) -> str | None:
    if c.bullets is None:
        return f"slot '{slot.id}': expected bullets"
    total = sum(len(b) for b in c.bullets)
    if slot.max_chars and total > slot.max_chars:
        return f"slot '{slot.id}': bullets {total} > max_chars {slot.max_chars}"
    return None


class FontFamilyPolicy:
    """추출 폰트명 → OS 가 해석 가능한 패밀리명 (pptx-font-fidelity FR-01).

    PDF 추출기는 서브패밀리명("Malgun Gothic Regular")과 서브셋 프리픽스
    ("ABCDEF+...")를 붙여 준다. 그대로 PPTX 에 적으면 뷰어가 폰트를 찾지 못해
    대체 렌더된다. 굵기는 패밀리명이 아니라 run 의 bold 속성으로 표현한다.
    """

    @staticmethod
    def normalize(name: str) -> tuple[str, bool]:
        """(패밀리명, bold 힌트). 토큰만으로 이뤄진 이름은 원본을 유지한다."""
        base = _SUBSET_PREFIX.sub("", (name or "").strip())
        tokens = [t for t in _FONT_TOKEN_SPLIT.split(base) if t]
        kept, bold = _strip_trailing_tokens(tokens)
        if not kept:
            return base.strip(), False  # 이름 전체가 토큰 — 원본이 곧 패밀리명
        return _rejoin(base, tokens, kept), bold

    @staticmethod
    def alias_key(name: str) -> str:
        """별칭 표 비교키 — 구분자 없는 이름에서도 접미사를 떼어낸다."""
        family, _ = FontFamilyPolicy.normalize(name)
        key = _FONT_KEY_STRIP.sub("", family).lower()
        while True:
            shorter = _TRAILING_TOKEN_KEY.sub("", key)
            if shorter == key or not shorter:
                return key
            key = shorter


def _family_key(tokens: list[str]) -> str:
    return "".join(tokens).lower()


def _strip_trailing_tokens(tokens: list[str]) -> tuple[list[str], bool]:
    """뒤에서부터 서브패밀리 토큰을 떼어 낸다.

    Design Ref: blueprint-font-mapping-migration DR-4 — 보호 검사는 진입부가 아니라
    이 루프 안에서 한다. 진입부 검사는 "Arial Black Italic" 을 놓쳐 Arial 까지
    깎아 내지만, 여기서는 Italic 만 떼고 "Arial Black" 에서 멈춘다.
    """
    kept = list(tokens)
    bold = False
    while kept and kept[-1].lower() in _SUBFAMILY_TOKENS:
        if _family_key(kept) in _PROTECTED_FAMILIES:
            break  # Plan SC-7: 실존 패밀리는 훼손하지 않는다
        bold = bold or kept[-1].lower() in _BOLD_TOKENS
        kept.pop()
    return kept, bold


def _rejoin(base: str, tokens: list[str], kept: list[str]) -> str:
    """원본의 구분자를 보존하기 위해 남길 토큰까지의 접두부를 잘라 낸다."""
    if len(kept) == len(tokens):
        return base.strip()
    cut = base.rfind(tokens[len(kept)])
    return base[:cut].strip(" -_")


def _check_table(c: SlotContent, slot: Slot) -> str | None:
    if c.table is None:
        return f"slot '{slot.id}': expected table"
    if slot.max_rows and len(c.table.rows) > slot.max_rows:
        return f"slot '{slot.id}': rows {len(c.table.rows)} > max_rows {slot.max_rows}"
    return None


def _check_chart(c: SlotContent, slot: Slot) -> str | None:
    if c.chart is None:
        return f"slot '{slot.id}': expected chart"
    if len(c.chart.series) > MAX_CHART_SERIES:
        return f"slot '{slot.id}': series {len(c.chart.series)} > {MAX_CHART_SERIES}"
    return None


# ── blueprint-slot-box-snap — 슬롯 좌표 실측 스냅 ────────────────────────────

_SNAP_TEXT_KINDS = (SlotKind.TITLE, SlotKind.TEXT, SlotKind.BULLETS)
_SNAP_MIN_SIDE = 0.01  # _clamped_box 와 동일한 최소 변 길이 (FR-06)


class SlotBoxPolicy:
    """비전 추정 슬롯 박스 → 실측 span union (blueprint-slot-box-snap FR-01~06).

    Design Ref: §3.2 알고리즘 / DR-2 — 비전 박스는 **배정 힌트로만** 쓰고 최종
    좌표에는 남기지 않는다. 비전은 영역은 맞히고 정밀도만 틀리기 때문이다.
    DR-9: 실패는 예외가 아니라 원본 유지 + 경고다.
    """

    @staticmethod
    def apply(
        page: PageStats,
        pattern: PagePattern,
        decorations: Sequence[Decoration],
        caption_size: float,
    ) -> tuple[PagePattern, tuple[str, ...]]:
        targets = [s for s in pattern.slots if s.kind in _SNAP_TEXT_KINDS]
        spans = _snappable_spans(page, caption_size)
        if not targets or not spans:
            return pattern, ()
        assigned = _assign(spans, targets)
        unions = {
            sid: _union(qs) for sid, qs in assigned.items() if qs
        }  # 미배정 슬롯은 폴백
        slots = tuple(
            _snapped(s, unions, pattern, decorations) if s.id in unions else s
            for s in pattern.slots
        )
        warnings = tuple(
            f"page {page.number}: slot '{s.id}' 매칭 span 없음 — 추정 좌표 유지"
            for s in targets
            if s.id not in unions
        )
        return replace(pattern, slots=slots), warnings


def _snappable_spans(page: PageStats, caption_size: float) -> list[TextSpan]:
    """푸터 밴드의 캡션 크기 span 을 제외한다 (FR-04, DR-3).

    FooterPolicy._band_spans 와 동일 기준 — 기준이 갈리면 같은 글자가 푸터로도
    슬롯으로도 렌더된다.
    """
    return [
        s
        for s in page.spans
        if s.text.strip()
        and not (s.box.y >= _FOOTER_BAND_Y and s.size <= caption_size + 1)
    ]


def _assign(spans: Sequence[TextSpan], targets: Sequence[Slot]) -> dict[str, list]:
    """span 중심점을 포함하는 슬롯에 배정. 동점은 중심 거리 → id 순 (DR-6)."""
    out: dict[str, list] = {s.id: [] for s in targets}
    for span in spans:
        cx, cy = span.box.x + span.box.w / 2, span.box.y + span.box.h / 2
        cands = [s for s in targets if _covers(s.box, cx, cy)]
        if not cands:
            continue
        best = min(cands, key=lambda s: (abs(cy - (s.box.y + s.box.h / 2)), s.id))
        out[best.id].append(span)
    return out


def _covers(box: RelBox, cx: float, cy: float) -> bool:
    return box.x <= cx <= box.x + box.w and box.y <= cy <= box.y + box.h


def _union(spans: Sequence[TextSpan]) -> RelBox:
    x = min(s.box.x for s in spans)
    y = min(s.box.y for s in spans)
    right = max(s.box.x + s.box.w for s in spans)
    bottom = max(s.box.y + s.box.h for s in spans)
    return RelBox(
        x=x,
        y=y,
        w=max(right - x, _SNAP_MIN_SIDE),
        h=max(bottom - y, _SNAP_MIN_SIDE),
    )


def _snapped(
    slot: Slot,
    unions: dict[str, RelBox],
    pattern: PagePattern,
    decorations: Sequence[Decoration],
) -> Slot:
    union = unions[slot.id]
    bottom = _bottom(slot, union, unions, pattern, decorations)
    height = max(bottom - union.y, _SNAP_MIN_SIDE)
    return replace(slot, box=_snap_clamped(union.x, union.y, union.w, height))


def _bottom(
    slot: Slot,
    union: RelBox,
    unions: dict[str, RelBox],
    pattern: PagePattern,
    decorations: Sequence[Decoration],
) -> float:
    """아래쪽 경계 — 종류 무관 최근접 + 포함 장식 하단 캡 (FR-03, DR-4·DR-5)."""
    edge = union.y + union.h
    tops = [_FOOTER_BAND_Y]
    for other in pattern.slots:  # DR-4: 표·차트·이미지 슬롯도 경계다
        if other.id == slot.id or other.kind is SlotKind.FOOTER:
            continue
        top = unions.get(other.id, other.box).y
        if top > edge:
            tops.append(top)
    tops.extend(d.box.y for d in decorations if d.box.y > edge)
    tops.extend(
        d.box.y + d.box.h for d in decorations if _encloses(d.box, union, edge)
    )
    return min(tops)


def _encloses(outer: RelBox, union: RelBox, edge: float) -> bool:
    """DR-5: union 을 완전히 감싸는 장식만 캡 대상이다."""
    return (
        outer.x <= union.x
        and outer.y <= union.y
        and outer.x + outer.w >= union.x + union.w
        and outer.y + outer.h >= edge
    )


def _snap_clamped(x: float, y: float, w: float, h: float) -> RelBox:
    """FR-06 — _clamped_box(application) 와 동일한 불변식을 도메인에서 재현."""
    x, y = min(max(x, 0.0), 0.99), min(max(y, 0.0), 0.99)
    return RelBox(
        x=x,
        y=y,
        w=max(min(w, 1.0 - x), _SNAP_MIN_SIDE),
        h=max(min(h, 1.0 - y), _SNAP_MIN_SIDE),
    )
