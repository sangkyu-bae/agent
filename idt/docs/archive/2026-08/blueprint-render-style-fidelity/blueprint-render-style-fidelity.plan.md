# blueprint-render-style-fidelity Planning Document

> **Summary**: 차트 데이터 레이블·단위, 표 테두리·zebra, 문단 줄간격을 살려 렌더 스타일을 원본에 맞춘다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-26
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 렌더러가 **쓰지 않는 스타일 정보**가 넷 있다 — 차트에 데이터 레이블 코드가 아예 없고, `ChartSpec.unit`은 **죽은 필드**이며, `TableStyle.border`는 **한 번도 참조되지 않고**, 불릿 문단은 줄간격·여백이 **설정조차 안 된다**. 그 결과 막대 위 값이 없고, 축에 %가 없고, 표에 테두리가 없고, 설명이 빽빽하게 붙는다 |
| **Solution** | 넷을 렌더러에서 실제로 쓰게 하고, 하드코딩된 값(zebra 색 `#F3F4F6`, `spacing=1.0`)을 **스타일 토큰으로 이동**해 관리 UI에서 조정 가능하게 한다 |
| **Function/UX Effect** | 막대 위에 값이 뜨고, y축이 `0.0%` 형식이 되고, 표에 테두리·zebra가 생기고, 설명 문단이 골든과 같은 간격(18.8pt / 33.2pt)으로 벌어진다 |
| **Core Value** | A(폰트)·B(좌표)·C(내용)로 **무엇이 어디에 무슨 글자로** 들어갈지를 맞췄다. 마지막으로 **어떻게 보이는지**를 맞춘다 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 스타일 정보가 이미 있는데 렌더러가 쓰지 않아 산출물이 밋밋하다 |
| **WHO** | P2 — 골든 샘플로 자사 양식의 보고서를 만들려는 KB 운영자 |
| **RISK** | `StyleTokens`에 필드를 추가하면 직렬화·하위호환에 파급 |
| **SUCCESS** | 골든 대비 데이터 레이블·축 %·표 테두리·문단 여백이 모두 렌더 결과에 존재 |
| **SCOPE** | 렌더러 4개 항목 + 하드코딩 상수의 토큰화. 추출 시점 실측은 제외 |

---

## 1. Overview

### 1.1 Purpose

사용자가 신고한 결함 4건 중 마지막이다. A(폰트)·B(좌표)·C(내용) 사이클이 **무엇이 어디에 무슨 글자로** 들어갈지를 해결했고, 이번은 **어떻게 보이는지**를 다룬다.

네 항목 모두 **정보가 이미 존재하는데 렌더러가 소비하지 않는** 형태다. 새 데이터를 만드는 게 아니라 있는 것을 쓰게 한다.

### 1.2 Background

#### D-1 — 차트에 데이터 레이블 코드가 없다

```
chart_builder.py 검색: data_label / number_format / has_data_labels / font  →  0건
```

골든 원본 4페이지는 막대 위에 **9pt Bold 값**을 표시한다.

```
'1.62'  9.0pt Bold   '1.71'  9.0pt Bold   '1.95'  9.0pt Bold
'2.08'  9.0pt Bold   '2.41'  9.0pt Bold
```

#### D-2 — `ChartSpec.unit`이 죽은 필드다

```
src/ 전체에서 .unit 참조:
  generation_use_case.py:396   s.chart.unit     ← draft → VO 복사만
```

도메인 VO(`value_objects.py:385`)와 LLM 스키마(`schemas.py:112`)에 선언돼 있고 LLM이 채우기도 하지만, **렌더러가 한 번도 읽지 않는다.** 골든 y축은 `0.0%` `0.6%` `1.2%` `1.8%` `2.4%` `3.0%` 형식이다.

#### D-3 — `TableStyle.border` 미사용 + 값이 하드코딩

```python
# extraction_use_case.py:283 — 추출이 상수를 넣는다
table_style=TableStyle(
    header_bg=palette["primary"],   # 이것만 측정값
    header_text="#FFFFFF",
    border="#CCCCCC",               # 상수
    zebra=False,                    # 상수
)

# pptx_renderer.py:386 — 렌더러도 상수를 쓴다
if ts.zebra and r % 2 == 0:
    cell.fill.fore_color.rgb = rgb("#F3F4F6")   # 상수
# ts.border 는 어디서도 참조되지 않는다
```

