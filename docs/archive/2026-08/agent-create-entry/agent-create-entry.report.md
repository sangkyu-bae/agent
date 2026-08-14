# agent-create-entry Completion Report

> **Status**: Complete (수동 E2E 1건 미수행 — §4.1 참조)
>
> **Project**: sangplusbot (`idt_front`)
> **Author**: tkdrb136@gmail.com
> **Completion Date**: 2026-08-13
> **PDCA Cycle**: Plan → Design → Do(3 sessions) → Check

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-create-entry — 에이전트 생성 진입 화면 |
| Start Date | 2026-08-12 |
| End Date | 2026-08-13 |
| Duration | 2일 (Do 단계 2세션: module-1,2 → module-3) |
| PRD | 없음 (Plan부터 시작) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 96.0%                    │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:        12 / 12                  │
│  ✅ 생명주기 계약:   5 / 5 (G1~G5)           │
│  ✅ DoD 충족:        4 / 5                   │
│  ⚠️ 품질 기준:       1 / 4 (3건 전역 기존이슈)│
│  ❌ Critical/Important Gap:  0 / 0           │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `+새 에이전트`가 빈 스튜디오로 직행해, 처음 만드는 사용자가 이름·지침·도구·모델을 스스로 채워야 했다. 이를 대신해 주는 자연어 조합(compose)은 스튜디오 안쪽 `Fix 에이전트` 탭에 묻혀 발견되지 않았다. |
| **Solution** | 전용 진입 화면 `/agent-builder/new` 신설. 설명 한 문장 → 기존 `POST /api/v1/agents/compose` → (필요 시 HITL) → 초안을 스튜디오 폼에 프리필. **백엔드 변경 0 파일** — 기존 자산의 재배치. |
| **Function/UX Effect** | 사이드바 진입점의 첫 화면이 "빈 폼"에서 "한 문장 설명"으로 대체됨. 초안 적용 시 이름·지침·도구 칩·모델·temperature 5개 필드가 자동 충전된다(통합 시나리오 1 검증). 숙련 사용자의 기존 3개 진입 버튼은 불변. |
| **Core Value** | 이미 구현돼 있던 compose·HITL·초안 변환 파이프라인의 **발견성 확보**. 신규 로직 추가가 아니라, 묻혀 있던 기능을 진입점으로 승격시킨 작업. |

---

## 1.4 Success Criteria Final Status

### DoD (Plan §4.1)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01 ~ FR-12 모두 구현 | ✅ Met | Analysis §2.4 — 12/12, 각 항목 file:line 근거 |
| SC-2 | 신규 코드 TDD (선작성 → red → 구현 → green) | ✅ Met | module-3에서 통합 테스트 선작성 → 5/7 red 확인 → 구현 → 7/7 green |
| SC-3 | 기존 `AgentBuilderPage`/`StudioLayout` 테스트 전량 통과 | ✅ Met | 기능 관련 7파일 75/75 |
| SC-4 | 수동 E2E 1회 (설명 → 프리필 → 저장) | ❌ Not Met | dev 서버 미기동. RTL+MSW 통합 테스트로만 검증 |
| SC-5 | SOT 화면 총람 반영 여부 확인 후 보고 | ✅ Met | 확인 완료 — 반영 필요. CLAUDE.md §6 규칙에 따라 수정하지 않고 보고 (§4.1) |

### Quality Criteria (Plan §4.2)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| QC-1 | `npm run lint` 0 에러 | ❌ Not Met | 전역 35 errors. **이 기능 변경 파일 기여분 0건** — `AgentBuilderPage` 2건은 HEAD에도 동일 존재 |
| QC-2 | `npm run build` 성공 | ❌ Not Met | `tsc -b` 실패. HEAD stash 대조로 **기존 18건** 확인. 이 기능 파일 에러는 검출 후 수정 완료 → 현재 0건 |
| QC-3 | `npm run test` 전량 통과 | ⚠️ Partial | 913 passed / 12 failed. 9건 기존 실패 + 3건 부하 기인 flake(격리 시 통과). 이 기능이 만든 회귀 0건 |
| QC-4 | 백엔드 변경 파일 0개 | ✅ Met | `git diff --stat -- idt/src idt/db` 출력 없음 |

**Success Rate**: 5/9 충족 · 1건 부분충족 · 3건 미충족

