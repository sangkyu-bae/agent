# knowledge-base-scoping Design Document

> **Plan**: `docs/01-plan/features/knowledge-base-scoping.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-07
> **Status**: Draft

---

## 1. 설계 요약

물리 컬렉션(관리자 전용)과 논리 지식베이스(사용자, payload 필터 단위)를 분리한다.
기존 코드는 **additive-only**로 유지하며, 아래 4개 블록을 신규 추가한다.

1. `knowledge_base` MySQL 테이블 + domain/application/infrastructure 신규 모듈
2. `/api/v1/knowledge-bases` CRUD 라우터
3. `/api/v1/admin/collections` 관리자 전용 컬렉션 생성 (기존 UseCase 재사용)
4. KB 지정 업로드 — 기존 `UnifiedUploadUseCase`에 optional `extra_metadata` 필드 추가(additive)로 `kb_id`/`kb_name`을 Qdrant payload + ES 문서에 주입

### 코드 확인으로 확정된 사실 (2026-07-07)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| Qdrant payload 주입 | `_store_to_qdrant`가 `chunk.metadata` **전체**를 payload로 복사 (`unified_upload/use_case.py:242`) | chunk.metadata에 넣으면 자동 전파 ✅ |
| ES 문서 주입 | `_store_to_es`는 **고정 필드 화이트리스트**로 body 구성 (`use_case.py:262-275`) | chunk.metadata만으론 전파 안 됨 → `_store_to_es`에 additive 수정 필요 ⚠️ |
| ES 매핑 | `es_index_mappings.py`에 명시 매핑, `dynamic` 미지정(기본 true) | `kb_id`/`kb_name` keyword 필드를 매핑에 추가 (기존 인덱스는 운영 노트 참조) |
| 임베딩 모델 해석 | activity log의 CREATE 엔트리에서 해석 (`use_case.py:196`) | 관리자 신규 엔드포인트도 기존 UseCase 재사용 → CREATE 로그 남음 → 업로드 정상 동작 ✅ |
| RBAC | `require_role('admin')` 존재 (`interfaces/dependencies/auth.py:70`) | 그대로 사용 |
| users.id 타입 | BIGINT (V002) | FK 컬럼 타입 일치 |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | payload 필터 키는 `kb_id`(UUID v4, VARCHAR(36), KB 테이블 PK와 동일 값). `kb_name`은 표시용으로 동봉 | 이름 변경 시 재태깅 불필요. PK=필터키로 조인/추적 단순화 |
| D2 | `UnifiedUploadRequest`에 `extra_metadata: dict[str, str]` optional 필드 추가 (frozen dataclass → `field(default_factory=dict)`). 기존 고정 키(document_id 등)가 **우선**하며 extra는 보조 | 기존 호출부 무영향(additive). wrapper 복제 대비 유지보수 지점 1곳 |
| D3 | ES: `DOCUMENTS_INDEX_MAPPINGS`에 `kb_id`/`kb_name` keyword 추가 + `_store_to_es` body에 extra_metadata 병합(고정 키 우선) | ES는 화이트리스트 방식이라 명시 병합 필수 (§1 확인 사실) |
| D4 | KB 삭제는 **soft delete**(`status: active/deleted`) | 고아 payload 정리(후속 kb-vector-cleanup)를 위해 kb_id 추적 보존. (owner, name) DB 유니크는 두지 않고 active 중복만 UseCase가 차단 — soft-delete 재생성 충돌 방지 (V037 D4 선례) |
| D5 | KB 이름은 **유니코드 허용**(한글 등), 1~100자, 제어문자 금지. 소유자 내 active 중복 금지 | 물리 컬렉션명과 달리 Qdrant 제약 없음 — 사용자 친화 |
| D6 | 물리 컬렉션 배정은 `CollectionAssignerInterface`(domain)로 추상화. 이번 구현체는 `UserSelectedCollectionAssigner`(사용자 선택 + 존재·읽기 권한 검증) | Plan 결정 — 추후 `AdminMappedCollectionAssigner`로 교체 가능 |
| D7 | KB 권한 판정은 `KnowledgeBasePolicy`를 domain/knowledge_base에 신규 작성. `CollectionScope` enum은 재사용(import), `collection_permissions` 테이블·서비스와는 **불연동** | 이중 권한 체계 혼란 방지 (Plan §4-3). 판정 규칙은 `CollectionPermissionPolicy`와 동형(ADMIN 전권, PERSONAL=소유자, DEPARTMENT=소속, PUBLIC=읽기전체/쓰기소유자) |
| D8 | 업로드 쓰기 권한: PERSONAL·DEPARTMENT는 기존 정책과 동형, **PUBLIC KB는 소유자+ADMIN만 쓰기** | `CollectionPermissionPolicy.can_write`의 PUBLIC=False 선례와 정합 |
| D9 | 신규 업로드 엔드포인트는 `get_current_user` 인증 필수, user_id는 토큰에서 추출 (기존 upload-all의 Query user_id 방식 답습 금지) | 신규 경로는 "우리 규칙"대로 — 보안 개선 |
| D10 | Qdrant `kb_id` payload index 생성은 **후속(kb-rag-filter)으로 이연** | 이번 범위에 검색이 없어 효과 검증 불가. 필터 검색 도입 시 함께 |
| D11 | KB CRUD의 activity log(collection_activity_log) 연동은 이연, StructuredLogger 로깅만 수행. 업로드는 위임받은 `UnifiedUploadUseCase`가 기존대로 ADD_DOCUMENT 로깅 | ActionType enum 확장은 기존 domain 스키마 수정이라 additive-only 원칙과 충돌 |
| D12 | KB 상세의 문서 수/포인트 수 집계는 이연 (레코드 필드만 반환) | Qdrant count-by-filter는 검색 연동 사이클에서 |

---

## 3. 파일 구조 (신규/수정)

```
idt/
├── db/migration/
│   └── V040__create_knowledge_base.sql                      [신규]
├── src/
│   ├── domain/knowledge_base/
│   │   ├── __init__.py                                      [신규]
│   │   ├── entities.py          # KnowledgeBase             [신규]
│   │   ├── interfaces.py        # Repository/Assigner IF    [신규]
│   │   └── policy.py            # KnowledgeBasePolicy       [신규]
│   ├── application/knowledge_base/
│   │   ├── __init__.py                                      [신규]
│   │   ├── use_case.py          # KnowledgeBaseUseCase      [신규]
│   │   ├── collection_assigner.py # UserSelectedCollectionAssigner [신규]
│   │   └── upload_use_case.py   # KnowledgeBaseUploadUseCase [신규]
│   ├── infrastructure/
│   │   ├── persistence/models/knowledge_base.py             [신규]
│   │   └── knowledge_base/repository.py                     [신규]
│   ├── api/routes/
│   │   ├── knowledge_base_router.py                         [신규]
│   │   └── admin_collection_router.py                       [신규]
│   ├── api/main.py              # 라우터 등록 + DI 배선     [수정: 추가만]
│   ├── application/unified_upload/
│   │   ├── schemas.py           # extra_metadata 필드       [수정: additive]
│   │   └── use_case.py          # 주입 2곳                  [수정: additive]
│   └── infrastructure/elasticsearch/
│       └── es_index_mappings.py # kb_id/kb_name keyword     [수정: additive]
└── tests/
    ├── domain/knowledge_base/test_policy.py                 [신규]
    ├── application/knowledge_base/test_use_case.py          [신규]
    ├── application/knowledge_base/test_collection_assigner.py [신규]
    ├── application/knowledge_base/test_upload_use_case.py   [신규]
    ├── application/unified_upload/test_extra_metadata.py    [신규]
    └── api/
        ├── test_knowledge_base_router.py                    [신규]
        └── test_admin_collection_router.py                  [신규]
