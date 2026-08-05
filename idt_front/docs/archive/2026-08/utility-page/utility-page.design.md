# utility-page Design — 유틸리티 카탈로그 페이지

> 작성일: 2026-08-02
> 상태: Draft
> Plan: `docs/01-plan/features/utility-page.plan.md`
> 프로젝트: idt_front (프론트 전용 — 백엔드 diff 0)

---

## 1. 설계 개요

`/tool-connection`의 목데이터 페이지를 제거하고, 기존 훅 3종(`useToolCatalog`·`useSkills`·`useLlmModels`)을 소비하는 읽기 전용 카탈로그 `UtilityPage`로 교체한다. 신규 API·신규 서비스 함수·백엔드 변경은 없다.

**Plan 확정 결정 (D1~D4) 재확인:**
- D1: 도구/스킬/모델 3탭 실연동, 미들웨어 탭은 "준비 중" 빈 상태
- D2: 설치됨/미설치 배지 제외
- D3: `/tool-connection` 경로 유지, 네비 라벨 '유틸리티'로 통일
- D4: 유형 필터는 `source`+`is_builtin` 매핑, 검색은 클라이언트 필터

**설계 조사에서 추가 확인된 사실:**
- `AppSidebar.tsx`는 이미 라벨이 '유틸리티'다(admin-nav-restructure에서 선반영) → TopNav·Sidebar만 갱신하면 3곳이 일치한다.
- 기존 테스트에 '도구 연결' 라벨 단언 없음 → 라벨 변경으로 인한 테스트 회귀 없음.
- `src/services/toolService.ts`는 어디서도 import되지 않는 죽은 코드 → ToolConnectionPage·`types/tool.ts`와 함께 삭제 가능.
- `GET /api/v1/llm-models?include_inactive=true`는 일반 로그인 사용자 허용(`get_current_user`) → 모델 탭에서 비활성 포함 조회 가능.

## 2. 컴포넌트 구조

```
src/pages/UtilityPage/
├── index.tsx          # 페이지: 헤더 + 탭 + 검색/필터 + 그리드 조립
├── UtilityCard.tsx    # 공통 카드 (이름 / 설명 / 배지 목록)
└── index.test.tsx     # MSW 통합 테스트
```

```
<UtilityPage>
 ├─ Header ─ 제목 "유틸리티" / 부제 / [새로고침] 버튼
 ├─ CategoryTabs ─ [도구] [모델] [미들웨어] [스킬]        (로컬 state)
 ├─ SearchInput ─ "검색..."                               (로컬 state)
 ├─ TypeFilterChips ─ 도구 탭에서만 렌더                   (로컬 state)
 └─ CardGrid
     ├─ 도구:  useToolCatalog()  → CatalogTool[]
     ├─ 모델:  useLlmModels(true) → LlmModel[]
     ├─ 스킬:  useSkills({scope:'all', size:100}) → SkillListResponse
     └─ 미들웨어: EmptyState "준비 중입니다" (API 호출 없음)
```

- 페이지 상태는 `useState` 3개(activeTab, search, toolTypeFilter)로 충분 — 스토어·URL 동기화 불필요(1차).
- 서브컴포넌트(탭·칩·빈상태)는 `index.tsx` 내부 함수 컴포넌트로 두되, `UtilityCard`만 파일 분리(3개 자원이 공유).
- 레이아웃·톤은 기존 페이지 스타일 관례(zinc/violet 팔레트, rounded-2xl 카드)를 계승한다. 헤더는 참고 이미지(utility.png)와 같이 텍스트만 사용(아이콘 없음).

## 3. 데이터 계약 (기존 훅 재사용 — 변경 없음)

| 탭 | 훅 호출 | 반환 data | 카드 필드 매핑 |
|----|---------|----------|---------------|
| 도구 | `useToolCatalog()` | `CatalogTool[]` | 제목=`name`, 설명=`description`, 배지=유형(§4), 보조=`requires_env`(있으면), MCP면 `mcp_server_name` |
| 모델 | `useLlmModels(true)` | `LlmModel[]` | 제목=`display_name`, 설명=`description ?? model_name`, 배지=`provider`+(`is_default`→'기본')+(`!is_active`→'비활성') |
| 스킬 | `useSkills({ scope: 'all', size: 100 })` | `SkillListResponse` (`.skills` 사용) | 제목=`name`, 설명=`description`, 배지=`script_type`(none 제외)+`visibility` |
| 미들웨어 | 없음 | — | EmptyState |

