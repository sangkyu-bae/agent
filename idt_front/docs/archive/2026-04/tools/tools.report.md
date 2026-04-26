# PDCA Completion Report: tools

> AgentBuilderPage 도구 카탈로그 API 연동

## 1. 요약

| 항목 | 내용 |
|------|------|
| Feature | tools (AgentBuilder 도구 카탈로그 API 연동) |
| 시작일 | 2026-04-21 |
| 완료일 | 2026-04-21 |
| Match Rate | **100%** |
| 반복 횟수 | 1 |
| 난이도 | Low |
| 예상 소요 | 1~2시간 |

---

## 2. PDCA 사이클 진행

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ → [Act] ✅ → [Report] ✅
```

| Phase | 결과 |
|-------|------|
| **Plan** | `docs/01-plan/features/tools.plan.md` — API 스펙, 구현 범위, 테스트 계획 수립 |
| **Design** | `docs/02-design/features/tools.design.md` — 타입/서비스/훅/UI 상세 설계 |
| **Do** | 6개 파일 생성/수정 완료 |
| **Check** | 초기 82% (14/17) → 반복 후 100% |
| **Act** | Gap 3건 해결 (테스트 2건 + Mock 데이터 정리 1건) |

---

## 3. 구현 결과

### 3-1. 신규 파일

| 파일 | 역할 |
|------|------|
| `src/types/toolCatalog.ts` | `CatalogTool`, `ToolCatalogResponse` 타입 정의 |
| `src/services/toolCatalogService.ts` | `getToolCatalog()` — authClient 기반 API 호출 |
| `src/hooks/useToolCatalog.ts` | TanStack Query 훅 (`queryKeys.toolCatalog.list()`) |
| `src/hooks/useToolCatalog.test.ts` | 훅 단위 테스트 (성공/에러/빈 목록 3개 시나리오) |
| `src/__tests__/components/AgentBuilderFormView.test.tsx` | 컴포넌트 통합 테스트 (로딩/목록/선택/에러 4개 시나리오) |

### 3-2. 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/constants/api.ts` | `TOOL_CATALOG: '/api/v1/tool-catalog'` 추가 |
| `src/lib/queryKeys.ts` | `toolCatalog.all`, `toolCatalog.list()` 키 추가 |
| `src/__tests__/mocks/handlers.ts` | `GET */api/v1/tool-catalog` MSW 핸들러 추가 |
| `src/pages/AgentBuilderPage/index.tsx` | `AVAILABLE_TOOLS` 하드코딩 제거, `useToolCatalog()` 훅 연동 |

---

## 4. Gap 분석 및 해결

### 초기 분석 (82%)

| Gap | 심각도 | 내용 | 해결 |
|-----|--------|------|------|
| MOCK_AGENTS tools 필드 | P3 | 구 ID 형식 남아있음 | 빈 배열로 리셋 |
| useToolCatalog.test.ts | P1 | 훅 단위 테스트 미작성 | 3개 시나리오 작성 완료 |
| FormView 컴포넌트 테스트 | P2 | 컴포넌트 테스트 미작성 | 4개 시나리오 작성 완료 |

### 반복 후 (100%)

모든 Gap 해결 — 17/17 항목 충족.

---

## 5. 테스트 결과

### 훅 테스트 (useToolCatalog.test.ts)

| 시나리오 | 상태 |
|----------|------|
| 성공 시 CatalogTool[] 반환 | ✅ |
| 서버 에러 시 isError === true | ✅ |
| 빈 목록 응답 처리 | ✅ |

### 컴포넌트 테스트 (AgentBuilderFormView.test.tsx)

| 시나리오 | 상태 |
|----------|------|
| 로딩 중 스켈레톤 UI 표시 | ✅ |
| 서버 데이터로 도구 목록 표시 | ✅ |
| 도구 선택/해제 토글 | ✅ |
| 에러 상태 + 다시 시도 버튼 | ✅ |

---

## 6. 아키텍처 패턴 준수

| 패턴 | 준수 여부 | 상세 |
|------|:---------:|------|
| 타입 파일 분리 (`types/`) | ✅ | `toolCatalog.ts` |
| 서비스 레이어 분리 (`services/`) | ✅ | authClient 사용 |
| TanStack Query 훅 (`hooks/`) | ✅ | queryKeys 팩토리 활용 |
| 엔드포인트 상수 관리 (`constants/api.ts`) | ✅ | 중앙 집중 |
| MSW 기반 API 모킹 | ✅ | handlers.ts에 추가 |
| TDD (Red → Green → Refactor) | ✅ | Act 단계에서 보완 |

---

## 7. 영향 범위

- **변경**: AgentBuilderPage의 도구 선택 UI (하드코딩 → 서버 API)
- **무변경**: ToolConnectionPage, ToolAdminPage, ChatPage 등 다른 페이지

---

## 8. 후속 작업 (참고)

| 항목 | 우선순위 | 설명 |
|------|---------|------|
| Agent CRUD API 연동 | P2 | MOCK_AGENTS를 서버 API로 교체 |
| Agent 도구 할당 저장 | P2 | 에이전트 생성/수정 시 tool_id 배열 전송 |
| 도구 아이콘 다양화 | P3 | source별 아이콘 분기 (현재 기본 아이콘 + MCP 뱃지) |
