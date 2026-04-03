# IDT (Intelligent Document Toolkit) — 기술 포트폴리오

> **최종 업데이트**: 2026-03-25
> **버전**: 1.0
> **상태**: 프로덕션 준비 완료 ✅

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [기술 스택](#2-기술-스택)
3. [아키텍처 설계](#3-아키텍처-설계)
4. [구현된 모듈 목록](#4-구현된-모듈-목록)
5. [핵심 기능 상세](#5-핵심-기능-상세)
6. [API 엔드포인트 전체 목록](#6-api-엔드포인트-전체-목록)
7. [PDCA 완료 이력](#7-pdca-완료-이력)
8. [품질 지표](#8-품질-지표)
9. [아키텍처 결정 기록 (ADR)](#9-아키텍처-결정-기록-adr)
10. [설계 원칙 및 코딩 컨벤션](#10-설계-원칙-및-코딩-컨벤션)

---

## 1. 프로젝트 개요

**IDT(Intelligent Document Toolkit)**는 금융·정책 문서 처리에 특화된 **AI 기반 문서 질의응답 + 에이전트 빌딩 플랫폼**입니다.

### 핵심 가치 제안

| 문제 | 해결 방법 |
|------|----------|
| 대용량 PDF/엑셀 문서에서 정보 추출 어려움 | LlamaParse/PyMuPDF + 계층적 청킹(Parent-Child) |
| 벡터 검색만으로는 키워드 누락 발생 | BM25 + 벡터 RRF 병합 하이브리드 검색 |
| LLM 할루시네이션으로 신뢰도 하락 | Self-Corrective Agent + 할루시네이션 평가기 |
| 도구 조합 에이전트 구축의 복잡성 | Auto Agent Builder (자연어 → 에이전트 자동 생성) |
| 외부 MCP 도구 연동의 어려움 | Dynamic MCP Registry (DB 기반 런타임 등록) |

### 전체 처리 흐름

```
[문서 업로드] ──→ [파싱 (LlamaParse / PyMuPDF)]
                        ↓
                [청킹 (Full-Token / Parent-Child / Semantic)]
                        ↓
         ┌──────────────┴───────────────┐
   [Qdrant 벡터 저장]         [Elasticsearch BM25 색인]
         └──────────────┬───────────────┘
                        ↓
              [사용자 질의 (자연어)]
                        ↓
           [하이브리드 검색 (RRF 병합)]
                        ↓
           [LLM 문서 압축 & 답변 생성]
                        ↓
              [할루시네이션 평가 → 재시도]
                        ↓
                  [최종 응답 반환]
```

---

## 2. 기술 스택

### 백엔드 코어

| 범주 | 기술 | 버전 | 용도 |
|------|------|------|------|
| 언어 | Python | 3.11+ | 전체 백엔드 |
| 웹 프레임워크 | FastAPI | 최신 | REST API |
| AI 오케스트레이션 | LangChain | 최신 | LLM 통합, 도구, 미들웨어 |
| 에이전트 그래프 | LangGraph | 최신 | StateGraph, Supervisor, ReAct |
| LLM (메인) | OpenAI GPT-4o | 최신 | 에이전트 추론, 문서 압축 |
| LLM (보조) | Claude (Anthropic) | 최신 | 엑셀 분석 에이전트 |
| LLM (로컬) | Ollama | 최신 | 오프라인/로컬 모델 실행 |

### 저장소

| 저장소 | 기술 | 용도 |
|--------|------|------|
| 벡터 DB | Qdrant | 문서 임베딩 저장, 의미 검색 |
| 전문 검색 | Elasticsearch | BM25 키워드 검색, 형태소 색인 |
| 관계형 DB | MySQL | 에이전트 정의, 대화 히스토리, 사용자 데이터 |
| 캐시/세션 | Redis | 멀티턴 세션, TTL 기반 임시 저장 |

### AI 도구 및 서비스

| 서비스 | 용도 |
|--------|------|
| Tavily Search | 웹 실시간 검색 도구 |
| LlamaParse | 고품질 PDF 파싱 (표, 수식 포함) |
| LangSmith | 에이전트 실행 추적, 성능 모니터링 |

### 언어 처리

| 라이브러리 | 용도 |
|-----------|------|
| Kiwi (kiwipiepy) | 한국어 형태소 분석 (NNG, NNP, VV, VA) |
| tiktoken | 토큰 기반 텍스트 분할 |

---

## 3. 아키텍처 설계

### Thin DDD (Domain-Driven Design)

프로젝트는 4계층 아키텍처를 채택합니다:

```
┌─────────────────────────────────────────────┐
│  API Layer (FastAPI Routers)                 │
│  → 요청/응답 스키마, 의존성 주입               │
├─────────────────────────────────────────────┤
│  Application Layer (UseCases, Workflows)     │
│  → 비즈니스 흐름 조율, LangGraph 그래프 정의   │
├─────────────────────────────────────────────┤
│  Domain Layer (Entities, Policies)           │
│  → 비즈니스 규칙, 인터페이스 추상화            │
│  → ❌ 외부 API / LangChain 의존 금지          │
├─────────────────────────────────────────────┤
│  Infrastructure Layer (Adapters)             │
│  → MySQL, Qdrant, ES, Redis, LLM 연동        │
└─────────────────────────────────────────────┘
```

### 의존성 주입 패턴

```python
# Router: placeholder 정의
def get_some_use_case() -> SomeUseCase:
    raise NotImplementedError

# main.py: dependency_overrides로 실제 구현 주입
app.dependency_overrides[get_some_use_case] = lambda: SomeUseCase(
    repository=MySQLRepository(...),
    logger=structured_logger,
)
```

### TDD 엄격 적용

```
테스트 작성 (Red) → 실패 확인 → 구현 (Green) → 리팩터링 (Refactor)
```

- domain 계층 테스트: Mock 금지 (순수 유닛 테스트)
- application 계층 테스트: AsyncMock 허용
- infrastructure 계층 테스트: Mock 또는 TestContainer

---

## 4. 구현된 모듈 목록

### 4.1 문서 처리 파이프라인

| Task ID | 모듈명 | 설명 | 상태 |
|---------|--------|------|------|
| DOC-001 | PDF Parser | LlamaParse / PyMuPDF 파서 추상화 | ✅ |
| PARSE-001 | PDF Parse Service | 공통 파싱 UseCase (asyncio.to_thread) | ✅ |
| CHUNK-001 | Chunking Module | Full-Token / Parent-Child / Semantic 전략 | ✅ |
| PIPELINE-001 | Document Pipeline | 파싱 → 청킹 → 저장 통합 워크플로우 | ✅ |
| INGEST-001 | Ingest API | PDF 인제스트 엔드포인트 (파서/청킹 선택) | ✅ |
| EXCEL-001 | Excel Parser | pandas 기반 엑셀 파싱 | ✅ |
| EXCEL-EXPORT-001 | Excel Exporter | 다중 시트 Excel 파일 생성 + LangChain Tool | ✅ |
| HTML-TO-PDF-001 | HTML to PDF | xhtml2pdf 기반 PDF 변환 모듈 | ✅ |

### 4.2 저장소 & 검색 인프라

| Task ID | 모듈명 | 설명 | 상태 |
|---------|--------|------|------|
| VEC-001 | Qdrant Repository | 벡터 임베딩 저장/검색 (Qdrant) | ✅ |
| ES-001 | Elasticsearch Repository | 인덱스/검색/CRUD 공통 Repository | ✅ |
| MYSQL-001 | MySQL Repository | Generic Base CRUD + 8가지 연산자 | ✅ |
| REDIS-001 | Redis Repository | 키-값 CRUD, Hash, List, 분산 잠금 | ✅ |
| CHUNK-IDX-001 | Chunk Index API | 텍스트 → 청킹 → BM25 키워드 추출 → ES 저장 | ✅ |
| KIWI-001 | Kiwi Analyzer | 한국어 형태소 분석기 (MorphAnalyzerInterface) | ✅ |
| MORPH-IDX-001 | Morph Index API | Kiwi 분석 → Qdrant + ES 이중 색인 | ✅ |

### 4.3 검색 & RAG

| Task ID | 모듈명 | 설명 | 상태 |
|---------|--------|------|------|
| RET-001 | Retriever | Child-first 벡터 검색 (top-k=10) | ✅ |
| COMP-001 | Document Compressor | LLM 기반 문서 압축 (true/false 필터링) | ✅ |
| HYBRID-001 | Hybrid Search | BM25 + 벡터 RRF 병합 검색 + API | ✅ |
| RETRIEVAL-001 | Retrieval API | 벡터 검색 + LLM 압축 REST API | ✅ |
| RAG-001 | RAG Agent API | LangGraph ReAct 에이전트 + 하이브리드 검색 | ✅ |
| CONV-001 | Conversation Memory | 멀티턴 대화 (6턴 초과 → 자동 요약) | ✅ |

### 4.4 LLM 클라이언트

| Task ID | 모듈명 | 설명 | 상태 |
|---------|--------|------|------|
| LLM-001 | Claude Client | Anthropic Claude API 클라이언트 (retry, streaming) | ✅ |
| OLLAMA-001 | Ollama Client | 로컬 Ollama 모델 클라이언트 (ChatOllama) | ✅ |
| QUERY-001 | Query Rewriter | LLM 기반 쿼리 재작성기 | ✅ |
| EVAL-001 | Hallucination Evaluator | LLM 기반 할루시네이션 평가 (binary) | ✅ |

### 4.5 에이전트 시스템

| Task ID | 모듈명 | 설명 | 상태 |
|---------|--------|------|------|
| AGENT-001 | Self-Corrective RAG | LangGraph 기반 Self-Corrective 에이전트 | ✅ |
| AGENT-002 | Excel Analysis Agent | 엑셀 분석 Self-Corrective 에이전트 | ✅ |
| AGENT-003 | Research Team | Supervisor + Web/Document 검색 팀 에이전트 | ✅ |
| AGENT-004 | Custom Agent Builder | LLM 도구 자동선택 + LangGraph Supervisor 동적 컴파일 | ✅ |
| AGENT-005 | Middleware Agent Builder | LangChain 미들웨어 기반 에이전트 빌더 | ✅ |
| AGENT-006 | Auto Agent Builder | 자연어 → 에이전트 자동 생성 (LLM 추론 + Redis 세션) | ✅ |

### 4.6 외부 도구 & 인프라

| Task ID | 모듈명 | 설명 | 상태 |
|---------|--------|------|------|
| SEARCH-001 | Tavily Search Tool | 웹 실시간 검색 (LangChain BaseTool) | ✅ |
| CODE-001 | Python Code Executor | 샌드박스 코드 실행 도구 | ✅ |
| MCP-001 | MCP Client | LangChain MCP 공통 클라이언트 (stdio/SSE/WebSocket) | ✅ |
| MCP-REG-001 | Dynamic MCP Registry | DB 기반 MCP 서버 동적 등록/조회 | ✅ |
| LANGSMITH-001 | LangSmith | 에이전트 실행 추적, 성능 모니터링 | ✅ |
| LOG-001 | Logging & Error Tracking | 구조화 로깅, request_id 전파, 스택 트레이스 | ✅ |

---

## 5. 핵심 기능 상세

### 5.1 에이전트 빌더 3세대 아키텍처

프로젝트의 핵심 혁신은 에이전트 생성 시스템의 단계적 진화입니다:

```
AGENT-004 (v1): Custom Agent Builder
    → LLM이 도구 자동 선택 + 시스템 프롬프트 생성
    → LangGraph Supervisor 동적 컴파일
    → POST /api/v1/agents

AGENT-005 (v2): Middleware Agent Builder
    → LangChain create_agent API 도입
    → 횡단 관심사(압축/PII/재시도)를 미들웨어로 선언적 조합
    → POST /api/v2/agents

AGENT-006 (v3): Auto Agent Builder
    → 자연어 요청 → LLM이 도구+미들웨어 자동 추론
    → confidence < 0.8: 보충 질문 (최대 3라운드)
    → confidence >= 0.8: 즉시 AGENT-005로 에이전트 생성
    → POST /api/v3/agents/auto
```

**핵심 설계 원칙: Zero Modification**
각 세대는 이전 세대 소스를 변경하지 않고 재사용합니다.

### 5.2 하이브리드 검색 (HYBRID-001)

```
사용자 쿼리
    ├─ [Qdrant 벡터 검색] → 의미 유사 문서 top-k
    └─ [Elasticsearch BM25] → 키워드 일치 문서 top-k
           ↓
    [RRF (Reciprocal Rank Fusion) 병합]
           ↓
    [LLM 문서 압축 (COMP-001)]
           ↓
    최종 결과 반환
```

키워드 단독 검색 대비 재현율 향상, 벡터 단독 검색 대비 정밀도 향상.

### 5.3 형태소 이중 색인 (MORPH-IDX-001)

Kiwi 형태소 분석기를 통해 한국어 문서를 정확하게 색인합니다:

- **추출 품사**: NNG(일반명사), NNP(고유명사), VV원형(동사), VA원형(형용사)
- **위치 메타데이터**: offset, sentence_index 포함
- **이중 저장**: Qdrant(벡터) + Elasticsearch(BM25) 동시 저장

### 5.4 Multi-Turn 대화 메모리 (CONV-001)

```
대화 Turn 1 ~ 6: 전체 기록 유지
       ↓ (6턴 초과 시)
[LLM 자동 요약] → conversation_summary 테이블에 저장
       ↓
다음 질의 컨텍스트: [요약본] + [최근 3턴]만 사용
```

- ❌ 전체 대화를 LLM에 무제한 전달 금지
- ❌ Vector DB에 대화 저장 금지 (MySQL만 사용)

### 5.5 Dynamic MCP Registry (MCP-REG-001)

```
DB 등록된 MCP 서버들
    ↓
GET /api/v1/agents/tools 요청 시
    ↓
내부 도구 4개 + MCP 도구 N개 동적 로드
    ↓
MCPToolLoader → SSE 연결 → LangChain BaseTool로 변환
    ↓
에이전트에서 즉시 사용 가능
```

- 배포 없이 런타임에 새 MCP 서버 등록 가능
- is_active 플래그로 임시 비활성화 지원
- 부분 실패 처리: MCP 서버 1개 다운 → 나머지 도구 정상 작동

### 5.6 5가지 LangChain 미들웨어 (AGENT-005)

| 미들웨어 | 기능 |
|---------|------|
| SummarizationMiddleware | 장문 컨텍스트 자동 압축 |
| PIIMiddleware | 개인정보(이름/전화/이메일) 자동 마스킹 |
| ToolRetryMiddleware | 도구 실패 시 자동 재시도 (n회) |
| ModelCallLimitMiddleware | LLM 호출 횟수 상한 제한 |
| ModelFallbackMiddleware | 기본 모델 실패 시 폴백 모델 자동 전환 |

---

## 6. API 엔드포인트 전체 목록

### 6.1 문서 처리 API

| 메서드 | 경로 | 설명 | Task ID |
|--------|------|------|---------|
| POST | `/api/v1/documents/upload` | PDF 업로드 → 파싱 → 청킹 → Qdrant 저장 (레거시) | PIPELINE-001 |
| POST | `/api/v1/ingest/pdf` | PDF 인제스트 (파서·청킹 전략 선택, 권장) | INGEST-001 |
| POST | `/api/v1/excel/upload` | 엑셀 업로드 → 청킹 → Qdrant 저장 | EXCEL-001 |
| POST | `/api/v1/chunk-index/upload` | 텍스트 → 청킹 → ES BM25 색인 | CHUNK-IDX-001 |
| POST | `/api/v1/morph-index/upload` | Kiwi 형태소 → Qdrant + ES 이중 색인 | MORPH-IDX-001 |

### 6.2 검색 & 질의응답 API

| 메서드 | 경로 | 설명 | Task ID |
|--------|------|------|---------|
| POST | `/api/v1/retrieval/search` | 벡터 유사도 검색 + LLM 압축 | RETRIEVAL-001 |
| POST | `/api/v1/hybrid-search/search` | BM25 + 벡터 RRF 병합 검색 | HYBRID-001 |
| POST | `/api/v1/rag-agent/query` | LangGraph ReAct 에이전트 질의응답 | RAG-001 |
| POST | `/api/v1/conversation/chat` | 멀티턴 대화 (6턴 초과 시 자동 요약) | CONV-001 |

### 6.3 AI 분석 API

| 메서드 | 경로 | 설명 | Task ID |
|--------|------|------|---------|
| POST | `/api/v1/analysis/excel` | 엑셀 Self-Corrective 에이전트 분석 | AGENT-002 |

### 6.4 에이전트 빌더 API (v1)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/agents/tools` | 사용 가능한 도구 목록 (내부 + MCP) |
| POST | `/api/v1/agents` | 에이전트 생성 (도구 자동 선택) |
| GET | `/api/v1/agents/{id}` | 에이전트 정의 조회 |
| PATCH | `/api/v1/agents/{id}/prompt` | 시스템 프롬프트 수정 |
| POST | `/api/v1/agents/{id}/run` | 에이전트 실행 |
| POST | `/api/v1/agents/interview/start` | 인터뷰 시작 (요구사항 보충) |
| POST | `/api/v1/agents/interview/{id}/answer` | 인터뷰 답변 제출 |
| POST | `/api/v1/agents/interview/{id}/finalize` | 인터뷰 완료 → 에이전트 생성 |

### 6.5 에이전트 빌더 API (v2 — 미들웨어)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v2/agents` | 미들웨어 포함 에이전트 생성 |
| GET | `/api/v2/agents/{id}` | 에이전트 조회 |
| PATCH | `/api/v2/agents/{id}` | 에이전트 수정 |
| DELETE | `/api/v2/agents/{id}` | 에이전트 삭제 |
| POST | `/api/v2/agents/{id}/run` | 에이전트 실행 |

### 6.6 에이전트 빌더 API (v3 — 자동)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v3/agents/auto` | 자연어 요청 → 자동 에이전트 빌드 시작 |
| POST | `/api/v3/agents/auto/{session_id}/reply` | 보충 질문 답변 제출 |
| GET | `/api/v3/agents/auto/{session_id}` | 빌드 세션 상태 조회 |

### 6.7 MCP Registry API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/mcp-registry` | MCP 서버 등록 |
| GET | `/api/v1/mcp-registry` | 전체 MCP 서버 목록 |
| GET | `/api/v1/mcp-registry/{id}` | 특정 MCP 서버 조회 |
| PATCH | `/api/v1/mcp-registry/{id}` | MCP 서버 수정 |
| DELETE | `/api/v1/mcp-registry/{id}` | MCP 서버 삭제 |

### 6.8 내보내기 API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/pdf/export` | HTML → PDF 변환 |
| POST | `/api/v1/excel/export` | 데이터 → Excel 파일 생성 |

### 6.9 기타

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 서버 상태 확인 |

---

## 7. PDCA 완료 이력

PDCA(Plan → Design → Do → Check → Act) 방법론을 통해 검증된 피처 목록:

### 7.1 아카이브된 완료 피처 (2026-03)

| 피처 | Task ID | 완료일 | Match Rate | 테스트 수 | 코드 줄 수 |
|------|---------|--------|-----------|----------|-----------|
| Custom Agent Builder | AGENT-004 | 2026-03-21 | 100% | 66개 | ~2,250 |
| Dynamic MCP Registry | MCP-REG-001 | 2026-03-21 | 100% | 91개 | ~5,000 |
| Middleware Agent Builder | AGENT-005 | 2026-03-24 | 95% | 63개 | - |
| Auto Agent Builder | AGENT-006 | 2026-03-24 | 97% | 62개 | 572 |

### 7.2 주요 PDCA 지표

| 지표 | 값 |
|------|-----|
| 완료된 PDCA 사이클 수 | 4+ (아카이브 기준) |
| 전체 테스트 수 (상기 4개 피처) | **282개** |
| 전체 테스트 통과율 | **100%** |
| 최소 Match Rate (Check 통과 기준) | 90% |
| 평균 Match Rate | **98%** |

### 7.3 이전 구현 완료 모듈 (태스크 기반)

아래 모듈은 task.md 기반으로 TDD 구현 완료:

- VEC-001, DOC-001, CHUNK-001, RET-001, COMP-001
- EXCEL-001, PIPELINE-001, LOG-001
- EVAL-001, QUERY-001, SEARCH-001
- AGENT-001, AGENT-002, AGENT-003
- LLM-001, CODE-001, LANGSMITH-001
- RETRIEVAL-001, REDIS-001, MCP-001
- ES-001, HYBRID-001, CHUNK-IDX-001
- KIWI-001, MORPH-IDX-001, RAG-001
- MYSQL-001, CONV-001, PARSE-001, INGEST-001
- HTML-TO-PDF-001, EXCEL-EXPORT-001
- OLLAMA-001

**총 구현 모듈**: **35개 이상**

---

## 8. 품질 지표

### 8.1 코드 품질

| 지표 | 목표 | 실제 |
|------|------|------|
| 타입 힌트 커버리지 | 100% | 100% |
| 함수 길이 | ≤ 40줄 | 준수 |
| if 중첩 깊이 | ≤ 2단계 | 준수 |
| DDD 계층 의존성 | domain → infra 금지 | 100% 준수 |
| LOG-001 컴플라이언스 | 100% | 100% |
| print() 사용 | 0건 | 0건 |

### 8.2 테스트 전략

```
domain 테스트     → Mock 금지, 순수 유닛 테스트
application 테스트 → AsyncMock, 비즈니스 로직 검증
infrastructure 테스트 → Mock 또는 TestContainer
api 테스트        → FastAPI TestClient + DI override
```

### 8.3 로깅 표준 (LOG-001)

모든 서비스/어댑터는 다음 패턴을 준수합니다:

```python
class SomeService:
    def __init__(self, logger: LoggerInterface):
        self._logger = logger

    async def process(self, request_id: str, data: dict):
        self._logger.info("Processing started",
                          request_id=request_id,
                          data_keys=list(data.keys()))
        try:
            result = await self._do_work(data)
            self._logger.info("Processing completed", request_id=request_id)
            return result
        except Exception as e:
            self._logger.error("Processing failed",
                               exception=e,
                               request_id=request_id)
            raise
```

**필수 항목**: `request_id` 전파, `exception=` 파라미터, 스택 트레이스
**금지 항목**: `print()`, 민감 정보 평문 로깅, 스택 트레이스 없는 에러 로그

---

## 9. 아키텍처 결정 기록 (ADR)

### ADR-001: Thin DDD 채택

**결정**: 과도한 추상화 없이 domain→application→infrastructure 3계층 유지
**이유**: 금융/정책 문서 처리는 빠른 실험이 중요하므로, 두꺼운 DDD보다 얇은 DDD가 생산성 극대화
**영향**: 빠른 피처 추가, 쉬운 테스트 작성

### ADR-002: Hybrid Search (BM25 + Vector)

**결정**: RRF(Reciprocal Rank Fusion)로 BM25와 벡터 검색 결과 병합
**이유**: 벡터 단독 → 키워드 누락, BM25 단독 → 의미 파악 불가. 두 방식의 장점 결합
**영향**: 검색 재현율 및 정밀도 모두 향상

### ADR-003: 대화 메모리 = MySQL (Vector DB 금지)

**결정**: 대화 기록은 MySQL에만 저장, Vector DB에 저장 금지
**이유**: 대화는 시간순 구조(RDBMS 적합), 벡터는 문서 의미 검색용 (용도 분리)
**영향**: 데이터 구조 명확화, 의도치 않은 문서-대화 교차 검색 방지

### ADR-004: Agent 버전별 Zero-Modification 원칙

**결정**: 신규 에이전트 세대는 이전 세대 소스를 일절 변경하지 않고 재사용
**이유**: 하위 호환성 보장, 회귀 버그 방지, 독립적 테스트 가능
**영향**: AGENT-004 → AGENT-005 → AGENT-006이 완전 독립적으로 동작

### ADR-005: Redis 세션 (Auto Agent Builder)

**결정**: Auto Agent Builder의 멀티턴 세션은 Redis에 저장 (MySQL 아님)
**이유**: 세션은 임시 데이터(TTL 24시간), 빠른 조회 필요, MySQL은 장기 데이터용
**영향**: REDIS-001 모듈 재사용, 세션 자동 만료

### ADR-006: LLM 추론 temperature=0

**결정**: 에이전트 빌더의 도구 선택 LLM은 temperature=0 사용
**이유**: 같은 요청에 항상 동일한 도구 선택 → 결정론적 동작, 테스트 용이
**영향**: LLM 비용 감소, 예측 가능한 에이전트 생성

---

## 10. 설계 원칙 및 코딩 컨벤션

### 10.1 절대 금지 사항

- `domain → infrastructure` 직접 참조
- Router/Controller에 비즈니스 로직 작성
- 대화 기록을 Vector DB에 저장
- `print()` 사용 (LoggerInterface 사용 필수)
- 스택 트레이스 없는 에러 처리
- Config 값 하드코딩
- 과도한 추상화 (두꺼운 DDD)
- spec에 없는 기능 구현

### 10.2 개발 흐름

새 기능 추가 시:
1. domain 정책 존재 여부 확인
2. task.md 작성 (LOG-001 의존성 명시)
3. 테스트 작성 (Red)
4. 테스트 실패 확인
5. 구현 (Green)
6. 리팩터링 (Refactor)
7. PDCA 분석 → Match Rate 90% 이상 달성

### 10.3 청킹 전략 선택 가이드

| 전략 | 적합한 문서 유형 |
|------|----------------|
| `full_token` | 단순 텍스트, 길이 균일한 문서 |
| `parent_child` | 계층 구조 문서 (법률, 정책, 보고서) |
| `semantic` | 주제 경계가 명확한 문서 |

---

## 참고 문서

- **CLAUDE.md**: 전체 프로젝트 코딩 규칙 및 AI 행동 지침
- **docs/apidocs/**: 전체 API 엔드포인트 상세 문서
- **docs/archive/2026-03/**: 완료된 PDCA 사이클 아카이브
- **docs/04-report/changelog.md**: 릴리즈 변경 이력
- **src/claude/task/**: 각 모듈별 구현 명세 (35개+)

---

*Generated: 2026-03-25*
*Total Modules: 35+*
*Total PDCA Cycles Completed: 4 (archived)*
*Total Tests (archived features): 282*
*Average Match Rate: 98%*
