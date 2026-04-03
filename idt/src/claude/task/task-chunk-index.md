# CHUNK-IDX-001: 청킹 + BM25 키워드 색인 모듈

> Task ID: CHUNK-IDX-001
> 의존성: CHUNK-001, ES-001, LOG-001
> 상태: Done

---

## 목적

기존 청킹 모듈(CHUNK-001)을 활용하여 문서를 청킹하고,
각 청크에서 **빈도 기반 키워드**를 추출하여 Elasticsearch에 색인한다.
이를 통해 HYBRID-001의 BM25 검색 품질을 높이고,
청킹→키워드→ES 색인 파이프라인을 단일 API로 제공한다.

---

## 아키텍처

```
POST /api/v1/chunk-index/upload
           │
           ▼
ChunkIndexRouter (interfaces/api)
           │
           ▼
ChunkAndIndexUseCase (application)
    ├── ChunkingStrategy.chunk()          ← 기존 청킹 모듈 재사용
    ├── KeywordExtractorInterface.extract() ← 청크별 키워드 추출
    └── ElasticsearchRepository.bulk_index() ← ES 색인
           │
           ▼
Elasticsearch Index
{
  "content": "청크 텍스트",
  "keywords": ["금융", "정책", "이자율"],
  "chunk_id": "uuid",
  "chunk_type": "child",
  "parent_id": "uuid",
  "document_id": "doc-uuid",
  "user_id": "u1"
}
```

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/keyword/schemas.py` | `KeywordExtractionResult` Value Object |
| `src/domain/keyword/interfaces.py` | `KeywordExtractorInterface` (추상) |

### Infrastructure Layer
| 파일 | 설명 |
|------|------|
| `src/infrastructure/keyword/simple_keyword_extractor.py` | 정규식 기반 빈도 키워드 추출 (외부 의존성 없음) |

### Application Layer
| 파일 | 설명 |
|------|------|
| `src/application/chunk_and_index/schemas.py` | `ChunkAndIndexRequest`, `IndexedChunk`, `ChunkAndIndexResult` |
| `src/application/chunk_and_index/use_case.py` | `ChunkAndIndexUseCase` |

### API Layer
| 파일 | 설명 |
|------|------|
| `src/api/routes/chunk_index_router.py` | `POST /api/v1/chunk-index/upload` |

---

## 키워드 추출 알고리즘

`SimpleKeywordExtractor` (정규식 기반, 외부 NLP 라이브러리 불필요):

```
1. 정규식으로 토큰 추출:
   - [가-힣]{2,} → 한국어 2글자 이상
   - [a-zA-Z]{2,} → 영어 2글자 이상
2. 영어 불용어(stopwords) 제거
3. Counter로 빈도 집계
4. 빈도 내림차순 top_n 반환
```

**결과 예시:**
```python
"금융 정책 금융 이자율 정책 금융"
→ keywords: ["금융", "정책", "이자율"]
→ frequencies: {"금융": 3, "정책": 2, "이자율": 1}
```

---

## API 인터페이스

```json
// 요청
POST /api/v1/chunk-index/upload
{
    "document_id": "doc-uuid",
    "content": "청킹할 문서 전체 텍스트...",
    "user_id": "user-1",
    "strategy_type": "parent_child",
    "top_keywords": 10,
    "chunk_size": 500,
    "chunk_overlap": 50
}

// 응답
{
    "document_id": "doc-uuid",
    "user_id": "user-1",
    "total_chunks": 5,
    "indexed_chunks": [
        {
            "chunk_id": "uuid",
            "chunk_type": "child",
            "keywords": ["금융", "정책", "이자율"],
            "content": "청크 텍스트..."
        }
    ],
    "request_id": "uuid"
}
```

---

## ES 문서 구조 (BM25 검색용)

```python
{
    "content": chunk.page_content,       # 전체 텍스트 (BM25 기본)
    "keywords": ["금융", "정책"],         # 추출 키워드 (키워드 강화 검색)
    "chunk_id": "uuid",
    "chunk_type": "child",               # child | parent | full | semantic
    "chunk_index": 0,
    "total_chunks": 10,
    "parent_id": "uuid",                 # child 청크인 경우
    "document_id": "doc-uuid",
    "user_id": "user-1"
}
```

HYBRID-001의 BM25 검색 쿼리:
```json
{"match": {"content": "검색어"}}
// 또는 keywords 필드 포함 multi_match 검색으로 확장 가능
{"multi_match": {"query": "검색어", "fields": ["content", "keywords"]}}
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock |
|------------|------|------|
| `tests/domain/keyword/test_schemas.py` | KeywordExtractionResult 생성 | ❌ |
| `tests/infrastructure/keyword/test_simple_keyword_extractor.py` | 키워드 추출 로직 (10 케이스) | ❌ |
| `tests/application/chunk_and_index/test_use_case.py` | UseCase 오케스트레이션 (12 케이스) | ✅ |
| `tests/api/test_chunk_index_router.py` | API 엔드포인트 (9 케이스) | ✅ |

총 33 테스트 케이스.

---

## LOG-001 로깅 체크리스트

- [x] `LoggerInterface` 주입 (ChunkAndIndexUseCase)
- [x] 처리 시작/완료 INFO 로그 (`request_id`, `document_id`, `strategy_type`)
- [x] 예외 발생 시 ERROR 로그 + `exception=e` (스택 트레이스)
- [x] `request_id` 컨텍스트 전파

---

## 완료 기준

- [x] `KeywordExtractionResult` Value Object
- [x] `KeywordExtractorInterface` ABC
- [x] `SimpleKeywordExtractor` (한국어/영어 정규식 기반)
- [x] `ChunkAndIndexUseCase` 오케스트레이션
- [x] `POST /api/v1/chunk-index/upload` API
- [x] `src/api/main.py` 라우터 등록 및 DI 연결
- [x] 전체 33 테스트 통과
- [x] LOG-001 로깅 적용

---

## 확장 포인트

| 확장 | 설명 |
|------|------|
| LLM 기반 키워드 추출 | Claude API로 고품질 키워드 추출 (`KeywordExtractorInterface` 구현체 교체) |
| Qdrant 동시 색인 | 청킹과 함께 벡터 임베딩 + Qdrant 색인까지 단일 API로 처리 |
| Multi-match 검색 | `content` + `keywords` 필드 동시 검색으로 BM25 정확도 향상 |
| 불용어 커스터마이징 | 도메인(금융/정책) 특화 불용어 주입 지원 |
