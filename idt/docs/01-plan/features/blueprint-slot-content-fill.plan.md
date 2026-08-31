# blueprint-slot-content-fill Planning Document

> **Summary**: 슬롯에 내용이 실제로 채워지게 한다 — 카드 슬롯 분할, 목차 결정론적 생성, 길이 초과 시 슬롯 폐기 방지.
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
| **Problem** | 생성된 PPT에서 **목차가 통째로 비고, 마지막 카드 3장이 전부 빈 상태**로 나온다. 원인은 셋이다 — ① 비전 모델이 카드 3장을 슬롯 **하나**로 뭉침 ② 목차를 슬라이드 1장씩 독립 호출로 쓰게 해 다른 슬라이드 제목을 모름 ③ `max_chars` 초과 시 슬롯을 **통째로 폐기** |
| **Solution** | ① 장식 경계 기준으로 슬롯 분할 ② 목차를 계획된 슬라이드 제목에서 **결정론적으로 생성**(LLM 경유 제거) ③ 길이 초과는 **경고만 남기고 내용 유지** |
| **Function/UX Effect** | 목차에 실제 슬라이드 제목이 채워지고, 카드 3장에 소제목·본문이 들어간다. 길이가 조금 넘쳤다는 이유로 슬라이드 한 장이 비는 일이 사라진다 |
| **Core Value** | 결함 A(폰트)·B(좌표)로 **모양**은 맞췄으니, 이제 **내용이 실제로 들어가게** 한다. 골든 샘플 충실도의 마지막 구조적 축이다 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 좌표와 폰트를 고쳤어도 목차·카드가 비어 있으면 산출물로 쓸 수 없다 |
| **WHO** | P2 — 골든 샘플로 자사 문서를 재현해 실제 보고서를 만들려는 KB 운영자 |
| **RISK** | 슬롯 분할이 슬롯 id를 바꿔 writer 프롬프트·정책·렌더러에 연쇄 파급 |
| **SUCCESS** | 골든 샘플 생성물의 목차에 4개 항목이 채워지고, 카드 3장 모두 소제목+본문을 갖는다 |
| **SCOPE** | 슬롯 분할(추출) + 목차 결정론(생성) + 길이 초과 폴백(정책). 차트·표 스타일은 제외 |

---

## 1. Overview

### 1.1 Purpose

결함 A(폰트)·B(좌표)가 산출물의 **형태**를 바로잡았다면, 이번은 **내용이 슬롯에 실제로 들어가게** 한다. 사용자가 신고한 "목차는 나오지도 않았고", "카드 3개 전부 빈 상태"를 해소한다.

### 1.2 Background

#### C-1 — 카드 3장이 슬롯 하나로 뭉쳐 있다

골든 6페이지는 카드 3장이고, 각 카드는 **장식 박스 안에 소제목(15pt Bold) + 본문(13pt)** 구조다.

```
장식 deco2 0.241~0.407  │ '심사 기준 강화'      15pt Bold  y=0.266
                        │ '제조·도소매 업종…'   13pt       y=0.331
장식 deco1 0.444~0.611  │ '조기경보 확대'       15pt Bold  y=0.470
                        │ '연체 15일 이상…'     13pt       y=0.535
장식 deco3 0.648~0.815  │ '한도 관리'          15pt Bold  y=0.673
                        │ '부문 한도 소진율…'   13pt       y=0.739
```

비전 모델은 이 6개 텍스트를 `bullets` 슬롯 **하나**로 줬다. 결과적으로 생성 시 카드 3장에 배분할 방법이 없어 전부 비었고, 결함 B에서도 이 때문에 겹침 3건이 남았다(분석 §5.1).

**접근 근거**: 장식 경계는 이미 **실측으로 확정**돼 있다(결함 B에서 확인). "슬롯에 배정된 span이 서로 다른 장식 N개에 나뉘면 슬롯을 N개로 쪼갠다"는 순수 기하 규칙이 성립하며, 결함 B가 만든 span 배정 기계를 그대로 재사용할 수 있다.

