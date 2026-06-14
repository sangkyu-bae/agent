# Admin User Registration Design Document

> **Plan**: [admin-user-registration.plan.md](../../01-plan/features/admin-user-registration.plan.md)
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-31
> **Status**: Draft
> **선행 작업**: [agent-user-context](../../archive/2026-05/agent-user-context/agent-user-context.report.md)

---

## 1. Overview

### 1.1 Design Goals

관리자가 `admin/users`에서 모달로 직원 계정을 **즉시 활성(`status=approved`)** 상태로 직접 생성하고, 이메일·비밀번호·이름·직급·사번·입사일·role·부서를 **단일 트랜잭션**에서 저장한다. 전체 사용자 목록(부서명 포함)을 같은 화면 탭에서 조회한다.

### 1.2 Design Principles

- **Thin DDD**: User/Profile 생성은 Application UseCase, 부서 검증은 도메인 규칙 재사용.
- **단일 세션/트랜잭션**(DB-001 §10.2): `AdminCreateUserUseCase`는 `get_session`으로 주입된 **하나의 세션**을 모든 repo(User/Profile/Department)에 공유 → User+Profile+부서가 함께 commit/rollback.
- **무회귀**: 기존 자가가입(`/auth/register`)·승인 흐름은 변경하지 않고 admin 경로만 추가.
- **재사용**: 부서 검증/배정은 `AssignUserDepartmentUseCase`의 도메인 규칙(부서 존재 확인, primary 1개 제한)을 그대로 사용.
- **TDD**: 모든 신규 모듈 테스트 우선.

### 1.3 Plan Open Questions 확정 (사용자 결정 반영)

| # | 질문 | 확정 |
|---|------|------|
| Q1 | 부서 배정 통합 vs 2-call | ✅ **생성 API에 통합** (department_id 파라미터, 1 트랜잭션) |
| Q2 | 라우터 위치 | ✅ **`admin_user_router.py`** (prefix `/api/v1/admin/users`, 응집도) |
| Q3 | 목록 응답 부서 | ✅ **부서명(department_names) 포함** |
| Q4 | 모달 role=admin | ✅ **허용** (select 기본 user, 감사 로그 남김) |
| Q5 | 권한(grant) 입력 | ✅ **후속 처리** (이번 모달 제외) |
| Q6 | 비밀번호 정책 강화 | ✅ **추후 재설계** (현행 `PasswordPolicy` 8자+ 재사용) |

---

## 2. Architecture

### 2.1 Component Diagram

```
[AdminUsersPage]
  ├─ Tab(전체 사용자)  ── useQuery(getAllUsers) ─────▶ GET  /api/v1/admin/users
  ├─ Tab(승인 대기)    ── 기존 pending 유지
  ├─ [사용자 등록] btn ─▶ <UserRegisterModal>
  │     ├─ useQuery(departments) ───────────────────▶ GET  /api/v1/departments
  │     └─ useMutation(createUser) ─────────────────▶ POST /api/v1/admin/users
  │            onSuccess → invalidate(adminAllUsers) + close
  ▼
[admin_user_router]  (require_role("admin"))
  POST /admin/users  → AdminCreateUserUseCase.execute()
  GET  /admin/users  → ListUsersUseCase.execute()
        │
        ▼ (단일 session = Depends(get_session))
  AdminCreateUserUseCase
     ├─ UserRepository.find_by_email / save        (User, status=APPROVED)
     ├─ UserProfileRepository.upsert               (display_name/position/employee_no/joined_at)
     └─ DepartmentRepository(find_by_id/count_primary/assign_user)  [department_id 있을 때]
  ListUsersUseCase
     ├─ UserRepository.find_all(filters)           (NEW)
     └─ DepartmentRepository.find_departments_by_user  (부서명 집계)
```

### 2.2 Data Flow (생성)

