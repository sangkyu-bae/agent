# blueprint-slot-content-fill Design Document

> **Summary**: 장식 경계로 카드 슬롯을 쪼개고, 목차를 계획 제목에서 결정론적으로 만들고, 길이 초과를 폐기 대신 경고로 낮춘다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-26
> **Status**: Draft
> **Planning Doc**: [blueprint-slot-content-fill.plan.md](../../01-plan/features/blueprint-slot-content-fill.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 좌표와 폰트를 고쳤어도 목차·카드가 비어 있으면 산출물로 쓸 수 없다 |
| **WHO** | P2 — 골든 샘플로 자사 문서를 재현해 실제 보고서를 만들려는 KB 운영자 |
| **RISK** | 슬롯 분할이 슬롯 id를 바꿔 writer 프롬프트·정책·렌더러에 연쇄 파급 |
| **SUCCESS** | 목차에 4개 항목이 채워지고, 카드 3장 모두 소제목+본문을 갖는다 |
| **SCOPE** | 슬롯 분할(추출) + 목차 결정론(생성) + 길이 초과 폴백(정책) |

---

## 1. Overview

### 1.1 Design Goals

1. **비전 모델이 뭉친 것을 실측 기하로 되돌린다** — 장식 경계는 이미 확정돼 있다.
2. **LLM에 맡길 이유가 없는 것은 맡기지 않는다** — 목차는 계획 단계에 이미 답이 있다.
3. **`max_chars` 추정값 하나로 슬라이드가 비지 않게 한다** — 모양 위반과 길이 초과를 구분한다.
4. **렌더러를 건드리지 않는다** — 기존 `SlotContent.heading`(pptx-font-fidelity FR-03)을 재사용한다.
5. 실패는 원본 유지 + 경고. 분할·목차 모두 개선 시도이지 필수 경로가 아니다.

### 1.2 Design Principles

- **기존 기계 재사용**: 결함 B가 만든 `_snappable_spans` / `_assign` / `_union`을 그대로 쓴다. 새 배정 규칙을 만들지 않는다.
- **좁은 분할 조건**: "서로 다른 장식에 **완전히 포함**"만 분할한다. 애매하면 유지.
- **치명과 권고의 분리**: 모양 불일치(text 자리에 bullets)는 폐기, 길이 초과는 경고.
- **결정론**: 분할·목차 모두 LLM 재호출 없음.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|----------|:-:|:-:|:-:|
| **분할 배치** | `SlotBoxPolicy`에 흡수 | 신규 모듈 + 배정 헬퍼 추출 | `policies.py`에 `SlotSplitPolicy` |
| **카드 표현** | BULLETS + heading | TITLE+TEXT 슬롯 쌍 | BULLETS + heading |
| **목차 배치** | `generation_use_case` 함수 | 신규 도메인 모듈 | `policies.py`에 `TocContentPolicy` |
| **C-3 방식** | `_check_*` 반환 플래그 | `ContentOutcome` 필드 추가 | `_violation` fatal/advisory 분리 |
| **New Files** | 0 | 2 | 0 |
| **Modified Files** | 3 | 4 | 4 |
| **렌더러 변경** | 없음 | **필요** | 없음 |
| **단일 책임** | ❌ | ✅ | ✅ |
| **Complexity** | Low | High | Medium |
| **Recommendation** | — | 카드 구조 확장 계획 시 | **기본 권장** |

**Selected**: **Option C — Pragmatic** (Checkpoint 3)

**Rationale**: `SlotContent.heading`을 재사용하면 **렌더러 변경이 0**이다. 분할·목차 정책이 각각 `SlotSplitPolicy`·`TocContentPolicy`로 단일 책임을 갖고, 직전 사이클의 `SlotBoxPolicy` 의미를 흐리지 않는다. B의 슬롯 쌍 표현은 구조적으로 정확하나 렌더러에 "슬롯 쌍을 카드로 묶는" 새 개념을 도입해야 하고, 배정 헬퍼 이관이 방금 만든 `SlotBoxPolicy`를 흔든다.

### 2.1 Component Diagram

```
┌──────────────── domain/blueprint/policies.py ────────────────┐
│                                                              │
│  ┌─ 추출 경로 ──────────────────────────────────────────┐    │
│  │  DecorationPolicy      장식 확정 (기존)               │    │
│  │           ↓                                          │    │
│  │  SlotSplitPolicy       장식 그룹 → 슬롯 N개  [신규]   │    │
│  │           ↓                                          │    │
│  │  SlotBoxPolicy         각 슬롯 좌표 스냅 (결함 B)      │    │
│  │                                                      │    │
│  │  공유 헬퍼: _snappable_spans / _assign / _union       │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─ 생성 경로 ──────────────────────────────────────────┐    │
│  │  TocContentPolicy      계획 제목 → 목차 bullets [신규] │    │
│  │  SlotContentPolicy     치명/권고 분리          [변경]  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
          ▲                                    ▲
          │ 결선                                │ 결선
┌─────────┴──────────────┐        ┌────────────┴─────────────┐
│ extraction_use_case.py │        │ generation_use_case.py   │
│  _style_and_patterns   │        │  _write_all / _write_one │
└────────────────────────┘        └──────────────────────────┘

renderer/pptx_renderer.py — 변경 없음 (heading 렌더는 FR-03 에서 이미 구현)
```

### 2.2 Data Flow

**C-1 분할 (추출)**

```
비전 슬롯 1개 (bullets)
  + 실측 span 6개
  + 실측 장식 3개
      ↓ SlotSplitPolicy
슬롯 3개 (bullets, bullets2, bullets3) — 각각 장식 하나에 대응
      ↓ SlotBoxPolicy
각 슬롯이 자기 장식 안으로 스냅 + 높이 확장 (장식 하단 캡)
      ↓
blueprint_json
```

**C-2 목차 (생성)**

```
_plan() → SlidePlan 목록 (제목 확정)
      ↓
toc 패턴 슬라이드?  ──아니오──▶ writer.write() (기존)
      │ 예
      ▼
TocContentPolicy.apply(plan, all_plans, pattern)
      ↓ LLM 미경유
SlideContent(title=plan.title, bullets=다른 슬라이드 제목들)
```

**C-3 길이 초과 (정책)**

```
                    기존                        변경
모양 불일치    →  경고 + 폐기              →  경고 + 폐기 (동일)
길이 초과      →  경고 + 폐기              →  경고 + **유지**
```

### 2.3 실행 순서

| 단계 | 정책 | 입력 | 이번 변경 |
|:----:|------|------|:--------:|
| 1 | `DecorationPolicy` | `_CONTENT_SLOT_KINDS`(CHART/IMAGE/TABLE)만 참조 | 영향 없음 — 텍스트 슬롯을 보지 않는다 |
| 2 | **`SlotSplitPolicy`** | 텍스트 슬롯 + span + 장식 | **신규** |
| 3 | `SlotBoxPolicy` | 분할된 슬롯 + span + 장식 | 입력이 늘어날 뿐 로직 무변경 |

**분할이 스냅보다 먼저인 이유**: 분할은 원본 비전 박스로 span을 배정해야 하고(쪼개기 전 상태), 스냅은 쪼갠 각 슬롯을 개별로 맞춰야 한다. 순서를 뒤집으면 뭉친 슬롯 하나가 세 카드를 가로지르는 박스로 스냅돼 분할 근거가 사라진다.

**멱등성**: 분할된 슬롯을 다시 `SlotSplitPolicy`에 넣으면 각 슬롯의 span이 장식 1개에만 속하므로 분할되지 않는다. 반복 적용이 안전하다.

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `SlotSplitPolicy` | `_snappable_spans` / `_assign` / `_union` (기존) | 배정·union 재사용 |
| `SlotSplitPolicy` | `Decoration`, `PagePattern`, `Slot` | 입력 |
| `TocContentPolicy` | `SlidePlan`, `PagePattern`, `SlotContent` | 입력·출력 |
| `SlotContentPolicy` | `_check_*` (변경) | 치명/권고 분리 |
| `pptx_renderer` | **변경 없음** | `heading` 렌더는 이미 존재 |

---

## 3. Data Model

### 3.1 Entity Definition

**신규 엔티티 없음.** 기존 구조만 쓴다.

```python
@dataclass(frozen=True)
class Slot:            # 분할로 개수가 늘어날 뿐, 구조 무변경
    id: str            # bullets → bullets, bullets2, bullets3
    ...

@dataclass(frozen=True)
class SlotContent:
    heading: str | None = None   # ← 카드 소제목 (pptx-font-fidelity FR-03, 재사용)
    bullets: tuple[str, ...] | None = None
    ...
```

### 3.2 알고리즘 명세

#### C-1 분할 (FR-01·FR-02·FR-06)

```
대상: 텍스트 슬롯(title/text/bullets)
1. spans  = _snappable_spans(page, caption)          # 푸터 배제 (기존)
2. 배정    = _assign(spans, 텍스트 슬롯들)             # 중심점 포함 (기존)
3. 각 슬롯에 대해:
     그룹 = {}                    # 장식 id → span 목록
     미소속 = 0
     for span in 배정[slot]:
         owner = span 을 **완전히 포함**하는 장식 (첫 번째)
         owner 없음 → 미소속 += 1
         있음      → 그룹[owner].append(span)
     분할 조건: len(그룹) >= 2 AND 미소속 == 0
     아니면 원본 유지 (FR-06)
4. 분할 시: 그룹을 y 오름차순 정렬 → 슬롯 N개 생성
     id   = 기존 suffix 규칙 (bullets, bullets2, bullets3)
     kind/role/align/max_chars = 원본 승계
     box  = _union(그룹 span)
```

**장식 선택이 첫 번째인 이유**: 골든에서 액센트 바(폭 0.008)는 span을 포함하지 못해 자연히 걸러진다. 여러 장식이 동시에 포함하는 경우(중첩 장식)는 패턴 내 등장 순서로 결정론을 확보한다.

#### C-1 소제목/본문 구분 (FR-03)

카드 내부는 **BULLETS 슬롯 + `heading`**으로 표현한다. writer가 채우고, 렌더러 `_bullets`가 heading 문단을 앞에 그린다(FR-03에서 구현 완료).

골든 카드는 15pt Bold(소제목) + 13pt(본문) 2줄이며, 렌더는 `h3` 크기·primary 색·bold로 그려진다.

> 슬롯 `role`에 원본 소제목 텍스트를 힌트로 남길지는 §12 DR-4 참조.

#### C-2 목차 (FR-04)

```
대상: pattern.kind is TOC 인 슬라이드
항목 = [p.title for p in 계획 목록
        if p 의 패턴 kind 가 COVER 도 TOC 도 아니고
           p.title.strip() 이 비어 있지 않음]
상한 = _TOC_MAX_ITEMS (12)
  초과 시: 앞에서부터 상한만큼 채우고 경고 1건
번호: 렌더러가 "1. " 를 붙인다 (기존 _bullets TOC 분기) → 항목에 번호를 넣지 않는다
결과: SlideContent(plan, (SlotContent(title슬롯, plan.title), SlotContent(bullets슬롯, bullets)), warnings)
빈 항목 목록 → 폴백: 기존 writer 경로 사용
```

**자기 자신·표지 제외**: 골든 목차가 3~6페이지만 담는다(표지 p1, 목차 자신 p2 제외).

**번호 중복 방지**: 렌더러 `_bullets`의 TOC 분기가 이미 `f"{i}. {b}"`를 붙인다. 정책이 번호를 넣으면 `1. 1. 요약`이 된다.

#### C-3 치명/권고 분리 (FR-05)

```python
# 기존
_violation(c, slot) -> str | None        # 반환되면 폐기

# 변경
_violation(c, slot) -> str | None        # 모양 불일치만 — 폐기 유지
_advisory(c, slot)  -> str | None        # 길이 초과 — 경고만, kept 에 포함
```

| 검사 | 분류 | 처리 |
|------|:----:|------|
| `text` 자리에 bullets가 옴 | 치명 | 경고 + 폐기 |
| `bullets` 자리에 text가 옴 | 치명 | 경고 + 폐기 |
| `table`/`chart` 내용 없음 | 치명 | 경고 + 폐기 |
| 슬롯이 패턴에 없음 | 치명 | 경고 + 폐기 |
| `max_chars` 초과 | **권고** | 경고 + **유지** |
| `max_rows` 초과 | **치명 유지** | 표 행 초과는 렌더 시 실제 깨짐 — 현행 유지 |

> `max_rows`를 권고로 낮추지 않는 이유: 표는 `add_table(len(rows)+1, ...)`로 행 수만큼 실제 도형을 만들어 슬롯 밖으로 넘친다. 문자 수 초과와 성질이 다르다.

### 3.3 Database Schema

**변경 없음.** DDL·마이그레이션 추가 없음. `blueprint_json`의 `slots` 배열 **길이**만 신규 추출분에서 늘 수 있다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 계약 변경 |
|--------|------|:--------:|
| POST | `/admin/blueprints/extract` | **없음** (`slots` 배열 길이만 변동) |
| GET | `/admin/blueprints/{id}` | **없음** |
| PUT | `/admin/blueprints/{id}` | **없음** |

**응답 스키마 무변경 → 프론트엔드 타입 동기화 불필요.**

### 4.2 관찰 가능한 동작 변화

```diff
  "patterns": [{ "id": "p6", "slots": [
      { "id": "title",   "kind": "title" },
-     { "id": "bullets", "kind": "bullets", "box": {"y": 0.266, "h": 0.614} }
+     { "id": "bullets",  "kind": "bullets", "box": {"y": 0.266, "h": 0.141} },
+     { "id": "bullets2", "kind": "bullets", "box": {"y": 0.470, "h": 0.141} },
+     { "id": "bullets3", "kind": "bullets", "box": {"y": 0.673, "h": 0.142} },
      { "id": "footer",  "kind": "footer" }
  ]}]
```

생성 측에서는 목차 슬라이드의 **writer LLM 호출이 사라진다**(비용·지연 감소).

---

## 5. UI/UX Design

해당 없음 — 백엔드 전용. 관리 UI의 슬롯 목록에 분할된 슬롯이 나타나는 부수 효과만 있다.

---

## 6. Error Handling

### 6.1 오류 정책

세 정책 모두 **예외를 던지지 않는다.**

| 상황 | 처리 | 경고 |
|------|------|:----:|
| 장식 그룹 1개 이하 | 원본 슬롯 유지 (FR-06) | ✕ (정상) |
| 미소속 span 존재 | 원본 슬롯 유지 | ✕ (정상) |
| 페이지에 장식 없음 | 패턴 무변경 | ✕ |
| 목차 항목 0개 | writer 경로로 폴백 | ✅ |
| 목차 항목 상한 초과 | 앞에서부터 채움 | ✅ |
| 목차 패턴에 bullets 슬롯 없음 | writer 경로로 폴백 | ✅ |
| `max_chars` 초과 | 내용 유지 | ✅ (권고) |

### 6.2 로깅

정책 자체는 로깅하지 않는다(도메인 순수). 경고는 `blueprint.warnings` / `PresentationResult.warnings`로 누적되어 기존 경로로 노출된다.

---

## 7. Security Considerations

- [x] 입력 검증 — 좌표·문자열 모두 기존 검증(`SlotDraft` pydantic, `RelBox`)을 통과한 값
- [x] 신뢰 경계 — **LLM 의존이 줄어든다**: 목차가 결정론 경로로 바뀌고 분할이 실측 기하로 결정된다
- [x] 주입 — 목차 항목은 계획 단계의 `SlidePlan.title`이며 렌더러가 데이터로만 그린다(기존 §7 주입 방어 유지)
- [x] 자원 소모 — 슬롯×span×장식 삼중 루프. 페이지당 수십 건 규모

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| **L1: Domain Unit** | `SlotSplitPolicy` / `TocContentPolicy` / `SlotContentPolicy` | pytest | Do |
| **L2: Application Integration** | 추출·생성 결선, 실행 순서 | pytest | Do |
| **L3: Golden Regression** | 실제 PDF → 분할 결과·겹침 | pytest | Do |
| **L4: Render E2E** | 생성물의 목차·카드 내용 | pytest + python-pptx | Do |

### 8.2 L1: Domain Unit 시나리오

#### SlotSplitPolicy

| # | 시나리오 | 기대 |
|---|----------|------|
| 1 | span이 장식 3개에 나뉘고 미소속 0 | 슬롯 3개로 분할 |
| 2 | 분할 슬롯 id | `bullets`, `bullets2`, `bullets3` (기존 suffix 규칙) |
| 3 | 분할 슬롯 속성 | kind·role·align·max_chars 원본 승계 |
| 4 | 분할 슬롯 순서·box | y 오름차순, 각 box = 그룹 union |
| 5 | 장식 그룹 1개 | **분할 안 함** (FR-06) |
| 6 | 미소속 span 1개 이상 | **분할 안 함** (FR-06) |
| 7 | 장식 없음 | 패턴 무변경 |
| 8 | 텍스트 아닌 슬롯(table/chart/image/footer) | **무변경** |
| 9 | 액센트 바처럼 좁은 장식 | span을 포함하지 못해 그룹에서 제외 |
| 10 | 중첩 장식이 같은 span을 포함 | 패턴 내 등장 순서로 결정론 |
| 11 | 멱등 | 분할 결과를 재적용해도 동일 |
| 12 | 푸터 밴드 span | 배정 대상에서 제외 (기존 `_snappable_spans`) |

#### TocContentPolicy

| # | 시나리오 | 기대 |
|---|----------|------|
| 13 | 계획 5장(표지·목차·본문 3) | 항목 3개 — 표지·목차 자신 제외 |
| 14 | 항목 순서 | 계획 순서 유지 |
| 15 | 번호 | 항목에 번호 **미포함** (렌더러가 붙임) |
| 16 | 제목이 빈 슬라이드 | 항목에서 제외 |
| 17 | 상한 초과 (13장) | 앞 12개 + 경고 1건 |
| 18 | 항목 0개 | `None` 반환 → writer 폴백 |
| 19 | bullets 슬롯 없는 toc 패턴 | `None` 반환 → writer 폴백 |
| 20 | title 슬롯 | `plan.title`로 채움 |

#### SlotContentPolicy (C-3)

| # | 시나리오 | 기대 |
|---|----------|------|
| 21 | `max_chars` 초과 bullets | **kept 에 포함** + 경고 1건 |
| 22 | `max_chars` 초과 text | **kept 에 포함** + 경고 1건 |
| 23 | text 자리에 bullets | 폐기 + 경고 (치명, 기존 유지) |
| 24 | bullets 자리에 text | 폐기 + 경고 (치명, 기존 유지) |
| 25 | `max_rows` 초과 표 | **폐기 유지** (치명) |
| 26 | 패턴에 없는 슬롯 id | 폐기 + 경고 (기존 유지) |
| 27 | 정상 내용 | kept, 경고 0건 |

### 8.3 L2: Application Integration 시나리오

| # | 시나리오 | 기대 |
|---|----------|------|
| 28 | `_style_and_patterns` | 분할 → 스냅 순서로 실행 |
| 29 | 분할 후 스냅 | 각 분할 슬롯이 자기 장식 안에 완전히 포함 |
| 30 | 장식 판정 불변 | 분할 전후 `DecorationPolicy` 출력 동일 |
| 31 | toc 슬라이드 생성 | **writer 호출 0회** (SC-6) |
| 32 | 비-toc 슬라이드 | writer 호출 유지 |
| 33 | 목차 폴백 | 항목 0개면 writer 호출 발생 |

> **v0.3 정정**: 최초 초안의 시나리오 31 "분할 경고 전파"를 삭제했다. §6.1이 분할 실패 3가지 상황 모두에 경고를 두지 않아 `SlotSplitPolicy`가 경고를 생성하지 않으므로, 검증할 대상이 없는 **문서 내부 모순**이었다. 결선부는 `split_warnings`를 전파하도록 되어 있어 향후 경고가 추가되면 그대로 동작한다.

### 8.4 L3: Golden Regression 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 35 | **SC-3** — p6 슬롯 분할 | 텍스트 슬롯이 title + bullets×3 = 4개 |
| 36 | **SC-4** — p6 겹침 | 부분 겹침 **0건** (기존 3건에서) |
| 37 | 전 패턴 겹침 | 6/6 패턴 부분 겹침 0건 — 결함 B의 `multi_card` 예외 제거 |
| 38 | 과분할 없음 | p1~p5 텍스트 슬롯 개수 변화 0 |
| 39 | 각 분할 슬롯 ↔ 장식 | 1:1 완전 포함 |

### 8.5 L4: Render E2E 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 40 | **SC-1** — 목차 렌더 | 목차 슬라이드에 4개 항목, 각 항목이 다른 슬라이드 제목과 일치 |
| 41 | 목차 번호 | `1. `~`4. ` 한 번씩만 (중복 `1. 1.` 없음) |
| 42 | **SC-2** — 카드 렌더 | 카드 3장 모두 텍스트 도형 보유 (빈 카드 0개) |
| 43 | **SC-5** — 길이 초과 | `max_chars` 초과 내용이 렌더에 살아남음 + 경고 존재 |

### 8.6 기존 테스트 교체 (SC-4)

| 테스트 | 조치 |
|--------|------|
| `test_known_limitation_multi_card_pattern_still_overlaps` | **삭제** — 겹침 3건 고정이 목적이었고 이제 0건 |
| `test_sc2_single_card_patterns_have_no_partial_overlap` | `multi_card` 예외 제거 → 전 패턴 검사 (시나리오 37) |

> 결함 B 설계가 "해소되면 이 테스트가 실패해 이월 항목을 정리하게 된다"고 의도한 대로다. **Do 단계에서 실패를 먼저 확인한 뒤 교체한다.**

### 8.7 Seed Data Requirements

| 픽스처 | 출처 | 수정 |
|--------|------|:----:|
| `samples/golden_sample_report.pdf` | 기존 | 금지 |
| `tests/fixtures/blueprint/golden_v1.json` | 기존 | **금지** — 저장된 패턴을 쓰는 v1 회귀 기준선, 이번 변경 영향 없음 |
| L1 단위 테스트용 VO | 신규 | 테스트 내 팩토리 (결함 B `test_slot_box_policy.py` 패턴 재사용) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 분할·목차·검증 규칙 (순수) | `src/domain/blueprint/policies.py` |
| **Application** | 정책 실행 순서·결선 | `extraction_use_case.py`, `generation_use_case.py` |
| **Infrastructure** | 변경 없음 | — |
| **Interfaces** | 변경 없음 | — |

### 9.2 Dependency Rules

```
Application ──▶ Domain ◀── Infrastructure

신규 정책은 policies.py 내부 헬퍼와 value_objects 만 참조한다.
test_layer_contract.py 의 금지 임포트 검사를 통과한다.
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 상태 |
|-----------|-------|----------|:----:|
| `SlotSplitPolicy` + 헬퍼 | Domain | `policies.py` | 신규 |
| `TocContentPolicy` | Domain | `policies.py` | 신규 |
| `SlotContentPolicy._advisory` | Domain | `policies.py` | 수정 |
| 분할 결선 | Application | `extraction_use_case.py` | 수정 |
| 목차 결선 | Application | `generation_use_case.py` | 수정 |

---

## 10. Coding Convention Reference

| Item | Convention |
|------|-----------|
| 함수 길이 | 40줄 이하 — `SlotSplitPolicy.apply`는 그룹화/생성 헬퍼로 분할 |
| if 중첩 | 2단계 이하 |
| 타이핑 | 명시적 (`Sequence[SlidePlan]`, `tuple[PagePattern, ...]`) |
| 하드코딩 | `_TOC_MAX_ITEMS`·`_SPLIT_MIN_GROUPS` 모듈 상수 |
| 로깅 | 정책 내 로깅 없음 |
| `print()` | 금지 |
| 주석 | `# Design Ref: blueprint-slot-content-fill §{절}` / `# Plan SC-{n}` |
| 린트 | **변경한 파일에만** `ruff check` |

### 10.2 명명

| 대상 | 규칙 | 예시 |
|------|------|------|
| 정책 클래스 | PascalCase + `Policy` | `SlotSplitPolicy`, `TocContentPolicy` |
| 내부 헬퍼 | `_` 접두 | `_decoration_groups`, `_split_slots`, `_toc_items` |
| 상수 | `_UPPER_SNAKE` | `_TOC_MAX_ITEMS`, `_SPLIT_MIN_GROUPS` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/blueprint/policies.py            [수정] SlotSplitPolicy + TocContentPolicy
│                                                  + _advisory 분리 (~140줄)
└── application/blueprint/
    ├── extraction_use_case.py              [수정] 분할 결선 (~15줄)
    └── generation_use_case.py              [수정] 목차 결선 (~20줄)

tests/
├── domain/blueprint/
│   ├── test_slot_split_policy.py           [신규] 시나리오 1~12
│   ├── test_toc_content_policy.py          [신규] 시나리오 13~20
│   └── test_policies.py                    [수정] 시나리오 21~27
├── application/blueprint/
│   ├── test_extraction_use_case.py         [수정] 시나리오 28~31
│   └── test_generation_use_case.py         [수정] 시나리오 32~34
└── integration/blueprint/
    └── test_golden_sample_fidelity.py      [수정] 시나리오 35~43 + §8.6 교체
```

**src 수정 3 (~175줄), 테스트 신규 2 / 수정 4 (~43 시나리오)**

### 11.2 Implementation Order

TDD — 각 단계 Red → Green → Refactor.

1. [ ] **C-3 치명/권고 분리** — 시나리오 21~27. 가장 독립적이고 다른 단계의 전제가 된다
2. [ ] **C-1 분할 정책** — 시나리오 1~12
3. [ ] **C-1 추출 결선** — 시나리오 28~31. `DecorationPolicy` → **분할** → `SlotBoxPolicy` 순서 고정
4. [ ] **C-2 목차 정책** — 시나리오 13~20
5. [ ] **C-2 생성 결선** — 시나리오 32~34
6. [ ] **골든 회귀** — 시나리오 35~39. **§8.6 기존 테스트 실패를 먼저 확인**한 뒤 교체
7. [ ] **렌더 E2E** — 시나리오 40~43
8. [ ] 변경 파일 `ruff check` + blueprint 전체 회귀

> **1번을 먼저 하는 이유**: 분할로 슬롯이 늘면 각 슬롯의 `max_chars`가 원본 승계값이라 초과가 더 잦아진다. C-3이 먼저 들어가 있어야 분할 검증이 길이 문제에 오염되지 않는다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 정책 (추출 측) | `module-1` | 구현 1~3 — C-3 + C-1 분할 + 추출 결선 | 30-35 |
| 정책 (생성 측) | `module-2` | 구현 4~5 — C-2 목차 + 생성 결선 | 20-25 |
| 검증 | `module-3` | 구현 6~8 — 골든 회귀, 렌더 E2E, 회귀 | 20-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2,module-3` | 55-70 |
| Session 3 | Check + Report | 전체 | 20-30 |

> 이전 두 사이클보다 범위가 넓다. 컨텍스트가 부족하면 `module-1`(추출) / `module-2+3`(생성·검증)로 끊는다.

---

## 12. Key Design Decisions (DR)

| ID | Decision | Rationale |
|----|----------|-----------|
| **DR-1** | 두 정책 모두 `policies.py`에 배치 | `DecorationPolicy`·`SlotBoxPolicy`와 동형. 기존 헬퍼 이관 없이 재사용 (Checkpoint 3) |
| **DR-2** | 카드 = **BULLETS 슬롯 + `heading`** | `pptx-font-fidelity` FR-03이 이미 렌더를 구현했다. **렌더러 변경 0** (Checkpoint 3) |
| **DR-3** | 분할 조건 = 장식 **완전 포함** + 미소속 0 | 시뮬레이션에서 과분할 0건 확인. 애매하면 유지가 안전하다 |
| **DR-4** | 분할 슬롯 id = 기존 suffix 규칙 | `_pattern_from_draft`와 동일 (`bullets`, `bullets2`, …). 새 규칙을 만들지 않아 연쇄 파급을 최소화 (Plan §5 최상단 리스크) |
| **DR-5** | 분할 → 스냅 순서 | 분할은 원본 비전 박스로 배정해야 하고, 스냅은 쪼갠 슬롯별로 맞춰야 한다 (§2.3) |
| **DR-6** | 목차 항목에 **번호를 넣지 않는다** | 렌더러 `_bullets` TOC 분기가 이미 `f"{i}. {b}"`를 붙인다. 넣으면 `1. 1. 요약`이 된다 |
| **DR-7** | 목차에서 **표지·목차 자신 제외** | 골든 목차가 3~6페이지만 담는다 |
| **DR-8** | 목차 상한 12 + 초과 시 경고 | 렌더 넘침 방지. 조용히 자르지 않는다 (Checkpoint 3) |
| **DR-9** | `max_chars`는 권고, **`max_rows`는 치명 유지** | 표는 행 수만큼 실제 도형을 만들어 슬롯 밖으로 넘친다 — 문자 수 초과와 성질이 다르다 |
| **DR-10** | 실패는 원본 유지 + 경고, 예외 없음 | 분할·목차 모두 개선 시도이지 필수 경로가 아니다 |

---

## 13. Verification Notes (설계 중 실측)

### 13.1 분할 규칙 시뮬레이션 — 과분할 0건

Plan §9 절차대로 규칙 초안을 골든 샘플에 돌렸다.

```
p1~p5 텍스트 슬롯 12개    → 전부 유지 (장식그룹 0~1개)
p6/bullets span 6개       → 분할 (장식그룹 3개, 미소속 0개)
   └ deco2: 크기[15.0, 13.0]  box=(0.094, 0.266, 0.452, 0.097)
   └ deco1: 크기[15.0, 13.0]  box=(0.094, 0.470, 0.381, 0.097)
   └ deco3: 크기[15.0, 13.0]  box=(0.094, 0.673, 0.376, 0.097)
```

- **의도한 슬롯 하나만 분할**됐다
- 각 그룹이 정확히 **소제목(15pt) + 본문(13pt)** 2개 span
- **액센트 바(폭 0.008)는 span을 포함하지 못해 자동 제외** — 별도 필터 불필요
- `p3/text`는 장식그룹 1개라 분할 안 함 — 조건이 제대로 좁혀졌다

### 13.2 `heading` 필드 재사용 가능 확인

`SlotContent.heading`은 `pptx-font-fidelity` FR-03에서 도입됐고, 렌더러 `_bullets`가 heading 문단을 h3 크기·bold·primary 색으로 앞에 그린다. 카드 소제목이 정확히 이 형태다.

**결과: 이번 사이클의 렌더러 변경이 0이다.** Option B가 필요로 했던 "슬롯 쌍을 카드로 묶는" 새 렌더 로직을 만들지 않는다.

### 13.3 결함 B 잔여 항목과의 연결

결함 B 분석 §5.1이 이월한 p6 겹침 3건은 이번 분할로 해소된다. 각 분할 슬롯의 union이 자기 장식에 완전히 포함되고, `SlotBoxPolicy`의 장식 캡(DR-5)이 높이를 그 장식 하단으로 제한하기 때문이다.

`test_known_limitation_multi_card_pattern_still_overlaps`가 실패로 전환되어야 정상이며, §8.6이 교체 절차를 정한다.

---

## 14. Plan 문서 갱신 필요 항목

| 항목 | 내용 |
|------|------|
| Plan §7.2 | 미정 4건 확정 — 분할 정책 배치(DR-1) / 분할↔스냅 순서(DR-5) / 카드 소제목 표현(DR-2) / 목차 상한(DR-8) |
| Plan §5 | "과분할" 리스크 Likelihood를 Medium → **Low**로 하향 (§13.1 시뮬레이션 근거) |
| Plan §5 | "슬롯 id 연쇄 파급" 완화책에 DR-4(기존 suffix 규칙 재사용) 명시 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-26 | 최초 작성 — Option C 선정, 분할 시뮬레이션으로 과분할 0건 확인 | 배상규 |
| 0.3 | 2026-08-26 | Check 반영 — §8.3 시나리오 31 삭제(내부 모순), 이후 번호 재정렬 | 배상규 |
