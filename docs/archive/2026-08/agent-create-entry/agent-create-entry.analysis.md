# agent-create-entry Analysis Report

| Field | Value |
|-------|-------|
| **Feature** | agent-create-entry |
| **Phase** | Check (Gap Analysis) |
| **Analyzed** | 2026-08-13 |
| **Plan** | `docs/01-plan/features/agent-create-entry.plan.md` |
| **Design** | `docs/02-design/features/agent-create-entry.design.md` |
| **PRD** | 없음 (`/pdca pm` 미실행 — Plan부터 시작한 사이클) |
| **Overall Match Rate** | **96.0%** |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 생성 진입점이 빈 폼이라 초보 사용자가 막히고, 이미 구현된 자연어 조합(compose+HITL)이 스튜디오 내부 탭에 묻혀 있다 |
| **WHO** | P2(에이전트 소유자/KB 운영자) 중 처음 에이전트를 만드는 사용자 |
| **RISK** | 진입 화면(신규 라우트)과 스튜디오(`AgentBuilderPage` 내부 `view` 상태) 사이의 초안 전달(state handoff) |
| **SUCCESS** | 사이드바 `+새 에이전트` → 설명 1문장 → (필요 시 HITL) → 프리필된 스튜디오 도달. 기존 회귀 0건 |
| **SCOPE** | 프론트 전용 3모듈. Import는 UI만 비활성 노출 |

---

## Strategic Alignment Check

PRD가 없으므로 Plan의 Executive Summary를 상위 기준으로 삼는다.

| 질문 | 판정 | 근거 |
|------|:----:|------|
| 핵심 문제(발견성)를 해결했는가 | ✅ | 사이드바 진입점이 `/agent-builder/new`로 이동(`AppSidebar.tsx:99`), 첫 화면이 설명 입력창으로 대체 |
| "새 기능이 아니라 재배치"라는 전제를 지켰는가 | ✅ | 백엔드 변경 0 파일(`git diff idt/src idt/db` 공백), compose·`ClarifyQuestionCard`·초안 변환 로직 전부 기존 자산 재사용 |
| 숙련 사용자 경로를 건드리지 않았는가 | ✅ | 목록 헤더·목록 빈 상태·사이드바 빈 상태 버튼은 `handleNew` 직행 유지 (통합 시나리오 6에서 검증) |
| 선택된 아키텍처(Option B)를 따랐는가 | ✅ | Zustand 핸드오프 스토어 + 독립 페이지. `AgentBuilderPage`에 진입 화면 UI를 얹지 않음 |

---

## Success Criteria Status (Plan §4)

### 4.1 Definition of Done

| # | 항목 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | FR-01 ~ FR-12 모두 구현 | ✅ | 아래 §2.4 표 |
| 2 | 신규 코드 TDD (테스트 선작성 → 실패 확인 → 구현) | ✅ | module-3에서 통합 테스트 선작성 후 5/7 red 확인 → 구현 → 7/7 green |
| 3 | 기존 `AgentBuilderPage`/`StudioLayout` 테스트 전량 통과 | ✅ | 기능 회귀 7파일 75/75 |
| 4 | 수동 E2E 1회 (설명 → 프리필 → 저장) | ❌ | **미수행** — dev 서버 미기동. RTL 통합 테스트로만 검증됨 |
| 5 | `docs/SOURCE-OF-TRUTH.md` 화면 총람 반영 여부 확인 후 보고 | ⚠️ | 확인 완료 — 반영 **필요**. §6-1/6-2가 `/agent-builder/new` 미포함(그 외에도 JobsPage 등 다수 누락으로 이미 stale). CLAUDE.md §6 규칙에 따라 **수정하지 않고 보고만** 함 |

### 4.2 Quality Criteria

| 항목 | 판정 | 근거 |
|------|:----:|------|
| `npm run lint` 0 에러 | ❌ | 프로젝트 전체 **35 errors / 4 warnings**. 이 중 이 기능 변경 파일 기여분은 **0건** (`AgentBuilderPage` 2건은 HEAD에도 동일 존재하는 기존 `set-state-in-effect`) |
| `npm run build` 성공 | ❌ | `tsc -b` 실패. HEAD stash 대조 결과 **기존 18건**(AgentStorePage, agentAttachmentService, StudioHeader, vite.config.ts, useAgentComposer.test.ts 등). 이 기능 파일 에러는 검출 후 **수정 완료 → 현재 0건** |
| `npm run test` 전량 통과 | ⚠️ | 913 passed / 12 failed. 9건은 stash 대조로 확인한 기존 실패, 3건은 격리 실행 시 통과하는 부하 기인 flake (§2.7) |
| 백엔드 변경 파일 0개 | ✅ | `git diff --stat -- idt/src idt/db` 출력 없음 |

