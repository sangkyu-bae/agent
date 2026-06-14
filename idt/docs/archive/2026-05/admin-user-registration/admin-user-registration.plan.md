# Admin User Registration Planning Document

> **Summary**: 관리자가 프론트 `admin/users` 페이지에서 "사용자 등록" 버튼 → 모달을 통해 직원을 직접 등록하고(이름·직급·사번·입사일·권한·부서 포함, 즉시 활성), 전체 사용자 목록을 한 화면에서 관리할 수 있게 한다. `agent-user-context`가 백엔드에 만든 `UserProfile`/권한/부서 데이터를 화면에서 입력·관리하는 운영 UI를 완성한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-30
> **Status**: Draft
> **Related (선행 작업)**: [agent-user-context](../../archive/2026-05/agent-user-context/agent-user-context.report.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `agent-user-context` 작업으로 백엔드에는 `user_profiles`(이름·직급·사번·입사일)·권한·부서 데이터 구조가 생겼지만, 이를 **입력·관리하는 화면이 없다**. 현재 가입은 사용자가 직접 신청(`status=pending`) 후 관리자가 승인하는 흐름뿐이라, 관리자가 직원 계정을 **직접 생성**하거나 프로필 메타데이터를 채울 방법이 없다. 또한 `admin/users` 페이지는 "승인 대기" 목록만 보여줘 전체 사용자를 볼 수 없다. |
| **Solution** | ① 관리자 전용 **직접 사용자 생성 API**(`POST /admin/users`) 신설 — 즉시 활성(`status=approved`) + UserProfile 전체 필드 + role + 부서 배정을 한 트랜잭션에서 처리. ② **전체 사용자 목록 API**(`GET /admin/users`) 신설. ③ 프론트 `AdminUsersPage`에 "전체 사용자 / 승인 대기" 탭 + "사용자 등록" 버튼 → **등록 모달**(`UserRegisterModal`) 추가. |
| **Function/UX Effect** | 관리자가 버튼 한 번으로 모달을 열어 이메일·비밀번호·이름·직급·사번·입사일·권한·부서를 입력하면 즉시 로그인 가능한 계정이 생성된다. 등록 직후 전체 목록 탭에서 바로 확인된다. 사용자가 가입 신청을 기다릴 필요 없이 관리자 주도로 온보딩이 가능해진다. |
| **Core Value** | `agent-user-context`가 마련한 "사내 신원·권한 데이터 기반"을 **실제로 채울 수 있는 운영 도구** 완성 → "나의 연차는?" 류 질의·권한 강제가 의미를 가지려면 정확한 프로필이 입력돼 있어야 하므로, 이 화면이 그 데이터 품질의 출발점이 된다. |

---

## 1. Overview

### 1.1 Purpose

`agent-user-context`(2026-05-28 완료)는 백엔드에 다음을 만들었다:

| 자산 | 위치 | 현재 입력 경로 |
|------|------|----------------|
| `UserProfile`(display_name, position, employee_no, joined_at) | `user_profiles` 테이블 | 회원가입 시 **display_name만** 채워짐. 나머지는 항상 NULL |
| 권한(grant/revoke) | `user_permissions` + `POST/DELETE /admin/users/{id}/permissions` | 화면 없음 (API만 존재) |
| 부서(N:M, is_primary) | `departments` + `POST /users/{id}/departments` | AdminDepartmentsPage 일부 존재 |
| 사용자 계정 | `users`(role, status) | **자가 가입(pending) → 관리자 승인**만 가능 |

본 기능은 위 데이터를 **관리자가 직접 입력·생성**하는 UI/API를 추가한다. 핵심은 `admin/users` 페이지의 "사용자 등록" 버튼 → 모달 회원등록이다.

### 1.2 Background

- **현재 `AdminUsersPage`**(`idt_front/src/pages/AdminUsersPage/index.tsx`)는 사실상 **"사용자 승인 관리"** 화면이다. `GET /admin/users/pending` 결과(승인 대기자)만 표시하고 승인/거절 버튼만 있다.
- **자가 가입 흐름**: `POST /auth/register`(email, password, display_name) → `User(status=pending)` + `UserProfile(display_name)` 생성 → 관리자가 `/admin/users/{id}/approve`로 활성화.
- **관리자 직접 생성 경로 부재**: register는 ① `status=pending` 고정, ② `position/employee_no/joined_at/role/부서`를 받지 않음 → 관리자가 직원을 한 번에 완전한 형태로 만들 수 없음.
- **전체 사용자 목록 API 부재**: 현재 `/admin/users/pending`(승인 대기)만 존재. 전체 사용자(승인됨 포함) 조회 API 없음.
- **이미 잘 되어 있는 점**:
  - `require_role("admin")` 의존성으로 관리자 인가 패턴 확립.
  - 부서 배정 API(`POST /users/{id}/departments`)·목록(`GET /departments`) 존재 → 모달 부서 드롭다운 즉시 연동 가능.
  - 권한 부여 API(`POST /admin/users/{id}/permissions`) 존재 → (선택) 모달/상세에서 연동 가능.
  - 프론트 `adminService`·`API_ENDPOINTS`·TanStack Query 패턴 확립.

### 1.3 핵심 제약 / 발견 (사전 조사)

- ⚠️ **`UserStatus`에 `ACTIVE`가 없다.** enum은 `PENDING / APPROVED / REJECTED`(`src/domain/auth/entities.py`). 따라서 "즉시 활성"은 **`status=approved`**로 매핑한다.
- `UserRole`: `user / admin` 2종.
- `UserProfile`은 `frozen` ValueObject — 변경은 UseCase 경유. 부서는 프로필이 아닌 **별도 N:M 테이블**.
- 부서 배정은 `dept_id`(string) 기반 별도 엔드포인트(`POST /api/v1/users/{user_id}/departments`).

### 1.4 Related Documents / Code

**Backend**
- `src/api/routes/auth_router.py` — `POST /register`
- `src/api/routes/admin_router.py` — `GET /admin/users/pending`, approve/reject
- `src/api/routes/admin_user_router.py` — 권한 부여/회수
- `src/api/routes/department_router.py` — 부서 CRUD + 사용자 배정
- `src/application/auth/register_use_case.py` — `RegisterUseCase`(UserProfile 동시 생성)
- `src/domain/auth/entities.py` — `User`, `UserRole`, `UserStatus`
- `src/domain/user_profile/entity.py` — `UserProfile`
- `src/domain/user_profile/interfaces.py` — `UserProfileRepositoryInterface`
- `src/domain/auth/interfaces.py` — `UserRepositoryInterface`, `PasswordHasherInterface`
- 규칙: `docs/rules/db-session.md`, `docs/rules/logging.md`, `docs/rules/testing.md`

**Frontend**
- `idt_front/src/pages/AdminUsersPage/index.tsx` — 승인 관리(확장 대상)
- `idt_front/src/pages/AdminDepartmentsPage/index.tsx` — 부서 관리(부서 목록 참고)
- `idt_front/src/services/adminService.ts` — 확장 대상
- `idt_front/src/constants/api.ts` — 엔드포인트 상수
- `idt_front/src/types/auth.ts` — `User`, `PendingUser`, `UserRole`, `UserStatus`

---

## 2. Scope

### 2.1 In Scope

**Backend (idt/)**
- [ ] `POST /api/v1/admin/users` — 관리자 직접 사용자 생성 (즉시 `status=approved`)
  - 입력: email, password, display_name, position?, employee_no?, joined_at?, role, department_id?
  - User + UserProfile(전체 필드) 생성 + (department_id 있으면) 부서 배정 — **단일 세션/트랜잭션**
- [ ] `GET /api/v1/admin/users` — 전체 사용자 목록 (프로필·부서·상태·role 포함, 검색/상태 필터/페이지네이션)
- [ ] `AdminCreateUserUseCase` 신설 (TDD)
- [ ] `ListUsersUseCase` 신설 (TDD)
- [ ] `UserRepositoryInterface`/구현에 목록 조회 메서드 추가 (profile join)
- [ ] 인터페이스 스키마: `AdminCreateUserRequest`, `AdminUserListItemResponse`
- [ ] main.py DI 배선
- [ ] 모든 신규 모듈 TDD (테스트 먼저)

**Frontend (idt_front/)**
- [ ] `AdminUsersPage` 재구성: "전체 사용자 / 승인 대기" 탭 + "사용자 등록" 버튼
- [ ] `UserRegisterModal` 컴포넌트 — 회원등록 폼(이메일·비밀번호·이름·직급·사번·입사일·role·부서)
- [ ] 부서 드롭다운: `GET /departments` 연동
- [ ] `adminService`에 `createUser`, `getAllUsers` 추가
- [ ] `types/auth.ts`에 `AdminUserListItem`, `AdminCreateUserRequest`, `AdminUserDetail` 추가
- [ ] `constants/api.ts`에 `ADMIN_USERS_CREATE`, `ADMIN_USERS_LIST` 추가
- [ ] TanStack Query 훅 + 등록 성공 시 목록 invalidate
- [ ] 폼 검증(이메일 형식, 비밀번호 8자 이상, 이름 필수) + 에러 토스트 (409 중복 이메일 등)
- [ ] MSW + Vitest/RTL 테스트

### 2.2 Out of Scope

- 기존 사용자 **수정/삭제**(프로필 편집, 비활성화) — 후속 feature (`admin-user-edit`)
- 권한(permission) 부여 UI — 본 범위는 등록까지. 권한은 기존 API로 별도. (Open Q5 참고)
- 비밀번호 재설정/초대 메일/SSO
- 부서 N:M 다중 배정 (모달은 **주 부서 1개**만, is_primary=true)
- 일괄 업로드(CSV 등)

---

## 3. Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | 관리자는 `admin/users`에서 "사용자 등록" 버튼으로 모달을 연다 | High |
| FR-02 | 모달에서 email, password, 이름(display_name)을 필수 입력한다 | High |
| FR-03 | 모달에서 직급(position), 사번(employee_no), 입사일(joined_at)을 선택 입력한다 | High |
| FR-04 | 모달에서 role(user/admin)을 선택한다 (기본 user) | High |
| FR-05 | 모달에서 부서를 드롭다운으로 선택한다 (선택, 단일) | Medium |
| FR-06 | 등록 시 계정은 즉시 `approved` 상태로 생성되어 바로 로그인 가능하다 | High |
| FR-07 | 이메일 중복 시 409로 모달에 에러 메시지를 표시한다 | High |
| FR-08 | 비밀번호는 8자 이상 정책을 클라이언트+서버 모두 검증한다 | High |
| FR-09 | 등록 성공 시 모달이 닫히고 전체 목록이 갱신되어 새 사용자가 보인다 | High |
| FR-10 | 전체 사용자 목록 탭에서 이메일·이름·직급·부서·role·상태·가입일을 표로 본다 | High |
| FR-11 | 목록은 상태 필터 + 이메일/이름 검색 + 페이지네이션을 지원한다 | Medium |
| FR-12 | 모든 신규 API는 `require_role("admin")`로 보호한다 | High |
| FR-13 | 백엔드 신규 UseCase/Repo는 단일 세션 내에서 User+Profile(+부서)를 생성한다 | High |

---

## 4. High-Level Design (개략)

### 4.1 Backend

**신규 엔드포인트 (admin_user_router.py 또는 admin_router.py 확장)**

```
POST /api/v1/admin/users         (require_role admin) → 201
  body: {
    email, password, display_name,
    position?, employee_no?, joined_at?,
    role: "user"|"admin" = "user",
    department_id?: string
  }
  → User(status=approved, role) + UserProfile(full) [+ 부서 배정]
  → 201 { id, email, role, status, display_name, position, employee_no, joined_at, departments[] }
  에러: 409(이메일 중복), 422(검증 실패)

GET /api/v1/admin/users          (require_role admin) → 200
  query: ?status=&q=&limit=20&offset=0
  → { items: AdminUserListItem[], total }
```

**신규 UseCase**
- `AdminCreateUserUseCase.execute(cmd, request_id)`
  - `Email` VO 검증 + `PasswordPolicy.validate`
  - 이메일 중복 체크 → `User(status=APPROVED, role=cmd.role)` save
  - `UserProfile(display_name, position, employee_no, joined_at)` upsert
  - `department_id` 있으면 `AssignUserDepartmentUseCase` 로직 호출(또는 repo 직접) — **동일 세션**
  - ⚠️ `docs/rules/db-session.md` 준수: 모든 repo가 **하나의 세션**을 공유해야 함 (CLAUDE.md 금지 규칙)
- `ListUsersUseCase.execute(filters, request_id)` → User+Profile(+부서) 조인 결과

**Repository**
- `UserRepositoryInterface.find_all(filters, request_id)` 추가 (profile left join, 부서 집계)

### 4.2 Frontend

```
AdminUsersPage
├── 헤더 + [사용자 등록] 버튼  ──▶ UserRegisterModal (open)
├── 탭: [전체 사용자] [승인 대기]
│    ├─ 전체 사용자: useQuery(getAllUsers) → 표(이메일/이름/직급/부서/role/상태/가입일)
│    └─ 승인 대기: 기존 pending 목록 + 승인/거절 (그대로 유지)
└── UserRegisterModal
     ├─ 폼: email / password / display_name / position / employee_no / joined_at / role(select) / department(select)
     ├─ 부서 옵션: useQuery(GET /departments)
     └─ submit → useMutation(createUser) → onSuccess: invalidate(allUsers) + close
```

**신규/수정 파일**
- 신규 `idt_front/src/components/admin/UserRegisterModal.tsx`
- 수정 `idt_front/src/pages/AdminUsersPage/index.tsx` (탭 + 버튼)
- 수정 `idt_front/src/services/adminService.ts` (`createUser`, `getAllUsers`)
- 수정 `idt_front/src/types/auth.ts`
- 수정 `idt_front/src/constants/api.ts`
- 신규 훅(선택) `idt_front/src/hooks/useAdminUsers.ts`

### 4.3 API Contract Sync (필수)

| Backend | Frontend |
|---------|----------|
| `interfaces/schemas/auth/request.py` `AdminCreateUserRequest` | `types/auth.ts` `AdminCreateUserRequest` |
| `interfaces/schemas/auth/response.py` `AdminUserListItemResponse` | `types/auth.ts` `AdminUserListItem` |
| `POST/GET /api/v1/admin/users` | `services/adminService.ts` + `constants/api.ts` |

---

## 5. Open Questions (설계 단계에서 확정)

> 사용자 확정 완료: ✅ 즉시 활성(=approved) / ✅ 전체 프로필 입력 / ✅ 관리자 직접 비밀번호 입력 / ✅ 전체 목록 탭 신설

설계(`/pdca design`) 단계에서 확정할 잔여 항목:

| # | 질문 | 잠정안 |
|---|------|--------|
| Q1 | 부서 배정을 **생성 API에 통합**(department_id 파라미터, 1 트랜잭션) vs 프론트 2-call(생성 후 assign 별도 호출)? | **통합** 권장 — 원자성 보장 + 단일 세션 규칙 부합. assign 로직 재사용. |
| Q2 | 신규 엔드포인트를 `admin_user_router.py`(현 prefix `/admin/users`)에 둘지, `admin_router.py`에 둘지? | `admin_user_router.py` — prefix 일치, 응집도. |
| Q3 | 목록 응답에 **권한(permission) 라벨**·**부서명**을 포함할지? | 부서명 포함, 권한은 제외(상세/별도). 성능 위해 부서는 집계 1쿼리. |
| Q4 | role=admin 을 모달에서 부여 허용? (보안) | 허용하되 select 기본 user + 확인. 감사로그는 logger로. |
| Q5 | 권한(grant) 입력을 이번 모달에 넣을지? | **Out** — 등록 후 별도 권한 화면(후속). 모달 비대화 방지. |
| Q6 | 비밀번호 정책(특수문자 등) 강화 여부? | 현행 `PasswordPolicy`(8자+) 재사용, 강화는 별도. |

---

## 6. Implementation Order (TDD, design 이후)

1. **Backend 도메인/UseCase 테스트 먼저**
   - `AdminCreateUserUseCase` 단위 테스트 (성공/이메일중복/검증실패/부서배정)
   - `ListUsersUseCase` 단위 테스트 (필터/페이지네이션)
2. UseCase 구현 → 통과
3. Repository `find_all` + 스키마 + 라우터 (router 테스트)
4. main.py DI 배선 → Zero Script QA(로그 기반)로 엔드포인트 확인
5. **Frontend**: 타입/서비스/상수 동기화 (api-contract)
6. `UserRegisterModal` (MSW + RTL 테스트 먼저)
7. `AdminUsersPage` 탭/버튼 통합
8. Gap 분석(`/pdca analyze`)

## 7. Risks / Notes

- 🔴 **단일 세션 규칙**(CLAUDE.md): User·Profile·Department 3 repo가 서로 다른 세션을 쓰면 안 됨 → UseCase 생성자에서 동일 세션 공유 배선 필수. design에서 세션 전략 명시.
- 🟡 `status=approved` 매핑: 프론트 `UserStatus`에 'active' 없음 → 'approved' 일관 사용.
- 🟡 부서 N:M지만 모달은 주 부서 1개만(is_primary). 다중은 후속.
- 🟡 기존 `register`(자가가입) 흐름은 **변경하지 않음** — 신규 admin 경로만 추가(무회귀).
- 🟢 부서/권한 API는 이미 존재 → 재사용으로 신규 표면 최소화.

---

## 8. Acceptance Criteria

- [ ] 관리자가 모달로 등록한 계정이 즉시 로그인 가능(`status=approved`)하다.
- [ ] 입력한 직급·사번·입사일·부서가 DB(`user_profiles`/부서 배정)에 반영된다.
- [ ] 전체 사용자 목록 탭에서 새 사용자가 즉시 보인다.
- [ ] 이메일 중복 시 409 + 모달 인라인 에러.
- [ ] 신규 API는 비관리자가 호출 시 403.
- [ ] 백엔드/프론트 신규 코드 모두 테스트 동반(무회귀).