- `useLlmModels`는 `select`로 이미 `models` 배열을 반환한다. 비활성 모델은 카드 전체 `opacity` 감쇠 + '비활성' 배지.
- 스킬 `total > 100`이면 그리드 하단에 "외 N개 — 관리 화면에서 전체 보기" 안내 문구만 표시(페이지네이션 미구현, Plan 비목표).
- 훅 3개는 탭과 무관하게 항상 마운트한다(조건부 훅 호출 금지 — React 규칙). 각 탭 카운트를 탭 라벨 옆에 표시하는 데에도 사용.

## 4. 도구 유형 매핑 & 필터

```ts
// UtilityPage 내부 순수 함수
type ToolKind = 'built-in' | 'custom' | 'mcp';

const toolKind = (t: CatalogTool): ToolKind =>
  t.source === 'mcp' ? 'mcp' : t.is_builtin ? 'built-in' : 'custom';
```

- 필터 칩: `전체 | built-in | custom | mcp` (도구 탭 전용, 단일 선택, 기본 '전체').
- 배지 색: built-in=sky, custom=violet, mcp=amber (기존 카테고리 칩 스타일 재사용).
- 스크린샷의 mcp-stdio/mcp-http/http 세분화는 데이터 근거 없음 → `mcp` 단일 (Plan D4).

## 5. 검색 (FR-06)

```ts
const matches = (q: string, ...fields: (string | null | undefined)[]) =>
  q.trim() === '' ||
  fields.some((f) => f?.toLowerCase().includes(q.trim().toLowerCase()));
```

- 현재 활성 탭 목록에만 적용. 대상 필드: 도구=`name`,`description` / 모델=`display_name`,`model_name`,`description` / 스킬=`name`,`description`.
- 로컬 배열 필터이므로 debounce 없음. 탭 전환 시 검색어는 유지(입력 보존이 자연스러움).
- 스킬은 서버 `search` 파라미터가 있지만 1차는 클라이언트 필터로 통일한다(자원 3종 동작 일관성 + 쿼리 키 파편화 방지).

## 6. 새로고침 (FR-07)

```ts
const queryClient = useQueryClient();
const handleRefresh = () => {
  queryClient.invalidateQueries({ queryKey: queryKeys.toolCatalog.all });
  queryClient.invalidateQueries({ queryKey: queryKeys.llmModels.all });
  queryClient.invalidateQueries({ queryKey: [...queryKeys.admin.all, 'skills'] });
};
```

- 3개 자원을 모두 invalidate(현재 탭만이 아니라) — 버튼 하나로 화면 전체 최신화라는 기대와 일치.
- 스킬 쿼리 키는 `useSkills`가 `queryKeys.admin.skills(params)`를 쓰므로 기존 invalidate 관례(`[...queryKeys.admin.all, 'skills']`)를 그대로 따른다.

## 7. 로딩 / 에러 / 빈 상태

| 상태 | 처리 |
|------|------|
| 로딩 | 탭 콘텐츠 영역에 스켈레톤 카드 6개 (기존 페이지들의 관례 따름) |
| 에러 | "목록을 불러오지 못했습니다" + [다시 시도] 버튼(해당 쿼리 `refetch`) |
| 빈 목록 | "표시할 항목이 없습니다" (검색어 또는 유형 필터로 0건이 되면 "검색 결과가 없습니다") |
| 미들웨어 탭 | "준비 중입니다 — 미들웨어 카탈로그는 곧 제공됩니다" 고정 EmptyState |

- 탭별 상태는 독립: 도구 탭 에러가 스킬 탭 렌더를 막지 않는다.

## 8. 라우팅 / 네비게이션 변경

| 파일 | 변경 |
|------|------|
| `src/App.tsx` | `<Route path="/tool-connection" element={<UtilityPage />} />` 로 교체 (import 교체) |
| `src/components/layout/TopNav.tsx:50-53` | label '도구 연결'→'유틸리티', description '사용 가능한 도구, 모델, 미들웨어, 스킬을 찾아봅니다'로 갱신 (읽기 전용 페이지이므로 '추가' 표현 제외) |
| `src/components/layout/Sidebar.tsx:29` | label '도구 연결'→'유틸리티' |
| `src/components/layout/AppSidebar.tsx` | 변경 없음 (이미 '유틸리티') |

