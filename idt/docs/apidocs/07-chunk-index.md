# 청킹 + ES 색인 API

> **태그**: `chunk-index`
> **Base Path**: `/api/v1/chunk-index`

---

## 개요

텍스트를 청크(분할)하고 각 청크에서 키워드를 추출하여 **Elasticsearch에만** 저장합니다.

### 처리 흐름

```
텍스트 입력
     ↓
선택한 전략으로 청킹 (분할)
     ↓
빈도 기반 키워드 추출
     ↓
Elasticsearch 색인 (BM25 검색용)
```

> Qdrant 벡터 저장은 포함되지 않습니다. 벡터 + ES 이중 저장이 필요하면 [형태소 이중 색인 API](./08-morph-index.md)를 사용하세요.

---

## 엔드포인트

### 청킹 + ES 색인

**`POST /api/v1/chunk-index/upload`**

#### 요청 (JSON)

```json
{
  "document_id": "doc_001",
  "content": "한국은행은 2024년 기준금리를 동결하기로 결정하였다...",
  "user_id": "user_001",
  "strategy_type": "parent_child",
  "metadata": {"source": "press_release.pdf"},
  "chunk_size": 500,
  "chunk_overlap": 50,
  "top_keywords": 10
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `document_id` | string | ✅ | - | 문서 고유 ID |
| `content` | string | ✅ | - | 청킹할 텍스트 내용 |
| `user_id` | string | ✅ | - | 사용자 ID |
| `strategy_type` | string | ❌ | `parent_child` | 청킹 전략 (`full_token`, `parent_child`, `semantic`) |
| `metadata` | object | ❌ | `{}` | 추가 메타데이터 (임의 키-값) |
| `chunk_size` | int | ❌ | 500 | 청크 크기 토큰 수 (최소 100) |
| `chunk_overlap` | int | ❌ | 50 | 청크 간 겹침 토큰 수 |
| `top_keywords` | int | ❌ | 10 | 청크당 추출할 키워드 수 (1~50) |

#### 응답 (200 OK)

```json
{
  "document_id": "doc_001",
  "user_id": "user_001",
  "total_chunks": 5,
  "indexed_chunks": [
    {
      "chunk_id": "doc_001_child_0",
      "chunk_type": "child",
      "keywords": ["기준금리", "동결", "한국은행", "결정", "통화정책"],
      "content": "한국은행은 2024년 기준금리를 동결하기로 결정하였다..."
    }
  ],
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `total_chunks` | 생성된 총 청크 수 |
| `indexed_chunks[].chunk_type` | `child` 또는 `parent` (parent_child 전략) |
| `indexed_chunks[].keywords` | 해당 청크에서 추출된 키워드 목록 |

#### 오류 응답 (422)

```json
{
  "detail": "strategy_type must be one of: ['full_token', 'parent_child', 'semantic']"
}
```

#### 예제

```bash
curl -X POST "http://localhost:8000/api/v1/chunk-index/upload" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "report_2024_q1",
    "content": "2024년 1분기 경제 보고서 내용...",
    "user_id": "user_001",
    "strategy_type": "parent_child",
    "chunk_size": 500,
    "top_keywords": 15
  }'
```

---

## 사용 시나리오

이 API는 **이미 파싱된 텍스트**를 ES에 색인할 때 사용합니다.

```
외부 시스템에서 텍스트 추출
         ↓
POST /api/v1/chunk-index/upload  ← 이 API
         ↓
하이브리드 검색(BM25) 가능
```

전체 파이프라인(PDF → 파싱 → 청킹 → 저장)이 필요하면 [PDF 인제스트 API](./02-ingest.md)를 사용하세요.
