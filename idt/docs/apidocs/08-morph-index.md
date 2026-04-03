# 형태소 분석 이중 색인 API

> **태그**: `morph-index`
> **Base Path**: `/api/v1/morph-index`

---

## 개요

텍스트를 청킹한 뒤 **Kiwi 한국어 형태소 분석기**로 키워드를 추출하고, **Qdrant(벡터)와 Elasticsearch(BM25) 두 곳에 동시에 저장**합니다.

### 처리 흐름

```
텍스트 입력
     ↓
청킹 (분할)
     ↓
Kiwi 형태소 분석 → NNG(일반명사), NNP(고유명사), VV원형(동사), VA원형(형용사) 추출
     ↓
     ├── Qdrant: 임베딩 벡터 + 전체 메타데이터 저장
     └── ES: 텍스트 + 형태소 키워드 + 위치 정보 저장
```

### 일반 청킹 색인 vs. 형태소 이중 색인 비교

| | [청킹 색인 API](./07-chunk-index.md) | 형태소 이중 색인 API |
|-|--------------------------------------|-------------------|
| Elasticsearch | ✅ (빈도 기반 키워드) | ✅ (형태소 분석 키워드) |
| Qdrant (벡터) | ❌ | ✅ |
| 한국어 최적화 | 기본 | **Kiwi 형태소 분석** |
| 위치 메타데이터 | ❌ | ✅ (char_start, char_end) |

---

## 엔드포인트

### 형태소 분석 이중 색인

**`POST /api/v1/morph-index/upload`**

#### 요청 (JSON)

```json
{
  "document_id": "doc_001",
  "content": "한국은행은 2024년 기준금리를 동결하기로 결정하였다. 이는 물가 안정을 위한 조치이다.",
  "user_id": "user_001",
  "strategy_type": "parent_child",
  "chunk_size": 500,
  "chunk_overlap": 50,
  "source": "press_release_2024.pdf",
  "metadata": {"department": "정책팀"}
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `document_id` | string | ✅ | - | 문서 고유 ID |
| `content` | string | ✅ | - | 청킹할 텍스트 |
| `user_id` | string | ✅ | - | 사용자 ID |
| `strategy_type` | string | ❌ | `parent_child` | 청킹 전략 |
| `chunk_size` | int | ❌ | 500 | 청크 크기 토큰 수 (최소 100) |
| `chunk_overlap` | int | ❌ | 50 | 청크 간 겹침 토큰 수 |
| `source` | string | ❌ | `""` | 원본 파일명 / 출처 |
| `metadata` | object | ❌ | `{}` | 추가 메타데이터 |

#### 응답 (200 OK)

```json
{
  "document_id": "doc_001",
  "user_id": "user_001",
  "total_chunks": 3,
  "qdrant_indexed": 3,
  "es_indexed": 3,
  "indexed_chunks": [
    {
      "chunk_id": "doc_001_child_0",
      "chunk_type": "child",
      "morph_keywords": ["한국은행", "기준금리", "동결", "결정", "물가"],
      "content": "한국은행은 2024년 기준금리를 동결하기로 결정하였다...",
      "char_start": 0,
      "char_end": 45,
      "chunk_index": 0
    }
  ],
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `qdrant_indexed` | Qdrant에 저장된 벡터 수 |
| `es_indexed` | Elasticsearch에 색인된 문서 수 |
| `indexed_chunks[].morph_keywords` | Kiwi로 분석된 형태소 키워드 |
| `indexed_chunks[].char_start` | 원본 텍스트에서 청크 시작 위치 (문자 인덱스) |
| `indexed_chunks[].char_end` | 원본 텍스트에서 청크 끝 위치 (문자 인덱스) |
| `indexed_chunks[].chunk_index` | 청크 순서 번호 |

#### 예제

```bash
curl -X POST "http://localhost:8000/api/v1/morph-index/upload" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "policy_doc_001",
    "content": "정부는 부동산 시장 안정화를 위해 다양한 정책을 시행하고 있다...",
    "user_id": "user_001",
    "strategy_type": "parent_child",
    "source": "housing_policy_2024.pdf"
  }'
```

---

## 형태소 분석 품사 태그

Kiwi가 추출하는 키워드 품사:

| 태그 | 품사 | 예시 |
|------|------|------|
| `NNG` | 일반 명사 | 금리, 정책, 경제 |
| `NNP` | 고유 명사 | 한국은행, 서울, LG |
| `VV` | 동사 (원형) | 결정하다, 인상하다 |
| `VA` | 형용사 (원형) | 안정적이다, 높다 |

---

## 사용 시나리오

**한국어 문서 + 하이브리드 검색 최적화**에 적합합니다.

```
한국어 문서 저장 (형태소 이중 색인)
         ↓
하이브리드 검색에서 형태소 기반 BM25 검색
         ↓
RAG 에이전트가 더 정확한 검색 결과 활용
```