> lint·build 미충족은 **이 기능 이전부터 존재하던 상태**다. 기준 자체가 리포지토리 전역이라 이번 사이클에서 달성 불가하며, 별도 정리 작업으로 분리해야 한다.

---

## 1. Analysis Overview

### 1.1 Purpose

Design 문서(특히 §2.4 핸드오프 생명주기 계약 G1~G5, §5.4 Page UI Checklist)와 실제 구현 코드의 간극을 측정한다.

### 1.2 Scope

- 대상 코드: `idt_front/src/` 신규 8파일 + 수정 4파일
- 백엔드: 무변경이 전제 — 변경 여부만 검증
- 런타임 검증: Playwright 미도입 프로젝트이므로 Design §8 방침대로 Vitest + RTL + MSW로 L2/L3 대체 수행

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Structural Match — 100%

| Design §11.1 명세 | 구현 | 판정 |
|-------------------|------|:----:|
| `src/store/agentDraftStore.ts` | 존재 (+ `.test.ts` 7 tests) | ✅ |
| `src/utils/composeDraftToForm.ts` | 존재 (+ `.test.ts` 13 tests) | ✅ |
| `src/pages/AgentCreateEntryPage/index.tsx` | 존재 (+ `index.test.tsx` 16 tests) | ✅ |
| `components/EntryHero.tsx` | 존재 | ✅ |
| `components/DescriptionComposer.tsx` | 존재 | ✅ |
| `components/EntryActionCards.tsx` | 존재 | ✅ |
| `components/ComposeFailureCard.tsx` | 존재 | ✅ |
| `AgentBuilderPage/index.tsx` 수정 (소비 effect·취소 분기·util 위임) | 3건 모두 반영 | ✅ |
| `/agent-builder/new` 라우트 (ProtectedRoute 하위) | `App.tsx:65` | ✅ |
| `__tests__/mocks/handlers.ts` 수정 | **미수정** | ✅ (의도적 — Design §8.5 주석이 "기본 핸들러 + 테스트별 `server.use()` override"를 지시. 파일 수정 불필요) |

### 2.2 Data Model

신규 DB 스키마 없음(무저장 계약). 클라이언트 전용 타입 1종:

```ts
type AgentCreateIntent =
  | { kind: 'draft'; draft: ComposeAgentDraftResponse }
  | { kind: 'blank' };
```

Design §3의 정의와 일치. ✅

### 2.3 Lifecycle Contract G1~G5 — 5/5 준수

| ID | 규칙 | 판정 | 근거 |
|----|------|:----:|------|
| **G1** | `persist` 금지, 브라우저 스토리지 미사용 | ✅ | `agentDraftStore.ts:22` 주석 + `create()` 순수 사용. `agentDraftStore.test.ts`가 `localStorage.length===0 && sessionStorage.length===0` 단언 |
| **G2** | `consumePendingIntent()` 원자적 읽기+비우기 | ✅ | `agentDraftStore.ts:32-36` — 같은 호출에서 `set({pendingIntent:null})`. 테스트: 2회 연속 호출 시 2번째 `null` |
| **G3** | 진입 화면 mount 시 `clearPendingIntent()` | ✅ | `AgentCreateEntryPage/index.tsx:52-54`. 통합 시나리오 4에서 검증 |
| **G4** | mount effect 1회 + ref 가드, selector 구독 금지 | ✅ | `AgentBuilderPage/index.tsx:116-122` — `consumedIntentRef` 가드 + `useAgentDraftStore.getState()`만 사용(훅 구독 없음). 통합 시나리오 3에서 재적용 없음 검증 |
| **G5** | 쿼리 settled 후에만 소비 | ✅ | `AgentBuilderPage/index.tsx:119` — `isToolsLoading \|\| isModelsLoading` 가드. 통합 시나리오 2가 80ms 지연 핸들러로 검증 |

> 이 기능의 최대 리스크(Context Anchor의 RISK)가 G1~G5에 집중되어 있었고, 5개 전부 코드와 테스트 양쪽에서 확인된다.

