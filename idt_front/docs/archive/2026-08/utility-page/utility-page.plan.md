# utility-page Plan — 유틸리티 카탈로그 페이지 (/tool-connection 전면 교체)

> 작성일: 2026-08-02
> 상태: Draft
> 프로젝트: idt_front (프론트 전용 — 백엔드 변경 0)
> 참고 이미지: `../docs/img/utility.png`

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `/tool-connection`(도구 연결) 페이지가 100% 목데이터로만 그려져 있어 실제 서버에 등록된 도구·스킬·모델과 무관한 가짜 화면을 사용자에게 보여주고 있다. |
| **Solution** | 페이지를 스크린샷(utility.png) 스타일의 "유틸리티" 카탈로그로 전면 교체하고, 이미 존재하는 3개 목록 API(tool-catalog / skills / llm-models)를 기존 훅으로 연동한다. 미들웨어 탭은 "준비 중"으로 표시한다. |
| **Function UX Effect** | 사용자가 탭(도구/모델/미들웨어/스킬) 전환·검색·유형 필터로 플랫폼에서 실제 사용 가능한 유틸리티를 한 화면에서 탐색할 수 있다. |
| **Core Value** | 가짜 데이터 화면 제거로 플랫폼 신뢰도 회복 + Agent Builder에서 쓰는 것과 동일한 카탈로그를 사용자에게 투명하게 노출 (P2 KB 운영자의 도구 파악 비용 절감). |

---

## 1. 배경 / 문제

- 현재 `idt_front/src/pages/ToolConnectionPage/index.tsx`는 `MOCK_TOOLS` 하드코딩 배열(웹 검색, 계산기 등 8종)만 렌더링하며 **서버 연동이 전혀 없다**. 토글도 로컬 state만 바꾸는 가짜 동작이다.
- 반면 백엔드에는 실제 카탈로그 API가 이미 존재한다:

| 자원 | API | 프론트 훅 | 상태 |
|------|-----|----------|------|
| 도구 | `GET /api/v1/tool-catalog` | `useToolCatalog` | ✅ 존재 (AgentBuilder·AdminTools에서 사용 중) |
| 스킬 | `GET /api/v1/skills/list` (scope/search/page) | `useSkills` | ✅ 존재 |
| 모델 | `GET /api/v1/llm-models` | `useLlmModels` | ✅ 존재 |
| 미들웨어 | 없음 | 없음 | ❌ 카탈로그 개념 자체가 서버에 없음 |

- 목표 화면(utility.png): 상단 탭(도구/모델/미들웨어/스킬), 검색창, 유형 필터 칩(built-in/custom/mcp-stdio/mcp-http/http), 태그 칩, 설치됨 배지, 카드 그리드, 새로고침 버튼.

## 2. 확정된 결정 사항 (사용자 Q&A, 2026-08-02)

| # | 질문 | 결정 |
|---|------|------|
| D1 | 실연동 탭 범위 | **도구 + 스킬 + 모델** 3탭 실연동. 미들웨어 탭은 UI만 두고 "준비 중" 표시 (신규 백엔드 API 없음) |
| D2 | 설치됨/미설치 배지 | **1차 제외**. 카탈로그에 있는 항목은 전부 사용 가능한 것으로 간주 |
| D3 | 라우트 | **`/tool-connection` 경로 유지, 페이지 내용 전면 교체**. 네비 라벨만 '도구 연결' → '유틸리티' |
| D4 | 태그/유형 필터 | **기존 필드로만 구현**. 유형 필터는 `source`+`is_builtin` 매핑, 검색은 이름·설명 클라이언트 필터. 태그 시스템은 후속 |

## 3. 목표 (Goals)

1. `/tool-connection`에서 목데이터를 완전히 제거하고 실제 서버 데이터를 표시한다.
2. 탭 4개(도구/모델/미들웨어/스킬)를 제공하며, 도구·모델·스킬 3탭은 실데이터, 미들웨어 탭은 "준비 중" 빈 상태를 보여준다.
3. 스크린샷 수준의 탐색 UX: 검색창(클라이언트 필터), 유형 필터 칩, 카드 그리드, 새로고침.
4. 기존 훅(`useToolCatalog`, `useSkills`, `useLlmModels`) 재사용 — 신규 API·신규 서비스 함수 0.

## 4. 비목표 (Non-Goals / Out of Scope)

- ❌ 백엔드 변경 일체 (API·스키마·마이그레이션 0)
- ❌ 미들웨어 카탈로그 API 신설 → 후속 기능 (`middleware-catalog`)
- ❌ 설치됨/미설치 상태 판정·배지 (D2)
- ❌ 태그 컬럼 추가 및 태그 필터 (D4) → 후속
- ❌ 상단 "전체/워크스페이스" 스코프 탭 — 스킬만 scope 개념이 있고 도구·모델은 없어 탭별 의미가 불일치하므로 1차 제외 (스킬 탭은 scope=all 고정)
- ❌ 이 페이지에서의 도구 활성/비활성 토글 — 빌트인 토글은 관리자용 `/tool-admin`(AdminToolsPage)의 역할이므로 중복 구현하지 않음. 본 페이지는 **읽기 전용 카탈로그 열람**
- ❌ MCP 도구 동기화(`POST /tool-catalog/sync`) 버튼 — 관리자 기능. "새로고침"은 React Query invalidate(재조회)만 수행

## 5. 기능 요구사항 (FR)

### FR-01 페이지 골격 교체
- `/tool-connection` 라우트가 신규 `UtilityPage`를 렌더링한다 (기존 ToolConnectionPage 대체).
- 헤더: 제목 "유틸리티" + 부제 "사용 가능한 도구, 모델, 미들웨어를 찾아보고 추가하세요" + 우측 새로고침 버튼.
- 네비 라벨 변경: TopNav·Sidebar·AppSidebar의 '도구 연결' → '유틸리티' (경로 불변).

