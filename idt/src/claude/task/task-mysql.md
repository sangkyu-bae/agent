# MYSQL-001: MySQL 공통 Repository 모듈

> Task ID: MYSQL-001
> 의존성: LOG-001
> 상태: Done

---

## 목적

프로젝트 전반에서 공통으로 사용할 최소 MySQL(SQLAlchemy 비동기) 기반 레이어.
단건 조회, 전체 조회, 조건 필터, 저장, 삭제, 카운트, 존재 여부를 제공하는
**제네릭 Base Repository**를 정의한다.

이후 도메인별 Repository는 이 클래스를 상속하여 추가 메서드만 작성하면 된다.

---

## 아키텍처

```
MySQLRepositoryInterface[T]        ← domain (ABC, Generic)
          │ 구현
          ▼
MySQLBaseRepository[T]             ← infrastructure (Generic SQLAlchemy 구현)
          │ 상속
          ▼
SomeDomainRepository(MySQLBaseRepository[SomeModel])  ← 도메인별 확장
```

기존 세션 관리:
- `src/infrastructure/persistence/database.py` — `get_engine()`, `get_session_factory()`, `get_session()` 재사용

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/mysql/schemas.py` | `MySQLQueryCondition`, `MySQLPaginationParams`, `MySQLPageResult[T]` |
| `src/domain/mysql/interfaces.py` | `MySQLRepositoryInterface[T]` (Generic ABC) |

### Infrastructure Layer
| 파일 | 설명 |
|------|------|
| `src/infrastructure/persistence/mysql_base_repository.py` | `MySQLBaseRepository[T]` — 공통 CRUD 구현 |

---

## 인터페이스

### MySQLQueryCondition (도메인 Value Object)

```python
@dataclass(frozen=True)
class MySQLQueryCondition:
    field: str          # 모델 컬럼명
    operator: str       # eq | ne | gt | lt | gte | lte | like | in
    value: Any          # 비교 값 (in 연산자는 list)
```

지원 연산자: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `like`, `in`

### MySQLRepositoryInterface 메서드

| 메서드 | 반환 | 설명 |
|--------|------|------|
| `save(entity, request_id)` | `T` | INSERT / UPDATE flush |
| `find_by_id(entity_id, request_id)` | `Optional[T]` | PK 단건 조회 |
| `find_all(request_id, pagination?)` | `list[T]` | 전체 조회 (페이지네이션) |
| `find_by_conditions(conditions, request_id, pagination?)` | `list[T]` | AND 조건 필터 조회 |
| `delete(entity_id, request_id)` | `bool` | PK 단건 삭제 |
| `count(request_id)` | `int` | 전체 건수 |
| `exists(entity_id, request_id)` | `bool` | PK 존재 여부 |

---

## 사용 예시 (도메인별 Repository 확장)

```python
# application/repositories/document_repository.py  (추상)
class DocumentRepository(MySQLRepositoryInterface[DocumentModel]):
    @abstractmethod
    async def find_by_user(self, user_id: str, request_id: str) -> list[DocumentModel]: ...

# infrastructure/persistence/repositories/document_repository.py  (구현)
class SQLAlchemyDocumentRepository(
    MySQLBaseRepository[DocumentModel],
    DocumentRepository,
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface):
        super().__init__(session, DocumentModel, logger)

    async def find_by_user(self, user_id: str, request_id: str) -> list[DocumentModel]:
        cond = MySQLQueryCondition(field="user_id", operator="eq", value=user_id)
        return await self.find_by_conditions([cond], request_id)
```

---

## 세션 주입 패턴

```python
# FastAPI 의존성 주입 예시
from src.infrastructure.persistence.database import get_session

@router.post("/documents")
async def create_document(
    data: CreateDocumentRequest,
    session: AsyncSession = Depends(get_session),
):
    logger = get_app_logger()
    repo = SQLAlchemyDocumentRepository(session=session, logger=logger)
    async with session.begin():
        saved = await repo.save(DocumentModel(...), request_id)
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock |
|------------|------|------|
| `tests/domain/mysql/test_schemas.py` | Value Object 생성/검증 (12 케이스) | ❌ |
| `tests/infrastructure/persistence/test_mysql_base_repository.py` | CRUD + 에러 처리 (25 케이스) | ✅ Mock AsyncSession |

총 37 테스트 케이스.

---

## LOG-001 로깅 체크리스트

- [x] `LoggerInterface` 주입 (MySQLBaseRepository)
- [x] 주요 처리 시작/완료 INFO 로그 (`request_id`, 모델명, count/found/deleted 등)
- [x] 예외 발생 시 ERROR 로그 + `exception=e` (스택 트레이스)
- [x] `request_id` 컨텍스트 전파

---

## 완료 기준

- [x] `MySQLQueryCondition`, `MySQLPaginationParams`, `MySQLPageResult` Value Object
- [x] `MySQLRepositoryInterface[T]` Generic ABC
- [x] `MySQLBaseRepository[T]` 공통 CRUD 구현
  - [x] `save` / `find_by_id` / `find_all` / `find_by_conditions`
  - [x] `delete` / `count` / `exists`
  - [x] 8가지 연산자 지원 (eq, ne, gt, lt, gte, lte, like, in)
- [x] 전체 37 테스트 통과 (Red → Green 순서 준수)
- [x] LOG-001 로깅 적용

---

## 확장 포인트

| 확장 | 설명 |
|------|------|
| `bulk_save(entities, request_id)` | 대량 저장 (bulk insert) |
| `find_by_conditions_count(conditions, request_id)` | 조건 기반 카운트 |
| `update_by_conditions(conditions, values, request_id)` | 조건 기반 UPDATE |
| `upsert(entity, request_id)` | INSERT OR UPDATE (MySQL ON DUPLICATE KEY) |
