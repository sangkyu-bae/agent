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

```
sangplusbot/
├── idt/           → 백엔드 API 서버      → 규칙: idt/CLAUDE.md
├── idt_front/     → 웹 UI (React SPA)    → 규칙: idt_front/CLAUDE.md
└── docs/          → 루트 레벨 PDCA 문서  → cross-project 기능 설계
```

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

```
백엔드 (idt/.env):
  OPENAI_API_KEY, MYSQL_HOST/PORT/USER/PASS/DB
  QDRANT_URL, QDRANT_API_KEY
  TAVILY_API_KEY, PERPLEXITY_API_KEY

프론트엔드 (idt_front/.env.local):
  VITE_API_BASE_URL=http://localhost:8000
  VITE_WS_URL=ws://localhost:8000
```

### 4-3. 개발 서버 실행

```bash
# 터미널 1 — 백엔드 (idt/ 에서)
uvicorn src.main:app --reload --port 8000

# 터미널 2 — 프론트엔드 (idt_front/ 에서)
npm run dev
```

### 4-4. TDD 공통 원칙

두 프로젝트 모두 **테스트 없이 구현 코드를 먼저 작성하지 않는다**.
- 백엔드: pytest (Red → Green → Refactor)
- 프론트: Vitest + React Testing Library + MSW

---

## 5. 루트 레벨 커스텀 스킬

```
/fullstack-feature   → 풀스택 기능 구현 순서 가이드
/api-contract-sync   → 백엔드↔프론트 타입 동기화 체크리스트
```

백엔드/프론트엔드 전용 스킬은 각 서브프로젝트의 `.claude/skills/` 참조.