```
관리자 모달 submit
 → POST /admin/users {email,password,display_name,position?,employee_no?,joined_at?,role,department_id?}
 → require_role("admin") 통과
 → AdminCreateUserUseCase.execute(cmd, request_id)  [session 1개]
     1. Email VO 검증 + PasswordPolicy.validate(password)
     2. find_by_email → 존재 시 ValueError("already registered")  → 409
     3. User(email, hash, role=cmd.role, status=APPROVED) save → user_id 확보
     4. UserProfile(user_id, display_name, position, employee_no, joined_at) upsert
     5. department_id 있으면:
          dept = department_repo.find_by_id → 없으면 ValueError → 422
          count_primary(user_id) 검증 후 assign_user(is_primary=True)
     6. return AdminCreateUserResult(...)
 → get_session 블록 정상 종료 시 일괄 commit (4·5 중 실패 시 전체 rollback)
 → 201 UserResponse 확장형
```

---

## 3. Domain Layer Design

신규 도메인 객체 **없음**. 기존 자산 재사용:
- `User`, `UserRole`, `UserStatus`(`PENDING/APPROVED/REJECTED`) — `src/domain/auth/entities.py`
- `Email` VO, `PasswordPolicy` — `src/domain/auth/`
- `UserProfile` (frozen) — `src/domain/user_profile/entity.py`
- `UserDepartment`, `Department` + `DepartmentRepositoryInterface` — `src/domain/department/`

### 3.1 Repository 인터페이스 확장 (`UserRepositoryInterface`)

```python
# src/domain/auth/interfaces.py — 메서드 추가
from dataclasses import dataclass

@dataclass
class UserListFilters:
    status: UserStatus | None = None
    query: str | None = None        # email/display_name 부분 일치
    limit: int = 20
    offset: int = 0

class UserRepositoryInterface(ABC):
    # ... 기존 save/find_by_email/find_by_id/find_by_status/update_status ...

    @abstractmethod
    async def find_all(
        self, filters: "UserListFilters", request_id: str
    ) -> tuple[list[User], int]:
        """필터/페이지네이션 적용 사용자 목록 + 전체 건수. (profile join은 repo에서)"""
```

> 목록 응답의 display_name·부서명은 UseCase에서 ProfileRepo/DepartmentRepo로 조합한다(아래 §4.2). `find_all`은 User 엔티티 + total만 책임진다. (N+1 우려는 §4.2 Note 참고)

---

## 4. Application Layer Design

### 4.1 `AdminCreateUserUseCase` (NEW)

