# Admin User Registration — Gap Analysis

> **Design**: [admin-user-registration.design.md](../02-design/features/admin-user-registration.design.md)
> **Plan**: [admin-user-registration.plan.md](../01-plan/features/admin-user-registration.plan.md)
> **Analyzer**: bkit:gap-detector
> **Date**: 2026-05-31
> **Phase**: Check

---

## Match Rate: **97%** ✅ — 완료 권고 (≥ 90%)

| 항목 | 점수 |
|------|:----:|
| Design Match (API/Domain/App/IF/FE) | 99% |
| FR Coverage (13개: 12 완전 + 1 부분) | 96% |
| §10 Risk 처리 | 100% |
| CLAUDE.md 준수 (경미 1건) | 100% |
| Test 충족 (설계 §9) | 100% |

---

## 1. FR Coverage (plan §3)

12/13 완전 충족. **FR-11만 부분(🟡)**: 백엔드 `find_all`은 status/query/limit/offset를 완전 지원하나, 프론트 `useAllUsers()`가 파라미터 없이 호출돼 **목록 필터/검색/페이지네이션 UI 컨트롤이 없다**. 설계 §7도 필터 UI를 명시하지 않아 설계≠구현 불일치는 아니며(설계≈구현), 운영 확대 시 후속 과제.

나머지 FR-01~10, 12, 13은 모달·탭·즉시 approved·409 인라인·단일 세션 등 모두 구현 확인.

## 2. 레이어별 Gap

- **API**: `POST/GET /api/v1/admin/users` 설계 §6.2 코드 블록과 1:1. 구현이 GET의 잘못된 `status`에 대해 `UserStatus()` try/except로 **422를 명시 처리**(설계엔 없던 안전장치, 개선).
- **Domain/Repo**: `UserListFilters` + `find_all` abstractmethod + 구현(§5.1) 모두 일치.
- **Application**: `AdminCreateUserUseCase`는 §4.1과 1:1. 부서 없으면 ValueError(롤백) 포함. `created_by` 감사 로그 기록.
- **ListUsersUseCase (개선/설계 초과)**: 설계 §4.2는 사용자별 dept 조회 루프(N+1)였으나, 구현은 `dept_repo.list_all()`로 **id→name 맵을 1회 구성**해 부서명 N+1을 선제 제거. profile은 MVP 범위 내 루프 유지.
- **Schemas / Frontend**: request/response, 상수, 타입, service, queryKeys, 훅, 모달, 페이지 모두 설계 §6·§7과 일치. BE↔FE 계약(`joined_at` string↔date, `department_id/names`) 동기화 충족(CLAUDE.md §4-1).

## 3. 설계 §10 Risk 처리 (100%)

- 🟡 **`find_all` 인터페이스 변경**: 정식 구현체는 `UserRepository` **단 1곳**이며 `find_all` 구현 완료. 테스트는 `AsyncMock` 사용으로 추상메서드 추가 영향 없음. repo 테스트에 find_all 3 cases 추가됨.
- 🔴→✅ **단일 세션/트랜잭션**: `create_admin_user_mgmt_factories`가 `Depends(get_session)` 하나의 세션을 user/profile/dept 3 repo에 공유. UseCase 내 commit/rollback 없음 → 부서 검증 실패 시 User/Profile 함께 롤백. **핵심 리스크 정확히 처리.**
- 🟡 role=admin 감사 로그, 🟢 마이그레이션 0건·무회귀(register/승인/권한 미변경) 모두 확인.

## 4. CLAUDE.md 규칙 위반: **0건**

- domain→infrastructure 참조 없음, 라우터 비즈니스 로직 없음, **Repository 내 commit/rollback 없음**(flush만), 단일 UseCase 단일 세션, logger 사용(print 없음) 전부 준수.
- 🟢 경미 1건: `AdminCreateUserUseCase.execute`가 로깅 포함 ~60줄로 권고 40줄 초과. 선형 5단계·중첩 없음이라 리팩토링 강제 불필요(설계 코드 블록과 동일 구조).

## 5. 테스트 (설계 §9 충족, 일부 초과)

UseCase 8 + ListUsers 4 + repo find_all 3 + router 8 + 모달 11 = **34 cases**. 설계 §9 명세 케이스 전부 포함 + admin role 허용·백드롭/X/Esc 닫기 등 추가.

> ⚠️ 백엔드 교차 실행 시 산발 ERROR/FAILED는 Windows TestClient+asyncio 이벤트 루프 teardown 오염(환경 이슈)으로, 파일 단위 격리 실행 시 전부 통과. 코드 결함 아님.

## 6. 감점 요인 (-3%)

1. FR-11 필터/검색/페이지네이션 **UI** 미구현 (-2%) — 백엔드 완비, 프론트 컨트롤만 부재.
2. `execute` 함수 길이 권고 초과 (-1%, 경미).

## 7. 권고 조치

**Match Rate ≥ 90% → 완료 권고**: `/pdca report admin-user-registration` 진행.

후속(backlog, 차단 아님):
- 🟡 목록 필터/검색/페이지네이션 UI 추가 (`useAllUsers(params)` 연결만 하면 BE 즉시 활용)
- 🟢 profile N+1 최적화(대량 시), display_name 검색(설계 Out of Scope)

설계 문서 미세 갱신(코드가 진실): §4.2 N+1 Note를 "부서명은 맵 1회 해소, profile만 루프"로, §6.2에 GET status→422 처리 반영.

---

## 검토 파일

- `src/application/auth/admin_create_user_use_case.py`
- `src/application/auth/list_users_use_case.py`
- `src/api/routes/admin_user_router.py`
- `src/api/main.py` (L1305-1344 팩토리, L2397-2399 override)
- `src/infrastructure/auth/user_repository.py` (find_all)
- `src/domain/auth/interfaces.py`
- `idt_front/src/pages/AdminUsersPage/index.tsx`
- `idt_front/src/components/admin/UserRegisterModal.tsx`

## History

| Version | Date | Match Rate | Note | By |
|---------|------|:----------:|------|-----|
| 0.1 | 2026-05-31 | 97% | 초기 Gap 분석 — 12/13 FR, 단일 트랜잭션·무회귀 확인, FR-11 UI만 후속 | bkit:gap-detector |
