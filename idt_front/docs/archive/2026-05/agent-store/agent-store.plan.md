# Agent Store (에이전트 스토어)

> 공개된 에이전트 템플릿을 탐색하고, 구독/포크하여 활용하며, 내 에이전트를 등록(공개)할 수 있는 마켓플레이스 페이지.

## 1. 개요

| 항목 | 내용 |
|------|------|
| Feature ID | AGENT-STORE-001 |
| 페이지 경로 | `/agent-store` |
| 우선순위 | P1 |
| 의존성 | 인증(AUTH-001), Agent Builder API (구현 완료) |
| API 상태 | **전체 실제 API 사용** (Mock 없음) |

### 목표
- 사용자가 공개/부서별 에이전트 템플릿을 탐색하고 상세 정보를 확인
- 구독(Subscribe) 또는 포크(Fork)를 통해 에이전트를 활용
- 내가 만든 에이전트를 스토어에 등록(visibility 변경)

---

## 2. 사용자 스토리

| ID | 역할 | 스토리 | 우선순위 |
|----|------|--------|---------|
| US-01 | 사용자 | 전체 공개 에이전트 목록을 카드 그리드로 볼 수 있다 | P1 |
| US-02 | 사용자 | 부서별 공개 에이전트만 필터링하여 볼 수 있다 | P1 |
| US-03 | 사용자 | 에이전트 카드를 클릭하면 상세 정보가 팝업 카드뷰로 표시된다 | P1 |
| US-04 | 사용자 | 에이전트를 구독하여 내 에이전트 목록에 추가할 수 있다 | P1 |
| US-05 | 사용자 | 에이전트를 포크하여 내 것으로 복사/커스터마이징할 수 있다 | P1 |
| US-06 | 사용자 | 내 에이전트(private)를 스토어에 등록(public/department)할 수 있다 | P1 |
| US-07 | 사용자 | 이름으로 에이전트를 검색할 수 있다 | P2 |
| US-08 | 사용자 | 구독 해제, 즐겨찾기(pin) 토글할 수 있다 | P2 |
| US-09 | 소유자 | 내 에이전트의 포크/구독 통계를 확인할 수 있다 | P3 |

---

## 3. API 매핑

### 3-1. 사용할 백엔드 API (전체 구현 완료)

| 기능 | Method | Endpoint | 비고 |
|------|--------|----------|------|
| 에이전트 목록 (scope) | GET | `/api/v1/agents?scope={all\|public\|department\|mine}` | 탭 필터링 |
| 에이전트 상세 | GET | `/api/v1/agents/{agent_id}` | 팝업 카드뷰 |
| 구독 | POST | `/api/v1/agents/{agent_id}/subscribe` | 201 |
| 구독 해제 | DELETE | `/api/v1/agents/{agent_id}/subscribe` | 204 |
| 구독 설정 (pin) | PATCH | `/api/v1/agents/{agent_id}/subscribe` | is_pinned |
| 포크 | POST | `/api/v1/agents/{agent_id}/fork` | name 선택 |
| 내 에이전트 목록 | GET | `/api/v1/agents/my?filter={all\|owned\|subscribed\|forked}` | 내 에이전트 탭 |
| 에이전트 공개 등록 | PATCH | `/api/v1/agents/{agent_id}` | visibility 변경 |
| 포크/구독 통계 | GET | `/api/v1/agents/{agent_id}/forks` | 소유자 전용 |

### 3-2. 응답 스키마 (백엔드 기준)

**ListAgentsResponse** (GET /api/v1/agents)
```typescript
{
  agents: AgentSummary[];  // agent_id, name, description, visibility, department_name, owner_user_id, owner_email, temperature, can_edit, can_delete, created_at
  total: number;
  page: number;
  size: number;
}
```

**GetAgentResponse** (GET /api/v1/agents/{id})
```typescript
{
  agent_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tool_ids: string[];
  workers: WorkerInfo[];
  flow_hint: string;
  llm_model_id: string;
  status: string;
  visibility: string;
  department_id?: string;
  department_name?: string;
  temperature: number;
  owner_user_id: string;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
}
```