```python
# src/application/auth/admin_create_user_use_case.py
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.application.department.schemas import AssignUserDepartmentRequest
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.interfaces import PasswordHasherInterface, UserRepositoryInterface
from src.domain.auth.policies import PasswordPolicy
from src.domain.auth.value_objects import Email
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.department.entity import UserDepartment
from src.domain.logging.interfaces import LoggerInterface
from src.domain.user_profile.entity import UserProfile
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface


@dataclass
class AdminCreateUserCommand:
    email: str
    password: str
    display_name: str
    position: str | None = None
    employee_no: str | None = None
    joined_at: date | None = None
    role: str = "user"               # "user" | "admin"
    department_id: str | None = None


@dataclass
class AdminCreateUserResult:
    user_id: int
    email: str
    role: str
    status: str
    display_name: str
    position: str | None
    employee_no: str | None
    joined_at: date | None
    department_id: str | None


class AdminCreateUserUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        user_profile_repo: UserProfileRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        password_hasher: PasswordHasherInterface,
        logger: LoggerInterface,
    ) -> None:
        self._user_repo = user_repo
        self._profile_repo = user_profile_repo
        self._dept_repo = department_repo
        self._hasher = password_hasher
        self._logger = logger

    async def execute(
        self, cmd: AdminCreateUserCommand, request_id: str, created_by: int
    ) -> AdminCreateUserResult:
        self._logger.info(
            "AdminCreateUser start",
            request_id=request_id, email=cmd.email,
            role=cmd.role, created_by=created_by,
        )
        # 1) 검증
        Email(cmd.email)
        PasswordPolicy.validate(cmd.password)
        if not cmd.display_name or not cmd.display_name.strip():
            raise ValueError("display_name is required")
        role = UserRole(cmd.role)  # 잘못된 값이면 ValueError → 422

        # 2) 중복
        if await self._user_repo.find_by_email(cmd.email):
            raise ValueError(f"Email already registered: {cmd.email}")

        # 3) User (즉시 활성)
        hashed = self._hasher.hash(cmd.password)
        user = User(
            email=cmd.email, password_hash=hashed,
            role=role, status=UserStatus.APPROVED,
        )
        saved = await self._user_repo.save(user)

        # 4) Profile
        now = datetime.now(timezone.utc)
        await self._profile_repo.upsert(
            UserProfile(
                user_id=saved.id,
                display_name=cmd.display_name.strip(),
                position=(cmd.position or None),
                employee_no=(cmd.employee_no or None),
                joined_at=cmd.joined_at,
                created_at=now, updated_at=now,
            ),
            request_id,
        )

        # 5) 부서 (선택) — AssignUserDepartmentUseCase 도메인 규칙 인라인 재사용
        if cmd.department_id:
            dept = await self._dept_repo.find_by_id(cmd.department_id, request_id)
            if dept is None:
                raise ValueError(f"부서를 찾을 수 없습니다: {cmd.department_id}")
            await self._dept_repo.assign_user(
                UserDepartment(
                    user_id=saved.id, department_id=cmd.department_id,
                    is_primary=True, created_at=now,
                ),
                request_id,
            )

        self._logger.info("AdminCreateUser done", request_id=request_id, user_id=saved.id)
        return AdminCreateUserResult(
            user_id=saved.id, email=saved.email,
            role=saved.role.value, status=saved.status.value,
            display_name=cmd.display_name.strip(),
            position=cmd.position, employee_no=cmd.employee_no,
            joined_at=cmd.joined_at, department_id=cmd.department_id,
        )
```

> **트랜잭션**: 위 3·4·5는 모두 동일 세션. `get_session`이 핸들러 정상 종료 시 commit, 예외 시 rollback → 부서 검증 실패(5)면 User/Profile도 함께 롤백되어 부분 생성이 남지 않는다.
> **참고**: `assign_user`의 `count_primary` 검증은 신규 사용자라 항상 0이므로 생략 가능(단순화). 도메인 일관성 우선 시 호출해도 무방.

### 4.2 `ListUsersUseCase` (NEW)

```python
# src/application/auth/list_users_use_case.py
@dataclass
class UserListItem:
    id: int
    email: str
    role: str
    status: str
    display_name: str | None
    position: str | None
    department_names: list[str]
    created_at: datetime | None

@dataclass
class UserListResult:
    items: list[UserListItem]
    total: int

class ListUsersUseCase:
    def __init__(self, user_repo, user_profile_repo, department_repo, logger): ...

    async def execute(self, filters: UserListFilters, request_id: str) -> UserListResult:
        users, total = await self._user_repo.find_all(filters, request_id)
        items = []
        for u in users:
            profile = await self._profile_repo.find_by_user_id(u.id, request_id)
            depts = await self._dept_repo.find_departments_by_user(u.id, request_id)
            items.append(UserListItem(
                id=u.id, email=u.email, role=u.role.value, status=u.status.value,
                display_name=profile.display_name if profile else None,
                position=profile.position if profile else None,
                department_names=[d.name for d in depts],
                created_at=u.created_at,
            ))
        return UserListResult(items=items, total=total)
```

> **N+1 Note**: 페이지당 limit(기본 20)만큼 profile/dept 조회. 운영 규모(사내 수백 명)에서 페이지 단위 20건이면 허용 범위. 향후 대량 시 `find_all`에 join 집계로 최적화(설계상 UseCase 시그니처 불변). MVP는 단순 루프 채택.

---

## 5. Infrastructure Layer Design

### 5.1 `UserRepository.find_all` 구현 (`src/infrastructure/auth/user_repository.py`)