```

---

## 4. DB 스키마 — `V040__create_knowledge_base.sql`

```sql
-- knowledge-base-scoping Design §4:
-- 논리 지식베이스 레지스트리. 벡터 격리는 Qdrant/ES payload(kb_id) — 물리 컬렉션과 분리.
-- soft delete(status): 삭제 후 고아 payload 정리(후속 kb-vector-cleanup)를 위해 kb_id 추적 보존.
-- (owner_id, name) 유니크 인덱스는 두지 않는다 — soft-delete 재생성과 충돌 (V037 D4 선례).
--   active 이름 중복 차단은 UseCase가 보장.
-- ⚠️ FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지, DB 기본 상속 (V037 선례).
CREATE TABLE knowledge_base (
    id              VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'kb_id — Qdrant/ES payload 필터 키',
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500) NULL,
    owner_id        BIGINT       NOT NULL,
    scope           ENUM('PERSONAL','DEPARTMENT','PUBLIC') NOT NULL DEFAULT 'PERSONAL',
    department_id   VARCHAR(36)  NULL,
    collection_name VARCHAR(100) NOT NULL COMMENT '배정된 물리 Qdrant 컬렉션',
    status          VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active | deleted',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_kb_owner FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT fk_kb_department FOREIGN KEY (department_id)
        REFERENCES departments(id) ON DELETE SET NULL,
    INDEX idx_kb_owner_status (owner_id, status),
    INDEX idx_kb_scope_status (scope, status),
    INDEX idx_kb_department (department_id)
) ENGINE=InnoDB;
```

SQLAlchemy 모델(`infrastructure/persistence/models/knowledge_base.py`)은 `CollectionPermissionModel` 패턴을 따른다 (Base 상속, Mapped 타입, server_default=func.now()).

---

## 5. Domain Layer

### 5.1 `entities.py`

```python
@dataclass
class KnowledgeBase:
    name: str
    owner_id: int
    scope: CollectionScope          # domain/collection/permission_schemas 재사용 (D7)
    collection_name: str
    description: str | None = None
    department_id: str | None = None
    id: str | None = None           # kb_id (UUID v4)
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### 5.2 `policy.py` — `KnowledgeBasePolicy`

