# Plan: Qdrant → MySQL 문서 메타데이터 역동기화

> Feature: `qdrant-mysql-data-migration`
> Created: 2026-04-24
> Status: Draft
> Priority: High
> Related: `doc-list-optimization` (archived: 2026-04)

---

## 1. 배경 및 목적

### 선행 작업 (doc-list-optimization)

`doc-list-optimization` 기능이 완료되어 아래 인프라가 모두 구축된 상태이다:

| 항목 | 상태 | 파일 |
|------|------|------|
| DDL | 완료 | `db/migration/V014__create_document_metadata.sql` |
| Domain 엔티티/인터페이스 | 완료 | `src/domain/doc_browse/schemas.py`, `interfaces.py` |
| MySQL Repository | 완료 | `src/infrastructure/doc_browse/document_metadata_repository.py` |
| Session-scoped Repository | 완료 | `src/infrastructure/doc_browse/session_scoped_metadata_repository.py` |
| ListDocumentsUseCase (MySQL 조회) | 완료 | `src/application/doc_browse/list_documents_use_case.py` |
| IngestUseCase (신규 문서 MySQL 저장) | 완료 | `src/application/ingest/ingest_use_case.py` |
| DI 바인딩 | 완료 | `src/api/main.py` |
| 마이그레이션 스크립트 | 완료 | `scripts/migrate_doc_metadata.py` |

### 현재 문제

신규 Ingest 문서는 자동으로 MySQL에 저장되지만, **기존에 Qdrant에만 저장된 문서 데이터**는 MySQL `document_metadata` 테이블에 존재하지 않는다.
따라서 문서 목록 조회 시 **기존 문서가 보이지 않는** 상태이다.

### 목적

Qdrant의 모든 컬렉션에 저장된 기존 문서 메타데이터를 MySQL `document_metadata` 테이블로 이관하여,
문서 목록 조회가 신규/기존 문서 구분 없이 정상 동작하도록 한다.

---

## 2. 현재 상태 분석 (As-Is)

### 데이터 흐름

```
[기존 문서 (Ingest 완료)]
  Qdrant: 청크+벡터 저장됨 ✅
  MySQL document_metadata: 레코드 없음 ❌
  → 문서 목록 조회 시 표시 안 됨

[신규 문서 (코드 배포 이후 Ingest)]
  Qdrant: 청크+벡터 저장됨 ✅
  MySQL document_metadata: 자동 INSERT ✅
  → 문서 목록 조회 정상 표시
```

### Qdrant 포인트에서 추출 가능한 메타데이터

각 포인트의 `payload`에서 아래 정보를 추출할 수 있다:

| 필드 | payload key | 비고 |
|------|------------|------|
| document_id | `document_id` | 문서 고유 ID |
| filename | `filename` | 원본 파일명 |
| category | `category` | 문서 분류 (없으면 "uncategorized") |
| user_id | `user_id` | 업로드 사용자 (없으면 "") |
| chunk_count | — | 동일 document_id 포인트 수로 계산 |
| chunk_strategy | `chunk_type` 유추 | "parent" 포함 시 parent_child, 아니면 full_token |
| collection_name | — | 컬렉션 이름 자체 |

---

## 3. 구현 범위

### 3-1. DDL 적용 확인

`document_metadata` 테이블이 운영 DB에 생성되어 있는지 확인한다.
생성되지 않았다면 `V014__create_document_metadata.sql`을 적용한다.

### 3-2. 마이그레이션 스크립트 실행

기존 `scripts/migrate_doc_metadata.py` 스크립트를 사용한다.

```
실행 흐름:
  1. Qdrant 전체 컬렉션 목록 조회
  2. 컬렉션별 scroll로 모든 포인트 순회 (with_vectors=False)
  3. document_id 기준 그룹핑
  4. 그룹별 메타정보 추출 → MySQL INSERT (이미 존재하면 SKIP)
```

**스크립트 특징:**
- UPSERT가 아닌 **SKIP** 방식 (이미 존재하는 document_id는 건너뜀)
- 배치 크기: 10,000 포인트씩 scroll
- 트랜잭션: 컬렉션 단위 `session.begin()` 내에서 처리

### 3-3. 검증 (Verification)

마이그레이션 완료 후 아래 항목을 검증한다:

| 검증 항목 | 방법 | 기대 결과 |
|-----------|------|----------|
| 레코드 수 일치 | Qdrant 고유 document_id 수 vs MySQL row 수 비교 | 일치 |
| 필드 정합성 | 샘플 문서 5건 이상 Qdrant payload vs MySQL 비교 | filename, category, user_id 일치 |
| 목록 API 정상 | `GET /collections/{name}/documents` 호출 | 기존 문서 모두 표시 |
| chunk_count 정확성 | Qdrant 포인트 수 vs MySQL chunk_count 비교 | 일치 |

### 3-4. 엣지 케이스 대응

| 케이스 | 대응 |
|--------|------|
| payload에 `document_id` 없는 포인트 | `"unknown"`으로 그룹핑 (스크립트 기존 동작) |
| payload에 `filename` 없는 포인트 | `"unknown"`으로 기록 |
| 동일 document_id가 여러 컬렉션에 존재 | UNIQUE KEY 충돌 → 첫 번째 컬렉션 기준 저장, 이후 SKIP |
| Qdrant 연결 실패 | 스크립트 에러로 중단 → 재실행 시 SKIP으로 이어서 처리 가능 |

