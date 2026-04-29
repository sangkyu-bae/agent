# 경력기술서

---

## 인적사항

| 항목 | 내용 |
|------|------|
| 이름 | 배상규 |
| 이메일 | tkdrb136@gmail.com |

---

## 프로젝트

### sangplusbot — RAG 기반 문서 질의응답 및 AI Agent 플랫폼

| 항목 | 내용 |
|------|------|
| 기간 | 2026.04 ~ 현재 (진행 중) |
| 구분 | 개인 프로젝트 (1인 기획/설계/개발) |
| 도메인 | 금융/정책 문서 특화 AI 질의응답 시스템 |
| GitHub | (비공개 레포지토리) |

---

### 1. 프로젝트 개요

금융/정책 문서를 업로드하면 자동으로 파싱, 청킹, 벡터화하고, 사용자가 자연어로 질문하면 관련 문서를 검색하여 AI가 출처 기반 답변을 생성하는 풀스택 플랫폼.  
커스텀 AI Agent를 GUI로 생성/관리하고, 다양한 외부 도구(MCP)를 연결하여 업무 자동화에 활용할 수 있는 확장형 아키텍처를 설계/구현하였다.

---

### 2. 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (Async), Pydantic v2 |
| **AI/LLM** | LangChain, LangGraph, OpenAI API, Anthropic API, Ollama |
| **검색 엔진** | Elasticsearch 8 (BM25), Qdrant (Vector DB), Hybrid Search (RRF) |
| **데이터베이스** | MySQL (RDB), Redis (캐시/세션) |
| **Frontend** | React 19, TypeScript, Vite 8, Tailwind CSS v4 |
| **상태관리** | Zustand, TanStack Query v5 |
| **테스트** | pytest, pytest-asyncio (BE) / Vitest, React Testing Library, MSW (FE) |
| **형태소 분석** | Kiwipiepy (한국어 형태소 분석기) |
| **프로토콜** | SSE (Server-Sent Events), WebSocket, MCP (Model Context Protocol) |
| **코드 품질** | Ruff, mypy (strict mode), ESLint |

---

### 3. 아키텍처 설계

#### 3-1. 백엔드: Thin DDD (Domain-Driven Design) 계층형 아키텍처

```
interfaces (FastAPI Router)
    ↓ 요청/응답 변환
application (UseCase / Workflow)
    ↓ 흐름 제어, 오케스트레이션
domain (Entity, Value Object, Policy, Interface)
    ↑ 의존성 역전 (DIP)
infrastructure (MySQL, Qdrant, ES, OpenAI, Redis)
```

**설계 원칙:**
- Domain 레이어는 외부 의존성(DB, API, LLM) 참조를 일체 금지하고, Interface(Protocol)만 정의
- Infrastructure가 Domain Interface를 구현하여 의존성 역전(DIP) 적용
- UseCase는 비즈니스 규칙을 직접 구현하지 않고, Domain Policy에 위임
- FastAPI Depends를 활용한 의존성 주입(DI)으로 테스트 용이성 확보

**적용 규모:**
- Interface 정의: 22개
- Policy/규칙 클래스: 18개
- Value Object: 10개
- Entity: 7개

#### 3-2. 프론트엔드: 관심사 분리 기반 레이어드 구조

```
pages/        → 라우트 단위 페이지 (15개)
components/   → 재사용 UI 컴포넌트 (chat, collection, agent, layout, common)
hooks/        → 커스텀 훅 (비즈니스 로직 캡슐화)
services/     → API 통신 레이어 (컴포넌트에서 직접 호출 금지)
store/        → Zustand 전역 상태 (슬라이스 팩토리 패턴)
types/        → TypeScript 타입 정의 (백엔드 스키마 동기화)
```

---

### 4. 주요 기능 및 구현 상세

#### 4-1. RAG (Retrieval-Augmented Generation) 파이프라인

**문서 인제스트 파이프라인 (LangGraph StateGraph)**

PDF 업로드부터 벡터 저장까지 전체 파이프라인을 LangGraph StateGraph로 구현.

