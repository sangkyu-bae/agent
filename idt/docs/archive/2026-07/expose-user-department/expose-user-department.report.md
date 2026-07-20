# expose-user-department Completion Report

> **Feature**: expose-user-department — `/auth/me` 부서 노출 + org 부서 작성/승격 UI
> **Author**: 배상규
> **Cycle**: Plan → Design → Do → Check → Report (2026-07-20 당일 완결)
> **Match Rate**: **100%** (사용자 지정 3결정·FR 전건 일치, Act 0회)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | expose-user-department (agent-memory-org-scope G1 후속) |
| 기간 | 2026-07-20 당일 사이클 |
| 산출물 | 백엔드 신규 2 + 수정 3 · 프론트 수정 5 · 마이그레이션 0 |
| Match Rate | 100% — Gap 0 |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 백엔드 테스트 | UC 3 + /me 라우터 3 = 6 통과, main import OK |
| 프론트 테스트 | SettingsPage 16 + 훅 10 |
| 회귀 | 0건 (UserResponse·기존 me 소비자 무변경) |
| Act 반복 | 0회 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | Phase 3 백엔드·hooks는 완성됐지만 `/auth/me`에 부서 정보가 없어 부서 작성·승격 UI를 만들 수 없어, 팀원이 org 메모리를 열람만 하고 기여 못 하는 반쪽 상태(org-scope G1) |
| **Solution** | `/me`가 이미 조립 가능한 부서 정보(find_departments_by_user)를 신규 MeResponse로 additive 노출 → SettingsPage 승격 버튼·admin 작성 폼 활성화 (Phase 3 배선 hooks 연결) |
| **Function UX Effect** | 관리자가 부서 메모리 직접 작성, 누구나 개인 메모리를 "부서로 승격"(1부서 즉시·다부서 드롭다운). 미소속은 UI 미노출 |
| **Core Value** | growing-agent "개인 학습 → 조직 지식" 승격 축의 마지막 UI 조각 — 부서 지식이 열람뿐 아니라 **기여 가능**해져 팀 자산 축적 루프가 닫힘 |

---

## 2. 구현 결과 (사용자 지정 3결정)

- **결정 ①** get_current_user 유지 + 부서 별도 조회 — `GetUserDepartmentsUseCase`가 `find_departments_by_user`(단일) + `list_all`(이름 map 1회, N+1 회피). get_auth_context(권한 조립) 미교체로 /me 비용 최소 증가
- **결정 ②** 다부서 선택 드롭다운 — 승격/작성 모두 부서 1개면 즉시, 2개+면 select
- **결정 ③** 신규 MeResponse — UserResponse 무변경(타 소비자 4곳 보호), /me만 전환
- 미소속(department_id 없음)은 승격/작성 UI 미노출(FR-05), UC도 링크 없으면 부서 조회 스킵

## 3. Lessons Learned

1. **정직한 gap 이월이 소형 사이클로 깔끔하게 회수** — org-scope에서 "프론트 부서 정보 부재"를 억지로 메우지 않고 G1으로 남긴 것이, 여기서 사용자 결정 3건과 함께 100% 사이클로 완결. 부채를 명시적 태스크로 남기는 것의 가치.
2. **데이터는 이미 있고 노출만 없던 케이스 반복** — AuthContext가 부서를 조립하지만 /me가 UserResponse로 잘라 반환하던 구조. "부족한 건 계산이 아니라 노출 경로"라는 패턴이 또 확인됨(retrieval-observability·agent-workspace-view와 동형).
3. **응답 타입 분리로 회귀 0** — /me만 MeResponse로 바꾸고 UserResponse는 유지 → 로그인·기타 소비자 무영향.

## 4. 이월 항목

| 항목 | 비고 |
|------|------|
| E2E | 다부서 사용자 승격 대상 선택·admin 부서 작성 왕복 — 실서버 |
| UX 튜닝 | 다부서 승격 시 primary 자동 vs 매번 선택 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 당일 사이클 완결 — Match 100%, org-scope G1 해소 | 배상규 |
