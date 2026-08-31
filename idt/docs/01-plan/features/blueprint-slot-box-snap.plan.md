# blueprint-slot-box-snap Planning Document

> **Summary**: 비전 LLM이 추정한 텍스트 슬롯 좌표를 PDF 실측 span으로 스냅해, 장식 박스와 글자가 어긋나고 겹치는 문제를 해소한다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 장식(decoration) 좌표는 서버가 PDF에서 **실측**하는데, 슬롯 좌표는 비전 LLM이 **추정**한다. 둘을 한 번도 맞추지 않아 글자가 하이라이트 박스 밖으로 나가고 아래 요소와 겹친다. 골든 샘플 13개 텍스트 슬롯 중 **오차 0인 것이 하나도 없고, 최대 1.83in** 어긋난다. |
| **Solution** | 추출 시점에 도메인 순수 정책이 각 텍스트 슬롯의 좌표를 **그 슬롯에 속한 실측 span의 union bbox**로 스냅한다. 위치·폭은 실측값, 높이는 다음 경계까지 확장해 생성물이 샘플보다 길어도 잘리지 않게 한다. |
| **Function/UX Effect** | 제목·본문·불릿이 원본 문서와 같은 자리에 놓인다. 하이라이트 박스 안에 글자가 들어가고, 3페이지의 0.15in 겹침이 사라진다. 표지 제목이 1.83in 밀려 나오던 문제가 해소된다. |
| **Core Value** | 블루프린트가 "대충 비슷한 레이아웃"에서 **"원본을 실제로 재현하는 템플릿"**이 된다. 골든 샘플 충실도의 마지막 큰 축이다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 슬롯은 추정 좌표, 장식은 실측 좌표 — 둘을 맞추지 않아 모든 슬라이드의 정렬이 어긋난다 |
| **WHO** | P2 — 골든 샘플을 등록해 자사 문서 양식을 재현하려는 KB 운영자/에이전트 소유자 |
| **RISK** | 스냅이 샘플 1건에 과적합되어 다른 문서에서 오히려 나빠질 수 있다 |
| **SUCCESS** | 골든 샘플 텍스트 슬롯의 위치 오차가 0.1in 이하로 줄고, 장식-슬롯 겹침이 0건이 된다 |
| **SCOPE** | 텍스트 슬롯(title/text/bullets) 좌표 스냅. 표·차트·이미지 및 기존 저장 블루프린트는 제외 |

---

## 1. Overview

### 1.1 Purpose

`PagePatternDraft.slots`의 x/y/w/h는 비전 LLM이 페이지 이미지를 보고 **눈대중으로 찍은 값**이다. 실제 텍스트가 어디 있는지는 `PageStats.spans`에 정확히 들어 있는데도 쓰지 않는다. 이 두 정보를 결합해 슬롯 좌표를 바로잡는다.

### 1.2 Background

**좌표 출처가 둘로 갈려 있다.**

```python
# 장식 — 서버가 PDF 벡터 사각형에서 실측 (DR-1)
common, per_pattern, warnings = DecorationPolicy.apply(stats, patterns, palette)

# 슬롯 — 비전 LLM 출력을 클램프만 하고 그대로 사용
# extraction_use_case.py:356
box=_clamped_box(s.x, s.y, s.w, s.h)   # s = SlotDraft (비전 모델 출력)
```

#### 실측 증거 — 골든 샘플 전 텍스트 슬롯 오차

