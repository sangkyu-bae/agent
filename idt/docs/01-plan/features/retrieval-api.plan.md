# Plan: retrieval-api

> Feature: 사용자 질문 기반 문서 검색 API (RAG Retrieval API)
> Created: 2026-03-04
> Status: Plan

---

## 1. 목적 (Why)

사용자의 자연어 질문을 받아 Qdrant 벡터 DB에서 관련 문서 청크를 검색하고,
LLM 기반 압축(Compressor)을 거쳐 최종 답변 생성에 필요한 컨텍스트를 반환하는 API.

금융/정책 문서에 최적화된 Child-first 검색 + Parent Requery 파이프라인 제공.

---

## 2. 기능 범위 (Scope)

### In Scope
- `POST /api/v1/retrieval/search` — 질문으로 문서 검색
- Query Rewriting (선택적): 질문 품질 개선 후 검색
- Child-first 벡터 검색 (기본 top_k=10)
- LLM 기반 관련성 필터링(Compressor)
- Parent Requery: child 결과 불충분 시 parent 컨텍스트 보완
- 메타데이터 필터 지원 (user_id, document_id, chunk_type)
- `POST /api/v1/retrieval/search-with-scores` — 유사도 점수 포함 검색

### Out of Scope
- 답변 생성(LLM 답변): RAG 검색까지만 담당
- 대화 기록 저장 (별도 CHAT 기능)
- 문서 업로드 (기존 document_upload API)

---

## 3. 기술 의존성

| 모듈 | Task ID | 상태 |
|------|---------|------|
| Qdrant 벡터 저장소 | VEC-001 | 구현됨 |
| RetrieverInterface / QdrantRetriever | RET-001 | 구현됨 |
| ParentChildRetriever | RET-001 | 구현됨 |
| LLM Compressor | COMP-001 | 구현됨 |
| Query Rewriter | QUERY-001 | 구현됨 |
| LoggerInterface | LOG-001 | 구현됨 |
| OpenAI Embedding | VEC-001 | 구현됨 |

---

## 4. API 설계 개요

### Request
```json
POST /api/v1/retrieval/search
{
  "query": "금리 인상 시 채권 가격 변화",
  "user_id": "user_123",
  "top_k": 10,
  "document_id": null,
  "use_query_rewrite": false,
  "use_compression": true,
  "use_parent_context": true
}
```

### Response
```json
{
  "query": "금리 인상 시 채권 가격 변화",
  "rewritten_query": null,
  "documents": [
    {
      "id": "abc123",
      "content": "금리가 상승하면 채권 가격은 하락한다...",
      "score": 0.92,
      "metadata": {
        "chunk_type": "child",
        "parent_id": "parent_001",
        "document_id": "doc_001",
        "user_id": "user_123"
      },
      "parent_content": "국채 금리와 가격의 역관계..."
    }
  ],
  "total_found": 5,
  "request_id": "uuid"
}
```

---

## 5. Application Layer 설계

### RetrievalUseCase
파일: `src/application/retrieval/retrieval_use_case.py`

흐름:
1. 입력 검증
2. (선택) QueryRewriter → 질문 개선
3. ParentChildRetriever.retrieve_with_parent() 호출
4. (선택) Compressor → 관련성 필터링
5. 결과 반환

---

## 6. TDD 계획

- `tests/application/retrieval/test_retrieval_use_case.py`
- `tests/api/test_retrieval_router.py`

---

## 7. CLAUDE.md 규칙 체크

- [x] domain에 외부 의존성 없음 (인터페이스만 사용)
- [x] application은 domain 규칙 조합
- [x] infrastructure 어댑터 재사용 (RetrieverInterface)
- [x] LOG-001 로깅 적용
- [x] TDD 순서: 테스트 → 구현

---

## 8. 완료 기준

- [ ] `POST /api/v1/retrieval/search` API 정상 동작
- [ ] Child-first 검색 + Parent Requery 동작
- [ ] Compressor 필터링 적용
- [ ] 테스트 커버리지 (use_case + router)
- [ ] LOG-001 로깅 적용
