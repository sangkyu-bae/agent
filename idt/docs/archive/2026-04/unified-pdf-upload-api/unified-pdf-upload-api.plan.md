# Plan: Unified PDF Upload API

> Created: 2026-04-26
> Updated: 2026-04-26
> Feature: unified-pdf-upload-api
> Phase: Plan

---

## 1. 배경 및 동기

현재 PDF 문서를 업로드하고 검색 가능하게 만들려면 **2개 API를 순차 호출**해야 한다:

1. `POST /api/v1/documents/upload` — PDF 파싱 → Parent-Child 청킹 → **Qdrant(벡터)만 저장**
2. `POST /api/v1/chunk-index/upload` — 텍스트 → 청킹 → 키워드 추출 → **ES(BM25)만 저장**

문제점:
- 프론트엔드에서 2회 API 호출 필요 (첫 번째 결과의 텍스트를 두 번째에 전달)
- 동일한 청킹을 2번 수행하는 비효율
- Qdrant/ES 간 청크 불일치 가능성 (별도 호출이므로 파라미터가 달라질 수 있음)
- 하이브리드 검색(시맨틱 + BM25)의 정합성 보장이 어려움
- 컬렉션별 임베딩 모델이 다를 수 있으나 기존 API는 하드코딩된 임베딩 모델 사용

## 2. 목표

**사용자가 기존 컬렉션을 선택하고 PDF를 업로드하면, 해당 컬렉션의 임베딩 모델에 맞춰 Qdrant(벡터) + ES(BM25) 동시 저장**을 완료하는 단일 API를 제공한다.

### 2-1. 핵심 목표
- 사용자가 선택한 컬렉션의 임베딩 모델을 자동으로 조회하여 적용
- PDF 파일 + 청킹 파라미터를 받아 한 번에 양쪽 저장소에 저장
- 동일한 청크 결과를 Qdrant와 ES에 일관되게 저장
- 프론트엔드 호출 1회로 단순화

### 2-2. 비목표 (Scope 외)
- 기존 `/api/v1/documents/upload` 엔드포인트 수정 (그대로 유지)
- 기존 `/api/v1/chunk-index/upload` 엔드포인트 수정 (그대로 유지)
- LLM 기반 문서 분류(classify) — 이번 API에서는 제외
- Excel/텍스트 등 PDF 외 파일 형식 지원
- 컬렉션 자동 생성 — 반드시 사전 생성된 컬렉션을 사용

## 3. 사용자 플로우

```
사용자가 컬렉션 목록에서 기존 컬렉션 선택
  → "문서 업로드" 버튼 클릭
  → PDF 파일 + 청킹 옵션 입력
  → API 1회 호출
  → 해당 컬렉션의 임베딩 모델로 벡터 생성 + ES BM25 저장
  → 완료 결과 표시
```

## 4. 기능 요구사항

### FR-01: 새 엔드포인트 생성

| 항목 | 값 |
|------|-----|
| Method | POST |
| Path | `/api/v1/documents/upload-all` |
| Content-Type | multipart/form-data |

### FR-02: 입력 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| file | UploadFile | O | - | PDF 파일 |
| user_id | str (Query) | O | - | 문서 소유자 ID |
| collection_name | str (Query) | O | - | 대상 Qdrant 컬렉션명 (기존 컬렉션) |
| child_chunk_size | int (Query) | X | 500 | 자식 청크 크기 (토큰, 100~4000) |
| child_chunk_overlap | int (Query) | X | 50 | 자식 청크 오버랩 (토큰, 0~500) |
| top_keywords | int (Query) | X | 10 | ES 저장 시 추출할 키워드 수 |

- **Parent 청크 크기**: 2000 토큰 고정 (사용자 입력 불가)

### FR-03: 컬렉션 임베딩 모델 자동 조회

사용자가 입력한 `collection_name`으로 해당 컬렉션의 임베딩 모델을 자동으로 결정한다.

**조회 흐름:**