| 패턴 | 슬롯 | vision 추정 (x,y,w,h) | 실측 span union | Δx | Δy |
|------|------|----------------------|-----------------|---:|---:|
| p1 표지 | title | (0.200, 0.300, 0.600, 0.200) | (0.062, 0.394, 0.506, 0.084) | **1.83in** | **0.71in** |
| p1 표지 | text | (0.200, 0.500, 0.600, 0.100) | (0.062, 0.519, 0.326, 0.044) | **1.83in** | 0.14in |
| p2 목차 | title | (0.050, 0.050, 0.900, 0.100) | (0.062, 0.081, 0.050, 0.059) | 0.17in | 0.23in |
| p2 목차 | bullets | (0.100, 0.200, 0.800, 0.600) | (0.104, 0.246, 0.170, 0.317) | 0.06in | 0.34in |
| p3 | title | (0.050, 0.050, 0.900, 0.100) | (0.062, 0.081, 0.256, 0.059) | 0.17in | 0.23in |
| p3 | text | (0.050, 0.200, 0.900, 0.100) | (0.094, 0.252, 0.712, 0.034) | 0.58in | 0.39in |
| p3 | bullets | (0.050, 0.350, 0.900, 0.300) | (0.094, 0.435, 0.372, 0.168) | 0.58in | **0.64in** |
| p4 | title | (0.050, 0.050, 0.900, 0.100) | (0.062, 0.081, 0.222, 0.059) | 0.17in | 0.23in |
| p4 | bullets | (0.600, 0.200, 0.350, 0.600) | (0.635, 0.227, 0.276, 0.438) | 0.47in | 0.20in |
| p5 | title | (0.050, 0.050, 0.900, 0.100) | (0.062, 0.081, 0.214, 0.059) | 0.17in | 0.23in |
| p5 | text | (0.050, 0.750, 0.900, 0.050) | (0.062, 0.758, 0.270, 0.025) | 0.17in | 0.06in |
| p6 | title | (0.050, 0.050, 0.900, 0.100) | (0.062, 0.081, 0.197, 0.059) | 0.17in | 0.23in |
| p6 | bullets | (0.050, 0.200, 0.900, 0.600) | (0.094, 0.266, 0.452, 0.505) | 0.58in | 0.50in |

**13/13 슬롯에 오차가 있다.** 비전 출력값이 전부 `0.05 / 0.1 / 0.2 / 0.3 / 0.5 / 0.6 / 0.9` 같은 반올림 수치라는 점이 결정적이다 — 모델은 **측정하지 않고 일반적인 그리드를 찍어내고 있다.** 비표지 5개 페이지의 title 박스가 `(0.050, 0.050, 0.900, 0.100)`으로 **전부 동일**한 것이 그 증거다.

#### 접근이 성립하는 근거

**매칭 실패 슬롯이 0건이다.** vision 박스는 "어느 영역인지"는 맞히고 정밀도만 틀린다. 따라서 **vision 박스를 배정 힌트로 쓰고 실측 span으로 정밀화**하는 2단계가 성립한다. 슬롯 종류·역할 분류라는 비전 모델의 강점은 그대로 쓰고, 좌표라는 약점만 실측으로 대체한다.

#### 겹침도 같이 풀린다

3페이지 하이라이트 장식은 실측 y 0.222~0.370이다.

```
장식      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓  0.222 ─ 0.370
bullets(vision)      ░░░░░░░░░  0.350 ─ 0.650   ← 0.020 (0.15in) 겹침
bullets(실측)             ░░░░░  0.435 ─ 0.603   ← 겹침 없음
```

원본 문서는 애초에 겹치지 않았으므로, 실측으로 스냅하면 겹침이 **부수 효과로 해소**된다. 별도 충돌 회피 로직이 필요 없다.

### 1.3 Related Documents