```python
async def find_all(self, filters: UserListFilters, request_id: str) -> tuple[list[User], int]:
    stmt = select(UserModel)
    count_stmt = select(func.count()).select_from(UserModel)
    if filters.status is not None:
        cond = UserModel.status == filters.status.value
        stmt = stmt.where(cond); count_stmt = count_stmt.where(cond)
    if filters.query:
        like = f"%{filters.query}%"
        # display_name은 user_profiles 조인 또는 email만 우선 (MVP: email LIKE)
        cond = UserModel.email.like(like)
        stmt = stmt.where(cond); count_stmt = count_stmt.where(cond)
    stmt = stmt.order_by(UserModel.created_at.desc()).limit(filters.limit).offset(filters.offset)
    rows = (await self._session.execute(stmt)).scalars().all()
    total = (await self._session.execute(count_stmt)).scalar_one()
    return [self._to_entity(r) for r in rows], total
```

- **마이그레이션 없음**: 신규 테이블/컬럼 없이 기존 `users`/`user_profiles`/부서 테이블 재사용.
- 검색은 MVP에서 email LIKE. display_name 검색은 후속(프로필 조인) — Out of Scope 명시.

### 5.2 DI 배선 (`src/api/main.py`)

`create_auth_context_factories` 패턴을 따라 신규 팩토리 추가. **동일 session 공유**:

```python
def create_admin_user_mgmt_factories():
    app_logger = get_app_logger()
    password_hasher = BcryptPasswordHasher()

    def _user(s): return UserRepository(session=s, logger=app_logger)
    def _profile(s): return UserProfileRepository(session=s, logger=app_logger)
    def _dept(s): return DepartmentRepository(session=s, logger=app_logger)

    def admin_create_user_factory(session: AsyncSession = Depends(get_session)):
        return AdminCreateUserUseCase(
            user_repo=_user(session), user_profile_repo=_profile(session),
            department_repo=_dept(session), password_hasher=password_hasher,
            logger=app_logger,
        )

    def list_users_factory(session: AsyncSession = Depends(get_session)):
        return ListUsersUseCase(
            user_repo=_user(session), user_profile_repo=_profile(session),
            department_repo=_dept(session), logger=app_logger,
        )
    return admin_create_user_factory, list_users_factory

# create_app() 내 등록 (agent-user-context override 블록 인근):
_create_f, _list_f = create_admin_user_mgmt_factories()
app.dependency_overrides[get_admin_create_user_use_case] = _create_f
app.dependency_overrides[get_list_users_use_case] = _list_f
# admin_user_router는 이미 include_router 됨 (line ~2606) — 신규 엔드포인트 자동 노출
```

---

## 6. Interface Layer Design

### 6.1 Schemas (`src/interfaces/schemas/auth/`)

```python
# request.py 추가
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field

class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1, max_length=100)
    position: Optional[str] = Field(None, max_length=50)
    employee_no: Optional[str] = Field(None, max_length=50)
    joined_at: Optional[date] = None
    role: Literal["user", "admin"] = "user"
    department_id: Optional[str] = None

# response.py 추가
class AdminUserListItemResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    display_name: Optional[str] = None
    position: Optional[str] = None
    department_names: list[str] = []
    created_at: Optional[str] = None  # ISO 8601

class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItemResponse]
    total: int

class AdminCreateUserResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    display_name: str
    position: Optional[str] = None
    employee_no: Optional[str] = None
    joined_at: Optional[str] = None
    department_id: Optional[str] = None
```

### 6.2 Router (`src/api/routes/admin_user_router.py` — 기존 파일에 추가)