#### C-2 — 목차를 지어내게 하고 있다

원본 목차는 **다른 페이지의 제목 그대로**다.

```
'1. 요약 및 핵심 메시지'   '2. 연체율 추이 분석'
'3. 포트폴리오 현황'       '4. 향후 대응 방안'
```

그런데 `build_write_messages`는 슬라이드를 **한 장씩 독립 호출**한다. 목차 슬라이드를 쓸 때 다른 슬라이드 제목을 전혀 모르므로 evidence만 보고 지어내야 한다.

- 구버전: `1. 서론 - 1페이지` 같은 **존재하지 않는 페이지 번호**를 씀
- 신버전: 아예 아무것도 못 씀 → 제목만 남은 빈 슬라이드

**계획 단계(`_plan`)에서 이미 전 슬라이드의 제목이 확정돼 있다.** LLM에 맡길 이유가 없다.

#### C-3 — 길이 초과 시 슬롯을 통째로 버린다

```python
# policies.py:644 _check_bullets
if slot.max_chars and total > slot.max_chars:
    return f"slot '{slot.id}': bullets {total} > max_chars {slot.max_chars}"
    # → SlotContentPolicy.apply 가 kept 에 넣지 않음 = 내용 소실
```

`_check_text`(632행)도 동일하다. 그리고 `max_chars`는 **비전 LLM 추정값**이라 기준 자체를 신뢰하기 어렵다. 슬롯 높이는 결함 B에서 이미 경계까지 확장했으므로, 조금 넘친다고 내용을 버릴 이유가 약해졌다.

### 1.3 Related Documents