```
1. collection_name으로 Qdrant 컬렉션 존재 여부 확인
   → 없으면 422 에러 반환

2. collection_activity_log 테이블에서 해당 컬렉션의 CREATE 액션 조회
   → detail JSON에서 embedding_model 추출

3. embedding_model 테이블에서 model_name으로 조회
   → provider, model_name, vector_dimension 획득

4. 해당 provider + model_name으로 임베딩 인스턴스 생성
   예: provider="openai", model_name="text-embedding-3-small" → OpenAIEmbedding(model="text-embedding-3-small")
```

**관련 테이블:**

| 테이블 | 사용 목적 |
|--------|----------|
| `collection_activity_log` | CREATE 이벤트의 `detail.embedding_model`에서 모델명 추출 |
| `embedding_model` | `model_name`으로 조회하여 `provider`, `vector_dimension` 획득 |

**에러 케이스:**

| 상황 | 동작 |
|------|------|
| 컬렉션이 Qdrant에 없음 | HTTP 422: "Collection '{name}' not found" |
| activity_log에 CREATE 기록 없음 | HTTP 422: "Cannot determine embedding model for collection" |
| embedding_model 테이블에 해당 모델 없음 | HTTP 422: "Embedding model '{name}' not registered" |

### FR-04: 처리 파이프라인

```
PDF 업로드 + collection_name
  → 1. 컬렉션 존재 확인 (Qdrant)
  → 2. 임베딩 모델 조회 (activity_log → embedding_model 테이블)
  → 3. PDF 파싱 (PDFParserInterface)
  → 4. Parent-Child 청킹 (ParentChildStrategy)
  → 5-A. Qdrant 저장 (조회된 임베딩 모델로 벡터 생성 → 해당 컬렉션에 저장)
  → 5-B. ES 저장 (키워드 추출 → BM25 인덱싱)
  → 6. activity_log에 ADD_DOCUMENT 기록
  → 7. 통합 응답 반환
```

- 5-A와 5-B는 동일한 청크 결과를 사용 (1회 청킹)
- 5-A와 5-B는 독립적이므로 `asyncio.gather`로 병렬 실행 가능

### FR-05: 응답 스키마

```json
{
  "document_id": "uuid",
  "filename": "example.pdf",
  "total_pages": 10,
  "chunk_count": 25,
  "qdrant": {
    "collection_name": "my-collection",
    "stored_ids": ["id1", "id2"],
    "embedding_model": "text-embedding-3-small",
    "status": "success"
  },
  "es": {
    "index_name": "my-index",
    "indexed_count": 25,
    "status": "success"
  },
  "chunking_config": {
    "strategy": "parent_child",
    "parent_chunk_size": 2000,
    "child_chunk_size": 500,
    "child_chunk_overlap": 50
  },
  "status": "completed"
}
```

### FR-06: 에러 처리

| 시나리오 | 동작 |
|----------|------|
| 컬렉션 미존재 | HTTP 422 즉시 반환 |
| 임베딩 모델 조회 실패 | HTTP 422 즉시 반환 |
| PDF 파싱 실패 | HTTP 422 즉시 반환 |
| 청킹 실패 | HTTP 500 즉시 반환 |
| Qdrant 저장 실패, ES 성공 | 부분 성공 반환 (status별 표기) |
| ES 저장 실패, Qdrant 성공 | 부분 성공 반환 (status별 표기) |
| 양쪽 모두 실패 | HTTP 500 전체 실패 반환 |

- 한쪽 저장소 실패 시에도 다른 쪽 결과는 유지 (부분 성공 허용)

## 5. 아키텍처 설계 방향

### 5-1. 새로 생성할 파일

| 파일 | 레이어 | 역할 |
|------|--------|------|
| `src/application/unified_upload/use_case.py` | Application | 통합 업로드 오케스트레이션 |
| `src/application/unified_upload/schemas.py` | Application | 요청/응답 DTO |
| `src/api/routes/unified_upload_router.py` | Interface | API 엔드포인트 |

### 5-2. 재사용할 기존 모듈