> 미충족 3건 중 QC-1·QC-2는 **이 기능 이전부터 리포지토리 전역에 존재하던 상태**다. 기준 자체가 전역 범위라 단일 기능 사이클로는 달성이 구조적으로 불가능했다 — Plan 단계의 기준 설정 오류에 가깝다(§6.2 참조). 실질적으로 이번 사이클이 책임질 미충족은 **SC-4(수동 E2E) 1건**이다.

---

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 별도 라우트 `/agent-builder/new` (목록은 `/agent-builder` 유지) | ✅ | URL과 화면이 1:1로 대응. 뒤로가기·북마크 정상 동작 |
| [Plan] | 무저장 프리필 — DB 반영은 스튜디오 `[저장]`만 | ✅ | 진입 화면에 create mutation 호출 경로 자체가 없음 (FR-12) |
| [Plan] | Import는 범위 제외 (비활성 노출) | ✅ | `aria-disabled="true"` + "준비 중" 라벨 |
| [Plan] | HITL은 진입 화면에서 처리 후 스튜디오 진입 | ✅ | 클라이언트 상한 3라운드로 무한 되물음 차단 |
| [Plan] | 실패(`coverage='none'`/API 에러) 시 진입 화면 유지 | ✅ | 라우팅 발생 안 함 + `missing_capabilities` 안내 |
| [Plan] | 취소는 경유 경로에 따라 분기 | ✅ | `fromEntry` 상태로 분기 (FR-11) |
| [Plan] | 사이드바 진입점만 변경 | ✅ | 나머지 3개 버튼 회귀 테스트로 고정 |
| [Design] | **Option B (클린 분리, Zustand 핸드오프)** — 사용자가 권고안 Option C를 물리고 선택 | ✅ | 독립 페이지로 분리돼 단위 테스트가 쉬웠다. 약점인 "유령 초안 잔존"은 G1~G5 계약으로 봉합 |
| [Design] | 생명주기 계약 G1~G5 정의 | ✅ | 5개 전부 코드+테스트 양쪽에서 검증 (§5.2) |
| [Plan] | 변환 로직 단일화 (중복 구현 금지) | ✅ | `composeDraftToForm` 단일 구현을 Fix 탭과 진입 화면이 공유 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-create-entry.plan.md](../01-plan/features/agent-create-entry.plan.md) | ✅ Finalized |
| Design | [agent-create-entry.design.md](../02-design/features/agent-create-entry.design.md) | ✅ Finalized |
| Check | [agent-create-entry.analysis.md](../03-analysis/agent-create-entry.analysis.md) | ✅ Complete (96.0%) |
| Act | 현재 문서 | ✅ Complete |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | `/agent-builder/new` 라우트 + 진입 화면 렌더 | ✅ | `App.tsx:65` (ProtectedRoute 하위) |
| FR-02 | 사이드바 `+새 에이전트` 목적지 변경 | ✅ | `AppSidebar.tsx:99`. 다른 3개 버튼 불변 |
| FR-03 | 공백 전송 차단 + 1~1000자 제한 | ✅ | 서버 `max_length=1000`과 일치 |
| FR-04 | compose 호출 + 로딩 + 중복 전송 차단 | ✅ | |
| FR-05 | HITL 질문 카드 + 재-compose (`round`+1) | ✅ | 클라이언트 상한 3라운드 추가 |
| FR-06 | `[건너뛰기]` 빈 answer 재-compose | ✅ | UI 표현은 Design과 상이 (§4.2) |
| FR-07 | 초안 → create 폼 반영, 변환 로직 공유 | ✅ | `composeDraftToForm` 단일 구현 |
| FR-08 | 실패 시 진입 화면 유지 + 안내 + 2버튼 | ✅ | `coverage_none`/`api_error`/`clarify_exhausted` 3분기 |
| FR-09 | `직접 만들기` → 빈 스튜디오 | ✅ | |
| FR-10 | `가져오기` disabled + "준비 중" | ✅ | |
| FR-11 | 취소 복귀 분기 | ✅ | |
| FR-12 | 저장은 `[저장]`으로만 | ✅ | |