| 메서드 | 규칙 |
|--------|------|
| `validate_name(name)` | strip 후 1~100자, 제어문자(`\x00-\x1f`) 금지. 유니코드 허용 (D5) |
| `can_read(user, kb, user_dept_ids)` | ADMIN=True / PUBLIC=True / PERSONAL=소유자 / DEPARTMENT=소속 부서 |
| `can_write(user, kb, user_dept_ids)` | ADMIN=True / PERSONAL=소유자 / DEPARTMENT=소속 / **PUBLIC=소유자만** (D8) |
| `can_delete(user, kb)` | ADMIN 또는 소유자 |
| `validate_scope(scope, department_id, user_dept_ids)` | DEPARTMENT면 department_id 필수 + 본인 소속 검증 (`CollectionPermissionPolicy.validate_scope_change`와 동형) |

### 5.3 `interfaces.py`

```python
class KnowledgeBaseRepositoryInterface(ABC):
    async def save(self, kb: KnowledgeBase, request_id: str) -> KnowledgeBase: ...
    async def find_by_id(self, kb_id: str, request_id: str) -> KnowledgeBase | None: ...   # active만
    async def find_accessible(self, owner_id: int, dept_ids: list[str], request_id: str) -> list[KnowledgeBase]: ...
    async def exists_active_name(self, owner_id: int, name: str, request_id: str) -> bool: ...
    async def soft_delete(self, kb_id: str, request_id: str) -> None: ...

class CollectionAssignerInterface(ABC):
    """KB가 사용할 물리 컬렉션 결정 전략 (D6). 현재: 사용자 선택형 / 추후: 관리자 매핑형."""
    async def assign(self, user: User, requested_collection: str | None, request_id: str) -> str: ...
```