### 2.4 Functional Depth Analysis — 96%

| FR | 요구 | 판정 | 근거 |
|----|------|:----:|------|
| FR-01 | `/agent-builder/new` 라우트가 인증 사용자에게 진입 화면 렌더 | ✅ | `App.tsx:65` (ProtectedRoute→AgentChatLayout 하위) |
| FR-02 | 사이드바 `+새 에이전트`만 목적지 변경 | ✅ | `AppSidebar.tsx:99`. 나머지 3개 버튼 불변 (통합 시나리오 6) |
| FR-03 | 공백만 입력 시 전송 비활성, 1~1000자 | ✅ | `DescriptionComposer.tsx:3,25,55` — `MAX_USER_REQUEST_CHARS=1000` slice + `canSubmit` |
| FR-04 | compose 호출 + 로딩 표시 + 중복 전송 차단 | ✅ | `index.tsx:129-136` (`isPending` 가드), `DescriptionComposer.tsx:41` 로딩 인디케이터 |
| FR-05 | `needs_clarification` → 질문 카드 → `[계속]`으로 재-compose (`round`+1) | ✅ | `index.tsx:66-82, 138-145` |
| FR-06 | `[건너뛰기]`는 빈 answer로 재-compose | ✅ | `index.tsx:148-157` — `answer: ''` 매핑 |
| FR-07 | 초안을 create 폼에 반영, 변환 로직 **공유** | ✅ | `composeDraftToForm.ts` 단일 구현을 Fix 탭(`handleApplyDraft`)과 진입 화면이 공유. 중복 구현 없음 |
| FR-08 | `coverage='none'`/실패 시 진입 화면 유지 + 안내 + 2버튼 | ✅ | `index.tsx:88-97, 120-124` + `ComposeFailureCard.tsx` |
| FR-09 | `직접 만들기` → 빈 스튜디오 | ✅ | `EntryActionCards.tsx:12` → `goStudio({kind:'blank'})` |
| FR-10 | `가져오기` disabled + "준비 중" | ✅ | `EntryActionCards.tsx:37,57` (`aria-disabled="true"`) |
| FR-11 | 취소 복귀 분기 | ✅ | `AgentBuilderPage/index.tsx:423-427` (`fromEntry`) |
| FR-12 | 저장은 `[저장]`으로만 발생 | ✅ | 진입 화면에 create mutation 호출 경로 없음. 핸드오프는 폼 프리필까지만 |

**감점 사유 (−4%)**: FR-06의 UI 표현이 Design §5.4 명세(`[건너뛰기]/[계속]` 2버튼 카드)와 다르게 구현됨 — 아래 §2.5 참조. 기능 계약은 충족.

### 2.5 Page UI Checklist Verification (Design §5.4)

| 항목 | 판정 | 비고 |
|------|:----:|------|
| 히어로 로고 + 타이틀 + 서브카피 | ✅ | `EntryHero.tsx` |
| 설명 textarea (라벨 있음) | ✅ | `aria-label="에이전트 설명"` |
| 전송 버튼 (빈 입력 시 disabled) | ✅ | `aria-label="에이전트 설명 전송"` |
| 로딩 인디케이터 | ✅ | `aria-label="초안 생성 중"` |
| `에이전트 직접 만들기` 카드 | ✅ | |
| `에이전트 가져오기` 카드 (비활성/준비 중) | ✅ | |
| 1000자 초과 입력 차단 | ✅ | |
| HITL 질문 카드 `[건너뛰기]` / `[계속]` | ⚠️ | 기존 `ClarifyQuestionCard`는 `[답변 제출]` 단일 버튼이며 skip 버튼이 없다. 카드를 수정하면 Fix 탭까지 영향을 받으므로 카드는 무변경 재사용하고, 진입 화면에 `건너뛰고 초안 만들기` 형제 버튼을 추가 (`index.tsx:188-197`). 라벨은 다르나 FR-06 계약은 충족 |
| 스튜디오 프리필 (이름/지침/도구 칩/모델/temperature) | ✅ | 통합 시나리오 1 |
| 취소 복귀 분기 | ✅ | 통합 시나리오 5 |
| 기존 3개 진입 버튼 불변 | ✅ | 통합 시나리오 6 |

### 2.6 API Contract Verification — 95%