---

## 4. 실행 계획

### 4-1. 사전 준비 (Pre-Migration)

```bash
# 1. MySQL에 document_metadata 테이블 존재 확인
mysql -u $MYSQL_USER -p $MYSQL_DB -e "SHOW TABLES LIKE 'document_metadata';"

# 2. 테이블 미존재 시 DDL 적용
mysql -u $MYSQL_USER -p $MYSQL_DB < db/migration/V014__create_document_metadata.sql

# 3. Qdrant 연결 확인
python -c "from qdrant_client import QdrantClient; c = QdrantClient(host='localhost', port=6333); print(c.get_collections())"

# 4. 현재 MySQL document_metadata 레코드 수 확인 (비어있어야 함 또는 신규 문서만 존재)
mysql -u $MYSQL_USER -p $MYSQL_DB -e "SELECT COUNT(*) FROM document_metadata;"
```

### 4-2. 마이그레이션 실행

```bash
# idt/ 디렉토리에서 실행
python -m scripts.migrate_doc_metadata
```

### 4-3. 사후 검증 (Post-Migration)

```bash
# 1. MySQL 레코드 수 확인
mysql -u $MYSQL_USER -p $MYSQL_DB -e "SELECT collection_name, COUNT(*) as doc_count FROM document_metadata GROUP BY collection_name;"

# 2. 문서 목록 API 호출 테스트
curl http://localhost:8000/collections/{collection_name}/documents?limit=10

# 3. 샘플 데이터 확인
mysql -u $MYSQL_USER -p $MYSQL_DB -e "SELECT document_id, filename, category, chunk_count FROM document_metadata LIMIT 10;"
```

---

## 5. 리스크 및 대응

| 리스크 | 영향도 | 대응 |
|--------|--------|------|
| 대량 데이터 시 스크립트 실행 시간 | Medium | 컬렉션별 순차 처리이므로 문서 수에 비례. 10,000문서 기준 수 분 이내 예상 |
| MySQL 디스크 부족 | Low | document_metadata는 경량 테이블 (문서당 ~500 bytes). 10,000문서 ≈ 5MB |
| Qdrant 고아 데이터 (payload 불완전) | Low | `"unknown"` 기본값으로 처리. 목록에는 표시되나 정보 부정확 |
| 스크립트 중간 실패 | Low | SKIP 방식이므로 재실행 시 이미 처리된 건은 건너뜀 (멱등성 보장) |

---

## 6. 롤백 전략

마이그레이션이 문제를 일으킬 경우:

```sql
-- 마이그레이션된 데이터 전체 삭제 (신규 Ingest 데이터도 함께 삭제되므로 주의)
TRUNCATE TABLE document_metadata;

-- 또는 특정 시점 이전 데이터만 삭제 (마이그레이션 실행 시간 기준)
DELETE FROM document_metadata WHERE created_at < '2026-04-24 12:00:00';
```

rollback 후에도 기존 시스템에는 영향 없음 (Qdrant 데이터는 변경하지 않으므로).

---

## 7. 성공 기준

| 항목 | 기준 |
|------|------|
| 데이터 완전성 | Qdrant 전 컬렉션의 고유 document_id가 MySQL에 100% 존재 |
| 목록 API 정상 | 모든 컬렉션에서 기존 문서가 목록 조회에 표시 |
| 스크립트 멱등성 | 재실행 시 중복 INSERT 없음 (SKIP 동작 확인) |
| 운영 영향 없음 | 마이그레이션 중/후 기존 Qdrant 검색 기능 정상 동작 |

---

## 8. 구현 순서

| 순서 | 작업 | 예상 시간 |
|------|------|----------|
| 1 | DDL 적용 확인 및 테이블 생성 | 5분 |
| 2 | Qdrant 연결 확인 + 컬렉션 목록 파악 | 5분 |
| 3 | 마이그레이션 스크립트 실행 | 데이터 규모에 따라 1~10분 |
| 4 | 데이터 정합성 검증 (레코드 수, 필드 비교) | 10분 |
| 5 | 문서 목록 API 통합 테스트 | 5분 |
| 6 | (선택) 검증 스크립트 작성 — Qdrant vs MySQL 자동 비교 | 30분 |

---

## 9. 선택적 개선 사항

### 9-1. 자동 검증 스크립트

마이그레이션 후 데이터 정합성을 자동으로 확인하는 검증 스크립트를 추가할 수 있다.

```
scripts/verify_doc_metadata.py

역할:
  1. Qdrant 전 컬렉션 순회 → 고유 document_id 집합 생성
  2. MySQL document_metadata 전체 조회 → document_id 집합 생성
  3. 차집합 비교: Qdrant에만 있는 문서, MySQL에만 있는 문서 리포트
  4. 샘플 비교: 랜덤 10건의 filename/category/chunk_count 일치 여부 확인
```

### 9-2. 주기적 정합성 체크

운영 중 정합성 불일치가 발생할 수 있으므로, 주기적으로 검증 스크립트를 실행하는 것을 권장한다.
(예: 주 1회 cron job 또는 수동 실행)
