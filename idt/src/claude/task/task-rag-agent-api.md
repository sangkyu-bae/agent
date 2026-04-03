# RAG-001: ReAct RAG Agent API (하이브리드 검색 + LLM 응답)

> Task ID: RAG-001
> 의존성: HYBRID-001, MORPH-IDX-001, LOG-001
> 상태: Done

---

## 목적

MORPH-IDX-001로 색인된 내부 문서를 대상으로 **BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색**을 수행하고,
LangChain **ChatOpenAI ReAct 에이전트**가 질문에 대해 내부 문서 필요 여부를 스스로 판단하여 답변한다.

- 내부 문서가 필요하면: `internal_document_search` 도구 호출 → 관련 문서 검색 → LLM 답변 생성
- 내부 문서가 불필요하면: 직접 답변 생성

---

## 아키텍처

```
POST /api/v1/rag-agent/query
         │
         ▼
RAGAgentRouter (interfaces/api)
         │
         ▼
RAGAgentUseCase (application)
    ├── create_react_agent(ChatOpenAI, [InternalDocumentSearchTool])
    │
    └── InternalDocumentSearchTool._arun()
            ├── HybridSearchUseCase.execute()   ← HYBRID-001 재사용
            │       ├── ES BM25  (bm25_top_k = top_k * 2)
            │       └── Qdrant Vector  (vector_top_k = top_k * 2)  ← 5:5 동등 가중치
            └── metadata["source"] 추출 → DocumentSource 수집
```

---

## 5:5 하이브리드 검색 구현

`bm25_top_k == vector_top_k` 로 설정하여 RRF 알고리즘에서 동등 가중치 보장.

```python
HybridSearchRequest(
    query=query,
    top_k=self.top_k,
    bm25_top_k=self.top_k * 2,    # 동등
    vector_top_k=self.top_k * 2,  # 동등
    rrf_k=60,
)
```

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/rag_agent/schemas.py` | `RAGAgentRequest`, `DocumentSource`, `RAGAgentResponse` |

### Application Layer
| 파일 | 설명 |
|------|------|
| `src/application/rag_agent/tools.py` | `InternalDocumentSearchTool` — LangChain BaseTool, 5:5 하이브리드 검색 |
| `src/application/rag_agent/use_case.py` | `RAGAgentUseCase` — LangGraph create_react_agent 오케스트레이션 |

### API Layer
| 파일 | 설명 |
|------|------|
| `src/api/routes/rag_agent_router.py` | `POST /api/v1/rag-agent/query` |

---

## ES 문서 메타데이터 출처 추출

MORPH-IDX-001에서 색인 시 `source` 필드가 메타데이터에 포함됨.

```python
source = hit.metadata.get("source", "unknown")  # 예: "report.pdf"
```

---

## API 인터페이스

```json
// 요청
POST /api/v1/rag-agent/query
{
    "query": "금융 정책 문서에서 대출 한도는?",
    "user_id": "user-1",
    "top_k": 5
}

// 응답
{
    "query": "금융 정책 문서에서 대출 한도는?",
    "answer": "내부 문서에 따르면 대출 한도는 ...",
    "sources": [
        {
            "content": "대출 한도 관련 내용...",
            "source": "financial_policy_2024.pdf",
            "chunk_id": "uuid",
            "score": 0.032
        }
    ],
    "used_internal_docs": true,
    "request_id": "uuid"
}
```

---

## ReAct 에이전트 동작 흐름

```
User: "금융 정책 대출 한도?"
  ↓
Agent: [내부 문서 필요 판단] → internal_document_search("금융 정책 대출 한도") 호출
  ↓
Tool: BM25 + Vector 5:5 하이브리드 검색 실행
  ↓
Agent: 검색 결과 기반으로 최종 답변 생성
  ↓
Response: answer + sources (출처 파일명 포함) + used_internal_docs=true
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock |
|------------|------|------|
| `tests/domain/rag_agent/test_schemas.py` | 스키마 (9 케이스) | ❌ |
| `tests/application/rag_agent/test_use_case.py` | Tool + UseCase (9 케이스) | ✅ |
| `tests/api/test_rag_agent_router.py` | API 엔드포인트 (8 케이스) | ✅ |

총 26 테스트 케이스.

---

## LOG-001 로깅 체크리스트

- [x] `LoggerInterface` 주입 (RAGAgentUseCase)
- [x] 처리 시작/완료 INFO 로그 (`request_id`, `query`, `user_id`, `used_internal_docs`, `sources_count`)
- [x] 예외 발생 시 ERROR 로그 + `exception=e`
- [x] `request_id` 컨텍스트 전파

---

## 완료 기준

- [x] `RAGAgentRequest`, `DocumentSource`, `RAGAgentResponse` 스키마
- [x] `InternalDocumentSearchTool` (BM25 + Vector 5:5, source 메타데이터 추출)
- [x] `RAGAgentUseCase` LangGraph ReAct 오케스트레이션
- [x] `POST /api/v1/rag-agent/query` API
- [x] `src/api/main.py` 라우터 등록 및 DI 연결
- [x] 전체 26 테스트 통과
- [x] LOG-001 로깅 적용
