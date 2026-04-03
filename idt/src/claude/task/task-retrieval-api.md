# RETRIEVAL-001: 문서 검색 API (RAG Retrieval)

- **상태**: 완료
- **목적**: 사용자 질문으로 Qdrant 벡터 DB에서 관련 문서 청크를 검색하고 LLM 압축을 거쳐 컨텍스트 반환
- **의존성**: VEC-001, RET-001, COMP-001, QUERY-001, LOG-001

---

## 구현 파일

| 레이어 | 파일 |
|--------|------|
| Domain | `src/domain/retrieval/schemas.py` |
| Domain | `src/domain/retrieval/policies.py` |
| Application | `src/application/retrieval/retrieval_use_case.py` |
| API | `src/api/routes/retrieval_router.py` |
| Tests | `tests/application/retrieval/test_retrieval_use_case.py` |
| Tests | `tests/api/test_retrieval_router.py` |

---

## API

```
POST /api/v1/retrieval/search
```

**Request:**
```json
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

**Response:**
```json
{
  "query": "금리 인상 시 채권 가격 변화",
  "rewritten_query": null,
  "documents": [...],
  "total_found": 5,
  "request_id": "uuid"
}
```

---

## 흐름

1. 입력 검증 (RetrievalPolicy)
2. (선택) QueryRewriter → 질문 개선
3. ParentChildRetriever.retrieve_with_parent() — Child-first + Parent 컨텍스트
4. (선택) DocumentCompressor — LLM 관련성 필터링
5. RetrievalResult 반환

---

## 테스트

- 9개 유즈케이스 테스트
- 6개 라우터 테스트
- 총 15개, 100% 통과