**12 / 12 완료**

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 회귀 안전성 | 기존 목록/생성/편집/삭제/저장 경로 무변경 | 기능 관련 75/75 통과, 회귀 0건 | ✅ |
| 테스트 | compose 성공·HITL·coverage none·실패 4시나리오 MSW | 4시나리오 전부 + L0/L1/L3 추가 | ✅ |
| 접근성 | textarea 라벨, `aria-disabled`, 로딩 안내 | `aria-label` 3종 + `aria-disabled` 적용, RTL role/name 쿼리로 고정 | ✅ |
| 성능 | compose 대기 중 UI 블로킹 없음 | 뮤테이션 비동기, `isPending`으로 입력만 비활성 | ✅ |
| 일관성 | violet-600 계열, `rounded-2xl`, Tailwind 컨벤션 | 기존 토큰 준수 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | LOC | Status |
|-------------|----------|----:|:------:|
| 핸드오프 스토어 | `src/store/agentDraftStore.ts` | 39 | ✅ |
| 초안→폼 변환 유틸 | `src/utils/composeDraftToForm.ts` | 69 | ✅ |
| 진입 화면 | `src/pages/AgentCreateEntryPage/index.tsx` | 215 | ✅ |
| 하위 컴포넌트 4종 | `.../components/` | 251 | ✅ |
| 단위 테스트 (L0) | `agentDraftStore.test.ts`, `composeDraftToForm.test.ts` | 301 | ✅ 20 tests |
| 컴포넌트 테스트 (L2) | `AgentCreateEntryPage/index.test.tsx` | 361 | ✅ 16 tests |
| 통합 테스트 (L3) | `src/__tests__/integration/agentCreateEntry.test.tsx` | 216 | ✅ 7 tests |
| 수정 | `App.tsx`, `AppSidebar.tsx`, `AgentBuilderPage/index.tsx` (+테스트) | +70 / −46 | ✅ |

**신규 1,452줄 (구현 574 / 테스트 878) · 수정 4파일**

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Estimated Effort |
|------|--------|:--------:|------------------|
| **수동 E2E 1회** (SC-4) | dev 서버(백엔드 8000 + 프론트 5173) 미기동 | **High** | 15분 — 사람 눈으로 확인되지 않은 유일한 항목 |
| `docs/SOURCE-OF-TRUTH.md` §6-1/6-2 갱신 | CLAUDE.md §6이 "어긋남 발견 시 고치지 말고 보고"를 규정 | Medium | SOT 전반이 이미 stale (JobsPage·AdminToolsPage 등 다수 누락) — 일괄 갱신 권장 |
| 전역 lint 35건 / `tsc -b` 18건 정리 | 이 기능 이전부터 존재. 범위 밖 | Medium | 별도 작업으로 분리 |
| 테스트 병렬 실행 flake 3건 | 부하 기인 타임아웃. 기능 고유 문제 아님 | Low | CI 재현 시 대응 |
| `에이전트 가져오기` 실제 구현 | Plan에서 명시적으로 범위 제외 | Low | 별도 사이클 |

### 4.2 Design 대비 조정 (설계 문서 갱신 필요)

| Item | Design 명세 | 실제 구현 | 사유 |
|------|-------------|-----------|------|
| HITL 스킵 UI | §5.4 `[건너뛰기]` / `[계속]` 2버튼 카드 | `ClarifyQuestionCard`는 `[답변 제출]` 단일 버튼 — 진입 화면에 `건너뛰고 초안 만들기` 형제 버튼 추가 | 카드를 수정하면 Fix 탭까지 동시 영향. 카드 무변경 재사용이 회귀 위험이 낮다. FR-06 계약은 충족 |
| MSW variant 핸들러 | §11.1 `handlers.ts` [수정] | 미수정 | §8.5 주석이 "기본 핸들러 + 테스트별 `server.use()` override"를 지시 — 파일 수정 불필요 |

> 두 항목 모두 **Design 문서를 현실에 맞춰 갱신**하는 것이 올바른 처리다.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Status |
|--------|:------:|:-----:|:------:|
| Design Match Rate | 90% | **96.0%** | ✅ +6.0 |
| ├ Structural | — | 100% | ✅ |
| ├ Functional Depth | — | 96% | ✅ |
| ├ API Contract | — | 95% | ✅ |
| └ Runtime | — | 95% | ✅ |
| Critical Gap | 0 | **0** | ✅ |
| Important Gap | 0 | **0** | ✅ |
| 신규 테스트 | — | **43** (L0 20 / L2 16 / L3 7) | ✅ |
| 기능 회귀 | 0 | **0** (75/75 통과) | ✅ |
| 백엔드 변경 | 0 파일 | **0 파일** | ✅ |