```python
# DI placeholder 추가
def get_admin_create_user_use_case() -> AdminCreateUserUseCase:
    raise NotImplementedError
def get_list_users_use_case() -> ListUsersUseCase:
    raise NotImplementedError

@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminCreateUserResponse)
async def create_user(
    body: AdminCreateUserRequest,
    admin: User = Depends(require_role("admin")),
    use_case: AdminCreateUserUseCase = Depends(get_admin_create_user_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        r = await use_case.execute(
            AdminCreateUserCommand(**body.model_dump()),
            request_id=request_id, created_by=admin.id,
        )
    except ValueError as e:
        msg = str(e)
        if "already registered" in msg:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return AdminCreateUserResponse(
        id=r.user_id, email=r.email, role=r.role, status=r.status,
        display_name=r.display_name, position=r.position,
        employee_no=r.employee_no,
        joined_at=r.joined_at.isoformat() if r.joined_at else None,
        department_id=r.department_id,
    )

@router.get("", response_model=AdminUserListResponse)
async def list_users(
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_role("admin")),
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
):
    request_id = str(uuid.uuid4())
    filters = UserListFilters(
        status=UserStatus(status_filter) if status_filter else None,
        query=q, limit=limit, offset=offset,
    )
    result = await use_case.execute(filters, request_id)
    return AdminUserListResponse(
        items=[AdminUserListItemResponse(
            id=i.id, email=i.email, role=i.role, status=i.status,
            display_name=i.display_name, position=i.position,
            department_names=i.department_names,
            created_at=i.created_at.isoformat() if i.created_at else None,
        ) for i in result.items],
        total=result.total,
    )
```

> ⚠️ prefix가 `/api/v1/admin/users`이므로 `@router.post("")` = `POST /api/v1/admin/users`. 기존 `@router.post("/{user_id}/permissions")`와 경로 충돌 없음.

---

## 7. Frontend Design

### 7.1 API 상수 (`constants/api.ts`)

```ts
ADMIN_USERS_LIST: '/api/v1/admin/users',     // GET (?status=&q=&limit=&offset=)
ADMIN_USERS_CREATE: '/api/v1/admin/users',   // POST
// 기존 ADMIN_DEPARTMENTS('/api/v1/departments') 재사용
```

### 7.2 Types (`types/auth.ts`)

```ts
export interface AdminCreateUserRequest {
  email: string; password: string; display_name: string;
  position?: string; employee_no?: string; joined_at?: string; // YYYY-MM-DD
  role: UserRole; department_id?: string;
}
export interface AdminUserListItem {
  id: number; email: string; role: UserRole; status: UserStatus;
  display_name: string | null; position: string | null;
  department_names: string[]; created_at: string | null;
}
export interface AdminUserListResponse { items: AdminUserListItem[]; total: number; }
```

### 7.3 Service (`services/adminService.ts`)

```ts
createUser: (body: AdminCreateUserRequest) =>
  authApiClient.post(API_ENDPOINTS.ADMIN_USERS_CREATE, body).then(r => r.data),
getAllUsers: (params: { status?: string; q?: string; limit?: number; offset?: number }) =>
  authApiClient.get<AdminUserListResponse>(API_ENDPOINTS.ADMIN_USERS_LIST, { params }).then(r => r.data),
```

### 7.4 컴포넌트

- `components/admin/UserRegisterModal.tsx`
  - 필드: email / password / display_name / position / employee_no / joined_at(date) / role(select: user·admin) / department(select)
  - 부서 옵션: `useQuery(['departments'], () => GET /departments)`
  - 검증: email 형식, password ≥ 8, display_name 필수 (제출 전 클라이언트 검증)
  - submit: `useMutation(createUser)` → `onSuccess`: `invalidateQueries(adminAllUsers)` + close + 성공 토스트
  - `onError`: 409 → "이미 등록된 이메일", 422 → 메시지 인라인 표시
- `pages/AdminUsersPage/index.tsx` (수정)
  - 상단 우측 [사용자 등록] 버튼 → 모달 open 상태 관리
  - 탭 2개: `전체 사용자`(getAllUsers 표) / `승인 대기`(기존 pending 유지)
  - 전체 표 컬럼: 이메일·이름·직급·부서(department_names join)·role·상태·가입일

### 7.5 queryKeys 확장 (`lib/queryKeys.ts`)

