# expose-user-department Gap Analysis (Check)

> **Design**: `docs/02-design/features/expose-user-department.design.md`
> **Analyzer**: 메인 세션 실측 (grep + 테스트 — 소형 기능)
> **Date**: 2026-07-20
> **Match Rate**: **100%** (사용자 지정 3결정·FR 전건 실측 일치, Gap 0)

---

## 1. Overall Scores

| Category | Score |
|----------|:-----:|
| Design Match (사용자 지정 3결정) | 100% |
| FR-01~06 | 100% |
| 회귀 (기존 me 소비자·auth) | 0건 |
| **Overall** | **100%** |

## 2. 사용자 지정 3결정 실측

| # | 결정 | 확인 | 방법 |
|---|------|:----:|------|
| ① | get_current_user 유지 + 부서 별도 조회 (get_auth_context 미교체) | ✅ | `grep get_auth_context auth_router.py` = 0, UC가 `find_departments_by_user` 재사용(2회) |
| ② | 다부서 선택 드롭다운 | ✅ | SettingsPage `showDeptPick`·`departments.length > 1` select (승격·작성 양쪽) |
| ③ | 신규 MeResponse (UserResponse 무변경) | ✅ | `/me` response_model=MeResponse, UserResponse는 타 소비자용으로 유지(4회 참조) |

## 3. FR 매칭

| FR | 확인 |
|----|:----:|
| FR-01 /me에 department_id·name·is_primary additive | ✅ MeResponse.departments |
| FR-02 기존 me 소비자 무회귀(optional) | ✅ 프론트 User.departments? optional, UserResponse 무변경 |
| FR-03 개인 메모리 승격(primary 사용) | ✅ MemoryItem 승격 버튼(1개 즉시·다부서 select) |
| FR-04 admin 작성 폼 | ✅ OrgSection canWrite=admin&&departments |
| FR-05 미소속 UI 미노출 | ✅ departments.length>0 조건 + UC 미소속 early return([]) |
| FR-06 409/422 표면화 | ✅ errorDetail 재사용 |

## 4. Gap 목록

**없음** — 사용자가 직접 지정한 3결정을 그대로 구현, FR 전건 존재.

## 5. 정당한 편차

- 없음. (프론트에서 useMe로 role·departments를 단일 소스로 읽는 것은 설계 §3-2 명시 그대로)

## 6. 테스트 결과

- 백엔드: GetUserDepartmentsUseCase 3 + /me 라우터 3(부서 포함·빈 리스트·401) = 6 통과, main import OK
- 프론트: SettingsPage 16(승격 노출/미소속 없음/promote 요청/admin 작성 폼) + 훅 10 통과
- 내 변경 파일 tsc 클린 (handlers.ts:310은 HEAD 동일 선재 에러 — LLM 모델 mock, 무관, git show 대조 확인)

## 7. 이월

- E2E: 다부서 사용자의 승격 대상 선택·admin 부서 작성 왕복 — 실서버
- 다부서 승격 시 primary 자동선택 vs 매번 선택 UX 튜닝 (현재 1개=즉시, 2개+=선택)

## 8. 총평

사용자 지정 3결정과 FR 전건이 실측으로 일치, org-scope G1(부서 기여 UI)을 완전 해소 — Match 100%. `/pdca report` 진행 가능. growing-agent "개인→조직" 승격 루프 완성.
