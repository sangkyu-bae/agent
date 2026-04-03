# Plan: sangplusbot 모노레포 CLAUDE.md 구성 전략

> Created: 2026-04-01  
> Feature: claude-md-structure  
> Phase: Plan

---

## 1. 배경 및 목적

### 현재 상황

```
sangplusbot/               ← 루트 (CLAUDE.md 없음)
├── idt/                   ← 백엔드 (Python/FastAPI/LangGraph, CLAUDE.md 있음)
│   └── CLAUDE.md          ← Thin DDD + TDD + 49개 Task 규칙 정의
└── idt_front/             ← 프론트엔드 (React/TypeScript, CLAUDE.md 있음)
    └── CLAUDE.md          ← React 19 + TDD + 상태관리 규칙 정의
```

### 문제점

- 루트에 CLAUDE.md가 없어 Claude가 **전체 프로젝트 컨텍스트를 파악하지 못함**
- 루트에서 작업 시작 시 어느 서브프로젝트를 다뤄야 할지 방향 없음
- 백엔드↔프론트엔드 연계 작업 시 cross-cutting 규칙이 명시되지 않음
- 스킬이 각 서브프로젝트에만 분산되어 있고 루트 레벨 스킬 없음

### 목표

- 루트 CLAUDE.md를 **"전체 시스템 내비게이터"** 로 구성
- 각 서브프로젝트 CLAUDE.md는 현행 유지 (이미 잘 작성됨)
- 루트 레벨 커스텀 스킬 추가로 cross-project 작업 효율화

---

## 2. 루트 CLAUDE.md 구성 전략

### 핵심 원칙: "내비게이터 역할, 중복 금지"

루트 CLAUDE.md는 각 서브프로젝트의 규칙을 **복사하지 않는다**.  
대신 Claude가 작업 시작 시 **어디로 가야 하는지**, **어떻게 두 프로젝트가 연결되는지**를 명시한다.

### 권장 루트 CLAUDE.md 구조

```markdown
# sangplusbot — AI Agent Platform

## 1. 프로젝트 개요
(전체 시스템 설명: 무엇을 하는 AI 플랫폼인지 1~3문장)

## 2. 워크스페이스 구조
(서브프로젝트 역할 설명 + CLAUDE.md 위치 안내)

## 3. 작업 진입점 가이드
(요청 유형별로 어느 디렉토리에서 작업해야 하는지)

## 4. Cross-Project 규칙
(API 계약, 타입 동기화, 환경변수 관리 등 두 프로젝트에 걸친 규칙)

## 5. 루트 레벨 스킬 안내
(사용 가능한 커스텀 스킬 목록)
```

---

## 3. 루트 CLAUDE.md 세부 내용 설계

### Section 1: 프로젝트 개요 (5줄 이내)
- AI Agent 플랫폼명 및 목적
- 기술 스택 요약 (백엔드: Python/FastAPI, 프론트엔드: React/TypeScript)
- 서비스 도메인 (RAG 기반 문서 질의응답, 에이전트 대화)

### Section 2: 워크스페이스 구조
```
idt/          → 백엔드 API 서버 (규칙: idt/CLAUDE.md)
idt_front/    → 웹 UI (규칙: idt_front/CLAUDE.md)
docs/         → 루트 레벨 PDCA 문서 (cross-project 기능)
```

### Section 3: 작업 진입점 가이드
Claude가 요청을 받았을 때 **즉시 방향을 잡을 수 있도록** 명시.

| 요청 유형 | 진입 디렉토리 | 참조 CLAUDE.md |
|-----------|--------------|----------------|
| API 엔드포인트 추가/수정 | `idt/` | `idt/CLAUDE.md` |
| LangGraph Agent 개발 | `idt/` | `idt/CLAUDE.md` |
| RAG 파이프라인 수정 | `idt/` | `idt/CLAUDE.md` |
| UI 컴포넌트 추가/수정 | `idt_front/` | `idt_front/CLAUDE.md` |
| 화면 디자인 / 레이아웃 | `idt_front/` | `idt_front/CLAUDE.md` |
| API 연동 (프론트) | `idt_front/` | `idt_front/CLAUDE.md` |
| 새 기능 (풀스택) | 두 프로젝트 모두 | 두 CLAUDE.md 모두 |

### Section 4: Cross-Project 규칙 (가장 중요)

#### 4-1. API 계약 동기화
- 백엔드 API 스키마 변경 시 프론트 타입 반드시 동기 수정
- 참조 경로: `idt/src/interfaces/schemas/` ↔ `idt_front/src/types/`
- 엔드포인트 상수 위치: `idt_front/src/constants/api.ts`

#### 4-2. 환경변수 관리
- 백엔드: `idt/.env` (OPENAI_API_KEY, MYSQL_*, QDRANT_*)
- 프론트: `idt_front/.env.local` (VITE_API_BASE_URL, VITE_WS_URL)
- 로컬 개발 기본값: API=`http://localhost:8000`, WS=`ws://localhost:8000`

#### 4-3. 개발 서버 실행
```bash
# 백엔드: idt/ 에서
uvicorn src.main:app --reload --port 8000

# 프론트엔드: idt_front/ 에서
npm run dev
```

