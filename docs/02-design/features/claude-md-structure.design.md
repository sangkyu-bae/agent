# Design: sangplusbot 모노레포 CLAUDE.md 구성 전략

> Created: 2026-04-01  
> Feature: claude-md-structure  
> Phase: Design  
> Reference Plan: docs/01-plan/features/claude-md-structure.plan.md

---

## 1. 생성/수정할 파일 목록

| 파일 경로 | 작업 | 우선순위 |
|-----------|------|----------|
| `CLAUDE.md` | 신규 생성 | 필수 |
| `.claude/skills/fullstack-feature.md` | 신규 생성 | 필수 |
| `.claude/skills/api-contract-sync.md` | 신규 생성 | 필수 |
| `idt/CLAUDE.md` | 1줄 추가 | 선택 |
| `idt_front/CLAUDE.md` | 1줄 추가 | 선택 |

---

## 2. 파일별 상세 설계

---

### 파일 1: `CLAUDE.md` (루트 내비게이터)

**목적**: Claude가 루트에서 실행될 때 전체 프로젝트 구조를 즉시 파악하고 올바른 서브프로젝트로 안내

**설계 원칙**:
- 각 서브프로젝트 CLAUDE.md 내용을 절대 중복하지 않음
- 내비게이터 역할에 집중: "무엇을 해야 하면 어디로 가라"
- 최대 100줄 이내 (간결함 유지)

**전체 내용 설계**:

```markdown
# sangplusbot — AI Agent Platform

> 이 파일은 루트 레벨 내비게이터입니다.
> 각 서브프로젝트의 상세 규칙은 해당 디렉토리의 CLAUDE.md를 참조하세요.

---

## 1. 프로젝트 개요

RAG(검색 증강 생성) 기반 문서 질의응답 및 AI Agent 대화 플랫폼.
금융/정책 문서에 특화된 보수적 동작과 예측 가능한 Agent 확장을 목표로 한다.

- **백엔드** (`idt/`): Python 3.11 + FastAPI + LangGraph/LangChain + MySQL + Qdrant
- **프론트엔드** (`idt_front/`): React 19 + TypeScript + Zustand + TanStack Query

---

## 2. 워크스페이스 구조

\`\`\`
sangplusbot/
├── idt/           → 백엔드 API 서버      → 규칙: idt/CLAUDE.md
├── idt_front/     → 웹 UI (React SPA)    → 규칙: idt_front/CLAUDE.md
└── docs/          → 루트 레벨 PDCA 문서  → cross-project 기능 설계
\`\`\`

---

## 3. 작업 진입점 가이드

요청 내용에 따라 즉시 해당 디렉토리로 이동하여 해당 CLAUDE.md를 읽고 작업한다.

| 요청 유형 | 작업 디렉토리 | 참조 CLAUDE.md |
|-----------|--------------|----------------|
| API 엔드포인트 추가/수정 | `idt/` | `idt/CLAUDE.md` |
| LangGraph Agent / RAG 파이프라인 | `idt/` | `idt/CLAUDE.md` |
| DB 스키마 / 마이그레이션 | `idt/` | `idt/CLAUDE.md` |
| UI 컴포넌트 / 페이지 추가 | `idt_front/` | `idt_front/CLAUDE.md` |
| 상태관리 / API 연동 (프론트) | `idt_front/` | `idt_front/CLAUDE.md` |
| 풀스택 기능 (API + UI 동시) | 두 디렉토리 모두 | 두 CLAUDE.md 모두 |

---

## 4. Cross-Project 규칙

### 4-1. API 계약 동기화 (필수)
백엔드 API 스키마를 변경하면 **반드시** 프론트엔드 타입도 함께 수정한다.

| 백엔드 (idt/) | 프론트엔드 (idt_front/) |
|---------------|------------------------|
| `src/interfaces/schemas/` | `src/types/` |
| `src/api/routes/` | `src/services/` + `src/hooks/` |

엔드포인트 상수 위치: `idt_front/src/constants/api.ts`

### 4-2. 환경변수 관리
\`\`\`
백엔드 (idt/.env):
  OPENAI_API_KEY, MYSQL_HOST/PORT/USER/PASS/DB
  QDRANT_URL, QDRANT_API_KEY
  TAVILY_API_KEY, PERPLEXITY_API_KEY

프론트엔드 (idt_front/.env.local):
  VITE_API_BASE_URL=http://localhost:8000
  VITE_WS_URL=ws://localhost:8000
\`\`\`

### 4-3. 개발 서버 실행
\`\`\`bash
# 터미널 1 — 백엔드 (idt/ 에서)
uvicorn src.main:app --reload --port 8000

# 터미널 2 — 프론트엔드 (idt_front/ 에서)
npm run dev
\`\`\`

### 4-4. TDD 공통 원칙
두 프로젝트 모두 **테스트 없이 구현 코드를 먼저 작성하지 않는다**.
- 백엔드: pytest (Red → Green → Refactor)
- 프론트: Vitest + React Testing Library + MSW

---

## 5. 루트 레벨 커스텀 스킬

\`\`\`
/fullstack-feature   → 풀스택 기능 구현 순서 가이드
/api-contract-sync   → 백엔드↔프론트 타입 동기화 체크리스트
\`\`\`

백엔드/프론트엔드 전용 스킬은 각 서브프로젝트의 `.claude/skills/` 참조.
```

