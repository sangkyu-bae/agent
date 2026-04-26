# Plan: 문서 목록 조회 성능 최적화

> Feature: `doc-list-optimization`
> Created: 2026-04-23
> Status: Draft
> Priority: High

---

## 1. 현재 상태 (As-Is)

### 문제 코드: `src/application/doc_browse/list_documents_use_case.py`

```
execute()
  → _scroll_all()         # Qdrant에서 전체 포인트를 scroll로 전건 조회
  → _group_by_document()  # Python에서 document_id 기준 그룹핑
  → _build_summaries()    # 그룹별 요약 생성
  → 메모리 내 슬라이싱     # summaries[offset:offset+limit]
```

### 핵심 문제

| 항목 | 설명 |
|------|------|
| **전건 스캔** | `_scroll_all()`이 컬렉션의 **모든 포인트**를 메모리에 로드 (SCROLL_BATCH_LIMIT=10,000씩 반복) |
| **O(N) 그룹핑** | Python `defaultdict`로 전체 포인트를 순회하며 `document_id` 기준 그룹핑 |
| **메모리 부하** | 문서 10,000건 × 평균 20청크 = 200,000 포인트가 한번에 메모리 적재 |
| **페이지네이션 무효** | offset/limit 파라미터가 있지만 **이미 전건 조회 후** 슬라이싱하므로 DB 레벨 페이지네이션 효과 없음 |
| **응답 지연** | 컬렉션 규모가 커질수록 선형적으로 응답시간 증가 |

---

## 2. 개선안 비교

### Option A: Qdrant Payload Index + Facet/Group API 활용

Qdrant 자체 기능으로 `document_id` 필드에 payload index를 생성하고, group API 또는 scroll + filter를 활용하여 DB 수준에서 그룹핑한다.

**구현 방법:**
1. `document_id` 필드에 keyword payload index 생성
2. Qdrant `group` API(`/points/query/groups`)로 document_id별 그룹 조회
3. group API에서 `limit`, `group_size` 파라미터로 DB 레벨 페이지네이션

**장점:**
- 별도 저장소 추가 불필요
- 기존 데이터 마이그레이션 불필요
- Qdrant 단독으로 완결

**단점:**
- Qdrant group API의 페이지네이션이 offset 기반이 아닌 커서 기반일 수 있어 정확한 offset/limit 구현에 제약
- document 메타데이터(filename, category 등)를 여전히 첫 번째 청크의 payload에서 추출해야 함
- Qdrant 버전 의존성 (group API는 1.7+ 필요)

**예상 작업량:** 2~3일

---

### Option B: MySQL에 문서 메타데이터 테이블 추가 (권장)

Ingest 시점에 MySQL `documents` 테이블에 문서 메타정보를 저장하고, 목록 조회는 MySQL에서 수행한다.

**구현 방법:**
1. `documents` 테이블 생성 (document_id, filename, category, user_id, chunk_count, chunk_strategy, collection_name, created_at)
2. `IngestDocumentUseCase.ingest()` 완료 시 MySQL에 문서 메타 레코드 INSERT
3. `ListDocumentsUseCase`가 MySQL에서 `SELECT ... LIMIT/OFFSET` 조회
4. 문서 삭제 시 MySQL 레코드도 함께 DELETE

**장점:**
- **DB 레벨 페이지네이션**: SQL의 LIMIT/OFFSET으로 진정한 페이지네이션
- **O(1) 카운트**: `SELECT COUNT(*)` 로 즉시 total 계산
- **확장성**: 검색, 필터링, 정렬이 SQL 인덱스로 효율적
- **관심사 분리**: 벡터DB는 검색 전용, RDB는 메타데이터 관리 전용

**단점:**
- MySQL ↔ Qdrant 간 데이터 정합성 관리 필요 (ingest/delete 시 양쪽 동기화)
- 기존 데이터 마이그레이션 스크립트 필요 (Qdrant → MySQL 역동기화)
- 테이블 스키마 + Repository + Migration 추가 작업

**예상 작업량:** 3~5일

---

### Option C: Qdrant Scroll + 서버 캐시 (Redis)

현재 로직을 유지하되, 문서 목록 결과를 Redis에 캐시하여 반복 조회 시 전건 스캔을 피한다.

**구현 방법:**
1. `ListDocumentsUseCase` 결과를 Redis에 TTL 캐시
2. Ingest/Delete 시 해당 컬렉션 캐시 무효화
3. 캐시 히트 시 즉시 응답, 미스 시 기존 로직 수행

**장점:**
- 기존 코드 변경 최소화
- 반복 조회 시 즉시 응답

**단점:**
- **근본 해결 아님**: 캐시 미스 시 여전히 전건 스캔
- 캐시 무효화 로직 복잡 (ingest, delete, update 시마다)
- Redis 인프라 의존성 추가
- 데이터 규모가 커지면 캐시 빌드 자체가 느림

**예상 작업량:** 2~3일

---

## 3. 추천 평가 매트릭스

| 기준 | Option A (Qdrant API) | Option B (MySQL) | Option C (Redis 캐시) |
|------|:---:|:---:|:---:|
| 근본적 해결 | ◎ | ◎ | △ |
| 페이지네이션 정확성 | ○ | ◎ | △ |
| 확장성 (필터/정렬) | △ | ◎ | △ |
| 구현 복잡도 | ○ | △ | ◎ |
| 데이터 정합성 리스크 | ◎ | △ | ○ |
| 기존 코드 변경량 | ○ | △ | ◎ |
| 인프라 추가 | 없음 | 없음 (MySQL 기존) | Redis 필요 |