`find_accessible` SQL: `status='active' AND (owner_id=:uid OR scope='PUBLIC' OR (scope='DEPARTMENT' AND department_id IN :dept_ids))`. ADMIN은 UseCase에서 전체 조회로 분기.

---

## 6. Application Layer

### 6.1 `KnowledgeBaseUseCase` (`use_case.py`)

`CollectionManagementUseCase` 패턴 준수. 의존성: `kb_repo`, `policy`, `assigner`, `dept_repo`(소속 조회), `logger`.

| 메서드 | 흐름 |
|--------|------|
| `create(req, user, request_id)` | validate_name → validate_scope → active 이름 중복 검사(소유자 내) → `assigner.assign(user, req.collection_name)` → save(kb_id=uuid4) → 반환 |
| `list(user, request_id)` | ADMIN이면 전체 active, 아니면 dept_ids 조회 후 `find_accessible` |
| `get(kb_id, user, request_id)` | find_by_id → 없으면 ValueError("not found") → `can_read` 아니면 PermissionError |
| `delete(kb_id, user, request_id)` | find_by_id → `can_delete` → `soft_delete`. **벡터/ES 정리는 하지 않음** — 응답 메시지에 명시 |

### 6.2 `UserSelectedCollectionAssigner` (`collection_assigner.py`)

```
assign(user, requested_collection, request_id):
    if not requested_collection: raise ValueError("collection_name is required")
    if not await collection_repo.collection_exists(requested_collection): raise ValueError(...)
    await perm_service.check_read_access(requested_collection, user, request_id)  # 기존 서비스 재사용
    return requested_collection
```

의존성: `CollectionRepositoryInterface`(Qdrant), `CollectionPermissionService`(기존). 물리 컬렉션의 접근 검사는 **KB 생성 시 이 1회만** 수행 (Plan §4-3).

### 6.3 `KnowledgeBaseUploadUseCase` (`upload_use_case.py`)

```
execute(kb_id, user, file_bytes, filename, chunk opts, request_id):
    kb = kb_repo.find_by_id(kb_id)                 # 없으면 ValueError
    dept_ids = dept_repo로 소속 조회
    policy.can_write(user, kb, dept_ids) 아니면 PermissionError
    unified_req = UnifiedUploadRequest(
        file_bytes, filename,
        user_id=str(user.id),
        collection_name=kb.collection_name,        # KB 레코드에서 자동 결정 — 요청에 컬렉션 없음
        extra_metadata={"kb_id": kb.id, "kb_name": kb.name},
    )
    return await unified_upload.execute(unified_req, request_id), kb
```

### 6.4 `UnifiedUploadUseCase` additive 수정 (2곳)

```python
# schemas.py — 기존 필드 뒤에 추가 (frozen dataclass)
extra_metadata: dict[str, str] = field(default_factory=dict)

# use_case.py execute() — 기존 고정 키 주입 블록(98-101행) 뒤에 추가.
# setdefault: 고정 키(document_id/user_id/collection_name)가 항상 우선 (D2)
for key, value in request.extra_metadata.items():
    for chunk in chunks:
        chunk.metadata.setdefault(key, value)

# use_case.py _store_to_es() — body 구성 뒤에 추가 (D3)
for key, value in request.extra_metadata.items():
    body.setdefault(key, value)
```

기본값이 빈 dict이므로 기존 호출부·기존 테스트에 동작 변화 없음.

### 6.5 ES 매핑 additive 수정

```python
# es_index_mappings.py DOCUMENTS_INDEX_MAPPINGS["properties"]에 추가
"kb_id": {"type": "keyword"},
"kb_name": {"type": "keyword"},
```