- **Parse 노드**: PyMuPDF / LlamaParse를 통한 PDF 텍스트 추출
- **Classify 노드**: LLM 기반 문서 카테고리 자동 분류 (금융/정책/일반)
- **Chunk 노드**: Strategy 패턴 기반 다중 청킹 전략
  - Full Token Strategy: 고정 토큰 윈도우 청킹
  - Parent-Child Strategy: 계층적 청킹 (부모 청크 → 자식 청크 분할)
  - Semantic Strategy: 의미 단위 청킹
- **Store 노드**: Qdrant 벡터 DB에 임베딩 저장

**하이브리드 검색 엔진**

- Elasticsearch BM25 (키워드 검색) + Qdrant (벡터 유사도 검색) 동시 수행
- RRF (Reciprocal Rank Fusion) 알고리즘으로 두 결과를 통합 랭킹
- Kiwipiepy 한국어 형태소 분석기를 통한 한국어 검색 품질 향상

**할루시네이션 평가 모듈**

- LLM 응답이 참조 문서에 기반하는지 자동 평가
- Domain Policy로 평가 기준을 정의하고, Infrastructure에서 LLM 호출 구현 (DIP 적용)

#### 4-2. AI Agent 시스템

**Custom Agent Builder**

사용자가 GUI에서 AI Agent를 정의하면, 백엔드에서 LangGraph 그래프를 동적으로 컴파일하여 실행.

- **인터뷰 기반 Agent 생성**: 자연어 대화로 Agent의 목적, 도구, 행동 규칙을 정의
- **WorkflowCompiler**: WorkflowDefinition → LangGraph Supervisor + Worker 그래프 동적 변환
- **Multi-LLM 지원**: OpenAI, Anthropic, Ollama 중 선택 가능 (LLM Model Registry)
- **도구 카탈로그**: MCP 프로토콜 기반 외부 도구 등록 및 Agent에 바인딩

**ReAct RAG Agent**

- LangGraph `create_react_agent`를 활용한 ReAct 패턴 구현
- 질문 의도에 따라 내부 문서 검색 도구 호출 여부를 Agent가 자율 판단
- 하이브리드 검색 결과를 바탕으로 출처 기반 답변 생성

**자동 Agent 빌더 (v3)**

- 자연어 설명만으로 Agent 스펙을 자동 추론 (AgentSpecInferenceService)
- 도구 선택, 프롬프트 생성, 워크플로우 구성을 LLM이 자동 수행

#### 4-3. MCP (Model Context Protocol) Tool Registry

- MCP 서버 등록/삭제/목록 조회 CRUD
- 등록된 MCP 서버에서 사용 가능한 도구를 자동 로드
- Agent Builder에서 MCP 도구를 선택하여 Agent에 바인딩

#### 4-4. 인증/인가 시스템

- JWT 기반 인증 (Access Token + Refresh Token)
- 비밀번호 정책을 Domain Policy로 분리
- 관리자 승인 흐름 (회원가입 → pending → 관리자 승인/거부)
- 부서 기반 접근 제어 (부서별 컬렉션 권한 관리)
- Axios Interceptor 기반 자동 토큰 갱신

#### 4-5. 컬렉션 관리 시스템

- 문서 컬렉션 생성/수정/삭제 + 권한(소유자/편집자/뷰어) 관리
- 컬렉션 단위 문서 업로드, 청크 열람, 하이브리드 검색
- 활동 로그 기록 및 조회 (Fire-and-Forget 비동기 로깅)
- 검색 히스토리 저장 및 재실행

#### 4-6. 프론트엔드 주요 구현

- **실시간 스트리밍**: SSE 기반 LLM 응답 실시간 렌더링 (delta 누적 + requestAnimationFrame)
- **WebSocket 훅**: 재연결 로직 포함 범용 WebSocket 커스텀 훅
- **Zustand 슬라이스 팩토리**: LoadingSlice, ListSlice, SelectionSlice 조합으로 보일러플레이트 제거
- **TanStack Query 중앙 관리**: QueryKey 팩토리 패턴, 도메인별 훅으로 서버 상태 관리
- **디자인 시스템**: 색상 토큰, 타이포그래피, 컴포넌트 패턴을 문서화하여 일관된 UI 유지