### FR-02 카테고리 탭
- 탭 4개: 도구(기본 선택) / 모델 / 미들웨어 / 스킬.
- 탭 전환 시 해당 자원 목록으로 그리드가 교체된다.
- 미들웨어 탭: "준비 중입니다" 빈 상태 안내만 표시 (API 호출 없음).

### FR-03 도구 탭 (useToolCatalog)
- `GET /api/v1/tool-catalog` 응답의 `tools[]`를 카드로 렌더링: 이름(name), 설명(description), 유형 배지.
- 유형 배지 매핑: `source=internal & is_builtin=true` → `built-in`, `source=internal & is_builtin=false` → `custom`, `source=mcp` → `mcp`. (스크린샷의 mcp-stdio/mcp-http/http 세분화는 서버 데이터에 없으므로 `mcp` 단일 배지)
- 유형 필터 칩: 전체 / built-in / custom / mcp — 클라이언트 필터.
- `requires_env`가 비어있지 않으면 카드에 필요한 환경변수 키를 보조 정보로 표시.

### FR-04 스킬 탭 (useSkills)
- `GET /api/v1/skills/list?scope=all` 응답의 `skills[]`를 카드로 렌더링: 이름, 설명, `script_type`·`visibility` 배지.
- 서버 페이지네이션 존재 → 1차는 size 상향(예: 100) 단일 조회로 단순화하고, total 초과 시 "더 보기"는 후속. (플랜 확정 시 재검토)

### FR-05 모델 탭 (useLlmModels)
- `GET /api/v1/llm-models` 응답의 모델 목록을 카드로 렌더링: 모델명, provider, 활성 여부 배지.
- 비활성 모델은 흐리게 표시(또는 배지)하되 목록에는 포함.

### FR-06 검색
- 검색창 입력 시 현재 탭 목록을 이름+설명 대상 클라이언트 필터 (debounce 불필요, 로컬 필터).

### FR-07 새로고침
- 새로고침 버튼 클릭 시 현재 탭의 React Query 캐시를 invalidate하여 재조회.

## 6. 구현 대상 파일 (예상)

| 파일 | 작업 |
|------|------|
| `src/pages/UtilityPage/index.tsx` | 신설 — 페이지 골격(탭·검색·필터·그리드) |
| `src/pages/UtilityPage/UtilityCard.tsx` | 신설 — 자원 공통 카드 (이름/설명/배지 슬롯) |
| `src/pages/UtilityPage/index.test.tsx` | 신설 — MSW 기반 탭·필터·검색·빈상태 테스트 |
| `src/App.tsx` | `/tool-connection` element를 UtilityPage로 교체 |
| `src/components/layout/TopNav.tsx` | 라벨 '도구 연결'→'유틸리티', 설명 문구 갱신 |
| `src/components/layout/Sidebar.tsx`, `AppSidebar.tsx` | 라벨 동일 갱신 (관련 테스트 단언 동기화) |
| `src/pages/ToolConnectionPage/` | 삭제 (mock 전용, 테스트 없음) |
| `src/types/tool.ts` | ToolConnectionPage 전용 mock 타입 정리 — 다른 사용처 확인 후 미사용 항목 제거 |

- 재사용: `useToolCatalog`, `useSkills`, `useLlmModels`, `constants/api.ts` (변경 없음)

## 7. 테스트 전략 (TDD)

- Vitest + RTL + MSW (`--pool=threads`, 파일별 server.listen 3종 훅 직접 선언).
- 케이스: ① 도구 탭 기본 렌더(카탈로그 카드), ② 유형 필터 동작, ③ 검색 필터 동작, ④ 스킬/모델 탭 전환 시 각 목록 렌더, ⑤ 미들웨어 탭 빈 상태, ⑥ API 실패 시 에러 상태, ⑦ 네비 라벨 '유틸리티' 단언.
- 기존 `TopNav.test.tsx`·`AppSidebar.test.tsx` 등에서 '도구 연결' 라벨 단언 여부 확인 후 동기화.

## 8. 리스크 / 주의

| 리스크 | 대응 |
|--------|------|
| 워킹트리에 admin-nav-restructure 미커밋 변경(TopNav 등)이 있음 | 해당 기능 커밋 후 본 작업 착수 권장 — 같은 파일(TopNav) 충돌 방지 |
| `@/types/tool`의 mock 타입을 다른 화면이 참조할 가능성 | 삭제 전 참조 검색으로 확인, 사용처 있으면 보존 |
| 스킬 `/list` 응답의 can_edit 등 권한 필드 | 본 페이지는 열람 전용이므로 사용하지 않음 (표시 정보만 소비) |
| 사전 실패 테스트 존재(프론트 8건) | 신규 회귀로 오인 금지 — 격리 실행으로 검증 |

## 9. 성공 기준

- [ ] `/tool-connection` 접속 시 목데이터가 아닌 서버 데이터(도구·스킬·모델)가 표시된다.
- [ ] 탭 4개 전환·검색·유형 필터·새로고침이 동작한다.
- [ ] 백엔드 diff 0, 신규 프론트 서비스 함수 0 (기존 훅만 재사용).
- [ ] 신규 테스트 전체 통과 + 기존 테스트 무회귀(사전 실패 8건 제외).

## 10. 후속 기능 (Backlog)

1. `middleware-catalog` — 미들웨어 카탈로그 API + 탭 실연동
2. 도구 태그 시스템 (tags 컬럼 + 필터)
3. 설치됨/미설치 판정 (requires_env 충족 or MCP 연결 상태)
4. 스킬 탭 페이지네이션("더 보기") 및 전체/워크스페이스 스코프 탭