---

### 파일 2: `.claude/skills/fullstack-feature.md`

**목적**: 풀스택 기능 구현 시 백엔드→프론트엔드 순서와 체크포인트를 Claude에게 강제

**설계 원칙**:
- 순서가 명확해야 함 (백엔드 먼저, 프론트 나중)
- 각 단계에서 멈추고 확인하는 체크포인트 포함
- 타입 동기화를 반드시 포함

**전체 내용 설계**:

```markdown
# Skill: fullstack-feature

풀스택 기능 구현 시 반드시 아래 순서를 따른다.
이 순서를 건너뛰거나 동시에 진행하지 않는다.

## 구현 순서

### Step 1: 도메인 설계 (idt/)
- [ ] `idt/CLAUDE.md` 읽기
- [ ] `idt/src/domain/` 에 Entity/ValueObject 설계
- [ ] `idt/src/interfaces/schemas/` 에 Request/Response 스키마 정의
- [ ] 스키마 확정 전 프론트 작업 시작 금지

### Step 2: 백엔드 구현 (idt/)
- [ ] TDD: pytest 테스트 먼저 작성
- [ ] `idt/src/application/` UseCase 구현
- [ ] `idt/src/infrastructure/` Adapter 구현
- [ ] `idt/src/api/routes/` 라우터 등록
- [ ] API 정상 동작 확인 (uvicorn 실행 후 테스트)

### Step 3: 타입 동기화 (idt_front/)
- [ ] `idt/src/interfaces/schemas/` 스키마 확인
- [ ] `idt_front/src/types/` TypeScript 타입 반영
- [ ] `idt_front/src/constants/api.ts` 엔드포인트 상수 추가

### Step 4: 프론트엔드 구현 (idt_front/)
- [ ] `idt_front/CLAUDE.md` 읽기
- [ ] TDD: Vitest 테스트 먼저 작성 (MSW 핸들러 포함)
- [ ] `idt_front/src/services/` API 서비스 구현
- [ ] `idt_front/src/hooks/` TanStack Query 훅 구현
- [ ] `idt_front/src/components/` 또는 `pages/` UI 구현

### Step 5: 통합 확인
- [ ] 백엔드 서버 실행 (port 8000)
- [ ] 프론트 서버 실행 (npm run dev)
- [ ] 실제 API 연동 동작 확인
- [ ] 타입 오류 없음 확인 (tsc --noEmit)

## 주의사항
- Step 1 완료 전 Step 4 진행 금지
- 백엔드 스키마 변경 시 Step 3부터 재실행
- WebSocket API는 `idt_front/.env.local`의 VITE_WS_URL 확인
```

