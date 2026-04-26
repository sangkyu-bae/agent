# Gap Analysis: tools

> AgentBuilderPage 도구 카탈로그 API 연동 — 설계 vs 구현 Gap 분석

## 분석 일시

2026-04-21

## 분석 대상

- **Design**: `docs/02-design/features/tools.design.md`
- **Implementation**: 타입, 상수, 서비스, 훅, 페이지, MSW 핸들러

---

## Gap Analysis 결과

| # | Design Item | Status | Notes |
|---|------------|--------|-------|
| 1 | `src/types/toolCatalog.ts` | ✅ Match | CatalogTool, ToolCatalogResponse 설계 100% 일치 |
| 2 | `src/constants/api.ts` — TOOL_CATALOG | ✅ Match | `'/api/v1/tool-catalog'` 추가됨 |
| 3 | `src/services/toolCatalogService.ts` | ✅ Match | authClient 사용, 설계 100% 일치 |
| 4 | `src/lib/queryKeys.ts` — toolCatalog | ✅ Match | all, list() 키 구조 일치 |
| 5 | `src/hooks/useToolCatalog.ts` | ✅ Match | queryKey, queryFn 설계 일치 |
| 6 | MSW 핸들러 — TOOL_CATALOG | ✅ Match | 설계 예시와 일치 |
| 7 | AVAILABLE_TOOLS 제거 | ✅ Match | 하드코딩 배열 완전 제거됨 |
| 8 | useToolCatalog() 훅 연동 | ✅ Match | isLoading, isError, refetch 모두 활용 |
| 9 | 스켈레톤 로딩 UI | ✅ Match | 2x2 그리드 (설계 2x3과 소폭 차이, 허용 범위) |
| 10 | 에러 상태 + 재시도 버튼 | ✅ Match | 인라인 에러 + "다시 시도" 버튼 |
| 11 | 빈 목록 상태 | ✅ Match | "등록된 도구가 없습니다" 표시 |
| 12 | tool.tool_id / tool.name 사용 | ✅ Match | FormView + AgentCard 모두 적용 |
| 13 | source 뱃지 (MCP) | ✅ Match | MCP 뱃지 구현됨 |
| 14 | AgentCard catalogTools prop | ✅ Match | catalogTools?.find() 패턴 사용 |
| 15 | MOCK_AGENTS tools 필드 정리 | ⚠️ Gap | 구 ID('file-read' 등) 남아있음 |
| 16 | useToolCatalog.test.ts | ❌ Missing | 훅 단위 테스트 미작성 |
| 17 | FormView 컴포넌트 테스트 | ❌ Missing | 컴포넌트 테스트 미작성 |

---

## Match Rate

**82%** (14/17 항목 충족)

---

## Gap 상세

### Gap 1: MOCK_AGENTS tools 필드 (P3)

- **현재**: `['file-read', 'rag-retrieval']`, `['code-exec', 'web-search']` 등 구 ID
- **설계**: 빈 배열로 리셋하거나 서버 tool_id 형식으로 매핑
- **영향**: 서버 연동 시 AgentCard에서 도구 이름이 fallback(toolId 자체 표시)됨

### Gap 2: useToolCatalog.test.ts 미작성 (P1)

- **설계 요구**: 성공/401 에러/빈 목록 3개 시나리오
- **현재**: 테스트 파일 없음
- **TDD 규칙 위반**: CLAUDE.md에 "테스트 없이 구현 코드를 먼저 작성하지 않는다" 명시

### Gap 3: FormView 컴포넌트 테스트 미작성 (P2)

- **설계 요구**: 로딩/도구 목록 표시/도구 선택/선택 해제 4개 시나리오
- **현재**: 테스트 파일 없음

---

## 개선 권장 사항

1. `useToolCatalog.test.ts` 훅 테스트 작성 (P1)
2. FormView 컴포넌트 테스트 작성 (P2)
3. MOCK_AGENTS의 tools 필드를 빈 배열로 리셋 (P3)