#### 4-4. TDD 공통 원칙
- 백엔드/프론트 **모두 TDD 강제**
- 테스트 없이 구현 코드 먼저 작성 금지
- 백엔드: pytest / 프론트: Vitest + RTL + MSW

### Section 5: 루트 레벨 스킬 안내
(아래 스킬 추천 항목 참고)

---

## 4. 서브프로젝트 CLAUDE.md 개선 권고

### idt/CLAUDE.md (현행 유지 + 1개 추가)
- 현재 구성: 충분히 상세하고 잘 작성됨
- 추가 권고: **프론트엔드 타입 참조 경로** 명시
  ```
  ## API 스키마 변경 시
  - interfaces/schemas/ 수정 후 idt_front/src/types/ 에 반영 요청
  ```

### idt_front/CLAUDE.md (현행 유지 + 1개 추가)
- 현재 구성: 충분히 상세하고 잘 작성됨
- 이미 `../src/api/routes/` 백엔드 참조 경로 명시됨 (양호)
- 추가 권고: **WebSocket 엔드포인트** 동기화 명시

---

## 5. 스킬 구성 전략

### 현재 스킬 현황

| 위치 | 스킬 | 용도 |
|------|------|------|
| idt/.claude/skills/ | langgraph, langchain-middleware, chunk, tdd, verify-* | 백엔드 전용 |
| idt_front/.claude/skills/ | front-end-design, tdd | 프론트 전용 |
| 루트 | **없음** | ← 이 부분 보완 필요 |

### 루트에 추가 권고 스킬

#### 필수 추가 (cross-project 작업용)

| 스킬명 | 설명 | 우선순위 |
|--------|------|----------|
| `fullstack-feature` | 풀스택 기능 구현 시 백/프론트 순서 가이드 (API 설계 → 백엔드 구현 → 타입 동기화 → 프론트 연동) | 높음 |
| `api-contract-sync` | 백엔드 스키마 변경 후 프론트 타입 자동 동기화 체크리스트 | 높음 |

#### 선택 추가 (편의성)

| 스킬명 | 설명 | 우선순위 |
|--------|------|----------|
| `dev-start` | 개발 환경 시작 가이드 (백/프론트 서버 동시 실행 방법) | 중간 |
| `pdca-fullstack` | 풀스택 기능의 PDCA Plan → Design 자동 생성 | 중간 |

### 기존 스킬 활용 권고

#### 백엔드 작업 시 (idt/ 디렉토리)
```
/langgraph          → LangGraph Agent 개발 시
/langchain-middleware → LangChain 미들웨어 추가 시
/chunk              → 문서 청킹 모듈 개발 시
/tdd                → 테스트 주도 개발 시
/verify-architecture → DDD 레이어 검증 시
/verify-logging     → LOG-001 규칙 검증 시
/verify-tdd         → 테스트 존재 여부 검증 시
/api-doc-generator  → API 문서 생성 시
```

#### 프론트엔드 작업 시 (idt_front/ 디렉토리)
```
/front-end-design   → UI 컴포넌트/페이지 개발 시
/tdd                → Vitest 기반 TDD 개발 시
```

---

## 6. 구현 계획

### Phase 1: 루트 CLAUDE.md 생성 (즉시)
- [ ] 루트 CLAUDE.md 파일 신규 작성
- [ ] Section 1~5 내용 작성

### Phase 2: 루트 스킬 추가 (필요시)
- [ ] `fullstack-feature` 스킬 생성
- [ ] `api-contract-sync` 스킬 생성

### Phase 3: 서브프로젝트 CLAUDE.md 보완 (선택)
- [ ] `idt/CLAUDE.md` — 프론트 타입 참조 경로 1줄 추가
- [ ] `idt_front/CLAUDE.md` — WebSocket 동기화 명시 1줄 추가

---

## 7. 최종 권장 파일 구조

```
sangplusbot/
├── CLAUDE.md                    ← [신규] 전체 내비게이터
├── .claude/
│   └── skills/                  ← [신규] 루트 레벨 스킬
│       ├── fullstack-feature.md
│       └── api-contract-sync.md
├── docs/
│   └── 01-plan/features/
│       └── claude-md-structure.plan.md  ← 이 파일
├── idt/
│   ├── CLAUDE.md                ← 현행 유지 (1줄 추가 권고)
│   └── .claude/skills/          ← 현행 유지
└── idt_front/
    ├── CLAUDE.md                ← 현행 유지 (1줄 추가 권고)
    └── .claude/skills/          ← 현행 유지
```

---

## 8. 성공 기준

- [ ] 루트에서 `claude` 실행 시 전체 프로젝트 컨텍스트 즉시 파악 가능
- [ ] "로그인 기능 추가해줘" 같은 요청에서 Claude가 어느 디렉토리를 수정해야 할지 스스로 판단 가능
- [ ] 백엔드 API 변경 시 프론트 타입 누락 없이 동기화
- [ ] 풀스택 기능 구현 시 명확한 작업 순서 가이드 제공