## 9. 삭제 대상 (교체 후 정리)

| 파일 | 근거 |
|------|------|
| `src/pages/ToolConnectionPage/` | UtilityPage로 대체. 테스트 파일 없음 |
| `src/services/toolService.ts` | import 0곳 — 죽은 코드 |
| `src/types/tool.ts` | ToolConnectionPage·toolService만 참조 — 동반 삭제 |
| `src/claude/task/task-tool-connection.md` | 목데이터 페이지 명세 문서 — 함께 제거 |

- 삭제 후 `tsc`/vitest로 잔여 참조 0 확인.

## 10. 테스트 설계 (TDD — 구현 전 작성)

파일: `src/pages/UtilityPage/index.test.tsx`
공통: MSW per-file 3종 훅(`server.listen/resetHandlers/close`) 직접 선언, `--pool=threads` 실행.

핸들러 픽스처:
- `GET */api/v1/tool-catalog` → internal builtin 1 + internal custom 1 + mcp 1 (requires_env 포함 1건)
- `GET */api/v1/llm-models` → 활성 1(is_default) + 비활성 1
- `POST */api/v1/skills/list` → 스킬 2건 (script_type none/python) — 목록 계약은 POST(`skillService.getSkills`)

| # | 케이스 | 단언 |
|---|--------|------|
| T1 | 도구 탭 기본 렌더 | 카탈로그 3건 카드 표시, 유형 배지(built-in/custom/mcp) 각각 표시 |
| T2 | 유형 필터 | 'mcp' 칩 클릭 → mcp 카드만 남음, '전체' 복귀 시 3건 |
| T3 | 검색 | 검색어 입력 → 일치 카드만 표시, 0건이면 "검색 결과가 없습니다" |
| T4 | 모델 탭 전환 | display_name 렌더, 비활성 모델에 '비활성' 배지 |
| T5 | 스킬 탭 전환 | 스킬 이름 렌더, visibility 배지 표시 |
| T6 | 미들웨어 탭 | "준비 중" 문구 표시 (미들웨어 전용 API는 존재하지 않음 — 훅 3종은 §3에 따라 항상 마운트되므로 "요청 없음" 단언은 하지 않는다) |
| T7 | 도구 API 500 | 에러 문구 + 다시 시도 버튼 렌더 |
| T8 | 새로고침 | 버튼 클릭 → tool-catalog 핸들러 재호출 확인(호출 카운터) |
| T9 | 헤더 | 제목 '유틸리티' 렌더 |

네비 라벨: `TopNav.test.tsx`에 '유틸리티' 항목 노출 단언 1건 추가(기존 단언 패턴 준수).

## 11. 구현 순서

1. `UtilityPage/index.test.tsx` 작성 (T1~T9, Red 확인)
2. `UtilityCard.tsx` + `UtilityPage/index.tsx` 구현 (Green)
3. `App.tsx` 라우트 교체 + TopNav·Sidebar 라벨 갱신 + TopNav 테스트 단언 추가
4. ToolConnectionPage·toolService·types/tool.ts·task 문서 삭제 → `tsc` + 전체 테스트로 잔여 참조 0 확인
5. Refactor: 스타일 정리, 카드 배지 색상 상수화

## 12. 영향 범위 / 주의

- **선행 조건**: admin-nav-restructure 미커밋 변경(TopNav 등)을 먼저 커밋할 것 — 같은 파일 수정 충돌 방지 (Plan §8).
- `useSkills` 쿼리 키가 `queryKeys.admin.*` 네임스페이스를 쓰는 것은 기존 구조 그대로 수용한다(키 리팩토링은 스코프 밖).
- AgentBuilder·AdminTools가 같은 `toolCatalog` 쿼리 키를 공유하므로 이 페이지의 invalidate가 해당 화면 캐시도 갱신한다 — 부작용 아닌 의도된 공유.
- 사전 실패 테스트 8건(collection 7 + ChatPage 1)은 본 작업과 무관 — 회귀 판정에서 제외.