> ◎ 우수 / ○ 보통 / △ 주의 필요

---

## 4. 권장안: Option B (MySQL 문서 메타데이터 테이블)

### 선정 근거

1. **MySQL이 이미 존재**: 프로젝트에 MySQL이 인프라로 세팅되어 있어 추가 비용 없음
2. **관심사 분리 원칙**: 벡터DB(Qdrant)는 임베딩 검색 전용, 메타데이터 관리는 RDB가 적합
3. **확장 가능성**: 향후 문서 검색(filename LIKE), 카테고리 필터, 정렬(최신순/이름순) 등 SQL로 즉시 구현 가능
4. **진정한 페이지네이션**: DB 레벨 LIMIT/OFFSET으로 대용량에서도 일정한 응답시간 보장
5. **사용자 의견과 일치**: "db에 저장하는 방법도 괜찮다"는 판단이 아키텍처적으로 정확

### 대안 활용: Option A를 단기 대안으로

Option B 구현 전 빠른 개선이 필요하다면, Option A(Qdrant payload index)를 중간 단계로 먼저 적용하는 것도 가능하다.

---

## 5. Option B 상세 구현 범위

### 5-1. 신규 테이블 스키마

```sql
CREATE TABLE documents (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id   VARCHAR(64) NOT NULL UNIQUE,
    collection_name VARCHAR(128) NOT NULL,
    filename      VARCHAR(512) NOT NULL,
    category      VARCHAR(128) NOT NULL DEFAULT 'uncategorized',
    user_id       VARCHAR(128) NOT NULL DEFAULT '',
    chunk_count   INT NOT NULL DEFAULT 0,
    chunk_strategy VARCHAR(64) NOT NULL DEFAULT 'unknown',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_collection (collection_name),
    INDEX idx_user (user_id),
    INDEX idx_created (created_at)
);
```

### 5-2. 변경 대상 파일

| 레이어 | 파일 | 변경 내용 |
|--------|------|----------|
| **domain** | `src/domain/doc_browse/interfaces.py` (신규) | DocumentMetadataRepository 인터페이스 정의 |
| **domain** | `src/domain/doc_browse/schemas.py` | DocumentMetadata 엔티티 추가 |
| **infrastructure** | `src/infrastructure/doc_browse/models.py` (신규) | SQLAlchemy DocumentModel |
| **infrastructure** | `src/infrastructure/doc_browse/document_repository.py` (신규) | MySQL Repository 구현 |
| **application** | `src/application/doc_browse/list_documents_use_case.py` | MySQL 조회로 교체 |
| **application** | `src/application/ingest/ingest_use_case.py` | ingest 완료 시 MySQL INSERT 추가 |
| **api** | `src/api/main.py` | DI 바인딩 추가 |
| **db/migration** | `db/migration/V0XX__create_documents_table.sql` (신규) | DDL |
| **script** | `scripts/migrate_doc_metadata.py` (신규) | 기존 Qdrant 데이터 → MySQL 역동기화 |

### 5-3. 시퀀스 흐름 (To-Be)

```
[문서 업로드 (Ingest)]
  → Qdrant에 청크+벡터 저장 (기존)
  → MySQL documents 테이블에 메타 INSERT (신규)

[문서 목록 조회 (ListDocuments)]
  → MySQL SELECT ... WHERE collection_name=? LIMIT ? OFFSET ?
  → 즉시 응답 (Qdrant 조회 없음)

[문서 삭제]
  → Qdrant에서 청크 삭제 (기존)
  → MySQL documents 테이블 DELETE (신규)
```

---

## 6. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| MySQL ↔ Qdrant 정합성 불일치 | 목록에는 보이지만 검색 안됨 (또는 반대) | Ingest/Delete를 하나의 UseCase 트랜잭션으로 묶고, 실패 시 rollback/보상 로직 |
| 기존 데이터 마이그레이션 누락 | 기존 문서가 목록에 안 보임 | 마이그레이션 스크립트로 Qdrant scroll → MySQL INSERT 일괄 수행 |
| chunk_count 불일치 | 실제 청크 수와 DB 기록 불일치 | Ingest 완료 후 실제 저장된 chunk 수로 기록. 주기적 정합성 체크 배치 고려 |

---

## 7. 성공 기준

| 항목 | 기준 |
|------|------|
| 응답 시간 | 문서 1,000건 이상 컬렉션에서 목록 조회 < 200ms |
| 메모리 | 목록 조회 시 Qdrant 전건 스캔 제거 (메모리 사용량 O(page_size)) |
| 페이지네이션 | DB 레벨 LIMIT/OFFSET 동작 확인 |
| 정합성 | Ingest → 목록 즉시 반영, Delete → 목록에서 즉시 제거 |
| 하위 호환 | 기존 API 응답 스키마 변경 없음 |

---

## 8. 구현 순서

1. **[TDD]** DocumentMetadataRepository 인터페이스 + MySQL 구현 테스트
2. **[Schema]** SQLAlchemy Model + Flyway 마이그레이션 DDL
3. **[Refactor]** ListDocumentsUseCase → MySQL 조회로 교체
4. **[Integration]** IngestDocumentUseCase에 MySQL INSERT 연동
5. **[Migration Script]** 기존 Qdrant 데이터 → MySQL 역동기화
6. **[E2E]** 전체 흐름 검증 (Ingest → List → Delete)
