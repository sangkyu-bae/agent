# RAG 에이전트 API

> **태그**: `rag-agent`
> **Base Path**: `/api/v1/rag-agent`

---

## 개요

LangGraph ReAct 에이전트가 내부 문서를 검색하여 질의응답을 수행합니다.

### 처리 흐름

```
사용자 질의 입력
       ↓
ReAct 에이전트 판단
       ├── 내부 문서 필요 → internal_document_search 도구 호출
       │         ↓
       │   BM25 + 벡터 하이브리드 검색 (5:5 비율)
       │         ↓
       │   관련 문서 기반 답변 생성
       │
       └── 내부 문서 불필요 → 직접 답변 생성

출처 문서 + 답변 반환
```

### ReAct (Reasoning + Acting) 패턴

에이전트는 단순 검색 후 답변이 아니라, **"내부 문서가 필요한가?"를 먼저 판단**한 후 도구를 사용합니다.

- 일반적인 상식 질문 → 도구 없이 직접 답변
- 내부 문서 관련 질문 → 검색 도구 호출 후 답변

---

## 엔드포인트

### 문서 질의응답

**`POST /api/v1/rag-agent/query`**

#### 요청 (JSON)

```json
{
  "query": "2024년 기준금리 결정 배경을 설명해줘",
  "user_id": "user_001",
  "top_k": 5
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `query` | string | ✅ | - | 질의 내용 (1자 이상) |
| `user_id` | string | ✅ | - | 사용자 ID |
| `top_k` | int | ❌ | 5 | 하이브리드 검색 결과 수 (1~20) |

#### 응답 (200 OK)

```json
{
  "query": "2024년 기준금리 결정 배경을 설명해줘",
  "answer": "2024년 한국은행의 기준금리 결정은 다음과 같은 배경에서 이루어졌습니다. 첫째, 물가상승률이 목표치(2%)에 근접하면서...",
  "sources": [
    {
      "content": "한국은행 금융통화위원회는 2024년 1월 기준금리를...",
      "source": "monetary_policy_jan2024.pdf",
      "chunk_id": "chunk_001",
      "score": 0.031
    }
  ],
  "used_internal_docs": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `answer` | LLM이 생성한 최종 답변 |
| `sources` | 답변 생성에 사용된 참조 문서 목록 |
| `sources[].source` | 원본 파일명 (`metadata["source"]`) |
| `sources[].score` | RRF 점수 (높을수록 관련성 높음) |
| `used_internal_docs` | 내부 문서 검색 실행 여부 |

#### 예제

```bash
# 내부 문서 기반 질의응답
curl -X POST "http://localhost:8000/api/v1/rag-agent/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "올해 주택담보대출 규제 내용 요약해줘",
    "user_id": "user_001",
    "top_k": 5
  }'
```

---

## 문서 준비 필요

이 API를 사용하기 전에 **먼저 문서를 색인**해야 합니다.

```
1. PDF 업로드 → POST /api/v1/morph-index/upload  (Qdrant + ES 이중 색인)
                 또는
                POST /api/v1/ingest/pdf           (Qdrant 벡터 저장만)

2. 질의응답   → POST /api/v1/rag-agent/query
```

문서를 색인하지 않으면 `used_internal_docs=true`라도 관련 문서를 찾지 못해 답변 품질이 낮아집니다.

---

## 다른 검색 API와 비교

| | RAG 에이전트 | [하이브리드 검색](./06-hybrid-search.md) | [문서 검색](./05-retrieval.md) |
|-|------------|----------------------------------------|-------------------------------|
| LLM 답변 생성 | ✅ | ❌ | ❌ |
| 출처 제공 | ✅ | ✅ | ✅ |
| 검색 방식 | BM25 + 벡터 | BM25 + 벡터 | 벡터만 |
| 적합한 용도 | 질의응답 챗봇 | 문서 목록 반환 | 정확한 벡터 검색 |
