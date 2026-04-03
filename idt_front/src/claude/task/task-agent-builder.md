# AGENT-001 — 에이전트 만들기 페이지

## 상태: 완료 (Mock 데이터)

## 목표
AI 에이전트를 생성·수정·관리하는 페이지.
리스트 뷰(카드 그리드)와 폼 뷰(생성/수정) 두 가지 뷰 상태를 전환하며 운영.

## 구현 완료 항목

### 페이지
- [x] `src/pages/AgentBuilderPage/index.tsx` — 전체 페이지 구현

### 라우터
- [x] `src/App.tsx` — `/agent-builder` 라우트 (기존)

### 네비게이션
- [x] `src/components/layout/TopNav.tsx` — "에이전트" 드롭다운에 "에이전트 만들기" 존재
- [x] `src/components/layout/Sidebar.tsx` — "에이전트 만들기" 사이드바 항목 존재

## UI 구성

### 뷰 상태 머신
```
'list' ↔ 'create' | 'edit'
```

### 리스트 뷰 (view === 'list')

#### 헤더
- 아이콘 + 제목 "에이전트 만들기" + 서브타이틀 "Agent Builder"
- 활성 에이전트 카운트 (X개 활성 / 전체 N개)
- "새 에이전트" 버튼 (violet-600)

#### 에이전트 카드 (3열 그리드)
- 그라디언트 이니셜 아바타 (2글자) + 이름 + 모델 배지
- 토글 스위치 (우측 상단)
- 설명 (2줄 clamp)
- 시스템 프롬프트 미리보기 (1줄 italic, bg-zinc-50)
- 도구 태그 (pill 형태)
- 실행 횟수 + 생성일 + 수정/삭제 버튼 (hover 시 노출)

#### 활성 에이전트 요약 섹션
- 활성화된 에이전트를 뱃지 형태로 나열

### 폼 뷰 (view === 'create' | 'edit')

#### 헤더
- "새 에이전트" / "에이전트 수정" + "취소" / "저장" 버튼

#### 폼 필드
- 이름 (required, text input)
- 설명 (text input)
- 모델 (4열 토글 버튼: Claude Sonnet 4.6 / Haiku 4.5 / Opus 4.6 / GPT-4o)
- 시스템 프롬프트 (6줄 textarea, focus-within border 효과)
- 도구 연결 (2열 체크박스 그리드, 6개 도구)
- Temperature (range slider 0~1, step 0.1, 값 실시간 표시)

## 모델 목록
| ID | 레이블 | 색상 배지 |
|----|--------|---------|
| claude-sonnet-4-6 | Claude Sonnet 4.6 | violet |
| claude-haiku-4-5 | Claude Haiku 4.5 | sky |
| claude-opus-4-6 | Claude Opus 4.6 | amber |
| gpt-4o | GPT-4o | emerald |

## 도구 목록 (6개)
| ID | 레이블 |
|----|--------|
| web-search | 웹 검색 |
| code-exec | 코드 실행 |
| file-read | 파일 읽기 |
| db-query | DB 쿼리 |
| api-call | API 호출 |
| rag-retrieval | RAG 검색 |

## Mock 에이전트 목록 (3개)
| ID | 이름 | 모델 | 도구 | 기본 활성 |
|----|------|------|------|---------|
| doc-analyst | 문서 분석가 | claude-sonnet-4-6 | file-read, rag-retrieval | O |
| code-reviewer | 코드 리뷰어 | claude-opus-4-6 | code-exec, web-search | O |
| data-analyst | 데이터 분석가 | claude-sonnet-4-6 | code-exec, db-query, api-call | X |

## API 연동 (예정)
- `GET /api/agents` → 에이전트 목록 조회
- `POST /api/agents` → 에이전트 생성
- `PUT /api/agents/{id}` → 에이전트 수정
- `DELETE /api/agents/{id}` → 에이전트 삭제
- `PATCH /api/agents/{id}/toggle` → 활성화 토글
- 현재: 로컬 useState로 상태 관리
