# blueprint-style-fidelity Design Document

> **Summary**: 골든 샘플 추출 시 손실되는 폰트·에셋 좌표·푸터·크기 계층·장식 도형을 블루프린트 스키마 v2로 보존하고, PPTX 렌더러가 이를 실제로 그리도록 하는 설계. 기존 레코드는 UseCase 메서드 + CLI로 같은 id에 재추출한다.
>
> **Project**: sangplusbot / idt
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-23
> **Status**: Draft
> **Planning Doc**: [blueprint-style-fidelity.plan.md](../../01-plan/features/blueprint-style-fidelity.plan.md)
> **Base Design**: [golden-sample-blueprint.design.md](../../archive/2026-08/golden-sample-blueprint/golden-sample-blueprint.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 블루프린트 추출이 폰트·좌표·도형·푸터 정보를 버려서 산출 PPT가 샘플 스타일과 무관해 보인다 |
| **WHO** | P2 KB 운영자/에이전트 소유자 (관리자 화면에서 골든 샘플 등록), 최종 PPT를 받는 에이전트 사용자 |
| **RISK** | `blueprint_json` 스키마 v2 전환 시 기존 레코드·프론트 라운드트립(PUT) 호환 — v1 읽기 폴백 + interface 스키마 필드 추가로 대응 |
| **SUCCESS** | 재추출 후 생성 PPT: ① 폰트 = Malgun Gothic ② 로고 = 본문 좌표(우상단) ③ 슬라이드당 페이지번호 1개 ④ 푸터 텍스트 = 원본 ⑤ 강조 상자·푸터 띠 존재 — 골든 샘플 회귀 테스트로 자동 검증 |
| **SCOPE** | Phase A 추출 정책 → Phase B 렌더러 → Phase C 재추출·회귀. 샘플 해상도·프론트 UI 변경은 범위 밖 |

---

## 1. Overview

### 1.1 Design Goals

1. **정보 보존**: 추출 단계에서 원본의 시각 규칙(폰트명, 반복 에셋의 본문 좌표, 푸터 텍스트/좌표, 6단 크기 계층, 채움 도형, 악센트 색)을 `DocumentBlueprint`에 남긴다.
2. **렌더 충실도**: 렌더러가 위 정보를 z-order(배경 → 장식 → 에셋 → 콘텐츠 → 푸터)로 그린다.
3. **푸터 단일 책임**: 푸터/페이지번호는 **스타일 토큰 + 렌더러**만 담당. LLM 슬롯에서 제거.
4. **호환**: `schema_version=2`. v1 JSON은 기본값으로 로드·렌더 가능. 프론트 PUT 라운드트립(`extra="forbid"`)은 interface 스키마에 필드를 추가해 유지.
5. **재추출**: `BlueprintAdminUseCase.reextract()`로 같은 id에 덮어쓰기(에셋 교체 허용).

### 1.2 Design Principles

- **D1 유지**: 좌표는 RelBox(0..1). EMU 변환은 렌더러만.
- **LLM 신뢰 경계 유지**: 장식·푸터는 LLM Draft에 두지 않는다(서버 계산). `SlotDraft.align`만 LLM 출력에 추가하고 기본값 폴백.
- **Thin DDD**: 휴리스틱은 `domain/blueprint/policies.py` 정적 정책으로, PyMuPDF/python-pptx는 infrastructure에만.
- **Degraded > Failure**: 푸터·도형·폰트 추출 실패는 빈 값 + `warnings`. 예외로 올리지 않는다.
- **함수 40줄 / if 중첩 ≤ 2** — 렌더러는 단계 함수로 분할.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | VO 옵션 필드 + 렌더러 if 분기, 스크립트가 repo 직접 호출 | 추출기·렌더러 전면 분해 + 재추출 API | 정책 2개·VO 1개 신설, 렌더러 단계 추가, UseCase 메서드 + CLI |
| **New Files** | 1 | 8~10 | 4 |
| **Modified Files** | 8 | 14+ | 11 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | 1 세션 | 4~5 세션 | 2~3 세션 |
| **Risk** | 스키마 버전 없음, 푸터 중복 재발 | 회귀 범위 큼 | 균형 |

**Selected**: **Option C** — 원 설계의 정책/렌더러 경계를 유지하면서 손실 지점만 명시적 구성요소로 추가. 재추출은 UseCase 메서드 + CLI (API·UI 버튼은 후속).

### 2.1 Component Diagram

```
[PDF] ─▶ PdfStyleExtractor ─▶ SampleStats(+footer 후보는 spans 그대로, fills=(hex, area, box))
                                   │
              BlueprintExtractionUseCase._assemble
                                   │
        ┌──────────────┬───────────┼────────────────┬───────────────┐
        ▼              ▼           ▼                ▼               ▼
 RepeatAssetPolicy  FooterPolicy  DecorationPolicy  SizeHierarchyPolicy  PaletteClusterPolicy
 (본문 최빈 box,    (footer_text, (패턴별 rect,      (h1/h2/h3/subtitle/  (accent1 = 도형색)
  cover_box)        boxes, fmt)   common_decorations) body/caption)
        └──────────────┴───────────┴────────────────┴───────────────┘
                                   ▼
                     DocumentBlueprint (schema_version=2)
                                   │  serialization v2 (v1 폴백)
                                   ▼
                        document_blueprint.blueprint_json
                                   │
      GenerationUseCase (footer 슬롯 제외) ─▶ PptxSlideRenderer
                                              ├ _background
                                              ├ _decorations   ← NEW (common + pattern)
                                              ├ _logo (cover_box / box)
                                              ├ _render_slot (align, role-size)
                                              └ _footer (style 전용, 1회)
```

### 2.2 Data Flow — 변경 지점

```
추출:  spans/fills ──FooterPolicy──▶ HeaderFooter(footer_text, footer_box, page_number_box, page_number_format)
       fills       ──DecorationPolicy──▶ PagePattern.decorations / StyleTokens.common_decorations
       images      ──RepeatAssetPolicy──▶ BlueprintAsset(box=본문 최빈, cover_box=표지)
       spans       ──SizeHierarchyPolicy──▶ sizes{h1,h2,h3,subtitle,body,caption}
       fonts       ──FontCatalog(패스스루)──▶ font_mapping{src: src}
생성:  pattern.slots[kind≠footer,image] ──▶ LLM write ──▶ SlotContent
렌더:  background → decorations → logo → slots(align, role size) → footer/page-number (1회)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `FooterPolicy` (domain) | `PageStats.spans` | 하단 반복 텍스트·페이지번호 패턴 검출 |
| `DecorationPolicy` (domain) | `PageStats.fills`(box 추가), `tables`, 슬롯 box | 장식 사각형 선별·반복 승격 |
| `PdfStyleExtractor` (infra) | PyMuPDF `get_drawings` | `fills`에 box 포함 |
| `PptxSlideRenderer` (infra) | python-pptx `add_shape` | 장식 도형 렌더 |
| `BlueprintAdminUseCase.reextract` | `BlueprintExtractionUseCase`, `BlueprintRepository.replace_assets` | 같은 id 재추출 |
| `scripts/blueprint_reextract.py` | `blueprint_di` 팩토리 | CLI 진입 |

---

## 3. Data Model

### 3.1 Entity Definition (`domain/blueprint/value_objects.py`)

```python
# ── 신규 ──
@dataclass(frozen=True)
class Decoration:
    """내용 없는 장식 도형. LLM이 채우지 않는다."""
    id: str                       # "deco1"…
    shape: Literal["rect"]        # v2 는 rect 만
    box: RelBox
    fill: str                     # #RRGGBB
    line: str | None = None       # 테두리 색 (없으면 None)
    # __post_init__: id 필수, fill/line hex 검증

Align = Literal["left", "center", "right"]

# ── 확장 (기본값으로 v1 호환) ──
@dataclass(frozen=True)
class Slot:
    ...기존 7필드...
    align: Align = "left"                       # NEW

@dataclass(frozen=True)
class PagePattern:
    ...기존...
    decorations: tuple[Decoration, ...] = ()    # NEW — 패턴 전용 장식 (카드 박스 등)
    # __post_init__: decoration id 중복 검사 추가

@dataclass(frozen=True)
class HeaderFooter:
    logo_asset_id: str | None
    page_number_format: str
    footer_text: str
    footer_box: RelBox | None = None            # NEW — None 이면 렌더러 폴백 상수
    page_number_box: RelBox | None = None       # NEW
    footer_color: str | None = None             # NEW — 캡션 색 (None → palette["text"])

@dataclass(frozen=True)
class StyleTokens:
    ...기존...
    common_decorations: tuple[Decoration, ...] = ()   # NEW — 전 슬라이드(비표지) 공통 장식

@dataclass(frozen=True)
class BlueprintAsset:
    ...기존...
    cover_box: RelBox | None = None             # NEW — 표지에서의 위치 (logo 전용)

# sizes 키: REQUIRED_SIZE_KEYS 는 유지({"h1","h2","body","caption"})
OPTIONAL_SIZE_KEYS = frozenset({"h3", "subtitle"})   # 렌더러는 .get(키, 폴백)
CURRENT_SCHEMA_VERSION = 2                            # serialization.SCHEMA_VERSION 과 동일 상수
```

**크기 역할 폴백 규칙 (렌더러 `_size(role)`)**: `h3 → h2*0.65 → body*1.15`, `subtitle → h1*0.55 → body*1.4`. 값은 `StyleTokens.size(role)` 메서드로 단일화.

### 3.2 LLM Draft 스키마 (`domain/blueprint/schemas.py`)

```python
class SlotDraft(_Strict):
    ...기존...
    align: Literal["left", "center", "right"] = "left"   # NEW — 프롬프트에 규칙 1줄 추가
# SlotKindLiteral 에서 "footer" 는 유지(분류 LLM이 인식), 생성 프롬프트에서만 제외
```

### 3.3 정책 정의 (`domain/blueprint/policies.py`)

#### FooterPolicy

```
입력: stats.pages (표지 제외: number ≥ 2, 총 페이지 ≥ 2)
규칙:
  band   = spans with box.y ≥ 0.88 and size ≤ caption_size + 1
  페이지번호 후보 = text 가 r"^\s*\d+\s*/\s*\d+\s*$" 또는 r"^\s*\d+\s*$" 에 매치
       → page_number_format = "{n} / {total}" | "{n}", page_number_box = 최빈 box(반올림 0.01)
  푸터 텍스트 후보 = band 중 페이지번호가 아닌 text, ≥ 2 페이지에서 동일(strip) 한 것의 최빈값
       → footer_text, footer_box = 최빈 box, footer_color = 최빈 color
  없으면: footer_text="" / box None / page_number_format 기본 "{n} / {total}"(현행 유지)
출력: HeaderFooter (logo_asset_id 는 호출자가 채움)
```

#### DecorationPolicy

```
입력: stats.pages, patterns(슬롯 box), rects = FillRect(color, box)  ← v0.2: fills 는 유지, 좌표는 별도 필드
제외: area < 0.001 | area > 0.6 | 색 == palette.bg 근접(RGB 거리 < 12 — 골든 띠 #F3F4F6 는 18.6)
      | 비전 슬롯(table/chart/image) 안에 포함율 ≥ 0.8 (PyMuPDF find_tables 는 카드 박스를 표로
        오탐하므로 쓰지 않는다)
      | 패턴에 chart 슬롯이 있을 때, primary/accent 색 + (얇음 < 0.02 또는 h/w ≥ 2) → 차트 막대·선
반복 승격: 동일 (hex, box 반올림 0.02) 가 비표지 페이지 ≥ 2 에서 등장
      → StyleTokens.common_decorations (예: 푸터 띠 #F2F4F5 (0,0.93,1,0.07))
나머지 → 해당 sample_page 의 PagePattern.decorations (예: p3 카드 박스, p6 카드 3개)
상한: common ≤ 4, 패턴당 ≤ 8 (초과는 면적 큰 순, 경고)
id: "deco{n}" (패턴 내 1부터)
```

#### SizeHierarchyPolicy (확장)

```
distinct = 내림차순 크기 클러스터(0.5pt 반올림), body = 최빈 가중
larger = body 보다 큰 것들
  h1 = larger[0], h2 = larger[1] (없으면 현행 폴백)
  upper = h1~h2 사이, lower = h2~body 사이 (내림차순)
  subtitle = upper[0] if upper else (lower.pop(0) if len(lower) ≥ 2 else None)
  h3 = lower[0] if lower else None
None 키는 sizes 에 넣지 않는다 (REQUIRED 4키만 보장, 렌더러 폴백)
골든 샘플: h1=34, h2=24, lower=[18,16,15] → subtitle=18, h3=16 (15 는 버림)
(v0.2 정정: 초안 규칙은 h1~h2 사이에만 subtitle 을 두어 골든 샘플에서 subtitle=None 이 됐음)
```

#### PaletteClusterPolicy (보정)

```
accent1 = fills 색 중 bg 근접·primary·회색조(채도 < 0.15) 제외 후 가중 면적 최다
          없으면 기존 로직(텍스트 색 빈도) 유지
```

#### RepeatAssetPolicy (보정)

```
logo/decoration: box = 비표지 페이지 등장 box 의 최빈값(0.02 반올림), cover_box = 1페이지 box (있으면)
cover: 현행 유지 (1페이지 전면)
```

### 3.4 Database Schema

DDL 변경 **없음**. `document_blueprint.blueprint_json` 내부 `schema_version: 1 → 2`.

```
serialization.py
  SCHEMA_VERSION = 2
  blueprint_from_dict: version ∈ {1, 2} 허용; v1 은 필드별 .get() 기본값으로 채움 (v0.2: 별도 _migrate_v1 함수 없음)
     - slots[].align = "left", patterns[].decorations = [], style.common_decorations = [],
       header_footer.footer_box/page_number_box/footer_color = None, assets[].cover_box = None
     - 로드 결과 schema_version 은 원본 값 유지(1) — 저장 시 to_dict 가 2 로 씀? → 아니오.
       **로드 시 버전을 바꾸지 않는다.** 재저장(update)은 AdminUseCase 가 CURRENT 로 올린다.
  blueprint_to_dict: Decoration/align/box 직렬화 (None → null)
```

### 3.5 Entity Relationships

```
DocumentBlueprint 1 ── 1 StyleTokens ── N common_decorations: Decoration
                  1 ── N PagePattern ── N Slot(align)
                                     └─ N decorations: Decoration
                  1 ── N BlueprintAsset(box, cover_box)
```

---

## 4. API Specification

엔드포인트 추가 없음. 기존 `POST /admin/blueprints/extract`, `POST`, `PUT /{id}`, `GET /{id}` 의 **페이로드만 확장**.

### 4.1 `interfaces/schemas/blueprint.py` 변경 (extra="forbid" 이므로 필수)

| Schema | 추가 필드 | 기본값 |
|--------|-----------|--------|
| `SlotSchema` | `align: Literal["left","center","right"]` | `"left"` |
| `DecorationSchema` (신규) | `id, shape, box, fill, line` | `line=None` |
| `PatternSchema` | `decorations: list[DecorationSchema]` | `[]` |
| `HeaderFooterSchema` | `footer_box, page_number_box: RelBoxSchema \| None`, `footer_color: str \| None` | `None` |
| `StyleSchema` | `common_decorations: list[DecorationSchema]` | `[]` |
| `AssetSchema` | `cover_box: RelBoxSchema \| None` | `None` |
| `BlueprintPayload` | `schema_version: int = 2` | — |

### 4.2 프론트 계약 (`idt_front/src/types/blueprint.ts`) — `/api-contract-sync` 대상

동일 필드를 optional 로 추가. 화면 편집 UI는 추가하지 않음(라운드트립 보존만). `BlueprintTabs.tsx` 는 spread 패치 방식이라 새 필드가 유지됨(검증 항목).

### 4.3 AdminUseCase

```python
async def update(self, blueprint_id, edited):
    ...기존 검증...
    merged = replace(edited, ..., schema_version=CURRENT_SCHEMA_VERSION, ...)  # v1 → 2 승격

async def reextract(self, blueprint_id: str, data: bytes, filename: str,
                    max_pages: int, request_id: str) -> DocumentBlueprint:
    current = await self.get(blueprint_id)                       # 404
    outcome = await self._extraction.run(data, filename, max_pages, request_id)
    merged = replace(outcome.blueprint, id=current.id, name=current.name,
                     description=current.description, status=current.status,
                     created_at=current.created_at, updated_at=now)
    await self._repo.replace(merged, outcome.assets)             # 트랜잭션 1개: 에셋 delete+insert, row update
    self._logger.info("blueprint.reextract", blueprint_id=..., warnings=len(merged.warnings))
    return merged
```

`BlueprintRepository.replace(bp, assets)` 신설 — 세션 내 commit 없음(규칙: Repository 는 commit 금지, UseCase 경계에서 처리하는 기존 패턴 따름).
(v0.2) `blueprint_di.build_admin_use_case(session, llm_factory, logger, settings)` — CLI 용 단일 세션 조립 헬퍼, `wire_blueprint` 과 동일 구성.

### 4.4 CLI `scripts/blueprint_reextract.py`

```
usage: python -m scripts.blueprint_reextract --id 3bac89cb… --file samples/golden_sample_report.pdf [--max-pages 20]
동작: blueprint_di 로 AdminUseCase 조립 → reextract → warnings 출력 → 종료 코드 0/1
```

---

## 5. UI/UX Design

프론트 화면 변경 없음 (타입만). 해당 없음.

### 5.4 Page UI Checklist

N/A (백엔드 전용)

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | 상황 | 처리 |
|------|------|------|------|
| `BLUEPRINT_NOT_FOUND` | 404 | reextract 대상 없음 | 기존 에러 재사용 |
| `UNSUPPORTED_MEDIA` | 415 | 재추출 파일 손상 | 기존 |
| `VALIDATION_ERROR` | 400 | v2 필드 검증 실패(hex, box 범위) | pydantic/`__post_init__` |
| `unsupported blueprint schema_version` | ValueError→500 | version ∉ {1,2} | 현행 유지 |

### 6.2 Degraded 경계

| 상황 | 처리 |
|------|------|
| 푸터 검출 실패 | `footer_text=""`, box None, 경고 없음(정상 케이스) |
| 장식 상한 초과 | 면적 큰 순 절삭 + `warnings` 1건 |
| 폰트 미설치 | `font_mapping[src]=src` + 경고 `"font 'X' not installed — kept as-is"` |
| LLM `align` 누락/오류 | pydantic 기본 `"left"` |
| v1 레코드 | 기본값으로 로드, 렌더 정상 |

---

## 7. Security Considerations

- 장식/푸터는 서버 계산값 — LLM 출력 경로 아님. `align` 만 LLM → Literal 검증.
- `reextract` 는 admin UseCase 경유(스크립트도 동일 경로). 파일 크기 상한은 기존 `MAX_UPLOAD_BYTES` 재사용.
- 푸터 텍스트는 원본 PDF 텍스트 그대로 — 렌더 시 마크업 해석 없음(§7 원칙 유지).

---

## 8. Test Plan

### 8.1 Test Scope

| Layer | 파일 | 핵심 케이스 |
|-------|------|------------|
| domain | `tests/domain/blueprint/test_value_objects.py` | Decoration hex/id 검증, Slot.align 기본, HeaderFooter 옵션 필드 |
| domain | `test_policies.py` | FooterPolicy(페이지번호 `n / N`·단독 `n`, 반복 텍스트, 표지 제외), DecorationPolicy(표/차트 IoU 제외, 반복 승격, 상한·경고), SizeHierarchy 6단(골든 스팬 픽스처 → 34/24/16/18/13/9), Palette accent=#E07A1F, RepeatAsset 본문 최빈 box + cover_box |
| domain | `test_serialization.py` | v2 왕복, **v1 픽스처 로드 → 기본값**, version 3 거부 |
| domain | `test_schemas.py` | SlotDraft.align 기본/오류 |
| infra | `test_pdf_style_extractor.py` | fills 에 box 포함, 골든 샘플 p2 footer band spans 존재 |
| infra | `test_fonts.py` | 카탈로그 비었을 때 패스스루 + 경고 문구 |
| infra | `test_pptx_renderer.py` | 장식 z-order(첫 shapes 가 AUTO_SHAPE), 푸터 1회, align 적용, h3/subtitle 폴백, cover_box 사용, v1 블루프린트 렌더 |
| infra | `test_repository.py` | `replace()` 에셋 교체 |
| app | `test_extraction_use_case.py` | `_assemble` 이 footer/decorations/cover_box 조립, footer 슬롯 유지 |
| app | `test_generation_use_case.py` + `test_prompts_and_llm.py` | write 프롬프트에 footer 슬롯 미포함, SlotContentPolicy 가 footer 내용 무시 |
| app | `test_admin_use_case.py` | update 가 schema_version 2 로 승격, reextract 가 id/name/created_at 보존·에셋 교체 |
| **회귀** | `tests/integration/blueprint/test_golden_sample_fidelity.py` (신규) | Plan SC-1~SC-8 전부 — fake vision(고정 PagePatternDraft) + 실제 PdfStyleExtractor + 실제 렌더러 |

### 8.2 L1 API

| # | 요청 | 기대 |
|---|------|------|
| 1 | `PUT /admin/blueprints/{id}` v2 페이로드(decorations 포함) | 200, 응답에 decorations 유지 |
| 2 | `PUT` 에 알 수 없는 필드 | 400 (forbid 유지) |
| 3 | `GET /{id}` v1 레코드 | 200, `decorations: []`, `schema_version: 1` |

### 8.3 L2/L3

프론트 변경 없음 → L2 생략. L3 = 회귀 테스트(8.1 마지막 행)가 대신한다.

### 8.5 Seed Data

- `tests/fixtures/blueprint/golden_v1.json` — 현재 DB 레코드 `3bac89cb…` 의 blueprint_json 스냅샷 (v1 폴백 테스트)
- `samples/golden_sample_report.pdf` — 회귀 입력 (이미 존재)
- (v0.2) 비전 분류 고정 결과는 별도 파일 없이 `GoldenAdapter` 가 `golden_v1.json` 의 patterns 에서 파생 — 픽스처 2개 간 표류 방지

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
domain/blueprint/
  value_objects.py   Decoration, Align, Slot.align, PagePattern.decorations, HeaderFooter(+3), StyleTokens.common_decorations(+size()), BlueprintAsset.cover_box, CURRENT_SCHEMA_VERSION
  policies.py        FooterPolicy(신규), DecorationPolicy(신규), SizeHierarchyPolicy/PaletteClusterPolicy/RepeatAssetPolicy(보정)
  schemas.py         SlotDraft.align
  serialization.py   v2 + _migrate_v1
application/blueprint/
  extraction_use_case.py  _style_tokens/_assemble 에 정책 연결, _pattern_from_draft 에 align·decorations
  generation_use_case.py  footer 슬롯 제외(_write_one 의 슬롯 필터), SlotContentPolicy 에 footer 무시
  admin_use_case.py       update 승격, reextract()
infrastructure/blueprint/
  extractors/pdf_style_extractor.py  fills → (hex, area, box)
  fonts.py                           패스스루
  renderer/pptx_renderer.py          _decorations, _footer(style box), _logo(cover_box), _textbox(align, size role)
  renderer/shapes.py (신규)           add_rect(slide, emu, fill, line) — python-pptx 도형 헬퍼 (함수 길이 규칙)
  prompts.py / prompts_generation.py  align 규칙 1줄 / footer 제외
  repository.py                      replace()
interfaces/schemas/blueprint.py      v2 필드
scripts/blueprint_reextract.py (신규)
tests/integration/blueprint/test_golden_sample_fidelity.py (신규)
```

### 9.2 Dependency Rules

domain → (없음) / application → domain / infrastructure → domain / interfaces → application·domain. `tests/*/blueprint/test_layer_contract.py` 가 검증.

### 9.3 Key Signatures

```python
# domain/policies.py
class FooterPolicy:
    @staticmethod
    def apply(stats: SampleStats, caption_size: float) -> HeaderFooter  # logo_asset_id=None
class DecorationPolicy:
    @staticmethod
    def apply(stats: SampleStats, patterns: Sequence[PagePattern], palette: dict[str, str]
              ) -> tuple[tuple[Decoration, ...], dict[str, tuple[Decoration, ...]], list[str]]
    # (common, {pattern_id: decorations}, warnings)

# domain/value_objects.py
class StyleTokens:
    def size(self, role: str) -> float   # h1|h2|h3|subtitle|body|caption, 폴백 규칙 §3.1

# infrastructure/renderer/pptx_renderer.py
def _decorations(ctx, slide, pattern, is_cover) -> None   # common(비표지) + pattern
def _footer(ctx, slide, n, total) -> None                 # hf.footer_box / page_number_box or 폴백 상수
def _textbox(ctx, slide, box, lines, font_role, size_pt, bold, color, align="left", line_spacing=1.0)

# application/admin_use_case.py
async def reextract(self, blueprint_id, data, filename, max_pages, request_id) -> DocumentBlueprint

# infrastructure/repository.py
async def replace(self, bp: DocumentBlueprint, assets: Mapping[str, bytes]) -> None
```

---

## 10. Decision Records

| # | 결정 | 대안 | 근거 |
|---|------|------|------|
| DR-1 | 장식은 `PagePattern.decorations` + `StyleTokens.common_decorations` 분리 | Slot.kind=SHAPE | 슬롯은 LLM 채움 대상. 분리해야 프롬프트·SlotContentPolicy 오염 없음 |
| DR-2 | 푸터 슬롯을 스키마에서 제거하지 않고 **생성 프롬프트에서만 제외** | SlotKind.FOOTER 삭제 | 분류 LLM이 footer 영역을 인식해야 DecorationPolicy·FooterPolicy가 슬롯 box와 대조 가능. v1 호환도 유지 |
| DR-3 | 폰트 패스스루 (카탈로그 비면 원본명) | NanumGothic 치환 | 사용자 결정(Plan). 산출물 소비 PC 기준 원본 폰트 존재 확률 높음 |
| DR-4 | `sizes`는 REQUIRED 4키 유지 + 옵션 2키, 렌더러 폴백 | REQUIRED 6키 | v1 레코드·프론트 편집기 호환 |
| DR-5 | v1 로드 시 버전 보존, 저장(update/reextract) 시 2 승격 | 로드 시 승격 | GET 응답이 DB와 다르면 혼란. 쓰기 경계에서만 승격 |
| DR-6 | 재추출 = UseCase 메서드 + CLI | API + UI 버튼 | 사용자 결정. 1회성 운영 작업, 후속 확장 가능 |
| DR-7 | `align`만 LLM Draft에 추가 | 줄간격·앵커도 LLM | 나머지는 패턴 kind 로 결정적 매핑(toc → 번호·1.5 줄간격) — 비결정성 최소화 |
| DR-8 | DecorationPolicy 가 차트 막대 제외를 **비전 슬롯 포함율 ≥0.8 + (chart 슬롯 보유 패턴에서) 색·형상 규칙**으로 처리 (v0.2 정정) | 비전 LLM 판단 / IoU + find_tables | 비용 0, 결정적. find_tables 는 카드를 표로 오탐. p4 막대는 형상 규칙, 악센트 선은 포함율로 제외, 카드 줄무늬(0.01 폭)는 보존 |
| DR-9 | `align` 은 표지 title 슬롯에서만 LLM 값 신뢰, 나머지는 left (v0.2, Plan §5 위험완화) | 전 슬롯 신뢰 | 본문 슬롯의 오판 영향이 큼. 표지 제목 중앙 정렬만 실익 |

---

## 11. Implementation Guide

### 11.1 File Structure — §9.1

### 11.2 Implementation Order (TDD: 각 항목 테스트 선작성)

1. domain VO(Decoration, align, HeaderFooter/StyleTokens/Asset 확장, `size()`, CURRENT_SCHEMA_VERSION)
2. serialization v2 + v1 폴백 (+ `golden_v1.json` 픽스처)
3. interfaces 스키마 v2 필드 → 프론트 타입 동기화(`/api-contract-sync`)
4. policies: SizeHierarchy 확장 → Palette 보정 → RepeatAsset 보정 → FooterPolicy → DecorationPolicy
5. PdfStyleExtractor fills box / FontCatalog 패스스루
6. ExtractionUseCase 조립 (+ SlotDraft.align, 분류 프롬프트 1줄)
7. 렌더러: shapes.py → _decorations → _footer(box) → _logo(cover_box) → _textbox(align/spacing) → 역할별 크기
8. GenerationUseCase footer 제외 + 프롬프트
9. Repository.replace → AdminUseCase.update 승격·reextract → CLI
10. 회귀 테스트 `test_golden_sample_fidelity.py` (SC-1~8) → 실 DB 재추출 → 육안 확인

### 11.3 Session Guide

| Module | Key | 범위 | 순서 |
|--------|-----|------|------|
| module-1 | `schema` | 11.2 #1~3 (VO·직렬화·interface·프론트 타입) | 세션 1 |
| module-2 | `extract` | 11.2 #4~6 (정책·추출기·폰트·조립) | 세션 1~2 |
| module-3 | `render` | 11.2 #7~8 (렌더러·생성 프롬프트) | 세션 2 |
| module-4 | `migrate` | 11.2 #9~10 (replace·reextract·CLI·회귀·실DB) | 세션 3 |

```
/pdca do blueprint-style-fidelity --scope schema
/pdca do blueprint-style-fidelity --scope extract
/pdca do blueprint-style-fidelity --scope render
/pdca do blueprint-style-fidelity --scope migrate
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-23 | 초안 — Option C 선택, 정책 2개·VO·v2 직렬화·렌더 단계·reextract 설계 | 배상규 |
| 0.2 | 2026-08-23 | Check 반영 — §3.3 subtitle 규칙·DecorationPolicy 임계 실데이터 정정, rects 필드, _migrate_v1 제거, §8.5 픽스처, DR-8 정정, DR-9 추가, `build_admin_use_case` 헬퍼 | 배상규 |
