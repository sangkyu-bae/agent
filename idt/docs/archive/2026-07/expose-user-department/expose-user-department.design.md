# expose-user-department Design Document

> **Plan**: `docs/01-plan/features/expose-user-department.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **소스 기준**: master 실코드 (auth_router.py:122 me · schemas/auth/response.py · department_repository.find_departments_by_user:136 · UserDepartment VO · SettingsPage)

---

## 1. Plan 이월 결정 3건 — 사용자 지정 확정

| # | 결정 | 확정안 (사용자 지정) | 설계 반영 |
|---|------|---------------------|----------|
| ① | /me 조립 방식 | **get_current_user 유지 + 부서 별도 조회** | `get_auth_context`(권한·프로필까지 조립, DB 3회)로 교체하지 않고, `find_departments_by_user`(단일 쿼리) + 부서명 조회만 경량 추가. me의 기존 계약·비용 최소 증가 |
| ② | 승격 대상 부서 | **다부서 선택 드롭다운** | 사용자가 여러 부서 소속이면 승격/작성 대상 부서를 드롭다운으로 선택. me 응답에 부서 목록(id+name) 제공 |
| ③ | 응답 타입 | **신규 MeResponse** | UserResponse는 무변경(다른 소비자 보호), `/me`만 `MeResponse`(부서 필드 포함)로 전환 |

## 2. Architecture

```
[백엔드]
 GET /api/v1/auth/me → MeResponse (신규)
   me(current_user, dept_uc=Depends(get_user_departments_use_case)):
     depts = await dept_uc.execute(current_user.id, request_id)   # 별도 경량 조회(결정 ①)
     return MeResponse(id, email, role, status, display_name,
                       departments=[{id, name, is_primary}])       # 결정 ②·③

 GetUserDepartmentsUseCase (신규, application/department)
   find_departments_by_user(user_id) → UserDepartment[]  (repo 기존, :136)
   + department 이름 해석 (list_departments 재사용 or repo find_by_id)
   → [DepartmentBrief{id, name, is_primary}]

[프론트]
 useMe → MeResponse(departments) → authStore/컴포넌트에서 부서 접근
 SettingsPage:
   MemoryItem: 부서 소속 시 "부서로 승격" — 부서 1개면 즉시, 다부서면 드롭다운(결정 ②)
   OrgSection: (admin) 작성 폼 + 부서 선택 드롭다운
```

## 3. Detailed Design

### 3-1. 백엔드

**신규 응답** (`schemas/auth/response.py`):
```python
class DepartmentBrief(BaseModel):
    id: str
    name: str
    is_primary: bool

class MeResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    display_name: str | None = None
    departments: list[DepartmentBrief] = []   # additive, 미소속이면 빈 리스트
```

**신규 UseCase** (`application/department/get_user_departments_use_case.py`):
```python
class GetUserDepartmentsUseCase:
    def __init__(self, department_repo, logger): ...
    async def execute(self, user_id: int, request_id: str) -> list[DepartmentBrief]:
        links = await self._repo.find_departments_by_user(user_id, request_id)  # :136
        if not links: return []
        # 부서명 해석: 전체 부서 1회 조회 후 map (부서 수 수십 수준 — N+1 회피)
        all_depts = await self._repo.find_all(request_id)  # 기존 list용 메서드 재사용
        name_by_id = {d.id: d.name for d in all_depts}
        return [DepartmentBrief(id=l.department_id,
                                name=name_by_id.get(l.department_id, l.department_id),
                                is_primary=l.is_primary) for l in links]
```

**라우터** (`auth_router.py:122` 교체 — 응답모델만 변경, get_current_user 유지):
```python
@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user),
             dept_uc = Depends(get_user_departments_use_case)):
    request_id = str(uuid.uuid4())
    departments = await dept_uc.execute(current_user.id, request_id)
    return MeResponse(id=..., email=..., role=..., status=..., departments=departments)
```
DI: `main.py`에 `get_user_departments_use_case` override (department_repo per-request 세션).

### 3-2. 프론트

- **타입** (`types/auth.ts`): `DepartmentBrief{id,name,is_primary}` + `User`에 `departments?: DepartmentBrief[]` additive (me 응답 확장 — 기존 필드 무변경, FR-02)
- **service** (`authService.me`): 반환 타입 `User`(departments 포함)로 확장, 엔드포인트 동일
- **훅**: `useMe` 그대로 — 반환 데이터에 departments 포함. 편의 `useMyDepartments()`(primary 우선 정렬) 선택
- **SettingsPage**:
  - `MemoryItem`에 "부서로 승격" 버튼 (departments 있을 때만, FR-05) — 부서 1개면 그 부서로 `usePromoteMemory`, 다부서면 인라인 부서 select(결정 ②)
  - `OrgSection`에 (admin && departments) 작성 폼 — 부서 select + 타입/내용 + `useCreateOrgMemory`
  - 409(중복)/422(상한) `errorDetail` 표면화 (FR-06)

## 4. Test Plan (TDD)

| 파일 | 케이스 |
|------|--------|
| `tests/application/department/test_get_user_departments_use_case.py` (신규) | 소속 부서 → DepartmentBrief(name 해석·is_primary) · 미소속 [] · 부서명 미존재 시 id 폴백 |
| `tests/api/test_auth_router.py` (확장) | GET /me가 departments 포함 · 미소속 빈 리스트 · 기존 필드 무변경 |
| `useMemories`/SettingsPage 테스트 | 승격 버튼(departments 있을 때만·다부서 select·성공 갱신) · admin 작성 폼(부서 select·작성) · 미소속 UI 없음 · 409/422 표면화 |
| authStore/useMe 회귀 | departments 없던 응답도 정상(optional) |

## 5. Implementation Order

1. MeResponse + DepartmentBrief + GetUserDepartmentsUseCase — UC 테스트 먼저
2. /me 라우터 교체 + main.py DI — auth 라우터 테스트
3. 프론트 타입·service 확장 (기존 me 소비자 회귀 확인)
4. SettingsPage 승격 버튼 + admin 작성 폼 (MSW me 핸들러 departments 추가) — 테스트 먼저
5. verify → analyze

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 해소 |
|-------------|------|
| /me 조립 비용 | 결정 ① — get_auth_context(권한 조립) 대신 부서 단일 조회 + 부서명 map 1회 |
| 다부서 승격 모호 | 결정 ② 드롭다운 — me가 부서 목록 제공 |
| 부서 노출 민감도 | id/name은 기존 화면에도 노출 — 신규 민감정보 아님 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-20 | 사용자 지정 3결정 확정(별도 조회·다부서 드롭다운·신규 MeResponse), find_departments_by_user 재사용 | 배상규 |
