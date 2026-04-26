# Plan: fix-missing-collection-permissions-table

> 작성일: 2026-04-23
> 상태: Draft

---

## 1. 문제 정의

### 1-1. 현상

`GET /api/v1/collections` 호출 시 500 에러 발생.

```
asyncmy.errors.ProgrammingError: (1146, "Table 'idt.collection_permissions' doesn't exist")
```

### 1-2. 원인 분석

마이그레이션 파일 `db/migration/V013__create_collection_permissions.sql`이 존재하지만, 실제 MySQL `idt` 데이터베이스에 테이블이 생성되지 않은 상태.

**호출 체인:**

```
collection_router.py:112  list_collections()
  → use_case.py:47  list_collections() → permission_service.get_accessible_collection_names()
    → permission_service.py:105  get_accessible_collection_names() → perm_repo.find_accessible()
      → permission_repository.py:78  find_accessible() → session.execute(stmt)
        → SQLAlchemy → MySQL: SELECT FROM collection_permissions → 1146 Table doesn't exist
```

### 1-3. 근본 원인

| 항목 | 상태 |
|------|------|
| 마이그레이션 SQL 파일 | 존재 (`V013__create_collection_permissions.sql`) |
| SQLAlchemy 모델 | 존재 (`permission_models.py: CollectionPermissionModel`) |
| Repository | 존재 (`permission_repository.py`) |
| Application Service | 존재 (`permission_service.py`) |
| **MySQL 테이블** | **미생성** |

마이그레이션이 수동 실행 방식(Flyway 형식 파일만 존재, 자동 실행 도구 미연결)이기 때문에, V013 마이그레이션이 DB에 적용되지 않았다.

### 1-4. FK 의존성

`collection_permissions` 테이블은 다음 FK를 가진다:

- `fk_perm_user`: `owner_id → users(id)` — `V002__create_auth_tables.sql`에서 생성
- `fk_perm_dept`: `department_id → departments(id)` — `V005__create_departments.sql`에서 생성

두 테이블이 이미 존재하는지 확인 필요.

---

## 2. 해결 방안

### 2-1. 즉시 조치 (DB 마이그레이션 적용)

1. `users`, `departments` 테이블 존재 확인
2. `V013__create_collection_permissions.sql` 실행하여 테이블 생성
3. `GET /api/v1/collections` 정상 동작 확인

### 2-2. 방어적 개선 (선택)

현재 `use_case.py:46`에서 `permission_service`가 존재할 때만 권한 필터링을 수행하는 조건 분기가 있으나, `permission_service`가 DI로 주입된 상태에서 테이블 미존재 시 예외가 발생한다.

**고려 옵션:**
- 테이블 미존재 시 graceful fallback (모든 컬렉션 반환) — 개발 편의성 향상
- 현재 상태 유지 (테이블 반드시 존재해야 함) — 운영 안정성 우선

---

## 3. 영향 범위

| 영향 받는 엔드포인트 | 설명 |
|----------------------|------|
| `GET /api/v1/collections` | 컬렉션 목록 조회 — 권한 필터링 실패 |
| `POST /api/v1/collections` | 컬렉션 생성 시 권한 레코드 저장 실패 가능 |
| `DELETE /api/v1/collections/{name}` | 삭제 시 권한 확인/삭제 실패 가능 |
| `PUT /api/v1/collections/{name}/scope` | 범위 변경 실패 가능 |

---

## 4. 작업 항목

| # | 작업 | 예상 시간 | 우선순위 |
|---|------|----------|----------|
| 1 | `users`, `departments` 테이블 존재 확인 | 1분 | P0 |
| 2 | V013 마이그레이션 SQL 실행 | 1분 | P0 |
| 3 | `GET /api/v1/collections` 정상 응답 확인 | 2분 | P0 |
| 4 | (선택) 테이블 미존재 시 fallback 로직 추가 검토 | 15분 | P2 |

---

## 5. 실행 방법

```sql
-- MySQL 접속 후 실행
SOURCE db/migration/V013__create_collection_permissions.sql;

-- 또는 직접 실행
CREATE TABLE IF NOT EXISTS collection_permissions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    owner_id        INT NOT NULL,
    scope           ENUM('PERSONAL','DEPARTMENT','PUBLIC') NOT NULL DEFAULT 'PERSONAL',
    department_id   VARCHAR(36) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_perm_collection_name (collection_name),
    INDEX ix_perm_owner (owner_id),
    INDEX ix_perm_department (department_id),
    INDEX ix_perm_scope (scope),
    CONSTRAINT fk_perm_user FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT fk_perm_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 6. 검증 기준

- [ ] `collection_permissions` 테이블이 MySQL에 존재
- [ ] `GET /api/v1/collections` 호출 시 200 응답
- [ ] 기존 컬렉션이 권한 레코드 없이도 목록에 표시됨
