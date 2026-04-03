# TOOL-001 — 도구 연결 페이지

## 상태: 완료 (Mock 데이터)

## 목표
AI 에이전트에 연결할 도구(Tool)를 탐색하고 활성화/비활성화하는 관리 페이지.

## 구현 완료 항목

### 타입
- [x] `src/types/tool.ts` — `Tool`, `ToolCategory`, `TOOL_CATEGORY`, `TOOL_CATEGORY_LABEL`, `ToolToggleRequest/Response`

### 상수
- [x] `src/constants/api.ts` — `TOOLS`, `TOOL_TOGGLE(toolId)` 엔드포인트 추가

### 서비스
- [x] `src/services/toolService.ts` — `getTools()`, `toggleTool(req)` (API 연동 준비)

### 페이지
- [x] `src/pages/ToolConnectionPage/index.tsx` — 전체 페이지 구현

### 라우터
- [x] `src/App.tsx` — `/tool-connection` 라우트 추가

### 네비게이션
- [x] `src/components/layout/TopNav.tsx` — "에이전트" 드롭다운에 "도구 연결" 추가
- [x] `src/components/layout/Sidebar.tsx` — "도구 연결" 사이드바 항목 추가

## UI 구성

### 헤더
- 도구 아이콘 + 제목 "도구 연결" + 서브타이틀
- 활성 도구 카운트 표시 (X개 / 전체)

### 필터 탭
- 전체 | 검색 | 실행 | API | 데이터

### 도구 카드 (3열 그리드)
- 아이콘 (활성: 보라 그라디언트, 비활성: 회색)
- 이름 + 버전
- 설명
- 카테고리 뱃지 (색상별 구분)
- 활성 표시 (emerald 점 + 애니메이션)
- 토글 스위치 (violet-600)

### 활성 도구 요약 섹션
- 활성화된 도구를 뱃지 형태로 나열

## 카테고리 색상 체계
| 카테고리 | 배지 색상 |
|---------|---------|
| 검색 | sky (파랑) |
| 실행 | amber (노랑) |
| API | emerald (초록) |
| 데이터 | violet (보라) |

## Mock 도구 목록 (9개)
| ID | 이름 | 카테고리 | 기본 활성 |
|----|------|---------|--------|
| web-search | 웹 검색 | search | O |
| news-search | 뉴스 검색 | search | O |
| code-execution | 코드 실행 | execution | X |
| file-reader | 파일 읽기 | execution | X |
| calculator | 계산기 | execution | O |
| http-request | HTTP 요청 | api | O |
| email | 이메일 전송 | api | X |
| sql-query | SQL 쿼리 | data | O |
| vector-search | 벡터 검색 | data | X |

## API 연동 (예정)
- `GET /api/tools` → 전체 도구 목록
- `PATCH /api/tools/{toolId}/toggle` → 활성화 상태 변경
- 현재: 로컬 useState로 토글 상태 관리
