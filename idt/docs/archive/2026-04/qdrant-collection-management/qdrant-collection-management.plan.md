# Plan: qdrant-collection-management

> Feature: Qdrant 벡터 DB 컬렉션 관리 API (CRUD) + 사용이력 DB 적재 + 프론트엔드 UI
> Created: 2026-04-21
> Status: Plan

---

## 1. 목적 (Why)

현재 시스템은 컬렉션을 코드 내부(`ensure_collection`)에서 암묵적으로 생성만 하고 있으며,
사용자가 컬렉션을 **조회/생성/수정(이름 변경)/삭제**할 수 있는 API나 UI가 없다.

또한 컬렉션에 대한 **모든 활동(관리 이벤트 + 검색 + 문서 추가 등)**을 MySQL에 기록하여
누가 언제 어떤 컬렉션에서 무엇을 했는지 추적할 수 있어야 한다.

---

## 2. 기능 범위 (Scope)

### In Scope

**A. 컬렉션 CRUD API**
- [x] **GET** `/api/v1/collections` — 컬렉션 목록 조회
- [x] **GET** `/api/v1/collections/{name}` — 컬렉션 상세 조회 (벡터 설정, 포인트 수)
- [x] **POST** `/api/v1/collections` — 컬렉션 생성
- [x] **PATCH** `/api/v1/collections/{name}` — 컬렉션 이름 변경 (alias 기반)
- [x] **DELETE** `/api/v1/collections/{name}` — 컬렉션 삭제

**B. 사용이력 (Activity Log)**
- [x] `collection_activity_log` MySQL 테이블 생성
- [x] 관리 이벤트 기록: 생성(CREATE), 삭제(DELETE), 이름변경(RENAME)
- [x] 조회 이벤트 기록: 목록 조회(LIST), 상세 조회(DETAIL)
- [x] 활동 이벤트 기록: 벡터 검색(SEARCH), 문서 추가(ADD_DOCUMENT), 문서 삭제(DELETE_DOCUMENT)
- [x] **GET** `/api/v1/collections/activity-log` — 전체 이력 조회 (페이지네이션, 필터)
- [x] **GET** `/api/v1/collections/{name}/activity-log` — 특정 컬렉션 이력 조회

**C. 프론트엔드 UI**
- [x] 컬렉션 관리 페이지 (목록 + 생성/삭제/이름변경)
- [x] 사용이력 탭/섹션 (테이블 + 필터)

### Out of Scope

- 벡터 설정 변경 (size, distance metric 등) — Qdrant는 생성 후 변경 불가
- 컬렉션 내 개별 포인트(문서) CRUD UI — 기존 document_upload API로 처리
- 컬렉션 백업/복원
- 컬렉션별 접근 권한 관리
- 이력 데이터 보존 정책 (자동 삭제/아카이브)

---

## 3. 기술 의존성

| 모듈 | 상태 | 비고 |
|------|------|------|
| `AsyncQdrantClient` | 구현됨 | `src/infrastructure/vector/qdrant_client.py` |
| `QdrantVectorStore` | 구현됨 | `src/infrastructure/vector/qdrant_vectorstore.py` |
| `Settings.qdrant_*` | 구현됨 | `src/config.py` |
| `MySQLBaseRepository` | 구현됨 | `src/infrastructure/persistence/mysql_base_repository.py` |
| `get_session` | 구현됨 | `src/infrastructure/persistence/database.py` |
| `LoggerInterface` | 구현됨 | LOG-001 규칙 적용 |
| 프론트엔드 API 클라이언트 | 구현됨 | `idt_front/src/services/`, `idt_front/src/constants/api.ts` |

---

## 4. API 설계 개요

### 4.1 컬렉션 CRUD

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/collections` | 목록 조회 |
| GET | `/api/v1/collections/{name}` | 상세 조회 |
| POST | `/api/v1/collections` | 생성 |
| PATCH | `/api/v1/collections/{name}` | 이름 변경 |
| DELETE | `/api/v1/collections/{name}` | 삭제 (기본 컬렉션 보호) |

### 4.2 사용이력 조회

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/collections/activity-log` | 전체 이력 (필터: collection, action, user, 날짜 범위) |
| GET | `/api/v1/collections/{name}/activity-log` | 특정 컬렉션 이력 |

### 4.3 사용이력 기록 대상

| Action Type | 발생 시점 | 기록 내용 |
|-------------|----------|-----------|
| `CREATE` | 컬렉션 생성 | name, vector_size, distance |
| `DELETE` | 컬렉션 삭제 | name |
| `RENAME` | 이름 변경 | old_name, new_name |
| `LIST` | 목록 조회 | (조회 자체 기록) |
| `DETAIL` | 상세 조회 | collection_name |
| `SEARCH` | 벡터 검색 | collection_name, query (앞 100자), top_k |
| `ADD_DOCUMENT` | 문서 추가 | collection_name, document_count |
| `DELETE_DOCUMENT` | 문서 삭제 | collection_name, document_ids |

