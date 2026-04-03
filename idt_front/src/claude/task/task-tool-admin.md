# TOOL-ADMIN-001 — 도구 관리 페이지 (어드민)

## 상태: 완료 (Mock 데이터)

## 목표
관리자가 AI 에이전트에서 사용할 도구(Tool)를 직접 정의하고 관리하는 어드민 페이지.
도구 이름·설명, 스키마 파라미터, API 엔드포인트를 추가·수정·삭제할 수 있다.

## 구현 완료 항목

### 타입
- [x] `src/types/toolAdmin.ts`
  - `ToolParamType` — `string | number | boolean | array | object`
  - `HttpMethod` — `GET | POST | PUT | PATCH | DELETE`
  - `ToolSchemaParam` — `{ id, name, type, description, required }`
  - `ToolEndpoint` — `{ id, method, path, description }`
  - `AdminTool` — 전체 도구 도메인 모델
  - `AdminToolFormData` — 폼 입력 전용 타입 (id 없음)
  - `AdminToolCreateRequest / UpdateRequest / Response` — API 연동 준비

### 상수
- [x] `src/constants/api.ts`
  - `ADMIN_TOOLS` — `GET /api/admin/tools`, `POST /api/admin/tools`
  - `ADMIN_TOOL_DETAIL(toolId)` — `GET/PUT/DELETE /api/admin/tools/{toolId}`

### 서비스
- [x] `src/services/toolAdminService.ts`
  - `getTools()` — 전체 도구 목록 조회
  - `createTool(req)` — 도구 생성
  - `updateTool(id, req)` — 도구 수정
  - `deleteTool(id)` — 도구 삭제

### 페이지
- [x] `src/pages/ToolAdminPage/index.tsx`

### 라우터
- [x] `src/App.tsx` — `/tool-admin` 라우트 추가

### 네비게이션
- [x] `src/components/layout/TopNav.tsx` — "에이전트" 드롭다운에 "도구 관리" 추가

## UI 구성

### 헤더
- 설정 아이콘 + "도구 관리" 제목 + "Tool Administration" 서브타이틀
- 도구 검색 인풋
- 활성 도구 카운트 표시
- "도구 추가" 버튼 (violet-600)

### 도구 목록 (테이블)
| 컬럼 | 내용 |
|------|------|
| 도구 | 아이콘 + 이름 + 설명 (max-w-xs truncate) |
| 카테고리 | 색상 뱃지 |
| 스키마 파라미터 | 파라미터명 태그 (최대 3개 표시, 초과 시 +N) |
| 엔드포인트 | METHOD 뱃지 + path (최대 2개 표시) |
| 상태 | 활성/비활성 (emerald 점) |
| 액션 | 수정/삭제 버튼 (hover 시 표시) |

### 도구 추가/수정 모달 (`ToolFormModal`)
- **기본 정보**: 이름*, 설명*, 카테고리 (search/execution/api/data/custom)
- **스키마 파라미터** (동적 추가/삭제):
  - 파라미터명 (font-mono)
  - 타입 select (string/number/boolean/array/object)
  - 설명
  - 필수 여부 checkbox
- **엔드포인트** (동적 추가/삭제):
  - HTTP 메서드 select (GET/POST/PUT/PATCH/DELETE)
  - 경로 (font-mono)
  - 설명

### 삭제 확인 다이얼로그 (`DeleteConfirm`)
- 경고 아이콘 + 도구 이름 표시
- 취소 / 삭제 버튼

## Mock 도구 목록 (3개)
| ID | 이름 | 카테고리 | 파라미터 | 엔드포인트 |
|----|------|---------|---------|---------|
| 1 | 웹 검색 | search | query, max_results | GET /api/tools/web-search |
| 2 | 코드 실행 | execution | code, timeout | POST /run, GET /result/{job_id} |
| 3 | HTTP 요청 | api | url, method, headers, body | POST /api/tools/http-request |

## API 연동 (예정)
- `GET /api/admin/tools` → 전체 도구 목록 조회
- `POST /api/admin/tools` → 신규 도구 생성
- `PUT /api/admin/tools/{toolId}` → 도구 전체 수정
- `DELETE /api/admin/tools/{toolId}` → 도구 삭제
- 현재: `useState`로 CRUD 상태 관리 (localStorage 미사용)
