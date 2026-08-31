# blueprint-render-style-fidelity Design Document

> **Summary**: 렌더러가 쓰지 않던 스타일 정보 넷을 살리고, 하드코딩 상수를 `TableStyle`·`StyleTokens` 토큰으로 옮긴다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-26
> **Status**: Draft
> **Planning Doc**: [blueprint-render-style-fidelity.plan.md](../../01-plan/features/blueprint-render-style-fidelity.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 스타일 정보가 이미 있는데 렌더러가 쓰지 않아 산출물이 밋밋하다 |
| **WHO** | P2 — 골든 샘플로 자사 양식의 보고서를 만들려는 KB 운영자 |
| **RISK** | ~~차트 API 한계~~ → **표 테두리 oxml 조작**으로 이동 (§13.1) |
| **SUCCESS** | 데이터 레이블·축 %·표 테두리·문단 여백이 모두 렌더 결과에 존재 |
| **SCOPE** | 렌더러 4개 항목 + 하드코딩 상수의 토큰화 |

---

## 1. Overview

### 1.1 Design Goals

1. **있는 정보를 쓰게 한다** — 새 데이터를 만들지 않는다. `unit`·`border`는 이미 존재하고 소비만 안 됐다.
2. **렌더러에 새 하드코딩을 만들지 않는다** — 값은 토큰, 불가피하면 명명된 기본 상수.
3. **하위호환을 깨지 않는다** — 신규 필드는 전부 기본값. v1/v2 블루프린트가 수정 없이 로드된다.
4. **oxml 조작을 전용 모듈에 격리한다** — `run_fonts.py` 선례를 따른다.
5. 값이 없거나 0이면 기존 동작 유지 (폴백).

### 1.2 Design Principles

- **API 우선, oxml 최후**: python-pptx가 지원하면 그것을 쓴다. 표 테두리만 예외다(§13.1).
- **평평한 토큰**: 중첩 VO를 만들지 않는다. 기존 v2 추가와 같은 `.get(default)` 패턴.
- **차트 종류별 분기 최소화**: 축이 없으면(pie) 레이블로 대체하는 한 갈래만 둔다.
- **리터럴 서식**: `unit`은 `'0.00"%"'`처럼 따옴표로 감싼다 — `'0.00%'`는 백분율 변환이 일어난다(§13.2).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|----------|:-:|:-:|:-:|
| **스타일 값 위치** | `zebra_bg`만 토큰, 나머지 상수 | 신규 `RenderStyle` VO 중첩 | 기존 VO 평평 확장 |
| **New Files** | 1 | 2 | 1 |
| **Modified Files** | 3 | 7 | 6 |
| **Checkpoint 2 충족** | ⚠️ 절반 | ✅ | ✅ |
| **직렬화** | 최소 | 중첩 파싱 추가 | 기존 `.get(default)` |
| **API 스키마** | 거의 무변경 | 중첩 스키마 | 평평한 선택 필드 |
| **schema_version** | 유지 | 유지 | 유지 |
| **Complexity** | Low | High | Medium |

**Selected**: **Option C — Pragmatic** (Checkpoint 3)

**Rationale**: 기존 v2 추가(`header_footer`·`common_decorations`)와 **동일한 평평한 `.get(default)` 패턴**이라 스키마 승격이 불필요하고 API도 선택 필드 추가로 끝난다. A는 Checkpoint 2 결정("상수를 토큰으로")을 절반만 충족하고, B는 `StyleSchema`에 중첩 객체가 생겨 프론트 타입 동기화 범위가 커진다.

### 2.1 Component Diagram

```
┌── domain/blueprint/value_objects.py ───────────────────┐
│  TableStyle    + zebra_bg, border_width_pt             │
│  StyleTokens   + body_line_spacing, body_space_after_pt│
│                + chart_label_size_pt, chart_label_bold │
│                (전부 기본값 보유)                        │
└────────────────────────┬───────────────────────────────┘
                         │ .get(default) 파싱
┌────────────────────────▼───────────────────────────────┐
│  serialization._style / interfaces StyleSchema         │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────┐
│ infrastructure/blueprint/renderer/                     │
│                                                        │
│  chart_builder.add_chart(slide, box, spec, style)      │
│    ├─ _data_labels()    D-1  plot.has_data_labels      │
│    └─ _number_format()  D-2  축 or 레이블 (pie 분기)    │
│                                                        │
│  pptx_renderer._table()                                │
│    ├─ zebra 색을 ts.zebra_bg 에서            D-3       │
│    └─ table_borders.apply_borders(...)       D-3       │
│                                                        │
│  pptx_renderer._bullets() / _styled_textbox()          │
│    └─ line_spacing + space_after             D-4       │
│                                                        │
│  table_borders.py  [신규] — oxml 조작 격리              │
└────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
StyleTokens / TableStyle (토큰)
        │
        ├──▶ chart_builder   데이터 레이블 크기·굵기·색, 숫자 서식
        ├──▶ _table          zebra 색, 테두리 색·굵기
        └──▶ _bullets        줄간격, 문단 간 여백

값 없음/0 → 기존 동작 유지 (FR-07)
```

### 2.3 oxml 격리 (Checkpoint 3)

python-pptx는 표 셀 테두리 API가 없다(§13.1). `renderer/table_borders.py`를 신설해 `run_fonts.py`와 같은 방식으로 격리한다.

| 모듈 | 책임 | oxml |
|------|------|:----:|
| `run_fonts.py` (기존) | run 의 latin/ea/cs 타이프페이스 | ✅ |
| `table_borders.py` (신규) | 표 셀 `a:lnL/lnR/lnT/lnB` | ✅ |
| 그 외 렌더러 전부 | python-pptx API만 | ❌ |

AST 계약 테스트로 `src/` 내 oxml 사용을 이 두 파일로 제한한다.

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `chart_builder.add_chart` | `StyleTokens` (시그니처 변경) | 레이블 스타일·서식 |
| `pptx_renderer._table` | `table_borders`, `TableStyle` | 테두리·zebra |
| `pptx_renderer._bullets` | `StyleTokens` (기존 `ctx.style`) | 줄간격·여백 |
| `table_borders` | `pptx.oxml.ns.qn` | oxml (격리) |
| `serialization._style` | 신규 필드 기본값 | 하위호환 |

---

## 3. Data Model

### 3.1 Entity Definition

**신규 VO 없음.** 기존 두 VO에 기본값을 가진 필드를 추가한다.

```python
@dataclass(frozen=True)
class TableStyle:
    header_bg: str
    header_text: str
    border: str
    zebra: bool
    zebra_bg: str = "#F3F4F6"        # 신규 — 렌더러 상수를 이동 (D-3)
    border_width_pt: float = 0.0     # 신규 — 0 이면 테두리 없음(현행) (D-3)


@dataclass(frozen=True)
class StyleTokens:
    ...
    body_line_spacing: float = 1.0        # 신규 — 1.0 이면 미설정(현행) (D-4)
    body_space_after_pt: float = 0.0      # 신규 — 0 이면 미설정(현행) (D-4)
    chart_label_size_pt: float = 0.0      # 신규 — 0 이면 레이블 없음(현행) (D-1)
    chart_label_bold: bool = True         # 신규 (D-1)
```

**기본값이 곧 현행 동작이다.** 필드를 추가해도 기존 블루프린트의 렌더 결과는 변하지 않는다 — FR-06·FR-07이 구조적으로 보장된다.

> **v0.2 정정**: 최초 초안이 `border_width_pt = 0.75` 로 적었으나 DR-2("기본값 = 현행 동작")와 어긋난다. **VO 기본값은 `0.0`(꺼짐)** 이고, 켜는 것은 **추출 기본값**의 몫이다(DR-10 v2).

### 3.2 알고리즘 명세

#### D-1 데이터 레이블 (FR-01)

```
chart_label_size_pt <= 0 AND unit 없음  →  아무것도 하지 않는다 (현행 유지)
그 외:
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.font.size  = Pt(chart_label_size_pt)
    dl.font.bold  = chart_label_bold
    dl.font.color.rgb = rgb(palette["text"])
    dl.position = OUTSIDE_END (bar/pie) | ABOVE (line)
```

레이블 위치는 차트 종류별로 다르다(§13.1 실측).

> **v0.2 정정**: 최초 초안은 가드를 `chart_label_size_pt <= 0` 단독으로 썼으나, 그러면
> `chart_label_size_pt=0` 인 pie 차트에서 단위를 표시할 방법이 없어 **DR-5 와 모순**된다.
> pie 는 축이 없어 레이블이 유일한 단위 표시 수단이다. 조건을 `AND unit 없음` 으로 정정한다.

#### D-2 단위 서식 (FR-02)

```
spec.unit 없음  →  아무것도 하지 않는다
있음:
    fmt = f'0.00"{unit}"'          # 리터럴 — §13.2
    레이블에 항상 적용: dl.number_format = fmt; number_format_is_linked = False
    축이 있으면(bar/line):
        value_axis.tick_labels.number_format = f'0.0"{unit}"'
        value_axis.tick_labels.number_format_is_linked = False
    pie: 축 접근이 ValueError → 레이블 적용으로 충분 (Checkpoint 3)
```

#### D-3 표 테두리·zebra (FR-03·FR-04)

```
zebra 색:  rgb(ts.zebra_bg)          # 상수 제거
테두리:    table_borders.apply_borders(table, ts.border, ts.border_width_pt)
           → 각 셀의 a:tcPr 에 lnL/lnR/lnT/lnB 를 solidFill 로 설정
           border_width_pt <= 0  →  아무것도 하지 않는다
```

#### D-4 문단 줄간격·여백 (FR-05)

```
_bullets (비-TOC):
    spacing      = style.body_line_spacing
    space_after  = style.body_space_after_pt      # 소제목 문단은 기존 6pt 유지

_styled_textbox:
    if line_spacing != 1.0:  paragraph.line_spacing = line_spacing   (기존)
    if line.space_after_pt:  paragraph.space_after  = Pt(...)        (기존)
```

**`_Line.space_after_pt`가 이미 존재한다**(pptx-font-fidelity FR-03에서 소제목용으로 도입). 불릿 줄에 값을 채우기만 하면 된다 — 렌더 로직 변경이 최소다.

**적용 범위 한정**: `_bullets`의 비-TOC 분기에만 적용한다. TOC는 기존 `_TOC_LINE_SPACING(1.5)`을 유지하고, 제목·본문·푸터는 손대지 않는다(§6.1).

### 3.3 Database Schema

**변경 없음.** DDL·마이그레이션 추가 없음. `schema_version` 승격 없음(§13.3).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 계약 변경 |
|--------|------|:--------:|
| POST | `/admin/blueprints/extract` | **선택 필드 추가** (기존 클라이언트 무영향) |
| GET | `/admin/blueprints/{id}` | 동상 |
| PUT | `/admin/blueprints/{id}` | 동상 |

### 4.2 관찰 가능한 동작 변화

```diff
  "style": {
    "table_style": {
      "header_bg": "#1F3A5F", "header_text": "#FFFFFF",
      "border": "#CCCCCC", "zebra": false,
+     "zebra_bg": "#F3F4F6", "border_width_pt": 0.75
    },
+   "body_line_spacing": 1.0,
+   "body_space_after_pt": 0.0,
+   "chart_label_size_pt": 0.0,
+   "chart_label_bold": true
  }
```

### 4.3 프론트엔드 영향

`StyleSchema`·`TableStyleSchema`에 **선택 필드**가 추가된다. 기존 클라이언트는 무시하므로 동작에 영향이 없지만, 관리 UI에서 새 값을 편집하려면 `idt_front/src/types/`에 필드를 추가해야 한다.

루트 CLAUDE.md §4-1에 따라 **프론트 타입 동기화 여부를 Do 단계에서 판단**한다 — 편집 UI를 이번에 만들지 않으면 동기화도 불필요하다.

---

## 5. UI/UX Design

해당 없음 — 백엔드 전용. 관리 UI에 새 스타일 필드가 노출되는 것은 후속 판단(§4.3).

---

## 6. Error Handling

### 6.1 오류 정책

렌더러는 **예외를 던지지 않는다.** 값이 없거나 0이면 기존 동작으로 되돌아간다(FR-07).

| 상황 | 처리 |
|------|------|
| `chart_label_size_pt <= 0` | 데이터 레이블 없음 (현행) |
| `spec.unit is None` | 숫자 서식 미적용 (현행) |
| pie 차트 + `unit` 있음 | 레이블에만 적용, 축 접근 안 함 |
| `border_width_pt <= 0` | 테두리 없음 (현행) |
| `zebra=False` | zebra 미적용 (현행) — 색 필드는 무시 |
| `body_line_spacing == 1.0` | 줄간격 미설정 (현행) |
| `body_space_after_pt == 0` | 여백 미설정 (현행) |
| v1/v2 블루프린트 (신규 필드 없음) | 전부 기본값 = 현행 동작 |

### 6.2 손대지 않는 것

| 대상 | 이유 |
|------|------|
| TOC 불릿 줄간격 | 기존 `_TOC_LINE_SPACING(1.5)` 유지 — 목차는 별도 규칙 |
| 제목·본문 텍스트박스 | `_title`/`_text`는 단일 문단이라 문단 여백 개념이 없다 |
| 푸터·페이지번호 | `wrap=False` 단일 줄 |
| 소제목 `space_after` | pptx-font-fidelity FR-03의 6pt 유지 |

### 6.3 로깅

렌더러는 로깅하지 않는다(기존 방침 유지).

---

## 7. Security Considerations

- [x] 입력 검증 — 색상은 기존 `_check_hex`, 수치는 VO 기본값
- [x] oxml 조작 — 전용 모듈 격리 + AST 계약 테스트 (§2.3)
- [x] 신뢰 경계 — `unit`은 LLM 출력이므로 **서식 문자열에 그대로 삽입된다**. 따옴표 이스케이프 필요 (§8.2 시나리오 12)
- [x] 자원 소모 — 셀 수 × 4변. 표 크기 상한(`max_rows`)이 이미 존재

> **`unit` 주입 주의**: `f'0.00"{unit}"'` 에서 `unit` 에 `"` 가 들어오면 서식이 깨진다. 큰따옴표를 제거하거나 이스케이프한다.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| **L1: VO / 직렬화** | 신규 필드 기본값·라운드트립 | pytest | Do |
| **L2: Renderer Unit** | `chart_builder` / `_table` / `_bullets` | pytest + python-pptx | Do |
| **L3: Golden Regression** | 골든 렌더 결과에 4개 항목 존재 | pytest | Do |
| **L4: Architecture** | oxml 격리 계약 | pytest + AST | Do |

### 8.2 L1: VO / 직렬화 시나리오

| # | 시나리오 | 기대 |
|---|----------|------|
| 1 | 신규 필드 없이 `TableStyle` 생성 | `zebra_bg="#F3F4F6"`, `border_width_pt=0.75` |
| 2 | 신규 필드 없이 `StyleTokens` 생성 | 4개 필드 기본값 |
| 3 | `zebra_bg` 잘못된 hex | `ValueError` (`_check_hex`) |
| 4 | 라운드트립 | `from_dict(to_dict(bp)) == bp` — 신규 필드 포함 |
| 5 | **v1 스냅샷 로드** (`golden_v1.json`) | 신규 필드 전부 기본값, 예외 없음 |
| 6 | 신규 필드가 담긴 dict 로드 | 값이 그대로 반영 |
| 7 | `StyleSchema` 왕복 | 선택 필드가 응답에 포함 |

### 8.3 L2: Renderer Unit 시나리오

#### 차트 (D-1·D-2)

| # | 시나리오 | 기대 |
|---|----------|------|
| 8 | `chart_label_size_pt=9` | 저장 XML 에 `<c:dLbls>` 존재 |
| 9 | `chart_label_size_pt=0` | `<c:dLbls>` 없음 (현행) |
| 10 | `unit="%"` + bar | 축·레이블 `formatCode` 에 `"%"` 리터럴 |
| 11 | `unit="%"` + pie | 레이블에만 적용, 예외 없음 |
| 12 | `unit='크기"'` (따옴표 포함) | 서식이 깨지지 않음 (§7 주입 방어) |
| 13 | `unit=None` | `formatCode` 미설정 |
| 14 | line 차트 레이블 위치 | `ABOVE` |

#### 표 (D-3)

| # | 시나리오 | 기대 |
|---|----------|------|
| 15 | `border_width_pt=0.75` | 각 셀 `a:tcPr` 에 `lnL/lnR/lnT/lnB` 존재, 색 일치 |
| 16 | `border_width_pt=0` | 테두리 요소 없음 (현행) |
| 17 | `zebra=True` | **데이터 2·4행**에 `zebra_bg` 색 (골든과 동일 행) |
| 18 | `zebra=False` | 배경 미적용 |
| 19 | `zebra_bg` 커스텀 색 | 상수가 아닌 토큰 색이 칠해짐 |

#### 문단 (D-4)

| # | 시나리오 | 기대 |
|---|----------|------|
| 20 | `body_line_spacing=1.45` | 불릿 문단의 `line_spacing` 설정됨 |
| 21 | `body_space_after_pt=33.2` | 불릿 문단의 `space_after` 설정됨 |
| 22 | 기본값(1.0 / 0) | 둘 다 미설정 (현행) |
| 23 | **TOC 불릿** | `_TOC_LINE_SPACING(1.5)` 유지 — 새 토큰 미적용 |
| 24 | 소제목 문단 | `space_after` 6pt 유지 (FR-03) |
| 25 | 제목·푸터 | 무변경 |

### 8.4 L3: Golden Regression 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 26 | **SC-1** 골든 렌더 차트 | 데이터 레이블 존재, 값이 `ChartSpec.series` 와 일치 |
| 27 | **SC-2** 축 서식 | `unit="%"` 차트의 `formatCode` 에 `%` 포함 |
| 28 | **SC-3** 표 테두리 | 셀에 테두리 요소 존재, 색이 `TableStyle.border` |
| 29 | **SC-4** zebra | 데이터 2·4행에 토큰 색 |
| 30 | **SC-5** 문단 | 불릿 문단에 줄간격·`space_after` 설정 |
| 31 | 슬라이드·도형 수 | 신규 필드 적용 전후 동일 (스타일만 변화) |
| 32 | **SC-6** v1 스냅샷 렌더 | 예외 없이 렌더, 기본값이라 현행과 동일 결과 |

### 8.5 L4: Architecture 시나리오

| # | 검사 | 기대 |
|---|------|------|
| 33 | `src/` 내 `pptx.oxml` 사용 파일 (AST) | `run_fonts.py`, `table_borders.py` **두 개뿐** |
| 34 | `chart_builder` 임포트 | domain VO 만, infrastructure 외부 참조 없음 |

### 8.6 Seed Data Requirements

| 픽스처 | 출처 | 수정 |
|--------|------|:----:|
| `samples/golden_sample_report.pdf` | 기존 | 금지 |
| `tests/fixtures/blueprint/golden_v1.json` | 기존 | **금지** — SC-6 회귀 기준선 |
| 신규 필드 테스트용 VO | 신규 | 테스트 내 팩토리 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 스타일 값 정의 + 직렬화 | `value_objects.py`, `serialization.py` |
| **Application** | 신규 필드 기본값 지정 | `extraction_use_case.py` |
| **Infrastructure** | 스타일 소비 (렌더) | `renderer/chart_builder.py`, `pptx_renderer.py`, `table_borders.py` |
| **Interfaces** | API 선택 필드 | `schemas/blueprint.py` |

### 9.2 Dependency Rules

```
Interfaces ──▶ Domain ◀── Infrastructure
                 ▲
Application ─────┘

table_borders.py 는 pptx 만 참조한다 (domain 무의존).
chart_builder.py 는 domain VO 를 참조한다 (기존과 동일).
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 상태 |
|-----------|-------|----------|:----:|
| `TableStyle` 필드 2개 | Domain | `value_objects.py` | 수정 |
| `StyleTokens` 필드 4개 | Domain | `value_objects.py` | 수정 |
| `_style` 파싱 | Domain | `serialization.py` | 수정 |
| 기본값 지정 | Application | `extraction_use_case.py` | 수정 |
| 데이터 레이블·서식 | Infrastructure | `chart_builder.py` | 수정 |
| 테두리·zebra·문단 | Infrastructure | `pptx_renderer.py` | 수정 |
| oxml 테두리 | Infrastructure | `renderer/table_borders.py` | **신규** |
| 선택 필드 | Interfaces | `schemas/blueprint.py` | 수정 |

---

## 10. Coding Convention Reference

| Item | Convention |
|------|-----------|
| 함수 길이 | 40줄 이하 — `add_chart`는 `_data_labels`/`_number_format` 헬퍼로 분할 |
| if 중첩 | 2단계 이하 |
| 타이핑 | 명시적 (`StyleTokens`, `TableStyle`, `float`) |
| **하드코딩** | **렌더러에 새 상수를 만들지 않는다.** 값은 VO 기본값에 둔다 |
| oxml | `table_borders.py` 에만 (§2.3) |
| 로깅 | 렌더러 로깅 없음 |
| 주석 | `# Design Ref: blueprint-render-style-fidelity §{절}` / `# Plan SC-{n}` |
| 린트 | **변경한 파일에만** `ruff check` |

### 10.2 명명

| 대상 | 규칙 | 예시 |
|------|------|------|
| VO 필드 | snake_case + 단위 접미사 | `body_space_after_pt`, `border_width_pt` |
| 헬퍼 | `_` 접두 | `_data_labels`, `_number_format`, `_label_position` |
| 상수 | `_UPPER_SNAKE` | `_LABEL_POSITIONS` (차트종류 → 위치 매핑) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/blueprint/
│   ├── value_objects.py                [수정] TableStyle +2, StyleTokens +4
│   └── serialization.py                [수정] .get(default) 파싱
├── application/blueprint/
│   └── extraction_use_case.py          [수정] 기본값 지정
├── infrastructure/blueprint/renderer/
│   ├── table_borders.py                [신규] oxml 테두리 (~40줄)
│   ├── chart_builder.py                [수정] 레이블 + 서식 (~50줄)
│   └── pptx_renderer.py                [수정] 테두리·zebra·문단 (~15줄)
└── interfaces/schemas/
    └── blueprint.py                    [수정] 선택 필드

tests/
├── domain/blueprint/
│   ├── test_value_objects.py           [수정] 시나리오 1~3
│   └── test_serialization.py           [수정] 시나리오 4~6
├── infrastructure/blueprint/
│   ├── test_chart_builder.py           [신규] 시나리오 8~14
│   ├── test_table_borders.py           [신규] 시나리오 15~16
│   └── test_pptx_renderer.py           [수정] 시나리오 17~25
├── api/test_admin_blueprint_router.py  [수정] 시나리오 7
├── domain/blueprint/test_layer_contract.py [수정] 시나리오 33~34
└── integration/blueprint/test_golden_sample_fidelity.py [수정] 시나리오 26~32
```

**src 신규 1 / 수정 6 (~120줄), 테스트 신규 2 / 수정 6**

### 11.2 Implementation Order

TDD — 각 단계 Red → Green → Refactor.

1. [ ] **VO + 직렬화** — 시나리오 1~7. 기본값이 현행 동작이므로 **이 단계만으로 회귀 0건**이어야 한다
2. [ ] **D-4 문단** — 시나리오 20~25. `_Line.space_after_pt`가 이미 있어 가장 단순
3. [ ] **D-3 zebra** — 시나리오 17~19. 상수 → 토큰 치환만
4. [ ] **D-3 테두리** — 시나리오 15~16 + `table_borders.py` 신설
5. [ ] **D-1 데이터 레이블** — 시나리오 8~9, 14
6. [ ] **D-2 단위 서식** — 시나리오 10~13. **주입 방어(12)를 빠뜨리지 말 것**
7. [ ] **골든 회귀** — 시나리오 26~32
8. [ ] **아키텍처 계약** — 시나리오 33~34
9. [ ] 변경 파일 `ruff check` + blueprint 전체 회귀

> **1번이 회귀 0건이어야 하는 이유**: 기본값 = 현행 동작이 이번 설계의 하위호환 근거다(FR-06·FR-07). 여기서 깨지면 설계 전제가 틀린 것이다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| VO·직렬화 | `module-1` | 구현 1 — 필드 추가, 기본값, 하위호환 | 15-20 |
| 표·문단 | `module-2` | 구현 2~4 — 문단 여백, zebra, 테두리(oxml) | 25-30 |
| 차트 | `module-3` | 구현 5~6 — 레이블, 단위 서식 | 20-25 |
| 검증 | `module-4` | 구현 7~9 — 골든 회귀, 계약, 회귀 | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2,module-3,module-4` | 55-70 |
| Session 3 | Check + Report | 전체 | 20-30 |

---

## 12. Key Design Decisions (DR)

| ID | Decision | Rationale |
|----|----------|-----------|
| **DR-1** | 기존 VO를 평평하게 확장 (Option C) | 기존 v2 추가와 동일한 `.get(default)` 패턴 — 스키마 승격·중첩 스키마 불필요 (Checkpoint 3) |
| **DR-2** | **신규 필드 기본값 = 현행 동작** | 하위호환이 구조적으로 보장된다. `chart_label_size_pt=0` → 레이블 없음, `body_line_spacing=1.0` → 미설정 |
| **DR-3** | oxml 은 `table_borders.py` 전용 모듈 | python-pptx가 셀 테두리를 지원하지 않는다(§13.1). `run_fonts.py` 선례를 따르고 AST 계약으로 고정 (Checkpoint 3) |
| **DR-4** | `unit` 은 **리터럴 서식** `'0.00"%"'` | `'0.00%'` 는 백분율 변환이 일어나 1.62 → 162.00% 가 된다 (§13.2) |
| **DR-5** | pie 는 축 대신 **레이블에 서식 적용** | `value_axis` 접근이 `ValueError` (§13.1). 사용자는 여전히 단위를 본다 (Checkpoint 3) |
| **DR-6** | 레이블 위치는 차트 종류별 매핑 | bar·pie `OUTSIDE_END`, line `ABOVE` — 실측 확인 (§13.1) |
| **DR-7** | 문단 토큰은 **비-TOC 불릿에만** | TOC는 기존 1.5 규칙, 제목·푸터는 단일 문단이라 무의미 |
| **DR-8** | `unit` 큰따옴표 제거·이스케이프 | LLM 출력이 서식 문자열에 삽입된다 (§7) |
| **DR-9** | `chart_builder.add_chart` 시그니처를 `palette` → `style` 로 | 레이블 스타일이 필요하고 `palette` 는 `style.palette` 로 접근 가능 |
| **DR-10** | ~~`zebra` 추출 기본값 `False` 유지~~ → **추출이 골든 실측값으로 스타일을 켠다** | **Checkpoint 5(v0.2)에서 변경.** 원안대로면 토큰만 생기고 기본 산출물이 그대로라 사용자 신고 2건(표 테두리·문단 여백)이 미해소로 남는다(분석 §5.1). VO 기본값(꺼짐)은 하위호환용으로 유지하고, **추출만** `zebra=True`·`border_width_pt=0.75`·`body_line_spacing=1.45`·`body_space_after_pt=33.2`·`chart_label_size_pt=caption` 을 넣는다 |

---

## 13. Verification Notes (설계 중 실측)

### 13.1 python-pptx API 사전 검증 — 리스크가 뒤집혔다

Plan §9 절차대로 실제 렌더 후 XML을 확인했다.

**차트 (Plan의 최대 리스크) — 전부 네이티브 지원**

```
plot.has_data_labels                  OK
data_labels.font size/bold/color      OK
data_labels.position                  OK
data_labels.number_format             OK
value_axis.tick_labels.number_format  OK
chart.font.name/size                  OK

저장 후 XML:  <c:dLbls> 있음 · formatCode 있음 · <c:valAx> 있음
formatCode 값: ['0.00&quot;%&quot;', '0.0&quot;%&quot;']
```

**oxml 조작이 불필요하다.** Plan §5 최상단 리스크는 해소됐다.

**차트 종류별 제약**

| 종류 | 레이블 위치 | `number_format` | `value_axis` |
|------|:----------:|:--------------:|:-----------:|
| bar | `OUTSIDE_END` ✅ | ✅ | ✅ |
| line | `ABOVE` ✅ | ✅ | ✅ |
| pie | `OUTSIDE_END` ✅ | ✅ | ❌ **ValueError** |

**표 — python-pptx 미지원 (신규 리스크)**

```
cell.border_left / border_top / border_bottom / border_right   전부 없음
tbl._tbl (oxml)                                                접근 가능
```

`a:tcPr` 에 `a:lnL/lnR/lnT/lnB` 를 직접 넣어야 한다 → DR-3.

### 13.2 서식 리터럴 함정

골든은 값 `1.62` 를 `1.62%` 로 표시한다. 데이터가 이미 퍼센트 값이므로 **백분율 변환을 하면 안 된다.**

```
'0.00"%"'   →  1.62 를 "1.62%" 로 표시 (리터럴 접미사)    ← 올바름
'0.00%'     →  1.62 를 "162.00%" 로 표시 (백분율 변환)   ← 틀림
```

DR-4로 고정하고 시나리오 10이 검증한다.

### 13.3 스키마 버전 승격 불필요 확인

기존 v2 추가분이 `.get(default)` 패턴을 쓴다.

```python
# serialization.py:_style
hf.get("page_number_format", ""),
common_decorations=_decorations(d.get("common_decorations")),
```

신규 필드도 같은 패턴이면 v1/v2 블루프린트가 기본값으로 로드된다. `CURRENT_SCHEMA_VERSION` 유지 (DR-1). 시나리오 5가 v1 스냅샷으로 고정한다.

### 13.4 골든 목표값

| 항목 | 골든 실측 | 대응 토큰 |
|------|----------|----------|
| 데이터 레이블 | 9pt Bold | `chart_label_size_pt=9`, `chart_label_bold=True` |
| 축 서식 | `0.0%` | `unit="%"` → `'0.0"%"'` |
| 표 헤더 | `#1F3A5F` | `header_bg` (기존, 측정값) |
| zebra | 데이터 2·4행 `#F3F4F6` | `zebra_bg` (기본값이 이미 일치) |
| 표 외곽선 | stroke | `border` + `border_width_pt` |
| 본문 줄간격 | 18.8pt (13pt의 1.45배) | `body_line_spacing=1.45` |
| 문단 간 여백 | 33.2pt | `body_space_after_pt=33.2` |

**zebra 로직은 이미 골든과 일치**한다 — `if ts.zebra and r % 2 == 0` 이 데이터 2·4행을 칠한다. `zebra=False` 상수만 막고 있다(Plan §1.2).

---

## 14. Plan 문서 갱신 필요 항목

| 항목 | 내용 |
|------|------|
| Plan §5 | "python-pptx 차트 API 한계" 리스크를 **해소**로 정정 (§13.1) |
| Plan §5 | **신규 리스크 추가** — "표 테두리 python-pptx 미지원 → oxml 조작 필요", 완화책 DR-3 |
| Plan §7.2 | 미정 3건 확정 — 필드 배치(DR-1) / `zebra` 기본값(DR-10) / `add_chart` 시그니처(DR-9) |
| Plan §3.1 | **FR-08 추가 검토** — `unit` 주입 방어(§7·DR-8). 최초 요구사항에 없었다 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-26 | 최초 작성 — Option C 선정, API 사전 검증으로 리스크 재배치 | 배상규 |
| 0.2 | 2026-08-29 | Checkpoint 5 반영 — DR-10 변경(추출이 스타일을 켠다), §3.2 D-1 가드 조건 정정 | 배상규 |
