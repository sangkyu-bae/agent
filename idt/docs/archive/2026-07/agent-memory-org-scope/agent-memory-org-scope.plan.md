# agent-memory-org-scope Plan Document (메모리 Phase 3)

> **Feature**: agent-memory-org-scope — 부서(org) 공유 메모리 + 승인 게이트
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **선행**: agent-memory Phase 1(수동 CRUD·주입) + Phase 2(자동 추출·승인) 완료·아카이브
> **비전 근거**: growing-agent-vision 메모리 축 3단계 — "개인 → 조직 지식 승격" + 부서 공유

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 지금 메모리는 전부 개인(user) 스코프 — 같은 부서가 공유하는 용어·규정·업무 배경을 각자 따로 등록해야 하고, 한 사람이 정리한 지식이 팀에 전파되지 않는다 |
| **Solution** | `scope='org'` 부서 메모리 계층 — 개인 메모리를 부서로 **승격(promote)**하거나 관리자가 직접 부서 메모리 작성. 주입 시 개인 + 소속 부서 메모리를 병합. **마이그레이션 0**: V050의 `scope` 예약 컬럼 사용 |
| **Function UX Effect** | `/settings`에 "부서 공유 메모리" 섹션 — 관리자는 작성·승인, 팀원은 열람. 개인 메모리에 "부서로 승격" 버튼. 답변은 개인+부서 배경을 함께 반영 |
| **Core Value** | growing-agent 7원칙 중 "개인 학습 → 조직 지식" 승격 축 — 메모리가 개인을 넘어 팀 자산이 되며, 거버넌스(부서 관리자 승인 게이트)로 무단 전파를 막는다 |

---

## 1. 배경 / 문제 (실코드 확인)

- V050 `agent_memory.scope VARCHAR(10) DEFAULT 'user'` + `user_id NULL 허용` — **org 스코프 예약 완료**. `find_active_by_user`가 user_id 고정이라 org는 미조회.
- `AuthContext.department_ids: tuple` / `primary_department_id` 존재 — 사용자 부서 소속 정보 런타임 접근 가능.
- 부서 CRUD·권한은 `require_role("admin")`(department_router) — 부서 메모리 관리 권한의 기준선 존재.
- Phase 2까지 개인 스코프만 실사용, org 컬럼은 스키마에만 존재.

## 2. 목표 / 범위

### In Scope (Phase 3)

1. **org 메모리 스토리지** — `scope='org'` + `user_id`에 부서 ID 저장(또는 별도 dept 컬럼 — Design 결정). 조회는 소속 부서 기준
2. **승격(promote)** — 개인 active 메모리를 부서 메모리로 복사/이동 (원본 유지 여부 Design 결정). 관리자 권한
3. **직접 작성** — 관리자가 부서 메모리 직접 등록 (CRUD)
4. **병합 주입** — General Chat 주입 블록에 개인 + 소속 부서 메모리 합쳐 렌더 (기존 assembler 확장, 예산 캡 공유)
5. **프론트** — `/settings` "부서 공유 메모리" 섹션(열람 전체·작성/승격 관리자), 개인 메모리 "부서로 승격" 버튼

### Out of Scope

- org 스코프 자동 추출(Phase 2 추출은 user 고정 유지)
- 다부서 교차 공유·전사(global) 메모리
- 부서 메모리 승인 워크플로우의 다단계(작성=관리자라 즉시 active)
- 부서 간 이관·병합

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | org 메모리 조회는 사용자 소속 부서(department_ids) 기준 | AuthContext 활용 |
| FR-02 | 주입 블록 = 개인 active + 부서 active 병합, 기존 문자 예산 캡 공유(폭주 방지) | assembler 확장 |
| FR-03 | 부서 메모리 작성·승격·삭제는 부서 관리 권한(admin 기준선) | require_role 선례 |
| FR-04 | 승격은 개인 메모리를 org로 — 원본 처리(유지/삭제) Design 확정 | |
| FR-05 | org 메모리에 개인 상한과 별도 부서 상한 | config 신규 |
| FR-06 | 병합 주입 블록에 개인/부서 출처 구분 표시(사용자 신뢰) | 렌더 라벨 |
| FR-07 | 기존 개인 메모리·Phase 2 추출 회귀 0 (scope='user' 경로 무변경) | |

## 4. 성공 기준

- Match ≥ 90%, Phase 1/2 회귀 0, 마이그레이션 0
- 병합 주입 시 예산 캡이 개인+부서 합산에 적용됨(폭주 없음) 검증

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| 부서 메모리가 많으면 개인 메모리를 캡에서 밀어냄 | 정렬 우선순위에 스코프 반영(개인 우선 or 타입 우선 — Design) + 합산 캡 |
| user_id 컬럼에 부서 ID 혼용 시 조회 오염 | Design 결정 ① — dept_id 별도 컬럼 없이 scope로 구분 vs 컬럼 추가(마이그레이션 발생) 트레이드오프 |
| 승격 시 개인/부서 중복 | content 정확 일치 dedup (Phase 2 dedup_candidates 재사용) |
| 다부서 소속 사용자의 주입량 폭증 | 부서별 상한 + 합산 캡 |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 부서 식별 저장 | `user_id` 컬럼에 dept_id 재사용(scope로 구분, 마이그레이션 0) vs `org_id` 컬럼 추가(V052 — 명확하나 마이그레이션) |
| ② | 승격 원본 처리 | 개인 원본 유지(복사) vs 이동(삭제) |
| ③ | 병합 정렬·캡 배분 | 개인 우선 vs 타입 우선, 부서/개인 예산 분리 vs 합산 단일 캡 |
| ④ | 부서 관리 권한 | 전역 admin만 vs 부서장 개념 도입(현재 부서장 롤 부재 — admin 기준선) |
| ⑤ | 조회 API 형태 | GET /memories?scope=org vs 별도 엔드포인트 |

## 7. 참조

- 스키마: V050 `agent_memory`(scope·user_id nullable 예약) — [[project-agent-memory-completion]]
- 병합 지점: `MemoryContextAssembler` (Phase 1) · dedup: `MemoryPolicy.dedup_candidates`(Phase 2)
- 부서·권한: `AuthContext.department_ids` · `department_router`(require_role admin)
- 선행 완료: [[project-agent-memory-extraction-completion]]