- 사용자 지적 원본: 결함 B (`docs/04-report/blueprint-font-mapping-migration.report.md` §4.2)
- 선행 사이클: `pptx-font-fidelity`, `blueprint-font-mapping-migration`
- 원 설계: `docs/architecture/golden-sample-blueprint.md`
- 코딩 규칙: `idt/CLAUDE.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 텍스트 슬롯(`title` / `text` / `bullets`) 좌표를 실측 span union으로 스냅
- [ ] 슬롯↔span 매칭 규칙 확정 (vision 박스 기준 배정, 중복 후보 처리)
- [ ] 높이 확장 정책 — x·y·w는 실측, h는 다음 경계까지 확장
- [ ] 푸터·페이지번호 span을 스냅 입력에서 배제 (DR-2: 스타일 값으로만 렌더)
- [ ] 매칭 span 0건일 때의 폴백
- [ ] 골든 샘플 기준 회귀 테스트 (오차 측정 + 겹침 0건 검증)

### 2.2 Out of Scope

- **표·차트·이미지 슬롯** — `find_tables`가 카드 박스를 표로 오탐한다는 기존 주석(`policies.py:445`)이 있어 근거 데이터 신뢰도가 낮다. 별도 판단 필요.
- **기존 저장 블루프린트 마이그레이션** — 실측 span은 추출 시점에만 존재하므로 로드 경계 정규화(사이클 A 방식)가 **기술적으로 불가능**하다. 기존 블루프린트는 재추출해야 혜택을 받는다. §5 리스크 참조.
- **텍스트박스 내부 여백(inset) 보정** — python-pptx 기본 inset으로 글자가 안쪽으로 밀리는 미세 오차. Design에서 다룰지 판단.
- **결함 C (목차·카드 내용 폴백)** — 별도 사이클
- **결함 D (차트 레이블·단위, 표 테두리, 문단 여백)** — 별도 사이클
- 비전 프롬프트 변경 — 모델에게 정확한 좌표를 요구하는 방향은 채택하지 않는다(비결정적)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 텍스트 슬롯의 `x`·`y`·`w`를 그 슬롯에 배정된 실측 span의 union bbox로 대체한다 | High | Pending |
| FR-02 | span 배정은 vision 박스를 기준으로 한다. 한 span이 여러 슬롯 후보에 걸리면 결정론적 규칙으로 하나에 배정한다 | High | Pending |
| FR-03 | 높이 `h`는 실측값이 아니라 **아래쪽 경계까지 확장**한다 — 생성물이 샘플보다 길어도 잘리지 않게 | High | Pending |
| FR-04 | 푸터·페이지번호에 해당하는 span은 스냅 입력에서 제외한다 (DR-2와 이중 렌더 방지) | High | Pending |
| FR-05 | 매칭 span이 0건이면 vision 좌표를 그대로 유지하고 경고를 남긴다 | Medium | Pending |
| FR-06 | 스냅 결과는 슬라이드 경계(0..1) 안에 있어야 한다 — 기존 `_clamped_box` 불변식 유지 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 스냅 정책은 도메인 순수 함수. domain → infrastructure 참조 없음 | `test_layer_contract.py` |
| 결정론 | 같은 입력 → 같은 출력. LLM 재호출 없음 | 도메인 단위 테스트 |
| 성능 | 페이지당 span 수는 수십 건 — 슬롯×span 이중 루프로 충분 | 추출 시간 유의미한 증가 없음 |
| 하위호환 | v1·v2 스키마 로드에 영향 없음 (좌표 형식 무변경) | 기존 직렬화 테스트 |
| 회귀 | blueprint 관련 기존 테스트 전부 통과 | `pytest tests/*/blueprint` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1 — 골든 샘플을 추출·렌더한 PPTX의 **텍스트 도형 위치가 원본 PDF의 같은 역할 텍스트와 0.1in 이내**
  > v0.2 정정: 최초 문구 "슬롯 좌표 오차 0.1in 이하"는 스냅 결과를 실측 union과 비교하는 **동어반복**이었다. 설계 §14 참조.
- [ ] SC-2 — 슬롯이 장식 하나에 대응하는 패턴에서 **부분 겹침 0건** (신고된 3페이지 겹침 해소 포함)
  > v0.3 정정: 최초 문구 "겹침 0건"은 p6(카드 3장)를 예상하지 못했다. 비전 모델이 카드 3개를 `bullets` 슬롯 **하나**로 준 구조 문제라 좌표 스냅으로 풀 수 없다 — **결함 C(슬롯 분할)로 이월**. 실측: 6개 패턴 중 5개 겹침 0건, p6만 3건.
- [ ] SC-3 — 표지 제목 x 오차 1.83in → 0.1in 이하
- [ ] SC-4 — 매칭 span 0건 슬롯에서 vision 좌표가 보존되고 경고가 남는다
- [ ] SC-5 — 푸터 span이 어떤 텍스트 슬롯에도 배정되지 않는다
- [ ] SC-6 — 설계 §Test Plan의 **모든 시나리오**에 대응하는 자동화 테스트가 존재한다
- [ ] SC-7 — blueprint 관련 기존 테스트 회귀 0건

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하 / if 중첩 2단계 이하
- [ ] `print()` 없음, 명시적 타입, config 하드코딩 없음
- [ ] ruff lint 0건 (**변경한 파일에만** 실행)
- [ ] 신규·변경 코드 커버리지 95% 이상

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **샘플 1건 과적합** — 골든 샘플에만 맞고 다른 문서에서 나빠진다 | High | Medium | ~~`samples/`의 다른 PPTX 2건으로 교차 확인~~ → **불가능(설계 §13.1)**: 해당 3건은 우리 생성물이고 PPTX 경로는 `render_png=None`이라 비전을 타지 않는다. **리스크 미완화 상태로 남는다.** 확보한 것: 골든 6페이지가 5종 패턴 커버, 규칙을 일반 기하로만 정의(DR-2·4·5), 폴백 안전망(DR-9). 실사용 문서 1~2건 확보 후 교차 확인 권장 |
| **span 배정 모호** — vision 박스가 겹치거나 span이 경계에 걸린다 | Medium | Medium | 중심점 포함 기준 + 동점 시 결정론적 타이브레이크. 규칙을 테스트로 고정 |
| **기존 저장 블루프린트에 미적용** — 사이클 A와 같은 상황 | Medium | **확실** | 기술적으로 불가피(실측 span이 추출 시점에만 존재). **수용하되 명시한다** — 사용자에게 "기존 블루프린트는 재추출 필요"를 보고서에 못박는다. 사이클 A의 교훈을 이번엔 미리 인지한 상태로 진행 |
| **높이 확장의 아래쪽 경계 판정** — 다음 슬롯도, 장식도, 푸터도 후보 | Medium | High | Design에서 우선순위를 명시하고 테스트로 고정. 후보가 없으면 vision 높이 유지 |
| **텍스트박스 inset 미보정** — 스냅해도 글자가 0.05in 안쪽으로 밀린다 | Low | High | 이번 범위 밖. 오차가 SC-1 기준(0.1in) 안이면 수용. 초과하면 Design에서 재검토 |
| **DecorationPolicy 결합** — 슬롯 박스가 바뀌면 장식 판정도 바뀐다 | High | **없음 (확인됨)** | `_CONTENT_SLOT_KINDS = (CHART, IMAGE, TABLE)` — 텍스트 슬롯은 장식 판정 입력이 아니다(`policies.py:428,479`). 텍스트만 스냅하는 이번 범위는 이 결합에서 **구조적으로 격리**된다 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 슬롯 좌표 생성 (`_pattern_from_draft` 또는 후속 단계) | Application | 비전 좌표 → 실측 스냅 좌표 |
| 신규 스냅 정책 | Domain Policy | `PageStats` + `PagePattern` → 좌표 보정된 `PagePattern` |
| `blueprint_json`의 slot box 값 | DB 데이터 | 스키마 무변경. **신규 추출분만** 반영 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `Slot.box` | READ | `pptx_renderer._render_slot` → `ctx.emu(slot.box)` | **주 수혜자** — 정확한 좌표 수신 |
| `Slot.box` | READ | `DecorationPolicy._eligible` (`policies.py:479`) | **영향 없음** — CHART/IMAGE/TABLE만 참조, 텍스트 슬롯 아님 ✅ 확인 완료 |
| `Slot.box` | READ | `renderer._with_title_fallback` | 영향 없음 (좌표 무관) |
| `Slot.box` | READ/WRITE | `interfaces/schemas/blueprint.py` `SlotSchema.box` | 값만 변경, 스키마 무변경 → **프론트 타입 동기화 불필요** |
| `Slot.box` | WRITE | `_heuristic_pattern` (PPTX 경로) | **Needs verification** — PPTX는 렌더 이미지가 없어 휴리스틱을 쓴다. 스냅 적용 여부 판단 필요 |
| `_clamped_box` | 호출 | `extraction_use_case.py:356` | 불변식 유지 필요 (FR-06) |
| `PageStats.spans` | READ | 현재 `SizeHierarchyPolicy`·`PaletteClusterPolicy`·`FooterPolicy` | 읽기만 추가 — 기존 소비자 영향 없음 |
| 골든 샘플 통합 테스트 | TEST | `tests/integration/blueprint/test_golden_sample_fidelity.py` | **기대값 갱신 필요** — 좌표 단언이 있으면 변경 |
| v1 스냅샷 픽스처 | TEST | `tests/fixtures/blueprint/golden_v1.json` | **영향 없음** — 저장된 좌표를 그대로 쓰는 회귀 기준선. 수정 금지 |

### 6.3 Verification

- [ ] 위 모든 소비자가 스냅된 좌표로 정상 동작함을 확인
- [x] PPTX 휴리스틱 경로 — **분기 불필요, 균일 적용로 확정** (설계 §13.3 / DR-8)
- [ ] 골든 샘플 통합 테스트의 좌표 관련 단언 목록 작성 후 갱신
- [ ] API 응답 스키마 무변경 확인 → 프론트 동기화 불필요

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
| 스냅 대상 | 텍스트만 / +이미지 / 전체 | **텍스트 슬롯만** | 오차가 가장 크고 근거 데이터가 가장 확실. `DecorationPolicy` 결합에서도 격리됨 (Checkpoint 2) |
| 높이 처리 | 실측 그대로 / **확장** / vision 유지 | **위치·폭만 스냅, 높이 확장** | 생성물이 샘플보다 길어도 잘리지 않는다 (Checkpoint 2) |
| 적용 시점 | **추출만** / 추출+안내 | **추출 시점만** | 실측 span이 추출 때만 존재 — 기술적으로 유일한 지점 (Checkpoint 2) |
| 정책 배치 레이어 | domain policy / application 헬퍼 | **domain `policies.py`** | `DecorationPolicy`와 입출력 모양 동일, 기하 헬퍼 재사용 (설계 DR-1) |
| 아래쪽 경계 우선순위 | 다음 슬롯 / 장식 / 푸터 | **세 후보의 최솟값 + 장식 캡** | 종류 무관 최근접 경계. 텍스트 아닌 슬롯 누락 시 표 영역을 삼킨다 (설계 DR-4·DR-5) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

영향 레이어:
┌──────────────────────────────────────────────────────────┐
│ domain/blueprint/                                        │
│   value_objects.py   PageStats.spans (입력, 무변경)       │
│   policies.py        ← 스냅 정책 후보 위치                 │
│                       (DecorationPolicy·FooterPolicy 동형)│
├──────────────────────────────────────────────────────────┤
│ application/blueprint/                                   │
│   extraction_use_case.py  _pattern_from_draft /           │
│                           _style_and_patterns 결선        │
└──────────────────────────────────────────────────────────┘

infrastructure·interfaces 변경 없음 — 좌표 형식이 그대로다.
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 (루트 + `idt/`)
- [x] `docs/rules/` 세부 규칙
- [x] ruff / pytest 설정
- [x] 도메인 순수성 AST 계약 테스트 (`test_layer_contract.py`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 기하 계산 헬퍼 | `_containment` 등 일부 존재 | 스냅용 union/포함 판정 재사용 여부 | Medium |
| 경고 메시지 형식 | exists (`warnings` 튜플) | 스냅 실패 경고 문구 | Low |
| 린트 실행 범위 | Plan에서 명문화됨 | **변경 파일에만 ruff** 유지 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | To Be Created |
|----------|---------|:-------------:|
| — | 신규 환경변수 없음 | ☐ |

### 8.4 Pipeline Integration

해당 없음.

---

## 9. Next Steps

1. [ ] 설계 문서 작성 (`/pdca design blueprint-slot-box-snap`) — 정책 배치·경계 우선순위 3안 비교
2. [ ] `samples/`의 다른 PPTX 2건으로 과적합 사전 확인 (§5 최상단 리스크)
3. [ ] TDD 구현 (Red → Green → Refactor)
4. [ ] Gap 분석 (`/pdca analyze`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — 결함 B 대응, 골든 샘플 13슬롯 오차 실측 포함 | 배상규 |
| 0.2 | 2026-08-25 | Design 실측 반영 — SC-1 동어반복 정정, 과적합 완화 실패 명시, 미정 3건 확정 | 배상규 |
| 0.3 | 2026-08-25 | Do 실측 반영 — SC-2 범위 조정(p6 카드 패턴은 결함 C 이월) | 배상규 |