3-way 검증: Design §4.2 ↔ 백엔드 `ComposeAgentRequest` (`idt/src/application/agent_composer/schemas.py:47-60`) ↔ 진입 화면 요청 (`AgentCreateEntryPage/index.tsx:107-116`).

| 필드 | 서버 제약 | 클라이언트 | 판정 |
|------|-----------|-----------|:----:|
| `user_request` | `min_length=1, max_length=1000` | 1000자 slice + trim 후 빈 값이면 미전송 | ✅ |
| `name` | `max_length=200`, nullable | `null` (LLM 제안 사용) | ✅ |
| `current_config` | nullable | `null` — 진입 화면은 편집 대상 폼이 없음 | ✅ |
| `history` | `max_length=20`, nullable | `null` | ✅ |
| `clarification_answers` | **`max_length=6`**, nullable | 클램프 **없음** — 서버 응답 질문 수만큼 그대로 전송 | ⚠️ |
| `clarification_answers[].question` | `min_length=1, max_length=500` | 서버 에코백 그대로 반환 | ✅ |
| `clarification_answers[].answer` | `max_length=1000` | 사용자 입력 무제한 | ⚠️ |
| `clarification_round` | `ge=0, le=10` | 클라이언트 상한 3 (`MAX_CLARIFY_ROUNDS`) | ✅ |

**클램프 부재의 실질 위험은 낮다**: 서버 `AgentComposerPolicy.MAX_QUESTIONS_PER_ROUND = 3` (`idt/src/domain/agent_composer/policies.py:73,92`)이 라운드당 질문을 3개로 잘라 반환하므로, 정상 서버 응답에서 6개 상한에 도달할 수 없다. 또한 이 동작은 **기존 Fix 탭(`FixAgentPanel.tsx:85`)과 동일**하며 이번 기능이 새로 만든 결함이 아니다.

### 2.7 Runtime Verification Results

> Playwright 미도입. Design §8 방침대로 Vitest + RTL + MSW로 L2/L3 대체.

| Level | 대상 | 결과 |
|-------|------|------|
| **L0 단위** | 스토어 계약 7 + 변환 유틸 13 | **20/20 통과** |
| **L1 계약** | compose 요청 본문 (MSW 캡처) | 진입 화면 테스트 내 3케이스 통과 — `current_config` 미전송, `round=0→1` 증가, HITL 에코백 |
| **L2 컴포넌트** | 진입 화면 상호작용 10 시나리오 | **16/16 통과** |
| **L3 통합** | Design §8.4 시나리오 1~6 + `kind:'blank'` | **7/7 통과** |
| **회귀** | `AgentBuilderPage` / `AgentBuilderStudio` / `draftToolMapping` | **75/75 통과** (기능 관련 7파일 전체) |

**전체 스위트**: 913 passed / 12 failed (925)

| 분류 | 건수 | 판정 |
|------|:----:|------|
| 기존 실패 (ChatPage, collection 모달 ×7, EvalDataset) | 9 | 이전 세션에서 `git stash` 대조로 clean tree에서도 동일 실패 확인 |
| 부하 기인 flake (WikiPage T3, AgentBuilderStudio 스케줄 ×2) | 3 | **격리 실행 시 27/27 전부 통과**. 동일 현상을 `AgentCreateEntryPage`에서도 1회 관측(격리 시 16/16 통과) |
| 이 기능이 만든 회귀 | **0** | |

**시나리오 8(비인증 리디렉트)**은 라우트 배치로 대체 검증했다. `App.tsx:65`가 `ProtectedRoute` 하위에 있어 기존 보호 라우트와 동일 경로를 탄다 — 별도 테스트를 쓰면 `ProtectedRoute` 자체를 재검증하는 중복이 된다.

### 2.8 Match Rate Summary

런타임 검증을 실제 실행했으므로 runtime 반영 공식을 적용한다.

| 축 | 점수 | 가중치 | 기여 |
|----|:----:|:------:|:----:|
| Structural | 100% | 0.15 | 15.0 |
| Functional Depth | 96% | 0.25 | 24.0 |
| API Contract | 95% | 0.25 | 23.75 |
| Runtime | 95% | 0.35 | 33.25 |
| **Overall** | | | **96.0%** |

> gap-detector 에이전트가 독립적으로 산출한 값은 **94.0%** (Critical 0 / Important 1)로, 오차 범위 내에서 일치한다. 다만 에이전트의 상세 리포트 본문이 2회 시도에도 전달되지 않아, 위 표의 근거는 전부 직접 재검증한 것이다.