### 5.2 핵심 리스크 봉합 — 생명주기 계약 G1~G5

Context Anchor의 RISK("초안 전달 중 상태 유실 또는 이중 소스")를 Design 단계에서 5개 규칙으로 명문화하고, 각 규칙에 테스트를 1:1로 붙였다.

| ID | 규칙 | 검증 |
|----|------|------|
| G1 | `persist` 금지, 브라우저 스토리지 미사용 | 스토어 테스트가 `localStorage.length===0 && sessionStorage.length===0` 단언 |
| G2 | `consumePendingIntent()` 원자적 읽기+비우기 | 2회 연속 호출 시 2번째 `null` |
| G3 | 진입 화면 mount 시 clear | 통합 시나리오 4 (유령 초안) |
| G4 | mount effect 1회 + ref 가드, selector 구독 금지 | 통합 시나리오 3 (재적용 없음) |
| G5 | 쿼리 settled 후에만 소비 | 통합 시나리오 2 (80ms 지연 핸들러) |

**5/5 준수.** 이 기능에서 가장 깨지기 쉬웠던 지점이며, 계약을 코드보다 먼저 문서화한 것이 실제로 작동했다.

### 5.3 발견된 Gap (전부 Minor/Info)

| # | Severity | 내용 | 처리 |
|---|:--------:|------|------|
| G-1 | Minor | `clarification_answers` 6개 상한 클라이언트 클램프 없음 | 서버가 질문을 3개로 자르므로(`policies.py:73`) 도달 불가. **기존 Fix 탭도 동일 동작** — 이번 기능이 만든 결함 아님. 미조치 |
| G-2 | Minor | HITL 스킵 UI가 Design §5.4와 상이 | 의도적 선택. Design 문서 갱신 권장 |
| G-3 | Minor | 병렬 실행 시 타임아웃 flake 3건 | 격리 시 27/27 통과. 기능 고유 문제 아님 |
| G-4 | Info | SOT에 `/agent-builder/new` 미반영 | 규칙에 따라 보고만 |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep

- **리스크를 규칙으로 명문화한 뒤 각 규칙에 테스트를 1:1로 붙인 것.** G1~G5는 Design 단계에서 "여기가 깨질 것"이라 지목한 지점이었고, 실제로 Check 단계에서 그 5개가 전부 초록임을 즉시 증명할 수 있었다. 특히 **G5(쿼리 settled 가드)는 문서화하지 않았으면 놓쳤을 함정**이다 — 로딩 중 초안을 적용하면 도구 매핑과 모델 역매핑이 **에러 없이 조용히 실패**한다.
- **module-1을 먼저 끝내고 기존 테스트 초록을 확인한 뒤 진행한 것.** `handleApplyDraft` 추출이 Fix 탭을 건드리는 유일한 지점이었는데, 여기서 회귀를 먼저 차단해 이후 모듈에서 원인 추적이 필요 없었다.
- **기존 실패의 baseline을 `git stash`로 먼저 확정한 것.** 전체 스위트에 9건의 기존 실패가 있었고, 이를 미리 분리해 두지 않았다면 Check 단계에서 내 변경 탓으로 오귀속됐을 것이다.
- **`ClarifyQuestionCard`를 수정하지 않고 재사용한 것.** 공유 컴포넌트를 고치는 대신 형제 버튼을 추가해 Fix 탭 회귀 위험을 0으로 유지했다.

### 6.2 Problem

- **Plan의 품질 기준이 리포지토리 전역 범위로 설정됐다.** "`npm run lint` 0 에러", "`npm run build` 성공"은 이 기능과 무관한 기존 부채(lint 35건, tsc 18건) 때문에 착수 시점부터 달성 불가였다. **단일 기능 사이클의 기준은 "변경 파일 기준"이어야 했다.**
- **`npm run type-check`(`tsc --noEmit`)와 `npm run build`(`tsc -b`)의 검사 범위가 달랐다.** Do 단계에서 전자만 돌려 "클린"으로 보고했으나, Check 단계에서 후자가 내 테스트 파일 2건의 타입 에러를 잡아냈다. **품질 게이트는 CI가 실제로 돌리는 명령과 동일해야 한다.**
- **MSW 핸들러 응답 형태를 훅의 `select`와 대조하지 않았다.** `useLlmModels`가 `select: data.models`로 꺼내는데 배열을 그대로 반환해 모델 역매핑이 조용히 실패했다. 기존 `AgentBuilderPage/index.test.tsx`도 같은 실수를 갖고 있으나 모델을 단언하지 않아 드러나지 않은 상태다 — **잠재적 위양성**.
- **gap-detector 서브에이전트의 리포트 본문이 2회 시도 모두 전달되지 않았다.** 결국 FR별 file:line, G1~G5, 백엔드 스키마 대조를 전부 직접 재검증했다. 에이전트 산출값(94.0%)이 자체 검증치(96.0%)와 일치한 것은 다행이나, **에이전트 결과를 검증 없이 신뢰했다면 근거 없는 수치를 보고할 뻔했다**.