- 사용자 지적 원본: 결함 C (`docs/04-report/blueprint-font-mapping-migration.report.md` §4.2)
- 직전 사이클: `blueprint-slot-box-snap` — 특히 [분석 §5.1](../../03-analysis/blueprint-slot-box-snap.analysis.md) 이 이번 C-1의 근거
- 선행: `pptx-font-fidelity`(FR-03 `SlotContent.heading` 도입), `blueprint-font-mapping-migration`
- 코딩 규칙: `idt/CLAUDE.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **C-1** 장식 경계 기준 슬롯 분할 — 카드 N장 → 슬롯 N개
- [ ] **C-1** 분할된 슬롯의 소제목/본문 구분 (15pt Bold vs 13pt)
- [ ] **C-2** `toc` 패턴 슬라이드의 목차를 계획된 슬라이드 제목에서 결정론적으로 생성
- [ ] **C-3** `max_chars` 초과 시 슬롯 폐기 → **경고만 남기고 내용 유지**
- [ ] 슬롯 id 변경에 따른 writer 프롬프트·정책·렌더러 연쇄 검증
- [ ] 골든 샘플 기준 회귀 — 목차 4항목, 카드 3장 채워짐

### 2.2 Out of Scope

- **결함 D** — 차트 데이터 레이블·단위, 표 테두리, 문단 여백. 별도 사이클
- **표·차트·이미지 슬롯 분할** — 텍스트 슬롯만
- **비전 프롬프트 변경** — 모델에게 카드를 나눠 달라고 요구하지 않는다(비결정적)
- **기존 저장 블루프린트** — C-1은 추출 시점 로직이라 재추출 필요. C-2·C-3은 생성 시점이라 즉시 적용
- `max_chars` 자체를 재계산하는 것 — 추정값을 그대로 두고 소비 방식만 바꾼다

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 텍스트 슬롯에 배정된 span이 서로 다른 장식 N개(N≥2)에 나뉘면 슬롯을 N개로 분할한다 | High | Pending |
| FR-02 | 분할된 각 슬롯은 결정론적 id를 갖고, 원본 슬롯의 kind·role·align을 승계한다 | High | Pending |
| FR-03 | 카드 내부의 소제목(큰 크기 또는 bold)과 본문을 구분해 표현한다 | Medium | Pending |
| FR-04 | `toc` 패턴 슬라이드의 bullets 내용을 **계획된 다른 슬라이드 제목**에서 생성한다 (LLM 미경유) | High | Pending |
| FR-05 | `max_chars` 초과 시 슬롯을 폐기하지 않고 내용을 유지하며 경고를 남긴다 | High | Pending |
| FR-06 | 분할이 불가능하거나 장식이 없으면 원본 슬롯을 유지한다 (폴백) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 분할·목차 규칙은 도메인 순수 함수. domain → infrastructure 참조 없음 | `test_layer_contract.py` |
| 결정론 | 목차 생성에 LLM 호출 없음. 분할은 같은 입력 → 같은 출력 | 도메인 단위 테스트 |
| 하위호환 | 분할되지 않은 기존 패턴은 동작 변화 없음 | 기존 blueprint 테스트 |
| 회귀 | blueprint 관련 기존 테스트(297건) 전부 통과 | `pytest tests/*/blueprint` |
| 비용 | 목차 슬라이드의 writer LLM 호출이 **줄어든다** | 호출 수 측정 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1 — 골든 샘플 생성물의 **목차 슬라이드에 4개 항목**이 채워지고, 각 항목이 다른 슬라이드의 실제 제목과 일치한다
- [ ] SC-2 — 골든 샘플 생성물의 **카드 3장 모두 소제목과 본문**을 갖는다 (빈 카드 0개)
- [ ] SC-3 — p6 패턴의 텍스트 슬롯이 **3개로 분할**되고, 각 슬롯이 서로 다른 장식 하나에 완전히 포함된다
- [ ] SC-4 — **결함 B 잔여 항목 해소**: p6의 장식-슬롯 부분 겹침 3건 → **0건** (`test_known_limitation_multi_card_pattern_still_overlaps`가 실패로 전환되어야 정상)
- [ ] SC-5 — `max_chars`를 초과하는 내용이 렌더에 **살아남고** 경고가 남는다
- [ ] SC-6 — 목차 생성에 LLM 호출이 **0회**임을 테스트가 고정한다
- [ ] SC-7 — 설계 §Test Plan의 **모든 시나리오**에 대응하는 자동화 테스트가 존재한다
- [ ] SC-8 — blueprint 관련 기존 테스트 회귀 0건

> **SC-4는 기존 테스트를 의도적으로 깨는 항목이다.** 결함 B에서 "해소되면 실패해 이월 항목 정리를 유도한다"고 설계한 대로다. 실패를 확인한 뒤 그 테스트를 겹침 0건 단언으로 교체한다.

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하 / if 중첩 2단계 이하
- [ ] `print()` 없음, 명시적 타입, config 하드코딩 없음
- [ ] ruff lint 0건 (**변경한 파일에만** 실행)
- [ ] 신규·변경 코드 커버리지 95% 이상

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **슬롯 id 변경의 연쇄 파급** — id가 바뀌면 writer 프롬프트·`SlotContentPolicy` 조회·렌더러·저장 JSON이 모두 영향 | **High** | High | 분할은 **추출 시점 1회**뿐이고 이후는 일반 슬롯과 동일하게 취급된다. id 생성 규칙을 기존 `_pattern_from_draft`의 suffix 방식(`bullets`, `bullets2`, …)과 통일해 새 규칙을 만들지 않는다 |
| **분할 순서와 좌표 스냅의 상호작용** — 분할은 span 배정이 필요하고 스냅도 그렇다 | Medium | High | Design에서 순서 확정. 분할 → 스냅이 자연스럽다(쪼갠 뒤 각각 스냅). 두 정책이 같은 배정 헬퍼를 공유하도록 설계 |
| **과분할** — 장식이 많은 페이지에서 슬롯이 과도하게 쪼개진다 | Medium | ~~Medium~~ → **Low** | 분할 조건을 "**서로 다른 장식에 완전히 포함**"으로 좁힌다. 애매하면 분할하지 않고 원본 유지(FR-06) |
| **목차 항목이 너무 많거나 길다** — 슬라이드 20장이면 목차 20줄 | Medium | Medium | Design에서 상한·요약 규칙 결정. 골든은 4항목 |
| **C-3 완화가 박스 넘침을 유발** — 길이 제한을 풀면 텍스트가 슬롯 밖으로 | Medium | Low | 결함 B에서 슬롯 높이를 경계까지 확장했고 장식 하단으로 캡했다. 넘침 여지가 이미 줄어든 상태 |
| **샘플 1건 과적합** — 결함 B와 동일 | High | Medium | **미해결 상태 그대로 이월.** 실사용 문서 미확보. 규칙을 일반 기하로만 정의하고 폴백을 둔다 |
| 목차 슬라이드가 자기 자신을 목차에 넣음 | Low | High | 생성 규칙에서 toc 패턴 슬라이드 자신을 제외 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 슬롯 분할 정책 | Domain Policy (신규) | `PageStats` + `PagePattern` + 장식 → 분할된 `PagePattern` |
| 목차 내용 생성 | Domain/Application (신규) | 계획된 `SlidePlan` 목록 → 목차 bullets |
| `_check_text` / `_check_bullets` | Domain Policy | 초과 시 폐기 → 경고 후 유지 |
| `PagePattern.slots` | 저장 데이터 | 스키마 무변경. 슬롯 **개수**가 늘 수 있음 (신규 추출분만) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `Slot.id` | READ | `prompts_generation._catalog` / `build_write_messages` — writer 에게 슬롯 목록 제시 | **의도된 변경** — 분할된 슬롯이 목록에 나타남 |
| `Slot.id` | READ | `SlotContentPolicy.apply` → `pattern.slot(c.slot_id)` | **Needs verification** — LLM이 없는 id를 쓰면 기존대로 경고 후 제외 |
| `Slot.id` | READ | `pptx_renderer._render_slide` → `by_slot` 딕셔너리 | 영향 없음 (id 기반 조회 유지) |
| `Slot.box` | READ | `SlotBoxPolicy` (결함 B) | **Needs verification** — 분할 후 스냅해야 각 슬롯이 제 장식에 맞는다 |
| `_check_bullets` | 호출 | `SlotContentPolicy._violation` | **의도된 변경** — 반환값 의미가 "폐기 사유"에서 "경고"로 |
| `SlotContentPolicy.apply` | 호출 | `generation_use_case._write_one:260` | **Needs verification** — kept/warnings 분리 규칙 변경 |
| writer LLM 호출 | 실행 | `generation_use_case._write_all` | toc 슬라이드에서 **호출 감소** |
| `SlotContent.heading` | READ | `pptx_renderer._bullets` (FR-03, 기존) | **재사용 후보** — 카드 소제목을 여기 담을지 Design에서 결정 |
| 결함 B 한계 테스트 | TEST | `test_known_limitation_multi_card_pattern_still_overlaps` | **의도적 파괴** — SC-4. 겹침 0건 단언으로 교체 |
| 골든 통합 테스트 | TEST | `test_golden_sample_fidelity.py` | 슬롯 개수 기대값 갱신 필요 |
| v1 스냅샷 | TEST | `tests/fixtures/blueprint/golden_v1.json` | **영향 없음** — 저장된 패턴을 그대로 쓰는 회귀 기준선. 수정 금지 |

### 6.3 Verification

- [ ] 분할된 슬롯 id가 writer 프롬프트에 정상 노출되는지 확인
- [ ] 분할 → 스냅 순서가 각 슬롯을 제 장식에 맞추는지 확인
- [ ] `SlotContentPolicy`의 kept/warnings 의미 변경이 기존 호출부를 깨지 않는지 확인
- [ ] 결함 B 한계 테스트를 **의도적으로 실패시킨 뒤** 교체
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
| C 범위 | 일부 / **전부** | **C-1 + C-2 + C-3** | 세 문제가 "슬롯이 비는" 하나의 증상으로 수렴 (Checkpoint 2) |
| 목차 생성 | **결정론적** / LLM 유지 / 복합 | **결정론적 생성** | 계획 단계에 이미 제목이 확정돼 있다. 실패할 여지를 없앤다 (Checkpoint 2) |
| 길이 초과 | **경고만** / truncate / 불릿 줄이기 | **경고만 남기고 유지** | `max_chars`가 비전 추정값이라 기준 자체가 불확실. 슬롯 높이는 이미 확장됨 (Checkpoint 2) |
| 분할 정책 배치 | domain policy / application | **domain `policies.py`** | `DecorationPolicy`·`SlotBoxPolicy`와 동형 (설계 DR-1) |
| 분할 ↔ 스냅 순서 | 분할 먼저 / 스냅 먼저 | **분할 → 스냅** | 분할은 원본 비전 박스로 배정해야 하고 스냅은 쪼개 슬롯별로 (설계 DR-5) |
| 카드 소제목 표현 | `SlotContent.heading` 재사용 / 슬롯 2개(title+text) | **`heading` 재사용** | 렌더러 변경 0 (설계 DR-2) |
| 목차 항목 상한 | — | **12항목 + 초과 시 경고** | 조용히 자르지 않는다 (설계 DR-8) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

영향 레이어:
┌──────────────────────────────────────────────────────────┐
│ domain/blueprint/                                        │
│   policies.py    SlotSplitPolicy(신규) + _check_* 변경    │
│                  SlotBoxPolicy(기존, 순서 협조)           │
├──────────────────────────────────────────────────────────┤
│ application/blueprint/                                   │
│   extraction_use_case.py   분할 결선                      │
│   generation_use_case.py   목차 결정론 생성 결선           │
├──────────────────────────────────────────────────────────┤
│ infrastructure/blueprint/                                │
│   prompts_generation.py    (검증만 — 슬롯 목록 자동 반영)  │
└──────────────────────────────────────────────────────────┘

renderer 변경 없음 — 분할된 슬롯도 일반 슬롯이다.
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙
- [x] `docs/rules/` 세부 규칙
- [x] ruff / pytest 설정
- [x] 도메인 순수성 AST 계약 테스트
- [x] 로드 경계 누락 방지 AST 계약 테스트 (결함 A에서 도입)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 슬롯 id 생성 | exists (`_pattern_from_draft` suffix) | 분할 시 동일 규칙 재사용 | High |
| 경고 메시지 형식 | exists | 분할·길이초과 경고 문구 | Low |
| 린트 실행 범위 | 명문화됨 | **변경 파일에만 ruff** 유지 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | To Be Created |
|----------|---------|:-------------:|
| — | 신규 환경변수 없음 | ☐ |

### 8.4 Pipeline Integration

해당 없음.

---

## 9. Next Steps

1. [ ] 설계 문서 작성 (`/pdca design blueprint-slot-content-fill`) — 분할 정책 배치·순서·소제목 표현 3안 비교
2. [ ] **설계 시뮬레이션** — 분할 규칙 초안을 골든 샘플에 돌려 결과 확인 (결함 B에서 효과 확인된 절차)
3. [ ] TDD 구현 (Red → Green → Refactor)
4. [ ] Gap 분석 (`/pdca analyze`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — 결함 C 대응 (C-1 분할 / C-2 목차 / C-3 길이 폴백) | 배상규 |
| 0.2 | 2026-08-26 | Design 실측 반영 — 미정 4건 확정, 과분할 리스크 하향 | 배상규 |
