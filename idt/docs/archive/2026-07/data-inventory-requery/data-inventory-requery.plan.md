# Data Inventory Requery Planning Document

> **Summary**: 시각화 재질문 시 이전 턴 재주입 데이터만으로 분석 워커를 **강제 라우팅**해 재검색 판단을 우회하는 결함 수정 — 보유 데이터를 "인벤토리"로 LLM에 제시하고, 재사용(범위 안) vs 재검색(범위 밖)을 supervisor LLM이 순회 판단하게 복원. 재검색 수집분은 기존 스냅샷 체계로 인벤토리에 누적
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-22
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 1턴 "나의 남은 휴가 그래프" → search → 차트 성공 후, 2턴 "전체 사용자 남은 휴가 그래프"에서 재검색 없이 "배상규님의 휴가 정보만 확인할 수 있으며 … 시각화할 수 없습니다" 응답. 원인: 이전 턴 검색결과가 `format_search_result` 규약으로 재주입되어 `is_search_result()`=True가 되고, `AttachmentRoutingHooks._viz_intent_with_search_results`가 "시각화 의도 + 검색결과 존재"만으로 분석 워커를 강제 라우팅 — supervisor LLM의 "보유 데이터 범위 밖이면 먼저 검색" 판단(`_render_data_context_block` 지시)이 LLM 호출 전 hook에서 우회됨 |
| **Solution** | ① 강제 라우팅 트리거에서 재주입분(REINJECTED_MARKER) 제외 — 현재 턴에서 실제 수집한 검색결과가 있을 때만 분석 워커 강제, 재주입분만 있으면 첫 라우팅은 LLM 판단 ② 보유 데이터 인지 블록을 "인벤토리" 형태로 강화(항목별 원 질문·출처·수집 시점 구분 노출)해 LLM이 항목을 순회하며 커버리지를 판단할 근거 제공 ③ 재검색 수집분은 기존 analysis-data-continuity 스냅샷 체계로 자동 누적·다음 턴 재주입(무변경 확인) |
| **Function/UX Effect** | 범위가 확대된 재질문("전체 사용자")은 재검색 → 분석 → 차트 경로를 정상 주행하고, 동일 범위 재질문("아까 그거 막대그래프로")은 재검색 없이 보유 데이터로 즉시 분석·차트 생성. 턴이 거듭될수록 수집 데이터가 인벤토리에 쌓여 후속 질문 커버리지가 넓어짐 |
| **Core Value** | 결정적 강제 라우팅(차트 경로 보장)과 LLM 판단(재사용 vs 재수집)의 책임 분리 복원 — 강제 라우팅은 "현재 턴에 데이터를 수집했다"는 확실한 신호에만 반응하고, 불확실한 판단(보유 데이터로 충분한가)은 인벤토리를 근거로 LLM이 수행 |

---

## 1. Overview

### 1.1 Purpose

시각화 재질문 턴에서 이전 턴 재주입 데이터만으로 분석 워커를 강제 라우팅해
재검색 기회를 차단하는 결함을 수정한다. 사용자 합의 방향:
**"들고 있던 데이터로 답을 낼 수 있으면 재사용, 새 데이터가 필요하면 검색해 수집하고,
수집분을 리스트(인벤토리)로 유지해 이후 질문 시 LLM이 순회 확인 후 판단"**.
기존 analysis-data-continuity 스냅샷 체계가 인벤토리 저장·재주입을 이미 담당하므로,
이번 수정은 **판단 우회 제거 + 판단 근거 강화**에 집중한다.

### 1.2 Background (2026-07-22 코드 추적으로 원인 확정)

**증상**: 커스텀 에이전트 대화에서
1턴 "나의 남은 휴가 그래프로 그려줘" → search 노드 → 분석 → 차트 생성 (정상).
2턴 "그럼 이제 전체 사용자 남은 휴가 그래프로 그려줄래" → **search 노드 미경유**,
"현재 시스템에서는 배상규님의 휴가 정보만 확인할 수 있으며, 다른 사용자들의 휴가 정보는
내부 문서에서 검색되지 않았습니다. … 추가적인 정보가 필요합니다." 응답.
("검색되지 않았습니다"는 실제 검색 결과가 아니라 보유 데이터 부재에 대한 LLM 작문)

**원인 체인**:

1. **이전 턴 검색결과 재주입** — `run_agent_use_case.py:881-904` `_inject_snapshot_messages`가
   1턴 스냅샷(배상규 휴가 데이터)을 `format_search_result(origin, ...)` 규약 AIMessage로
   새 user 메시지 직전에 삽입. 재주입 본문에 `REINJECTED_MARKER`가 있지만
   `is_search_result()`(`search_pipeline.py:44-54`)는 name + "검색결과" 마커만 보므로 True.