**중요한 발견: zebra 로직 자체는 이미 골든과 정확히 일치한다.**

| | 골든 원본 (page 5) | 렌더러 |
|---|---|---|
| 헤더 | `[60,120,900,164]` navy `#1F3A5F` | `ts.header_bg` = palette primary ✅ |
| zebra | `[60,208,900,252]`, `[60,296,900,340]` `#F3F4F6` → **데이터 2·4행** | `if ts.zebra and r % 2 == 0` → **r=2, r=4** ✅ |
| 외곽선 | `[60,120,900,384]` stroke | **없음** ❌ |

즉 **`zebra=False` 상수 하나가 이미 맞는 로직을 막고 있다.**

#### D-4 — 문단 줄간격·여백이 설정조차 안 된다

```python
# pptx_renderer.py:_bullets (비-TOC)
spacing = 1.0
# → _styled_textbox
if line_spacing != 1.0:      # False! 아무것도 설정되지 않는다
    paragraph.line_spacing = line_spacing
```

문단 간 `space_after`도 소제목(FR-03, 6pt)을 빼면 0이다.

**골든 실측 (page 4, 13pt 본문)**

```
'• 중소기업 연체율 5분기 연속 상승 (…'   y=167.0
'2.41%)'                                y=185.8   ← 줄간격 18.8pt
'• 3Q 상승폭 +0.33%p는 최근 2년 내 최대'  y=219.0   ← 문단 간 33.2pt
'• 가계 부문은 1% 미만 유지, 변동성 낮음'  y=271.0   ← 52.0 - 18.8 = 33.2pt
'• 제조업(2.9%)·도소매(2.7%)가 부문 …'    y=323.0   ← 동일
```

두 줄짜리 문단과 한 줄짜리 문단 **양쪽에서 33.2pt로 일관**된다.

#### 스키마 버전 승격이 불필요하다

기존 v2 추가분이 `.get(default)` 패턴을 썼다.

```python
# serialization.py:_style
hf.get("page_number_format", ""),
common_decorations=_decorations(d.get("common_decorations")),
```

신규 스타일 필드도 같은 패턴이면 v1/v2 블루프린트가 **기본값으로 그대로 로드**된다. `CURRENT_SCHEMA_VERSION` 승격 없이 진행 가능하다.

### 1.3 Related Documents

- 사용자 지적 원본: 결함 D (`docs/04-report/blueprint-font-mapping-migration.report.md` §4.2)
- 선행 사이클: `pptx-font-fidelity`(A) · `blueprint-slot-box-snap`(B) · `blueprint-slot-content-fill`(C)
- 코딩 규칙: `idt/CLAUDE.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **D-1** 차트 데이터 레이블 표시 (크기·굵기·색은 스타일 토큰)
- [ ] **D-2** `ChartSpec.unit`을 축 숫자 서식으로 적용 — 죽은 필드 부활
- [ ] **D-3** `TableStyle.border`를 렌더러가 실제로 사용
- [ ] **D-3** zebra 색을 상수 → 토큰화, `zebra` 기본값 재검토
- [ ] **D-4** 불릿 문단 줄간격·문단 간 여백 적용
- [ ] 하드코딩 상수(`#F3F4F6`, `spacing=1.0`)의 스타일 토큰 이동
- [ ] 신규 필드가 v1/v2 블루프린트에서 기본값으로 로드됨을 검증
- [ ] 골든 샘플 기준 회귀 — 4개 항목이 렌더 결과에 존재

### 2.2 Out of Scope

