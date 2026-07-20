# agent-memory-extraction Plan Document (메모리 Phase 2)

> **Feature**: agent-memory-extraction — 대화 자동 메모리 추출 + 승인 게이트
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **선행**: agent-memory Phase 1 (아카이브 완료 98% — `docs/archive/2026-07/agent-memory/`)
> **비전 근거**: `docs/architecture/growing-agent-vision.md` 메모리 축 2단계 (extract→reconcile→store 파이프라인 + 인간 승인 게이트)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Phase 1 메모리는 사용자가 직접 등록해야만 쌓인다 — 대화에서 반복 드러나는 배경 정보(소속·용어 교정·선호)를 사용자가 매번 옮겨 적지 않으면 에이전트는 성장하지 않는다 |
| **Solution** | 대화 종료 후 백그라운드 LLM 추출로 메모리 후보를 `pending`으로 적재하고, 사용자가 `/settings`에서 승인/거부해야만 주입 대상(`active`)이 된다 — Phase 1 스키마의 예약 컬럼(status/source_run_id/confidence)을 그대로 사용, 마이그레이션 0 |
| **Function UX Effect** | 채팅은 기존과 동일(추출은 비동기 격리, 실패해도 무영향). `/settings`에 "승인 대기" 섹션이 추가되어 후보를 원클릭 승인/거부 — 승인 즉시 다음 질문부터 반영 |
| **Core Value** | growing-agent 7원칙 중 "인간 승인 게이트 + 출처 불변식(source_run_id)"의 메모리 축 구현 — 자동 학습의 이득과 금융 도메인의 보수성(무단 학습 금지)을 동시에 충족 |

---

## 1. 배경 / 문제

- Phase 1(수동 CRUD + 상주 주입)은 완결됐지만 등록 주체가 사용자뿐 — "쓰면서 성장"이 없다.
- 위키 축은 이미 distill(자동) → draft → 관리자 승인 구조를 운영 중. 메모리 축만 자동 유입 경로가 없다.
- Phase 1 스키마가 이 확장을 선반영해 둠: `status='pending'`, `source_run_id`(추출 출처 run), `confidence`(<100). **테이블 변경 없이 착수 가능.**

## 2. 목표 / 범위

### In Scope (Phase 2)

1. **추출 파이프라인 (백엔드)**
   - General Chat 답변 완료 후(`_persist_messages` 이후) **fire-and-forget 백그라운드 추출** — `section_summary/launcher.py`의 `asyncio.create_task` + guarded 러너 선례 재사용
   - LLM 1회 structured output: 이번 턴(사용자 질문+답변)에서 저장 가치가 있는 사실만 후보 추출 (mem_type 4종 분류 + confidence 자체 평가)
   - 후보는 `status=pending`, `source_run_id=run_id`(관측성 연결), `confidence=LLM 평가값`으로 저장
2. **정합(reconcile) — 최소 규칙**
   - 기존 메모리(active+pending) 목록을 추출 프롬프트에 제공해 중복 억제 (위키 distill의 중복 검사 부재 실수 반복 금지)
   - 저장 직전 content 정확 일치 중복은 코드로 차단
3. **승인 게이트 (API + 프론트)**
   - `PATCH /memories/{id}/approve` (pending→active) / `PATCH /memories/{id}/reject` (pending→rejected) — 본인 것만, 404 은닉 규칙 동일
   - `GET /memories`에 pending 목록 포함(구분 필드) 또는 status 쿼리 — Design에서 확정
   - `/settings`에 "승인 대기" 섹션: 후보 content + 근거(어느 대화에서) + 승인/거부 버튼
4. **가드**
   - 사용자당 pending 상한(신규 config) — 폭주 방지, 초과 시 추출 스킵
   - 전역 on/off config (기본 off로 배포 → 검증 후 on)

### Out of Scope (Phase 3+)

- org 스코프 공유 메모리, Tier 1 온디맨드 검색, expires_at 기반 만료 배치, 추출 대상 확장(Supervisor/Excel 경로), 메모리 자동 수정·병합(LLM reconciler), 임베딩 유사도 중복 검사

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | 답변 완료 후 백그라운드 추출 — 채팅 스트림 지연·실패 전파 0 | launcher 선례, 예외는 warning |
| FR-02 | 추출 결과는 반드시 `pending` — active 직행 금지 | 승인 게이트 원칙 |
| FR-03 | `source_run_id` 기록 — 어떤 대화에서 나왔는지 추적 가능 | 출처 불변식 |
| FR-04 | 기존 메모리 제공 + content 정확 일치 차단으로 중복 억제 | distill 실수 재발 방지 |
| FR-05 | 추출 0건이면 아무것도 저장하지 않음 (빈 후보 강제 금지) | |
| FR-06 | pending은 주입에 절대 포함되지 않음 | Phase 1 `find_active_by_user`가 이미 보장 — 회귀 테스트로 고정 |
| FR-07 | 승인/거부는 본인만, 타인·미존재 404 은닉 | Phase 1 계약 승계 |
| FR-08 | pending 상한 도달 시 추출 스킵 (에러 아님, debug 로그) | |
| FR-09 | 전역 off 시 추출 경로 완전 비활성 — Phase 1 동작과 100% 동일 | optional 의존성 선례 |
| FR-10 | 프론트 승인 대기 섹션 — 승인 시 목록 이동, 거부 시 제거 | |

## 4. 성공 기준

- Match Rate ≥ 90%, 기존 general_chat·memory 테스트 회귀 0
- off 상태에서 Phase 1과 바이트 동일 동작 (assembler/CRUD 무영향)
- 추출→pending→승인→주입 전 구간 단위 테스트로 검증 (E2E는 실서버 이월)

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| LLM이 매 턴 후보를 남발 → pending 폭주 | 프롬프트에 "저장 가치 기준" 명시 + 턴당 추출 상한 + pending 총량 상한(FR-08) |
| 민감 정보(PII)가 메모리로 추출 | 프롬프트 금지 지침 + content는 승인 전 사용자 눈으로 확인하는 구조 자체가 게이트. pii_masking 연동은 Design에서 판단 |
| 추출 LLM 비용 | 전역 off 기본 + 경량 모델 지정 config + 짧은 입력(마지막 턴만) |
| 백그라운드 태스크 미완료 유실 | fire-and-forget 허용 손실로 명시(추출은 best-effort) — 잡 테이블 미도입 |
| 이벤트 루프 내 세션 충돌 | 러너는 session_factory per-call (launcher·assembler 선례) |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 추출 입력 범위 | 마지막 턴만 vs 최근 N턴 — 비용·품질 트레이드오프 |
| ② | 추출 LLM 지정 방식 | config 고정(search_pipeline 선례) vs 기본 LLM 재사용 |
| ③ | pending 노출 API 형태 | GET /memories에 status 쿼리 vs 응답에 pending 배열 동봉 |
| ④ | 근거 표시 | source_run_id → 대화 링크 조회 여부 (retrieval-observability 조회 API 재사용 가능성) |
| ⑤ | 훅 위치 | stream() 내 create_task vs CHAT_DONE 이후 라우터 레벨 — 관측성(run_id 접근)과 격리 관점 비교 |

## 7. 참조

- 선행 사이클: `docs/archive/2026-07/agent-memory/` (특히 design §3-3 assembler·§3-1 스키마 예약 컬럼)
- 백그라운드 잡 선례: `src/application/section_summary/launcher.py`
- 승인 게이트 선례: wiki draft→approve (`wiki/review_use_case.py`)
- 훅 지점: `src/application/general_chat/use_case.py:381` (_persist_messages) 이후
