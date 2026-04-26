# Custom RAG Tool Frontend Design Document

> **Summary**: 에이전트 빌더에서 RAG 도구(internal_document_search) 선택 시 검색 설정 패널을 제공하는 프론트엔드 기능
>
> **Project**: IDT Front (React + TypeScript)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-04-21
> **Status**: Draft
> **Planning Doc**: [custom-rag-tool-frontend.plan.md](../01-plan/features/custom-rag-tool-frontend.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A |
| Phase 2 | Coding Conventions | ✅ (CLAUDE.md) |
| Phase 3 | Mockup | N/A (Plan 문서에 ASCII 목업 포함) |
| Phase 4 | API Spec | ✅ (Plan 문서 Section 4) |

---

## 1. Overview

### 1.1 Design Goals

- 에이전트 빌더 FormView에 **RagConfigPanel**을 추가하여 RAG 도구의 검색 범위/파라미터를 커스텀
- 기존 AgentBuilderPage의 폼 스타일과 100% 일관성 유지
- 백엔드 `tool_configs` 필드와 완전한 데이터 동기화
- 컬렉션/메타데이터 키를 API에서 동적으로 로딩하여 사용자 입력 부담 최소화

### 1.2 Design Principles

- **조건부 렌더링**: `internal_document_search` 선택 시에만 패널 노출 — 불필요한 UI 복잡도 방지
- **하위 호환**: `tool_configs`는 Optional — 기존 에이전트 생성 플로우에 영향 없음
- **Graceful Degradation**: API 실패 시 수동 입력 폴백 제공

---

## 2. Architecture

### 2.1 Component Diagram

```
AgentBuilderPage (FormView)
  ├─ 기존 폼 필드 (이름, 설명, 모델, 프롬프트, Temperature)
  ├─ 도구 연결 섹션
  │    ├─ ToolButton (internal_document_search) ← 선택 트리거
  │    ├─ ToolButton (tavily_search)
  │    └─ ...
  └─ RagConfigPanel (조건부: tool 선택 시에만)
       ├─ CollectionSelect        ← useCollections() 훅
       ├─ MetadataFilterEditor    ← useMetadataKeys() 훅
       ├─ SearchParamsControl     ← 로컬 상태 (radio + slider)
       └─ ToolIdentityEditor     ← 로컬 상태 (input + textarea)
```

### 2.2 Data Flow

```
[사용자: 도구 선택]
  → handleToolToggle('internal:internal_document_search')
  → form.toolConfigs[RAG_TOOL_ID]에 DEFAULT_RAG_CONFIG 설정
  → RagConfigPanel 렌더링 (toolConfigs[RAG_TOOL_ID] 존재 시)
    → useCollections() → GET /api/v1/rag-tools/collections (staleTime: 5min)
    → 컬렉션 선택 시 useMetadataKeys(collectionName) → GET /api/v1/rag-tools/metadata-keys (staleTime: 3min)
    → 설정 변경 시 onChange(config) → form.toolConfigs 업데이트
  → handleSave()
    → 현재: Mock 로컬 상태 업데이트 (API 연동은 향후 스프린트)
    → 향후: requestBody.tool_configs = form.toolConfigs → POST /api/v1/agents

[사용자: 도구 해제]
  → handleToolToggle('internal:internal_document_search')
  → form.toolConfigs에서 RAG_TOOL_ID 키 삭제
  → RagConfigPanel 언마운트
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| RagConfigPanel | useCollections, useMetadataKeys | 컬렉션/메타데이터 키 동적 로딩 |
| useCollections | ragToolService, queryKeys | API 호출 + 캐싱 |
| useMetadataKeys | ragToolService, queryKeys | 컬렉션별 메타데이터 키 조회 |
| ragToolService | apiClient, API_ENDPOINTS | HTTP 요청 |
| AgentBuilderPage | RagConfigPanel, RagToolConfig 타입 | 패널 통합 + 폼 데이터 확장 |

---

## 3. Data Model

### 3.1 Entity Definition

```typescript
/** RAG 도구 커스텀 설정 */
export interface RagToolConfig {
  collection_name?: string;
  es_index?: string;
  metadata_filter: Record<string, string>;
  top_k: number;
  search_mode: 'hybrid' | 'vector_only' | 'bm25_only';
  rrf_k: number;
  tool_name: string;
  tool_description: string;
}

/** 컬렉션 정보 */
export interface CollectionInfo {
  name: string;
  display_name: string;
  vectors_count?: number;
}

/** 메타데이터 키 정보 */
export interface MetadataKeyInfo {
  key: string;
  sample_values: string[];
  value_count: number;
}
```

### 3.2 Default Values

```typescript
export const DEFAULT_RAG_CONFIG: RagToolConfig = {
  metadata_filter: {},
  top_k: 5,
  search_mode: 'hybrid',
  rrf_k: 60,
  tool_name: '내부 문서 검색',
  tool_description: '내부 문서에서 관련 정보를 검색합니다. 질문에 대한 내부 문서 정보가 필요할 때 사용하세요.',
};
```

### 3.3 RAG_TOOL_ID

```typescript
const RAG_TOOL_ID = 'internal:internal_document_search';
```

> `internal:` 접두사는 백엔드 도구 카탈로그의 `tool_id` 형식과 일치시키기 위함.

### 3.4 AgentFormData 확장

```typescript
interface AgentFormData {
  name: string;
  description: string;
  model: string;
  systemPrompt: string;
  tools: string[];
  temperature: number;
  toolConfigs: Record<string, RagToolConfig>;  // 추가
}
```

### 3.5 Service Layer 패턴

> `ragToolService`는 axios 응답을 내부에서 unwrap하여 도메인 데이터만 반환한다.
> 응답 래퍼 타입(`CollectionsResponse`, `MetadataKeysResponse`)은 서비스 파일 내부에 private으로 정의한다.

```typescript
// ragToolService.ts
const ragToolService = {
  getCollections: async (): Promise<CollectionInfo[]> => {
    const { data } = await apiClient.get<CollectionsResponse>(...);
    return data.collections;
  },
  getMetadataKeys: async (collectionName?: string): Promise<MetadataKeyInfo[]> => {
    const { data } = await apiClient.get<MetadataKeysResponse>(...);
    return data.keys;
  },
};
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/rag-tools/collections` | 사용 가능한 Qdrant 컬렉션 목록 | No |
| GET | `/api/v1/rag-tools/metadata-keys` | 메타데이터 키 + 샘플 값 | No |
| POST | `/api/v1/agents` (기존) | 에이전트 생성 — `tool_configs` 필드 추가 | No |

### 4.2 GET /api/v1/rag-tools/collections

**Response (200):**
```json
{
  "collections": [
    { "name": "documents", "display_name": "전체 문서", "vectors_count": 500 },
    { "name": "finance_docs", "display_name": "금융 문서", "vectors_count": 200 },
    { "name": "tech_manuals", "display_name": "기술 매뉴얼", "vectors_count": 150 }
  ]
}
```

### 4.3 GET /api/v1/rag-tools/metadata-keys

**Query Params:** `collection_name` (optional)

**Response (200):**
```json
{
  "keys": [
    { "key": "department", "sample_values": ["finance", "tech", "hr"], "value_count": 3 },
    { "key": "category", "sample_values": ["policy", "manual", "guide"], "value_count": 3 },
    { "key": "year", "sample_values": ["2024", "2025", "2026"], "value_count": 3 }
  ]
}
```

### 4.4 POST /api/v1/agents — tool_configs 확장

**Request body (tool_configs 부분):**
```json
{
  "tool_configs": {
    "internal:internal_document_search": {
      "collection_name": "finance_docs",
      "metadata_filter": { "department": "finance" },
      "top_k": 10,
      "search_mode": "vector_only",
      "rrf_k": 60,
      "tool_name": "금융 정책 검색",
      "tool_description": "금융 관련 내부 정책 문서를 검색합니다."
    }
  }
}
```

> **Note**: `handleSave`의 API 연동은 현재 Mock 단계이며, 향후 API 연동 스프린트에서 구현 예정.
```

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
AgentBuilderPage (FormView, max-w: 720px)
┌─────────────────────────────────────────────┐
│  에이전트 이름 *         [________________] │
│  설명                    [________________] │
│  모델                    [btn][btn][btn]    │
│  시스템 프롬프트         [________________] │
│                          [________________] │
│  도구 연결                                  │
│  ┌─────────────┐  ┌─────────────┐          │
│  │ ✓ 문서 검색 │  │   검색 도구 │          │
│  └─────────────┘  └─────────────┘          │
│                                             │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
│  │  RagConfigPanel (violet-50 bg)        │ │
│  │  ┌──────────────────────────────────┐ │ │
│  │  │ 검색 대상 컬렉션  [▼ dropdown ] │ │ │
│  │  └──────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────┐ │ │
│  │  │ 메타데이터 필터                  │ │ │
│  │  │ [key ▼] [value ▼]        [✕]   │ │ │
│  │  │ [+ 필터 추가]                   │ │ │
│  │  └──────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────┐ │ │
│  │  │ 검색 모드  (●)하이브리드 ( )벡터│ │ │
│  │  │ 결과 수    ──●──────── [5]      │ │ │
│  │  └──────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────┐ │ │
│  │  │ 도구 이름  [________________]   │ │ │
│  │  │ 도구 설명  [________________]   │ │ │
│  │  │            0/500                │ │ │
│  │  └──────────────────────────────────┘ │ │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘ │
│                                             │
│  Temperature               [0.7]           │
│  ├──────────●──────────────────┤            │
└─────────────────────────────────────────────┘
```

### 5.2 User Flow

```
도구 목록에서 "내부 문서 검색" 선택
  → RagConfigPanel 펼침 (기본값 자동 세팅)
  → (선택) 컬렉션 변경 → 메타데이터 필터 초기화 + 키 재로딩
  → (선택) 메타데이터 필터 추가/삭제
  → (선택) 검색 모드/top_k 조정
  → (선택) 도구 이름/설명 커스텀
  → "저장" 클릭 → (현재 Mock 로컬 저장 / 향후 tool_configs 포함 API 호출)
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| RagConfigPanel | `src/components/agent-builder/` | RAG 설정 패널 메인 (4개 섹션 통합) |
| CollectionSelect (내부) | RagConfigPanel 내부 | 컬렉션 드롭다운 + 로딩/에러 상태 |
| MetadataFilterEditor (내부) | RagConfigPanel 내부 | key-value 필터 동적 추가/삭제 |
| SearchParamsControl (내부) | RagConfigPanel 내부 | search_mode 라디오 + top_k 슬라이더 |
| ToolIdentityEditor (내부) | RagConfigPanel 내부 | tool_name + tool_description 입력 |

### 5.4 RagConfigPanel 스타일링

```
패널 전체: rounded-2xl border border-violet-200 bg-violet-50/30 p-5
레이블: text-[13px] font-semibold text-zinc-700
입력: rounded-xl border border-zinc-300 focus:border-violet-400 focus:ring-2 focus:ring-violet-100
버튼(추가): bg-violet-600 text-white rounded-xl
버튼(삭제): text-zinc-400 hover:text-red-500
섹션 간격: space-y-6
```

---

## 6. Error Handling

### 6.1 Error Scenarios

| Scenario | UI 처리 | 폴백 |
|----------|---------|------|
| 컬렉션 API 실패 | "컬렉션 목록을 불러올 수 없습니다" + 재시도 버튼 | 없음 (컬렉션 선택 불가) |
| 메타데이터 키 API 실패 | 자동완성 비활성 | 수동 입력 모드 (자유 key-value 입력) |
| 메타데이터 필터 10개 초과 | "필터 추가" 버튼 비활성 | 최대 10개 제한 표시 |
| tool_description 500자 초과 | maxLength 속성으로 방지 | 글자 수 카운터 표시 |
| tool_name 100자 초과 | maxLength 속성으로 방지 | - |

---

## 7. Security Considerations

- [x] XSS: 사용자 입력(tool_name, tool_description, metadata 값)은 React가 자동 이스케이프
- [x] 입력 길이 제한: tool_name(100), tool_description(500), metadata_filter(10개)
- [ ] 인증: 현재 RAG Tools API는 공개 엔드포인트 — 향후 인증 추가 시 authClient로 전환

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | useCollections, useMetadataKeys 훅 | Vitest + MSW |
| Component Test | RagConfigPanel | React Testing Library |
| Integration | AgentBuilderPage + RagConfigPanel | React Testing Library |

### 8.2 Test Cases

**훅 테스트 (useRagToolConfig.test.ts):**
- [x] `useCollections` — 컬렉션 목록 반환
- [x] `useCollections` — API 실패 시 isError
- [x] `useMetadataKeys` — 컬렉션명 제공 시 키 반환
- [x] `useMetadataKeys` — 컬렉션명 미제공 시 비활성
- [x] `useMetadataKeys` — sample_values 포함 확인

**컴포넌트 테스트 (향후):**
- [ ] 컬렉션 드롭다운 선택 시 onChange 호출
- [ ] 메타데이터 필터 추가/삭제 동작
- [ ] search_mode 라디오 전환
- [ ] top_k 슬라이더 값 변경
- [ ] tool_description 글자 수 카운터

---

## 9. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| RagConfigPanel | Presentation | `src/components/agent-builder/RagConfigPanel.tsx` |
| useCollections, useMetadataKeys | Application | `src/hooks/useRagToolConfig.ts` |
| RagToolConfig, CollectionInfo, MetadataKeyInfo | Domain | `src/types/ragToolConfig.ts` |
| ragToolService + CollectionsResponse, MetadataKeysResponse | Infrastructure | `src/services/ragToolService.ts` |
| API_ENDPOINTS (RAG_TOOL_*) | Infrastructure | `src/constants/api.ts` |
| queryKeys.ragTools | Infrastructure | `src/lib/queryKeys.ts` |

### Import Rules

```
RagConfigPanel → useCollections, useMetadataKeys → ragToolService → apiClient
     ↓                                                    ↓
  RagToolConfig (types)                          API_ENDPOINTS (constants)
```

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| Component naming | PascalCase (`RagConfigPanel.tsx`) |
| Hook naming | camelCase (`useRagToolConfig.ts`) |
| Type naming | PascalCase interface (`RagToolConfig`, `CollectionInfo`) |
| Service naming | camelCase object literal (`ragToolService`) |
| Props | `interface RagConfigPanelProps` — 파일 상단 |
| Export | `export default` — 파일 하단 단독 |
| State management | 서버 상태: TanStack Query / 로컬 상태: props 기반 controlled |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── types/ragToolConfig.ts           (신규) 타입 + DEFAULT_RAG_CONFIG
├── constants/api.ts                 (수정) RAG_TOOL_* 엔드포인트 추가
├── lib/queryKeys.ts                 (수정) ragTools 도메인 추가
├── services/ragToolService.ts       (신규) API 호출
├── hooks/useRagToolConfig.ts        (신규) useCollections, useMetadataKeys
├── hooks/useRagToolConfig.test.ts   (신규) 훅 테스트
├── components/agent-builder/
│   └── RagConfigPanel.tsx           (신규) RAG 설정 패널
├── pages/AgentBuilderPage/
│   └── index.tsx                    (수정) FormData 확장 + 패널 통합
└── __tests__/mocks/
    └── handlers.ts                  (수정) MSW 핸들러 추가
```

### 11.2 Implementation Order

**Step 1: 타입 + 상수 (의존성 없음)**
1. [ ] `src/types/ragToolConfig.ts` — 타입 + `DEFAULT_RAG_CONFIG`
2. [ ] `src/constants/api.ts` — `RAG_TOOL_COLLECTIONS`, `RAG_TOOL_METADATA_KEYS` 추가
3. [ ] `src/lib/queryKeys.ts` — `ragTools` 도메인 추가

**Step 2: 서비스 + 훅 + 테스트**
4. [ ] `src/services/ragToolService.ts` — API 호출
5. [ ] `src/hooks/useRagToolConfig.ts` — 훅 구현
6. [ ] `src/__tests__/mocks/handlers.ts` — RAG Tools 핸들러 추가
7. [ ] `src/hooks/useRagToolConfig.test.ts` — 훅 테스트 (5개)

**Step 3: UI 컴포넌트**
8. [ ] `src/components/agent-builder/RagConfigPanel.tsx` — 4개 섹션

**Step 4: 페이지 통합**
9. [ ] `AgentBuilderPage/index.tsx` — AgentFormData.toolConfigs 확장
10. [ ] `AgentBuilderPage/index.tsx` — handleToolToggle 수정
11. [ ] `AgentBuilderPage/index.tsx` — FormView에 RagConfigPanel 조건부 렌더링
12. [ ] `AgentBuilderPage/index.tsx` — 저장 시 tool_configs 전달

**Step 5: 수동 검증**
13. [ ] 개발 서버에서 전체 플로우 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-21 | Initial draft | 배상규 |