| 모듈 | 위치 | 용도 |
|------|------|------|
| PDFParserInterface | `src/domain/parser/interfaces.py` | PDF 파싱 |
| ParentChildStrategy | `src/infrastructure/chunking/strategies/` | 청킹 |
| ChunkingStrategyFactory | `src/infrastructure/chunking/chunking_factory.py` | 전략 생성 |
| CollectionRepositoryInterface | `src/domain/collection/interfaces.py` | 컬렉션 존재 확인 |
| ActivityLogRepository | `src/infrastructure/collection/activity_log_repository.py` | 임베딩 모델명 조회 |
| EmbeddingModelRepositoryInterface | `src/domain/embedding_model/interfaces.py` | 임베딩 모델 정보 조회 |
| VectorStoreInterface | `src/domain/vector/interfaces.py` | Qdrant 저장 |
| EmbeddingInterface | `src/domain/vector/interfaces.py` | 임베딩 생성 |
| ElasticsearchRepositoryInterface | `src/domain/elasticsearch/interfaces.py` | ES 저장 |
| SimpleKeywordExtractor | `src/infrastructure/keyword/` | 키워드 추출 |
| ActivityLogService | `src/application/collection/activity_log_service.py` | ADD_DOCUMENT 기록 |

### 5-3. DI 구성

`src/api/main.py`에서 `UnifiedUploadUseCase`에 아래 의존성을 조립하여 주입:
- PDF 파서
- 컬렉션 레포지토리 (Qdrant 존재 확인)
- 활동 로그 레포지토리 (임베딩 모델명 조회)
- 임베딩 모델 레포지토리 (모델 상세 조회)
- 임베딩 팩토리 (provider별 임베딩 인스턴스 생성)
- 벡터 스토어 팩토리 (컬렉션별 Qdrant 클라이언트)
- ES 레포지토리
- 키워드 추출기
- 활동 로그 서비스 (ADD_DOCUMENT 기록)

### 5-4. 임베딩 팩토리 필요성

현재 `OpenAIEmbedding`은 생성 시 `model_name`이 고정된다. 컬렉션별로 다른 모델을 사용하려면 **요청 시점에 동적으로 임베딩 인스턴스를 생성**해야 한다.

```
EmbeddingFactory.create(provider="openai", model_name="text-embedding-3-small")
→ OpenAIEmbedding(model_name="text-embedding-3-small")
```

기존에 이 패턴이 없다면 간단한 팩토리 함수를 추가한다.

## 6. 수용 기준

- [ ] `POST /api/v1/documents/upload-all`로 PDF 업로드 시 Qdrant + ES 모두 저장됨
- [ ] 컬렉션의 임베딩 모델이 자동으로 조회되어 올바른 모델로 임베딩됨
- [ ] 존재하지 않는 컬렉션명 입력 시 422 에러 반환
- [ ] child_chunk_size, child_chunk_overlap 파라미터로 청킹 크기 조절 가능
- [ ] Qdrant와 ES에 저장된 청크의 chunk_id가 동일 (정합성)
- [ ] 업로드 후 activity_log에 ADD_DOCUMENT 액션 기록됨
- [ ] 한쪽 저장소 실패 시 부분 성공 응답 반환
- [ ] 기존 `/documents/upload`, `/chunk-index/upload` API 영향 없음
- [ ] TDD: 유스케이스 단위 테스트 작성 (Red → Green → Refactor)

## 7. 의존성 및 전제조건

- Qdrant 서버 가동 중 + 대상 컬렉션 사전 생성
- Elasticsearch 서버 가동 중
- embedding_model 테이블에 사용할 모델 등록됨
- 컬렉션 생성 시 activity_log에 embedding_model 정보 기록됨
- 기존 chunking, vector, elasticsearch 인프라 모듈 정상 동작

## 8. 예상 작업 규모

| 항목 | 예상 |
|------|------|
| 신규 파일 | 3~4개 (use_case, schemas, router, embedding_factory) |
| 수정 파일 | 1개 (main.py — DI 등록) |
| 테스트 파일 | 1~2개 |
| 난이도 | 중 (기존 모듈 조합 + 임베딩 모델 동적 조회 로직 추가) |
