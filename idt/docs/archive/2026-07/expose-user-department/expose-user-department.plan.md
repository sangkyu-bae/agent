# expose-user-department Plan Document

> **Feature**: expose-user-department — `/auth/me`에 부서 정보 노출 + org 부서 작성/승격 UI 완성
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **선행**: agent-memory-org-scope 완료(91%) — G1 이월 gap의 후속

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Phase 3(부서 공유 메모리)의 백엔드·hooks는 완성됐지만, 프론트 `/auth/me`(UserResponse)에 부서 정보가 없어 부서 작성·승격 **UI를 만들 수 없다** — 팀원이 org 메모리를 열람만 하고 기여(작성/승격)할 수 없는 반쪽 상태 |
| **Solution** | `/auth/me`가 `get_auth_context`로 조립되는 부서 정보(primary_department_id·department_ids)를 UserResponse에 additive 노출 → 프론트가 부서 컨텍스트 확보 → SettingsPage에 admin 부서 작성 폼 + 개인 메모리 "부서로 승격" 버튼 활성화(hooks·service 준비 완료) |
| **Function UX Effect** | `/settings`에서 관리자가 부서 메모리를 직접 작성하고, 누구나 자기 개인 메모리를 "부서로 승격"할 수 있다 — 팀 지식 기여 경로 완성 |
| **Core Value** | growing-agent "개인→조직" 승격 축의 마지막 UI 조각 — 부서 지식이 열람뿐 아니라 **기여 가능**해져 실제 팀 자산 축적 루프가 닫힌다 |

---

## 1. 배경 / 문제 (실코드 확인)

- `/auth/me`(`auth_router.py:122`)는 `UserResponse{id,email,role,status,display_name}`만 반환 — 부서 없음.
- `AuthContext`(get_auth_context 조립)에는 `primary_department_id`·`department_ids`·`department_names`가 이미 존재 — **데이터는 조립되나 /me가 노출 안 함**.
- 프론트 `useMe`→`authService.me()`가 `User`(부서 없음)를 반환. org create/promote 훅은 dept_id를 인자로 받지만 UI가 그 값을 얻을 소스가 없음.

## 2. 목표 / 범위

### In Scope

1. **백엔드**: `/auth/me`를 `get_auth_context` 기반으로 확장 — `UserResponse`에 `department_id`(primary)·`department_ids`·`department_names` additive 필드. 기존 필드·소비자 무변경
2. **프론트 타입**: `User`(또는 me 응답 타입)에 부서 필드 추가 → `useMe`로 접근
3. **프론트 UI**: SettingsPage
   - 개인 메모리 카드에 "부서로 승격" 버튼 — 사용자의 primary_department_id로 `usePromoteMemory`
   - 부서 공유 섹션에 (admin) 작성 폼 — `useCreateOrgMemory`
   - 부서 미소속 사용자는 승격/작성 미노출

### Out of Scope

- 다부서 선택 UI(사용자가 여러 부서일 때 어느 부서로 승격할지 선택) — 1차는 primary_department_id 고정, 다부서 선택은 후속
- 부서장 롤 도입 (admin 기준 유지)
- 백엔드 org 로직 변경 (Phase 3에서 완성 — 이번은 노출·UI만)

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | `/auth/me` 응답에 department_id·department_ids·department_names additive | get_auth_context 재사용 |
| FR-02 | 기존 /me 소비자(useMe·authStore) 무회귀 — 신규 필드는 optional | |
| FR-03 | 개인 메모리 "부서로 승격" 버튼 — primary_department_id 사용, 성공 시 org 목록 갱신 | usePromoteMemory 재사용 |
| FR-04 | 부서 공유 섹션 admin 작성 폼 — useCreateOrgMemory, 성공 시 갱신 | |
| FR-05 | 부서 미소속(department_id null) 사용자는 승격·작성 UI 미노출 | |
| FR-06 | 승격 중복(409)·상한(422) 에러 문구 표면화 | 기존 errorDetail 재사용 |

## 4. 성공 기준

- Match ≥ 90%, 기존 auth·memory 테스트 회귀 0
- 부서 소속 사용자가 승격/작성 왕복, 미소속은 UI 없음 — 테스트로 검증

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| /me 확장이 auth 조립 비용 증가 | get_auth_context는 이미 다른 라우터에서 사용 — 동일 비용, 캐시 대상 |
| 다부서 사용자의 승격 대상 모호 | 1차 primary_department_id 고정 + Design에서 다부서 UI 여부 결정 |
| 부서 정보 노출 민감도 | department_id/name은 이미 AuthContext·다른 화면에서 노출 — 신규 민감정보 아님 |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | /me 조립 방식 | get_auth_context 의존성 교체 vs get_current_user 유지 + 부서 별도 조회 |
| ② | 승격 대상 부서 | primary 고정 vs 다부서 선택 드롭다운 |
| ③ | 응답 타입 | UserResponse 확장 vs 신규 MeResponse |

## 7. 참조

- 대상: `auth_router.py:122`(me) · `schemas/auth/response.py`(UserResponse) · `dependencies/auth.py`(get_auth_context)
- 프론트: `types/auth.ts`(User) · `services/authService.ts`(me) · `hooks/useAuth.ts`(useMe) · `pages/SettingsPage`(OrgSection·MemoryItem)
- 준비됨: `usePromoteMemory`·`useCreateOrgMemory`·memoryService(promote/createOrg) — [[project-agent-memory-org-scope-completion]]