- **차트 내부 텍스트 폰트** — 현재 Office 기본(Calibri)이다. 최초 결함 D 보고에는 포함됐으나 Checkpoint 2 선택 항목이 아니었다. **후속 항목으로 남긴다.**
- **추출 시점 실측** — zebra 여부·테두리색·줄간격을 PDF에서 측정하는 것. Checkpoint 2에서 "상수를 토큰으로 이동"을 택했으므로 추출은 기본값을 넣고 관리 UI에서 조정한다
- `schema_version` 승격 — `.get(default)` 패턴으로 불필요 (§1.2)
- 차트 종류 추가 (bar/line/pie 외)
- 표 열 정렬·숫자 서식 — 골든도 전부 좌측 정렬이라 현행과 동일

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 차트에 데이터 레이블을 표시한다. 크기·굵기·색은 스타일 토큰에서 온다 | High | Pending |
| FR-02 | `ChartSpec.unit`이 있으면 축(또는 레이블) 숫자 서식에 반영한다 | High | Pending |
| FR-03 | 표에 `TableStyle.border` 색으로 테두리를 그린다 | High | Pending |
| FR-04 | zebra 배경색을 `TableStyle` 토큰에서 읽는다 (상수 제거) | High | Pending |
| FR-05 | 불릿 문단에 줄간격과 문단 간 여백을 적용한다. 값은 스타일 토큰 | High | Pending |
| FR-06 | 신규 스타일 필드는 기본값을 가져 v1·v2 블루프린트가 수정 없이 로드된다 | High | Pending |
| FR-07 | 값이 없거나 0이면 기존 동작을 유지한다 (폴백) | Medium | Pending |
| FR-08 | `unit` 은 LLM 출력이므로 서식 문자열에 삽입하기 전 큰따옴표를 제거·이스케이프한다 | High | Pending |

