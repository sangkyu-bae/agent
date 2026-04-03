# MORPH-IDX-001: Kiwi 형태소 + Vector DB + ES 이중 색인 API

> Task ID: MORPH-IDX-001
> 의존성: CHUNK-001, VEC-001, ES-001, KIWI-001, LOG-001
> 상태: In Progress

---

## 목적

기존 청킹 API(CHUNK-IDX-001)를 건드리지 않고,
**Kiwi 형태소 분석** 기반의 새로운 이중 색인 API를 제공한다.

| 색인 대상 | 저장 내용 |
|---------|---------|
| Qdrant (Vector DB) | 청크 임베딩 + 전체 메타데이터 |
| Elasticsearch (BM25) | 청크 텍스트 + 형태소 키워드(NNG/NNP/VV원형/VA원형) + 위치 메타데이터 |

---

## 아키텍처

```
POST /api/v1/morph-index/upload
           │
           ▼
MorphIndexRouter (interfaces/api)
           │
           ▼
MorphAndDualIndexUseCase (application)
    ├── ChunkingStrategy.chunk()           ← 기존 청킹 재사용
    ├── KiwiMorphAnalyzer.analyze()        ← KIWI-001 형태소 분석
    │   └── NNG + NNP + VV(원형) + VA(원형) 추출
    ├── EmbeddingInterface.embed_documents() ← 벡터 생성
    ├── VectorStoreInterface.add_documents() ← Qdrant 색인
    └── ElasticsearchRepository.bulk_index() ← ES 색인
           │
           ▼
Qdrant: { content, vector, chunk_id, chunk_type, char_start, char_end, ... }
Elasticsearch: { content, morph_keywords, chunk_id, char_start, char_end, ... }
```

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/morph_index/schemas.py` | `MorphIndexRequest`, `DualIndexedChunk`, `MorphIndexResult` |

### Application Layer
| 파일 | 설명 |
|------|------|
| `src/application/morph_index/use_case.py` | `MorphAndDualIndexUseCase` |

### API Layer
| 파일 | 설명 |
|------|------|
| `src/api/routes/morph_index_router.py` | `POST /api/v1/morph-index/upload` |

---

## 형태소 키워드 추출 규칙

```
NNG (일반 명사)  → surface 그대로
NNP (고유 명사)  → surface 그대로
VV  (동사)       → surface + "다"  (원형/기본형, 예: "달리" → "달리다")
VA  (형용사)     → surface + "다"  (원형/기본형, 예: "좋"  → "좋다")

중복 제거, 출현 순서 유지
```

---

## ES 문서 구조

```json
{
  "content": "청크 텍스트",
  "morph_keywords": ["금융", "정책", "달리다", "좋다"],
  "chunk_id": "uuid",
  "chunk_type": "child",
  "chunk_index": 0,
  "total_chunks": 10,
  "char_start": 0,
  "char_end": 300,
  "parent_id": "uuid",
  "document_id": "doc-uuid",
  "user_id": "user-1",
  "source": "report.pdf"
}
```

## Qdrant 페이로드 메타데이터

```python
metadata: Dict[str, str] = {
    "document_id": "doc-uuid",
    "user_id": "user-1",
    "chunk_id": "uuid",
    "chunk_type": "child",
    "chunk_index": "0",
    "total_chunks": "10",
    "char_start": "0",
    "char_end": "300",
    "parent_id": "uuid",     # child 청크인 경우
    "morph_keywords": '["금융", "정책"]',  # JSON 직렬화
    "source": "report.pdf",  # 있는 경우
}
```

---

## API 인터페이스

```json
// 요청
POST /api/v1/morph-index/upload
{
    "document_id": "doc-uuid",
    "content": "전체 문서 텍스트...",
    "user_id": "user-1",
    "strategy_type": "parent_child",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "source": "report.pdf",
    "metadata": {}
}

// 응답
{
    "document_id": "doc-uuid",
    "user_id": "user-1",
    "total_chunks": 8,
    "qdrant_indexed": 8,
    "es_indexed": 8,
    "indexed_chunks": [
        {
            "chunk_id": "uuid",
            "chunk_type": "child",
            "morph_keywords": ["금융", "정책", "달리다"],
            "content": "청크 텍스트...",
            "char_start": 0,
            "char_end": 300,
            "chunk_index": 0
        }
    ],
    "request_id": "uuid"
}
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock |
|------------|------|------|
| `tests/domain/morph_index/test_schemas.py` | 스키마 (6 케이스) | ❌ |
| `tests/application/morph_index/test_use_case.py` | UseCase 오케스트레이션 (12 케이스) | ✅ |
| `tests/api/test_morph_index_router.py` | API 엔드포인트 (9 케이스) | ✅ |

총 27 테스트 케이스.

---

## LOG-001 로깅 체크리스트

- [x] `LoggerInterface` 주입 (MorphAndDualIndexUseCase)
- [x] 처리 시작/완료 INFO 로그 (`request_id`, `document_id`, `strategy_type`)
- [x] 예외 발생 시 ERROR 로그 + `exception=e`
- [x] `request_id` 컨텍스트 전파

---

## 완료 기준

- [x] `MorphIndexRequest`, `DualIndexedChunk`, `MorphIndexResult` 스키마
- [x] `MorphAndDualIndexUseCase` 오케스트레이션
- [x] `POST /api/v1/morph-index/upload` API
- [x] `src/api/main.py` 라우터 등록 및 DI 연결
- [x] 전체 27 테스트 통과
- [x] LOG-001 로깅 적용