2. **강제 라우팅이 LLM 판단을 우회** — `supervisor_nodes.py:181-187`에서 supervisor 노드는
   LLM 호출 **전에** `hooks.force_worker(state)`를 먼저 평가. `supervisor_hooks.py:69-80`
   `_viz_intent_with_search_results`는 (a) 최신 질문의 시각화 의도 + (b) `any(is_search_result(m))`
   만으로 분석 워커를 강제 반환 — 재주입분/현재 턴 수집분을 구분하지 않음.
3. **판단 지시는 존재하나 도달 불가** — `supervisor_nodes.py:49-67` `_render_data_context_block`이
   "요청이 보유 데이터 범위를 벗어나면(대상·기간·집단 확대 등) 먼저 검색 워커로 새 데이터를
   수집한 뒤 분석 워커를 호출하세요"를 이미 지시하지만, 2턴 첫 라우팅이 hook에서 강제되어
   LLM이 이 지시를 적용할 기회 자체가 없음.
4. **결과** — 분석 워커는 배상규 데이터만 보유한 채 "전체 사용자" 요청을 받고
   "시각화 불가·추가 정보 필요" 응답 생성. 이후 `visualization_done`/skip 가드로 재시도 없이 종료.

**설계 의도와의 충돌**: `_viz_intent_with_search_results`의 원 목적(supervisor-viz-routing)은
"**현재 턴에서** 검색을 마친 뒤 LLM이 검색결과만으로 FINISH 해 차트 경로를 건너뛰는 것"의 차단.
재주입분은 이 목적의 트리거로 의도된 적이 없으나, 메시지 규약 공유(`is_search_result`)로
analysis-data-continuity 도입 시점부터 오탐이 발생하게 됨 — 두 기능의 교차 회귀.

**데이터 전제 (사용자 확인)**: 전체 사용자 휴가 데이터는 KB에 색인되어 있고 질문자가 접근
가능해야 함 — 1턴 검색이 동일 문서(휴가 현황)에서 배상규 데이터를 찾았으므로 재검색 시
"전체 사용자" 쿼리로 히트 가능해야 정상. E2E에서 실측 확인(S5).

### 1.3 Related Documents

- 재주입 체계: analysis-data-continuity Design §3.3-3.5 (`analysis_snapshot_policy.py`, `run_agent_use_case.py:829-904`)
- 시각화 강제 라우팅: supervisor-viz-routing (`supervisor_hooks.py:25-87` docstring)
- 검색 파이프라인·메시지 규약: search-node-query-pipeline Design §2-2 (`search_pipeline.py`)
- 인접 선례: `docs/archive/2026-07/` supervisor-overblock-fix — "결정적 코드가 LLM 판단을 이긴다"의 동일 계열 결함 (그쪽은 프롬프트 프레이밍, 이번은 hook 우회)
- 하류 권한 필터: rag-auth-filter-fix (검색 자체는 정상 동작 전제)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 강제 라우팅 재주입분 제외**: `AttachmentRoutingHooks._viz_intent_with_search_results`가
      재주입 메시지(`REINJECTED_MARKER` 포함)를 트리거 집계에서 제외 — 현재 턴 수집
      검색결과가 1건 이상일 때만 분석 워커 강제. 재주입 판정은
      `AnalysisSnapshotPolicy.is_reinjected`(domain) 재사용 (규약 단일 출처 유지)
- [ ] **S2. 데이터 인벤토리 블록 강화**: `_render_data_context_block`을 인벤토리 형태로 개선 —
      항목별로 ① 수집 구분(이번 턴 수집 / 이전 턴 보유) ② 원 질문(재주입 본문의 `(질문: ...)`)
      ③ 출처 워커 ④ 내용 요약을 리스트로 노출하고, "각 항목을 순회하며 현재 요청을 커버하는지
      확인 후 재사용/재수집을 결정하라"는 순회 판단 지시로 문구 보강 (문구는 Design에서 확정)
- [ ] **S3. 인벤토리 누적 경로 확인**: 재검색 수집분이 스냅샷으로 수집(`_snapshot_items` — 재주입분
      제외 수집 기존 로직)되고 `select_recent` 상한 내에서 이전 스냅샷과 함께 다음 턴 재주입되는지
      확인 — **코드 무변경 목표**, 동작 확인 테스트만 추가 (상한/선별 정책 변경은 Out of Scope)
- [ ] **S4. 회귀 테스트**: ① hooks 단위 — 재주입분만 존재 시 강제 라우팅 안 함 / 현재 턴 수집분
      존재 시 강제함 / 엑셀 첨부 트리거·visualization_done 가드 불변 ② 인벤토리 블록 렌더링 단언
      ③ 기존 supervisor·hooks·search 테스트 무회귀