> **운영 노트**: 매핑 정의는 인덱스 신규 생성 시에만 적용된다. 기존 인덱스는
> `PUT /{index}/_mapping {"properties": {"kb_id": {"type":"keyword"}, "kb_name": {"type":"keyword"}}}`
> 1회 실행 필요. 미실행 시에도 dynamic mapping(기본 true)으로 색인은 되지만 `text+keyword` 이중 필드가
> 되므로 매핑 선반영을 권장. 이 절차를 Do 단계 체크리스트에 포함한다.

---

## 7. API 명세

### 7.1 `/api/v1/knowledge-bases` (신규 라우터, tags=["KnowledgeBases"])

모든 엔드포인트 `Depends(get_current_user)`. DI 플레이스홀더 + main.py override 패턴(기존 collection_router와 동일).

| Method | Path | Request | Response | 에러 |
|--------|------|---------|----------|------|
| POST | `/` | `{name, description?, scope="PERSONAL", department_id?, collection_name}` | 201 `{kb_id, name, scope, collection_name, message}` | 409 이름 중복 / 422 검증 실패·컬렉션 없음 / 403 컬렉션 접근 불가 |
| GET | `/` | - | `{knowledge_bases: [KbInfo], total}` | - |
| GET | `/{kb_id}` | - | `KbDetail` (레코드 필드 전체, D12) | 404 / 403 |
| DELETE | `/{kb_id}` | - | `{kb_id, message: "... vectors remain until cleanup"}` | 404 / 403 |
| POST | `/{kb_id}/documents` | multipart `file` + Query `child_chunk_size`(500), `child_chunk_overlap`(50) | 기존 `UnifiedUploadResponse` 필드 + `{kb_id, kb_name, collection_name}` | 404 / 403 / 422 |

`KbInfo`: `{kb_id, name, description, scope, department_id, collection_name, owner_id, created_at}`

예외 매핑 규약(기존 collection_router와 동일): `PermissionError`→403, `ValueError("not found")`→404, `ValueError("already exists")`→409, 기타 `ValueError`→422.

### 7.2 `/api/v1/admin/collections` (신규 라우터, tags=["Admin"])

| Method | Path | 가드 | 처리 |
|--------|------|------|------|
| POST | `/` | `Depends(require_role('admin'))` | body는 기존 `CreateCollectionBody`와 동일. 내부에서 기존 `CollectionManagementUseCase.create_collection` 호출 (로직 복제 금지). scope 기본값 `PUBLIC` (관리자 컬렉션은 공용 전제) |

기존 `POST /api/v1/collections`는 무수정 유지.

---

## 8. DI 배선 (main.py — 추가만)

`create_collection_management_factories` 패턴(main.py:2413~)을 따라 신규 factory 함수 1개 추가:

```
def create_knowledge_base_factories():
    qdrant_client = AsyncQdrantClient(...)          # 기존 패턴과 동일
    collection_repo = QdrantCollectionRepository(qdrant_client)

    def kb_use_case_factory(session = Depends(get_session)):
        kb_repo = KnowledgeBaseRepository(session, app_logger)
        perm_service = CollectionPermissionService(...)   # 기존 조립식 재사용
        assigner = UserSelectedCollectionAssigner(collection_repo, perm_service)
        dept_repo = DepartmentRepository(session, app_logger)
        return KnowledgeBaseUseCase(kb_repo, KnowledgeBasePolicy(), assigner, dept_repo, app_logger)

    def kb_upload_factory(session = Depends(get_session)):
        kb_repo = KnowledgeBaseRepository(session, app_logger)
        unified = <기존 unified upload 조립식과 동일 구성, 동일 session>
        return KnowledgeBaseUploadUseCase(kb_repo, KnowledgeBasePolicy(), dept_repo, unified, app_logger)
```