> FR-08은 Design §7 안전 검토에서 발견된 항목이다 (DR-8).

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 스타일 값은 domain VO, 소비는 infrastructure 렌더러 | `test_layer_contract.py` |
| 하위호환 | v1·v2 블루프린트가 수정 없이 로드·렌더 | 기존 직렬화·v1 스냅샷 테스트 |
| API 계약 | `StyleSchema`에 선택 필드 추가 — 기존 클라이언트 무영향 | 관리 라우터 테스트 |
| 회귀 | blueprint 관련 기존 테스트(337건) 전부 통과 | `pytest tests/*/blueprint` |
| 결정론 | 렌더 결과가 같은 입력에 같은 출력 | 골든 회귀 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1 — 렌더된 차트에 **데이터 레이블이 존재**하고, 값이 `ChartSpec.series`와 일치한다
- [ ] SC-2 — `unit="%"` 인 차트의 축 숫자 서식에 **`%`가 반영**된다
- [ ] SC-3 — 렌더된 표에 **테두리가 존재**하고 색이 `TableStyle.border`와 일치한다
- [ ] SC-4 — `zebra=True`일 때 **데이터 2·4행**에 토큰 색이 칠해진다 (골든과 동일 행)
- [ ] SC-5 — 불릿 문단에 **줄간격과 `space_after`가 설정**되고, 값이 스타일 토큰과 일치한다
- [ ] SC-6 — **v1 스냅샷(`golden_v1.json`)이 수정 없이 로드·렌더**되고 신규 필드는 기본값을 갖는다
- [ ] SC-7 — 설계 §Test Plan의 **모든 시나리오**에 대응하는 자동화 테스트가 존재한다
- [ ] SC-8 — blueprint 관련 기존 테스트 회귀 0건

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하 / if 중첩 2단계 이하
- [ ] `print()` 없음, 명시적 타입
- [ ] **렌더러에 새 하드코딩 상수를 만들지 않는다** — 값은 토큰 또는 명명된 기본 상수
- [ ] ruff lint 0건 (**변경한 파일에만** 실행)
- [ ] 신규·변경 코드 커버리지 95% 이상

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **`StyleTokens` 필드 추가의 직렬화 파급** | High | Medium | 기존 v2 추가와 동일한 `.get(default)` 패턴 사용(§1.2 검증 완료). SC-6이 v1 스냅샷으로 고정 |
| ~~**python-pptx 차트 API 한계**~~ | Medium | ~~Medium~~ → **해소** | **설계 사전 검증으로 해소(설계 §13.1)**: 데이터 레이블·축 서식·폰트 전부 네이티브 지원, 저장 XML 반영 확인. **oxml 불필요**. 다만 pie 는 value_axis 접근이 ValueError → DR-5 로 대응 |
| **표 테두리 python-pptx 미지원** — cell.border_* 가 없어 oxml 직접 조작이 필요 | High | **확실 (실측)** | 신규 리스크 — 설계 §13.1 에서 발견. **전용 모듈 `renderer/table_borders.py` 로 격리**하고 AST 계약 테스트로 고정 (DR-3). `run_fonts.py` 선례와 동일 |
| **`zebra=True` 전환이 기존 산출물 외형을 바꾼다** | Medium | High | 추출 기본값을 바꿀지 Design에서 결정. 바꾸면 신규 추출분만 영향(기존은 저장값 유지) |
| **문단 여백 33.2pt가 과하게 커 내용이 잘린다** | Medium | Medium | 슬롯 높이는 B에서 경계까지 확장됐고 C에서 길이 초과가 권고로 낮아졌다. 넘침 여지가 이미 줄어든 상태. 골든 회귀로 확인 |
| **API 스키마에 필드 추가 → 프론트 영향** | Medium | Low | 선택 필드이므로 기존 클라이언트는 무시한다. 루트 CLAUDE.md §4-1에 따라 필요 시 프론트 타입 동기화 |
| 샘플 1건 과적합 | High | Medium | **세 사이클 연속 미해결 이월.** 다만 이번은 좌표·구조가 아닌 스타일 값이라 문서 특성 의존이 낮다 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `TableStyle` | Domain VO | zebra 배경색 필드 추가 (기본값 보유) |
| `StyleTokens` | Domain VO | 문단 줄간격·여백, 차트 레이블 스타일 필드 추가 (기본값 보유) |
| `chart_builder.add_chart` | Infrastructure | 데이터 레이블 + 축 숫자 서식 |
| `pptx_renderer._table` | Infrastructure | 테두리 적용, zebra 색을 토큰에서 |
| `pptx_renderer._bullets` | Infrastructure | 줄간격·`space_after` 적용 |
| `serialization._style` | Domain | 신규 필드 `.get(default)` 파싱 |
| `StyleSchema` / `TableStyleSchema` | Interfaces | 선택 필드 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `TableStyle.border` | READ | **현재 소비자 없음** | **의도된 변경** — 렌더러가 쓰기 시작 |
| `TableStyle.zebra` | READ | `pptx_renderer.py:386` | 값 출처만 변경 (상수 → 토큰) |
| `ChartSpec.unit` | READ | **현재 소비자 없음** (복사만) | **의도된 변경** — 죽은 필드 부활 |
| `add_chart` | 호출 | `pptx_renderer._render_slot:264` | 시그니처 변경 여부 Design에서 결정 |
| `_styled_textbox` | 호출 | `_textbox` / `_bullets` / `_footer` / `_title` / `_text` | **Needs verification** — 줄간격 규칙 변경이 푸터·제목에도 닿는지 확인 |
| `StyleTokens` | 생성 | `extraction_use_case._style_and_patterns:275` | 신규 필드 기본값 지정 필요 |
| `StyleTokens` | 직렬화 | `serialization.blueprint_to_dict` / `_style` | **Needs verification** — `asdict` 기반이라 자동 포함, 역방향은 `.get` 필요 |
| `StyleSchema` | API | `interfaces/schemas/blueprint.py` | 선택 필드 추가 → **프론트 타입 동기화 검토 필요** |
| v1 스냅샷 | TEST | `tests/fixtures/blueprint/golden_v1.json` | **수정 금지** — SC-6의 회귀 기준선 |
| 골든 통합 테스트 | TEST | `test_golden_sample_fidelity.py` | 도형 수 기대값 갱신 가능성 (테두리·레이블이 도형을 늘릴 수 있음) |

### 6.3 Verification