```ts
admin: {
  pendingUsers: () => ['admin','users','pending'],
  allUsers: (params?) => ['admin','users','all', params],   // NEW
  departments: () => ['admin','departments'],               // 재사용/추가
}
```

---

## 8. Sequence Diagram (정상 생성)

```
Admin ─submit modal─▶ POST /admin/users
  FastAPI ─require_role(admin)─▶ AdminCreateUserUseCase.execute(cmd, created_by)
    ├ Email/PasswordPolicy/role 검증
    ├ find_by_email → None
    ├ user_repo.save(User status=APPROVED)         ┐
    ├ profile_repo.upsert(UserProfile)             ├ same session
    └ (dept) dept_repo.find_by_id + assign_user    ┘
  ◀ 201 AdminCreateUserResponse
  get_session 종료 → COMMIT (모두 성공 시)
FE onSuccess → invalidate(allUsers) → 목록 갱신 → 모달 close
```

---

## 9. Test Strategy

### 9.1 Backend (pytest, TDD)

| 대상 | 케이스 |
|------|--------|
| `AdminCreateUserUseCase` | ① 성공(부서 없음) ② 성공(부서 포함) ③ 이메일 중복→ValueError ④ 약한 비밀번호→ValueError ⑤ display_name 공백→ValueError ⑥ 잘못된 role→ValueError ⑦ 없는 department_id→ValueError(롤백) |
| `ListUsersUseCase` | ① 필터 없음 ② status 필터 ③ 페이지네이션 total ④ 부서명/프로필 조합 ⑤ 프로필 없는 사용자(None 처리) |
| `UserRepository.find_all` | status/like/limit/offset + total 정확성 (실DB or fake) |
| Router | POST 201 / 409 / 422, GET 200 / 403(비admin) / 쿼리 파라미터 매핑 |

### 9.2 Frontend (Vitest + RTL + MSW)

| 대상 | 케이스 |
|------|--------|
| `UserRegisterModal` | 필수검증, 부서 옵션 로드, submit 성공 close, 409 에러 표시 |
| `AdminUsersPage` | 탭 전환, 전체 목록 렌더, 등록 버튼→모달 open, 등록 후 목록 invalidate |
| `adminService` | createUser/getAllUsers 요청 형태(MSW) |

---

## 10. Impact / Risks

- 🟢 **마이그레이션 0건** — 기존 테이블만 사용.
- 🟢 **무회귀** — `/auth/register`·승인·권한·부서 기존 엔드포인트 불변. admin_user_router에 엔드포인트만 추가(이미 include됨).
- 🟡 `UserRepositoryInterface.find_all` 추가 → 인터페이스 변경이므로 **기존 구현체 1곳 + 테스트 fake 업데이트** 필요.
- 🟡 role=admin 부여 허용 → 감사 로그(`created_by`, role) logger 기록으로 추적성 확보.
- 🟡 N+1(목록) → MVP 페이지 20건 허용, 후속 join 최적화 여지(시그니처 불변).
- 🔵 후속(Out): 사용자 수정/삭제, display_name 검색, 권한 입력 UI, 다중 부서.

---

## 11. Implementation Order (Do 단계)

1. (BE) `UserListFilters` + `UserRepositoryInterface.find_all` 시그니처 + fake/impl 테스트 → 구현
2. (BE) `AdminCreateUserUseCase` 테스트 → 구현
3. (BE) `ListUsersUseCase` 테스트 → 구현
4. (BE) 스키마(request/response) + admin_user_router 엔드포인트 + 라우터 테스트
5. (BE) main.py DI 팩토리/override 배선 → Zero Script QA(로그)로 200/201/403/409 확인
6. (FE) constants/types/service 동기화 (`/api-contract-sync`)
7. (FE) `UserRegisterModal` (MSW/RTL 테스트 우선) → 구현
8. (FE) `AdminUsersPage` 탭/버튼 통합 + 목록 표
9. `/pdca analyze admin-user-registration` (Gap)