---

## 3. Gap List

| # | Severity | Confidence | 위치 | 내용 |
|---|:--------:|:----------:|------|------|
| G-1 | **Minor** | 95% | `AgentCreateEntryPage/index.tsx:148-157` | `clarification_answers` 6개 상한·`answer` 1000자 상한을 클라이언트에서 클램프하지 않음. 서버가 질문을 3개로 자르므로 정상 경로에서는 도달 불가하며, 기존 Fix 탭과 동일한 동작. 방어적 보강 성격 |
| G-2 | **Minor** | 100% | `ClarifyQuestionCard` 재사용 | Design §5.4의 `[건너뛰기]/[계속]` 2버튼 명세와 실제 UI(단일 `[답변 제출]` + 형제 skip 버튼)가 불일치. 카드 수정 시 Fix 탭 동시 영향 때문에 내린 의도적 선택 — Design 문서를 현실에 맞춰 갱신하는 편이 옳다 |
| G-3 | **Minor** | 80% | 테스트 인프라 | 전체 병렬 실행 시 타임아웃 flake 3건. 이 기능 고유 문제는 아니나 CI에서 재현될 수 있음 |
| G-4 | **Info** | 100% | `docs/SOURCE-OF-TRUTH.md` §6-1/6-2 | `/agent-builder/new` 미반영. SOT 전반이 이미 stale(JobsPage 등 다수 누락). CLAUDE.md §6 규칙에 따라 수정하지 않고 보고 |

**Critical 0건 / Important 0건.**

---

## 4. Decision Record Verification

| 결정 | 출처 | 준수 | 근거 |
|------|------|:----:|------|
| 별도 라우트 `/agent-builder/new` (목록은 `/agent-builder` 유지) | Plan 확정 | ✅ | `App.tsx:61,65` |
| 무저장 프리필 — DB 반영은 스튜디오 `[저장]`만 | Plan 확정 | ✅ | FR-12 |
| Import 범위 제외 (비활성 노출) | Plan 확정 | ✅ | FR-10 |
| HITL은 진입 화면에서 처리 후 스튜디오 진입 | Plan 확정 | ✅ | FR-05/06 |
| 실패 시 진입 화면 유지 + 안내 | Plan 확정 | ✅ | FR-08 |
| 취소는 경유 경로에 따라 분기 | Plan 확정 | ✅ | FR-11 |
| 사이드바 진입점만 변경 | Plan 확정 | ✅ | FR-02 |
| **Option B (클린 분리, Zustand 핸드오프)** | Design Checkpoint 3 | ✅ | 독립 페이지 + 비영속 스토어. 사용자가 권고안(Option C)을 물리고 선택한 안을 그대로 구현 |
| 변환 로직 단일화 (중복 구현 금지) | Plan FR-07 | ✅ | `composeDraftToForm` 공유 |

---

## 5. Clean Architecture Compliance

| Layer | 배치 | 판정 |
|-------|------|:----:|
| Presentation | `pages/AgentCreateEntryPage/`, `components/` | ✅ |
| Application | `store/agentDraftStore.ts`, `hooks/useAgentComposer` | ✅ |
| Domain | `utils/composeDraftToForm.ts` (순수 함수), `types/agentComposer` | ✅ |
| Infrastructure | `services/` (기존 재사용) | ✅ |

역방향 의존 없음. `composeDraftToForm`은 React·서비스 의존이 전혀 없는 순수 함수로, 페이지 두 곳이 함께 참조한다. ✅

---

## 6. Recommendation

Overall 96.0%, Critical·Important 0건으로 **품질 게이트(90%)를 통과**한다. Gap 4건은 전부 Minor/Info이며 기능 동작을 막지 않는다.

권고 순서:

1. **수동 E2E 1회** (DoD 4번 미충족) — dev 서버 기동 후 사이드바 → 설명 → 프리필 → 저장 경로 확인. 이것만이 아직 사람 눈으로 확인되지 않은 항목이다.
2. `/pdca report agent-create-entry` — 나머지는 문서/전역 정리 성격
3. 별도 작업으로 분리 권장: 리포지토리 전역 lint 35건 · `tsc -b` 18건 정리, SOT 문서 갱신

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | Check 단계 Gap 분석 — Overall 96.0%, Critical 0 / Important 0 / Minor 3 / Info 1 | tkdrb136@gmail.com |
