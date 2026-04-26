# collection-permission-management Planning Document

> **Summary**: 벡터 DB 컬렉션에 대한 권한 기반 관리 — 개인/부서/관리자 역할별로 컬렉션 접근 및 문서(청킹) 추가·삭제·조회를 제어한다.
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-04-22
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 Qdrant 컬렉션은 인증된 사용자라면 누구나 모든 컬렉션에 접근·수정·삭제할 수 있다.
문서 관리 단계에서 **개인·부서·관리자** 3단계 권한 모델을 도입하여 컬렉션별 접근 범위를 제어한다.

### 1.2 Background

- 벡터 DB(Qdrant) 컬렉션은 이미 구축 완료
- 인증 시스템: `User`(role=user|admin), `Department`, `UserDepartment` 엔티티 존재
- 현재 컬렉션 API(`/api/v1/collections`)에는 권한 검사 없음
- 향후 문서 관리 UI에서 "내 컬렉션 / 우리 부서 컬렉션 / 전체 관리" 구분이 필요

### 1.3 Current System Analysis

| 구성요소 | 현재 상태 | 비고 |
|----------|----------|------|
| User | `UserRole.USER / ADMIN` | 2단계 역할 |
| Department | departments, user_departments 테이블 존재 | 부서↔사용자 N:M 매핑 |
| Collection | Qdrant 기반, 권한 없음 | 전체 공개 |
| Activity Log | collection_activity_log 테이블 | user_id 기록 중 |
| Ingest | IngestDocumentUseCase | collection_name 파라미터로 대상 컬렉션 지정 |

### 1.4 Related Documents

- Auth entities: `src/domain/auth/entities.py` (UserRole, User)
- Auth dependency: `src/interfaces/dependencies/auth.py` (get_current_user, require_role)
- Department entity: `src/domain/department/entity.py` (Department, UserDepartment)
- Collection interface: `src/domain/collection/interfaces.py`
- Collection use case: `src/application/collection/use_case.py`
- Collection router: `src/api/routes/collection_router.py`
- Ingest use case: `src/application/ingest/ingest_use_case.py`

---

## 2. Permission Model

### 2.1 Ownership Scope (3단계)

| Scope | 설명 | 예시 |
|-------|------|------|
| **PERSONAL** | 생성한 사용자 본인만 접근 | 개인 학습용 문서 컬렉션 |
| **DEPARTMENT** | 해당 부서 소속 사용자 전원 접근 | 부서 공유 정책/매뉴얼 컬렉션 |
| **PUBLIC** | 모든 인증 사용자 접근 (기존 동작) | 회사 공통 문서 컬렉션 |

### 2.2 Role-based Permission Matrix

| Action | PERSONAL 소유자 | DEPARTMENT 소속원 | ADMIN | 비소유 일반 USER |
|--------|:--------------:|:-----------------:|:-----:|:----------------:|
| 컬렉션 조회 (목록) | O (자기 것만) | O (부서 것) | O (전체) | O (PUBLIC만) |
| 컬렉션 상세 조회 | O | O | O | PUBLIC만 |
| 청킹 문서 추가 | O | O | O | X |
| 청킹 문서 삭제 | O | O (부서 권한 정책에 따라) | O | X |
| 컬렉션 생성 | O | O | O | O (PERSONAL만) |
| 컬렉션 삭제 | O (자기 것만) | X | O | X |
| 컬렉션 이름 변경 | O (자기 것만) | X | O | X |
| 권한 변경 (scope 변경) | O (자기 것만) | X | O | X |

### 2.3 Admin Override

- `UserRole.ADMIN`은 모든 컬렉션에 대해 전체 권한을 가진다.
- Admin은 어떤 컬렉션이든 scope를 변경할 수 있다.

---

## 3. Scope

### 3.1 In Scope

- [ ] 컬렉션-소유권 매핑 테이블 설계 (MySQL: `collection_permissions`)
- [ ] 컬렉션 생성 시 소유자(user_id) 및 scope 자동 기록
- [ ] 컬렉션 목록 조회 시 권한 필터링 (본인/부서/공개)
- [ ] 컬렉션 상세 조회 시 권한 검사
- [ ] 청킹 문서 추가/삭제 시 권한 검사
- [ ] 컬렉션 삭제/이름변경 시 소유자 또는 Admin 검사
- [ ] scope 변경 API (PERSONAL ↔ DEPARTMENT ↔ PUBLIC)
- [ ] 기존 컬렉션에 대한 마이그레이션 전략 (기본값 PUBLIC)