**세션 규칙**: 한 요청의 모든 repository는 같은 `Depends(get_session)` 세션 사용 (`docs/rules/db-session.md`). `kb_upload_factory`에서 `UnifiedUploadUseCase` 내부의 `document_metadata_repo` 등도 동일 세션으로 조립한다.

admin 라우터는 기존 `get_collection_use_case` factory를 그대로 override 대상으로 공유한다.

---

## 9. 테스트 설계 (TDD — Red 먼저)

| 파일 | 케이스 |
|------|--------|
| `test_policy.py` | 이름: 빈 문자열/101자/제어문자 거부, 한글 허용. can_read/write/delete 스코프×역할 매트릭스(PUBLIC 쓰기=소유자만 포함). validate_scope: DEPARTMENT에 dept 누락/비소속 거부 |
| `test_use_case.py` | create: 정상(kb_id UUID 발급, assigner 호출 확인) / active 이름 중복 409 경로(ValueError already exists) / soft-deleted 동명 재생성 허용. list: PERSONAL 타인 KB 제외, PUBLIC 포함, ADMIN 전체. get: 404/403. delete: 소유자 OK, 타인 403, soft_delete 호출 검증 |
| `test_collection_assigner.py` | 컬렉션 미존재 ValueError / 읽기 권한 없음 PermissionError 전파 / 정상 반환 |
| `test_upload_use_case.py` | KB 없음 ValueError / 쓰기 권한 없음 PermissionError / UnifiedUploadRequest에 collection_name=kb.collection_name, extra_metadata={kb_id, kb_name} 전달 검증 (mock unified) |
| `test_extra_metadata.py` | extra_metadata 지정 시: Qdrant `add_documents`에 전달된 metadata에 kb_id 포함 + ES `bulk_index` body에 kb_id 포함 (mock client/repo). **미지정 시 기존 동작 불변**(회귀 가드) + 고정 키 충돌 시 고정 키 우선 |
| `test_knowledge_base_router.py` | CRUD 상태코드 매핑(201/409/404/403/422), 업로드 200 + 응답에 kb_id |
| `test_admin_collection_router.py` | 일반 사용자 403, ADMIN 201 (mock use case로 create_collection 호출 검증) |

기존 테스트 스위트: 신규 회귀 0건 (사전 실패분은 [[preexisting-api-test-failures-auth-di]] 참조 — 오인 금지).

---

## 10. 구현 순서 (Do Phase)

1. `V040__create_knowledge_base.sql` + SQLAlchemy 모델
2. domain: entities → policy(테스트 먼저) → interfaces
3. infrastructure: `KnowledgeBaseRepository`(테스트 먼저)
4. application: assigner → `KnowledgeBaseUseCase` → `UnifiedUploadUseCase` additive 수정(`test_extra_metadata.py` 먼저) → `KnowledgeBaseUploadUseCase`
5. ES 매핑 additive 수정
6. api: `knowledge_base_router.py` → `admin_collection_router.py`(테스트 먼저)
7. main.py DI 배선 + 라우터 등록
8. `/verify-architecture`, `/verify-tdd`, `/verify-logging` 실행
9. 기존 인덱스 `PUT _mapping` 운영 절차 문서화 (Do 체크리스트)

---

## 11. 리스크 재확인 (Plan §5 대비 갱신)

| Plan 리스크 | Design 확인 결과 |
|-------------|------------------|
| ES 매핑에 kb_id 부재 | **실제 확인됨** — 화이트리스트 body 구성이라 매핑+코드 2곳 additive 수정으로 해소 (D3) |
| 이중 권한 체계 혼란 | KB 경로는 KnowledgeBasePolicy 단독 판정, 물리 컬렉션 검사는 생성 시 assigner 1회로 격리 (D6, D7) |
| 고아 payload | soft delete로 kb_id 추적 보존 → 후속 cleanup에서 delete-by-filter 가능 (D4) |
| 필터 검색 성능 | payload index는 검색 도입 사이클로 이연 (D10) |