---

### 5. 테스트 전략 및 커버리지

| 영역 | 테스트 파일 수 | 테스트 코드 라인 | 프로덕션 코드 라인 | 비율 |
|------|--------------|----------------|------------------|------|
| Backend | 391 | 41,562 | 31,673 | 131% |
| Frontend | 14 | 1,765 | 14,029 | 12.6% |

**백엔드 테스트 전략:**
- TDD (Red → Green → Refactor) 사이클 엄수
- 레이어별 단위 테스트: Router / UseCase / Domain Policy / Infrastructure Adapter
- pytest-asyncio를 활용한 비동기 코드 테스트
- FastAPI TestClient를 활용한 API 통합 테스트

**프론트엔드 테스트 전략:**
- Vitest + React Testing Library로 커스텀 훅 단위 테스트
- MSW (Mock Service Worker)로 네트워크 레벨 API 모킹
- 컴포넌트 렌더링 + 사용자 인터랙션 테스트

---

### 6. 개발 프로세스 및 방법론

| 항목 | 적용 내용 |
|------|----------|
| **버전 관리** | Feature Branch + Pull Request 기반 워크플로 (15개 PR 머지) |
| **코드 컨벤션** | CLAUDE.md에 레이어 규칙, 금지 행위, 네이밍 규칙 명문화 |
| **DB 마이그레이션** | Flyway 형식 SQL 마이그레이션 (V002 ~ V015, 14개 버전) |
| **린팅/타입 체크** | Ruff + mypy strict (BE), ESLint + tsc --noEmit (FE) |
| **PDCA 사이클** | Plan → Design → Do → Check(Gap Analysis) → Act(Iterate) |

---

### 7. 정량적 성과

| 지표 | 수치 |
|------|------|
| 백엔드 소스 파일 | 518개 |
| 백엔드 테스트 파일 | 391개 |
| 프론트엔드 소스 파일 | 128개 |
| API 엔드포인트 (라우터) | 30개 |
| 도메인 모듈 | 47개 |
| DDD Interface 정의 | 22개 |
| DDD Policy 클래스 | 18개 |
| DB 마이그레이션 | 14개 버전 |
| 프론트엔드 페이지 | 15개 |
| PR 머지 | 15회 |
| Feature 브랜치 | 12개 |

---

### 8. 이 프로젝트에서 얻은 역량

| 역량 | 상세 |
|------|------|
| **AI/LLM 엔지니어링** | LangGraph StateGraph 설계, ReAct Agent 구현, 하이브리드 검색 엔진 구축, 할루시네이션 평가 파이프라인 |
| **백엔드 아키텍처** | DDD 계층 설계, 의존성 역전(DIP), Policy 패턴, Strategy 패턴, FastAPI DI |
| **풀스택 개발** | Python + TypeScript 동시 개발, API 계약 동기화, 프론트-백엔드 일관된 타입 체계 |
| **테스트 주도 개발** | TDD 사이클 실천, 레이어별 테스트 전략 수립, 테스트 코드 비율 131% 달성 |
| **검색 시스템** | Elasticsearch BM25 + Qdrant Vector 하이브리드, RRF 랭킹, 한국어 형태소 분석 적용 |
| **프로젝트 관리** | 1인 개발 환경에서 Feature Branch 워크플로, 코드 컨벤션 문서화, PDCA 사이클 적용 |

---

### 9. 향후 개선 계획

| 항목 | 계획 |
|------|------|
| 배포 인프라 | Docker Compose 기반 통합 환경 구축 → 클라우드 배포 |
| CI/CD | GitHub Actions 기반 자동 테스트/빌드/배포 파이프라인 |
| 모니터링 | 구조화된 로그 수집 + 알림 시스템 구축 |
| 성능 최적화 | 벡터 검색 캐싱, 대용량 문서 처리 최적화 |
| 프론트엔드 테스트 강화 | 컴포넌트 테스트 커버리지 60% 이상 확보 |

---

*작성일: 2026-04-29*