### 3.2 Out of Scope

- 부서 내 세부 역할(부서장/팀원) 구분 — 현재 UserDepartment에 role 필드 없음
- 문서 단위 (point 단위) 개별 권한 — 컬렉션 단위로만 제어
- 컬렉션 공유 초대/링크 기능
- 프론트엔드 UI 구현 (별도 Plan으로 분리)

---

## 4. Requirements

### 4.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `collection_permissions` 테이블: collection_name, owner_id, scope, department_id 저장 | High | Pending |
| FR-02 | 컬렉션 생성 시 자동으로 permission 레코드 생성 (owner=현재 사용자, scope=PERSONAL 기본) | High | Pending |
| FR-03 | `GET /api/v1/collections` — 현재 사용자 권한에 따라 필터링된 목록 반환 | High | Pending |
| FR-04 | `GET /api/v1/collections/{name}` — 권한 없으면 403 반환 | High | Pending |
| FR-05 | `POST /api/v1/collections/{name}/documents` (Ingest) — 권한 검사 후 문서 추가 | High | Pending |
| FR-06 | `DELETE /api/v1/collections/{name}/documents/{doc_id}` — 권한 검사 후 문서 삭제 | High | Pending |
| FR-07 | `PATCH /api/v1/collections/{name}/permission` — scope 변경 API | Medium | Pending |
| FR-08 | Admin은 모든 컬렉션에 대해 full access | High | Pending |
| FR-09 | DEPARTMENT scope 시 department_id 필수, 해당 부서원만 접근 | High | Pending |
| FR-10 | 기존 컬렉션은 마이그레이션 시 scope=PUBLIC으로 자동 설정 | Medium | Pending |

### 4.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| Performance | 권한 검사로 인한 API 응답 지연 < 50ms | 로그 기반 측정 |
| Consistency | 컬렉션 생성/삭제 시 permission 레코드 동기화 보장 | 트랜잭션 테스트 |
| Backward Compatibility | 기존 API 응답 형식 유지, 권한 필드만 추가 | 기존 테스트 통과 |

---

## 5. Data Model (초안)

### 5.1 collection_permissions 테이블

```sql
CREATE TABLE collection_permissions (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    owner_id    INT NOT NULL,                          -- FK → users.id
    scope       ENUM('PERSONAL','DEPARTMENT','PUBLIC') NOT NULL DEFAULT 'PERSONAL',
    department_id VARCHAR(36) NULL,                    -- FK → departments.id (scope=DEPARTMENT일 때)
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_collection_name (collection_name),
    INDEX ix_owner (owner_id),
    INDEX ix_department (department_id),
    INDEX ix_scope (scope),

    CONSTRAINT fk_perm_user FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT fk_perm_dept FOREIGN KEY (department_id) REFERENCES departments(id)
);
```

### 5.2 Domain Entity (예상)

```python
class CollectionScope(str, Enum):
    PERSONAL = "PERSONAL"
    DEPARTMENT = "DEPARTMENT"
    PUBLIC = "PUBLIC"

@dataclass
class CollectionPermission:
    collection_name: str
    owner_id: int
    scope: CollectionScope
    department_id: str | None = None
```

---

## 6. Architecture Considerations

### 6.1 Project Level

- **Level**: Enterprise (Thin DDD)
- 기존 레이어 구조 유지

### 6.2 Layer Mapping

| Layer | Component | 역할 |
|-------|-----------|------|
| **Domain** | `CollectionScope` enum, `CollectionPermission` entity | 권한 모델 정의 |
| **Domain** | `CollectionPermissionPolicy` | 접근 가능 여부 판단 규칙 |
| **Domain** | `CollectionPermissionRepositoryInterface` | 저장소 인터페이스 |
| **Application** | `CollectionPermissionService` | 권한 검사 오케스트레이션 |
| **Application** | 기존 `CollectionManagementUseCase` 수정 | 권한 서비스 주입 |
| **Infrastructure** | `CollectionPermissionRepository` | MySQL 구현 |
| **Infrastructure** | `CollectionPermissionModel` | SQLAlchemy ORM |
| **Interfaces** | collection_router 수정 | `get_current_user` 의존성 추가 |

### 6.3 Key Design Decisions