- [ ] **S5. E2E 수동 검증**: 재현 시나리오 2턴 질의가 search 노드를 경유해 "전체 사용자" 데이터를
      수집 → 분석 → 차트 생성하는지 run step 실측 + 동일 범위 재질문("방금 데이터 막대그래프로")이
      재검색 없이 분석 직행하는지 실측

### 2.2 Out of Scope

- 스냅샷 저장·선별·상한 정책 변경 (`analysis_snapshot_policy.py` 무변경 — is_reinjected 재사용만)
- 검색 파이프라인(rewrite/validate/compress)·메시지 규약(`is_search_result`) 변경 —
  규약 시그니처를 바꾸면 final_answer/analysis 노드 등 공용 소비처 전반에 파급
- General Chat 경로(`general_chat/use_case.py`)의 스냅샷·차트 편집 분기 — 이번 결함은
  agent supervisor 경로 한정 (General Chat은 chart-context-continuity 편집 분기가 별도 담당)
- "전체 사용자" 검색이 0건일 때의 KB 색인·권한 보강 (rag-auth-payload-indexing 후속 트랙 —
  S5 실측에서 0건이 확인되면 해당 트랙으로 이관)
- 프론트엔드 변경 (백엔드 전용 — API 계약 불변)
- DB 마이그레이션 (없음)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | state의 검색결과가 재주입분뿐일 때 시각화 의도가 있어도 분석 워커 강제 라우팅이 발생하지 않는다 (첫 라우팅은 supervisor LLM 판단) | High | Pending |
| FR-02 | 현재 턴에서 수집한(비-재주입) 검색결과가 존재하면 기존과 동일하게 시각화 의도 시 분석 워커가 강제 라우팅된다 (supervisor-viz-routing 기능 보존) | High | Pending |
| FR-03 | 엑셀 첨부 강제 라우팅·`visualization_done` 가드·분석 워커 직후 재강제 금지 등 기존 hook 동작은 불변이다 | High | Pending |
| FR-04 | 데이터 인지 블록이 항목별 수집 구분·원 질문·출처를 포함한 인벤토리 리스트로 렌더링되고, 순회 판단 지시를 포함한다 | High | Pending |
| FR-05 | 재검색으로 수집한 데이터가 스냅샷으로 영속되어 다음 턴 인벤토리에 이전 수집분과 함께 나타난다 (기존 select_recent 상한 정책 내) | Medium | Pending |
| FR-06 | 범위 확대 재질문 시나리오에서 search 노드 경유 후 분석·차트가 생성된다 (E2E 수동 — run step 실측) | High | Pending |
| FR-07 | 동일 범위 재질문 시나리오에서 재검색 없이 보유 데이터로 분석·차트가 생성된다 (E2E 수동) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 pytest 무회귀 (사전 실패분 제외 기준) — 특히 supervisor_hooks·supervisor_nodes·viz 라우팅 테스트 | pytest 격리 실행 |
| 아키텍처 | application → domain 참조만 추가 (`analysis_snapshot_policy` import) — 레이어 규칙 준수 | verify-architecture 스킬 |
| TDD | 테스트 선행 (Red → Green → Refactor) | verify-tdd 스킬 |
| 토큰 비용 | 인벤토리 블록은 항목당 1-2줄 요약 유지 (본문 미포함 — 기존 `_summarize_data_entry` 절약 원칙 계승) | 렌더링 테스트 단언 |
| 로깅 | 강제 라우팅 skip 사유(재주입분만 존재)를 관측 가능하게 — 신규 로그 LOG-001 준수 | verify-logging 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 재현 시나리오: 1턴 "나의 남은 휴가 그래프" → 차트, 2턴 "전체 사용자 남은 휴가 그래프" →
      **search 노드 경유** → 전체 사용자 데이터 수집 → 차트 생성 (run step 실측)