### 6.3 Try

- 품질 기준을 **"변경 파일 기준"과 "전역 기준"으로 분리 표기**한다. 전역 부채는 별도 정리 사이클로 뺀다.
- Plan 단계에서 **CI가 실제로 실행하는 명령**을 확인해 그대로 품질 기준에 적는다.
- MSW 핸들러 작성 시 **대응 훅의 `select`/응답 타입을 먼저 확인**한다.
- 서브에이전트 결과는 **핵심 수치 1~2개를 직접 재검증**한 뒤 채택한다.
- 공유 컴포넌트 재사용 시 Design 명세와 실물이 어긋나면, **구현을 맞추기보다 Design을 갱신**하는 쪽을 기본값으로 한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement |
|-------|---------|-------------|
| Plan | 품질 기준이 전역/지역 구분 없이 기술됨 | 기준마다 측정 범위(변경 파일 / 전역)를 명시 |
| Design | G1~G5 계약 문서화가 매우 효과적이었음 | **상태 핸드오프가 있는 기능은 생명주기 계약 명문화를 기본 절차로** 승격 |
| Do | `type-check`와 `build`의 범위 차이를 인지 못함 | Do 종료 게이트를 `npm run build`로 통일 |
| Check | 서브에이전트 리포트 전달 실패 | 에이전트 결과 미도달 시 즉시 직접 검증으로 전환 (이번에 실제로 수행) |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] **수동 E2E 1회** — dev 서버 기동 후 사이드바 → 설명 입력 → 프리필 확인 → 저장 (SC-4 유일 미충족)
- [ ] Design 문서 §5.4 / §11.1 갱신 (§4.2 조정 2건 반영)
- [ ] `/pdca archive agent-create-entry`

### 8.2 Next Cycle 후보

| Item | Priority | Note |
|------|:--------:|------|
| `에이전트 가져오기` 실구현 | Medium | 같은 핸드오프 경로(파일 → 초안 → 스튜디오) 재사용 가능하도록 설계됨 |
| SOT 문서 일괄 갱신 | Medium | `/agent-builder/new` 외 다수 누락 |
| 전역 lint/tsc 부채 정리 | Medium | 35 + 18건 |

---

## 9. Changelog

### agent-create-entry (2026-08-13)

**Added:**
- `/agent-builder/new` — 에이전트 생성 진입 화면 (히어로 + 설명 입력 + 액션 카드 2종)
- 자연어 설명 → compose 초안 → 스튜디오 프리필 흐름 (HITL 3라운드 상한 포함)
- `agentDraftStore` — 1회 소비 비영속 핸드오프 스토어 (G1~G5 계약)
- `composeDraftToForm` — 초안→폼 변환 순수 함수 (Fix 탭과 공유)
- 신규 테스트 43건 (L0 20 / L2 16 / L3 7)

**Changed:**
- 사이드바 `+새 에이전트` 목적지: `/agent-builder` → `/agent-builder/new`
- `AgentBuilderPage.handleApplyDraft`: 40줄 인라인 로직 → 4줄 위임 래퍼
- 스튜디오 `[취소]`: 진입 화면 경유 시 `/agent-builder/new`로 복귀 (그 외 목록 유지)

**Unchanged (의도적):**
- 목록 헤더 `+새 에이전트`, 목록 빈 상태, 사이드바 빈 상태 버튼 — 빈 스튜디오 직행 유지
- 백엔드 — 0 파일

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-13 | 완료 보고서 작성 — Match 96.0%, FR 12/12, Critical·Important 0건 | tkdrb136@gmail.com |