---

### 파일 3: `.claude/skills/api-contract-sync.md`

**목적**: 백엔드 API 변경 시 프론트 타입 누락을 방지하는 체크리스트

**전체 내용 설계**:

```markdown
# Skill: api-contract-sync

백엔드 API(스키마/엔드포인트)를 변경할 때마다 이 체크리스트를 실행한다.

## 트리거 조건
다음 파일이 변경된 경우 이 스킬을 실행한다:
- `idt/src/interfaces/schemas/*.py`
- `idt/src/api/routes/*.py`

## 동기화 체크리스트

### 1. 변경 내용 파악
- [ ] 어떤 Request/Response 스키마가 변경되었는가?
- [ ] 새로운 필드가 추가되었는가? (필수/선택 여부 확인)
- [ ] 기존 필드가 삭제/변경되었는가?
- [ ] 엔드포인트 URL이 변경되었는가?

### 2. 프론트엔드 타입 동기화
변경된 스키마에 해당하는 파일을 순서대로 수정:

| 백엔드 변경 위치 | 프론트엔드 동기화 위치 |
|-----------------|----------------------|
| `schemas/{name}Request` | `idt_front/src/types/{name}.ts` |
| `schemas/{name}Response` | `idt_front/src/types/{name}.ts` |
| `routes/{name}_router.py` URL 변경 | `idt_front/src/constants/api.ts` |

### 3. 서비스/훅 업데이트
- [ ] `idt_front/src/services/{name}Service.ts` 파라미터 타입 확인
- [ ] `idt_front/src/hooks/use{Name}.ts` 반환 타입 확인

### 4. 검증
- [ ] `tsc --noEmit` 실행 — TypeScript 오류 없음 확인
- [ ] MSW 핸들러 (`src/mocks/handlers.ts`) 응답 스키마 업데이트

## 주의사항
- 백엔드 Optional 필드 → 프론트에서 `field?: type` 으로 표현
- 백엔드 `List[T]` → 프론트에서 `T[]` 으로 표현
- 백엔드 `datetime` → 프론트에서 `string` (ISO 8601)
- 백엔드 `Enum` → 프론트에서 `as const` 또는 TypeScript `enum`
```

---

## 3. 구현 순서

```
Step 1: 루트 디렉토리에 CLAUDE.md 생성
Step 2: .claude/skills/ 디렉토리 생성
Step 3: fullstack-feature.md 스킬 생성
Step 4: api-contract-sync.md 스킬 생성
Step 5: (선택) idt/CLAUDE.md 에 cross-reference 1줄 추가
Step 6: (선택) idt_front/CLAUDE.md 에 cross-reference 1줄 추가
```

---

## 4. 검증 기준

| 검증 항목 | 확인 방법 |
|-----------|----------|
| 루트 CLAUDE.md 100줄 이내 | `wc -l CLAUDE.md` |
| 각 서브 CLAUDE.md 내용 중복 없음 | 내용 대조 |
| 스킬 파일 마크다운 문법 정상 | 파일 읽기 확인 |
| 작업 진입점 테이블 완전성 | 주요 요청 유형 모두 포함 여부 |

---

## 5. 구현 후 검증 질문

설계 완료 후 아래 질문에 Claude가 바르게 답할 수 있으면 성공:

1. "Agent 기능 추가해줘" → `idt/` 디렉토리, LangGraph 관련 파일 수정
2. "채팅 UI 개선해줘" → `idt_front/` 디렉토리, components/chat/ 수정
3. "새 API 추가하고 화면도 만들어줘" → fullstack-feature 스킬 실행, Step 1부터 순서대로
4. "API 응답 필드 추가됐어" → api-contract-sync 스킬 실행, 타입 동기화 체크리스트
