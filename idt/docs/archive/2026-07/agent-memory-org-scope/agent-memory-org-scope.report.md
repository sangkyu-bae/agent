# agent-memory-org-scope Completion Report (메모리 Phase 3)

> **Feature**: agent-memory-org-scope — 부서(org) 공유 메모리 + 승격
> **Author**: 배상규
> **Cycle**: Plan → Design → Do → Check → Report (2026-07-20 당일 완결)
> **Match Rate**: **91%** (백엔드 100%, 프론트 부서 작성/승격 UI는 데이터 gap으로 이월)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | agent-memory-org-scope (growing-agent 메모리 축 3단계 — 개인→조직 승격) |
| 기간 | 2026-07-20 당일 사이클 |
| 산출물 | 백엔드 additive 10파일 + 프론트 7파일 · **마이그레이션 0**(V050 슬롯 재사용) |
| Match Rate | 91% — 백엔드 100%, G1(프론트 부서 작성/승격 UI) 이월 |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 백엔드 테스트 | 6스위트 93건 통과(org 신규 ~25) + general_chat 회귀 25/25 |
| 프론트 테스트 | 훅 10 + SettingsPage 12, tsc 클린 |
| 마이그레이션 | **0** (실측 — V052+ 신규 파일 없음) |
| Act 반복 | 0회 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 메모리가 전부 개인 스코프 — 부서가 공유하는 용어·규정을 각자 등록, 정리한 지식이 팀에 전파되지 않음 |
| **Solution** | `scope='org'` 부서 메모리 계층 — 개인 메모리 승격(복사) + 관리자 직접 작성, 주입 시 개인+부서 병합. V050의 `scope`/`user_id` 예약 슬롯 재사용으로 **마이그레이션 0** |
| **Function UX Effect** | `/settings`에 "부서 공유 메모리" 열람 섹션, 답변은 개인+부서 배경 병합(부서는 "(부서 공유)" 라벨), 예산 캡 합산으로 폭주 차단 |
| **Core Value** | growing-agent 7원칙 중 **"개인 학습 → 조직 지식" 승격 축** — 메모리가 팀 자산이 되며, admin+소속 부서 게이트로 무단 전파 차단 |

---

## 2. 구현 결과

- **저장**: V050 무변경 — scope='org'·user_id=부서id 신규 행. **FR-07 핵심 안전장치**: `find_active_by_user`/`find_by_user_and_status`/`count_by_user_and_status`에 `scope='user'` 가드 3곳 추가 → user_id 슬롯 재사용에도 개인 조회가 org 행에 오염되지 않음(회귀 테스트로 고정)
- **주입**: assembler `build_block(dept_ids)` 확장 — 개인∪부서 병합(content 중복 시 개인 유지), 개인 우선 정렬, 단일 합산 캡. general_chat이 `auth_ctx.department_ids` 전달
- **CRUD**: `list_org`·`create_org`(부서 상한)·`promote`(복사·중복 거부). 라우터는 `_require_dept_membership`(admin 또는 소속 부서, 비소속 403)·승격 중복 409
- **프론트**: 계약 5종·훅 3종·MSW 3핸들러 + SettingsPage 부서 공유 메모리 읽기 섹션

## 3. Lessons Learned

1. **예약 컬럼의 배당이 3연속** — Phase 1이 넣어둔 scope/user_id nullable 덕에 Phase 2(pending)·Phase 3(org) 모두 마이그레이션 0. 선반영 설계의 복리.
2. **슬롯 재사용에는 반드시 판별 조건을 명시** — user_id를 개인/부서가 공유하면, 기존 조회에 scope 가드를 넣지 않으면 조용히 오염된다. FR-07을 구현 1순위로 두고 회귀 테스트로 고정한 것이 핵심.
3. **설계의 암묵 전제를 Do에서 실측으로 검증** — 설계는 "프론트가 부서 정보 가용"을 전제했으나 `/auth/me`(User 타입)에 department_id 부재. 억지로 부서 UI를 만들지 않고 gap으로 정직하게 이월(Phase 1 SettingsPage 스텁 발견과 동형).

## 4. 이월 항목

| 항목 | 비고 |
|------|------|
| **G1: 부서 작성/승격 UI** | 후속 `expose-user-department` — `/auth/me`에 department_id 추가 + SettingsPage admin 폼·승격 버튼(hooks·service·MSW 준비 완료) |
| E2E 실측 | 같은 부서 사용자 2명 org 메모리 공유·병합 주입 확인 — 실서버 |
| 만료 배치 | expires_at 기반 만료 (Phase 3 out-of-scope 유지) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 당일 사이클 완결 — Match 91%(백엔드 100%), 마이그레이션 0, G1 이월 | 배상규 |