---

## 5. DB 스키마 개요

```sql
CREATE TABLE collection_activity_log (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    action       VARCHAR(30)  NOT NULL,  -- CREATE, DELETE, RENAME, LIST, DETAIL, SEARCH, ADD_DOCUMENT, DELETE_DOCUMENT
    user_id      VARCHAR(100) NULL,
    detail       JSON         NULL,      -- 액션별 추가 정보
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_collection_name (collection_name),
    INDEX ix_action (action),
    INDEX ix_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 6. 레이어 구조 (Thin DDD)

### 컬렉션 관리

| Layer | 파일 | 역할 |
|-------|------|------|
| domain | `src/domain/collection/schemas.py` | Entity, VO, Enum 정의 |
| domain | `src/domain/collection/policy.py` | 삭제 보호, 이름 검증 규칙 |
| domain | `src/domain/collection/interfaces.py` | Repository 인터페이스 |
| application | `src/application/collection/use_case.py` | CRUD 유스케이스 |
| infrastructure | `src/infrastructure/collection/qdrant_collection_repository.py` | Qdrant API 호출 |
| interfaces | `src/api/routes/collection_router.py` | FastAPI 엔드포인트 |

### 사용이력

| Layer | 파일 | 역할 |
|-------|------|------|
| domain | `src/domain/collection/schemas.py` | ActivityLog Entity, ActionType Enum |
| domain | `src/domain/collection/interfaces.py` | ActivityLogRepositoryInterface |
| application | `src/application/collection/activity_log_service.py` | 이력 기록/조회 서비스 |
| infrastructure | `src/infrastructure/collection/models.py` | SQLAlchemy ORM 모델 |
| infrastructure | `src/infrastructure/collection/activity_log_repository.py` | MySQL 이력 저장 |

---

## 7. TDD 계획

### 백엔드

| 테스트 파일 | 대상 |
|------------|------|
| `tests/domain/collection/test_policy.py` | 삭제 보호, 이름 검증 |
| `tests/application/collection/test_use_case.py` | UseCase 흐름 |
| `tests/application/collection/test_activity_log_service.py` | 이력 기록 서비스 |
| `tests/infrastructure/collection/test_qdrant_collection_repository.py` | Qdrant API 호출 |
| `tests/infrastructure/collection/test_activity_log_repository.py` | MySQL 이력 저장 |
| `tests/api/test_collection_router.py` | 엔드포인트 통합 |

### 프론트엔드

| 테스트 파일 | 대상 |
|------------|------|
| `src/hooks/useCollections.test.ts` | Query/Mutation 훅 |
| `src/__tests__/mocks/handlers.ts` | MSW 핸들러 추가 |

---

## 8. CLAUDE.md 규칙 체크

- [x] domain에 외부 의존성 없음 (인터페이스만)
- [x] application은 domain 규칙 조합, 비즈니스 규칙 직접 구현 안 함
- [x] infrastructure에서 AsyncQdrantClient, AsyncSession 래핑
- [x] router에 비즈니스 로직 없음
- [x] Repository 내부에서 commit()/rollback() 호출 안 함
- [x] 한 UseCase 안에서 repository 별 서로 다른 세션 사용 안 함
- [x] LOG-001 로깅 적용
- [x] TDD 순서: 테스트 → 실패 확인 → 구현 → 통과

---

## 9. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Qdrant는 컬렉션 이름 변경 미지원 | 중 | alias 활용 |
| 기본 컬렉션 삭제 시 시스템 장애 | 높 | Policy에서 삭제 차단 |
| 이력 테이블 급격한 증가 (검색 포함) | 중 | 인덱스 최적화 + 향후 보존 정책 별도 설계 |
| 검색/문서추가 시 이력 기록으로 인한 성능 저하 | 중 | 이력 기록을 비동기(fire-and-forget) 처리 |

---

## 10. 완료 기준

- [ ] 5개 컬렉션 CRUD API 정상 동작
- [ ] 2개 이력 조회 API 정상 동작 (전체 + 특정 컬렉션)
- [ ] 8종 액션 타입 이력 자동 기록
- [ ] 기본 컬렉션 삭제 보호 동작
- [ ] 프론트엔드 컬렉션 관리 + 이력 조회 페이지
- [ ] 백엔드 테스트 커버리지 (domain + application + router)
- [ ] DB 마이그레이션 파일 생성 (V011)
- [ ] LOG-001 로깅 적용

---

## 11. 다음 단계

1. [ ] Design 문서 작성 (`qdrant-collection-management.design.md`)
2. [ ] 이름 변경 구현 방식 확정 (alias vs 복사+삭제)
3. [ ] 구현 시작 (TDD)