**SubscribeResponse** (POST /subscribe)
```typescript
{
  subscription_id: string;
  agent_id: string;
  agent_name: string;
  is_pinned: boolean;
  subscribed_at: string;
}
```

**ForkAgentResponse** (POST /fork)
```typescript
{
  agent_id: string;
  name: string;
  forked_from: string;
  forked_at: string;
  system_prompt: string;
  workers: WorkerInfo[];
  visibility: string;
  temperature: number;
  llm_model_id: string;
}
```

**ListMyAgentsResponse** (GET /my)
```typescript
{
  agents: MyAgentSummary[];  // agent_id, name, description, source_type, visibility, temperature, owner_user_id, forked_from, is_pinned, created_at
  total: number;
  page: number;
  size: number;
}
```

**ForkStatsResponse** (GET /forks)
```typescript
{
  agent_id: string;
  fork_count: number;
  subscriber_count: number;
}
```

---

## 4. 페이지 구조 및 UI 설계

### 4-1. 레이아웃

```
┌─────────────────────────────────────────────────────────┐
│ 헤더: 에이전트 스토어 아이콘 + 제목 + 검색바 + [등록] 버튼 │
├─────────────────────────────────────────────────────────┤
│ 탭: [전체] [부서별] [내 에이전트]                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ Agent    │ │ Agent    │ │ Agent    │                │
│  │ Card 1   │ │ Card 2   │ │ Card 3   │                │
│  │          │ │          │ │          │                │
│  └──────────┘ └──────────┘ └──────────┘                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ Card 4   │ │ Card 5   │ │ Card 6   │                │
│  └──────────┘ └──────────┘ └──────────┘                │
│                                                         │
│  [ 이전 ] 1 / 3 [ 다음 ]                                │
└─────────────────────────────────────────────────────────┘
```

### 4-2. 에이전트 카드 (AgentStoreCard)

```
┌──────────────────────────────┐
│ [아바타] 에이전트 이름         │
│          @소유자 · public     │
│                              │
│ 에이전트 설명 (2줄 제한)      │
│                              │
│ [도구태그] [도구태그]         │
│                              │
│ temp 0.7 · 2026-05-04       │
│                              │
│ [구독] [포크]                 │
└──────────────────────────────┘
```

### 4-3. 상세 팝업 카드뷰 (AgentDetailModal)

카드 클릭 시 모달/오버레이로 상세 정보 표시:

```
┌─────────────────────────────────────┐
│  [X 닫기]                           │
│                                     │
│  [아바타]  에이전트 이름             │
│            @소유자 · visibility      │
│            부서: OO부서              │
│                                     │
│  ─── 설명 ───                       │
│  에이전트 상세 설명 전문             │
│                                     │
│  ─── 시스템 프롬프트 ───            │
│  프롬프트 전문 (스크롤)              │
│                                     │
│  ─── 연결된 도구 ───                │
│  [도구1] [도구2] [도구3]            │
│                                     │
│  ─── 설정 ───                       │
│  모델: GPT-4o  Temperature: 0.7     │
│                                     │
│  ─── 통계 (소유자만) ───            │
│  구독 12명 · 포크 5회               │
│                                     │
│  [구독하기]  [포크하기]              │
└─────────────────────────────────────┘
```

### 4-4. 내 에이전트 등록 모달 (PublishAgentModal)

"등록" 버튼 클릭 시:
1. `GET /api/v1/agents/my?filter=owned` — 내가 소유한 private 에이전트 목록 조회
2. 목록에서 공개할 에이전트 선택
3. visibility 선택 (public / department) + department_id (부서 선택)
4. `PATCH /api/v1/agents/{id}` — visibility + department_id 업데이트

### 4-5. 내 에이전트 탭

`GET /api/v1/agents/my` 사용, 서브 필터: `전체 | 소유 | 구독 | 포크`

---

## 5. 프론트엔드 구현 범위

### 5-1. 신규 파일

