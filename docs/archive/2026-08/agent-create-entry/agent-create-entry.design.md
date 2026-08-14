---
template: design
version: 1.3
feature: agent-create-entry
---

# agent-create-entry Design Document

> **Summary**: `/agent-builder/new` 진입 화면에서 자연어 설명 → 기존 compose API 초안 → Zustand 휘발성 스토어를 통해 스튜디오 폼에 프리필 진입.
>
> **Project**: sangplusbot (idt_front)
> **Author**: tkdrb136@gmail.com
> **Date**: 2026-08-12
> **Status**: Draft
> **Planning Doc**: [agent-create-entry.plan.md](../../01-plan/features/agent-create-entry.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 3 | 참조 시안 `docs/img/create_agent.png` | ✅ |
| Phase 4 | API 신규 없음 (기존 `POST /api/v1/agents/compose` 재사용) | N/A |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 생성 진입점이 빈 폼이라 초보 사용자가 막히고, 이미 구현된 자연어 조합(compose+HITL)이 스튜디오 내부 탭에 묻혀 있다 |
| **WHO** | P2(에이전트 소유자/KB 운영자) 중 **처음 에이전트를 만드는 사용자**. 기존 숙련 사용자 경로는 무변경 |
| **RISK** | 진입 화면(라우트)과 스튜디오(`AgentBuilderPage` 내부 `view` 상태) 사이의 **초안 전달** — 상태 유실 또는 이중 소스 시 기존 저장 경로까지 파손 |
| **SUCCESS** | 사이드바 `+새 에이전트` → 설명 1문장 → (필요 시 HITL 1라운드) → 이름/지침/도구/모델이 채워진 스튜디오 도달. 기존 회귀 0건 |
| **SCOPE** | 프론트 전용 3모듈: (1) 스토어+유틸 추출, (2) 진입 화면, (3) 라우트 배선. Import는 UI만 비활성 |

---

## 1. Overview

### 1.1 Design Goals

1. **기존 자산 재사용 최대화** — compose API·`ClarifyQuestionCard`·초안→폼 변환 로직을 새로 만들지 않는다.
2. **핸드오프의 생명주기를 명시적으로 봉인** — 초안은 휘발성이며 "1회 소비 후 소멸"이 계약이다. 유령 초안이 다음 세션에 되살아나는 경로를 설계 수준에서 차단한다.
3. **기존 경로 무변경** — 목록/편집/저장/Fix 탭은 코드 경로가 바뀌지 않는다. 바뀌는 것은 진입점 1개(`AppSidebar.tsx:97`)뿐이다.
4. **단일 변환 구현** — 초안→폼 변환은 한 곳에만 존재하고 Fix 탭과 진입 화면이 공유한다.

### 1.2 Design Principles

- **Consume-once**: 스토어 값은 읽는 즉시 비워진다. 읽기와 비우기는 원자적 1회 호출.
- **No persistence**: `persist` 미들웨어를 쓰지 않는다. 새로고침 = 초안 소멸(정상 동작).
- **No render-time subscription**: 핸드오프 값은 selector로 구독하지 않고 `getState()`로만 읽는다 (구독 시 소비→리렌더→재소비 루프 위험).
- **Dependency-gated apply**: 도구 카탈로그·모델 목록이 도착하기 전에는 변환을 실행하지 않는다 (기존 edit prime 패턴과 동일).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | `AgentBuilderPage`에 `view='entry'` 추가 | 별도 페이지 + Zustand 핸드오프 스토어 + 유틸 추출 | 별도 페이지 + router `state` 핸드오프 |
| **New Files** | 1 | 4 | 3 |
| **Modified Files** | 3 | 4 | 3 |
| **Complexity** | Low | Medium | Medium |
| **Maintainability** | Low (640줄 페이지 비대화) | High | Medium-High |
| **Effort** | Low | Medium | Medium |
| **Risk** | Low (단, URL↔화면 불일치) | Low (스토어 생명주기 관리 필요) | Low |
| **URL 정확성** | ✗ | ✓ | ✓ |

**Selected**: **Option B (클린 분리)** — **Rationale**: 진입 화면을 독립 페이지로 두어 단위 테스트가 쉬워지고, 향후 `에이전트 가져오기(Import)`가 같은 핸드오프 경로(파일 → 초안 → 스튜디오)를 그대로 재사용할 수 있다. 유일한 약점인 "유령 초안 잔존"은 §2.4 생명주기 계약(G1~G5)으로 봉합한다.

### 2.1 Component Diagram

```
┌──────────────────────────────┐
│ AppSidebar                   │
│  [+ 새 에이전트]              │ ─── navigate('/agent-builder/new')
└──────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────┐
│ AgentCreateEntryPage      (/agent-builder/new)       │
│  ├ Hero                                              │
│  ├ DescriptionComposer  ── useComposeAgent ──────────┼──▶ POST /api/v1/agents/compose
│  ├ ClarifyQuestionCard  (재사용, needs_clarification) │      (기존 · 무변경)
│  ├ ComposeFailureCard   (coverage=none / error)      │
│  └ EntryActionCards     [직접 만들기] [가져오기(disabled)]│
└──────────────────────────────────────────────────────┘
                │ setPendingIntent({kind, draft?})
                ▼
        ┌────────────────────────────┐
        │ agentDraftStore (Zustand)  │  휘발성 · 비영속 · 소비 1회
        │  pendingIntent | null      │
        └────────────────────────────┘
                │ consumePendingIntent()  (mount effect, 의존 쿼리 settled 후)
                ▼
┌──────────────────────────────────────────────────────┐
│ AgentBuilderPage          (/agent-builder)           │
│  view: 'list' | 'create' | 'edit'   ← 기존 그대로     │
│  setForm(composeDraftToForm(draft, DEFAULT_FORM, …)) │
│  setView('create')                                   │
└──────────────────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        │ StudioLayout   │ ← Fix 탭도 동일 util 사용
        └────────────────┘
```

### 2.2 Data Flow

```
설명 입력
  └▶ compose(user_request)
       ├─ status='needs_clarification'
       │    └▶ ClarifyQuestionCard → 답변/건너뛰기
       │         └▶ compose(user_request, clarification_answers, round+1)   ← 진입 화면 내 루프
       ├─ status='draft' & coverage!=='none'
       │    └▶ setPendingIntent({kind:'draft', draft})
       │         └▶ navigate('/agent-builder')
       │              └▶ [쿼리 settled] consumePendingIntent()
       │                   └▶ setForm(composeDraftToForm(...)) + setView('create')
       │                        └▶ 사용자 검토 → [저장] → POST /api/v1/agents   ← 여기서만 DB 반영
       └─ coverage='none' | 4xx/5xx | network
            └▶ ComposeFailureCard (진입 화면 유지)
                 ├ [다시 설명하기] → 입력 초기화
                 └ [그래도 직접 만들기] → setPendingIntent({kind:'blank'}) → navigate
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AgentCreateEntryPage` | `useComposeAgent`, `agentDraftStore`, `ClarifyQuestionCard` | 초안 생성 + HITL + 핸드오프 적재 |
| `AgentBuilderPage` | `agentDraftStore`, `composeDraftToForm`, `useToolCatalog`, `useLlmModels` | 핸드오프 소비 + 폼 프리필 |
| `composeDraftToForm` | `mapDraftToolIdsToCatalog`, `DEFAULT_RAG_CONFIG` | 초안 → 폼 변환 (단일 구현) |
| `FixAgentPanel`(기존) | `composeDraftToForm` (간접, `onApplyDraft` 경유) | 동일 변환 공유 |

### 2.4 핸드오프 생명주기 계약 (Option B 리스크 봉합)

> 선택안의 유일한 약점은 "유령 초안 잔존"이다. 아래 5개 규칙을 **구현 필수 조건**으로 못 박는다.

| ID | 규칙 | 이유 | 검증 |
|----|------|------|------|
| **G1** | `persist` 미들웨어 **금지**. localStorage/sessionStorage 미사용 | 새로고침·재로그인 후 옛 초안 부활 차단 | 코드 리뷰 + 스토어 테스트 |
| **G2** | `consumePendingIntent()`는 값을 반환하면서 **같은 호출 안에서** `null`로 set (원자적) | 읽기/비우기 분리 시 중간에 재진입하면 이중 적용 | 스토어 단위 테스트: 2회 연속 호출 시 2번째는 `null` |
| **G3** | `AgentCreateEntryPage` mount 시 `clearPendingIntent()` 호출 | 스튜디오에서 뒤로가기로 재진입했을 때 잔여 값 제거 | 컴포넌트 테스트 |
| **G4** | `AgentBuilderPage`의 소비는 **mount effect 1회 + ref 가드**. selector 구독 금지, `getState()`로만 접근 | 렌더 중 구독 시 소비→리렌더→재소비 루프 | 컴포넌트 테스트: 리렌더 후 폼 유지(재적용 없음) |
| **G5** | 소비는 `catalogTools`·`models` 쿼리가 **settled된 뒤에만** 실행 (`isToolsLoading \|\| isModelsLoading` 가드) | 로딩 중 변환 시 도구 매핑·모델 역매핑이 조용히 실패 | 컴포넌트 테스트: 쿼리 지연 시에도 도구 칩이 반영됨 |

> G5는 기존 편집 프라임 로직(`index.tsx:97-103`, `primedAgentRef`)이 이미 쓰는 패턴이다. 동일 패턴을 초안 적용에도 적용해 일관성을 유지한다.

---

## 3. Data Model

### 3.1 스토어 상태

```typescript
// src/store/agentDraftStore.ts
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';

/** 진입 화면 → 스튜디오로 넘기는 1회성 의도. 'blank'는 빈 폼으로 시작. */
export type AgentCreateIntent =
  | { kind: 'draft'; draft: ComposeAgentDraftResponse }
  | { kind: 'blank' };

interface AgentDraftState {
  /** 소비 대기 중인 의도. 소비 즉시 null. 절대 persist 하지 않는다 (G1). */
  pendingIntent: AgentCreateIntent | null;
  setPendingIntent: (intent: AgentCreateIntent) => void;
  /** 읽기+비우기 원자적 1회 (G2). 없으면 null. */
  consumePendingIntent: () => AgentCreateIntent | null;
  clearPendingIntent: () => void;
}
```

### 3.2 변환 유틸 시그니처

```typescript
// src/utils/composeDraftToForm.ts
export interface DraftToFormDeps {
  catalogTools?: ToolCatalogItem[];
  models?: LlmModel[];
}

/**
 * 초안 → 폼 변환 (단일 구현).
 * 기존 AgentBuilderPage.handleApplyDraft(index.tsx:371) 본문을 그대로 이관한 것으로,
 * 도구 ID 매핑 · 빌트인 제외 · RAG 기본설정 · 문서추출기/생성기 드래프트 정리 ·
 * 모델 역매핑 실패 시 기존 모델 유지 규칙을 모두 보존한다.
 */
export const composeDraftToForm = (
  draft: ComposeAgentDraftResponse,
  prev: AgentBuilderFormData,
  deps: DraftToFormDeps,
): AgentBuilderFormData => { /* ... */ };
```

### 3.3 진입 화면 로컬 상태

```typescript
// AgentCreateEntryPage 내부 (compose 무저장 원칙 — FixAgentPanel과 동일 정책)
const [input, setInput] = useState('');
const [questions, setQuestions] = useState<ClarifyingQuestion[] | null>(null);
const [planSummary, setPlanSummary] = useState('');
const [pendingClarify, setPendingClarify] =
  useState<{ userRequest: string; round: number } | null>(null);
const [failure, setFailure] =
  useState<{ reason: 'coverage_none' | 'api_error'; message: string;
             missing: ComposeMissingCapability[] } | null>(null);
```

### 3.4 DB 스키마

**변경 없음.** compose는 무저장이며 저장은 기존 `POST /api/v1/agents` 경로 그대로다.

---

## 4. API Specification

### 4.1 사용 엔드포인트 (전부 기존 · 변경 없음)

| Method | Path | 용도 | Auth |
|--------|------|------|------|
| POST | `/api/v1/agents/compose` | 자연어 → 초안 (무저장) + HITL 질문 | Required |
| POST | `/api/v1/agents` | 최종 저장 (스튜디오 `[저장]`) | Required |
| GET | `/api/v1/tools` (카탈로그) | 도구 ID 매핑용 | Required |
| GET | LLM 모델 목록 | 모델 역매핑용 | Required |

### 4.2 진입 화면의 compose 요청 규약

Fix 탭과 달리 **편집 대상 폼이 없으므로** `current_config`는 보내지 않는다.

```jsonc
// 1차 요청
{
  "user_request": "사내 규정 문서를 찾아 답해주는 봇",
  "name": null,              // LLM 제안 이름 사용
  "current_config": null,    // 진입 화면 = 빈 폼 (Fix 탭과의 차이)
  "history": null,
  "clarification_round": 0
}

// HITL 2차 요청 (같은 엔드포인트, stateless 재구성)
{
  "user_request": "사내 규정 문서를 찾아 답해주는 봇",   // 원 문장 그대로 재전송
  "clarification_answers": [
    { "question_id": "q1", "question": "어떤 문서를 참조하나요?", "answer": "지식베이스 A" }
  ],
  "clarification_round": 1
}
```

**클라이언트 제약**: `user_request` 1~1000자(서버 `max_length=1000`과 동일), `clarification_answers` 최대 6개, `clarification_round` 상한 3(서버 상한 10보다 보수적 — 무한 질문 루프 방지).

### 4.3 응답 분기

| 조건 | 처리 |
|------|------|
| `status='needs_clarification'` | 질문 카드 렌더, `pendingClarify = {userRequest, round+1}` |
| `status='draft'` && `coverage!=='none'` | `setPendingIntent({kind:'draft', draft})` → `navigate('/agent-builder')` |
| `status='draft'` && `coverage==='none'` | `ComposeFailureCard(reason='coverage_none')` — `missing_capabilities`·`notes` 표시 |
| HTTP 4xx/5xx/네트워크 | `ComposeFailureCard(reason='api_error')` — 에러 메시지 + 재시도 |
| `clarification_round > 3` | 질문 무시하고 실패 카드로 강하 (탈출구 보장) |

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│                        ✿ (로고)                          │
│                                                         │
│           생성하려는 에이전트에 대해 알려주세요              │
│    원하는 에이전트가 무엇을 하길 원하는지 설명해 주시면,      │
│              단계별로 안내해 드리겠습니다                   │
│                                                         │
│   ┌─────────────────────────────────────────────────┐   │
│   │ 구축하려는 에이전트에 대해 설명해 주세요            │   │
│   │                                                 │   │
│   │ ───────────────────────────────────────────     │   │
│   │                                          (▷)    │   │
│   └─────────────────────────────────────────────────┘   │
│                                                         │
│   ┌───────────────────────┐ ┌───────────────────────┐   │
│   │         ✎             │ │         ⬆             │   │
│   │   에이전트 직접 만들기    │ │    에이전트 가져오기     │   │
│   └───────────────────────┘ └───────────────────────┘   │
│                                     (준비 중 · disabled) │
└─────────────────────────────────────────────────────────┘
```

전송 후(HITL/실패)에는 입력 카드와 액션 카드 **사이**에 질문/실패 카드가 삽입된다. 히어로·입력창은 유지된다.

### 5.2 User Flow

```
사이드바 [+새 에이전트]
  → /agent-builder/new
      ├ 설명 입력 → ▷
      │    ├ (질문) 답변/건너뛰기 → 재요청
      │    ├ (성공) → /agent-builder · 스튜디오 프리필 → [저장]
      │    └ (실패) 안내 → [다시 설명하기] | [그래도 직접 만들기]
      ├ [에이전트 직접 만들기] → /agent-builder · 빈 스튜디오
      └ [에이전트 가져오기] → (동작 없음, 준비 중)

스튜디오 [취소] → origin==='entry' ? /agent-builder/new : 목록
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AgentCreateEntryPage` | `src/pages/AgentCreateEntryPage/index.tsx` | 화면 조립, compose 호출, HITL 루프, 핸드오프 적재 |
| `EntryHero` | `.../components/EntryHero.tsx` | 로고 + 타이틀 + 서브카피 (정적) |
| `DescriptionComposer` | `.../components/DescriptionComposer.tsx` | textarea + 전송 버튼 + 글자수/로딩/비활성 |
| `EntryActionCards` | `.../components/EntryActionCards.tsx` | 직접 만들기 / 가져오기(disabled) 카드 2개 |
| `ComposeFailureCard` | `.../components/ComposeFailureCard.tsx` | coverage=none·에러 안내 + 2개 액션 |
| `ClarifyQuestionCard` | `src/components/agent-builder/fix/` (기존) | HITL 질문 — **재사용, 무변경** |
| `agentDraftStore` | `src/store/agentDraftStore.ts` | 1회성 핸드오프 |
| `composeDraftToForm` | `src/utils/composeDraftToForm.ts` | 초안 → 폼 변환 (추출) |

### 5.4 Page UI Checklist

#### AgentCreateEntryPage (`/agent-builder/new`)

- [ ] 로고: 상단 중앙 그라디언트 아이콘 (기존 violet→indigo 토큰 재사용)
- [ ] 제목: "생성하려는 에이전트에 대해 알려주세요" (violet 계열, bold)
- [ ] 서브카피: "원하는 에이전트가 무엇을 하길 원하는지 설명해 주시면, 단계별로 안내해 드리겠습니다"
- [ ] Textarea: placeholder "구축하려는 에이전트에 대해 설명해 주세요", `aria-label` 부여, 최대 1000자
- [ ] 전송 버튼: 원형 ▷ 아이콘, 우하단 배치, 공백 입력 또는 요청 중이면 `disabled`
- [ ] 키보드: Enter 전송 / Shift+Enter 줄바꿈 (FixAgentPanel과 동일 규약)
- [ ] 로딩 표시: 요청 중 점 3개 애니메이션 + `aria-label="초안 생성 중"`
- [ ] 카드: "에이전트 직접 만들기" — ✎ 아이콘, 클릭 시 빈 스튜디오
- [ ] 카드: "에이전트 가져오기" — ⬆ 아이콘, `disabled` + "준비 중" 표기 + `aria-disabled="true"`
- [ ] 질문 카드(조건부): `ClarifyQuestionCard` — 선택지·자유입력·[건너뛰기]/[계속]
- [ ] 실패 카드(조건부): 사유 문구 + `missing_capabilities` 목록(capability/reason/suggestion) + [다시 설명하기] + [그래도 직접 만들기]
- [ ] 글자수 초과 시 입력 차단(1000자 slice)

#### AgentBuilderPage (`/agent-builder`) — 변경분만

- [ ] 초안 소비 후 create 스튜디오 진입 시 이름/지침/도구 칩/모델/temperature가 채워져 있음
- [ ] `[취소]`: 진입 화면 경유 시 `/agent-builder/new`로, 그 외 목록으로
- [ ] 목록 헤더 `+새 에이전트`, 목록 빈 상태 버튼은 **기존대로** 빈 스튜디오 직행

---

## 6. Error Handling

### 6.1 오류 분류

| 상황 | 원인 | 처리 | 사용자 문구 |
|------|------|------|-------------|
| `coverage='none'` | 요청을 충족할 도구/능력 없음 | 진입 화면 유지 + 실패 카드 | "이 요청을 충족할 도구가 없습니다" + missing 목록 |
| 422 | `user_request` 검증 실패 | 실패 카드 + 입력 유지 | "설명을 다시 확인해 주세요" |
| 401 | 세션 만료 | 기존 axios 인터셉터의 로그인 리디렉트에 위임 | — |
| 5xx / 네트워크 | 서버·LLM 오류 | 실패 카드 + 재시도 | "초안 생성에 실패했습니다: {message}" |
| `round > 3` | 질문 루프 | 질문 무시하고 실패 카드 | "요청을 더 구체적으로 적어 주세요" |
| 도구/모델 카탈로그 로드 실패 | 부수 쿼리 실패 | 초안 적용은 진행하되 매핑 실패분은 기존 폴백(모델 미변경) | 스튜디오의 기존 재시도 UI 사용 |

### 6.2 실패 시 상태 보존

실패해도 `input`은 지우지 않는다. 사용자가 문장을 수정해 재전송할 수 있어야 한다. `[다시 설명하기]`는 실패 카드만 닫고 textarea에 포커스한다.

---

## 7. Security Considerations

- [x] 인증: `/agent-builder/new`는 `ProtectedRoute` 하위 배치 — 비인증 접근 시 로그인 리디렉트
- [x] 입력 검증: 클라이언트 1000자 제한 + 서버 pydantic `max_length=1000` 이중 방어
- [x] XSS: 초안 문자열은 React 기본 이스케이프로 렌더 (`dangerouslySetInnerHTML` 사용 금지)
- [x] 데이터 노출: 초안은 DB 미저장·비영속 스토어 — 브라우저 스토리지에 잔존하지 않음 (G1)
- [x] 권한: 저장 시점의 권한 검사는 기존 `POST /api/v1/agents` 그대로

---

## 8. Test Plan

> 이 프로젝트는 Playwright 미도입. L2/L3는 **Vitest + RTL + MSW**로 대체 수행한다.
> 백엔드 무변경이므로 L1은 신규 작성 대신 기존 compose 계약 준수 확인으로 한정한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: API 계약 | compose 요청 페이로드가 서버 스키마와 일치 | MSW 요청 검증 | Do |
| L2: 컴포넌트 액션 | 진입 화면 요소·상호작용 | Vitest + RTL | Do |
| L3: 통합 시나리오 | 진입 → 핸드오프 → 스튜디오 프리필 | Vitest + RTL (MemoryRouter) | Do |
| L0: 단위 | 스토어 계약, 변환 유틸 | Vitest | Do |

### 8.2 L1: API 계약 시나리오

| # | 검증 대상 | 기대 |
|---|-----------|------|
| 1 | 1차 compose 요청 본문 | `user_request` 존재, `current_config` 미전송(null), `clarification_round=0` |
| 2 | HITL 2차 요청 본문 | 원 `user_request` 동일, `clarification_answers[].question_id/question/answer` 포함, `round=1` |
| 3 | 1000자 초과 입력 | 전송 전 클라이언트에서 slice — 서버 422 유발 안 함 |
| 4 | 저장 요청 | 진입 화면 경유해도 `POST /api/v1/agents` 페이로드가 기존과 동일 |

### 8.3 L2: 컴포넌트 액션 시나리오

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | 페이지 로드 | §5.4 체크리스트 요소 전부 렌더, 전송 버튼 disabled |
| 2 | 공백만 입력 | 전송 버튼 여전히 disabled |
| 3 | 문장 입력 + ▷ | compose 호출 1회, 로딩 표시, 중복 클릭 무시 |
| 4 | `needs_clarification` 응답 | 질문 카드 표시, 초안 미적용 |
| 5 | 질문 답변 + [계속] | `round=1`로 재호출 |
| 6 | [건너뛰기] | 빈 answer로 재호출 |
| 7 | `coverage='none'` 응답 | 실패 카드 표시 + 라우팅 발생 안 함 |
| 8 | compose 500 | 실패 카드 + input 보존 |
| 9 | [에이전트 직접 만들기] | `pendingIntent={kind:'blank'}` 적재 후 `/agent-builder` 이동 |
| 10 | [에이전트 가져오기] | `disabled`, 클릭해도 라우팅·상태 변화 없음 |

### 8.4 L3: 통합 시나리오

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 초안 프리필 | 설명 입력 → draft 응답 → `/agent-builder` | create 뷰, 이름/지침/도구 칩/모델 반영 |
| 2 | 쿼리 지연 내성 (G5) | 도구·모델 쿼리를 지연시킨 뒤 초안 소비 | 지연 해제 후 도구 칩이 정상 반영 |
| 3 | 소비 1회 (G2/G4) | 초안 소비 후 강제 리렌더 | 폼 유지, 재적용·초기화 없음 |
| 4 | 유령 초안 (G3) | 초안 적재 → 스튜디오 → 뒤로가기 → 진입 화면 재진입 → 직접 만들기 | 빈 폼으로 진입 (옛 초안 미적용) |
| 5 | 취소 복귀 (FR-11) | 진입 경유 스튜디오에서 [취소] | `/agent-builder/new`로 이동 |
| 6 | 회귀 — 기존 경로 | 목록 헤더 `+새 에이전트` 클릭 | 빈 스튜디오 직행 (라우팅 변화 없음) |
| 7 | 회귀 — Fix 탭 | 스튜디오 Fix 탭에서 초안 적용 | 리팩터 이전과 동일 결과 (기존 테스트 통과) |
| 8 | 비인증 접근 | 로그아웃 상태로 `/agent-builder/new` | 로그인 페이지 리디렉트 |

### 8.5 Seed Data Requirements

| Entity | Minimum | Key Fields |
|--------|:------:|------------|
| MSW compose 핸들러 | 4 variant | `draft`(정상), `needs_clarification`, `coverage:'none'`, 500 에러 |
| 도구 카탈로그 mock | 기존 재사용 | `tool_id`, `is_builtin` |
| LLM 모델 mock | 기존 재사용 | `id`, `model_name`, `is_default` |

> 기존 `__tests__/mocks/handlers.ts:993`의 compose 핸들러를 기본값으로 두고, 시나리오별 override는 각 테스트에서 `server.use()`로 주입한다 (기존 테스트 관례와 동일).

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Presentation | 페이지·컴포넌트 | `src/pages/`, `src/components/` |
| Application | 훅·스토어(오케스트레이션) | `src/hooks/`, `src/store/` |
| Domain | 타입·순수 변환 | `src/types/`, `src/utils/` |
| Infrastructure | API 클라이언트 | `src/services/` |

### 9.2 Dependency Rules

```
Presentation ──→ Application ──→ Domain ←── Infrastructure
   (Page)          (hook/store)    (types/utils)   (service)

규칙: Domain(composeDraftToForm)은 React·라우터·스토어를 import 하지 않는다 (순수 함수).
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `AgentCreateEntryPage` + 하위 컴포넌트 | Presentation | `src/pages/AgentCreateEntryPage/` |
| `agentDraftStore` | Application | `src/store/agentDraftStore.ts` |
| `useComposeAgent` (기존) | Application | `src/hooks/useAgentComposer.ts` |
| `composeDraftToForm` | Domain (순수 함수) | `src/utils/composeDraftToForm.ts` |
| `agentComposerService` (기존) | Infrastructure | `src/services/agentComposerService.ts` |

---

## 10. Coding Convention Reference

### 10.1 이 기능의 규약

| Item | 적용 |
|------|------|
| 컴포넌트 파일 | PascalCase.tsx, 페이지는 `PascalCase/index.tsx` |
| 유틸 파일 | camelCase.ts, named export |
| 스토어 파일 | `src/store/{name}Store.ts`, `use{Name}Store` 훅 export (기존 `chatPreferencesStore` 패턴) |
| 스타일 | Tailwind — violet-600 primary, `rounded-2xl` 카드, `shadow-sm` (기존 AgentBuilder 톤 일치) |
| 주석 | 설계 근거는 `// Design §N` 형식으로 표기 (기존 `// fix-agent-composer FR-05` 관례 계승) |
| 테스트 | 구현 파일과 같은 디렉토리에 `*.test.ts(x)` |

### 10.2 Design 참조 주석 규칙 (Do 단계 필수)

```typescript
// Design §2.4 G2 — 읽기와 비우기는 원자적 1회 (분리 시 이중 적용)
consumePendingIntent: () => {
  const cur = get().pendingIntent;
  if (cur) set({ pendingIntent: null });
  return cur;
},
```

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt_front/src/
├── App.tsx                                   [수정] + /agent-builder/new
├── components/layout/AppSidebar.tsx          [수정] :97 목적지 변경
├── store/
│   ├── agentDraftStore.ts                    [신규]
│   └── agentDraftStore.test.ts               [신규]
├── utils/
│   ├── composeDraftToForm.ts                 [신규 · handleApplyDraft 본문 이관]
│   └── composeDraftToForm.test.ts            [신규]
├── pages/
│   ├── AgentCreateEntryPage/
│   │   ├── index.tsx                         [신규]
│   │   ├── index.test.tsx                    [신규]
│   │   └── components/
│   │       ├── EntryHero.tsx                 [신규]
│   │       ├── DescriptionComposer.tsx       [신규]
│   │       ├── EntryActionCards.tsx          [신규]
│   │       └── ComposeFailureCard.tsx        [신규]
│   └── AgentBuilderPage/index.tsx            [수정] 소비 effect + 취소 분기 + util 위임
└── __tests__/mocks/handlers.ts               [수정] compose variant 핸들러
```

### 11.2 Implementation Order

1. [ ] `agentDraftStore` 테스트 작성 → 구현 (G1/G2 계약)
2. [ ] `composeDraftToForm` 테스트 작성 → `handleApplyDraft` 본문 이관 → `handleApplyDraft`를 래퍼로 축소
3. [ ] **기존 테스트 전량 재실행** (Fix 탭 회귀 확인) — 여기서 초록이 아니면 다음으로 진행 금지
4. [ ] `AgentCreateEntryPage` 하위 컴포넌트 (Hero / Composer / ActionCards / FailureCard)
5. [ ] `AgentCreateEntryPage` 조립 — compose 호출 + HITL 루프 + 실패 분기 + 핸드오프 적재
6. [ ] `App.tsx` 라우트 + `AppSidebar` 목적지 변경
7. [ ] `AgentBuilderPage` 소비 effect (G3/G4/G5) + 취소 복귀 분기
8. [ ] MSW variant 핸들러 + L3 통합 테스트
9. [ ] lint / tsc / 전체 테스트

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 핸드오프 기반 | `module-1` | `agentDraftStore` + `composeDraftToForm` 추출 + 기존 회귀 확인 (구현 순서 1~3) | 12-18 |
| 진입 화면 | `module-2` | `AgentCreateEntryPage` + 하위 컴포넌트 4종 + compose/HITL/실패 (4~5) | 25-35 |
| 배선·통합 | `module-3` | 라우트·사이드바·소비 effect·취소 분기·MSW·통합 테스트 (6~9) | 20-30 |

> `module-1`은 **반드시 먼저** 끝내고 기존 테스트가 초록인 것을 확인한다. 이 모듈이 기존 Fix 탭 동작을 건드리는 유일한 지점이라, 여기서 회귀를 잡지 못하면 이후 모듈에서 원인 추적이 어려워진다.

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 40-50 |
| Session 3 | Do | `--scope module-3` | 20-30 |
| Session 4 | Check + Report | 전체 | 30-40 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-12 | 초안 작성 — Option B(클린 분리) 선택, 핸드오프 생명주기 계약 G1~G5 정의 | tkdrb136@gmail.com |
