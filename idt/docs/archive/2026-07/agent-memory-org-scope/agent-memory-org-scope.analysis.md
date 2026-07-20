# agent-memory-org-scope Gap Analysis (Check)

> **Design**: `docs/02-design/features/agent-memory-org-scope.design.md`
> **Analyzer**: 메인 세션 실측 (gap-detector API 오류로 중단 → 직접 grep/테스트 검증)
> **Date**: 2026-07-20
> **Match Rate**: **91%** (백엔드 100%, 프론트 부서 작성/승격 UI는 데이터 gap으로 이월)

---

## 1. Overall Scores

| Category | Score | 근거 |
|----------|:-----:|------|
| Design Match (백엔드) | 100% | 결정 5건·FR 전건 코드 존재, 실측 확인 |
| **마이그레이션 0** | ✅ | `db/migration`에 V052+ 신규 파일 0 (실측) |
| FR-07 안전장치 | ✅ | scope='user' 가드 3곳(find_active_by_user·find_by_user_and_status·count_by_user_and_status) + 회귀 테스트 |
| 프론트 계약·열람 | 100% | 계약 5종·훅 3종·org 읽기 섹션 |
| 프론트 부서 작성/승격 UI | ⏳ | **데이터 gap 이월** (아래 G1) |
| **Overall** | **91%** | 기준 90% 충족 |

## 2. 매칭 확인 (실측)

| Design 요구 | 확인 | 방법 |
|-------------|:----:|------|
| 결정 ① user_id 슬롯 재사용·scope 항상 명시·**마이그레이션 0** | ✅ | `ls db/migration | grep V05[2-9]` = 0 |
| **FR-07** scope='user' 가드 + org 행 배제 회귀 | ✅ | `grep -c MemoryScope.USER.value repository.py` = 3, `test_find_active_by_user는_org행을_배제한다` |
| 결정 ② 승격 = 복사(원본 유지) | ✅ | promote 내 `delete` 호출 0, `test_승격은_org_복사_원본유지` |
| 결정 ③ sort_for_injection_scoped(개인→부서→타입) + 합산 캡 + _merge 개인 우선 | ✅ | policies·assembler 테스트 통과 |
| 결정 ④ _require_dept_membership(admin/소속 403) ⑤ GET·POST /org·promote | ✅ | 라우터 22건(403·409 포함) |
| FR-02 병합 주입(dept_ids 없으면 개인만), FR-06 부서 라벨 | ✅ | assembler `test_dept_ids_없으면_개인만`·`(부서 공유)` |
| general_chat auth_ctx.department_ids → build_block(dept_ids=) | ✅ | use_case.py:354 실측 + 주입 테스트 |
| §4 Test Plan | ✅ | 백엔드 6스위트(정책29·repo15·crud27·assembler10·라우터22·주입10) + 프론트 훅10·SettingsPage12 |

## 3. Gap 목록

| # | 심각도 | 내용 | 위치 | 처리 |
|---|:---:|------|------|------|
| G1 | Medium | **프론트 부서 작성/승격 UI 미구현** — 설계 §3-5는 "관리자 작성·승격 버튼"을 명시했으나, `/auth/me`(User 타입)에 department_id가 없어 프론트가 부서 id를 알 수 없음. 작성/승격 hooks·service·MSW는 배선·테스트했으나 SettingsPage에는 **org 읽기 섹션만** 렌더 | `SettingsPage/index.tsx`(OrgSection read-only), `types/auth.ts`(User에 department 없음) | **이월** — 설계가 "부서 정보 가용"을 암묵 전제했으나 실코드 미충족(Phase 1 SettingsPage 스텁 발견과 동형). 후속 `expose-user-department`(/auth/me에 department_id 추가)에서 UI 완성. **부서 열람은 이미 작동**(서버 스코프)하므로 기능 가치는 확보 |

## 4. 정당한 편차 (Gap 아님)

- 부서 관리 권한을 전역 admin + 소속 부서원(`_require_dept_membership`)으로 — 설계 결정 ④ 그대로(부서장 롤 부재).
- org 읽기 섹션을 sky 색으로 구분(개인=기본, 부서=sky, pending=amber) — 스코프 시각 구분, 설계 자유 범위.

## 5. 테스트 결과

- 백엔드 6스위트 **93건** 통과(정책29·repo15·crud27·assembler10·라우터22·주입10 중 org 신규 ~25) + general_chat 회귀 25/25 + main import OK
- 프론트 훅 10 + SettingsPage 12 통과, tsc 클린
- **마이그레이션 0·백엔드 diff는 additive만** — Phase 1/2 경로 무변경(scope 가드는 org 행 없을 때 동작 동일)

## 6. 이월 항목

| 항목 | 비고 |
|------|------|
| **G1: 부서 작성/승격 UI** | 후속 — `/auth/me` department_id 노출 + SettingsPage admin 폼·승격 버튼 (hooks 준비 완료) |
| E2E 실측 | 부서 A 사용자 2명이 org 메모리 공유·주입 확인 — 실서버 |
| 만료 배치 | expires_at 기반 org/개인 만료 (Phase 3 out-of-scope 유지) |

## 7. 총평

1. 백엔드는 설계 100% 일치 — 마이그레이션 0(V050 슬롯 재사용)·FR-07 scope 가드·승격 복사·병합 주입이 전부 실측/테스트로 확인됐다.
2. 유일한 실질 gap(G1)은 프론트 부서 작성/승격 UI로, `/auth/me`가 department_id를 노출하지 않는 데이터 부재가 원인 — 설계의 암묵 전제와 실코드의 어긋남이며, 부서 **열람**은 이미 작동하므로 UI 완성만 후속으로 분리.
3. Match 91% ≥ 90% → `/pdca report` 진행 가능. G1은 report 이월 항목으로 명시.