| 결정사항 | 선택 | 이유 |
|----------|------|------|
| 권한 저장소 | MySQL (별도 테이블) | Qdrant metadata에 넣으면 검색 성능에 영향, RDB로 분리 |
| 권한 검사 위치 | Application Layer (UseCase) | Domain Policy로 규칙 정의, UseCase에서 조합 |
| 기존 API 호환 | 응답 형식 유지 + scope 필드 추가 | Backward compatibility |
| 부서 scope | department_id 1개만 | 다중 부서 공유는 Out of Scope |

### 6.4 영향 받는 기존 파일

| File | 변경 유형 |
|------|----------|
| `src/application/collection/use_case.py` | 권한 서비스 의존성 추가, 각 메서드에 권한 검사 |
| `src/api/routes/collection_router.py` | `get_current_user` 의존성 추가 |
| `src/domain/collection/policy.py` | 권한 관련 Policy 메서드 추가 또는 별도 Policy 생성 |
| `src/application/ingest/ingest_use_case.py` | 문서 추가 시 권한 검사 연동 |

---

## 7. Success Criteria

### 7.1 Definition of Done

- [ ] `collection_permissions` 테이블 마이그레이션 파일 작성
- [ ] PERSONAL 컬렉션: 소유자만 접근 가능 확인
- [ ] DEPARTMENT 컬렉션: 같은 부서원만 접근 가능 확인
- [ ] PUBLIC 컬렉션: 모든 인증 사용자 접근 가능 확인
- [ ] Admin: 모든 컬렉션 접근 가능 확인
- [ ] 기존 컬렉션 PUBLIC 마이그레이션 완료
- [ ] 단위/통합 테스트 작성 및 통과
- [ ] 기존 테스트 깨지지 않음

### 7.2 Quality Criteria

- [ ] TDD 방식 (테스트 먼저 작성)
- [ ] DDD 레이어 규칙 준수
- [ ] 함수 40줄 초과 금지
- [ ] Zero lint error

---

## 8. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기존 API 호환성 깨짐 | High | Medium | 기존 응답 형식 유지, scope 필드는 optional 추가 |
| 권한 검사로 인한 성능 저하 | Medium | Low | permission 조회를 단일 쿼리로, 필요 시 캐싱 |
| Qdrant 컬렉션과 MySQL permission 동기화 불일치 | High | Medium | 컬렉션 생성/삭제를 UseCase 트랜잭션으로 묶기 |
| 부서 없는 사용자의 DEPARTMENT 컬렉션 접근 | Low | Medium | 부서 미소속 시 DEPARTMENT 컬렉션 생성 불가 정책 |
| 마이그레이션 시 기존 컬렉션 owner 불명 | Medium | High | 기존 컬렉션은 owner_id=NULL 허용 또는 admin 계정으로 할당 |

---

## 9. Convention Prerequisites

### 9.1 Existing Conventions

- [x] `CLAUDE.md` coding conventions 확인
- [x] DDD 레이어 규칙 확인
- [x] TDD 필수 규칙 확인
- [x] DB 세션 규칙 (`docs/rules/db-session.md`) 확인 필요

### 9.2 Conventions to Follow

| Category | Rule |
|----------|------|
| Layer | domain → infrastructure 참조 금지 |
| Error | `print()` 사용 금지, logger 사용 |
| Transaction | Repository 내부에서 commit/rollback 금지 |
| Session | UseCase 내에서 단일 세션 사용 |
| Test | 테스트 먼저 작성 (Red → Green → Refactor) |

---

## 10. Implementation Order (예상)

```
1. Domain: CollectionScope enum, CollectionPermission entity, Policy
2. Domain: CollectionPermissionRepositoryInterface
3. Infrastructure: CollectionPermissionModel (SQLAlchemy), Migration
4. Infrastructure: CollectionPermissionRepository 구현
5. Application: CollectionPermissionService (권한 검사 서비스)
6. Application: CollectionManagementUseCase 수정 (권한 서비스 주입)
7. Interfaces: collection_router 수정 (인증 의존성 추가)
8. Application: IngestDocumentUseCase 연동
9. Migration: 기존 컬렉션 → PUBLIC 초기 데이터
10. 통합 테스트
```

---

## 11. Next Steps

1. [ ] Design 문서 작성 (`collection-permission-management.design.md`)
2. [ ] TDD로 구현 (Domain → Infrastructure → Application → Interfaces)
3. [ ] Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial draft | AI Assistant |