- [ ] `_styled_textbox`의 줄간격 변경이 푸터·제목 렌더를 바꾸지 않는지 확인
- [ ] v1 스냅샷이 신규 필드 없이 로드되는지 확인 (SC-6)
- [ ] python-pptx 차트 API가 축 서식·데이터 레이블을 실제로 반영하는지 **Design에서 렌더 후 XML 확인**
- [ ] `StyleSchema` 필드 추가 시 프론트 타입 동기화 필요 여부 판단
- [ ] 골든 렌더 도형 수 변화 확인 후 기대값 갱신

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (Thin DDD) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| D 범위 | 일부 / **전부** | **D-1 + D-2 + D-3 + D-4** | 넷 다 "정보는 있는데 안 쓴다"는 같은 성격 (Checkpoint 2) |
| 스타일 값 출처 | **토큰 이동** / PDF 실측 / 현행 상수 | **상수를 스타일 토큰으로 이동** | 범위가 렌더러에 머물고 관리 UI에서 조정 가능 (Checkpoint 2) |
| `schema_version` | 승격 / **유지** | **유지** | 기존 v2 추가와 동일한 `.get(default)` 패턴 (§1.2 검증 완료) |
| 신규 필드 배치 | 기존 VO 확장 / 중첩 VO / 상수 | **기존 VO 평평 확장 (Option C)** | 기존 v2 추가와 동일한 `.get(default)` 패턴 (설계 DR-1) |
| `zebra` 추출 기본값 | `False` 유지 / `True` 전환 | **`False` 유지** | 값 변경은 관리 UI 몴. 이번은 토큰화가 목표 (설계 DR-10) |
| `add_chart` 시그니처 | 스타일 전달 방식 | **`palette` → `style`** | 레이블 스타일이 필요하고 palette 는 style.palette 로 접근 (설계 DR-9) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

영향 레이어:
┌──────────────────────────────────────────────────────────┐
│ domain/blueprint/                                        │
│   value_objects.py    TableStyle·StyleTokens 필드 추가    │
│   serialization.py    .get(default) 파싱                  │
├──────────────────────────────────────────────────────────┤
│ application/blueprint/                                   │
│   extraction_use_case.py   신규 필드 기본값 지정           │
├──────────────────────────────────────────────────────────┤
│ infrastructure/blueprint/renderer/                       │
│   chart_builder.py    데이터 레이블 + 축 서식  (D-1·D-2)  │
│   pptx_renderer.py    표 테두리·zebra, 문단 여백 (D-3·D-4)│
├──────────────────────────────────────────────────────────┤
│ interfaces/schemas/                                      │
│   blueprint.py        선택 필드 추가                       │
└──────────────────────────────────────────────────────────┘

이번 사이클은 **렌더러가 주 무대**다 — 직전 세 사이클과 반대.
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙
- [x] `docs/rules/` 세부 규칙
- [x] ruff / pytest 설정
- [x] 도메인 순수성 AST 계약 테스트
- [x] oxml 조작은 `run_fonts.py` 1곳 격리 (pptx-font-fidelity DR)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 렌더러 상수 | 하드코딩 산재 (`#F3F4F6`, `1.0`) | **토큰 우선, 불가피하면 명명 상수** | High |
| oxml 직접 조작 | `run_fonts.py`에만 허용 | 차트 축 서식이 oxml을 요구하면 **격리 규칙 준수** | High |
| 린트 실행 범위 | 명문화됨 | **변경 파일에만 ruff** 유지 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | To Be Created |
|----------|---------|:-------------:|
| — | 신규 환경변수 없음 | ☐ |

### 8.4 Pipeline Integration

해당 없음.

---

## 9. Next Steps

1. [ ] 설계 문서 작성 (`/pdca design blueprint-render-style-fidelity`) — 필드 배치·`zebra` 기본값·`add_chart` 시그니처 3안 비교
2. [ ] **python-pptx 차트 API 사전 검증** — 데이터 레이블·축 서식을 실제로 렌더해 XML 확인 (§5 리스크)
3. [ ] TDD 구현 (Red → Green → Refactor)
4. [ ] Gap 분석 (`/pdca analyze`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-26 | 최초 작성 — 결함 D 대응 (D-1 레이블 / D-2 단위 / D-3 표 / D-4 문단) | 배상규 |
| 0.2 | 2026-08-26 | Design 사전검증 반영 — 차트 리스크 해소·표 테두리 리스크 신규, 미정 3건 확정, FR-08 추가 | 배상규 |
