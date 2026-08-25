# blueprint-slot-box-snap Design Document

> **Summary**: 도메인 정책 `SlotBoxPolicy`가 비전 추정 슬롯 박스를 배정 힌트로만 쓰고, 좌표는 실측 span union으로 대체한다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft
> **Planning Doc**: [blueprint-slot-box-snap.plan.md](../../01-plan/features/blueprint-slot-box-snap.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 슬롯은 추정 좌표, 장식은 실측 좌표 — 둘을 맞추지 않아 모든 슬라이드의 정렬이 어긋난다 |
| **WHO** | P2 — 골든 샘플을 등록해 자사 문서 양식을 재현하려는 KB 운영자/에이전트 소유자 |
| **RISK** | 스냅이 샘플 1건에 과적합될 수 있다 — **교차 확인용 독립 문서가 없어 완화하지 못함** (§13.1) |
| **SUCCESS** | 렌더된 텍스트 위치가 원본 PDF와 0.1in 이내로 일치하고, 장식-슬롯 겹침이 0건 |
| **SCOPE** | 텍스트 슬롯(title/text/bullets) 좌표 스냅. 표·차트·이미지 및 기존 저장 블루프린트는 제외 |

---

## 1. Overview

### 1.1 Design Goals

1. 비전 모델의 **강점(슬롯 종류·역할 분류)은 유지**하고 **약점(좌표 정밀도)만 실측으로 대체**한다.
2. 규칙을 문서 특성이 아닌 **일반 기하 관계**(중심점 포함 / 최근접 경계 / 포함 캡)로만 정의한다.
3. 실패 시 기존 동작으로 안전하게 되돌아간다 — 스냅은 **개선 시도**이지 필수 경로가 아니다.
4. 생성물이 샘플보다 길어도 잘리지 않도록 높이를 확장하되, 장식 밖으로 새지 않게 캡한다.
5. 출처(PDF/PPTX) 분기 없이 `spans` 하나로 동작한다.

### 1.2 Design Principles

- **추정은 배정에만, 좌표는 실측에서**: vision 박스는 "이 span이 어느 슬롯 소속인가"를 정하는 데만 쓰고, 최종 좌표에는 그 값이 남지 않는다.
- **결정론**: 같은 입력이면 같은 출력. 동점은 명시적 타이브레이크로 깬다.
- **안전한 열화**: 매칭 0건이면 vision 좌표 유지 + 경고. 예외를 던지지 않는다.
- **겹침은 부수 효과로 해소**: 원본 문서가 겹치지 않았으므로 실측 스냅이면 충돌 회피 로직이 불필요하다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|----------|:-:|:-:|:-:|
| **배치** | `extraction_use_case.py` 모듈 함수 | 신규 `slot_box.py` + 기하 헬퍼 모듈 | `policies.py`에 `SlotBoxPolicy` |
| **New Files** | 0 | 2 | 0 |
| **Modified Files** | 1 | 1 | 2 |
| **기존 정책 일관성** | ❌ | ⚠️ | ✅ `DecorationPolicy`와 동형 |
| **레이어 규칙** | ⚠️ application에 기하 규칙 | ✅ domain | ✅ domain |
| **기하 헬퍼 재사용** | 복제 | 이관 (기존 소비자 영향) | ✅ 그대로 |
| **Complexity** | Low | High | Low |
| **Recommendation** | — | 정책이 더 늘어날 때 | **기본 권장** |

**Selected**: **Option C — Pragmatic** (Checkpoint 3)

**Rationale**: `SlotBoxPolicy`는 `DecorationPolicy`와 입출력 모양이 같다(`PageStats` + `PagePattern` → 보정 결과 + 경고). 같은 파일의 같은 계층에 두는 것이 구조적으로 일관되고, `_containment` 같은 기하 헬퍼를 이관 없이 재사용한다. B의 헬퍼 이관은 `DecorationPolicy` 등 기존 소비자를 함께 흔들어 이번 변경이 감당할 범위를 넘는다.

### 2.1 Component Diagram

```
                  ┌──────────────────────────────────────────────┐
                  │ domain/blueprint/policies.py                 │
  PageStats       │                                              │
   .spans ───────▶│  SlotBoxPolicy.apply(page, pattern, decos)   │
   .images        │    ① _snappable_spans()   푸터 밴드 배제      │
                  │    ② _assign()            중심점 포함 배정    │
  PagePattern ───▶│    ③ _union()             실측 union bbox     │
   .slots(vision) │    ④ _bottom()            경계 + 장식 캡      │
                  │    ⑤ 폴백                 매칭 0건 → 원본     │
  Decoration ────▶│                    │                          │
   (실측)          │                    ▼                          │
                  │        보정된 PagePattern + warnings          │
                  │                                              │
                  │  재사용: _containment / _clamped 불변식        │
                  └────────────────────┬─────────────────────────┘
                                       │
                  ┌────────────────────▼─────────────────────────┐
                  │ application/blueprint/extraction_use_case.py │
                  │   _style_and_patterns()                      │
                  │     1. PaletteClusterPolicy                  │
                  │     2. SizeHierarchyPolicy                   │
                  │     3. DecorationPolicy  ← 장식 확정          │
                  │     4. SlotBoxPolicy     ← 신규, 장식을 입력  │
                  └──────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
비전 LLM ──▶ SlotDraft(x,y,w,h)  ──▶ _clamped_box ──▶ Slot.box (추정)
                                                          │
PDF/PPTX ──▶ PageStats.spans (실측)                       │ 배정 힌트로만 사용
                     │                                    │
                     └────────────┬───────────────────────┘
                                  ▼
                        SlotBoxPolicy.apply()
                                  │
                                  ▼
                        Slot.box (실측 좌표)  ──▶ blueprint_json ──▶ 렌더
```

**핵심**: 최종 `Slot.box`에 비전 좌표는 **남지 않는다**(매칭 0건 폴백 제외).

### 2.3 실행 순서와 순환 없음

`DecorationPolicy`가 먼저, `SlotBoxPolicy`가 나중이다. 순환처럼 보이지만 아니다.

| 정책 | 입력으로 쓰는 슬롯 | 이번 변경 영향 |
|------|-------------------|:--------------:|
| `DecorationPolicy._eligible` | `_CONTENT_SLOT_KINDS = (CHART, IMAGE, TABLE)` (`policies.py:428,479`) | **없음** — 텍스트 슬롯을 보지 않는다 |
| `SlotBoxPolicy` | 텍스트 슬롯 + 장식(경계·캡용) | 장식이 먼저 확정돼야 함 |

텍스트 슬롯만 스냅하므로 **장식 판정이 스냅 전후로 동일**하다. 따라서 `DecorationPolicy → SlotBoxPolicy` 단방향 순서가 성립한다.

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `SlotBoxPolicy` | `PageStats`, `PagePattern`, `Decoration`, `RelBox` | 입력 |
| `SlotBoxPolicy` | `_containment`, `_FOOTER_BAND_Y` (기존) | 기하 판정 / 푸터 배제 기준 재사용 |
| `_style_and_patterns` | `SlotBoxPolicy` | 결선 |
| `pptx_renderer` | (변경 없음) | 보정된 좌표를 그대로 수신 |

---

## 3. Data Model

### 3.1 Entity Definition

**신규 엔티티 없음.** 기존 `Slot.box` 값만 바뀐다.

```python
@dataclass(frozen=True)
class Slot:
    box: RelBox        # ← 이 필드의 값만 변경 (형식·타입 무변경)
    ...
```

### 3.2 알고리즘 명세

#### ① 스냅 대상 span 선별 (FR-04)

```
제외: box.y >= _FOOTER_BAND_Y(0.88) AND size <= caption_size + 1
```

`FooterPolicy._band_spans`와 **동일 기준**을 쓴다. 푸터·페이지번호는 `HeaderFooter` 스타일 값으로만 렌더되므로(DR-2), 텍스트 슬롯에 배정되면 이중 렌더가 된다.

#### ② span → 슬롯 배정 (FR-02)

```
후보 = span 중심점을 포함하는 텍스트 슬롯들 (vision 박스 기준)
후보 0개 → 그 span은 버린다 (스냅에 기여하지 않음)
후보 1개 → 그 슬롯
후보 2개 이상 → 중심 y 거리가 가까운 슬롯, 동점이면 slot.id 사전순
```

골든 샘플에서는 후보 2개 이상인 span이 0건이었다. 타이브레이크는 방어적 규칙이다.

#### ③ union bbox (FR-01)

```
x  = min(span.x)
y  = min(span.y)
w  = max(span.x + span.w) - x
bot = max(span.y + span.h)          ← h 계산의 시작점
```

#### ④ 높이 확장 (FR-03)

```
경계 후보 = {
    다른 슬롯(종류 무관, footer 제외)의 스냅 후 top 중 bot 보다 아래인 것,
    장식(common + pattern)의 top 중 bot 보다 아래인 것,
    _FOOTER_BAND_Y
}
h = min(경계 후보) - y

캡 (Checkpoint 3): union(x, y, w, bot)을 완전히 포함하는 장식이 있으면
                   그 장식의 하단도 경계 후보에 넣는다
```

> **경계 후보에 텍스트 아닌 슬롯을 반드시 포함해야 한다.** 설계 중 시뮬레이션에서 이를 빠뜨려 `p5 title` 높이가 0.676(표 영역 전체를 삼킴)으로 나왔다. 포함 후 0.119로 정상화. §13.2 참조.

#### ⑤ 폴백 (FR-05)

```
배정 span 0건 → 해당 슬롯의 box 를 그대로 두고 경고 1건 추가
```

#### ⑥ 경계 불변식 (FR-06)

결과 박스는 `_clamped_box`와 동일한 불변식(0 ≤ x,y ≤ 0.99, w,h ≥ 0.01, x+w ≤ 1, y+h ≤ 1)을 만족해야 한다.

### 3.3 Database Schema

**변경 없음.** DDL·마이그레이션 추가 없음. `blueprint_json`의 좌표 **값**만 신규 추출분에서 달라진다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 계약 변경 |
|--------|------|:--------:|
| POST | `/admin/blueprints/extract` | **없음** (`SlotSchema.box` 구조 동일, 값만 정확해짐) |
| GET | `/admin/blueprints/{id}` | **없음** |
| PUT | `/admin/blueprints/{id}` | **없음** |

**응답 스키마 무변경 → 프론트엔드 타입 동기화 불필요** (루트 CLAUDE.md §4-1 요건 해당 없음).

### 4.2 관찰 가능한 동작 변화

```diff
  "slots": [
    { "id": "title", "kind": "title",
-     "box": { "x": 0.050, "y": 0.050, "w": 0.900, "h": 0.100 }   ← 전 페이지 동일한 추정값
+     "box": { "x": 0.062, "y": 0.081, "w": 0.256, "h": 0.171 }   ← 페이지별 실측값
    }
  ]
```

---

## 5. UI/UX Design

해당 없음 — 백엔드 전용. 관리 UI의 슬롯 미리보기가 실제 위치를 반영하는 부수 효과만 있다.

---

## 6. Error Handling

### 6.1 오류 정책

`SlotBoxPolicy`는 **예외를 던지지 않는다.** 도메인 순수 함수이며 모든 실패는 원본 유지 + 경고다.

| 상황 | 처리 | 경고 |
|------|------|:----:|
| 배정 span 0건 | vision 박스 유지 | ✅ FR-05 |
| 페이지에 span 자체가 없음 | 패턴 전체를 그대로 반환 | ✅ |
| union 폭·높이가 0에 수렴 | `_clamped_box` 최소값(0.01) 적용 | — |
| 경계 후보가 없음 | `_FOOTER_BAND_Y`가 항상 후보에 있어 발생 불가 | — |
| 텍스트 슬롯이 없는 패턴 | 무변경 반환 | — |

경고는 `blueprint.warnings`에 누적되어 관리 UI에서 확인 가능하다 — `DecorationPolicy`의 기존 경고 경로와 동일하다.

### 6.2 로깅

정책 자체는 로깅하지 않는다(도메인 순수). 경고 개수는 기존 `blueprint.extract` 완료 로그의 `warnings` 필드에 합산된다.

---

## 7. Security Considerations

- [x] 입력 검증 — 좌표는 이미 `SlotDraft`의 pydantic `ge/le` 제약과 `_clamped_box`를 통과한 값
- [x] 신뢰 경계 — 비전 LLM 출력은 **배정 힌트로만** 쓰이고 최종 좌표에 반영되지 않아, 오히려 LLM 출력 의존도가 낮아진다
- [x] 자원 소모 — 슬롯×span 이중 루프. 페이지당 span 수십 건 규모로 상수 시간에 가깝다
- [x] 인증/인가 — 변경 없음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| **L1: Domain Unit** | `SlotBoxPolicy` 규칙 전체 | pytest | Do |
| **L2: Application Integration** | `_style_and_patterns` 결선·순서 | pytest | Do |
| **L3: Golden Sample Regression** | 실제 PDF → 좌표·겹침 검증 | pytest + pymupdf | Do |
| **L4: Render End-to-End** | 렌더된 PPTX 텍스트 위치 vs 원본 PDF | pytest + python-pptx | Do |

### 8.2 L1: Domain Unit 시나리오

| # | 대상 | 입력 | 기대 |
|---|------|------|------|
| 1 | union | 슬롯에 span 3개 | x·y는 최솟값, w는 최대 우변 - x |
| 2 | 배정 | span 중심이 슬롯 A 박스 안 | A에 배정 |
| 3 | 배정 | span 중심이 어느 박스에도 없음 | 버려짐 — 어떤 슬롯에도 기여 안 함 |
| 4 | 배정 | span 중심이 A·B 두 박스에 포함 | 중심 y가 가까운 쪽 |
| 5 | 배정 | 중심 y 거리 동점 | slot.id 사전순 (결정론) |
| 6 | 푸터 배제 | y=0.95, size=caption | 어떤 슬롯에도 배정 안 됨 (FR-04) |
| 7 | 푸터 배제 | y=0.95, size=본문 크기 | **배정됨** — 크기 조건 미충족이므로 푸터 아님 |
| 8 | 경계 | 아래에 다른 텍스트 슬롯 | 그 슬롯 top까지 확장 |
| 9 | 경계 | 아래에 **표 슬롯** | 표 top까지 확장 (§13.2 회귀 방어) |
| 10 | 경계 | 아래에 장식 | 장식 top까지 확장 |
| 11 | 경계 | 아래에 아무것도 없음 | `_FOOTER_BAND_Y`까지 |
| 12 | 장식 캡 | union이 장식에 완전 포함 | 장식 하단으로 캡 (Checkpoint 3) |
| 13 | 장식 캡 | union이 장식과 일부만 겹침 | 캡하지 않음 |
| 14 | 폴백 | 배정 span 0건 | vision 박스 유지 + 경고 1건 (FR-05) |
| 15 | 폴백 | 페이지에 span 없음 | 패턴 무변경 |
| 16 | 대상 한정 | table/chart/image 슬롯 | **무변경** — 스냅 대상 아님 |
| 17 | 대상 한정 | footer 슬롯 | 무변경 |
| 18 | 불변식 | 결과 박스 | 0≤x,y / w,h≥0.01 / x+w≤1 / y+h≤1 (FR-06) |
| 19 | 멱등 | 이미 스냅된 패턴 재적용 | 동일 결과 |

### 8.3 L2: Application Integration 시나리오

| # | 시나리오 | 기대 |
|---|----------|------|
| 20 | `_style_and_patterns` 호출 | 반환 패턴의 텍스트 슬롯이 스냅된 좌표 |
| 21 | 실행 순서 | `DecorationPolicy` 결과가 `SlotBoxPolicy` 입력으로 전달됨 |
| 22 | 장식 판정 불변 | 스냅 전후 `DecorationPolicy` 출력 동일 (§2.3 근거) |
| 23 | 경고 전파 | 스냅 경고가 `blueprint.warnings`에 누적 |

### 8.4 L3: Golden Sample Regression 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 24 | **SC-1 핵심** — 골든 PDF 추출 | 13개 텍스트 슬롯의 `x`·`y`가 그 슬롯 실측 span union과 **정확히 일치** |
| 25 | **SC-2** — 장식-슬롯 겹침 | 슬롯↔장식이 1:1인 패턴에서 부분 겹침 **0건**. p6(카드 3장)는 구조 한계로 제외 — Do 실측 §15 |
| 26 | **SC-3** — 표지 제목 | `x`가 0.062±0.001 (기존 0.200) |
| 27 | **SC-5** — 푸터 span | 어떤 텍스트 슬롯 union에도 푸터 좌표가 포함되지 않음 |
| 28 | 패턴 종류 다양성 | cover·toc·section_lead·chart_with_notes·table 5종 전부에서 스냅 성공 |

### 8.5 L4: Render End-to-End 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 29 | 골든 PDF → 블루프린트 → PPTX 렌더 | 각 텍스트 도형의 좌표가 원본 PDF 같은 역할 텍스트 위치와 **0.1in 이내** |
| 30 | 렌더 결과 도형 수 | 스냅 전후 동일 (좌표 외 변화 없음) |

> **시나리오 29가 SC-1의 진짜 검증이다.** §14에서 Plan의 SC-1 문구를 이 정의로 교체해야 한다 — 현재 문구("오차 0.1in 이하")는 스냅 결과를 실측 union과 비교하는 셈이라 **항상 참인 동어반복**이다.

### 8.6 Seed Data Requirements

| 픽스처 | 출처 | 수정 |
|--------|------|:----:|
| `samples/golden_sample_report.pdf` | 기존 | 금지 (회귀 기준선) |
| `tests/fixtures/blueprint/golden_v1.json` | 기존 | 금지 — **저장된 좌표를 쓰는 v1 스냅샷 테스트라 이번 변경 영향 없음** |
| L1 단위 테스트용 `PageStats`·`PagePattern` | 신규 | 테스트 내 팩토리 함수 (기존 `_bp()` 패턴) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 좌표 스냅 기하 규칙 (순수) | `src/domain/blueprint/policies.py` |
| **Application** | 정책 실행 순서 결선 | `src/application/blueprint/extraction_use_case.py` |
| **Infrastructure** | 변경 없음 | — |
| **Interfaces** | 변경 없음 | — |

### 9.2 Dependency Rules

```
Application ──▶ Domain
                  ▲
Infrastructure ───┘

SlotBoxPolicy 는 policies.py 내부 헬퍼와 value_objects 만 참조한다.
test_layer_contract.py 의 금지 임포트 검사를 그대로 통과한다.
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 상태 |
|-----------|-------|----------|:----:|
| `SlotBoxPolicy` | Domain | `policies.py` | 신규 클래스 |
| `_snappable_spans` / `_assign` / `_union` / `_bottom` | Domain | `policies.py` | 신규 헬퍼 |
| `_style_and_patterns` 결선 | Application | `extraction_use_case.py` | 수정 |

---

## 10. Coding Convention Reference

### 10.1 이 기능의 적용 규칙

| Item | Convention |
|------|-----------|
| 함수 길이 | 40줄 이하 — `apply`는 5개 단계 헬퍼로 분할 |
| if 중첩 | 2단계 이하 |
| 타이핑 | 명시적 (`Sequence[TextSpan]`, `RelBox`, `tuple[PagePattern, ...]`) |
| 하드코딩 | 임계값은 모듈 상수 (`_FOOTER_BAND_Y` 재사용, 신규 상수는 `_SNAP_` 접두) |
| 로깅 | 정책 내 로깅 없음 (§6.2) |
| `print()` | 금지 |
| 주석 | `# Design Ref: §{절}` / `# Plan SC-{n}` |
| 린트 | **변경한 파일에만** `ruff check` |

### 10.2 명명

| 대상 | 규칙 | 예시 |
|------|------|------|
| 정책 클래스 | PascalCase + `Policy` | `SlotBoxPolicy` |
| 내부 헬퍼 | `_` 접두 snake_case | `_snappable_spans`, `_assign`, `_union`, `_bottom` |
| 상수 | `_UPPER_SNAKE` | `_SNAP_TEXT_KINDS` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/blueprint/
│   └── policies.py                    [수정] SlotBoxPolicy + 헬퍼 4개 (~90줄)
└── application/blueprint/
    └── extraction_use_case.py         [수정] _style_and_patterns 결선 (~5줄)

tests/
├── domain/blueprint/
│   └── test_slot_box_policy.py        [신규] 시나리오 1~19
├── application/blueprint/
│   └── test_extraction_use_case.py    [수정] 시나리오 20~23
└── integration/blueprint/
    └── test_golden_sample_fidelity.py [수정] 시나리오 24~30
```

**src 수정 2 (~95줄), 테스트 신규 1 / 수정 2 (~260줄)**

### 11.2 Implementation Order

TDD — 각 단계 Red → Green → Refactor.

1. [ ] **배정·union** — 시나리오 1~5(Red) → `_snappable_spans`·`_assign`·`_union`(Green)
2. [ ] **푸터 배제** — 시나리오 6~7 (FR-04)
3. [ ] **높이 경계** — 시나리오 8~11. **시나리오 9(표 슬롯 경계)를 반드시 포함** — §13.2 결함 회귀 방어
4. [ ] **장식 캡** — 시나리오 12~13
5. [ ] **폴백·대상 한정·불변식** — 시나리오 14~19
6. [ ] **결선** — 시나리오 20~23. `DecorationPolicy` 다음 순서 고정
7. [ ] **골든 샘플 회귀** — 시나리오 24~28
8. [ ] **렌더 E2E** — 시나리오 29~30 (SC-1의 실질 검증)
9. [ ] 변경 파일 `ruff check` + blueprint 전체 회귀

> **3번의 시나리오 9를 건너뛰지 말 것.** 설계 시뮬레이션에서 실제로 밟은 함정이다(§13.2).

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 스냅 정책 | `module-1` | 구현 1~5 — `SlotBoxPolicy` + 도메인 테스트 19건 | 25-30 |
| 결선·검증 | `module-2` | 구현 6~9 — 결선, 골든 회귀, 렌더 E2E | 20-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 45-55 |
| Session 3 | Check + Report | 전체 | 20-30 |

> 단일 세션 구현을 권장한다. 컨텍스트가 부족하면 `module-1`에서 끊는다.

---

## 12. Key Design Decisions (DR)

| ID | Decision | Rationale |
|----|----------|-----------|
| **DR-1** | `SlotBoxPolicy`를 `policies.py`에 배치 | `DecorationPolicy`와 입출력 모양이 동일. 기하 헬퍼 이관 없이 재사용 (Checkpoint 3, Option C) |
| **DR-2** | 비전 박스는 **배정 힌트로만**, 최종 좌표에 미반영 | 골든 샘플에서 매칭 실패 0건 — 비전은 영역은 맞히고 정밀도만 틀린다. 강점만 취한다 |
| **DR-3** | 푸터 배제는 `FooterPolicy._band_spans`와 **동일 기준** | 기준이 갈리면 어떤 span은 푸터로도 슬롯으로도 렌더된다. 상수 `_FOOTER_BAND_Y` 공유 |
| **DR-4** | 높이 경계 후보에 **텍스트 아닌 슬롯도 포함** | 설계 시뮬레이션에서 누락 시 `p5 title` 높이가 표 전체를 삼켰다 (§13.2) |
| **DR-5** | union이 장식에 **완전 포함**되면 장식 하단으로 캡 | 생성물 텍스트가 샘플보다 길어도 하이라이트 박스 밖으로 새지 않는다 (Checkpoint 3) |
| **DR-6** | 배정 동점은 **중심 y 거리 → slot.id 사전순** | 결정론. 골든에서는 발생하지 않았으나 방어적으로 고정 |
| **DR-7** | `DecorationPolicy` → `SlotBoxPolicy` 순서 | 장식이 경계·캡 입력. 역방향 의존은 없음 — 장식 판정은 텍스트 슬롯을 보지 않는다 (§2.3) |
| **DR-8** | 출처(PDF/PPTX) **분기 없음** | PPTX의 span box는 이미 도형 실측이라 균일 적용이 더 단순하고 양쪽 다 개선된다 (§13.3) |
| **DR-9** | 실패는 **원본 유지 + 경고**, 예외 없음 | 스냅은 개선 시도이지 필수 경로가 아니다. 기존 동작이 안전망 |

---

## 13. Verification Notes (설계 중 실측)

### 13.1 ⚠️ 과적합 리스크 — 완화 실패

Plan §5 최상단 리스크의 완화책은 "`samples/`의 다른 PPTX 2건으로 교차 확인"이었다. **불가능하다.**

- `samples/`의 PPTX 3건은 전부 **우리가 생성한 산출물**이다
- PPTX 추출 경로는 `render_png=None`(`pptx_style_extractor.py:106`)이라 **비전 분류를 아예 타지 않는다**

즉 **비전 좌표 추정 문제를 재현하는 독립 문서가 이 저장소에 없다.** 리스크는 미완화 상태로 남는다.

**대신 확보한 것**: 골든 샘플 6페이지가 cover / toc / section_lead(×2) / chart_with_notes / table **5종 패턴**을 커버한다. 규칙을 문서 특성이 아닌 일반 기하로만 정의했고(DR-2·DR-4·DR-5), 실패 시 폴백(DR-9)이 안전망이다. 그래도 **단일 문서 기반이라는 사실은 바뀌지 않는다.**

**권장**: 실사용 문서 1~2건을 확보해 Check 또는 후속 사이클에서 교차 확인.

### 13.2 설계 시뮬레이션이 잡은 규칙 결함

높이 경계 후보를 텍스트 슬롯으로만 한정한 초안을 골든 샘플에 돌린 결과:

```
p5 title  h = 0.676   ← 표 영역(0.2~0.7)을 통째로 삼킴
```

표·차트·이미지 슬롯을 경계 후보에 넣은 뒤 **0.119로 정상화**됐다. DR-4로 고정하고 시나리오 9로 회귀 방어한다.

### 13.3 PPTX 경로 — 분기 불필요 확인

Plan §6.2가 "PPTX 휴리스틱 경로의 스냅 적용 여부 결정 필요"로 남긴 항목의 답:

- PPTX는 비전을 타지 않아 이번 문제가 애초에 없다
- 그러나 `_heuristic_pattern`의 `_TITLE_BAND`/`_BODY_BAND`도 **상수**라 부정확하다
- PPTX의 span box는 `_runs(shape, box, theme)`에서 **도형 실측 박스**다

따라서 균일 적용이 분기보다 단순하고 PPTX도 개선된다 (DR-8).

### 13.4 시뮬레이션 최종 결과

| 항목 | 결과 |
|------|------|
| 스냅된 텍스트 슬롯 | 13 / 13 |
| 장식-텍스트 **부분** 겹침 | **0건** (3페이지 0.15in 겹침 해소) |
| 최대 이동량 | 표지 제목 1.83in |
| 높이 이상값 | 0건 (DR-4 적용 후) |
| 매칭 0건 폴백 발동 | 0건 |

---

## 14. Plan 문서 갱신 필요 항목

| 항목 | 내용 |
|------|------|
| Plan §4.1 SC-1 | **문구 교체 필요** — 현재 "슬롯 좌표 오차 0.1in 이하"는 스냅 결과를 실측 union과 비교하는 **동어반복**이다. "**렌더된 PPTX의 텍스트 위치가 원본 PDF와 0.1in 이내**"(시나리오 29)로 바꿔야 실질 검증이 된다 |
| Plan §5 과적합 리스크 | 완화책 "다른 PPTX 2건 교차 확인"을 **"불가능 — 독립 문서 없음"**으로 정정하고, 미완화 상태임을 명시 (§13.1) |
| Plan §6.2 PPTX 경로 | "Needs verification" → **"분기 불필요, 균일 적용"**으로 확정 (§13.3) |
| Plan §7.2 | 미정 2건(정책 배치 레이어 / 아래쪽 경계 우선순위) → DR-1 / DR-4 로 확정 |

---

## 15. Do 단계 실측 — 다중 카드 패턴의 구조적 한계

골든 6페이지(p6)는 카드 3장이고, 각 카드는 장식 박스 + 액센트 바 + 소제목(15pt) + 본문(13pt)이다. 그런데 **비전 모델은 이 6개 텍스트를 `bullets` 슬롯 하나로 뭉쳤다.**

```
슬롯 bullets  0.266 ─────────────────────── 0.880   ← 하나
장식 deco2    0.241 ── 0.407
장식 deco1              0.444 ── 0.611
장식 deco3                        0.648 ── 0.815
```

슬롯 하나가 카드 3장을 가로지르므로 **좌표를 아무리 정확히 스냅해도 부분 겹침이 불가피**하다. 높이 확장 때문도 아니다 — union 자체(0.266~0.771)가 이미 세 카드에 걸쳐 있어, 확장 전에도 동일하게 3건 겹친다.

| 패턴 | 종류 | 부분 겹침 |
|------|------|:--------:|
| p1 | cover | 0건 |
| p2 | toc | 0건 |
| p3 | section_lead | **0건** ← 사용자 신고 원본, 해소 |
| p4 | chart_with_notes | 0건 |
| p5 | table | 0건 |
| p6 | section_lead (카드 3장) | **3건** ← 구조 한계 |

**결함 C(슬롯 내용 구조)로 이월한다.** 같은 페이지가 생성물에서 "카드 3개 전부 빈 상태"로 나온 것도 동일 원인이며, 슬롯 분할 없이는 양쪽 다 풀리지 않는다.

`test_known_limitation_multi_card_pattern_still_overlaps`가 겹침 3건을 고정한다 — 결함 C에서 해소되면 이 테스트가 실패해 이월 항목을 정리하도록 유도한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — Option C 선정, 시뮬레이션으로 DR-4 결함 발견·수정 | 배상규 |
| 0.2 | 2026-08-25 | Do 실측 반영 — §15 다중 카드 패턴 한계 추가, 시나리오 25 범위 조정 | 배상규 |