| 분류 | 파일 경로 | 설명 |
|------|----------|------|
| **타입** | `src/types/agentStore.ts` | 스토어 전용 타입 (API 응답 매핑) |
| **상수** | `src/constants/api.ts` (수정) | 에이전트 스토어 엔드포인트 추가 |
| **서비스** | `src/services/agentStoreService.ts` | 에이전트 스토어 API 호출 |
| **훅** | `src/hooks/useAgentStore.ts` | TanStack Query 훅 (목록, 상세, 구독, 포크) |
| **쿼리키** | `src/lib/queryKeys.ts` (수정) | agentStore 쿼리 키 추가 |
| **페이지** | `src/pages/AgentStorePage/index.tsx` | 메인 페이지 |
| **컴포넌트** | `src/components/agent-store/AgentStoreCard.tsx` | 에이전트 카드 |
| **컴포넌트** | `src/components/agent-store/AgentDetailModal.tsx` | 상세 팝업 카드뷰 |
| **컴포넌트** | `src/components/agent-store/PublishAgentModal.tsx` | 내 에이전트 등록 모달 |
| **컴포넌트** | `src/components/agent-store/AgentStoreTab.tsx` | 탭 네비게이션 |
| **라우트** | `src/App.tsx` (수정) | `/agent-store` 라우트 추가 |
| **네비게이션** | `src/components/layout/TopNav.tsx` (수정) | 메뉴 항목 추가 |

### 5-2. 테스트 파일

| 파일 | 대상 |
|------|------|
| `src/hooks/useAgentStore.test.ts` | 훅 단위 테스트 (TanStack Query) |
| `src/components/agent-store/AgentStoreCard.test.tsx` | 카드 렌더링 + 클릭 |
| `src/components/agent-store/AgentDetailModal.test.tsx` | 모달 표시 + 구독/포크 |
| `src/__tests__/mocks/handlers.ts` (수정) | agent-store MSW 핸들러 추가 |

---

## 6. 구현 순서

```
Step 1: 타입 + 상수 + 서비스 + 쿼리키
  ├── src/types/agentStore.ts
  ├── src/constants/api.ts (엔드포인트 추가)
  ├── src/services/agentStoreService.ts
  └── src/lib/queryKeys.ts (쿼리키 추가)

Step 2: TanStack Query 훅
  └── src/hooks/useAgentStore.ts
      ├── useAgentList(scope, search, page, size)
      ├── useAgentDetail(agentId)
      ├── useMyAgents(filter, search, page, size)
      ├── useSubscribeAgent()
      ├── useUnsubscribeAgent()
      ├── useUpdateSubscription()
      ├── useForkAgent()
      ├── usePublishAgent()
      └── useForkStats(agentId)

Step 3: 컴포넌트
  ├── AgentStoreCard.tsx (카드 UI)
  ├── AgentStoreTab.tsx (탭 전환)
  ├── AgentDetailModal.tsx (상세 팝업)
  └── PublishAgentModal.tsx (등록 모달)

Step 4: 페이지 + 라우팅
  ├── AgentStorePage/index.tsx
  ├── App.tsx (라우트 추가)
  └── TopNav.tsx (메뉴 추가)

Step 5: 테스트
  ├── useAgentStore.test.ts
  ├── AgentStoreCard.test.tsx
  ├── AgentDetailModal.test.tsx
  └── MSW 핸들러 추가
```

---

## 7. 비기능 요구사항

| 항목 | 기준 |
|------|------|
| 인증 | 모든 API에 Bearer 토큰 필요 (`authClient` 사용) |
| 페이지네이션 | 서버 사이드, 20개/페이지 기본 |
| 에러 처리 | 409(이미 구독), 403(권한 없음), 404 각각 사용자 친화적 메시지 |
| 로딩 | 스켈레톤 카드 표시 |
| 빈 상태 | 탭별 적절한 빈 상태 메시지 |
| 반응형 | 카드 그리드 3열(lg) → 2열(md) → 1열(sm) |

---

## 8. 제외 범위 (Out of Scope)

- 에이전트 실행 (기존 채팅 페이지에서 처리)
- 에이전트 생성 폼 (기존 AgentBuilderPage에서 처리)
- 에이전트 편집/삭제 (기존 AgentBuilderPage에서 처리)
- 리뷰/평점 시스템
- 카테고리/태그 필터링 (현재 API 미지원)