- [ ] 동일 범위 재질문은 재검색 없이 분석 직행 (불필요 재검색 미발생)
- [ ] hooks·인벤토리 블록 신규 테스트 전부 통과 + 기존 테스트 무회귀
- [ ] 2턴 검색이 0건이면 결함이 아니라 KB 색인/권한 문제로 판별 가능 (search step 로그로 분리 관측)

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, 하드코딩 config 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM이 동일 범위 재질문에서도 재검색을 선택 (불필요 비용·지연) | Low | Medium | 인벤토리 블록의 "범위 안이면 재수집 없이 분석 워커 호출" 지시 유지·강화 (S2). FR-07 E2E로 확인 |
| LLM이 범위 확대인데도 분석 직행 선택 (증상 잔존) | Medium | Low | 강제 라우팅 제거로 판단 기회는 구조적으로 보장 — 인벤토리에 원 질문("나의 남은 휴가")이 노출되어 "전체 사용자"와의 범위 차이가 명시적으로 대비됨. 잔존 시 Design에서 지시 문구 반복 배치 검토 |
| 재주입분 제외로 기존 viz 강제 라우팅 회귀 (검색 직후 FINISH 재발) | High | Low | 현재 턴 수집분은 재주입 마커가 없어 기존 트리거 그대로 동작 (FR-02) — hooks 단위 테스트로 결정적 검증 |
| "전체 사용자" 재검색이 실제 0건 (KB 색인·auth 필터 원인) | Medium | Medium | 이번 수정과 독립된 데이터 문제로 분리 — search step 로그로 판별하고 rag-auth-payload-indexing 트랙으로 이관 (Out of Scope 명시). 라우팅 수정 자체는 유효 |
| LLM 비결정성으로 E2E 검증 불안정 | Medium | Medium | 단위 검증은 hook·렌더링 단언으로 결정적으로 수행, E2E는 보조 실측(FR-06/07)으로 한정 |
| application(hooks) → domain(snapshot policy) 신규 의존이 결합 증가 | Low | Low | domain 정책 재사용은 레이어 규칙상 허용 방향 — 마커 문자열 중복 정의(이중 출처)보다 안전 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 재사용/재수집 판단 주체 | 결정적 코드(무조건 재검색) / LLM 판단 | LLM 판단 (사용자 합의) | 동일 범위 재질문의 불필요 재검색 방지 — 강제 라우팅은 "현재 턴 수집 완료"라는 확실 신호에만 유지 |
| 재주입 판정 방법 | 마커 문자열 재정의 / domain 정책 재사용 | `AnalysisSnapshotPolicy.is_reinjected` 재사용 | 규약 단일 출처 (D2 원칙 계승) — 마커 변경 시 파급 1곳 |
| 인벤토리 저장소 | 신규 state 필드 / 기존 스냅샷 체계 | 기존 스냅샷 체계 (무변경) | analysis-data-continuity가 이미 "리스트 누적 + 상한 선별 + 재주입"을 제공 — 신규 저장소는 이중 관리 |
| 인벤토리 제시 위치 | supervisor 결정 프롬프트 블록 / 별도 노드 | 기존 `_render_data_context_block` 강화 | 구조 변경 없이 판단 근거만 보강 — 변경 반경 최소화 |

### 6.3 변경 대상 파일 (예상)

```
idt/src/
├── application/agent_builder/supervisor_hooks.py   # S1: 재주입분 제외 트리거
├── application/agent_builder/supervisor_nodes.py   # S2: 인벤토리 블록 렌더링·지시 문구
└── tests/application/agent_builder/
    ├── test_supervisor_hooks.py (또는 기존 파일)    # S4: FR-01/02/03 단언
    └── supervisor_nodes 렌더링 테스트               # S4: FR-04 단언, S3: FR-05 확인
```

> 인벤토리 블록의 정확한 항목 구성·지시 문구·로그 위치는 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] 검증 스킬 존재: verify-architecture, verify-logging, verify-tdd
- [x] 백엔드 테스트 격리 실행 관례 (Windows 이벤트 루프 flakiness)
- 환경변수·마이그레이션·API 계약 변경 **없음** (프론트 동기화 불필요)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. FR-01/02/03  hooks 재주입분 제외: 단위 테스트 먼저 (재주입만/현재턴수집/첨부/가드 4분면) → supervisor_hooks 수정
2. FR-04        인벤토리 블록 강화: 렌더링 테스트 먼저 → _render_data_context_block 수정
3. FR-05        스냅샷 누적 경로 확인 테스트 (코드 무변경 목표)
4. 전체 pytest 무회귀 + FR-06/07 E2E 수동 실측
```

### 8.2 검증 자료

- 검증 경로: `GET /agents/runs/{run_id}` step 목록 — 2턴에 search 워커 step 존재 여부,
  supervisor step `output_summary`(reasoning), search step `output_summary`(query·attempts·결과 길이)
- 재현 질의: 1턴 "나의 남은 휴가 개수 그래프로 그려줘" → 2턴 "그럼 이제 전체 사용자 남은 휴가
  그래프로 그려줄래" (원 결함 시나리오 그대로) + 3턴 동일 범위 변형 "방금 그 데이터 막대그래프로"

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design data-inventory-requery`) — 인벤토리 항목 구성·지시 문구·hook 시그니처 확정
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze data-inventory-requery`)
4. [ ] E2E에서 "전체 사용자" 검색 0건 확인 시: rag-auth-payload-indexing 트랙으로 데이터 문제 이관

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-22 | Initial draft — 재주입×강제 라우팅 교차 회귀 원인 코드 추적 + 인벤토리 판단 방향(사용자 합의) 반영 | 배상규 |
